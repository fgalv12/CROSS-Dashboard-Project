# CROSS Dashboard – Project Specification

## 1. Product Requirements

### 1.1 Purpose

The **CROSS Dashboard** (Crisis Response & Operational Statewide Status) gives state-level crisis response leaders a single screen to assess readiness, monitor active response, and direct resources during public health emergencies or statewide crises — without reading spreadsheets or waiting for manual reports.

### 1.2 Who Is This For?

| Audience | How they use it |
|---|---|
| **Governor's office / State leadership** | Morning briefing: "Are we in trouble anywhere?" — glance at the Executive Snapshot and AI Summary |
| **State Health Department ops leads** | Drill into regions and counties to decide where to send staff, equipment, and supplies |
| **Emergency Operations leadership** | Monitor response times, escalation patterns, and emerging hotspots in real time |
| **Hospital coalition coordinators** | Track facility-level ICU capacity, staffing gaps, and inter-county resource transfers |

### 1.3 Problems It Solves

1. **Data is siloed.** Hospital data, logistics feeds, incident reports, and inventory systems don't talk to each other. Leaders lack a unified view of what's happening across the state.
2. **Decisions are reactive.** Without trend monitoring and early-warning indicators, leadership only learns about capacity crises after they've already hit.
3. **Dashboard overload.** Even when data is available, busy leaders don't have time to interpret dozens of charts. They need the data to tell them what matters — not the other way around.

### 1.4 What the Product Does

The dashboard has five capabilities, organized as milestones.

---

**Milestone 1 — Statewide Situational Awareness (Core Dashboard)**

Deliver the four-panel dashboard with real data from the CROSS dataset.

| Capability | Detail |
|---|---|
| **Executive Snapshot** | KPI cards: Total Active Incidents, ICU Capacity %, Avg Response Time, Resource Deployment Lag, Counties in Alert/Critical Status |
| **Geographic View** | Interactive Kansas county map with incident density heatmap, ICU capacity overlay, and severity color-coding (Normal → Watch → Alert → Critical) |
| **Logistics & Operations** | Time-series charts: PPE inventory trends, staff availability by region, equipment transfer flows between counties, average supply delays |
| **Emerging Threat Panel** | 30/60/90-day trend lines for key metrics, spike detection flags, list of trending-upward counties |

Filters: date range, region, county, incident type, facility type.

**Definition of done:** A user can open the dashboard, see today's statewide status at a glance, click into a region or county, and identify capacity risks — all without touching a spreadsheet.

---

**Milestone 2 — AI Situational Awareness Agent**

Integrate the AI agent directly into the dashboard as a streaming panel. Instead of reading every chart, a decision-maker sees a plain-language briefing that answers:

- **What changed?** (vs. prior day or prior week)
- **What looks abnormal?** (statistical outliers, threshold breaches)
- **What requires attention?** (items needing decisions or escalation)

| Capability | Detail |
|---|---|
| **On-demand briefing** | User clicks "Generate Briefing" and sees the AI summary stream into the dashboard in real time |
| **Configurable lookback** | Toggle between 1-day, 7-day, and 30-day comparison windows |
| **Context-aware** | Briefing reflects the user's active filters (if they've drilled into a specific region, the AI focuses there) |

**Definition of done:** A state leader can open the dashboard and within 15 seconds have a written executive summary of what's happening, what's abnormal, and what needs their attention — without interpreting a single chart.

---

**Milestone 3 — Drill-Down and Detail Views**

| Capability | Detail |
|---|---|
| **County detail view** | Click a county on the map → see facility-level ICU/staffing data, inventory levels by item, incident history, and alert status timeline |
| **Facility detail view** | Click a facility → see daily bed occupancy, staff fill rate, ICU trend |
| **Transfer tracking** | Sankey or flow diagram showing resource movement between counties (volume, direction, delay status) |
| **Incident timeline** | Filterable table of individual incident events with detection time, escalation time, response time, severity, and type |

**Definition of done:** From any high-level KPI, a user can drill down to county → facility → individual incident level in 2-3 clicks.

---

**Milestone 4 — Alerting and Thresholds** *(Completed 2026-04-09)*

| Capability | Detail | Status |
|---|---|---|
| **Configurable alert thresholds** | Users set thresholds (e.g., ICU > 90%, PPE < 5 days on hand) that trigger visual indicators | Done |
| **Alert history** | Timeline showing when counties entered/exited each alert status | Done |
| **Daily digest export** | Generate and download a PDF or Markdown briefing for email distribution | Done |

**Definition of done:** A user can configure their own alert thresholds and receive a daily digest without opening the dashboard.

**Implementation notes:** 6 configurable thresholds stored in Streamlit session state. Threshold Alerts panel (collapsed expander) shows breach summary, county breach table, and interactive heatmap. Daily digest available as Markdown and PDF downloads in the AI Briefing panel. Panel reorganization collapses Transfer Tracking, Incident Timeline, and Threshold Alerts into expanders to reduce information overload.

---

## 2. Technical Design

### 2.1 Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| **Frontend / App** | **Streamlit** (Python) | Fastest path from existing Python agent to interactive dashboard. Native support for charts, maps, layout, and streaming text. No JS build tooling required. |
| **Charts** | **Plotly Express** | Integrates natively with Streamlit via `st.plotly_chart`. Rich interactivity (hover, zoom, click) without custom code. Supports all required chart types: line, bar, heatmap, Sankey, choropleth. |
| **Map** | **Plotly Choropleth** (county-level GeoJSON) | Same library as charts — no extra dependencies. Kansas county boundaries available via US Census GeoJSON. Supports heatmap fill, hover tooltips, and click events. |
| **Data layer** | **Pandas + Excel/JSON files** | Dataset is static (90 days, ~60K total fact rows). Fits entirely in memory. No database overhead. Excel file is loaded once at app startup and cached. |
| **AI Agent** | **Anthropic Python SDK** (`anthropic`) | Existing agent already built. Streaming support via `client.messages.stream()` for real-time briefing generation. Uses `claude-sonnet-4-20250514`. |
| **Language** | **Python 3.11+** | Single language across the entire stack. |

### 2.2 Engineering Requirements

**Performance**
- Dashboard must load in under 3 seconds with the full dataset cached in memory.
- AI briefing must begin streaming within 2 seconds of request.
- All chart interactions (filter, hover, drill-down) must respond in under 500ms.

**Data handling**
- Dataset is loaded once at startup using `@st.cache_data` and persisted across user sessions.
- No database. If the dataset grows beyond memory (unlikely for state-level daily aggregates), migrate to SQLite.
- All date filtering, aggregation, and comparison logic happens in Pandas.

**AI agent integration**
- Agent runs server-side; API key is stored in Streamlit secrets (`.streamlit/secrets.toml`), never exposed to the client.
- Streaming responses rendered via `st.write_stream()` for real-time output.
- Agent receives the same structured metrics JSON it currently computes (snapshot + changes + trends), scoped to the user's active filters.

**Security**
- No PHI/PII in the dataset — all metrics are county-level aggregates.
- API key managed via Streamlit secrets, not environment variables in code.
- If deployed, Streamlit Community Cloud or internal hosting with SSO/RBAC via Streamlit's auth layer.

### 2.3 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Streamlit App                         │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Executive   │  │  Geographic  │  │  Logistics &  │  │
│  │  Snapshot    │  │  View (Map)  │  │  Operations   │  │
│  │  (KPI Cards) │  │  (Plotly     │  │  (Plotly      │  │
│  │             │  │  Choropleth) │  │  time series) │  │
│  └─────────────┘  └──────────────┘  └───────────────┘  │
│                                                         │
│  ┌──────────────────┐  ┌────────────────────────────┐   │
│  │  Emerging Threat  │  │  AI Situational Awareness  │   │
│  │  Panel (Plotly    │  │  Agent (streaming panel)   │   │
│  │  trend lines)     │  │                            │   │
│  └──────────────────┘  └─────────────┬──────────────┘   │
│                                      │                   │
│  ┌───────────────────┐               │                   │
│  │  Sidebar Filters  │               │                   │
│  │  Date / Region /  │               │                   │
│  │  County / Type    │               │                   │
│  └───────────────────┘               │                   │
│                                      │                   │
├──────────────────────────────────────┼───────────────────┤
│             Data Layer               │   AI Layer        │
│                                      │                   │
│  ┌─────────────────────────┐   ┌─────┴─────────────┐    │
│  │  Pandas DataFrames      │   │  Anthropic SDK     │    │
│  │  (cached at startup)    │   │  claude-sonnet     │    │
│  │                         │   │                    │    │
│  │  Source:                │   │  Input: structured │    │
│  │  KS_CROSS_mock_dataset  │   │  metrics JSON      │    │
│  │  .xlsx                  │   │                    │    │
│  │                         │   │  Output: streaming │    │
│  │  Fact tables joined     │   │  markdown briefing │    │
│  │  with dimension tables  │   │                    │    │
│  └─────────────────────────┘   └────────────────────┘    │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### 2.4 System Design

**Data flow:**

```
Excel file (.xlsx)
    │
    ▼
Load all 15 sheets into Pandas DataFrames (@st.cache_data)
    │
    ▼
Join fact tables with dimensions (region names, county names, item names, etc.)
    │
    ├──▶ Sidebar filters select date range, region, county, incident type
    │
    ▼
Filtered DataFrames
    │
    ├──▶ KPI cards (aggregated scalars)
    ├──▶ Choropleth map (county-level metrics)
    ├──▶ County drill-down → facility ICU/staffing, inventory, incidents, alerts
    │       └──▶ Facility drill-down → ICU trend, staff fill rate, bed occupancy
    ├──▶ Transfer Sankey (inter-county resource flows)
    ├──▶ Time-series charts (daily aggregates over selected window)
    ├──▶ Trend analysis (30-day stats + anomaly detection)
    ├──▶ Incident timeline (filterable event table with severity chart)
    │
    └──▶ AI Agent
            │
            ├── Compute snapshot (current date metrics)
            ├── Compute changes (vs. prior period)
            ├── Compute trends (30-day z-scores)
            │
            ▼
         Anthropic API (streaming)
            │
            ▼
         Rendered as streaming Markdown in dashboard panel
```

**File structure:**

```
CROSS Dashboard Project/
├── app.py                                # Streamlit entry point (7 panels + AI)
├── cross_situational_awareness_agent.py  # AI agent (standalone CLI + importable)
├── data/
│   ├── KS_CROSS_mock_dataset.xlsx        # Source dataset
│   └── kansas_counties.geojson           # County boundary polygons (TIGER/Line)
├── utils/
│   ├── data_loader.py                    # Load + cache + join + filter Excel sheets
│   ├── metrics.py                        # KPI computation, drill-down metrics, AI prompts
│   ├── charts.py                         # Plotly chart builder functions (16 chart types)
│   └── faq_agent.py                      # OpenAI Agent SDK FAQ assistant
├── .streamlit/
│   ├── config.toml                       # Theme, layout settings
│   └── secrets.toml                      # API keys (not committed)
├── docs/
│   ├── architecture.md                   # System architecture documentation
│   ├── changelog.md                      # Change history
│   └── project_status.md                 # Milestone tracking
├── requirements.txt                      # anthropic, pandas, openpyxl, streamlit, plotly
├── project_spec.md                       # This file
└── CLAUDE.md                             # AI coding assistant context
```

**Key design decisions:**

1. **Single-process, no database.** The entire dataset is ~60K rows across all fact tables. Pandas handles this in-memory with sub-second query times. Adding a database would increase complexity without improving performance at this scale.

2. **Agent is both standalone and importable.** `cross_situational_awareness_agent.py` works as a CLI tool (`python3 agent.py --date ...`) and its functions (`compute_snapshot`, `compute_changes`, `compute_trends`) are imported by the Streamlit app. No code duplication.

3. **Streaming AI responses.** The Anthropic SDK's `client.messages.stream()` is piped directly to `st.write_stream()`. The user sees the briefing appear word-by-word, matching the mental model of "the AI is analyzing the data right now."

4. **Filters scope everything, including the AI.** When a user selects a region in the sidebar, the AI agent's input data is filtered to that region. The briefing becomes region-specific without needing a separate prompt.

5. **GeoJSON for Kansas counties.** County boundaries loaded from US Census TIGER/Line shapefiles (public domain). Joined to the dataset on FIPS code. Stored as a static `.geojson` file in `data/`.
