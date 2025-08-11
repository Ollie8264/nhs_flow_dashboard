
import io
import os
import re
import zipfile
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

import pandas as pd
import requests

NHSE_HEADERS = {"User-Agent": "HospitalFlowDashboard/1.0 (education use)"}

CACHE_DIR = os.path.join(os.path.dirname(__file__), "data", "nhse_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

@dataclass
class PeerSet:
    providers: List[str]  # provider names or ODS codes substrings to match (case-insensitive)

def _cache_path(name: str) -> str:
    return os.path.join(CACHE_DIR, name)

def _download(url: str) -> bytes:
    r = requests.get(url, headers=NHSE_HEADERS, timeout=60)
    r.raise_for_status()
    return r.content

def _read_csv_bytes(b: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(b))

def _read_excel_bytes(b: bytes, sheet_name=0) -> pd.DataFrame:
    return pd.read_excel(io.BytesIO(b), sheet_name=sheet_name, engine="openpyxl")

# ------------------------
# A&E Monthly (provider)
# ------------------------
AEM_BASE = "https://www.england.nhs.uk/statistics/statistical-work-areas/ae-waiting-times-and-activity/ae-attendances-and-emergency-admissions-2024-25/"

AEM_MONTH_FILES = [
    # (label, csv_url) - add more months as needed or scrape the page
    ("2025-03", "https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2025/04/A-E-Monthly-March-2025.csv"),
    ("2025-02", "https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2025/05/A-E-Monthly-February-2025-1.csv"),
    ("2025-01", "https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2025/02/A-E-Monthly-January-2025.csv"),
    ("2024-12", "https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2025/01/A-E-Monthly-December-2024.csv"),
]

def fetch_ae_monthly_provider(peers: PeerSet) -> pd.DataFrame:
    frames = []
    for label, url in AEM_MONTH_FILES:
        cache = _cache_path(f"ae_{label}.csv")
        if os.path.exists(cache):
            df = pd.read_csv(cache)
        else:
            b = _download(url)
            df = pd.read_csv(io.BytesIO(b))
            df.to_csv(cache, index=False)
        df["period"] = label
        frames.append(df)
    ae = pd.concat(frames, ignore_index=True)

    # Try to normalise provider column
    prov_col = next((c for c in ae.columns if c.lower() in ["provider code","provider","provider_name","organisation"]), None)
    if prov_col is None:
        # Common structure: "Provider Code" + "Provider Name"
        # Create a unified PROVIDER field
        if "Provider Name" in ae.columns:
            prov_col = "Provider Name"
        else:
            raise ValueError("Provider column not found in A&E monthly file.")
    ae["PROVIDER"] = ae[prov_col].astype(str)

    # Filter peers (substring match on name or code)
    if peers.providers:
        mask = False
        for p in peers.providers:
            p = str(p).lower().strip()
            mask = mask | ae["PROVIDER"].str.lower().str.contains(p)
        ae = ae[mask]

    # Select a small set of useful fields (names vary across months)
    wanted_cols = []
    candidates = [
        "Att attendances (type 1+2+3)", "Total Attendances", "All attendances",
        "Treated within 4 hours (all)","Patients spending > 4 hours from arrival to discharge, admission or transfer",
        "Total emergency admissions via A&E","% within 4 hours (all)"
    ]
    for c in ae.columns:
        if any(k.lower() in c.lower() for k in [ "attend", "within 4", "emergency admissions", "% within 4"]):
            wanted_cols.append(c)

    out = ae[["period","PROVIDER"] + wanted_cols].copy()
    return out

# ------------------------
# UEC Daily SitRep – Ambulance handovers weekly timeseries
# ------------------------
AMB_HANDOVER_URL = "https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2025/03/Web-File-Timeseries-Ambulance-Collection.xlsx"

def fetch_ambulance_handover_timeseries(peers: PeerSet) -> pd.DataFrame:
    cache = _cache_path("amb_handover.xlsx")
    if os.path.exists(cache):
        with open(cache, "rb") as f:
            b = f.read()
    else:
        b = _download(AMB_HANDOVER_URL)
        with open(cache, "wb") as f:
            f.write(b)
    # Typical sheet: "Ambulance handover delays by provider"
    xls = pd.ExcelFile(io.BytesIO(b))
    sheet = next((s for s in xls.sheet_names if "provider" in s.lower()), xls.sheet_names[0])
    df = pd.read_excel(io.BytesIO(b), sheet_name=sheet, engine="openpyxl")
    # Try to locate provider column
    prov_col = next((c for c in df.columns if "provider" in c.lower() and "code" not in c.lower()), None)
    if prov_col is None:
        prov_col = next((c for c in df.columns if "organisation" in c.lower()), None)
    if prov_col is None:
        raise ValueError("Provider column not found in Ambulance handover file.")
    df["PROVIDER"] = df[prov_col].astype(str)

    # Filter peers
    if peers.providers:
        mask = False
        for p in peers.providers:
            mask = mask | df["PROVIDER"].str.lower().str.contains(p.lower())
        df = df[mask]

    # Keep week end date and key metrics
    # Common metrics: arrivals, handover delays 15m/30m/60m
    time_cols = [c for c in df.columns if "week ending" in c.lower() or "week end" in c.lower() or "date" in c.lower()]
    if time_cols:
        df = df.melt(id_vars=["PROVIDER"], var_name="metric_or_date", value_name="value")
        # Heuristic: dates look like datetime or contain '202'
        mask_date = df["metric_or_date"].astype(str).str.contains("202") | pd.to_datetime(df["metric_or_date"], errors="coerce").notna()
        # Not perfect; depends on sheet format. Keep as-is for demo.
    return df

# ------------------------
# Acute Discharge Weekly SitRep (NCTR/MOFD proxy)
# ------------------------
ACUTE_DISCHARGE_URL = "https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2025/03/Web-File-Timeseries-Acute-Discharge-SitRep.xlsx"

def fetch_acute_discharge_timeseries(peers: PeerSet) -> pd.DataFrame:
    cache = _cache_path("acute_discharge.xlsx")
    if os.path.exists(cache):
        with open(cache, "rb") as f:
            b = f.read()
    else:
        b = _download(ACUTE_DISCHARGE_URL)
        with open(cache, "wb") as f:
            f.write(b)
    xls = pd.ExcelFile(io.BytesIO(b))
    sheet = next((s for s in xls.sheet_names if "provider" in s.lower()), xls.sheet_names[0])
    df = pd.read_excel(io.BytesIO(b), sheet_name=sheet, engine="openpyxl")
    prov_col = next((c for c in df.columns if "provider" in c.lower() and "code" not in c.lower()), None)
    if prov_col is None:
        raise ValueError("Provider column not found in Acute discharge file.")
    df["PROVIDER"] = df[prov_col].astype(str)

    if peers.providers:
        mask = False
        for p in peers.providers:
            mask = mask | df["PROVIDER"].str.lower().str.contains(p.lower())
        df = df[mask]

    return df

# ------------------------
# RTT – Full CSV ZIP (provider)
# ------------------------
def fetch_rtt_full_csv(month_label: str="2025-03") -> pd.DataFrame:
    # Convert to page link pattern; the monthly "Full CSV data file <MonYY> (ZIP)" is linked with predictable path
    # Provide a small lookup for recent months
    lookup = {
        "2025-03": "https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2025/07/rtt-full-csv-Mar25.zip",
        "2025-02": "https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2025/07/rtt-full-csv-Feb25.zip",
        "2025-01": "https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2025/02/rtt-full-csv-Jan25.zip",
        "2024-12": "https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2025/01/rtt-full-csv-Dec24.zip",
    }
    url = lookup.get(month_label)
    if url is None:
        raise ValueError("Month not in demo lookup; extend the list in fetch_rtt_full_csv.")
    cache = _cache_path(f"rtt_{month_label}.zip")
    if not os.path.exists(cache):
        b = _download(url)
        with open(cache, "wb") as f:
            f.write(b)
    else:
        with open(cache, "rb") as f:
            b = f.read()
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        # Find provider file (usually contains 'provider' and '.csv')
        name = next((n for n in z.namelist() if "provider" in n.lower() and n.lower().endswith(".csv")), None)
        if name is None:
            name = z.namelist()[0]
        with z.open(name) as f:
            df = pd.read_csv(f)
    return df

# ------------------------
# KH03 – Bed availability/occupancy (quarterly)
# ------------------------
KH03_Q4_2024_25_CSV = "https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2025/06/KH03-Q4-2024-25-data-CSV.csv"

def fetch_kh03_latest() -> pd.DataFrame:
    cache = _cache_path("kh03_q4_2024_25.csv")
    if os.path.exists(cache):
        return pd.read_csv(cache)
    b = _download(KH03_Q4_2024_25_CSV)
    df = pd.read_csv(io.BytesIO(b))
    df.to_csv(cache, index=False)
    return df

# ------------------------
# Utilities
# ------------------------
def rolling_12_week_average(df: pd.DataFrame, date_col: str, group_cols: List[str], value_col: str) -> pd.DataFrame:
    """Given a weekly time series, compute 12-week mean for each group."""
    x = df.copy()
    x[date_col] = pd.to_datetime(x[date_col])
    x = x.sort_values(date_col)
    x["avg_12w"] = x.groupby(group_cols)[value_col].transform(lambda s: s.rolling(12, min_periods=4).mean())
    return x

def normalise_provider_name(s: str) -> str:
    return str(s).replace("NHS FOUNDATION TRUST","").replace("NHS TRUST","").strip().lower()
