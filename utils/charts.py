"""
Plotly chart builders for the CROSS Dashboard.
All charts use a consistent color scheme matching the dashboard mockup.
"""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Consistent color scheme
ALERT_COLORS = {
    "Critical": "#B22222",
    "Alert": "#FF8C00",
    "Watch": "#FFD700",
    "Normal": "#2E8B57",
}

CHART_TEMPLATE = "plotly_dark"
CHART_HEIGHT = 350


def _base_layout(fig: go.Figure, title: str = "") -> go.Figure:
    """Apply consistent layout to all charts."""
    fig.update_layout(
        template=CHART_TEMPLATE,
        title=dict(text=title, font=dict(size=14)),
        height=CHART_HEIGHT,
        margin=dict(l=40, r=20, t=40, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#FAFAFA", size=11),
    )
    return fig


def make_choropleth(
    county_df: pd.DataFrame,
    geojson: dict,
    color_col: str = "ICUCapacityPct",
) -> go.Figure:
    """
    Kansas county choropleth map.
    color_col options: ICUCapacityPct, ActiveIncidents, CapacityStressScore, AlertStatus
    """
    if county_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data available", showarrow=False, font=dict(size=16))
        return _base_layout(fig, "Geographic View")

    if color_col == "AlertStatus":
        # Map alert status to numeric for coloring
        status_map = {"Normal": 0, "Watch": 1, "Alert": 2, "Critical": 3}
        county_df = county_df.copy()
        county_df["AlertNumeric"] = county_df["AlertStatus"].map(status_map).fillna(0)

        fig = px.choropleth(
            county_df,
            geojson=geojson,
            locations="CountyFIPS5",
            featureidkey="id",
            color="AlertNumeric",
            color_continuous_scale=[
                [0, ALERT_COLORS["Normal"]],
                [0.33, ALERT_COLORS["Watch"]],
                [0.67, ALERT_COLORS["Alert"]],
                [1.0, ALERT_COLORS["Critical"]],
            ],
            hover_name="CountyName",
            hover_data={
                "AlertStatus": True,
                "AlertNumeric": False,
                "CountyFIPS5": False,
                "ICUCapacityPct": ":.1f",
                "ActiveIncidents": True,
            },
        )
        fig.update_coloraxes(
            colorbar_title="Alert<br>Status",
            colorbar_tickvals=[0, 1, 2, 3],
            colorbar_ticktext=["Normal", "Watch", "Alert", "Critical"],
        )
    else:
        # Determine color scale based on metric
        if color_col == "ICUCapacityPct":
            color_scale = "RdYlGn"
            range_color = [0, 100]
            title_suffix = "ICU Capacity %"
        elif color_col == "ActiveIncidents":
            color_scale = "Reds"
            range_color = [0, county_df["ActiveIncidents"].quantile(0.95)] if len(county_df) > 0 else [0, 10]
            title_suffix = "Active Incidents"
        elif color_col == "CapacityStressScore":
            color_scale = "RdYlGn_r"
            range_color = [0, 1]
            title_suffix = "Stress Score"
        else:
            color_scale = "Reds"
            range_color = None
            title_suffix = color_col

        hover_data_dict = {"CountyFIPS5": False}
        if "RegionName" in county_df.columns:
            hover_data_dict["RegionName"] = True
        if "ICUCapacityPct" in county_df.columns:
            hover_data_dict["ICUCapacityPct"] = ":.1f"
        if "ActiveIncidents" in county_df.columns:
            hover_data_dict["ActiveIncidents"] = True
        if "AlertStatus" in county_df.columns:
            hover_data_dict["AlertStatus"] = True

        fig = px.choropleth(
            county_df,
            geojson=geojson,
            locations="CountyFIPS5",
            featureidkey="id",
            color=color_col,
            color_continuous_scale=color_scale,
            range_color=range_color,
            hover_name="CountyName",
            hover_data=hover_data_dict,
        )

    fig.update_geos(
        fitbounds="locations",
        visible=False,
        bgcolor="rgba(0,0,0,0)",
    )
    fig.update_layout(
        template=CHART_TEMPLATE,
        height=450,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#FAFAFA"),
        geo=dict(bgcolor="rgba(0,0,0,0)"),
    )
    return fig


def make_ppe_trend(inventory_df: pd.DataFrame) -> go.Figure:
    """Line chart: avg EstimatedDaysOnHand by item over time."""
    if inventory_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No inventory data", showarrow=False)
        return _base_layout(fig, "PPE Inventory Trend")

    fig = px.line(
        inventory_df,
        x="Date",
        y="AvgDaysOnHand",
        color="ItemName",
        markers=False,
    )
    fig.update_layout(
        xaxis_title="",
        yaxis_title="Avg Days on Hand",
        legend_title="Supply Item",
    )
    return _base_layout(fig, "PPE Inventory Trend")


def make_staff_availability(staff_df: pd.DataFrame) -> go.Figure:
    """Line chart: staff shortage rate by region over time."""
    if staff_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No staffing data", showarrow=False)
        return _base_layout(fig, "Staff Availability by Region")

    fig = px.line(
        staff_df,
        x="Date",
        y="StaffShortageRate",
        color="RegionName",
        markers=False,
    )
    fig.update_layout(
        xaxis_title="",
        yaxis_title="Staff Shortage Rate",
        legend_title="Region",
    )
    fig.update_yaxes(tickformat=".1%")
    return _base_layout(fig, "Staff Availability by Region")


def make_transfer_volume(transfer_df: pd.DataFrame) -> go.Figure:
    """Bar chart: daily transfer quantity."""
    if transfer_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No transfer data", showarrow=False)
        return _base_layout(fig, "Equipment Transfers Between Counties")

    fig = px.bar(
        transfer_df,
        x="Date",
        y="TotalQuantity",
        color_discrete_sequence=["#B22222"],
    )
    fig.update_layout(
        xaxis_title="",
        yaxis_title="Transfer Quantity",
    )
    return _base_layout(fig, "Equipment Transfers Between Counties")


def make_supply_delay(supply_df: pd.DataFrame) -> go.Figure:
    """Line chart: average supply delay days over time."""
    if supply_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No supply delay data", showarrow=False)
        return _base_layout(fig, "Average Supply Delay")

    fig = px.line(
        supply_df,
        x="Date",
        y="AvgSupplyDelayDays",
        color_discrete_sequence=["#FF8C00"],
        markers=True,
    )
    fig.update_layout(
        xaxis_title="",
        yaxis_title="Avg Delay (days)",
    )
    return _base_layout(fig, "Average Supply Delay")


def make_trend_line(trend_df: pd.DataFrame, metric_col: str, label: str) -> go.Figure:
    """
    30-day trend line with mean +/- 1.5 std dev bands and anomaly markers.
    """
    if trend_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No trend data", showarrow=False)
        return _base_layout(fig, f"{label} — 30-Day Trend")

    series = trend_df[metric_col]
    mean_val = series.mean()
    std_val = series.std()
    upper = mean_val + 1.5 * std_val
    lower = mean_val - 1.5 * std_val

    fig = go.Figure()

    # Confidence band
    fig.add_trace(go.Scatter(
        x=list(trend_df["Date"]) + list(trend_df["Date"][::-1]),
        y=[upper] * len(trend_df) + [lower] * len(trend_df),
        fill="toself",
        fillcolor="rgba(178, 34, 34, 0.1)",
        line=dict(color="rgba(178, 34, 34, 0.3)", dash="dash"),
        name="1.5\u03c3 Band",
        hoverinfo="skip",
    ))

    # Mean line
    fig.add_hline(
        y=mean_val,
        line_dash="dot",
        line_color="rgba(255,255,255,0.4)",
        annotation_text=f"Mean: {mean_val:.1f}",
        annotation_font_color="rgba(255,255,255,0.6)",
    )

    # Main trend line
    fig.add_trace(go.Scatter(
        x=trend_df["Date"],
        y=series,
        mode="lines+markers",
        name=label,
        line=dict(color="#4FC3F7", width=2),
        marker=dict(size=4),
    ))

    # Anomaly markers
    anomalies = trend_df[abs(series - mean_val) > 1.5 * std_val]
    if not anomalies.empty:
        fig.add_trace(go.Scatter(
            x=anomalies["Date"],
            y=anomalies[metric_col],
            mode="markers",
            name="Anomaly",
            marker=dict(color="#FF4444", size=10, symbol="diamond"),
        ))

    fig.update_layout(
        xaxis_title="",
        yaxis_title=label,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    fig = _base_layout(fig, f"{label} — 30-Day Trend")
    fig.update_layout(
        margin=dict(t=90),
        title=dict(y=0.98, yanchor="top"),
    )
    return fig


def make_alert_donut(alert_counts: dict) -> go.Figure:
    """Donut chart showing alert status distribution."""
    if not alert_counts:
        fig = go.Figure()
        fig.add_annotation(text="No alert data", showarrow=False)
        return _base_layout(fig, "Alert Status Distribution")

    statuses = list(alert_counts.keys())
    counts = list(alert_counts.values())
    colors = [ALERT_COLORS.get(s, "#888888") for s in statuses]

    fig = go.Figure(data=[go.Pie(
        labels=statuses,
        values=counts,
        hole=0.5,
        marker_colors=colors,
        textinfo="label+value",
        textfont=dict(size=12),
    )])

    fig.update_layout(
        showlegend=False,
    )
    return _base_layout(fig, "Alert Status Distribution")


# ---------------------------------------------------------------------------
# Milestone 3: Drill-Down Chart Functions
# ---------------------------------------------------------------------------

SEVERITY_COLORS = {
    "Critical": "#B22222",
    "High": "#FF8C00",
    "Medium": "#FFD700",
    "Low": "#2E8B57",
}


def make_facility_capacity_bars(facility_df: pd.DataFrame, datesk: int) -> go.Figure:
    """Horizontal bar chart of ICU occupancy % per facility for a single date."""
    if facility_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No facility data", showarrow=False)
        return _base_layout(fig, "Facility ICU Occupancy")

    day = facility_df[facility_df["DateSK"] == datesk].copy()
    if day.empty:
        day = facility_df.drop_duplicates("FacilitySK", keep="last").copy()

    day = day.sort_values("ICUOccPct", ascending=True)

    colors = []
    for pct in day["ICUOccPct"]:
        if pct >= 95:
            colors.append("#B22222")
        elif pct >= 85:
            colors.append("#FF8C00")
        elif pct >= 70:
            colors.append("#FFD700")
        else:
            colors.append("#2E8B57")

    fig = go.Figure(go.Bar(
        y=day["FacilityName"],
        x=day["ICUOccPct"],
        orientation="h",
        marker_color=colors,
        text=day["ICUOccPct"].apply(lambda x: f"{x:.0f}%"),
        textposition="outside",
    ))

    fig.update_layout(
        xaxis_title="ICU Occupancy %",
        yaxis_title="",
        xaxis=dict(range=[0, 110]),
    )
    height = max(CHART_HEIGHT, len(day) * 35 + 80)
    fig = _base_layout(fig, "Facility ICU Occupancy")
    fig.update_layout(height=height)
    return fig


def make_facility_icu_trend(facility_df: pd.DataFrame) -> go.Figure:
    """Line chart of ICU occupancy % over time for a single facility."""
    if facility_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data", showarrow=False)
        return _base_layout(fig, "ICU Occupancy Trend")

    fig = px.line(
        facility_df,
        x="Date",
        y="ICUOccPct",
        markers=True,
        color_discrete_sequence=["#4FC3F7"],
    )
    fig.update_layout(xaxis_title="", yaxis_title="ICU Occupancy %")
    fig.add_hline(y=85, line_dash="dash", line_color="#FF8C00",
                  annotation_text="85% threshold")
    return _base_layout(fig, "ICU Occupancy Trend")


def make_facility_staff_trend(facility_df: pd.DataFrame) -> go.Figure:
    """Line chart of staff fill rate over time for a single facility."""
    if facility_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data", showarrow=False)
        return _base_layout(fig, "Staff Fill Rate")

    fig = px.line(
        facility_df,
        x="Date",
        y="StaffFillRate",
        markers=True,
        color_discrete_sequence=["#81C784"],
    )
    fig.update_layout(xaxis_title="", yaxis_title="Staff Fill Rate")
    fig.update_yaxes(tickformat=".0%")
    return _base_layout(fig, "Staff Fill Rate")


def make_facility_bed_occupancy(facility_df: pd.DataFrame) -> go.Figure:
    """Stacked area chart: occupied vs total staffed beds over time."""
    if facility_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data", showarrow=False)
        return _base_layout(fig, "Bed Occupancy")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=facility_df["Date"],
        y=facility_df["StaffedBedsTotal"],
        fill="tozeroy",
        name="Total Beds",
        line=dict(color="rgba(79, 195, 247, 0.3)"),
        fillcolor="rgba(79, 195, 247, 0.1)",
    ))
    fig.add_trace(go.Scatter(
        x=facility_df["Date"],
        y=facility_df["StaffedBedsOccupied"],
        fill="tozeroy",
        name="Occupied",
        line=dict(color="#FF8C00"),
        fillcolor="rgba(255, 140, 0, 0.3)",
    ))
    fig.update_layout(
        xaxis_title="", yaxis_title="Beds",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return _base_layout(fig, "Bed Occupancy")


def make_county_inventory_detail(inventory_df: pd.DataFrame) -> go.Figure:
    """Inventory levels by item over time for one county."""
    if inventory_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No inventory data", showarrow=False)
        return _base_layout(fig, "County Inventory Levels")

    fig = px.line(
        inventory_df,
        x="Date",
        y="EstimatedDaysOnHand",
        color="ItemName",
        markers=False,
    )
    fig.update_layout(
        xaxis_title="", yaxis_title="Est. Days on Hand",
        legend_title="Item",
    )
    return _base_layout(fig, "County Inventory Levels")


def make_alert_timeline(alert_df: pd.DataFrame) -> go.Figure:
    """Color-coded timeline of daily alert status for a county."""
    if alert_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No alert data", showarrow=False)
        return _base_layout(fig, "Alert Status Timeline")

    status_map = {"Normal": 0, "Watch": 1, "Alert": 2, "Critical": 3}
    df = alert_df.copy()
    df["StatusNum"] = df["AlertStatus"].map(status_map).fillna(0)

    fig = go.Figure(go.Bar(
        x=df["Date"],
        y=[1] * len(df),
        marker_color=[ALERT_COLORS.get(s, "#888") for s in df["AlertStatus"]],
        text=df["AlertStatus"],
        textposition="inside",
        hovertemplate="Date: %{x}<br>Status: %{text}<extra></extra>",
    ))

    fig.update_layout(
        xaxis_title="",
        yaxis=dict(visible=False),
        bargap=0,
    )
    fig = _base_layout(fig, "Alert Status Timeline")
    fig.update_layout(height=150)
    return fig


def make_transfer_sankey(transfer_df: pd.DataFrame, top_n: int = 20) -> go.Figure:
    """Sankey diagram of inter-county resource flows (top N pairs by volume)."""
    if transfer_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No transfer data", showarrow=False)
        return _base_layout(fig, "Resource Transfer Flows")

    df = transfer_df.head(top_n)

    # Build unique node list: sources on left, destinations on right
    sources = df["FromCountyName"].unique().tolist()
    destinations = df["ToCountyName"].unique().tolist()
    # Nodes that appear in both get separate source/dest entries
    all_nodes = [f"{s} (out)" for s in sources] + [f"{d} (in)" for d in destinations]
    source_idx = {s: i for i, s in enumerate(sources)}
    dest_idx = {d: i + len(sources) for i, d in enumerate(destinations)}

    link_source = [source_idx[r["FromCountyName"]] for _, r in df.iterrows()]
    link_target = [dest_idx[r["ToCountyName"]] for _, r in df.iterrows()]
    link_value = df["TotalQty"].tolist()

    # Color links by delay
    link_colors = []
    for _, r in df.iterrows():
        delay = r["AvgDelayDays"]
        if delay > 3:
            link_colors.append("rgba(178, 34, 34, 0.5)")
        elif delay > 1.5:
            link_colors.append("rgba(255, 140, 0, 0.5)")
        else:
            link_colors.append("rgba(46, 139, 87, 0.5)")

    fig = go.Figure(go.Sankey(
        node=dict(
            pad=15,
            thickness=20,
            label=all_nodes,
            color="rgba(79, 195, 247, 0.8)",
        ),
        link=dict(
            source=link_source,
            target=link_target,
            value=link_value,
            color=link_colors,
        ),
    ))

    fig = _base_layout(fig, "Resource Transfer Flows")
    fig.update_layout(height=500)
    return fig


def make_incident_severity_chart(incident_df: pd.DataFrame) -> go.Figure:
    """Stacked bar chart of incidents by severity level over time."""
    if incident_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No incident data", showarrow=False)
        return _base_layout(fig, "Incidents by Severity")

    daily = incident_df.groupby(["Date", "SeverityLevel"]).size().reset_index(name="Count")

    fig = px.bar(
        daily,
        x="Date",
        y="Count",
        color="SeverityLevel",
        color_discrete_map=SEVERITY_COLORS,
        barmode="stack",
    )
    fig.update_layout(
        xaxis_title="",
        yaxis_title="Incident Count",
        legend_title="Severity",
    )
    return _base_layout(fig, "Incidents by Severity")
