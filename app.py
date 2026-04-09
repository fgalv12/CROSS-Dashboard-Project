"""
CROSS Dashboard — Crisis Response & Operational Statewide Status
Streamlit entry point with 4 panels + AI Situational Awareness Agent.
"""

import os
import streamlit as st

st.set_page_config(
    page_title="CROSS Dashboard",
    page_icon="\u271a",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Set OpenAI API key from Streamlit secrets into env (needed by Agent SDK)
if "OPENAI_API_KEY" not in os.environ or not os.environ["OPENAI_API_KEY"]:
    try:
        os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
    except Exception:
        # Fallback: read directly from secrets.toml
        try:
            import tomllib
            _secrets_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                ".streamlit", "secrets.toml",
            )
            with open(_secrets_path, "rb") as _f:
                _sec = tomllib.load(_f)
            os.environ["OPENAI_API_KEY"] = _sec.get("OPENAI_API_KEY", "")
        except Exception:
            st.warning("OPENAI_API_KEY not found — FAQ agent will not work.")

import pandas as pd

# ---------------------------------------------------------------------------
# Alert Threshold Defaults
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS = {
    "icu_capacity_pct": {"value": 90.0, "direction": ">=", "label": "ICU Capacity %", "unit": "%"},
    "avg_response_time": {"value": 4.0, "direction": ">=", "label": "Avg Response Time", "unit": "hrs"},
    "ppe_days_on_hand": {"value": 5.0, "direction": "<=", "label": "PPE Days on Hand", "unit": "days"},
    "staff_shortage_rate": {"value": 0.15, "direction": ">=", "label": "Staff Shortage Rate", "unit": ""},
    "supply_delay_days": {"value": 3.0, "direction": ">=", "label": "Supply Delay", "unit": "days"},
    "capacity_stress_score": {"value": 0.7, "direction": ">=", "label": "Stress Score", "unit": ""},
}

from utils.data_loader import (
    filter_data,
    get_counties,
    get_date_range,
    get_facilities,
    get_incident_types,
    get_regions,
    load_data,
    load_geojson,
)
from utils.metrics import (
    SYSTEM_PROMPT,
    _datesk_to_date,
    _prior_datesk,
    build_briefing_prompt,
    compute_changes,
    compute_snapshot,
    compute_trends,
    evaluate_county_thresholds,
    evaluate_thresholds,
    build_daily_digest_md,
    build_daily_digest_pdf,
    get_active_breaches,
    get_county_alert_timeline,
    get_county_detail,
    get_county_facility_capacity,
    get_county_incidents,
    get_county_inventory,
    get_county_metrics_for_map,
    get_facility_detail,
    get_incident_timeline,
    get_inventory_series,
    get_kpi_cards,
    get_staff_by_region,
    get_supply_delay_series,
    get_threshold_breach_timeline,
    get_transfer_flows,
    get_transfer_summary,
    get_trend_series,
    resolve_datesk,
)
from utils.charts import (
    make_alert_donut,
    make_alert_timeline,
    make_breach_heatmap,
    make_breach_summary,
    make_choropleth,
    make_county_inventory_detail,
    make_facility_bed_occupancy,
    make_facility_capacity_bars,
    make_facility_icu_trend,
    make_facility_staff_trend,
    make_incident_severity_chart,
    make_ppe_trend,
    make_staff_availability,
    make_supply_delay,
    make_transfer_sankey,
    make_transfer_volume,
    make_trend_line,
)

# ---------------------------------------------------------------------------
# Data Loading
# ---------------------------------------------------------------------------

@st.cache_data
def cached_load():
    return load_data()

data = cached_load()
geojson = load_geojson()

min_date, max_date = get_date_range(data)
regions = get_regions(data)
incident_types = get_incident_types(data)

# ---------------------------------------------------------------------------
# Sidebar Filters
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### \u271a CROSS Dashboard")
    st.caption("Crisis Response & Operational Statewide Status")
    st.divider()

    # Date range
    st.markdown("**Date Range**")
    date_range = st.date_input(
        "Select date range",
        value=(min_date.date(), max_date.date()),
        min_value=min_date.date(),
        max_value=max_date.date(),
        label_visibility="collapsed",
    )

    # Handle single date selection
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = end_date = date_range if not isinstance(date_range, tuple) else date_range[0]

    st.divider()

    # Region filter
    region_options = {r["RegionName"]: r["RegionSK"] for r in regions}
    selected_region_names = st.multiselect(
        "Region",
        options=list(region_options.keys()),
        default=[],
        placeholder="All regions",
    )
    selected_region_sks = [region_options[n] for n in selected_region_names] if selected_region_names else None

    # County filter (cascading — filtered by region)
    counties = get_counties(data, region_sks=selected_region_sks)
    county_options = {c["CountyName"]: c["CountySK"] for c in counties}
    selected_county_names = st.multiselect(
        "County",
        options=list(county_options.keys()),
        default=[],
        placeholder="All counties",
    )
    selected_county_sks = [county_options[n] for n in selected_county_names] if selected_county_names else None

    st.divider()

    # Incident type filter (informational — displayed but not used for main filtering)
    incident_options = {t["IncidentTypeName"]: t["IncidentTypeSK"] for t in incident_types}
    selected_incident_names = st.multiselect(
        "Incident Type",
        options=list(incident_options.keys()),
        default=[],
        placeholder="All types",
    )

    # ------------------------------------------------------------------
    # Alert Threshold Configuration
    # ------------------------------------------------------------------
    st.divider()
    st.markdown("**Alert Thresholds**")

    # Initialize session state
    if "alert_thresholds" not in st.session_state:
        import copy
        st.session_state.alert_thresholds = copy.deepcopy(DEFAULT_THRESHOLDS)

    # Reset callback — runs before widgets are instantiated on next rerun
    def _reset_thresholds():
        import copy
        st.session_state.alert_thresholds = copy.deepcopy(DEFAULT_THRESHOLDS)
        st.session_state.thresh_icu = DEFAULT_THRESHOLDS["icu_capacity_pct"]["value"]
        st.session_state.thresh_response = DEFAULT_THRESHOLDS["avg_response_time"]["value"]
        st.session_state.thresh_ppe = DEFAULT_THRESHOLDS["ppe_days_on_hand"]["value"]
        st.session_state.thresh_staff = DEFAULT_THRESHOLDS["staff_shortage_rate"]["value"]
        st.session_state.thresh_delay = DEFAULT_THRESHOLDS["supply_delay_days"]["value"]
        st.session_state.thresh_stress = DEFAULT_THRESHOLDS["capacity_stress_score"]["value"]

    thresholds = st.session_state.alert_thresholds

    # Seed widget keys on first run so number_inputs pick up defaults
    _THRESH_WIDGET_MAP = {
        "thresh_icu": ("icu_capacity_pct", 0.0, 100.0, 5.0, None),
        "thresh_response": ("avg_response_time", 0.0, 24.0, 0.5, None),
        "thresh_ppe": ("ppe_days_on_hand", 0.0, 30.0, 1.0, None),
        "thresh_staff": ("staff_shortage_rate", 0.0, 1.0, 0.05, "%.2f"),
        "thresh_delay": ("supply_delay_days", 0.0, 14.0, 0.5, None),
        "thresh_stress": ("capacity_stress_score", 0.0, 1.0, 0.05, "%.2f"),
    }
    for wkey, (tkey, *_) in _THRESH_WIDGET_MAP.items():
        if wkey not in st.session_state:
            st.session_state[wkey] = thresholds[tkey]["value"]

    with st.expander("Configure thresholds", expanded=False):
        thresholds["icu_capacity_pct"]["value"] = st.number_input(
            "ICU Capacity % (alert when >=)",
            min_value=0.0, max_value=100.0,
            step=5.0, key="thresh_icu",
        )
        thresholds["avg_response_time"]["value"] = st.number_input(
            "Avg Response Time hrs (alert when >=)",
            min_value=0.0, max_value=24.0,
            step=0.5, key="thresh_response",
        )
        thresholds["ppe_days_on_hand"]["value"] = st.number_input(
            "PPE Days on Hand (alert when <=)",
            min_value=0.0, max_value=30.0,
            step=1.0, key="thresh_ppe",
        )
        thresholds["staff_shortage_rate"]["value"] = st.number_input(
            "Staff Shortage Rate (alert when >=)",
            min_value=0.0, max_value=1.0,
            step=0.05, format="%.2f", key="thresh_staff",
        )
        thresholds["supply_delay_days"]["value"] = st.number_input(
            "Supply Delay days (alert when >=)",
            min_value=0.0, max_value=14.0,
            step=0.5, key="thresh_delay",
        )
        thresholds["capacity_stress_score"]["value"] = st.number_input(
            "Capacity Stress Score (alert when >=)",
            min_value=0.0, max_value=1.0,
            step=0.05, format="%.2f", key="thresh_stress",
        )

        st.button("Reset to Defaults", key="thresh_reset", on_click=_reset_thresholds)

    st.divider()
    st.caption(f"Data: {min_date.date()} to {max_date.date()}")

    # ------------------------------------------------------------------
    # FAQ Chat Widget (sidebar)
    # ------------------------------------------------------------------
    st.divider()
    st.markdown("**💬 CROSS FAQ Assistant**")
    st.caption("Ask questions about the CROSS Dashboard")

    # Initialize FAQ chat state
    if "faq_messages" not in st.session_state:
        st.session_state.faq_messages = []
    if "faq_history" not in st.session_state:
        st.session_state.faq_history = []

    # Chat input at top
    faq_input = st.chat_input("Ask about CROSS...", key="faq_chat_input")

    if faq_input:
        # Get FAQ agent response before rendering
        try:
            from utils.faq_agent import run_faq

            answer, updated_history = run_faq(
                faq_input,
                st.session_state.faq_history,
            )
            st.session_state.faq_history = updated_history
            st.session_state.faq_messages.insert(
                0, {"role": "assistant", "content": answer}
            )
        except Exception as e:
            st.session_state.faq_messages.insert(
                0, {"role": "assistant", "content": f"FAQ error: {e}"}
            )
        st.session_state.faq_messages.insert(
            0, {"role": "user", "content": faq_input}
        )

    # Display chat history (newest first) in scrollable container
    if st.session_state.faq_messages:
        with st.container(height=400):
            for msg in st.session_state.faq_messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

# ---------------------------------------------------------------------------
# Apply Filters
# ---------------------------------------------------------------------------

filtered = filter_data(
    data,
    date_range=(pd.Timestamp(start_date), pd.Timestamp(end_date)),
    region_sks=selected_region_sks,
    county_sks=selected_county_sks,
)

# Resolve current date (latest in filtered range)
end_datesk = resolve_datesk(filtered, str(end_date))
start_datesk = int(pd.Timestamp(start_date).strftime("%Y%m%d"))

# ---------------------------------------------------------------------------
# Title Bar
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div style="text-align: center; padding: 0.5rem 0 0.2rem 0;">
        <h1 style="color: #B22222; margin-bottom: 0; font-size: 1.8rem;">
            &#10010; Crisis Response & Operational Statewide Status (CROSS) Dashboard
        </h1>
        <p style="color: #888; margin-top: 0.2rem; font-size: 0.9rem;">
            Kansas &mdash; Real-Time Crisis Readiness & Response Analytics
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# AI Briefing Panel
# ---------------------------------------------------------------------------

with st.expander("\U0001f916 AI Situational Awareness Briefing", expanded=False):
    col_lookback, col_button, _ = st.columns([2, 1, 3])
    with col_lookback:
        lookback = st.radio(
            "Comparison period",
            options=[1, 7, 30],
            format_func=lambda x: f"{x}-day lookback",
            horizontal=True,
            label_visibility="collapsed",
        )
    with col_button:
        generate = st.button("\U0001f4ca Generate Briefing", type="primary", use_container_width=True)

    # Persist briefing in session state
    if "briefing_text" not in st.session_state:
        st.session_state.briefing_text = None

    if generate:
        # Compute metrics for the AI
        snapshot = compute_snapshot(filtered, end_datesk)
        prior_sk = _prior_datesk(filtered, end_datesk, lookback)
        prior_snapshot = compute_snapshot(filtered, prior_sk) if prior_sk else None
        changes = compute_changes(snapshot, prior_snapshot) if prior_snapshot else None
        trends = compute_trends(filtered, end_datesk)

        # Build active filter context
        active_filters = {}
        if selected_region_names:
            active_filters["regions"] = selected_region_names
        if selected_county_names:
            active_filters["counties"] = selected_county_names
        if selected_incident_names:
            active_filters["incident_types"] = selected_incident_names

        user_message = build_briefing_prompt(
            date_label=str(_datesk_to_date(end_datesk).date()),
            lookback=lookback,
            snapshot=snapshot,
            prior_snapshot=prior_snapshot,
            changes=changes,
            trends=trends,
            active_filters=active_filters if active_filters else None,
        )

        # Stream the AI response
        try:
            import anthropic

            api_key = st.secrets.get("ANTHROPIC_API_KEY")
            if not api_key:
                st.error("ANTHROPIC_API_KEY not found in .streamlit/secrets.toml")
            else:
                client = anthropic.Anthropic(api_key=api_key)
                placeholder = st.empty()
                full_text = ""

                with client.messages.stream(
                    model="claude-sonnet-4-20250514",
                    max_tokens=2048,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_message}],
                ) as stream:
                    for text in stream.text_stream:
                        full_text += text
                        placeholder.markdown(full_text + "\u2588")

                placeholder.markdown(full_text)
                st.session_state.briefing_text = full_text

        except Exception as e:
            st.error(f"AI briefing error: {e}")

    elif st.session_state.briefing_text:
        st.markdown(st.session_state.briefing_text)

    # Daily Digest Export
    st.divider()
    st.markdown("**Export Daily Digest**")

    # Compute digest inputs (uses snapshot computed later, so compute here too)
    _digest_snapshot = compute_snapshot(filtered, end_datesk)
    _digest_prior_sk = _prior_datesk(filtered, end_datesk, 1)
    _digest_prior = compute_snapshot(filtered, _digest_prior_sk) if _digest_prior_sk else None
    _digest_kpis = get_kpi_cards(_digest_snapshot, _digest_prior)
    _digest_breaches = evaluate_thresholds(_digest_snapshot, thresholds)
    _digest_active = get_active_breaches(filtered, end_datesk, thresholds)
    _digest_date = str(_datesk_to_date(end_datesk).date())

    _digest_filters = {}
    if selected_region_names:
        _digest_filters["regions"] = selected_region_names
    if selected_county_names:
        _digest_filters["counties"] = selected_county_names
    if selected_incident_names:
        _digest_filters["incident_types"] = selected_incident_names

    dl_col1, dl_col2, _ = st.columns([1, 1, 3])

    with dl_col1:
        md_content = build_daily_digest_md(
            date_label=_digest_date,
            snapshot=_digest_snapshot,
            kpi_cards=_digest_kpis,
            breach_results=_digest_breaches,
            active_breaches_df=_digest_active,
            briefing_text=st.session_state.briefing_text,
            active_filters=_digest_filters if _digest_filters else None,
        )
        st.download_button(
            label="Download Markdown",
            data=md_content,
            file_name=f"CROSS_Digest_{_digest_date}.md",
            mime="text/markdown",
            use_container_width=True,
        )

    with dl_col2:
        try:
            pdf_bytes = build_daily_digest_pdf(
                date_label=_digest_date,
                snapshot=_digest_snapshot,
                kpi_cards=_digest_kpis,
                breach_results=_digest_breaches,
                active_breaches_df=_digest_active,
                briefing_text=st.session_state.briefing_text,
                active_filters=_digest_filters if _digest_filters else None,
            )
            st.download_button(
                label="Download PDF",
                data=pdf_bytes,
                file_name=f"CROSS_Digest_{_digest_date}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except ImportError:
            st.warning("Install `fpdf2` for PDF export: `pip install fpdf2`")

# ---------------------------------------------------------------------------
# Panel 1: Executive Snapshot
# ---------------------------------------------------------------------------

st.markdown(
    '<div style="background: #8B1A1A; padding: 0.4rem 1rem; border-radius: 6px; margin: 0.8rem 0 0.5rem 0;">'
    '<h3 style="color: white; margin: 0; font-size: 1.1rem; text-align: center;">Executive Snapshot</h3></div>',
    unsafe_allow_html=True,
)

# Compute KPI snapshots
snapshot = compute_snapshot(filtered, end_datesk)

# Get prior day snapshot for deltas
prior_sk = _prior_datesk(filtered, end_datesk, 1)
prior_snapshot = compute_snapshot(filtered, prior_sk) if prior_sk else None

kpi_cards = get_kpi_cards(snapshot, prior_snapshot)

# Evaluate thresholds for breach highlighting
breach_results = evaluate_thresholds(snapshot, thresholds)

# Map KPI labels to threshold keys for breach detection
KPI_THRESHOLD_MAP = {
    "ICU Capacity %": "icu_capacity_pct",
    "Avg Response Time": "avg_response_time",
    "Resource Deploy Lag": "supply_delay_days",
}

kpi_cols = st.columns(len(kpi_cards))
for col, card in zip(kpi_cols, kpi_cards):
    thresh_key = KPI_THRESHOLD_MAP.get(card["label"])
    breached = thresh_key and breach_results.get(thresh_key, {}).get("breached", False)

    if breached:
        col.markdown(
            f'<div style="border: 2px solid #B22222; border-radius: 8px; padding: 2px 6px; '
            f'background: rgba(178,34,34,0.15);">',
            unsafe_allow_html=True,
        )
    col.metric(
        label=card["label"],
        value=card["value"],
        delta=card["delta"],
        delta_color=card["delta_color"],
    )
    if breached:
        b = breach_results[thresh_key]
        col.markdown(
            f'<div style="color: #FF6B6B; font-size: 0.75rem; margin-top: -0.5rem;">'
            f'Threshold: {b["direction"]} {b["threshold"]}</div></div>',
            unsafe_allow_html=True,
        )

# Threshold Alerts (subsection of Executive Snapshot)
active_breaches_df = get_active_breaches(filtered, end_datesk, thresholds)
_breach_count = len(active_breaches_df)
_breach_label = (
    f"Threshold Alerts — {_breach_count} active breach{'es' if _breach_count != 1 else ''}"
    if _breach_count > 0
    else "Threshold Alerts — No active breaches"
)

with st.expander(_breach_label, expanded=False):
    ta_col1, ta_col2 = st.columns([1, 2])

    with ta_col1:
        fig_breach_summary = make_breach_summary(active_breaches_df)
        st.plotly_chart(fig_breach_summary, use_container_width=True, key="breach_summary")

    with ta_col2:
        if not active_breaches_df.empty:
            st.dataframe(
                active_breaches_df,
                use_container_width=True,
                hide_index=True,
                height=min(_breach_count * 35 + 40, 350),
                column_config={
                    "CountyName": "County",
                    "RegionName": "Region",
                    "Metric": "Threshold",
                    "Value": st.column_config.NumberColumn("Actual", format="%.2f"),
                    "Threshold": st.column_config.NumberColumn("Limit", format="%.2f"),
                    "Direction": "Dir",
                },
            )
        else:
            st.success("No counties are currently breaching any configured thresholds.")

    # Breach timeline heatmap
    breach_timeline_df = get_threshold_breach_timeline(filtered, start_datesk, end_datesk, thresholds)

    if not breach_timeline_df.empty:
        available_metrics = sorted(breach_timeline_df[breach_timeline_df["Breached"]]["Metric"].unique())
        if available_metrics:
            breach_metric = st.selectbox(
                "View breach timeline for",
                options=available_metrics,
                key="breach_heatmap_metric",
            )
            fig_heatmap = make_breach_heatmap(breach_timeline_df, breach_metric)
            st.plotly_chart(fig_heatmap, use_container_width=True, key="breach_heatmap")
        else:
            st.info("No threshold breaches detected in the selected date range.")
    else:
        st.info("No threshold data available for the selected filters.")

# ---------------------------------------------------------------------------
# Panel 2: Geographic View
# ---------------------------------------------------------------------------

st.markdown(
    '<div style="background: #8B1A1A; padding: 0.4rem 1rem; border-radius: 6px; margin: 0.8rem 0 0.5rem 0;">'
    '<h3 style="color: white; margin: 0; font-size: 1.1rem; text-align: center;">Geographic View</h3></div>',
    unsafe_allow_html=True,
)

map_metric = st.radio(
    "Map color metric",
    options=["ICUCapacityPct", "ActiveIncidents", "CapacityStressScore", "AlertStatus"],
    format_func=lambda x: {
        "ICUCapacityPct": "ICU Capacity %",
        "ActiveIncidents": "Active Incidents",
        "CapacityStressScore": "Capacity Stress Score",
        "AlertStatus": "Alert Status",
    }[x],
    horizontal=True,
    label_visibility="collapsed",
)

county_df = get_county_metrics_for_map(filtered, end_datesk)

# Add threshold breach info per county for map hover
if not county_df.empty:
    COUNTY_COL_THRESH_MAP = {
        "ICUCapacityPct": "icu_capacity_pct",
        "AvgResponseTimeHours": "avg_response_time",
        "PPEDaysOnHand": "ppe_days_on_hand",
        "StaffShortageRate": "staff_shortage_rate",
        "CapacityStressScore": "capacity_stress_score",
    }

    def _row_breaches(row):
        breached = []
        for col, tkey in COUNTY_COL_THRESH_MAP.items():
            if col not in row.index or tkey not in thresholds:
                continue
            val = row[col]
            if pd.isna(val):
                continue
            t = thresholds[tkey]
            if t["direction"] == ">=" and val >= t["value"]:
                breached.append(t["label"])
            elif t["direction"] == "<=" and val <= t["value"]:
                breached.append(t["label"])
        return ", ".join(breached) if breached else "None"

    county_df = county_df.copy()
    county_df["Breaches"] = county_df.apply(_row_breaches, axis=1)

fig_map = make_choropleth(county_df, geojson, color_col=map_metric)
st.plotly_chart(fig_map, use_container_width=True, key="choropleth_map")

# ---------------------------------------------------------------------------
# County Drill-Down (below map)
# ---------------------------------------------------------------------------

# Build county options from the filtered map data
drilldown_counties = get_counties(data, region_sks=selected_region_sks)
if selected_county_sks:
    drilldown_counties = [c for c in drilldown_counties if c["CountySK"] in selected_county_sks]

county_drill_options = {c["CountyName"]: c["CountySK"] for c in drilldown_counties}
selected_drill_county = st.selectbox(
    "Drill down into a county",
    options=[""] + list(county_drill_options.keys()),
    index=0,
    placeholder="Select a county to view details...",
    key="drill_county",
)

if selected_drill_county:
    drill_county_sk = county_drill_options[selected_drill_county]
    county_info = get_county_detail(filtered, drill_county_sk, end_datesk)

    if county_info:
        # County header with KPIs
        alert_color = {
            "Critical": "#B22222", "Alert": "#FF8C00",
            "Watch": "#FFD700", "Normal": "#2E8B57",
        }.get(county_info["alert_status"], "#888")

        st.markdown(
            f'<div style="background: #1A1A2E; padding: 0.6rem 1rem; border-radius: 6px; '
            f'border-left: 4px solid {alert_color}; margin: 0.5rem 0;">'
            f'<span style="font-size: 1.2rem; font-weight: bold;">{county_info["county_name"]}</span>'
            f' &mdash; <span style="color: #aaa;">{county_info["region_name"]}</span>'
            f' &nbsp; <span style="background: {alert_color}; padding: 2px 8px; border-radius: 4px; '
            f'font-size: 0.8rem;">{county_info["alert_status"]}</span></div>',
            unsafe_allow_html=True,
        )

        # Evaluate county thresholds
        county_breaches = evaluate_county_thresholds(county_info, thresholds)

        # County KPI cards with breach highlighting
        county_kpis = [
            ("Active Incidents", str(county_info["active_incidents"]), None),
            ("ICU Capacity", f"{county_info['icu_capacity_pct']}%", "icu_capacity_pct"),
            ("Avg Response", f"{county_info['avg_response_time']} hrs", "avg_response_time"),
            ("PPE Days", str(county_info["ppe_days_on_hand"]), "ppe_days_on_hand"),
            ("Staff Shortage", f"{county_info['staff_shortage_rate']:.0%}", "staff_shortage_rate"),
        ]

        ck_cols = st.columns(5)
        for col, (label, value, thresh_key) in zip(ck_cols, county_kpis):
            cb = county_breaches.get(thresh_key, {}) if thresh_key else {}
            is_breached = cb.get("breached", False)

            if is_breached:
                col.markdown(
                    '<div style="border: 2px solid #B22222; border-radius: 8px; padding: 2px 6px; '
                    'background: rgba(178,34,34,0.15);">',
                    unsafe_allow_html=True,
                )
            col.metric(label, value)
            if is_breached:
                col.markdown(
                    f'<div style="color: #FF6B6B; font-size: 0.75rem; margin-top: -0.5rem;">'
                    f'Threshold: {cb["direction"]} {cb["threshold"]}</div></div>',
                    unsafe_allow_html=True,
                )

        # Tabbed detail views
        tab_fac, tab_inv, tab_inc, tab_alert = st.tabs(
            ["Facilities", "Inventory", "Incidents", "Alert History"]
        )

        with tab_fac:
            fac_df = get_county_facility_capacity(filtered, drill_county_sk, start_datesk, end_datesk)
            if not fac_df.empty:
                fig_fac_bars = make_facility_capacity_bars(fac_df, end_datesk)
                st.plotly_chart(fig_fac_bars, use_container_width=True, key="fac_bars")

                # Facility drill-down
                facilities = get_facilities(data, county_sk=drill_county_sk)
                fac_options = {f["FacilityName"]: f["FacilitySK"] for f in facilities}
                selected_facility = st.selectbox(
                    "Select a facility for details",
                    options=[""] + list(fac_options.keys()),
                    index=0,
                    key="drill_facility",
                )

                if selected_facility:
                    fac_sk = fac_options[selected_facility]
                    fac_detail_df = get_facility_detail(filtered, fac_sk, start_datesk, end_datesk)
                    if not fac_detail_df.empty:
                        fc1, fc2, fc3 = st.columns(3)
                        with fc1:
                            st.plotly_chart(
                                make_facility_icu_trend(fac_detail_df, icu_threshold=thresholds["icu_capacity_pct"]["value"]),
                                use_container_width=True, key="fac_icu",
                            )
                        with fc2:
                            st.plotly_chart(
                                make_facility_staff_trend(fac_detail_df),
                                use_container_width=True, key="fac_staff",
                            )
                        with fc3:
                            st.plotly_chart(
                                make_facility_bed_occupancy(fac_detail_df),
                                use_container_width=True, key="fac_beds",
                            )
                    else:
                        st.info("No capacity data for this facility.")
            else:
                st.info("No facility data for this county.")

        with tab_inv:
            inv_detail_df = get_county_inventory(filtered, drill_county_sk, start_datesk, end_datesk)
            if not inv_detail_df.empty:
                st.plotly_chart(
                    make_county_inventory_detail(inv_detail_df),
                    use_container_width=True, key="county_inv",
                )
            else:
                st.info("No inventory data for this county.")

        with tab_inc:
            inc_detail_df = get_county_incidents(filtered, drill_county_sk, start_datesk, end_datesk)
            if not inc_detail_df.empty:
                st.dataframe(
                    inc_detail_df,
                    use_container_width=True,
                    hide_index=True,
                    height=min(len(inc_detail_df) * 35 + 40, 400),
                    column_config={
                        "Date": st.column_config.DateColumn("Date"),
                        "IncidentTypeName": "Incident Type",
                        "SeverityLevel": "Severity",
                        "DetectionTimeHours": st.column_config.NumberColumn("Detection (hrs)", format="%.1f"),
                        "EscalationTimeHours": st.column_config.NumberColumn("Escalation (hrs)", format="%.1f"),
                        "ResponseTimeHours": st.column_config.NumberColumn("Response (hrs)", format="%.1f"),
                    },
                )
            else:
                st.info("No incidents for this county.")

        with tab_alert:
            alert_tl_df = get_county_alert_timeline(filtered, drill_county_sk, start_datesk, end_datesk)
            if not alert_tl_df.empty:
                st.plotly_chart(
                    make_alert_timeline(alert_tl_df),
                    use_container_width=True, key="alert_tl",
                )
            else:
                st.info("No alert history for this county.")

# Transfer Tracking (subsection of Geographic View)
xfer_county_sk = county_drill_options.get(selected_drill_county) if selected_drill_county else None
transfer_flow_df = get_transfer_flows(filtered, start_datesk, end_datesk, county_sk=xfer_county_sk)

_xfer_count = int(transfer_flow_df["TransferCount"].sum()) if not transfer_flow_df.empty else 0
_xfer_label = (
    f"Transfer Tracking — {_xfer_count:,} transfers"
    if _xfer_count > 0
    else "Transfer Tracking — No transfers"
)

with st.expander(_xfer_label, expanded=False):
    if not transfer_flow_df.empty:
        top_n_slider = st.slider("Top N transfer pairs", min_value=5, max_value=50, value=20, key="sankey_top_n")
        fig_sankey = make_transfer_sankey(transfer_flow_df, top_n=top_n_slider)
        st.plotly_chart(fig_sankey, use_container_width=True, key="sankey")

        # Summary stats
        ts1, ts2, ts3, ts4 = st.columns(4)
        ts1.metric("Total Transfers", f"{transfer_flow_df['TransferCount'].sum():,}")
        ts2.metric("Total Quantity", f"{transfer_flow_df['TotalQty'].sum():,}")
        ts3.metric("Avg Delay", f"{transfer_flow_df['AvgDelayDays'].mean():.1f} days")
        ts4.metric("Delayed (>3 days)", f"{(transfer_flow_df['AvgDelayDays'] > 3).sum()}")
    else:
        st.info("No transfer data for the selected filters.")

# ---------------------------------------------------------------------------
# Panel 3: Logistics & Operations
# ---------------------------------------------------------------------------

st.markdown(
    '<div style="background: #8B1A1A; padding: 0.4rem 1rem; border-radius: 6px; margin: 0.8rem 0 0.5rem 0;">'
    '<h3 style="color: white; margin: 0; font-size: 1.1rem; text-align: center;">Logistics & Operations</h3></div>',
    unsafe_allow_html=True,
)

log_col1, log_col2 = st.columns(2)

with log_col1:
    inv_df = get_inventory_series(filtered, start_datesk, end_datesk)
    fig_ppe = make_ppe_trend(inv_df, ppe_threshold=thresholds["ppe_days_on_hand"]["value"])
    st.plotly_chart(fig_ppe, use_container_width=True, key="ppe_trend")

with log_col2:
    staff_df = get_staff_by_region(filtered, start_datesk, end_datesk)
    fig_staff = make_staff_availability(staff_df, shortage_threshold=thresholds["staff_shortage_rate"]["value"])
    st.plotly_chart(fig_staff, use_container_width=True, key="staff_avail")

log_col3, log_col4 = st.columns(2)

with log_col3:
    xfer_df = get_transfer_summary(filtered, start_datesk, end_datesk)
    fig_xfer = make_transfer_volume(xfer_df)
    st.plotly_chart(fig_xfer, use_container_width=True, key="transfer_vol")

with log_col4:
    supply_df = get_supply_delay_series(filtered, start_datesk, end_datesk)
    fig_supply = make_supply_delay(supply_df, delay_threshold=thresholds["supply_delay_days"]["value"])
    st.plotly_chart(fig_supply, use_container_width=True, key="supply_delay")

# ---------------------------------------------------------------------------
# Panel 4: Emerging Threats
# ---------------------------------------------------------------------------

st.markdown(
    '<div style="background: #8B1A1A; padding: 0.4rem 1rem; border-radius: 6px; margin: 0.8rem 0 0.5rem 0;">'
    '<h3 style="color: white; margin: 0; font-size: 1.1rem; text-align: center;">Emerging Threats</h3></div>',
    unsafe_allow_html=True,
)

threat_col1, threat_col2 = st.columns([3, 2])

with threat_col1:
    # Trend line with metric selector
    trend_metric = st.radio(
        "Trend metric",
        options=[
            ("active_incidents", "Active Incidents"),
            ("avg_response_time", "Avg Response Time (hrs)"),
            ("avg_icu_capacity", "Avg ICU Capacity %"),
            ("avg_ppe_days", "Avg PPE Days on Hand"),
            ("avg_staff_shortage", "Staff Shortage Rate"),
            ("critical_counties", "Counties in Critical"),
        ],
        format_func=lambda x: x[1],
        horizontal=True,
        label_visibility="collapsed",
    )

    # Map trend metric columns to threshold keys
    TREND_THRESHOLD_MAP = {
        "avg_icu_capacity": "icu_capacity_pct",
        "avg_response_time": "avg_response_time",
        "avg_ppe_days": "ppe_days_on_hand",
        "avg_staff_shortage": "staff_shortage_rate",
        "avg_supply_delay": "supply_delay_days",
    }
    trend_thresh_key = TREND_THRESHOLD_MAP.get(trend_metric[0])
    trend_thresh_val = thresholds[trend_thresh_key]["value"] if trend_thresh_key else None

    trend_df = get_trend_series(filtered, end_datesk, lookback_days=30)
    if not trend_df.empty:
        fig_trend = make_trend_line(trend_df, trend_metric[0], trend_metric[1], threshold_value=trend_thresh_val)
        st.plotly_chart(fig_trend, use_container_width=True, key="trend_line")
    else:
        st.info("No trend data available for the selected filters.")

with threat_col2:
    # Alert status donut
    alert_counts = snapshot.get("alert_status_counts", {})
    fig_donut = make_alert_donut(alert_counts)
    st.plotly_chart(fig_donut, use_container_width=True, key="alert_donut")

    # Counties in Alert/Critical table
    alert_critical = snapshot.get("critical_counties", []) + snapshot.get("alert_counties", [])
    if alert_critical:
        st.markdown("**Counties in Alert/Critical**")
        alert_table = pd.DataFrame(alert_critical)
        if not alert_table.empty:
            st.dataframe(
                alert_table,
                use_container_width=True,
                hide_index=True,
                height=min(len(alert_table) * 35 + 40, 300),
            )
    else:
        st.success("No counties in Alert or Critical status.")

# Incident Timeline (subsection of Emerging Threats)
with st.expander("Incident Timeline", expanded=False):
    itl_col1, itl_col2, itl_col3 = st.columns(3)
    with itl_col1:
        itl_type_options = {"All Types": None}
        itl_type_options.update({t["IncidentTypeName"]: t["IncidentTypeSK"] for t in incident_types})
        itl_type = st.selectbox("Incident Type", options=list(itl_type_options.keys()), key="itl_type")
    with itl_col2:
        itl_sev_options = ["All Severities", "Critical", "High", "Medium", "Low"]
        itl_sev = st.selectbox("Severity", options=itl_sev_options, key="itl_sev")
    with itl_col3:
        itl_county_options = {"All Counties": None}
        itl_county_options.update(county_drill_options)
        itl_county = st.selectbox("County", options=list(itl_county_options.keys()), key="itl_county")

    timeline_df = get_incident_timeline(
        filtered,
        start_datesk,
        end_datesk,
        county_sk=itl_county_options[itl_county],
        incident_type_sk=itl_type_options[itl_type],
        severity=itl_sev if itl_sev != "All Severities" else None,
    )

    if not timeline_df.empty:
        fig_sev = make_incident_severity_chart(timeline_df)
        st.plotly_chart(fig_sev, use_container_width=True, key="sev_chart")

        st.dataframe(
            timeline_df,
            use_container_width=True,
            hide_index=True,
            height=min(len(timeline_df) * 35 + 40, 500),
            column_config={
                "Date": st.column_config.DateColumn("Date"),
                "CountyName": "County",
                "IncidentTypeName": "Type",
                "SeverityLevel": "Severity",
                "DetectionTimeHours": st.column_config.NumberColumn("Detection (hrs)", format="%.1f"),
                "EscalationTimeHours": st.column_config.NumberColumn("Escalation (hrs)", format="%.1f"),
                "ResponseTimeHours": st.column_config.NumberColumn("Response (hrs)", format="%.1f"),
            },
        )
        st.caption(f"Showing {len(timeline_df):,} incidents")
    else:
        st.info("No incidents match the selected filters.")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()
st.caption(
    f"CROSS Dashboard v1.2 | Data: Kansas mock dataset | "
    f"Showing: {start_date} to {end_date} | "
    f"Prepared by Francisco Galvez (Oracle Health AI CoE)"
)
