# Changelog

All notable changes to the CROSS Dashboard will be documented in this file.

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
