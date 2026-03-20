"""
Data loading, caching, and filtering for the CROSS Dashboard.
"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

# Path to dataset — relative to project root
DATA_FILE = Path(__file__).parent.parent / "docs" / "KS_CROSS_mock_dataset.xlsx"
GEOJSON_FILE = Path(__file__).parent.parent / "data" / "kansas_counties.geojson"

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

# Fact tables that should be filtered by date/region/county
FACT_TABLES = {"daily_county", "facility_capacity", "inventory", "transfers", "incidents"}


@st.cache_data
def load_data(path: str | None = None) -> dict[str, pd.DataFrame]:
    """Load all sheets from the CROSS dataset into a dict of DataFrames."""
    file_path = Path(path) if path else DATA_FILE
    xls = pd.ExcelFile(file_path)
    data = {}
    for key, sheet in SHEET_NAMES.items():
        data[key] = pd.read_excel(xls, sheet_name=sheet)
    return data


@st.cache_data
def load_geojson(path: str | None = None) -> dict:
    """Load the Kansas counties GeoJSON."""
    file_path = Path(path) if path else GEOJSON_FILE
    with open(file_path) as f:
        return json.load(f)


def get_date_range(data: dict) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return (min_date, max_date) from the date dimension."""
    dates = data["dates"]["Date"].sort_values()
    return dates.iloc[0], dates.iloc[-1]


def get_regions(data: dict) -> list[dict]:
    """Return list of {RegionSK, RegionName} dicts."""
    df = data["regions"].sort_values("RegionName")
    return df[["RegionSK", "RegionName"]].to_dict("records")


def get_counties(data: dict, region_sks: list[int] | None = None) -> list[dict]:
    """Return list of {CountySK, CountyName} dicts, optionally filtered by region."""
    df = data["counties"].sort_values("CountyName")
    if region_sks:
        df = df[df["RegionSK"].isin(region_sks)]
    return df[["CountySK", "CountyName"]].to_dict("records")


def get_incident_types(data: dict) -> list[dict]:
    """Return list of {IncidentTypeSK, IncidentTypeName} dicts."""
    df = data["incident_types"].sort_values("IncidentTypeName")
    return df[["IncidentTypeSK", "IncidentTypeName"]].to_dict("records")


def _date_to_datesk(dt: pd.Timestamp) -> int:
    """Convert a Timestamp to DateSK integer (YYYYMMDD)."""
    return int(dt.strftime("%Y%m%d"))


def filter_data(
    data: dict,
    date_range: tuple[pd.Timestamp, pd.Timestamp] | None = None,
    region_sks: list[int] | None = None,
    county_sks: list[int] | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Return a new data dict with filtered fact tables.
    Dimension tables are passed through unmodified.
    """
    filtered = {}

    # Compute DateSK range if date_range provided
    if date_range:
        start_sk = _date_to_datesk(date_range[0])
        end_sk = _date_to_datesk(date_range[1])
    else:
        start_sk = end_sk = None

    # Get county SKs for selected regions (for tables that only have CountySK, not RegionSK)
    county_sks_from_region = None
    if region_sks:
        county_sks_from_region = set(
            data["counties"][data["counties"]["RegionSK"].isin(region_sks)]["CountySK"].tolist()
        )

    # Combine county filters
    effective_county_sks = None
    if county_sks:
        effective_county_sks = set(county_sks)
        if county_sks_from_region:
            effective_county_sks = effective_county_sks & county_sks_from_region
    elif county_sks_from_region:
        effective_county_sks = county_sks_from_region

    for key, df in data.items():
        if key not in FACT_TABLES:
            filtered[key] = df
            continue

        result = df.copy()

        # Filter by date
        if start_sk is not None and "DateSK" in result.columns:
            result = result[(result["DateSK"] >= start_sk) & (result["DateSK"] <= end_sk)]

        # Filter by county
        if effective_county_sks is not None and "CountySK" in result.columns:
            result = result[result["CountySK"].isin(effective_county_sks)]

        # Filter by region (for tables that have RegionSK directly)
        if region_sks and "RegionSK" in result.columns and "CountySK" not in result.columns:
            result = result[result["RegionSK"].isin(region_sks)]

        filtered[key] = result

    return filtered
