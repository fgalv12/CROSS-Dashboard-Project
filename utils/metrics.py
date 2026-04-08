"""
Metric computation helpers for the CROSS Dashboard.
Re-exports agent functions and adds dashboard-specific helpers.
"""

import json
import sys
from pathlib import Path

import pandas as pd

# Add project root to path so we can import the agent module
sys.path.insert(0, str(Path(__file__).parent.parent))

from cross_situational_awareness_agent import (
    SYSTEM_PROMPT,
    _county_name,
    _datesk_to_date,
    _prior_datesk,
    _region_name,
    compute_changes,
    compute_snapshot,
    compute_trends,
)

# Re-export for convenience
__all__ = [
    "SYSTEM_PROMPT",
    "compute_snapshot",
    "compute_changes",
    "compute_trends",
    "_datesk_to_date",
    "_prior_datesk",
    "_region_name",
    "_county_name",
    "resolve_datesk",
    "get_kpi_cards",
    "get_county_metrics_for_map",
    "get_trend_series",
    "get_inventory_series",
    "get_staff_by_region",
    "get_transfer_summary",
    "build_briefing_prompt",
]


def resolve_datesk(data: dict, target_date: str | None = None) -> int:
    """
    Return DateSK for target_date, or the latest available date.
    Unlike agent's _resolve_date, raises ValueError instead of sys.exit().
    """
    dates_df = data["dates"]
    if target_date:
        target = pd.Timestamp(target_date)
        match = dates_df[dates_df["Date"] == target]
        if match.empty:
            available = dates_df["Date"].sort_values()
            raise ValueError(
                f"Date {target_date} not found. "
                f"Available: {available.iloc[0].date()} to {available.iloc[-1].date()}"
            )
        return int(match.iloc[0]["DateSK"])
    return int(dates_df["DateSK"].max())


def get_kpi_cards(snapshot: dict, prior_snapshot: dict | None = None) -> list[dict]:
    """
    Return list of dicts for st.metric() display.
    Each dict has: label, value, delta, delta_color ("normal" or "inverse").
    """
    metrics = [
        ("Total Active Incidents", "total_active_incidents", "{:,}", "inverse"),
        ("ICU Capacity %", "avg_icu_capacity_pct", "{:.1f}%", "normal"),
        ("Avg Response Time", "avg_response_time_hours", "{:.1f} hrs", "inverse"),
        ("Resource Deploy Lag", "avg_deployment_lag_hours", "{:.1f} hrs", "inverse"),
        ("Counties in Alert/Critical", None, "{}", "inverse"),
    ]

    cards = []
    for label, key, fmt, delta_color in metrics:
        if key is None:
            # Special: counties in alert + critical
            alert_counts = snapshot.get("alert_status_counts", {})
            value = alert_counts.get("Alert", 0) + alert_counts.get("Critical", 0)
            if prior_snapshot:
                prior_counts = prior_snapshot.get("alert_status_counts", {})
                prior_value = prior_counts.get("Alert", 0) + prior_counts.get("Critical", 0)
                delta = value - prior_value
            else:
                delta = None
            cards.append({
                "label": label,
                "value": str(value),
                "delta": f"{delta:+d}" if delta is not None else None,
                "delta_color": delta_color,
            })
        else:
            value = snapshot.get(key, 0)
            if prior_snapshot:
                prior_value = prior_snapshot.get(key, 0)
                delta = round(value - prior_value, 2)
                # Format delta
                if "pct" in key.lower() or "capacity" in key.lower():
                    delta_str = f"{delta:+.1f}%"
                elif "time" in key or "lag" in key or "hours" in key:
                    delta_str = f"{delta:+.1f} hrs"
                else:
                    delta_str = f"{delta:+,.0f}"
            else:
                delta_str = None
            cards.append({
                "label": label,
                "value": fmt.format(value),
                "delta": delta_str,
                "delta_color": delta_color,
            })

    return cards


def get_county_metrics_for_map(data: dict, datesk: int) -> pd.DataFrame:
    """
    Return DataFrame with county-level metrics for the choropleth map.
    Columns: CountyFIPS5, CountyName, RegionName, AlertStatus, ICUCapacityPct,
             ActiveIncidents, CapacityStressScore
    """
    dcm = data["daily_county"]
    day = dcm[dcm["DateSK"] == datesk].copy()

    if day.empty:
        return pd.DataFrame()

    # Join county names and FIPS codes
    counties = data["counties"][["CountySK", "CountyName", "CountyFIPS5"]].copy()
    counties["CountyFIPS5"] = counties["CountyFIPS5"].astype(str).str.zfill(5)

    # Join region names
    regions = data["regions"][["RegionSK", "RegionName"]]

    merged = day.merge(counties, on="CountySK", how="left")
    merged = merged.merge(regions, on="RegionSK", how="left")

    cols = ["CountyFIPS5", "CountyName", "RegionName", "AlertStatus",
            "ICUCapacityPct", "ActiveIncidents", "CapacityStressScore",
            "AvgResponseTimeHours", "StaffShortageRate", "PPEDaysOnHand"]
    available = [c for c in cols if c in merged.columns]
    return merged[available]


def get_trend_series(data: dict, end_datesk: int, lookback_days: int = 30) -> pd.DataFrame:
    """
    Return daily aggregated DataFrame for trend charts over lookback_days.
    Columns: DateSK, Date, active_incidents, avg_response_time, avg_icu_capacity,
             avg_ppe_days, avg_staff_shortage, critical_counties
    """
    from datetime import timedelta

    dcm = data["daily_county"]
    end_date = _datesk_to_date(end_datesk)
    start_date = end_date - timedelta(days=lookback_days)
    start_sk = int(start_date.strftime("%Y%m%d"))

    window = dcm[(dcm["DateSK"] >= start_sk) & (dcm["DateSK"] <= end_datesk)]
    if window.empty:
        return pd.DataFrame()

    daily = window.groupby("DateSK").agg(
        active_incidents=("ActiveIncidents", "sum"),
        avg_response_time=("AvgResponseTimeHours", "mean"),
        avg_icu_capacity=("ICUCapacityPct", "mean"),
        avg_ppe_days=("PPEDaysOnHand", "mean"),
        avg_staff_shortage=("StaffShortageRate", "mean"),
        critical_counties=("AlertStatus", lambda x: (x == "Critical").sum()),
    ).reset_index()

    # Add readable date
    daily["Date"] = daily["DateSK"].apply(lambda sk: _datesk_to_date(sk).date())
    return daily


def get_inventory_series(data: dict, start_datesk: int, end_datesk: int) -> pd.DataFrame:
    """
    Return daily inventory by item for PPE trend chart.
    Columns: Date, ItemName, AvgDaysOnHand
    """
    inv = data["inventory"]
    window = inv[(inv["DateSK"] >= start_datesk) & (inv["DateSK"] <= end_datesk)]
    if window.empty:
        return pd.DataFrame()

    items = data["items"][["ItemSK", "ItemName"]]
    merged = window.merge(items, on="ItemSK", how="left")

    daily = merged.groupby(["DateSK", "ItemName"]).agg(
        AvgDaysOnHand=("EstimatedDaysOnHand", "mean"),
    ).reset_index()

    daily["Date"] = daily["DateSK"].apply(lambda sk: _datesk_to_date(sk).date())
    return daily


def get_staff_by_region(data: dict, start_datesk: int, end_datesk: int) -> pd.DataFrame:
    """
    Return daily staff shortage rate by region.
    Columns: Date, RegionName, StaffShortageRate
    """
    dcm = data["daily_county"]
    window = dcm[(dcm["DateSK"] >= start_datesk) & (dcm["DateSK"] <= end_datesk)]
    if window.empty:
        return pd.DataFrame()

    regions = data["regions"][["RegionSK", "RegionName"]]

    # daily_county already has RegionSK — join directly to get region names
    merged = window.merge(regions, on="RegionSK", how="left")

    daily = merged.groupby(["DateSK", "RegionName"]).agg(
        StaffShortageRate=("StaffShortageRate", "mean"),
    ).reset_index()

    daily["Date"] = daily["DateSK"].apply(lambda sk: _datesk_to_date(sk).date())
    return daily


def get_transfer_summary(data: dict, start_datesk: int, end_datesk: int) -> pd.DataFrame:
    """
    Return daily transfer volume.
    Columns: Date, TotalTransfers, TotalQuantity, AvgDelayDays
    """
    xfer = data["transfers"]
    window = xfer[(xfer["DateSK"] >= start_datesk) & (xfer["DateSK"] <= end_datesk)]
    if window.empty:
        return pd.DataFrame()

    daily = window.groupby("DateSK").agg(
        TotalTransfers=("TransferQty", "count"),
        TotalQuantity=("TransferQty", "sum"),
        AvgDelayDays=("ShipmentDelayDays", "mean"),
    ).reset_index()

    daily["Date"] = daily["DateSK"].apply(lambda sk: _datesk_to_date(sk).date())
    return daily


def get_supply_delay_series(data: dict, start_datesk: int, end_datesk: int) -> pd.DataFrame:
    """
    Return daily average supply delay.
    Columns: Date, AvgSupplyDelayDays
    """
    dcm = data["daily_county"]
    window = dcm[(dcm["DateSK"] >= start_datesk) & (dcm["DateSK"] <= end_datesk)]
    if window.empty:
        return pd.DataFrame()

    daily = window.groupby("DateSK").agg(
        AvgSupplyDelayDays=("AvgSupplyDelayDays", "mean"),
    ).reset_index()

    daily["Date"] = daily["DateSK"].apply(lambda sk: _datesk_to_date(sk).date())
    return daily


def build_briefing_prompt(
    date_label: str,
    lookback: int,
    snapshot: dict,
    prior_snapshot: dict | None,
    changes: dict | None,
    trends: dict,
    active_filters: dict | None = None,
) -> str:
    """
    Build the user message for the Claude briefing API call.
    Mirrors the agent's prompt construction (lines 423-443) plus filter context.
    """
    content = f"**Briefing Date:** {date_label}\n"
    content += f"**Comparison Period:** vs. {lookback} day(s) prior\n\n"

    if active_filters:
        filter_parts = []
        if active_filters.get("regions"):
            filter_parts.append(f"Regions: {', '.join(active_filters['regions'])}")
        if active_filters.get("counties"):
            filter_parts.append(f"Counties: {', '.join(active_filters['counties'])}")
        if active_filters.get("incident_types"):
            filter_parts.append(f"Incident Types: {', '.join(active_filters['incident_types'])}")
        if filter_parts:
            content += "**Active Filters:** " + "; ".join(filter_parts) + "\n"
            content += "(Note: All metrics below reflect only the filtered subset of data.)\n\n"

    content += "## Current Day Snapshot\n```json\n"
    content += json.dumps(snapshot, indent=2, default=str)
    content += "\n```\n\n"

    if changes:
        content += "## Changes vs Prior Period\n```json\n"
        content += json.dumps(changes, indent=2, default=str)
        content += "\n```\n\n"

    if trends:
        content += "## 30-Day Trend Analysis\n```json\n"
        content += json.dumps(trends, indent=2, default=str)
        content += "\n```\n\n"

    content += (
        "Produce the executive situational awareness briefing based on the data above. "
        "Focus on what decision-makers need to know right now."
    )
    return content


# ---------------------------------------------------------------------------
# Milestone 3: Drill-Down Metric Functions
# ---------------------------------------------------------------------------


def get_county_detail(data: dict, county_sk: int, datesk: int) -> dict:
    """Single-county snapshot with name, region, alert status, and key KPIs."""
    dcm = data["daily_county"]
    row = dcm[(dcm["CountySK"] == county_sk) & (dcm["DateSK"] == datesk)]
    if row.empty:
        return {}

    row = row.iloc[0]
    return {
        "county_name": _county_name(data, county_sk),
        "region_name": _region_name(data, int(row["RegionSK"])),
        "alert_status": row.get("AlertStatus", "Unknown"),
        "active_incidents": int(row.get("ActiveIncidents", 0)),
        "avg_response_time": round(float(row.get("AvgResponseTimeHours", 0)), 1),
        "icu_capacity_pct": round(float(row.get("ICUCapacityPct", 0)), 1),
        "staff_shortage_rate": round(float(row.get("StaffShortageRate", 0)), 2),
        "ppe_days_on_hand": round(float(row.get("PPEDaysOnHand", 0)), 1),
        "capacity_stress_score": round(float(row.get("CapacityStressScore", 0)), 2),
    }


def get_county_facility_capacity(
    data: dict, county_sk: int, start_datesk: int, end_datesk: int
) -> pd.DataFrame:
    """
    Facility-level ICU/staffing data for a county.
    Columns: Date, FacilitySK, FacilityName, ICUTotalBeds, ICUOccupiedBeds,
             ICUOccPct, StaffFillRate, StaffedBedsTotal, StaffedBedsOccupied
    """
    fac_cap = data["facility_capacity"]
    fac_dim = data["facilities"][["FacilitySK", "FacilityName", "CountySK"]]

    window = fac_cap[
        (fac_cap["CountySK"] == county_sk)
        & (fac_cap["DateSK"] >= start_datesk)
        & (fac_cap["DateSK"] <= end_datesk)
    ]
    if window.empty:
        return pd.DataFrame()

    merged = window.merge(fac_dim[["FacilitySK", "FacilityName"]], on="FacilitySK", how="left")
    merged["ICUOccPct"] = (merged["ICUOccupiedBeds"] / merged["ICUTotalBeds"] * 100).round(1)
    merged["Date"] = merged["DateSK"].apply(lambda sk: _datesk_to_date(sk).date())
    return merged


def get_county_inventory(
    data: dict, county_sk: int, start_datesk: int, end_datesk: int
) -> pd.DataFrame:
    """
    Inventory levels by item for a single county.
    Columns: Date, ItemName, OnHandQty, EstimatedDaysOnHand
    """
    inv = data["inventory"]
    items = data["items"][["ItemSK", "ItemName"]]

    window = inv[
        (inv["CountySK"] == county_sk)
        & (inv["DateSK"] >= start_datesk)
        & (inv["DateSK"] <= end_datesk)
    ]
    if window.empty:
        return pd.DataFrame()

    merged = window.merge(items, on="ItemSK", how="left")
    merged["Date"] = merged["DateSK"].apply(lambda sk: _datesk_to_date(sk).date())
    return merged


def get_county_incidents(
    data: dict, county_sk: int, start_datesk: int, end_datesk: int
) -> pd.DataFrame:
    """
    Incident events for a single county.
    Columns: Date, IncidentTypeName, SeverityLevel, DetectionTimeHours,
             EscalationTimeHours, ResponseTimeHours
    """
    inc = data["incidents"]
    types = data["incident_types"][["IncidentTypeSK", "IncidentTypeName"]]

    window = inc[
        (inc["CountySK"] == county_sk)
        & (inc["DateSK"] >= start_datesk)
        & (inc["DateSK"] <= end_datesk)
    ]
    if window.empty:
        return pd.DataFrame()

    merged = window.merge(types, on="IncidentTypeSK", how="left")
    merged["Date"] = merged["DateSK"].apply(lambda sk: _datesk_to_date(sk).date())
    cols = ["Date", "IncidentTypeName", "SeverityLevel", "DetectionTimeHours",
            "EscalationTimeHours", "ResponseTimeHours"]
    return merged[cols].sort_values("Date", ascending=False)


def get_county_alert_timeline(
    data: dict, county_sk: int, start_datesk: int, end_datesk: int
) -> pd.DataFrame:
    """
    Daily alert status for a single county.
    Columns: Date, AlertStatus
    """
    dcm = data["daily_county"]
    window = dcm[
        (dcm["CountySK"] == county_sk)
        & (dcm["DateSK"] >= start_datesk)
        & (dcm["DateSK"] <= end_datesk)
    ]
    if window.empty:
        return pd.DataFrame()

    result = window[["DateSK", "AlertStatus"]].copy()
    result["Date"] = result["DateSK"].apply(lambda sk: _datesk_to_date(sk).date())
    return result[["Date", "AlertStatus"]].sort_values("Date")


def get_facility_detail(
    data: dict, facility_sk: int, start_datesk: int, end_datesk: int
) -> pd.DataFrame:
    """
    Single facility daily capacity data.
    Columns: Date, ICUTotalBeds, ICUOccupiedBeds, ICUOccPct, StaffFillRate,
             StaffedBedsTotal, StaffedBedsOccupied
    """
    fac_cap = data["facility_capacity"]
    window = fac_cap[
        (fac_cap["FacilitySK"] == facility_sk)
        & (fac_cap["DateSK"] >= start_datesk)
        & (fac_cap["DateSK"] <= end_datesk)
    ]
    if window.empty:
        return pd.DataFrame()

    result = window.copy()
    result["ICUOccPct"] = (result["ICUOccupiedBeds"] / result["ICUTotalBeds"] * 100).round(1)
    result["Date"] = result["DateSK"].apply(lambda sk: _datesk_to_date(sk).date())
    return result.sort_values("Date")


def get_transfer_flows(
    data: dict, start_datesk: int, end_datesk: int, county_sk: int | None = None
) -> pd.DataFrame:
    """
    Aggregated transfer flows for Sankey diagram.
    Columns: FromCountyName, ToCountyName, TotalQty, AvgDelayDays, TransferCount
    """
    xfer = data["transfers"]
    counties = data["counties"][["CountySK", "CountyName"]]

    window = xfer[(xfer["DateSK"] >= start_datesk) & (xfer["DateSK"] <= end_datesk)]

    if county_sk is not None:
        window = window[
            (window["FromCountySK"] == county_sk) | (window["ToCountySK"] == county_sk)
        ]

    if window.empty:
        return pd.DataFrame()

    # Join from/to county names
    merged = window.merge(
        counties.rename(columns={"CountySK": "FromCountySK", "CountyName": "FromCountyName"}),
        on="FromCountySK",
        how="left",
    ).merge(
        counties.rename(columns={"CountySK": "ToCountySK", "CountyName": "ToCountyName"}),
        on="ToCountySK",
        how="left",
    )

    agg = merged.groupby(["FromCountyName", "ToCountyName"]).agg(
        TotalQty=("TransferQty", "sum"),
        AvgDelayDays=("ShipmentDelayDays", "mean"),
        TransferCount=("TransferQty", "count"),
    ).reset_index()

    return agg.sort_values("TotalQty", ascending=False)


def get_incident_timeline(
    data: dict,
    start_datesk: int,
    end_datesk: int,
    county_sk: int | None = None,
    incident_type_sk: int | None = None,
    severity: str | None = None,
) -> pd.DataFrame:
    """
    Filterable incident event table.
    Columns: Date, CountyName, IncidentTypeName, SeverityLevel,
             DetectionTimeHours, EscalationTimeHours, ResponseTimeHours
    """
    inc = data["incidents"]
    types = data["incident_types"][["IncidentTypeSK", "IncidentTypeName"]]
    counties = data["counties"][["CountySK", "CountyName"]]

    window = inc[(inc["DateSK"] >= start_datesk) & (inc["DateSK"] <= end_datesk)]

    if county_sk is not None:
        window = window[window["CountySK"] == county_sk]
    if incident_type_sk is not None:
        window = window[window["IncidentTypeSK"] == incident_type_sk]
    if severity is not None:
        window = window[window["SeverityLevel"] == severity]

    if window.empty:
        return pd.DataFrame()

    merged = window.merge(types, on="IncidentTypeSK", how="left")
    merged = merged.merge(counties, on="CountySK", how="left")
    merged["Date"] = merged["DateSK"].apply(lambda sk: _datesk_to_date(sk).date())

    cols = ["Date", "CountyName", "IncidentTypeName", "SeverityLevel",
            "DetectionTimeHours", "EscalationTimeHours", "ResponseTimeHours"]
    return merged[cols].sort_values("Date", ascending=False)
