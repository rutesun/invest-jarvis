import pytest

from src.providers.kis import KISProvider


@pytest.mark.asyncio
async def test_get_finance_data_passes_div_cls_code(monkeypatch):
    kis = KISProvider("k", "s")

    captured = {}

    async def fake_token():
        from src.providers.kis_models import KISToken

        return KISToken(access_token="t", token_type="Bearer", expires_in=10)

    monkeypatch.setattr(kis, "_get_access_token", fake_token)

    class FakeResp:
        def raise_for_status(self): ...
        def json(self):
            return {"output": [{"stac_yymm": "202503"}]}

    class FakeClient:
        def __init__(self, *a, **k): ...
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a): ...
        async def get(self, url, headers=None, params=None):
            captured["params"] = params
            return FakeResp()

    monkeypatch.setattr("src.providers.kis.httpx.AsyncClient", FakeClient)

    await kis.get_profit_ratio("005930", div_cls_code="1")
    assert captured["params"]["FID_DIV_CLS_CODE"] == "1"

    await kis.get_profit_ratio("005930")  # default
    assert captured["params"]["FID_DIV_CLS_CODE"] == "0"


@pytest.mark.asyncio
async def test_get_growth_ratio_uses_growth_endpoint(monkeypatch):
    kis = KISProvider("k", "s")

    async def fake_token():
        from src.providers.kis_models import KISToken

        return KISToken(access_token="t", token_type="Bearer", expires_in=10)

    monkeypatch.setattr(kis, "_get_access_token", fake_token)

    captured = {}

    class FakeResp:
        def raise_for_status(self): ...
        def json(self):
            return {"output": [{"stac_yymm": "202503"}]}

    class FakeClient:
        def __init__(self, *a, **k): ...
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a): ...
        async def get(self, url, headers=None, params=None):
            captured["url"] = url
            return FakeResp()

    monkeypatch.setattr("src.providers.kis.httpx.AsyncClient", FakeClient)

    await kis.get_growth_ratio("005930", div_cls_code="1")
    assert captured["url"].endswith("/finance/growth-ratio")


@pytest.mark.asyncio
async def test_get_price_history_uses_adjusted_price_by_default(monkeypatch):
    from src.providers.kis import ADJUSTED

    kis = KISProvider("k", "s")

    async def fake_token():
        from src.providers.kis_models import KISToken

        return KISToken(access_token="t", token_type="Bearer", expires_in=10)

    monkeypatch.setattr(kis, "_get_access_token", fake_token)

    seen = []

    class FakeResp:
        def raise_for_status(self): ...
        def json(self):
            return {"output2": []}

    class FakeClient:
        def __init__(self, *a, **k): ...
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a): ...
        async def get(self, url, headers=None, params=None):
            seen.append(params["FID_ORG_ADJ_PRC"])
            return FakeResp()

    monkeypatch.setattr("src.providers.kis.httpx.AsyncClient", FakeClient)

    await kis.get_price_history("005930", period="1mo")
    assert all(v == ADJUSTED for v in seen)
