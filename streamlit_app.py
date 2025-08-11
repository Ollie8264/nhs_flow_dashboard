
import streamlit as st, pandas as pd, numpy as np
import plotly.express as px, plotly.graph_objects as go
from datetime import datetime

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

with st.sidebar:
    st.title("Filters")
    min_date = min(ed["date"].min(), ip["date"].min())
    max_date = max(ed["date"].max(), ip["date"].max())
    date_range = st.date_input("Date range", (pd.to_datetime(max_date) - pd.Timedelta(days=6), pd.to_datetime(max_date)))
    sites = sorted(ip["site"].unique().tolist())
    site = st.selectbox("Site", ["All"] + sites)
    divisions = sorted(ip["division"].unique().tolist())
    division = st.selectbox("Division (inpatients)", ["All"] + divisions)
    st.markdown("---")
    target_occ = st.slider("Target bed occupancy %", 80, 98, 92)
    admit_conv = st.slider("ED admission conversion %", 10, 40, 25)

start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
edf = ed[(ed["date"] >= start) & (ed["date"] <= end)].copy()
ambf = amb[(amb["date"] >= start) & (amb["date"] <= end)].copy()
ipf = ip[(ip["date"] >= start) & (ip["date"] <= end)].copy()
thf = th[(th["date"] >= start) & (th["date"] <= end)].copy()
wlf = wl[(wl["date"] >= start) & (wl["date"] <= end)].copy()

if site != "All":
    edf = edf[edf.get("site","Main").eq(site)] if "site" in edf.columns else edf
    ipf = ipf[ipf["site"] == site]
if division != "All":
    ipf = ipf[ipf["division"] == division]

def safe_div(a,b): return (a/b) if b else 0

st.title("Hospital Flow Command Centre")
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Ops Overview","ED & Ambulance","Beds & Flow","Discharge","Theatres & Elective","Benchmarking"])

with tab1:
    st.subheader("At-a-glance")
    last_day = ipf["date"].max()
    ip_day = ipf[ipf["date"] == last_day]
    ed_day = edf[edf["date"] == last_day]
    todays_arrivals = ed_day["arrivals"].sum()
    todays_admits = int(todays_arrivals * (st.session_state.get("admit_conv",25)/100))
    todays_discharges = ip_day["discharges"].sum()
    beds = ip_day["beds"].sum(); occ = ip_day["occupied"].sum()
    target_occ_v = beds * target_occ / 100
    gap = max(0, (occ + todays_admits - todays_discharges) - target_occ_v)
    c1,c2,c3,c4,c5,c6=st.columns(6)
    c1.metric("ED arrivals (today)", int(todays_arrivals))
    c2.metric("Ambulance arrivals (today)", int(ed_day["ambulance_arrivals"].sum()))
    c3.metric("4-hour performance", f"{int(100*safe_div(ed_day['seen_within_4h'].sum(), max(ed_day['arrivals'].sum(),1)))}%")
    c4.metric("Bed occupancy", f"{int(100*safe_div(occ, max(beds,1)))}%")
    c5.metric("Discharges before noon", f"{int(100*safe_div(ip_day['discharges_before_noon'].sum(), max(ip_day['discharges'].sum(),1)))}%")
    c6.metric("Capacity gap vs target occ", int(gap), " beds")

    colA, colB = st.columns(2)
    with colA:
        ed_trend = edf.groupby("date")[["arrivals","admitted_from_ed"]].sum().reset_index()
        st.plotly_chart(px.line(ed_trend, x="date", y=["arrivals","admitted_from_ed"], markers=True, title="ED arrivals & admissions"), use_container_width=True)
    with colB:
        occ_trend = ipf.groupby("date")[["occupied","beds"]].sum().reset_index()
        occ_trend["occ_pct"] = (occ_trend["occupied"]/occ_trend["beds"])*100
        st.plotly_chart(px.line(occ_trend, x="date", y="occ_pct", markers=True, title="Bed occupancy %"), use_container_width=True)

with tab2:
    st.subheader("ED live picture")
    edh = edf.groupby(["date","hour"])[["arrivals","admitted_from_ed","left_without_being_seen","ambulance_arrivals","seen_within_4h"]].sum().reset_index()
    pivot = edh.pivot(index="hour", columns="date", values="arrivals")
    st.plotly_chart(px.imshow(pivot, aspect="auto", title="Arrivals heatmap by hour"), use_container_width=True)
    col1,col2=st.columns(2)
    col1.plotly_chart(px.bar(edh.groupby("hour")[["arrivals","ambulance_arrivals"]].sum().reset_index(), x="hour", y=["arrivals","ambulance_arrivals"], barmode="group", title="Arrivals by hour"), use_container_width=True)
    edh["seen_pct"] = 100*(edh["seen_within_4h"]/edh["arrivals"].replace(0,np.nan))
    col2.plotly_chart(px.line(edh.groupby("date")["seen_pct"].mean().reset_index(), x="date", y="seen_pct", markers=True, title="4-hour performance trend"), use_container_width=True)
    st.subheader("Ambulance handovers")
    amb_day = ambf[ambf["date"] == ambf["date"].max()].sort_values("slot")
    amb_day["time"] = pd.to_datetime(amb_day["slot"]*15, unit="m").dt.strftime('%H:%M')
    fig5 = go.Figure()
    fig5.add_trace(go.Scatter(x=amb_day["time"], y=amb_day["queue"], mode="lines+markers", name="Queue"))
    fig5.add_trace(go.Bar(x=amb_day["time"], y=amb_day["arrivals"], name="Arrivals", opacity=0.4))
    fig5.update_layout(title="Today's ambulance arrivals and queue (15-min slots)")
    st.plotly_chart(fig5, use_container_width=True)
    c3,c4,c5 = st.columns(3)
    c3.metric(">15m", int(amb_day["handover_over_15m"].sum()))
    c4.metric(">30m", int(amb_day["handover_over_30m"].sum()))
    c5.metric(">60m", int(amb_day["handover_over_60m"].sum()))

with tab3:
    st.subheader("Bed state & flow by ward")
    latest = ipf[ipf["date"] == ipf["date"].max()].copy()
    latest["occ_pct"] = (latest["occupied"]/latest["beds"])*100
    st.plotly_chart(px.bar(latest.sort_values("occ_pct", ascending=False), x="ward", y="occ_pct", hover_data=["occupied","beds","division","site"], title="Ward occupancy % (latest)"), use_container_width=True)
    st.dataframe(latest[["site","division","ward","beds","occupied","nctr_mofd","stranded_7d","super_stranded_21d","admissions","discharges","discharges_before_noon"]].sort_values(["site","division","ward"]), use_container_width=True)

with tab4:
    st.subheader("Discharge pipeline and performance")
    daily = ipf.groupby("date")[["discharges","discharges_before_noon","nctr_mofd","occupied","beds"]].sum().reset_index()
    daily["before_noon_pct"] = 100 * (daily["discharges_before_noon"] / daily["discharges"].replace(0,np.nan))
    st.plotly_chart(px.line(daily, x="date", y=["discharges","discharges_before_noon"], markers=True, title="Discharges and before-noon discharges"), use_container_width=True)
    col1,col2=st.columns(2)
    col1.plotly_chart(px.line(daily, x="date", y="before_noon_pct", markers=True, title="% Discharged before noon"), use_container_width=True)
    col2.plotly_chart(px.line(daily, x="date", y="nctr_mofd", markers=True, title="NCTR/MOFD patients"), use_container_width=True)

with tab5:
    st.subheader("Elective performance")
    t = thf.groupby(["date","specialty"])[["sessions","planned_cases","completed_cases","cancelled_on_the_day"]].sum().reset_index()
    st.plotly_chart(px.bar(t, x="date", y="completed_cases", color="specialty", title="Completed cases per day by specialty"), use_container_width=True)
    wl_latest = wlf[wlf["date"] == wlf["date"].max()]
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Waiting list (total)", int(wl_latest["total_waiting"].sum()))
    c2.metric(">52 weeks", int(wl_latest["over_52_weeks"].sum()))
    c3.metric(">65 weeks", int(wl_latest["over_65_weeks"].sum()))
    c4.metric(">78 weeks", int(wl_latest["over_78_weeks"].sum()))

with tab6:
    st.subheader("Benchmarking")
    st.caption("Use the controls below to fetch NHSE data and benchmark Main vs Peers.")
    import nhse_scraper as ns
    with st.expander("NHSE data fetchers"):
        peers_text = st.text_input("Peers (comma-separated; provider names or ODS codes)", value="Portsmouth, University Hospitals Sussex, University Hospitals Dorset")
        peers = [p.strip() for p in peers_text.split(",") if p.strip()]
        col1,col2 = st.columns(2)
        if col1.button("Fetch A&E monthly (provider)"):
            try:
                df = ns.fetch_ae_monthly_provider(ns.PeerSet(peers))
                st.success(f"Fetched {len(df):,} rows"); st.dataframe(df.head(50))
            except Exception as e: st.error(str(e))
        if col2.button("Fetch Ambulance handover time series"):
            try:
                df = ns.fetch_ambulance_handover_timeseries(ns.PeerSet(peers))
                st.success(f"Fetched {len(df):,} rows"); st.dataframe(df.head(50))
            except Exception as e: st.error(str(e))
        if st.button("Fetch Acute Discharge SitRep time series"):
            try:
                df = ns.fetch_acute_discharge_timeseries(ns.PeerSet(peers))
                st.success(f"Fetched {len(df):,} rows"); st.dataframe(df.head(50))
            except Exception as e: st.error(str(e))

    st.markdown("---")
    st.markdown("### Peer benchmarking (Model Hospital–style)")
    default_main = "Portsmouth"; default_peers = ["Isle of Wight","Southampton","Hampshire Hospitals"]
    main_site = st.text_input("Main site", value=default_main)
    peer_sites = st.multiselect("Peers", default_peers, default=default_peers)
    if st.button("Run peer comparison"):
        try:
            ae = ns.fetch_ae_monthly_provider(ns.PeerSet([main_site]+peer_sites))
            # pick columns
            total_col = next((c for c in ae.columns if ("attend" in c.lower()) and "%" not in c.lower()), None)
            pct_col = next((c for c in ae.columns if "% within 4" in c.lower()), None)
            within4_col = next((c for c in ae.columns if "within 4" in c.lower() and "%" not in c.lower()), None)
            ae["period_dt"] = pd.to_datetime(ae["period"] + "-01")
            ae = ae.sort_values(["PROVIDER","period_dt"], ascending=[True, False]).groupby("PROVIDER").head(3)
            if pct_col:
                ae["within4_pct"] = ae[pct_col].astype(float)
                if ae["within4_pct"].mean() <= 1.0: ae["within4_pct"]*=100.0
            elif within4_col and total_col:
                ae["within4_pct"] = (ae[within4_col].astype(float)/ae[total_col].replace(0,np.nan).astype(float))*100.0
            agg = ae.groupby("PROVIDER").agg(within4_12wk=("within4_pct","mean"), attendances_3m=(total_col,"sum")).reset_index()
            mask = agg["PROVIDER"].str.contains(main_site, case=False, na=False)
            for p in peer_sites: mask = mask | agg["PROVIDER"].str.contains(p, case=False, na=False)
            view = agg[mask].copy()
            peer_avg = view.loc[~view["PROVIDER"].str.contains(main_site, case=False, na=False), "within4_12wk"].mean()
            view["rank"] = view["within4_12wk"].rank(ascending=False, method="min").astype(int)
            view["delta_vs_peer_avg"] = view["within4_12wk"] - peer_avg
            fig = px.bar(view.sort_values("within4_12wk", ascending=False), x="PROVIDER", y="within4_12wk", title="A&E 4h % (~12-week avg) — Main vs Peers", labels={"within4_12wk":"4h %"})
            fig.add_hline(y=peer_avg, line_dash="dash", annotation_text=f"Peer avg: {peer_avg:.1f}%")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(view[["PROVIDER","within4_12wk","rank","delta_vs_peer_avg","attendances_3m"]].sort_values("rank"), use_container_width=True)
        except Exception as e:
            st.error(f"Peer comparison failed: {e}")
