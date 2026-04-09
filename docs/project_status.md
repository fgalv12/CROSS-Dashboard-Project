# Project Status

**Last Updated:** 2026-04-09

This document describes milestones, what has been accomplished, and what's next since last time.

## Current Phase: Alerting and Thresholds Complete (Milestone 4)

The CROSS Dashboard has a fully functional Streamlit application with all primary panels, data pipeline, AI integration, progressive drill-down views, configurable alert thresholds with visual indicators, threshold breach tracking, and daily digest export.

## Completed Milestones

### Data Pipeline
- [x] Excel data loader with `@st.cache_data` caching for all 15 sheets
- [x] Star schema joins (dimensions + fact tables)
- [x] Cascading sidebar filters (date range, region, county, incident type)
- [x] KPI computation engine (snapshots, deltas, trends)
- [x] Z-score anomaly detection (flags values >1.5 sigma from 30-day mean)

### Dashboard UI
- [x] Executive Snapshot panel with KPI cards and day-over-day deltas
- [x] Geographic View with interactive Kansas choropleth (multiple color metrics)
- [x] Logistics & Operations panel (PPE trends, staffing, transfers, delays)
- [x] Emerging Threats panel (30-day trend lines, confidence bands, anomaly markers)
- [x] Alert status donut chart and critical county table
- [x] Dark theme styling (dark red primary, plotly_dark charts)
- [x] Responsive column layout

### AI Agent
- [x] Standalone CLI tool (`python3 cross_situational_awareness_agent.py`)
- [x] Importable functions for dashboard integration
- [x] Streaming Claude Sonnet 4 briefings via Anthropic SDK
- [x] Session state persistence for generated briefings
- [x] 1/7/30-day lookback options
- [x] `--raw` mode for JSON output (no API key needed)

### Infrastructure
- [x] Streamlit config with custom dark theme
- [x] Secrets management via `.streamlit/secrets.toml`
- [x] GeoJSON county boundaries for Kansas (TIGER/Line shapefiles)
- [x] Requirements file with pinned minimum versions
- [x] Project documentation (CLAUDE.md, project_spec.md)

### Drill-Down Views (Milestone 3)
- [x] County detail drilldown view with tabbed interface (Facilities, Inventory, Incidents, Alert History)
- [x] Facility detail view with ICU trend, staff fill rate, bed occupancy charts
- [x] Resource transfer Sankey diagram with delay color-coding and top-N filter
- [x] Incident event timeline with filterable table and severity chart
- [x] County KPI header with alert status badge
- [x] Nested facility selector within county detail panel
- [x] Transfer summary statistics (total transfers, quantity, avg delay, delayed count)

### Documentation
- [x] Populate and maintain docs folder (architecture, changelog, status)

### Alerting and Thresholds (Milestone 4)

- [x] Configurable alert thresholds sidebar UI (6 metrics: ICU %, response time, PPE days, staff shortage, supply delay, stress score)
- [x] Reset to Defaults button with proper Streamlit session state handling
- [x] Visual breach indicators on Executive Snapshot and County Detail KPI cards (red border + threshold label)
- [x] Threshold reference lines on 5 chart types (PPE trend, staff availability, supply delay, trend line, facility ICU)
- [x] Breach info in choropleth map hover data
- [x] Threshold Alerts panel (collapsed expander under Executive Snapshot) with:
  - Active breaches summary bar chart
  - Sortable county-level breach table
  - Interactive breach timeline heatmap by metric
- [x] Threshold evaluation engine (`evaluate_thresholds`, `evaluate_county_thresholds`, `get_active_breaches`, `get_threshold_breach_timeline`)
- [x] Daily digest export with Download Markdown and Download PDF buttons
- [x] PDF generation via fpdf2 with formatted tables, sections, and branding
- [x] Digest includes: KPI snapshot, threshold breaches, county-level breach table, alert status distribution, AI briefing
- [x] Panel reorganization: Transfer Tracking collapsed under Geographic View, Incident Timeline collapsed under Emerging Threats

## Planned / Next Steps

### Medium-Term
- [ ] Role-based access controls (RBAC) via Streamlit auth

### Long-Term
- [ ] Multi-state scalability (standardized KPI definitions)
- [ ] Real-time data feed integration (replace batch Excel)
- [ ] Deployment to Streamlit Community Cloud or internal hosting with SSO
