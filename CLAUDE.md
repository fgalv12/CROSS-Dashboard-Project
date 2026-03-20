# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**CROSS Dashboard** (Crisis Response & Operational Statewide Status) is a state-level analytics dashboard for crisis response leaders. It provides near real-time visibility into crisis readiness, response performance, and resource movement during public health emergencies or statewide crises.

Prepared by Francisco Galvez (Oracle Health HDI Solution Engineer Intern). This is currently in the **design/planning phase** — no production code exists yet.

## Key Documents

- `project_spec.md` - Full requirements, API specs, tech details
- `State Crisis Response Dashboard v1_FG.docx` — Full requirements document (purpose, scope, features, data model, KPIs, open questions)
- `CROSS Dashboard.png` — Dashboard mockup showing all four panels
- `KS_CROSS_mock_dataset.xlsx` — Mock dataset (Kansas) star schema with 15 sheets (see Data Model below)
- `Screenshot 2026-03-09 at 11.08.35 AM.png` — Dataset schema/structure overview
- `cross_situational_awareness_agent.py` — AI agent that analyzes dashboard data and generates executive briefings
- Update files in the docs folder after major milestones and major additions to the project.
- Use the /update-docs-and-commit slash command when making git commits.

## Dashboard Architecture (Four Panels)

1. **Executive Snapshot** — Top-level KPIs: Total Active Incidents, ICU Capacity %, Avg Response Time, Resource Deployment Lag, Counties in Alert Status
2. **Geographic View** — Map with incident density heatmap, hospital capacity overlay, severity color-coding (Normal/Watch/Alert/Critical)
3. **Logistics & Operations** — PPE inventory trends, staff availability by region, equipment transfers between counties, average supply delays
4. **Emerging Threat Panel** — 30/60/90 day trend lines, spike detection flags, trending-upward counties list

## Architecture Overview

**File structure:**

```
CROSS Dashboard Project/
├── app.py                                # Streamlit entry point
├── cross_situational_awareness_agent.py  # AI agent (existing, also importable)
├── data/
│   └── KS_CROSS_mock_dataset.xlsx        # Source dataset
├── utils/
│   ├── data_loader.py                    # Load + cache + join Excel sheets
│   ├── metrics.py                        # KPI computation, snapshot, changes, trends
│   └── charts.py                         # Plotly chart builder functions
├── .streamlit/
│   ├── config.toml                       # Theme, layout settings
│   └── secrets.toml                      # ANTHROPIC_API_KEY (not committed)
├── requirements.txt                      # anthropic, pandas, openpyxl, streamlit, plotly
├── project_spec.md                       # This file
└── CLAUDE.md                            # AI coding assistant context
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
    ├──▶ Time-series charts (daily aggregates over selected window)
    ├──▶ Trend analysis (30/60/90-day stats + anomaly detection)
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
- TypeScript strict mode
- Run `npm run lint` before committing
- No `any` types without justification

## Repository Etiquette

**Branching**
- ALWAYS create a feature branch before starting major changes
- NEVER commit directly to `main`
- Branch naming: `feature/description` or `fix/description`

**Git workflow for major changes:**
1. Create a new branch: `git checkout -b feature/your-feature-name`
2. Develop and commit on the feature branch
3. Test locally before pushing:
    - `npm run dev` - start dev server at localhost:3000
    - `npm run lint` - check for linting errors
    - `npm run build` - production build to catch type errors
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
1. Run `npm run lint`
2. Run `npm run build` to catch type errors

## Commands

```bash
# Development
npm run dev         # Start dev server at localhost:3000
npm run build       # Production build (also catches type errors)
npm run start       # Run production build locally
npm run lint        # ESLint check
```
