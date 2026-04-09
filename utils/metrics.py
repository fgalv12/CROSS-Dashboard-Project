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
    "evaluate_thresholds",
    "evaluate_county_thresholds",
    "get_threshold_breach_timeline",
    "get_active_breaches",
    "build_daily_digest_md",
    "build_daily_digest_pdf",
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


def _check_breach(actual: float, threshold_value: float, direction: str) -> bool:
    """Check if an actual value breaches a threshold given a direction."""
    if direction == ">=":
        return actual >= threshold_value
    elif direction == "<=":
        return actual <= threshold_value
    return False


def evaluate_thresholds(snapshot: dict, thresholds: dict) -> dict:
    """
    Evaluate which thresholds are breached for a statewide snapshot.
    Returns dict keyed by threshold key with breach details.
    """
    # Map snapshot keys to threshold keys
    mapping = {
        "icu_capacity_pct": "avg_icu_capacity_pct",
        "avg_response_time": "avg_response_time_hours",
        "ppe_days_on_hand": "avg_ppe_days_on_hand",
        "staff_shortage_rate": "avg_staff_shortage_rate",
        "supply_delay_days": "avg_supply_delay_days",
        "capacity_stress_score": "avg_capacity_stress_score",
    }

    results = {}
    for thresh_key, snap_key in mapping.items():
        if thresh_key not in thresholds:
            continue
        thresh = thresholds[thresh_key]
        actual = snapshot.get(snap_key, 0)
        if actual is None:
            actual = 0
        results[thresh_key] = {
            "breached": _check_breach(float(actual), thresh["value"], thresh["direction"]),
            "actual": float(actual),
            "threshold": thresh["value"],
            "direction": thresh["direction"],
            "label": thresh["label"],
        }
    return results


def evaluate_county_thresholds(county_info: dict, thresholds: dict) -> dict:
    """
    Evaluate which thresholds are breached for a single county detail dict.
    Returns dict keyed by threshold key with breach details.
    """
    # Map county_info keys to threshold keys
    mapping = {
        "icu_capacity_pct": "icu_capacity_pct",
        "avg_response_time": "avg_response_time",
        "ppe_days_on_hand": "ppe_days_on_hand",
        "staff_shortage_rate": "staff_shortage_rate",
        "capacity_stress_score": "capacity_stress_score",
    }

    results = {}
    for thresh_key, county_key in mapping.items():
        if thresh_key not in thresholds:
            continue
        thresh = thresholds[thresh_key]
        actual = county_info.get(county_key, 0)
        if actual is None:
            actual = 0
        results[thresh_key] = {
            "breached": _check_breach(float(actual), thresh["value"], thresh["direction"]),
            "actual": float(actual),
            "threshold": thresh["value"],
            "direction": thresh["direction"],
            "label": thresh["label"],
        }
    return results


def get_threshold_breach_timeline(
    data: dict, start_datesk: int, end_datesk: int, thresholds: dict
) -> pd.DataFrame:
    """
    Evaluate custom thresholds across all counties over a date range.
    Returns DataFrame with columns:
        Date, DateSK, CountySK, CountyName, RegionName, Metric, Breached, Value, Threshold
    One row per county per day per threshold metric.
    """
    dcm = data["daily_county"]
    window = dcm[(dcm["DateSK"] >= start_datesk) & (dcm["DateSK"] <= end_datesk)].copy()
    if window.empty:
        return pd.DataFrame()

    counties = data["counties"][["CountySK", "CountyName"]]
    regions = data["regions"][["RegionSK", "RegionName"]]
    window = window.merge(counties, on="CountySK", how="left")
    window = window.merge(regions, on="RegionSK", how="left")

    # Map threshold keys to DataFrame columns
    col_map = {
        "icu_capacity_pct": "ICUCapacityPct",
        "avg_response_time": "AvgResponseTimeHours",
        "ppe_days_on_hand": "PPEDaysOnHand",
        "staff_shortage_rate": "StaffShortageRate",
        "supply_delay_days": "AvgSupplyDelayDays",
        "capacity_stress_score": "CapacityStressScore",
    }

    rows = []
    for thresh_key, col_name in col_map.items():
        if thresh_key not in thresholds or col_name not in window.columns:
            continue
        t = thresholds[thresh_key]
        vals = window[col_name]
        breached = vals.apply(lambda v: _check_breach(float(v), t["value"], t["direction"]))

        subset = window[["DateSK", "CountySK", "CountyName", "RegionName"]].copy()
        subset["Date"] = subset["DateSK"].apply(lambda sk: _datesk_to_date(sk).date())
        subset["Metric"] = t["label"]
        subset["Breached"] = breached
        subset["Value"] = vals.values
        subset["Threshold"] = t["value"]
        rows.append(subset)

    if not rows:
        return pd.DataFrame()

    return pd.concat(rows, ignore_index=True).sort_values(["Date", "CountyName", "Metric"])


def get_active_breaches(
    data: dict, datesk: int, thresholds: dict
) -> pd.DataFrame:
    """
    Return currently active threshold breaches for a single date.
    Returns DataFrame with columns:
        CountyName, RegionName, Metric, Value, Threshold, Direction
    Only includes rows where a breach is active.
    """
    dcm = data["daily_county"]
    day = dcm[dcm["DateSK"] == datesk].copy()
    if day.empty:
        return pd.DataFrame()

    counties = data["counties"][["CountySK", "CountyName"]]
    regions = data["regions"][["RegionSK", "RegionName"]]
    day = day.merge(counties, on="CountySK", how="left")
    day = day.merge(regions, on="RegionSK", how="left")

    col_map = {
        "icu_capacity_pct": "ICUCapacityPct",
        "avg_response_time": "AvgResponseTimeHours",
        "ppe_days_on_hand": "PPEDaysOnHand",
        "staff_shortage_rate": "StaffShortageRate",
        "supply_delay_days": "AvgSupplyDelayDays",
        "capacity_stress_score": "CapacityStressScore",
    }

    rows = []
    for thresh_key, col_name in col_map.items():
        if thresh_key not in thresholds or col_name not in day.columns:
            continue
        t = thresholds[thresh_key]
        for _, row in day.iterrows():
            val = float(row[col_name])
            if _check_breach(val, t["value"], t["direction"]):
                rows.append({
                    "CountyName": row["CountyName"],
                    "RegionName": row["RegionName"],
                    "Metric": t["label"],
                    "Value": round(val, 2),
                    "Threshold": t["value"],
                    "Direction": t["direction"],
                })

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values(["Metric", "CountyName"])


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


# ---------------------------------------------------------------------------
# Milestone 4: Daily Digest Export
# ---------------------------------------------------------------------------


def build_daily_digest_md(
    date_label: str,
    snapshot: dict,
    kpi_cards: list[dict],
    breach_results: dict,
    active_breaches_df: pd.DataFrame,
    briefing_text: str | None = None,
    active_filters: dict | None = None,
) -> str:
    """
    Generate a Markdown daily digest report suitable for email distribution.
    """
    lines = []
    lines.append("# CROSS Daily Situational Digest")
    lines.append(f"**Date:** {date_label}")
    lines.append(f"**Generated:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    if active_filters:
        parts = []
        if active_filters.get("regions"):
            parts.append(f"Regions: {', '.join(active_filters['regions'])}")
        if active_filters.get("counties"):
            parts.append(f"Counties: {', '.join(active_filters['counties'])}")
        if active_filters.get("incident_types"):
            parts.append(f"Incident Types: {', '.join(active_filters['incident_types'])}")
        if parts:
            lines.append(f"**Filters:** {'; '.join(parts)}")
            lines.append("")

    lines.append("---")
    lines.append("")

    # Executive KPIs
    lines.append("## Executive Snapshot")
    lines.append("")
    lines.append("| Metric | Value | Change |")
    lines.append("|--------|-------|--------|")
    for card in kpi_cards:
        delta = card["delta"] if card["delta"] else "—"
        lines.append(f"| {card['label']} | {card['value']} | {delta} |")
    lines.append("")

    # Threshold breaches
    breached_items = {k: v for k, v in breach_results.items() if v["breached"]}
    if breached_items:
        lines.append("## Threshold Alerts")
        lines.append("")
        lines.append(f"**{len(breached_items)} statewide threshold(s) breached:**")
        lines.append("")
        for key, b in breached_items.items():
            lines.append(f"- **{b['label']}**: {b['actual']:.2f} (threshold: {b['direction']} {b['threshold']})")
        lines.append("")

    # Active county breaches
    if not active_breaches_df.empty:
        lines.append(f"### County-Level Breaches ({len(active_breaches_df)} total)")
        lines.append("")
        lines.append("| County | Region | Metric | Actual | Limit |")
        lines.append("|--------|--------|--------|--------|-------|")
        # Show top 20 to keep digest manageable
        for _, row in active_breaches_df.head(20).iterrows():
            lines.append(
                f"| {row['CountyName']} | {row['RegionName']} | {row['Metric']} "
                f"| {row['Value']:.2f} | {row['Direction']} {row['Threshold']:.2f} |"
            )
        if len(active_breaches_df) > 20:
            lines.append(f"| ... | ... | ... | ... | ... |")
            lines.append(f"*{len(active_breaches_df) - 20} additional breaches not shown.*")
        lines.append("")
    else:
        lines.append("## Threshold Alerts")
        lines.append("")
        lines.append("No counties are currently breaching any configured thresholds.")
        lines.append("")

    # Alert status summary
    alert_counts = snapshot.get("alert_status_counts", {})
    if alert_counts:
        lines.append("## Alert Status Distribution")
        lines.append("")
        for status in ["Critical", "Alert", "Watch", "Normal"]:
            count = alert_counts.get(status, 0)
            if count > 0:
                lines.append(f"- **{status}:** {count} counties")
        lines.append("")

    # AI Briefing
    if briefing_text:
        lines.append("---")
        lines.append("")
        lines.append("## AI Situational Briefing")
        lines.append("")
        lines.append(briefing_text)
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append("*CROSS Dashboard — Crisis Response & Operational Statewide Status*")
    lines.append("*Prepared by Francisco Galvez (Oracle Health AI CoE)*")

    return "\n".join(lines)


def build_daily_digest_pdf(
    date_label: str,
    snapshot: dict,
    kpi_cards: list[dict],
    breach_results: dict,
    active_breaches_df: pd.DataFrame,
    briefing_text: str | None = None,
    active_filters: dict | None = None,
) -> bytes:
    """
    Generate a PDF daily digest report. Returns PDF as bytes.
    Requires fpdf2 package.
    """
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(178, 34, 34)
    pdf.cell(0, 12, "CROSS Daily Situational Digest", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6, f"Date: {date_label}  |  Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}", new_x="LMARGIN", new_y="NEXT", align="C")

    if active_filters:
        parts = []
        if active_filters.get("regions"):
            parts.append(f"Regions: {', '.join(active_filters['regions'])}")
        if active_filters.get("counties"):
            parts.append(f"Counties: {', '.join(active_filters['counties'])}")
        if active_filters.get("incident_types"):
            parts.append(f"Incident Types: {', '.join(active_filters['incident_types'])}")
        if parts:
            pdf.cell(0, 6, f"Filters: {'; '.join(parts)}", new_x="LMARGIN", new_y="NEXT", align="C")

    pdf.ln(4)
    pdf.set_draw_color(178, 34, 34)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(6)

    # Executive Snapshot
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 8, "Executive Snapshot", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # KPI table
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(139, 26, 26)
    pdf.set_text_color(255, 255, 255)
    col_w = [55, 40, 40]
    headers = ["Metric", "Value", "Change"]
    for w, h in zip(col_w, headers):
        pdf.cell(w, 7, h, border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(0, 0, 0)
    for card in kpi_cards:
        delta = card["delta"] if card["delta"] else "-"
        pdf.cell(col_w[0], 6, card["label"], border=1)
        pdf.cell(col_w[1], 6, card["value"], border=1, align="C")
        pdf.cell(col_w[2], 6, str(delta), border=1, align="C")
        pdf.ln()

    pdf.ln(4)

    # Threshold Alerts
    breached_items = {k: v for k, v in breach_results.items() if v["breached"]}
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "Threshold Alerts", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    if breached_items:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, f"{len(breached_items)} statewide threshold(s) breached:", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        for key, b in breached_items.items():
            pdf.cell(0, 5, f"  - {b['label']}: {b['actual']:.2f} (threshold: {b['direction']} {b['threshold']})", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    if not active_breaches_df.empty:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, f"County-Level Breaches ({len(active_breaches_df)} total):", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(139, 26, 26)
        pdf.set_text_color(255, 255, 255)
        bcol_w = [35, 30, 35, 25, 25]
        bheaders = ["County", "Region", "Metric", "Actual", "Limit"]
        for w, h in zip(bcol_w, bheaders):
            pdf.cell(w, 6, h, border=1, fill=True, align="C")
        pdf.ln()

        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(0, 0, 0)
        for _, row in active_breaches_df.head(25).iterrows():
            pdf.cell(bcol_w[0], 5, str(row["CountyName"])[:18], border=1)
            pdf.cell(bcol_w[1], 5, str(row["RegionName"])[:16], border=1)
            pdf.cell(bcol_w[2], 5, str(row["Metric"]), border=1)
            pdf.cell(bcol_w[3], 5, f"{row['Value']:.2f}", border=1, align="C")
            pdf.cell(bcol_w[4], 5, f"{row['Direction']} {row['Threshold']:.2f}", border=1, align="C")
            pdf.ln()
        if len(active_breaches_df) > 25:
            pdf.set_font("Helvetica", "I", 8)
            pdf.cell(0, 5, f"... {len(active_breaches_df) - 25} additional breaches not shown.", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(46, 139, 87)
        pdf.cell(0, 6, "No counties are currently breaching any configured thresholds.", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

    pdf.ln(4)

    # Alert Status Distribution
    alert_counts = snapshot.get("alert_status_counts", {})
    if alert_counts:
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 8, "Alert Status Distribution", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 10)
        for status in ["Critical", "Alert", "Watch", "Normal"]:
            count = alert_counts.get(status, 0)
            if count > 0:
                pdf.cell(0, 5, f"  {status}: {count} counties", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    # AI Briefing
    if briefing_text:
        pdf.set_draw_color(178, 34, 34)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, "AI Situational Briefing", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 9)
        # Clean markdown formatting and replace Unicode characters unsupported by Helvetica
        clean_text = briefing_text.replace("**", "").replace("##", "").replace("# ", "")
        clean_text = (
            clean_text
            .replace("\u2022", "-")   # bullet •
            .replace("\u2013", "-")   # en dash –
            .replace("\u2014", "--")  # em dash —
            .replace("\u2018", "'")   # left single quote '
            .replace("\u2019", "'")   # right single quote '
            .replace("\u201c", '"')   # left double quote "
            .replace("\u201d", '"')   # right double quote "
            .replace("\u2026", "...") # ellipsis …
            .replace("\u00b7", "-")   # middle dot ·
        )
        # Strip any remaining non-latin1 characters
        clean_text = clean_text.encode("latin-1", errors="replace").decode("latin-1")
        pdf.multi_cell(0, 4.5, clean_text)

    # Footer
    pdf.ln(6)
    pdf.set_draw_color(178, 34, 34)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, "CROSS Dashboard - Crisis Response & Operational Statewide Status", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.cell(0, 5, "Prepared by Francisco Galvez (Oracle Health AI CoE)", new_x="LMARGIN", new_y="NEXT", align="C")

    return bytes(pdf.output())
