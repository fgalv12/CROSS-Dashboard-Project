# Changelog

All notable changes to the CROSS Dashboard will be documented in this file.

## [0.2.0] - 2026-04-06

### Added

- **County drill-down view** — select a county below the map to see a tabbed detail panel with:
  - Facilities tab: horizontal ICU occupancy bars color-coded by stress level
  - Inventory tab: per-item inventory levels over time
  - Incidents tab: sortable table of incident events
  - Alert History tab: color-coded daily alert status timeline
- **Facility drill-down view** — select a facility within a county to see:
  - ICU occupancy trend with 85% threshold line
  - Staff fill rate trend
  - Bed occupancy stacked area chart (occupied vs total)
- **Transfer Tracking panel** — Sankey diagram showing inter-county resource flows:
  - Links color-coded by delay (green/orange/red)
  - Adjustable top-N filter to control diagram density
  - Summary statistics: total transfers, quantity, avg delay, delayed count
- **Incident Timeline panel** — filterable incident event table with:
  - Stacked severity bar chart
  - Filters for incident type, severity level, and county
  - Sortable columns with formatted time values
- **New data functions** (`utils/metrics.py`): `get_county_detail()`, `get_county_facility_capacity()`, `get_county_inventory()`, `get_county_incidents()`, `get_county_alert_timeline()`, `get_facility_detail()`, `get_transfer_flows()`, `get_incident_timeline()`
- **New chart functions** (`utils/charts.py`): `make_facility_capacity_bars()`, `make_facility_icu_trend()`, `make_facility_staff_trend()`, `make_facility_bed_occupancy()`, `make_county_inventory_detail()`, `make_alert_timeline()`, `make_transfer_sankey()`, `make_incident_severity_chart()`
- **Facility lookup** (`utils/data_loader.py`): `get_facilities()` for county-scoped facility queries

## [0.1.0] - 2026-03-20

### Added
- **Streamlit dashboard** (`app.py`) with four main panels:
  - Executive Snapshot: KPI cards with day-over-day deltas (Active Incidents, ICU Capacity %, Avg Response Time, Deployment Lag, Alert Counties)
  - Geographic View: Interactive Kansas choropleth map with selectable color metrics (ICU %, incidents, stress score, alert status)
  - Logistics & Operations: PPE inventory trends, staff availability by region, equipment transfer volumes, supply delay trends
  - Emerging Threats: 30-day trend analysis with mean/confidence bands, anomaly detection markers, alert status donut chart
- **Data pipeline** (`utils/data_loader.py`): Loads and caches all 15 Excel sheets; cascading sidebar filters for date range, region, county, incident type
- **Metrics engine** (`utils/metrics.py`): KPI computation (snapshots, deltas, 30-day trends), z-score anomaly detection (>1.5 sigma threshold)
- **Chart library** (`utils/charts.py`): Plotly chart builders with consistent dark theme styling
- **AI Situational Awareness Agent** (`cross_situational_awareness_agent.py`):
  - Standalone CLI with `--date`, `--lookback`, and `--raw` options
  - Streaming Claude Sonnet 4 briefings integrated into dashboard via button click
  - Session state persistence for generated briefings
- **Kansas GeoJSON** (`data/kansas_counties.geojson`): County boundaries from US Census TIGER/Line shapefiles
- **Mock dataset** (`data/KS_CROSS_mock_dataset.xlsx`): Star schema with 8 dimension tables and 5 fact tables (~60K total rows)
- **Streamlit theming** (`.streamlit/config.toml`): Dark red (#B22222) primary, dark background (#0E1117)
- **Project documentation**: CLAUDE.md, project_spec.md, docs folder structure
