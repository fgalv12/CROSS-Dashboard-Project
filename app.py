"""
CROSS Dashboard — Crisis Response & Operational Statewide Status
Streamlit entry point with 4 panels + AI Situational Awareness Agent.
"""

import streamlit as st

st.set_page_config(
    page_title="CROSS Dashboard",
    page_icon="\u271a",
    layout="wide",
    initial_sidebar_state="expanded",
)

import pandas as pd

from utils.data_loader import (
    filter_data,
    get_counties,
    get_date_range,
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
    get_county_metrics_for_map,
    get_inventory_series,
    get_kpi_cards,
    get_staff_by_region,
    get_supply_delay_series,
    get_transfer_summary,
    get_trend_series,
    resolve_datesk,
)
from utils.charts import (
    make_alert_donut,
    make_choropleth,
    make_ppe_trend,
    make_staff_availability,
    make_supply_delay,
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

    st.divider()
    st.caption(f"Data: {min_date.date()} to {max_date.date()}")

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

# ---------------------------------------------------------------------------
# Panel 1: Executive Snapshot
# ---------------------------------------------------------------------------

st.markdown(
    '<div style="background: #8B1A1A; padding: 0.4rem 1rem; border-radius: 6px; margin: 0.8rem 0 0.5rem 0;">'
    '<h3 style="color: white; margin: 0; font-size: 1.1rem;">Executive Snapshot</h3></div>',
    unsafe_allow_html=True,
)

# Compute KPI snapshots
snapshot = compute_snapshot(filtered, end_datesk)

# Get prior day snapshot for deltas
prior_sk = _prior_datesk(filtered, end_datesk, 1)
prior_snapshot = compute_snapshot(filtered, prior_sk) if prior_sk else None

kpi_cards = get_kpi_cards(snapshot, prior_snapshot)

kpi_cols = st.columns(len(kpi_cards))
for col, card in zip(kpi_cols, kpi_cards):
    col.metric(
        label=card["label"],
        value=card["value"],
        delta=card["delta"],
        delta_color=card["delta_color"],
    )

# ---------------------------------------------------------------------------
# Panel 2: Geographic View
# ---------------------------------------------------------------------------

st.markdown(
    '<div style="background: #8B1A1A; padding: 0.4rem 1rem; border-radius: 6px; margin: 0.8rem 0 0.5rem 0;">'
    '<h3 style="color: white; margin: 0; font-size: 1.1rem;">Geographic View</h3></div>',
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
fig_map = make_choropleth(county_df, geojson, color_col=map_metric)
st.plotly_chart(fig_map, use_container_width=True, key="choropleth_map")

# ---------------------------------------------------------------------------
# Panel 3: Logistics & Operations
# ---------------------------------------------------------------------------

st.markdown(
    '<div style="background: #8B1A1A; padding: 0.4rem 1rem; border-radius: 6px; margin: 0.8rem 0 0.5rem 0;">'
    '<h3 style="color: white; margin: 0; font-size: 1.1rem;">Logistics & Operations</h3></div>',
    unsafe_allow_html=True,
)

log_col1, log_col2 = st.columns(2)

with log_col1:
    inv_df = get_inventory_series(filtered, start_datesk, end_datesk)
    fig_ppe = make_ppe_trend(inv_df)
    st.plotly_chart(fig_ppe, use_container_width=True, key="ppe_trend")

with log_col2:
    staff_df = get_staff_by_region(filtered, start_datesk, end_datesk)
    fig_staff = make_staff_availability(staff_df)
    st.plotly_chart(fig_staff, use_container_width=True, key="staff_avail")

log_col3, log_col4 = st.columns(2)

with log_col3:
    xfer_df = get_transfer_summary(filtered, start_datesk, end_datesk)
    fig_xfer = make_transfer_volume(xfer_df)
    st.plotly_chart(fig_xfer, use_container_width=True, key="transfer_vol")

with log_col4:
    supply_df = get_supply_delay_series(filtered, start_datesk, end_datesk)
    fig_supply = make_supply_delay(supply_df)
    st.plotly_chart(fig_supply, use_container_width=True, key="supply_delay")

# ---------------------------------------------------------------------------
# Panel 4: Emerging Threats
# ---------------------------------------------------------------------------

st.markdown(
    '<div style="background: #8B1A1A; padding: 0.4rem 1rem; border-radius: 6px; margin: 0.8rem 0 0.5rem 0;">'
    '<h3 style="color: white; margin: 0; font-size: 1.1rem;">Emerging Threats</h3></div>',
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

    trend_df = get_trend_series(filtered, end_datesk, lookback_days=30)
    if not trend_df.empty:
        fig_trend = make_trend_line(trend_df, trend_metric[0], trend_metric[1])
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

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()
st.caption(
    f"CROSS Dashboard v1.0 | Data: Kansas mock dataset | "
    f"Showing: {start_date} to {end_date} | "
    f"Prepared by Francisco Galvez (Oracle Health HDI)"
)
