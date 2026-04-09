# CROSS Dashboard

**Crisis Response & Operational Statewide Status** — a state-level analytics dashboard for crisis response leaders providing near real-time visibility into crisis readiness, response performance, and resource movement during public health emergencies.

Prepared by **Francisco Galvez** (Oracle Health HDI Solution Engineer Intern).

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-1.30+-red)
![License](https://img.shields.io/badge/License-Private-gray)

## Dashboard Panels

| Panel | Description |
|---|---|
| **Executive Snapshot** | Top-level KPIs with day-over-day deltas and threshold breach highlighting; collapsible Threshold Alerts subsection with breach summary, county breach table, and breach timeline heatmap |
| **Geographic View** | Interactive Kansas choropleth map with selectable color metrics and threshold breach info in hover data; collapsible Transfer Tracking subsection (Sankey diagram); county drill-down with tabbed detail views |
| **County Drill-Down** | Select a county below the map to view facility-level ICU/staffing, inventory by item, incident history, and alert status timeline — with nested facility detail views and threshold breach indicators |
| **Logistics & Operations** | PPE inventory trends, staff availability by region, equipment transfer volumes, average supply delays — all with configurable threshold reference lines |
| **Emerging Threats** | 30-day trend lines with confidence bands, anomaly detection markers, threshold reference lines, alert status donut chart, critical county table, and collapsible Incident Timeline subsection |
| **AI Briefing** | On-demand executive summary powered by Claude Sonnet 4 with streaming response; daily digest export in Markdown and PDF formats |

## Tech Stack

- **Frontend:** Streamlit (wide layout, dark theme)
- **Data:** Pandas, in-memory star schema from Excel (~60K rows across 15 sheets)
- **Visualizations:** Plotly (choropleth maps, time-series, bar charts, donut charts)
- **AI:** Anthropic Claude API with streaming responses
- **Geography:** Kansas county boundaries via US Census TIGER/Line GeoJSON

## Quick Start

### Prerequisites

- Python 3.10+
- An Anthropic API key (required only for AI briefings)

### Installation

```bash
git clone <repo-url>
cd "CROSS Dashboard Project"
pip install -r requirements.txt
```

### Configuration

Create a `.streamlit/secrets.toml` file for the AI briefing feature:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
```

Alternatively, copy `.env.example` and set your key there.

### Run

```bash
streamlit run app.py
```

The dashboard opens at **http://localhost:8501**.

## Project Structure

```
CROSS Dashboard Project/
├── app.py                                # Streamlit entry point (7 panels + AI)
├── cross_situational_awareness_agent.py  # AI agent (standalone CLI + importable)
├── data/
│   ├── KS_CROSS_mock_dataset.xlsx        # Source dataset (Kansas mock data)
│   └── kansas_counties.geojson           # County boundary polygons
├── utils/
│   ├── data_loader.py                    # Load, cache, join, and filter Excel sheets
│   ├── metrics.py                        # KPI computation, snapshots, trends, drill-down metrics, threshold evaluation, digest export
│   ├── charts.py                         # Plotly chart builder functions (18 chart types)
│   └── faq_agent.py                      # OpenAI Agent SDK FAQ assistant
├── .streamlit/
│   └── config.toml                       # Theme and layout settings
├── docs/
│   ├── architecture.md                   # System architecture documentation
│   ├── changelog.md                      # Change history
│   └── project_status.md                 # Milestone tracking
├── requirements.txt                      # Python dependencies
├── project_spec.md                       # Full product specification
└── CLAUDE.md                             # AI coding assistant context
```

## Data Model

The dataset uses a **star schema** with 8 dimension tables and 5 fact tables covering 90 days of Kansas crisis response data (2025-12-05 to 2026-03-04):

**Dimensions:** State, Region (6), County (105), Date (90 days), Facility Type (5), Facility (127), Incident Type (6), Item (4 supply types)

**Fact Tables:**
- `Fact_DailyCountyMetrics` — daily per-county KPIs (9,450 rows)
- `Fact_FacilityCapacityDaily` — facility bed/ICU/staffing (11,430 rows)
- `Fact_InventoryDaily` — per-county per-item inventory (37,800 rows)
- `Fact_ResourceTransfers` — inter-county shipments (556 rows)
- `Fact_IncidentEvents` — individual incidents with timing and severity (4,525 rows)

## AI Situational Awareness Agent

The agent can run standalone or integrated into the dashboard:

```bash
# Run for latest date (1-day comparison)
python3 cross_situational_awareness_agent.py

# Specific date with 7-day lookback
python3 cross_situational_awareness_agent.py --date 2026-02-15 --lookback 7

# Raw metrics JSON (no API key needed)
python3 cross_situational_awareness_agent.py --raw
```

In the dashboard, click **Generate Briefing** in the AI panel to get a streaming executive summary scoped to your active filters. Use the **Download Markdown** or **Download PDF** buttons to export a daily digest for email distribution.

## Filters

All panels respond to sidebar filters:

- **Date range** — constrain the analysis window
- **Region** — filter to one or more of Kansas's 6 regions
- **County** — cascading filter (narrows based on selected regions)
- **Incident type** — filter by emergency category
- **Alert thresholds** — configure custom thresholds (ICU %, response time, PPE days, staff shortage, supply delay, stress score) that trigger visual indicators across all panels

## Drill-Down Navigation

From any high-level KPI, users can drill down to county, facility, and incident level in 2-3 clicks:

1. **Select a county** below the Geographic View map
2. **View 4 tabs**: Facilities (ICU bars + nested facility selector), Inventory, Incidents, Alert History
3. **Select a facility** to see ICU trend, staff fill rate, and bed occupancy charts

The **Transfer Tracking** panel shows a Sankey diagram of inter-county resource flows, color-coded by delay status. The **Incident Timeline** provides a filterable table of all individual events.

## Roadmap

- [x] ~~County and facility drilldown views~~
- [x] ~~Resource transfer Sankey diagrams~~
- [x] ~~Incident event timeline~~
- [x] ~~Configurable alert thresholds with visual indicators~~
- [x] ~~Threshold breach timeline and alert history~~
- [x] ~~PDF/Markdown daily digest export~~
- [ ] Role-based access controls (RBAC)
- [ ] Multi-state scalability
- [ ] Real-time data feed integration
