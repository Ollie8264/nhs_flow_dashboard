
# Hospital Flow Command Centre (Prototype)

This is a self-contained Streamlit app with synthetic data to prototype an interactive dashboard for site operations.

## How to run
```bash
cd nhs_flow_dashboard
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

The app loads CSVs from `data/`. Replace them with your live extracts (same columns) or modify the code to connect to your data sources.

## Tabs and KPIs
- **Ops Overview:** ED arrivals and admissions, 4-hour performance, occupancy, discharges before noon, capacity gap vs target occupancy.
- **ED & Ambulance:** Hourly arrivals heatmap, ambulance arrivals/queue, handover delays (>15, >30, >60 min).
- **Beds & Flow:** Ward-level occupancy with NCTR/MOFD, stranded (7d) and super-stranded (21d).
- **Discharge:** Daily discharges, % before noon, NCTR/MOFD trend.
- **Theatres & Elective:** Completed cases by specialty, waiting list summary (>52, >65, >78 weeks).

## Data dictionary (CSV schemas)
### `ed.csv`
- date (YYYY-MM-DD), hour (0-23), site, arrivals, ambulance_arrivals, admitted_from_ed, left_without_being_seen, seen_within_4h

### `ambulance.csv`
- date, slot (0-95 per 15-min), arrivals, queue, handover_over_15m, handover_over_30m, handover_over_60m

### `inpatients.csv`
- date, site, division, ward, beds, occupied, admissions, discharges, discharges_before_noon, nctr_mofd, stranded_7d, super_stranded_21d

### `theatres.csv`
- date, specialty, sessions, planned_cases, completed_cases, cancelled_on_the_day

### `waiting_list.csv`
- date, specialty, total_waiting, over_52_weeks, over_65_weeks, over_78_weeks

## Notes
- All data is synthetic and for demonstration only.
- You can add authentication, alerting, and colour thresholds as needed.
