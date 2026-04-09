# Architecture

This document describes the high-level system architecture, data flow, and component relationships.

**Last Updated:** 2026-04-09

## Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| App Framework | Streamlit | 1.30.0+ |
| Data Processing | Pandas / NumPy | 2.0+ / 1.24+ |
| Visualization | Plotly | 5.18.0+ |
| AI Integration | Anthropic SDK (Claude Sonnet 4) | 0.40.0+ |
| PDF Export | fpdf2 | 2.7.0+ |
| Data Source | Excel via openpyxl | 3.1.0+ |
| Language | Python | 3.11+ |

## Project Structure

```
CROSS Dashboard Project/
├── app.py                                # Streamlit entry point (7 panels + AI)
├── cross_situational_awareness_agent.py  # AI agent (standalone CLI + importable)
├── requirements.txt                      # Python dependencies
├── .env.example                          # Example environment variables
├── .streamlit/
│   ├── config.toml                       # Theme & layout settings
│   └── secrets.toml                      # API keys (not committed)
├── utils/
│   ├── __init__.py
│   ├── data_loader.py                    # Excel loading, caching, filtering, facility lookups
│   ├── metrics.py                        # KPI computation, snapshots, trends, drill-down metrics, threshold evaluation, digest export
│   ├── charts.py                         # Plotly chart builder functions (18 chart types)
│   └── faq_agent.py                      # OpenAI Agent SDK FAQ assistant
├── data/
│   ├── KS_CROSS_mock_dataset.xlsx        # Source dataset (15 sheets, ~60K rows)
│   └── kansas_counties.geojson           # County boundaries for choropleth
├── docs/
│   ├── architecture.md                   # This file
│   ├── changelog.md                      # Version history
│   ├── project_status.md                 # Milestones & progress
│   └── (reference assets)               # Mockup, schema screenshot, requirements doc
├── project_spec.md                       # Full requirements & API specs
└── CLAUDE.md                             # AI assistant context
```

## Data Flow

```
KS_CROSS_mock_dataset.xlsx (15 sheets, star schema)
    │
    ▼
@st.cache_data load_data() → Dict of Pandas DataFrames
    │
    ▼
Sidebar filters (date range, region, county, incident type)
    │
    ▼
filter_data() → Filtered DataFrames
    │
    ├──▶ compute_snapshot()    → KPI scalars for cards
    ├──▶ compute_changes()     → Deltas vs prior period
    ├──▶ compute_trends()      → 30-day stats + z-score anomalies
    │
    ├──▶ get_county_metrics()  → Choropleth map data
    ├──▶ get_inventory_series()→ PPE trend chart data
    ├──▶ get_staff_by_region() → Staffing chart data
    ├──▶ get_transfer_summary()→ Transfer bar chart data
    ├──▶ get_supply_delay()    → Delay trend chart data
    ├──▶ get_trend_series()    → Anomaly detection chart data
    │
    ├──▶ Drill-Down (on county select)
    │       ├── get_county_detail()            → County KPI header
    │       ├── get_county_facility_capacity()  → Facility ICU bars
    │       ├── get_county_inventory()          → County inventory chart
    │       ├── get_county_incidents()          → County incident table
    │       ├── get_county_alert_timeline()     → Alert status timeline
    │       └── get_facility_detail()           → Facility ICU/staff/bed trends
    │
    ├──▶ get_transfer_flows()  → Sankey diagram data
    ├──▶ get_incident_timeline()→ Filterable incident event table
    │
    ├──▶ Threshold Evaluation (configurable via sidebar)
    │       ├── evaluate_thresholds()              → Statewide breach check
    │       ├── evaluate_county_thresholds()        → Per-county breach check
    │       ├── get_active_breaches()               → Current breach table
    │       └── get_threshold_breach_timeline()     → Historical breach heatmap
    │
    ├──▶ Daily Digest Export
    │       ├── build_daily_digest_md()  → Markdown report download
    │       └── build_daily_digest_pdf() → PDF report download (fpdf2)
    │
    └──▶ AI Agent (on demand)
            ├── Builds JSON prompt from snapshot + changes + trends
            ├── Calls Anthropic API (claude-sonnet-4, streaming)
            └── Streams word-by-word to st.write_stream()
```

## Data Model (Star Schema)

**Dimension Tables (8):**
- `Dim_State` — State-level info
- `Dim_Region` — 6 Kansas regions
- `Dim_County` — 105 counties (with FIPS codes for GeoJSON join)
- `Dim_Date` — 90 days (2025-12-05 to 2026-03-04)
- `Dim_FacilityType` — 5 facility types
- `Dim_Facility` — 127 facilities
- `Dim_IncidentType` — 6 incident categories
- `Dim_Item` — 4 supply items

**Fact Tables (5):**
- `Fact_DailyCountyMetrics` (9,450 rows) — daily per-county KPIs
- `Fact_FacilityCapacityDaily` (11,430 rows) — daily facility bed/ICU/staffing
- `Fact_InventoryDaily` (37,800 rows) — daily per-county per-item inventory
- `Fact_ResourceTransfers` (556 rows) — inter-county shipments
- `Fact_IncidentEvents` (4,525 rows) — individual incidents with severity/timing

## Dashboard Panels

1. **AI Briefing** — On-demand streaming executive summary powered by Claude Sonnet 4 with configurable lookback; daily digest export (Markdown + PDF)
2. **Executive Snapshot** — KPI cards with day-over-day deltas and threshold breach highlighting; collapsed Threshold Alerts subsection with breach summary chart, county breach table, and breach timeline heatmap
3. **Geographic View** — Interactive Kansas choropleth map with selectable color metrics and threshold breach info in hover data; collapsed Transfer Tracking subsection (Sankey diagram); County drill-down with tabbed detail views
4. **County Detail View** — Tabbed drill-down (Facilities, Inventory, Incidents, Alert History) with nested facility selector; KPI cards show threshold breach indicators
5. **Logistics & Operations** — 2x2 grid: PPE inventory trends, staff availability by region, equipment transfer volumes, supply delay trends — all with configurable threshold reference lines
6. **Emerging Threats** — 30-day trend line with mean/confidence bands, anomaly markers, and threshold reference line; alert status donut chart; alert/critical county table; collapsed Incident Timeline subsection

## AI Integration

The situational awareness agent serves two roles:
- **Standalone CLI:** `python3 cross_situational_awareness_agent.py [--date DATE] [--lookback N] [--raw]`
- **Dashboard integration:** Functions imported by `utils/metrics.py`; streaming briefings triggered by button click

The agent computes three analysis layers (snapshot, changes, trends), passes them as JSON to Claude Sonnet 4, and streams the response. The system prompt instructs Claude to produce 8-15 actionable bullets, bad news first.

## Key Design Decisions

1. **Single-process, no database** — ~60K total rows fit in-memory with sub-second Pandas queries
2. **Dual-use agent** — Same code for CLI and dashboard (no duplication)
3. **Streaming AI responses** — `client.messages.stream()` piped to `st.write_stream()`
4. **Filters scope everything** — Including AI briefings, which become region/county-specific automatically
5. **GeoJSON for Kansas counties** — US Census TIGER/Line shapefiles joined on FIPS code
6. **Dark theme** — Dark red (#B22222) primary, dark background (#0E1117), plotly_dark template
7. **Thresholds in session state** — No database persistence; thresholds reset on page refresh, appropriate for analytical dashboard use. Widget keys are seeded on first run to avoid Streamlit's value/key conflicts
8. **Collapsible subsections** — Transfer Tracking, Incident Timeline, and Threshold Alerts use `st.expander` to reduce information overload while keeping content accessible
9. **Backward-compatible chart APIs** — All threshold parameters default to `None`, so existing chart calls work without modification
