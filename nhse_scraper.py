
import io, os, zipfile, pandas as pd, requests
from dataclasses import dataclass
from typing import List

NHSE_HEADERS = {"User-Agent": "HospitalFlowDashboard/1.0 (education use)"}
CACHE_DIR = os.path.join(os.path.dirname(__file__), "data", "nhse_cache"); os.makedirs(CACHE_DIR, exist_ok=True)

@dataclass
class PeerSet:
    providers: List[str]

def _cache_path(name: str) -> str: return os.path.join(CACHE_DIR, name)
def _download(url: str) -> bytes:
    r = requests.get(url, headers=NHSE_HEADERS, timeout=60); r.raise_for_status(); return r.content

AEM_MONTH_FILES = [
    ("2025-03","https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2025/04/A-E-Monthly-March-2025.csv"),
    ("2025-02","https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2025/05/A-E-Monthly-February-2025-1.csv"),
    ("2025-01","https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2025/02/A-E-Monthly-January-2025.csv"),
    ("2024-12","https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2025/01/A-E-Monthly-December-2024.csv"),
]

def fetch_ae_monthly_provider(peers: PeerSet) -> pd.DataFrame:
    frames=[]
    for label,url in AEM_MONTH_FILES:
        cache=_cache_path(f"ae_{label}.csv")
        if os.path.exists(cache): df=pd.read_csv(cache)
        else:
            b=_download(url); df=pd.read_csv(io.BytesIO(b)); df.to_csv(cache, index=False)
        df["period"]=label; frames.append(df)
    ae=pd.concat(frames, ignore_index=True)
    prov_col = next((c for c in ae.columns if c.lower() in ["provider","provider name","provider_name","organisation","provider code"]), None)
    if prov_col is None:
        if "Provider Name" in ae.columns: prov_col="Provider Name"
        else: raise ValueError("Provider column not found in A&E monthly file.")
    ae["PROVIDER"]=ae[prov_col].astype(str)
    if peers.providers:
        mask=False
        for p in peers.providers: mask = mask | ae["PROVIDER"].str.lower().str.contains(str(p).lower())
        ae = ae[mask]
    return ae

def fetch_ambulance_handover_timeseries(peers: PeerSet)->pd.DataFrame:
    # Placeholder: return empty; UI will guide user to share mapping
    return pd.DataFrame()

def fetch_acute_discharge_timeseries(peers: PeerSet)->pd.DataFrame:
    # Placeholder: return empty
    return pd.DataFrame()
