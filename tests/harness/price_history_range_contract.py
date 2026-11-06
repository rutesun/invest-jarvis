"""Synthetic range response contracts; no captured raw provenance is claimed."""

from datetime import datetime


KIS_RANGE_FIELDS = (
    "stck_bsop_date",
    "stck_oprc",
    "stck_hgpr",
    "stck_lwpr",
    "stck_clpr",
    "acml_vol",
)


def assert_kis_range_response_contract(response: dict) -> None:
    assert isinstance(response.get("output2"), list), "output2 must be a daily-record list"
    for row in response["output2"]:
        assert all(key in row for key in KIS_RANGE_FIELDS), "missing KIS daily OHLCV field"
        datetime.strptime(row["stck_bsop_date"], "%Y%m%d")
        for key in KIS_RANGE_FIELDS[1:]:
            float(row[key])
