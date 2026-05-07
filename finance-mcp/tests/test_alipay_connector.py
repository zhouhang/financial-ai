from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from platforms.base import PlatformAppConfig
from platforms.connectors.alipay import AlipayConnector, build_alipay_row_key
from platforms.factory import build_connector


def _config() -> PlatformAppConfig:
    return PlatformAppConfig(
        id="app-row-id",
        company_id="00000000-0000-0000-0000-00000000dd01",
        platform_code="alipay",
        app_name="支付宝",
        app_key="2021006152656574",
        app_secret="-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----",
        app_type="isv",
        auth_base_url="https://openauth.alipay.com/oauth2/appToAppAuth.htm",
        token_url="https://openapi.alipay.com/gateway.do",
        refresh_url="https://openapi.alipay.com/gateway.do",
        redirect_uri="https://tally.example.com/api/platform-auth/callback/alipay",
        extra={
            "app_public_cert": "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----",
            "alipay_public_cert": "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----",
            "alipay_root_cert": "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----",
            "mode": "real",
        },
        auth_mode="real",
    )


def test_build_connector_returns_alipay_connector():
    assert isinstance(build_connector(_config()), AlipayConnector)


def test_build_auth_url_uses_app_to_app_auth_endpoint():
    connector = AlipayConnector(_config())

    auth_url = connector.build_auth_url(state="state-123")

    assert auth_url.startswith("https://openauth.alipay.com/oauth2/appToAppAuth.htm?")
    assert "app_id=2021006152656574" in auth_url
    assert (
        "redirect_uri=https%3A%2F%2Ftally.example.com%2Fapi%2Fplatform-auth%2Fcallback%2Falipay"
        in auth_url
    )
    assert "state=state-123" in auth_url


def test_token_response_maps_app_auth_fields():
    connector = AlipayConnector(_config())

    bundle = connector._token_bundle_from_response(
        {
            "alipay_open_auth_token_app_response": {
                "app_auth_token": "merchant-token",
                "app_refresh_token": "merchant-refresh",
                "expires_in": 31536000,
                "re_expires_in": 32140800,
                "auth_app_id": "2021000000000001",
                "user_id": "2088123412341234",
            }
        }
    )

    assert bundle.access_token == "merchant-token"
    assert bundle.refresh_token == "merchant-refresh"
    assert bundle.expires_in == 31536000
    assert bundle.refresh_expires_in == 32140800
    assert bundle.raw_payload["auth_app_id"] == "2021000000000001"
    assert bundle.raw_payload["user_id"] == "2088123412341234"
    assert bundle.raw_payload["app_auth_token"] == "***REDACTED***"
    assert bundle.raw_payload["app_refresh_token"] == "***REDACTED***"


def test_refresh_response_maps_refreshed_app_auth_fields():
    connector = AlipayConnector(_config())

    bundle = connector._token_bundle_from_response(
        {
            "alipay_open_auth_token_app_response": {
                "app_auth_token": "new-token",
                "app_refresh_token": "new-refresh",
                "expires_in": "31536000",
                "re_expires_in": "32140800",
            }
        }
    )

    assert bundle.access_token == "new-token"
    assert bundle.refresh_token == "new-refresh"
    assert bundle.expires_in == 31536000
    assert bundle.refresh_expires_in == 32140800


def test_exchange_code_for_token_prefers_app_auth_code_from_callback(monkeypatch):
    connector = AlipayConnector(_config())
    captured = {}

    def fake_post_alipay_request(*, method, app_auth_token, biz_content):
        captured["method"] = method
        captured["app_auth_token"] = app_auth_token
        captured["biz_content"] = biz_content
        return {
            "alipay_open_auth_token_app_response": {
                "app_auth_token": "merchant-token",
                "app_refresh_token": "merchant-refresh",
            }
        }

    monkeypatch.setattr(connector, "_post_alipay_request", fake_post_alipay_request)

    connector.exchange_code_for_token(
        code="",
        callback_payload={"app_auth_code": "real-app-auth-code"},
    )

    assert captured["method"] == "alipay.open.auth.token.app"
    assert captured["app_auth_token"] == ""
    assert captured["biz_content"]["grant_type"] == "authorization_code"
    assert captured["biz_content"]["code"] == "real-app-auth-code"


def test_fetch_shop_profile_uses_merchant_display_name_from_session():
    connector = AlipayConnector(_config())
    bundle = connector._token_bundle_from_response(
        {
            "alipay_open_auth_token_app_response": {
                "app_auth_token": "merchant-token",
                "app_refresh_token": "merchant-refresh",
                "auth_app_id": "2021000000000001",
                "user_id": "2088123412341234",
            }
        }
    )

    profile = connector.fetch_shop_profile(
        token_bundle=bundle,
        auth_session={"extra": {"merchant_display_name": "福游网络"}},
    )

    assert profile.external_shop_id == "2088123412341234"
    assert profile.external_shop_name == "福游网络"
    assert profile.external_seller_id == "2021000000000001"
    assert profile.shop_type == "merchant"


def test_query_bill_download_url_builds_signed_request(monkeypatch):
    connector = AlipayConnector(_config())
    captured = {}

    monkeypatch.setattr(connector, "_sign_params", lambda params: "fake-sign")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "alipay_data_dataservice_bill_downloadurl_query_response": {
                    "bill_download_url": "https://download.example.com/bill.zip"
                }
            }

    def fake_post(url, data, timeout):
        captured["url"] = url
        captured["data"] = data
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("platforms.connectors.alipay.requests.post", fake_post)

    download_url = connector.query_bill_download_url(
        app_auth_token="merchant-token",
        bill_type="signcustomer",
        bill_date="2026-05-06",
    )

    assert download_url == "https://download.example.com/bill.zip"
    assert captured["url"] == "https://openapi.alipay.com/gateway.do"
    assert captured["data"]["method"] == "alipay.data.dataservice.bill.downloadurl.query"
    assert captured["data"]["app_auth_token"] == "merchant-token"
    assert captured["data"]["sign"] == "fake-sign"
    assert "signcustomer" in captured["data"]["biz_content"]


def test_parse_bill_zip_rows_adds_metadata_and_row_key():
    connector = AlipayConnector(_config())
    csv_text = "商户订单号,支付宝交易号,金额\nM-1,A-1,10.00\n"
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as zf:
        zf.writestr("2088_20260506.csv", csv_text.encode("gbk"))

    rows = connector.parse_bill_file(
        content=raw.getvalue(),
        file_name="bill.zip",
        bill_type="trade",
        bill_date="2026-05-06",
        merchant_display_name="福游网络",
        shop_connection_id="shop-1",
    )

    assert rows[0]["bill_type"] == "trade"
    assert rows[0]["bill_date"] == "2026-05-06"
    assert rows[0]["merchant_order_no"] == "M-1"
    assert rows[0]["alipay_trade_no"] == "A-1"
    assert len(rows[0]["source_row_key"]) == 64
    assert rows[0]["source_row_key"] != "M-1"
    assert rows[0]["raw"]["金额"] == "10.00"


def test_download_bill_file_sanitizes_http_error_url(monkeypatch):
    connector = AlipayConnector(_config())

    class FakeResponse:
        content = b""

        def raise_for_status(self):
            raise requests.HTTPError(
                "403 Client Error: Forbidden for url: https://download.example.com/secret.zip"
            )

    monkeypatch.setattr(
        "platforms.connectors.alipay.requests.get",
        lambda url, timeout: FakeResponse(),
    )

    with pytest.raises(RuntimeError) as exc_info:
        connector.download_bill_file(
            bill_download_url="https://download.example.com/secret.zip",
        )

    message = str(exc_info.value)
    assert "支付宝账单文件下载失败" in message
    assert "download.example.com" not in message
    assert "secret.zip" not in message


def test_download_bill_file_rejects_non_https_url(monkeypatch):
    connector = AlipayConnector(_config())

    def fail_get(url, timeout):
        raise AssertionError("requests.get should not be called for non-HTTPS URLs")

    monkeypatch.setattr("platforms.connectors.alipay.requests.get", fail_get)

    with pytest.raises(RuntimeError) as exc_info:
        connector.download_bill_file(bill_download_url="http://download.example.com/bill.zip")

    message = str(exc_info.value)
    assert message == "支付宝账单文件下载失败"
    assert "download.example.com" not in message
    assert "bill.zip" not in message


def test_parse_csv_skips_preamble_before_header():
    connector = AlipayConnector(_config())
    content = (
        "支付宝业务明细查询\n"
        "账号,2088123412341234\n"
        "商户订单号,支付宝交易号,金额\n"
        "M-1,A-1,10.00\n"
    ).encode("utf-8")

    rows = connector.parse_bill_file(
        content=content,
        file_name="bill.csv",
        bill_type="trade",
        bill_date="2026-05-06",
        merchant_display_name="福游网络",
        shop_connection_id="shop-1",
    )

    assert len(rows) == 1
    assert rows[0]["merchant_order_no"] == "M-1"
    assert rows[0]["alipay_trade_no"] == "A-1"
    assert rows[0]["raw"]["金额"] == "10.00"


def test_parse_direct_csv_rows_adds_business_order_no():
    connector = AlipayConnector(_config())
    content = "业务订单号,支付宝流水号,金额\nB-1,F-1,12.00\n".encode("utf-8-sig")

    rows = connector.parse_bill_file(
        content=content,
        file_name="bill.csv",
        bill_type="signcustomer",
        bill_date="2026-05-06",
        merchant_display_name="福游网络",
        shop_connection_id="shop-1",
    )

    assert rows[0]["business_order_no"] == "B-1"
    assert rows[0]["alipay_trade_no"] == "F-1"
    assert rows[0]["source_file_name"] == "bill.csv"
    assert rows[0]["source_row_number"] == 2
    assert len(rows[0]["source_row_key"]) == 64
    assert rows[0]["source_row_key"] != "B-1"


def test_build_alipay_row_key_is_hash_even_with_business_identifier():
    row_key = build_alipay_row_key(
        bill_type="signcustomer",
        bill_date="2026-05-06",
        source_file_name="bill.csv",
        source_row_number=3,
        row={"业务订单号": "B-1", "金额": "10.00"},
    )

    assert len(row_key) == 64
    assert row_key != "B-1"


def test_sign_params_returns_base64_signature_for_pem_private_key():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    config = _config()
    config.app_secret = private_pem
    connector = AlipayConnector(config)

    signature = connector._sign_params(
        {
            "app_id": config.app_key,
            "method": "alipay.open.auth.token.app",
            "charset": "utf-8",
            "biz_content": json.dumps({"code": "abc"}, separators=(",", ":")),
        }
    )

    assert signature
    assert isinstance(signature, str)
    assert set(signature) <= set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
    )


def test_gateway_response_signature_malformed_signature_raises_sanitized_error():
    connector = AlipayConnector(_config())

    with pytest.raises(RuntimeError) as exc_info:
        connector._verify_gateway_response_signature(
            {
                "alipay_open_auth_token_app_response": {"app_auth_token": "merchant-token"},
                "sign": "not-base64",
            }
        )

    message = str(exc_info.value)
    assert message == "支付宝网关响应验签失败"
    assert "not-base64" not in message


def test_gateway_request_error_sanitizes_url(monkeypatch):
    connector = AlipayConnector(_config())
    monkeypatch.setattr(connector, "_sign_params", lambda params: "fake-sign")

    def fake_post(url, data, timeout):
        raise requests.HTTPError(
            "403 Client Error: Forbidden for url: https://openapi.alipay.com/gateway.do?secret=1"
        )

    monkeypatch.setattr("platforms.connectors.alipay.requests.post", fake_post)

    with pytest.raises(RuntimeError) as exc_info:
        connector.query_bill_download_url(
            app_auth_token="merchant-token",
            bill_type="signcustomer",
            bill_date="2026-05-06",
        )

    message = str(exc_info.value)
    assert "支付宝网关请求失败" in message
    assert "openapi.alipay.com" not in message
    assert "gateway.do" not in message
    assert "secret=1" not in message
