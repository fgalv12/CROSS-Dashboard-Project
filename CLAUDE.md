# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**CROSS Dashboard** (Crisis Response & Operational Statewide Status) is a state-level analytics dashboard for crisis response leaders. It provides near real-time visibility into crisis readiness, response performance, and resource movement during public health emergencies or statewide crises.

Prepared by Francisco Galvez (Oracle Health HDI Solution Engineer Intern). Milestones 1-4 are complete — the dashboard is fully functional with drill-down views, configurable alert thresholds, threshold breach tracking, and daily digest export.

## Key Documents

- `project_spec.md` - Full requirements, API specs, tech details
- `State Crisis Response Dashboard v1_FG.docx` — Full requirements document (purpose, scope, features, data model, KPIs, open questions)
- `CROSS Dashboard.png` — Dashboard mockup showing all four panels
- `KS_CROSS_mock_dataset.xlsx` — Mock dataset (Kansas) star schema with 15 sheets (see Data Model below)
- `Screenshot 2026-03-09 at 11.08.35 AM.png` — Dataset schema/structure overview
- `cross_situational_awareness_agent.py` — AI agent that analyzes dashboard data and generates executive briefings
- Update files in the docs folder after major milestones and major additions to the project.
- Use the /update-docs-and-commit slash command when making git commits.

## Dashboard Architecture (Panels + AI)

1. **AI Briefing** — On-demand streaming executive summary powered by Claude Sonnet 4 with 1/7/30-day lookback; daily digest export (Markdown + PDF)
2. **Executive Snapshot** — Top-level KPIs with day-over-day deltas and threshold breach highlighting; collapsible Threshold Alerts subsection (breach summary chart, county breach table, breach timeline heatmap)
3. **Geographic View** — Choropleth map with selectable color metrics (ICU %, incidents, stress score, alert status) + threshold breach info in hover; collapsible Transfer Tracking subsection (Sankey diagram); county drill-down selector
4. **County Detail View** — Tabbed panel (Facilities, Inventory, Incidents, Alert History) with nested facility drill-down; KPI cards show threshold breach indicators
5. **Logistics & Operations** — PPE inventory trends, staff availability by region, equipment transfers between counties, average supply delays — all with configurable threshold reference lines
6. **Emerging Threat Panel** — 30-day trend lines with confidence bands, anomaly detection, threshold reference lines, alert status donut, critical county table; collapsible Incident Timeline subsection

## Architecture Overview

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
│   ├── metrics.py                        # KPI computation, drill-down metrics, threshold evaluation, digest export, AI prompts
│   ├── charts.py                         # Plotly chart builder functions (18 chart types)
│   └── faq_agent.py                      # OpenAI Agent SDK FAQ assistant
├── .streamlit/
│   ├── config.toml                       # Theme, layout settings
│   └── secrets.toml                      # API keys (not committed)
├── docs/
│   ├── architecture.md                   # System architecture documentation
│   ├── changelog.md                      # Change history
│   └── project_status.md                 # Milestone tracking
├── requirements.txt                      # anthropic, pandas, openpyxl, streamlit, plotly, fpdf2
├── project_spec.md                       # Full product specification
└── CLAUDE.md                             # AI coding assistant context
```

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
    ├──▶ County drill-down → facility-level ICU/staffing, inventory, incidents, alerts
    │       └──▶ Facility drill-down → ICU trend, staff fill rate, bed occupancy
    ├──▶ Transfer Sankey (inter-county resource flows with delay coloring)
    ├──▶ Time-series charts (daily aggregates over selected window)
    ├──▶ Trend analysis (30-day stats + anomaly detection)
    ├──▶ Incident timeline (filterable event table with severity chart)
    │
    ├──▶ Threshold Evaluation (configurable via sidebar)
    │       ├── evaluate_thresholds()           → Statewide breach check
    │       ├── evaluate_county_thresholds()    → Per-county breach check
    │       ├── get_active_breaches()           → Current breach table
    │       └── get_threshold_breach_timeline() → Historical breach heatmap
    │
    ├──▶ Daily Digest Export
    │       ├── build_daily_digest_md() → Markdown report
    │       └── build_daily_digest_pdf()→ PDF report (fpdf2)
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

**Key design decisions:**

1. **Single-process, no database.** The entire dataset is ~60K rows across all fact tables. Pandas handles this in-memory with sub-second query times. Adding a database would increase complexity without improving performance at this scale.

2. **Agent is both standalone and importable.** `cross_situational_awareness_agent.py` works as a CLI tool (`python3 agent.py --date ...`) and its functions (`compute_snapshot`, `compute_changes`, `compute_trends`) are imported by the Streamlit app. No code duplication.

3. **Streaming AI responses.** The Anthropic SDK's `client.messages.stream()` is piped directly to `st.write_stream()`. The user sees the briefing appear word-by-word, matching the mental model of "the AI is analyzing the data right now."

4. **Filters scope everything, including the AI.** When a user selects a region in the sidebar, the AI agent's input data is filtered to that region. The briefing becomes region-specific without needing a separate prompt.

5. **GeoJSON for Kansas counties.** County boundaries loaded from US Census TIGER/Line shapefiles (public domain). Joined to the dataset on FIPS code. Stored as a static `.geojson` file in `data/`.

## Data Model (Star Schema)

**Dimensions:** Dim_State, Dim_Region (6 KS regions), Dim_County (105 counties), Dim_Date (90 days: 2025-12-05 to 2026-03-04), Dim_FacilityType (5 types), Dim_Facility (127 facilities), Dim_IncidentType (6 types), Dim_Item (4 supply items)

**Fact tables:**
- `Fact_DailyCountyMetrics` (9,450 rows) — daily per-county KPIs: incidents, response time, ICU capacity, staffing, PPE, alert status, stress scores
- `Fact_FacilityCapacityDaily` (11,430 rows) — daily per-facility bed/ICU/staffing data
- `Fact_InventoryDaily` (37,800 rows) — daily per-county per-item inventory levels
- `Fact_ResourceTransfers` (556 rows) — inter-county resource shipments
- `Fact_IncidentEvents` (4,525 rows) — individual incidents with detection/escalation/response times and severity

## AI Situational Awareness Agent

`cross_situational_awareness_agent.py` — reads the dataset, computes metrics/changes/trends, and calls Claude API to generate executive briefings.

```bash
# Prerequisites
pip install anthropic pandas openpyxl
export ANTHROPIC_API_KEY=sk-ant-...

# Run for latest date (1-day comparison)
python3 cross_situational_awareness_agent.py

# Specific date with 7-day lookback
python3 cross_situational_awareness_agent.py --date 2026-02-15 --lookback 7

# Raw metrics JSON (no API key needed)
python3 cross_situational_awareness_agent.py --raw
```

## Data Considerations

- Data is county/region-level, aggregated and de-identified (no PHI/PII at the dashboard layer)
- Must support county/regional drilldowns and date range filtering
- KPI definitions must be standardized for multi-state scalability
- Dashboard must load quickly for briefing use; designed for minimal clicks
- Role-based access controls (RBAC) required

## Design Constraints

- This is an **informational dashboard**, not a command-and-control system — it informs decisions but does not replace incident management
- Current scope is conceptual design and batch/refresh-based reporting, not real-time streaming
- Start with minimum viable dashboard using most reliable data feeds, then iterate

## Constraints & Policies

**Security - MUST follow:**
- No PHI/PII in the dataset — all metrics are county-level aggregates.
- API key managed via Streamlit secrets, not environment variables in code.
- If deployed, Streamlit Community Cloud or internal hosting with SSO/RBAC via Streamlit's auth layer.
- NEVER expose `ANTHROPIC_API_KEY` to client - server-side only
- ALWAYS use envrionment variables for secrets
- NEVER commit `.env.local` or any file with API keys
- Validate and sanitize all user input

**Code Quality**
- Follow PEP 8 conventions
- Type hints for function signatures
- Test locally before committing

## Repository Etiquette

**Branching**
- ALWAYS create a feature branch before starting major changes
- NEVER commit directly to `main`
- Branch naming: `feature/description` or `fix/description`

**Git workflow for major changes:**
1. Create a new branch: `git checkout -b feature/your-feature-name`
2. Develop and commit on the feature branch
3. Test locally before pushing:
    - `streamlit run app.py` - start dev server at localhost:8501
    - Verify all panels render without errors
4. Push the branch: `git push -u origin feature/your-feature-name`
5. Create a PR to merge into `main`
6. Use the `/update-docs-and-commit` slash command for commits - this ensures docs are updated alongside code changes

**Commits:**
- Write clear commit messages describing the change
- Keep commits focused on single changes

**Pull Requests:**
- Create PRs for all changes to `main`
- NEVER force push to `main`
- Include description of what changed and why

**Before pushing:**
1. Run `streamlit run app.py` and verify all panels load
2. Check for Python syntax errors

## Commands

```bash
# Development
pip install -r requirements.txt   # Install dependencies
streamlit run app.py              # Start dashboard at localhost:8501

# AI Agent (standalone)
python3 cross_situational_awareness_agent.py              # Latest date briefing
python3 cross_situational_awareness_agent.py --raw         # JSON output only
python3 cross_situational_awareness_agent.py --lookback 7  # 7-day comparison
```
