"""
CROSS Dashboard – AI Situational Awareness Agent

Monitors dashboard data and produces executive-ready briefings that answer:
  • What changed?
  • What looks abnormal?
  • What requires attention?

Usage:
    python3 cross_situational_awareness_agent.py                     # latest date
    python3 cross_situational_awareness_agent.py --date 2026-02-15   # specific date
    python3 cross_situational_awareness_agent.py --lookback 7        # compare vs 7 days ago (default: 1)

Requires:
    pip install anthropic pandas openpyxl
    export ANTHROPIC_API_KEY=sk-ant-...
"""

import argparse
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

import anthropic
import pandas as pd

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

DATA_FILE = Path(__file__).parent / "KS_CROSS_mock_dataset.xlsx"

SHEET_NAMES = {
    "regions": "Dim_Region",
    "counties": "Dim_County",
    "dates": "Dim_Date",
    "facility_types": "Dim_FacilityType",
    "facilities": "Dim_Facility",
    "incident_types": "Dim_IncidentType",
    "items": "Dim_Item",
    "daily_county": "Fact_DailyCountyMetrics",
    "facility_capacity": "Fact_FacilityCapacityDaily",
    "inventory": "Fact_InventoryDaily",
    "transfers": "Fact_ResourceTransfers",
    "incidents": "Fact_IncidentEvents",
}


def load_data(path: Path = DATA_FILE) -> dict[str, pd.DataFrame]:
    """Load all sheets from the CROSS dataset into a dict of DataFrames."""
    xls = pd.ExcelFile(path)
    data = {}
    for key, sheet in SHEET_NAMES.items():
        data[key] = pd.read_excel(xls, sheet_name=sheet)
    return data


# ---------------------------------------------------------------------------
# Metric extraction
# ---------------------------------------------------------------------------


def _datesk_to_date(datesk: int) -> pd.Timestamp:
    """Convert integer DateSK (YYYYMMDD) to Timestamp."""
    return pd.Timestamp(str(datesk))


def _resolve_date(data: dict, target_date: str | None) -> int:
    """Return the DateSK for the target date, or the latest available date."""
    dates_df = data["dates"]
    if target_date:
        target = pd.Timestamp(target_date)
        match = dates_df[dates_df["Date"] == target]
        if match.empty:
            available = dates_df["Date"].sort_values()
            sys.exit(
                f"Date {target_date} not found in dataset. "
                f"Available range: {available.iloc[0].date()} to {available.iloc[-1].date()}"
            )
        return int(match.iloc[0]["DateSK"])
    return int(dates_df["DateSK"].max())


def _prior_datesk(data: dict, current_sk: int, lookback: int) -> int | None:
    """Return the DateSK that is `lookback` days before current_sk, or None."""
    current = _datesk_to_date(current_sk)
    prior = current - timedelta(days=lookback)
    prior_sk = int(prior.strftime("%Y%m%d"))
    if prior_sk in data["dates"]["DateSK"].values:
        return prior_sk
    return None


def _region_name(data: dict, region_sk: int) -> str:
    match = data["regions"][data["regions"]["RegionSK"] == region_sk]
    return match.iloc[0]["RegionName"] if not match.empty else f"Region {region_sk}"


def _county_name(data: dict, county_sk: int) -> str:
    match = data["counties"][data["counties"]["CountySK"] == county_sk]
    return match.iloc[0]["CountyName"] if not match.empty else f"County {county_sk}"


def _incident_type_name(data: dict, type_sk: int) -> str:
    match = data["incident_types"][data["incident_types"]["IncidentTypeSK"] == type_sk]
    return match.iloc[0]["IncidentTypeName"] if not match.empty else f"Type {type_sk}"


def _item_name(data: dict, item_sk: int) -> str:
    match = data["items"][data["items"]["ItemSK"] == item_sk]
    return match.iloc[0]["ItemName"] if not match.empty else f"Item {item_sk}"


def compute_snapshot(data: dict, datesk: int) -> dict:
    """Compute a full metrics snapshot for a single date."""
    dcm = data["daily_county"]
    day = dcm[dcm["DateSK"] == datesk]

    snapshot = {}

    # --- Statewide KPIs ---
    snapshot["total_active_incidents"] = int(day["ActiveIncidents"].sum())
    snapshot["total_new_incidents"] = int(day["NewIncidents"].sum())
    snapshot["avg_response_time_hours"] = round(day["AvgResponseTimeHours"].mean(), 2)
    snapshot["avg_deployment_lag_hours"] = round(day["ResourceDeploymentLagHours"].mean(), 2)
    snapshot["avg_icu_capacity_pct"] = round(day["ICUCapacityPct"].mean(), 2)
    snapshot["avg_staff_shortage_rate"] = round(day["StaffShortageRate"].mean(), 4)
    snapshot["avg_ppe_days_on_hand"] = round(day["PPEDaysOnHand"].mean(), 2)
    snapshot["avg_supply_delay_days"] = round(day["AvgSupplyDelayDays"].mean(), 2)

    # --- Alert status distribution ---
    alert_counts = day["AlertStatus"].value_counts().to_dict()
    snapshot["alert_status_counts"] = {str(k): int(v) for k, v in alert_counts.items()}

    # --- Counties in Critical/Alert ---
    critical_counties = day[day["AlertStatus"] == "Critical"]
    alert_counties = day[day["AlertStatus"] == "Alert"]
    snapshot["critical_counties"] = [
        {
            "county": _county_name(data, row["CountySK"]),
            "icu_capacity_pct": round(row["ICUCapacityPct"], 1),
            "active_incidents": int(row["ActiveIncidents"]),
            "capacity_stress_score": round(row["CapacityStressScore"], 3),
        }
        for _, row in critical_counties.iterrows()
    ]
    snapshot["alert_counties"] = [
        {
            "county": _county_name(data, row["CountySK"]),
            "icu_capacity_pct": round(row["ICUCapacityPct"], 1),
            "active_incidents": int(row["ActiveIncidents"]),
        }
        for _, row in alert_counties.iterrows()
    ]

    # --- Trending up counties ---
    trending = day[day["TrendingUpFlag"] == "Y"]
    snapshot["trending_up_counties"] = [
        _county_name(data, row["CountySK"]) for _, row in trending.iterrows()
    ]

    # --- Hospital overload flags ---
    overloaded = day[day["HospitalOverloadFlag"] == "Y"]
    snapshot["hospital_overload_counties"] = [
        _county_name(data, row["CountySK"]) for _, row in overloaded.iterrows()
    ]

    # --- Regional breakdowns ---
    region_stats = []
    for region_sk, group in day.groupby("RegionSK"):
        region_stats.append(
            {
                "region": _region_name(data, region_sk),
                "active_incidents": int(group["ActiveIncidents"].sum()),
                "new_incidents": int(group["NewIncidents"].sum()),
                "avg_response_time": round(group["AvgResponseTimeHours"].mean(), 2),
                "avg_icu_capacity_pct": round(group["ICUCapacityPct"].mean(), 2),
                "avg_ppe_days_on_hand": round(group["PPEDaysOnHand"].mean(), 2),
                "avg_staff_shortage_rate": round(group["StaffShortageRate"].mean(), 4),
                "counties_in_critical": int((group["AlertStatus"] == "Critical").sum()),
                "counties_in_alert": int((group["AlertStatus"] == "Alert").sum()),
            }
        )
    snapshot["regions"] = region_stats

    # --- Facility capacity highlights ---
    fcd = data["facility_capacity"]
    fac_day = fcd[fcd["DateSK"] == datesk]
    if not fac_day.empty:
        fac_day = fac_day.copy()
        fac_day["ICUOccPct"] = (fac_day["ICUOccupiedBeds"] / fac_day["ICUTotalBeds"] * 100).round(1)
        high_icu = fac_day[fac_day["ICUOccPct"] >= 90].sort_values("ICUOccPct", ascending=False).head(10)
        snapshot["high_icu_facilities"] = [
            {
                "facility": data["facilities"][data["facilities"]["FacilitySK"] == row["FacilitySK"]].iloc[0]["FacilityName"]
                if not data["facilities"][data["facilities"]["FacilitySK"] == row["FacilitySK"]].empty
                else f"Facility {row['FacilitySK']}",
                "icu_occupancy_pct": row["ICUOccPct"],
                "staff_fill_rate": round(row["StaffFillRate"], 3),
            }
            for _, row in high_icu.iterrows()
        ]

    # --- Inventory concerns ---
    inv = data["inventory"]
    inv_day = inv[inv["DateSK"] == datesk]
    if not inv_day.empty:
        low_inv = inv_day[inv_day["EstimatedDaysOnHand"] <= 5]
        inv_concerns = []
        for _, row in low_inv.iterrows():
            inv_concerns.append(
                {
                    "county": _county_name(data, row["CountySK"]),
                    "item": _item_name(data, row["ItemSK"]),
                    "days_on_hand": round(row["EstimatedDaysOnHand"], 1),
                    "on_hand_qty": round(row["OnHandQty"], 1),
                }
            )
        snapshot["low_inventory_items"] = sorted(inv_concerns, key=lambda x: x["days_on_hand"])[:20]

    # --- Resource transfer activity ---
    xfer = data["transfers"]
    xfer_day = xfer[xfer["DateSK"] == datesk]
    if not xfer_day.empty:
        snapshot["transfers_today"] = {
            "total_transfers": len(xfer_day),
            "total_quantity": int(xfer_day["TransferQty"].sum()),
            "avg_delay_days": round(xfer_day["ShipmentDelayDays"].mean(), 2),
            "status_breakdown": {str(k): int(v) for k, v in xfer_day["ShipmentStatus"].value_counts().to_dict().items()},
            "delayed_transfers": len(xfer_day[xfer_day["ShipmentDelayDays"] > 2]),
        }

    # --- Incident breakdown by type ---
    inc = data["incidents"]
    inc_day = inc[inc["DateSK"] == datesk]
    if not inc_day.empty:
        type_stats = []
        for type_sk, group in inc_day.groupby("IncidentTypeSK"):
            type_stats.append(
                {
                    "type": _incident_type_name(data, type_sk),
                    "count": len(group),
                    "avg_detection_hours": round(group["DetectionTimeHours"].mean(), 2),
                    "avg_response_hours": round(group["ResponseTimeHours"].mean(), 2),
                    "severity_breakdown": {
                        str(k): int(v) for k, v in group["SeverityLevel"].value_counts().to_dict().items()
                    },
                }
            )
        snapshot["incidents_by_type"] = type_stats

    return snapshot


def compute_changes(current: dict, prior: dict) -> dict:
    """Compute deltas between two snapshots for key metrics."""
    changes = {}

    metric_pairs = [
        ("total_active_incidents", "Active Incidents"),
        ("total_new_incidents", "New Incidents"),
        ("avg_response_time_hours", "Avg Response Time (hrs)"),
        ("avg_deployment_lag_hours", "Avg Deployment Lag (hrs)"),
        ("avg_icu_capacity_pct", "Avg ICU Capacity %"),
        ("avg_staff_shortage_rate", "Avg Staff Shortage Rate"),
        ("avg_ppe_days_on_hand", "Avg PPE Days on Hand"),
        ("avg_supply_delay_days", "Avg Supply Delay (days)"),
    ]

    deltas = []
    for key, label in metric_pairs:
        cur_val = current.get(key, 0)
        pri_val = prior.get(key, 0)
        if pri_val != 0:
            pct_change = round((cur_val - pri_val) / abs(pri_val) * 100, 1)
        else:
            pct_change = None
        deltas.append(
            {
                "metric": label,
                "current": cur_val,
                "prior": pri_val,
                "absolute_change": round(cur_val - pri_val, 2),
                "pct_change": pct_change,
            }
        )
    changes["kpi_deltas"] = deltas

    # Region-level changes
    cur_regions = {r["region"]: r for r in current.get("regions", [])}
    pri_regions = {r["region"]: r for r in prior.get("regions", [])}
    region_changes = []
    for name, cur_r in cur_regions.items():
        pri_r = pri_regions.get(name)
        if pri_r:
            region_changes.append(
                {
                    "region": name,
                    "incident_change": cur_r["active_incidents"] - pri_r["active_incidents"],
                    "incident_pct_change": (
                        round((cur_r["active_incidents"] - pri_r["active_incidents"]) / max(pri_r["active_incidents"], 1) * 100, 1)
                    ),
                    "response_time_change": round(cur_r["avg_response_time"] - pri_r["avg_response_time"], 2),
                    "icu_capacity_change": round(cur_r["avg_icu_capacity_pct"] - pri_r["avg_icu_capacity_pct"], 2),
                    "ppe_days_change": round(cur_r["avg_ppe_days_on_hand"] - pri_r["avg_ppe_days_on_hand"], 2),
                }
            )
    changes["region_changes"] = region_changes

    # Alert status shifts
    cur_alerts = current.get("alert_status_counts", {})
    pri_alerts = prior.get("alert_status_counts", {})
    all_statuses = set(list(cur_alerts.keys()) + list(pri_alerts.keys()))
    alert_shifts = {}
    for status in sorted(all_statuses):
        cur_count = cur_alerts.get(status, 0)
        pri_count = pri_alerts.get(status, 0)
        if cur_count != pri_count:
            alert_shifts[status] = {"current": cur_count, "prior": pri_count, "change": cur_count - pri_count}
    changes["alert_status_shifts"] = alert_shifts

    return changes


# ---------------------------------------------------------------------------
# 30-day trend analysis
# ---------------------------------------------------------------------------


def compute_trends(data: dict, current_datesk: int) -> dict:
    """Compute 30-day trend stats for statewide KPIs."""
    dcm = data["daily_county"]
    current_date = _datesk_to_date(current_datesk)
    start_date = current_date - timedelta(days=30)
    start_sk = int(start_date.strftime("%Y%m%d"))

    window = dcm[(dcm["DateSK"] >= start_sk) & (dcm["DateSK"] <= current_datesk)]
    if window.empty:
        return {}

    daily = window.groupby("DateSK").agg(
        active_incidents=("ActiveIncidents", "sum"),
        avg_response_time=("AvgResponseTimeHours", "mean"),
        avg_icu_capacity=("ICUCapacityPct", "mean"),
        avg_ppe_days=("PPEDaysOnHand", "mean"),
        avg_staff_shortage=("StaffShortageRate", "mean"),
        critical_counties=("AlertStatus", lambda x: (x == "Critical").sum()),
    ).reset_index()

    trends = {}
    for col in ["active_incidents", "avg_response_time", "avg_icu_capacity", "avg_ppe_days", "avg_staff_shortage", "critical_counties"]:
        series = daily[col]
        trends[col] = {
            "mean_30d": round(series.mean(), 2),
            "min_30d": round(series.min(), 2),
            "max_30d": round(series.max(), 2),
            "current": round(series.iloc[-1], 2),
            "std_30d": round(series.std(), 2),
        }
        # Flag if current value is > 1.5 std devs from mean
        mean = series.mean()
        std = series.std()
        current_val = series.iloc[-1]
        if std > 0:
            z_score = (current_val - mean) / std
            trends[col]["z_score"] = round(z_score, 2)
            trends[col]["is_anomalous"] = abs(z_score) > 1.5
        else:
            trends[col]["z_score"] = 0
            trends[col]["is_anomalous"] = False

    return trends


# ---------------------------------------------------------------------------
# LLM briefing generation
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an AI Situational Awareness Agent for the CROSS (Crisis Response & Operational \
Statewide Status) Dashboard. You serve state-level crisis response leaders in Kansas.

Your job is to produce a concise, actionable executive briefing from structured metrics data. \
You answer three questions:
1. What changed? (compared to the prior period)
2. What looks abnormal? (statistical outliers, threshold breaches, anomalous trends)
3. What requires attention? (items needing decisions or escalation)

Guidelines:
- Lead with the most critical items. Bad news first.
- Use specific numbers: counties by name, exact percentages, directional changes.
- Flag counties that entered Critical or Alert status.
- Highlight capacity, staffing, and supply risks.
- Note any positive developments too (improvements, resolved alerts).
- Keep the briefing to 8-15 bullet points. Be concise, not verbose.
- Group bullets under the three questions as headers.
- Start with a one-sentence bold "Bottom Line" assessment immediately after the date, before the three sections.
- Use plain language appropriate for executive leadership, not technical jargon.
- Format output in clean Markdown.
"""


def generate_briefing(
    date_label: str,
    lookback: int,
    current_snapshot: dict,
    prior_snapshot: dict | None,
    changes: dict | None,
    trends: dict,
) -> str:
    """Call Claude API to produce the situational awareness briefing."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit(
            "Error: ANTHROPIC_API_KEY environment variable is not set.\n"
            "Export your API key: export ANTHROPIC_API_KEY=sk-ant-..."
        )

    client = anthropic.Anthropic(api_key=api_key)

    user_content = f"**Briefing Date:** {date_label}\n"
    user_content += f"**Comparison Period:** vs. {lookback} day(s) prior\n\n"

    user_content += "## Current Day Snapshot\n```json\n"
    user_content += json.dumps(current_snapshot, indent=2, default=str)
    user_content += "\n```\n\n"

    if changes:
        user_content += "## Changes vs Prior Period\n```json\n"
        user_content += json.dumps(changes, indent=2, default=str)
        user_content += "\n```\n\n"

    if trends:
        user_content += "## 30-Day Trend Analysis\n```json\n"
        user_content += json.dumps(trends, indent=2, default=str)
        user_content += "\n```\n\n"

    user_content += (
        "Produce the executive situational awareness briefing based on the data above. "
        "Focus on what decision-makers need to know right now."
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    return response.content[0].text


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="CROSS Dashboard AI Situational Awareness Agent"
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target date (YYYY-MM-DD). Defaults to latest date in dataset.",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=1,
        help="Number of days to look back for comparison (default: 1).",
    )
    parser.add_argument(
        "--data-file",
        type=str,
        default=None,
        help="Path to CROSS dataset Excel file.",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print raw metrics JSON instead of generating AI briefing.",
    )
    args = parser.parse_args()

    data_path = Path(args.data_file) if args.data_file else DATA_FILE
    if not data_path.exists():
        sys.exit(f"Data file not found: {data_path}")

    log = (lambda msg: print(msg, file=sys.stderr, flush=True)) if args.raw else (lambda msg: print(msg, flush=True))

    log("Loading CROSS dataset...")
    data = load_data(data_path)

    current_datesk = _resolve_date(data, args.date)
    current_date = _datesk_to_date(current_datesk)
    log(f"Target date: {current_date.date()} (DateSK: {current_datesk})")

    prior_datesk = _prior_datesk(data, current_datesk, args.lookback)
    if prior_datesk:
        log(f"Comparison date: {_datesk_to_date(prior_datesk).date()} ({args.lookback}-day lookback)")
    else:
        log(f"No comparison date available for {args.lookback}-day lookback.")

    log("Computing metrics...")
    current_snapshot = compute_snapshot(data, current_datesk)
    prior_snapshot = compute_snapshot(data, prior_datesk) if prior_datesk else None
    changes = compute_changes(current_snapshot, prior_snapshot) if prior_snapshot else None
    trends = compute_trends(data, current_datesk)

    if args.raw:
        output = {
            "date": str(current_date.date()),
            "snapshot": current_snapshot,
            "changes": changes,
            "trends": trends,
        }
        print(json.dumps(output, indent=2, default=str))
        return

    print("Generating AI briefing...\n", flush=True)
    briefing = generate_briefing(
        date_label=str(current_date.date()),
        lookback=args.lookback,
        current_snapshot=current_snapshot,
        prior_snapshot=prior_snapshot,
        changes=changes,
        trends=trends,
    )

    print("=" * 72)
    print(briefing)
    print("=" * 72)


if __name__ == "__main__":
    main()
