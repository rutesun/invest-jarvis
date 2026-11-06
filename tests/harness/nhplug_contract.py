"""NH 공개 문서 예제의 경계 계약. 실계좌 관찰을 주장하지 않는다."""

from decimal import Decimal


NUMERIC_FIELDS = {
    "kr_balance": ("rsdl_qty", "itg_bnc_qty", "ny_stl_qty", "phs_pr", "eal_amt", "eal_pls_amt"),
    "us_balance": (
        "cns_bse_bnc_qty",
        "fc_phs_uit_pr",
        "fc_sec_end_pr",
        "fc_eal_amt",
        "krw_eal_amt",
        "fc_eal_pls_amt",
        "krw_eal_pls_amt",
    ),
    "kr_executions": ("itg_orr_no", "tot_cns_qty", "cns_avg_uit_pr", "cns_amt"),
    "us_history": (
        "trd_sno", "trd_qty", "trd_uit_pr", "fc_trd_amt", "krw_trd_amt",
        "trd_bf_bnc_qty", "trd_af_bnc_qty",
    ),
}


def validate_nh_fixture(name: str, body: dict) -> None:
    """fixture loader에서 호출해 숫자·행 종류 등 의미 가정을 고정한다."""
    assert isinstance(body, dict)
    if name == "token":
        assert body["token_type"] == "Bearer"
        assert body["expires_in"] == 86400
        assert body["access_token"] == "TOKEN"
        return
    assert body["rsp_cd"] == ("00000" if name == "accounts" else "00166")
    rows = body["Output_1" if name.endswith("balance") else "Output_0"]
    assert isinstance(rows, list)
    if name == "accounts":
        assert {row["acct_type"] for row in rows} == {"01", "03"}
        assert all(row["acct_no"].startswith("ACCOUNT NUMBER") for row in rows)
        return
    for row in rows:
        assert isinstance(row["iem_cd"], str) and row["iem_cd"]
        for key in NUMERIC_FIELDS[name]:
            assert isinstance(row[key], (int, Decimal)) and not isinstance(row[key], bool)
            assert Decimal(row[key]).is_finite()
    if name == "kr_balance":
        assert {r["tp_cd_nm"] for r in rows} == {"현금", "유통융자"}
        assert all(r["rsdl_qty"] == r["itg_bnc_qty"] + r["ny_stl_qty"] for r in rows)
    elif name == "us_balance":
        assert all(r["cur_cd"] == "USD" and r["fc_sec_trd_nat_cd"] == "200" for r in rows)
    elif name == "kr_executions":
        assert any(r["tot_cns_qty"] == 0 for r in rows)
        assert any(r["tot_cns_qty"] > 0 for r in rows)
    elif name == "us_history":
        assert all(r["act_trd_tp_nm"] == "매수" and r["iem_cd"].endswith(" US") for r in rows)
        assert all(0 < r["trd_qty"] < 1 and len(r["ral_trd_dt"]) == 8 for r in rows)
