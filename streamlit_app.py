
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Hospital Flow Command Centre", layout="wide")

@st.cache_data
def load_data():
    ed = pd.read_csv("data/ed.csv", parse_dates=["date"])
    amb = pd.read_csv("data/ambulance.csv", parse_dates=["date"])
    ip = pd.read_csv("data/inpatients.csv", parse_dates=["date"])
    th = pd.read_csv("data/theatres.csv", parse_dates=["date"])
    wl = pd.read_csv("data/waiting_list.csv", parse_dates=["date"])
    return ed, amb, ip, th, wl

ed, amb, ip, th, wl = load_data()

# Filters
with st.sidebar:
    st.title("Filters")
    min_date = min(ed["date"].min(), ip["date"].min())
    max_date = max(ed["date"].max(), ip["date"].max())
    date_range = st.date_input("Date range", (max_date - pd.Timedelta(days=6), max_date),
                               min_value=min_date, max_value=max_date)
    sites = sorted(ip["site"].unique().tolist())
    site = st.selectbox("Site", ["All"] + sites)
    divisions = sorted(ip["division"].unique().tolist())
    division = st.selectbox("Division (inpatients)", ["All"] + divisions)
    st.markdown("---")
    st.caption("Capacity Gap parameters")
    target_occ = st.slider("Target bed occupancy %", 80, 98, 92)
    admit_conv = st.slider("ED admission conversion %", 10, 40, 25)
    discharge_need = st.slider("Daily discharge need (beds)", 0, 120, 60)

# Apply filters
start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
edf = ed[(ed["date"] >= start) & (ed["date"] <= end)].copy()
ambf = amb[(amb["date"] >= start) & (amb["date"] <= end)].copy()
ipf = ip[(ip["date"] >= start) & (ip["date"] <= end)].copy()
thf = th[(th["date"] >= start) & (th["date"] <= end)].copy()
wlf = wl[(wl["date"] >= start) & (wl["date"] <= end)].copy()

if site != "All":
    edf = edf[edf["site"] == site] if "site" in edf.columns else edf
    ipf = ipf[ipf["site"] == site]

if division != "All":
    ipf = ipf[ipf["division"] == division]

# -------------
# Helper KPIs
# -------------
def kpi_card(label, value, suffix="", help_text=None):
    st.metric(label, f"{value}{suffix}" if suffix else f"{value}", help=help_text)

def safe_div(a,b):
    return (a / b) if b else 0

def capacity_gap(ip_day, target_occ_pct, expected_admits, planned_discharges):
    beds = ip_day["beds"].sum()
    occ = ip_day["occupied"].sum()
    target_occ = beds * target_occ_pct / 100
    # Positive gap means we are short of beds
    gap = max(0, (occ + expected_admits - planned_discharges) - target_occ)
    return gap, beds, occ, target_occ

st.title("Hospital Flow Command Centre")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Ops Overview", "ED & Ambulance", "Beds & Flow", "Discharge", "Theatres & Elective"
])

# ---------------- Ops Overview ----------------
with tab1:
    st.subheader("At-a-glance")
    # Aggregate last day
    last_day = ipf["date"].max()
    ip_day = ipf[ipf["date"] == last_day]
    ed_day = edf[edf["date"] == last_day]
    amb_day = ambf[ambf["date"] == last_day]

    todays_arrivals = ed_day["arrivals"].sum()
    todays_admits = int(todays_arrivals * (admit_conv/100))
    todays_discharges = ip_day["discharges"].sum()
    gap, beds, occ, target_occ_v = capacity_gap(ip_day, target_occ, todays_admits, todays_discharges)

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        kpi_card("ED arrivals (today)", int(todays_arrivals))
    with col2:
        kpi_card("Ambulance arrivals (today)", int(ed_day["ambulance_arrivals"].sum()))
    with col3:
        kpi_card("4-hour performance", f"{int(100*safe_div(ed_day['seen_within_4h'].sum(), max(ed_day['arrivals'].sum(),1)))}%", "")
    with col4:
        kpi_card("Bed occupancy", f"{int(100*safe_div(occ, beds))}%", "")
    with col5:
        kpi_card("Discharges before noon", f"{int(100*safe_div(ip_day['discharges_before_noon'].sum(), max(ip_day['discharges'].sum(),1)))}%", "")
    with col6:
        kpi_card("Capacity gap vs target occ", int(gap), " beds", "Positive = short of beds")

    # Trend charts
    colA, colB = st.columns(2)
    with colA:
        ed_trend = edf.groupby("date")[["arrivals","admitted_from_ed"]].sum().reset_index()
        fig = px.line(ed_trend, x="date", y=["arrivals","admitted_from_ed"], markers=True,
                      labels={"value": "Patients", "date":"Date", "variable": "Metric"},
                      title="ED arrivals & admissions")
        st.plotly_chart(fig, use_container_width=True)
    with colB:
        occ_trend = ipf.groupby("date")[["occupied","beds"]].sum().reset_index()
        occ_trend["occ_pct"] = (occ_trend["occupied"] / occ_trend["beds"]) * 100
        fig2 = px.line(occ_trend, x="date", y="occ_pct", markers=True, title="Bed occupancy %")
        st.plotly_chart(fig2, use_container_width=True)

# ---------------- ED & Ambulance ----------------
with tab2:
    st.subheader("ED live picture")
    # Heatmap of arrivals by hour
    edh = edf.groupby(["date","hour"])[["arrivals","admitted_from_ed","left_without_being_seen","ambulance_arrivals","seen_within_4h"]].sum().reset_index()
    pivot = edh.pivot(index="hour", columns="date", values="arrivals")
    fig = px.imshow(pivot, aspect="auto", title="Arrivals heatmap by hour")
    st.plotly_chart(fig, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        fig3 = px.bar(edh.groupby("hour")[["arrivals","ambulance_arrivals"]].sum().reset_index(),
                      x="hour", y=["arrivals","ambulance_arrivals"], barmode="group",
                      title="Average arrivals by hour (selected dates)")
        st.plotly_chart(fig3, use_container_width=True)
    with col2:
        edh["seen_pct"] = 100 * (edh["seen_within_4h"] / edh["arrivals"].replace(0, np.nan))
        fig4 = px.line(edh.groupby("date")["seen_pct"].mean().reset_index(), x="date", y="seen_pct",
                       markers=True, title="4-hour performance trend")
        st.plotly_chart(fig4, use_container_width=True)

    st.subheader("Ambulance handovers")
    amb_day = ambf[ambf["date"] == ambf["date"].max()]
    amb_day = amb_day.sort_values("slot")
    amb_day["time"] = pd.to_datetime(amb_day["slot"]*15, unit="m").dt.strftime('%H:%M')
    fig5 = go.Figure()
    fig5.add_trace(go.Scatter(x=amb_day["time"], y=amb_day["queue"], mode="lines+markers", name="Queue"))
    fig5.add_trace(go.Bar(x=amb_day["time"], y=amb_day["arrivals"], name="Arrivals", opacity=0.4))
    fig5.update_layout(title="Today's ambulance arrivals and queue (15-min slots)", xaxis_title="Time", yaxis_title="Count")
    st.plotly_chart(fig5, use_container_width=True)

    col3, col4, col5 = st.columns(3)
    with col3:
        over15 = int(amb_day["handover_over_15m"].sum())
        st.metric("Handover >15m (today)", over15)
    with col4:
        over30 = int(amb_day["handover_over_30m"].sum())
        st.metric(">30m", over30)
    with col5:
        over60 = int(amb_day["handover_over_60m"].sum())
        st.metric(">60m", over60)

# ---------------- Beds & Flow ----------------
with tab3:
    st.subheader("Bed state & flow by ward")
    latest = ipf[ipf["date"] == ipf["date"].max()]
    if site != "All":
        latest = latest[latest["site"] == site]
    if division != "All":
        latest = latest[latest["division"] == division]

    latest["occ_pct"] = (latest["occupied"] / latest["beds"]) * 100
    fig6 = px.bar(latest.sort_values("occ_pct", ascending=False),
                  x="ward", y="occ_pct", hover_data=["occupied","beds","division","site"],
                  title="Ward occupancy % (latest day)")
    st.plotly_chart(fig6, use_container_width=True)

    st.dataframe(latest[["site","division","ward","beds","occupied","nctr_mofd","stranded_7d","super_stranded_21d","admissions","discharges","discharges_before_noon"]]
                 .sort_values(["site","division","ward"]))

# ---------------- Discharge ----------------
with tab4:
    st.subheader("Discharge pipeline and performance")
    # EDD vs actual is not in sample; use discharges needed vs achieved
    daily = ipf.groupby("date")[["discharges","discharges_before_noon","nctr_mofd","occupied","beds"]].sum().reset_index()
    daily["before_noon_pct"] = 100 * (daily["discharges_before_noon"] / daily["discharges"].replace(0,np.nan))
    fig7 = px.line(daily, x="date", y=["discharges","discharges_before_noon"], markers=True, title="Discharges and before-noon discharges")
    st.plotly_chart(fig7, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        fig8 = px.line(daily, x="date", y="before_noon_pct", markers=True, title="% Discharged before noon")
        st.plotly_chart(fig8, use_container_width=True)
    with col2:
        fig9 = px.line(daily, x="date", y="nctr_mofd", markers=True, title="Patients with No Criteria to Reside (NCTR/MOFD)")
        st.plotly_chart(fig9, use_container_width=True)

    st.caption("Tip: Compare NCTR/MOFD against system D2A capacity to plan the afternoon discharge push.")

# ---------------- Theatres & Elective ----------------
with tab5:
    st.subheader("Elective performance")
    t = thf.groupby(["date","specialty"])[["sessions","planned_cases","completed_cases","cancelled_on_the_day"]].sum().reset_index()
    fig10 = px.bar(t, x="date", y="completed_cases", color="specialty", title="Completed cases per day by specialty")
    st.plotly_chart(fig10, use_container_width=True)

    wl_latest = wlf[wlf["date"] == wlf["date"].max()]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Waiting list (total)", int(wl_latest["total_waiting"].sum()))
    col2.metric(">52 weeks", int(wl_latest["over_52_weeks"].sum()))
    col3.metric(">65 weeks", int(wl_latest["over_65_weeks"].sum()))
    col4.metric(">78 weeks", int(wl_latest["over_78_weeks"].sum()))

st.markdown("---")
st.caption("Prototype dashboard with synthetic data. Replace CSVs in /data with live extracts (same schema) or connect to your ED, EPR and theatre data sources.")


# ---------------- Benchmarking (NHSE scrape) ----------------
with st.tabs(["Ops Overview", "ED & Ambulance", "Beds & Flow", "Discharge", "Theatres & Elective", "Benchmarking"])[5]:
    st.subheader("Benchmarking (12-week average)")
    st.caption("Pulls public NHSE data (A&E monthly, UEC SitRep time series, RTT, KH03). Data is cached locally.")

    # Peer selector (free text; match by provider name substring or ODS code)
    peers_text = st.text_input("Peers (comma-separated; provider names or ODS codes)", value="Portsmouth, University Hospitals Sussex, University Hospitals Dorset")
    peers = [p.strip() for p in peers_text.split(",") if p.strip()]

    import nhse_scraper as ns

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Fetch A&E monthly (provider)"):
            try:
                df = ns.fetch_ae_monthly_provider(ns.PeerSet(peers))
                st.success(f"Fetched {len(df):,} rows")
                st.dataframe(df.head(50))
            except Exception as e:
                st.error(str(e))

    with col2:
        if st.button("Fetch Ambulance handover time series"):
            try:
                df = ns.fetch_ambulance_handover_timeseries(ns.PeerSet(peers))
                st.success(f"Fetched {len(df):,} rows")
                st.dataframe(df.head(50))
            except Exception as e:
                st.error(str(e))

    st.markdown("### Acute Discharge (weekly) — NCTR/MOFD proxy")
    if st.button("Fetch Acute Discharge SitRep time series"):
        try:
            df = ns.fetch_acute_discharge_timeseries(ns.PeerSet(peers))
            st.success(f"Fetched {len(df):,} rows")
            st.dataframe(df.head(50))
        except Exception as e:
            st.error(str(e))

    st.markdown("### RTT (provider) — full CSV (month)")
    rtt_month = st.selectbox("RTT month", ["2025-03","2025-02","2025-01","2024-12"])
    if st.button("Fetch RTT full CSV for month"):
        try:
            df = ns.fetch_rtt_full_csv(rtt_month)
            # Simple view: provider, incomplete pathways, >52w, >65w, >78w if present
            keep = [c for c in df.columns if any(k in c.lower() for k in ["provider","incomplete","52","65","78","wait"])]
            st.success(f"Fetched {len(df):,} rows")
            st.dataframe(df[keep].head(50))
        except Exception as e:
            st.error(str(e))

    st.markdown("### KH03 – Bed availability/occupancy (latest quarter)")
    if st.button("Fetch KH03 latest"):
        try:
            df = ns.fetch_kh03_latest()
            st.success(f"Fetched {len(df):,} rows")
            st.dataframe(df.head(50))
        except Exception as e:
            st.error(str(e))

    st.info("Once you confirm the exact peer list and metrics, we can automate a nightly job to refresh and compute 12-week averages and rank vs. peers.")
