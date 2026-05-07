from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from platforms.base import PlatformAppConfig, PlatformTokenBundle
from platforms.connectors.taobao import TaobaoConnector


def _config() -> PlatformAppConfig:
    return PlatformAppConfig(
        id="app-001",
        company_id="company-001",
        platform_code="taobao",
        app_name="Tally Taobao",
        app_key="app-key",
        app_secret="app-secret",
        app_type="isv",
        auth_base_url="",
        token_url="",
        refresh_url="",
        redirect_uri="https://example.com/callback",
        scopes=[],
        extra={},
        status="active",
        auth_mode="real",
    )


def test_build_auth_url_uses_taobao_oauth_endpoint():
    connector = TaobaoConnector(_config())

    url = connector.build_auth_url(state="state-001")

    assert url.startswith("https://oauth.taobao.com/authorize?")
    assert "response_type=code" in url
    assert "client_id=app-key" in url
    assert "state=state-001" in url


def test_normalize_trade_rows_flattens_child_orders():
    connector = TaobaoConnector(_config())

    rows = connector.normalize_trade_rows(
        trades=[
            {
                "tid": "T1",
                "status": "TRADE_FINISHED",
                "payment": "100.00",
                "total_fee": "120.00",
                "discount_fee": "20.00",
                "post_fee": "0.00",
                "commission_fee": "1.00",
                "alipay_no": "A1",
                "pay_time": "2026-05-06 12:30:00",
                "modified": "2026-05-06 13:00:00",
                "receiver_mobile": "13800000000",
                "orders": {
                    "order": [
                        {
                            "oid": "O1",
                            "status": "TRADE_FINISHED",
                            "refund_status": "NO_REFUND",
                            "payment": "80.00",
                            "total_fee": "90.00",
                            "discount_fee": "10.00",
                            "sku_id": "SKU1",
                            "outer_sku_id": "OUT1",
                            "num": "2",
                        }
                    ]
                },
            }
        ],
        company_id="company-001",
        data_source_id="source-001",
        dataset_id="dataset-001",
        shop_connection_id="shop-001",
        shop_name="A店",
        external_shop_id="tb-shop-001",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["tid"] == "T1"
    assert row["oid"] == "O1"
    assert row["biz_date"] == "2026-05-06"
    assert row["trade_status"] == "TRADE_FINISHED"
    assert row["order_status"] == "TRADE_FINISHED"
    assert row["alipay_no"] == "A1"
    assert row["payment"] == "100.00"
    assert row["order_payment"] == "80.00"
    assert row["payload"]["shop_name"] == "A店"
    assert "receiver_mobile" not in row["payload"]


def test_sync_orders_calls_incremental_method_without_detail_fetch(monkeypatch):
    connector = TaobaoConnector(_config())
    calls: list[dict[str, object]] = []

    def fake_top_request(*, method: str, session: str, params: dict[str, object]) -> dict[str, object]:
        calls.append({"method": method, "session": session, "params": params})
        return {"trades_sold_increment_get_response": {"trades": {"trade": []}, "has_next": False}}

    monkeypatch.setattr(connector, "_top_request", fake_top_request)

    result = connector.fetch_order_lines(
        token_bundle=PlatformTokenBundle(access_token="session-key"),
        mode="incremental",
        window_start="2026-05-06 00:00:00",
        window_end="2026-05-06 02:00:00",
        page_size=100,
        company_id="company-001",
        data_source_id="source-001",
        dataset_id="dataset-001",
        shop_connection_id="shop-001",
        shop_name="A店",
        external_shop_id="tb-shop-001",
    )

    assert result["success"] is True
    assert calls[0]["method"] == "taobao.trades.sold.increment.get"
    assert calls[0]["params"]["fields"]
    assert all(call["method"] != "taobao.trade.fullinfo.get" for call in calls)
    assert all(call["method"] != "taobao.trade.amount.get" for call in calls)
