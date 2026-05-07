from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from platforms.base import PlatformAppConfig, PlatformTokenBundle
from platforms.connectors.taobao import TaobaoConnector, TmallConnector
from platforms.factory import build_connector


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


def test_real_fetch_shop_profile_uses_token_identity_payload():
    connector = TaobaoConnector(_config())

    profile = connector.fetch_shop_profile(
        token_bundle=PlatformTokenBundle(
            access_token="session-key",
            raw_payload={
                "taobao_user_id": 123456,
                "taobao_user_nick": "旗舰店",
                "seller_id": "seller-001",
            },
        )
    )

    assert profile.external_shop_id == "123456"
    assert profile.external_shop_name == "旗舰店"
    assert profile.external_seller_id == "seller-001"
    assert profile.auth_subject_name == "旗舰店"
    assert profile.metadata["source"] == "oauth_token"


def test_real_token_exchange_redacts_raw_payload_secrets(monkeypatch):
    connector = TaobaoConnector(_config())

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return (
                b'{"access_token":"access-secret","refresh_token":"refresh-secret",'
                b'"session_key":"session-secret","taobao_user_id":"123","taobao_user_nick":"shop"}'
            )

    monkeypatch.setattr("platforms.connectors.taobao.urlopen", lambda *args, **kwargs: FakeResponse())

    token = connector.exchange_code_for_token(code="code-1")

    assert token.access_token == "access-secret"
    assert token.refresh_token == "refresh-secret"
    assert token.raw_payload["access_token"] == "***REDACTED***"
    assert token.raw_payload["refresh_token"] == "***REDACTED***"
    assert token.raw_payload["session_key"] == "***REDACTED***"
    assert token.raw_payload["taobao_user_id"] == "123"


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


def test_normalize_trade_rows_preserves_numeric_zero_values():
    connector = TaobaoConnector(_config())

    rows = connector.normalize_trade_rows(
        trades=[
            {
                "tid": "T0",
                "status": "TRADE_FINISHED",
                "payment": 0,
                "total_fee": 0,
                "discount_fee": 0,
                "post_fee": 0,
                "pay_time": "2026-05-06 12:30:00",
                "orders": {"order": [{"oid": "O0", "payment": 0, "total_fee": 0, "num": 0}]},
            }
        ],
        company_id="company-001",
        data_source_id="source-001",
        dataset_id="dataset-001",
        shop_connection_id="shop-001",
        shop_name="A店",
        external_shop_id="tb-shop-001",
    )

    assert rows[0]["payment"] == "0.00"
    assert rows[0]["order_payment"] == "0.00"
    assert rows[0]["quantity"] == "0"


def test_factory_keeps_tmall_legacy_connector():
    config = _config()
    config.platform_code = "tmall"

    connector = build_connector(config)

    assert isinstance(connector, TmallConnector)
