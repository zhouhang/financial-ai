"""淘宝 / 天猫平台 connector。"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from platforms.base import BasePlatformConnector, PlatformShopProfile, PlatformTokenBundle

logger = logging.getLogger(__name__)

TAOBAO_ORDER_FIELDS = ",".join(
    [
        "tid",
        "type",
        "status",
        "created",
        "modified",
        "pay_time",
        "end_time",
        "seller_nick",
        "buyer_nick",
        "payment",
        "total_fee",
        "post_fee",
        "discount_fee",
        "adjust_fee",
        "received_payment",
        "commission_fee",
        "alipay_no",
        "orders",
    ]
)
TAOBAO_ROUTER_URL = "https://eco.taobao.com/router/rest"
TAOBAO_TOKEN_URL = "https://oauth.taobao.com/token"
TAOBAO_TZ = timezone(timedelta(hours=8))


def _parse_top_datetime(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TAOBAO_TZ)
    except ValueError:
        return text
    return parsed.isoformat()


def _biz_date_from_trade(trade: dict[str, Any]) -> str:
    for key in ("pay_time", "created", "modified"):
        text = str(trade.get(key) or "").strip()
        if len(text) >= 10:
            return text[:10]
    return datetime.now(TAOBAO_TZ).date().isoformat()


def _money(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        return f"{Decimal(text):.2f}"
    except (InvalidOperation, ValueError):
        return text


def _quantity(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        return str(Decimal(text))
    except (InvalidOperation, ValueError):
        return text


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _coerce_list(value: Any, child_key: str) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        nested = value.get(child_key)
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
        if isinstance(nested, dict):
            return [nested]
    return []


class TaobaoConnector(BasePlatformConnector):
    platform_code = "taobao"

    def _authorize_url(self) -> str:
        return str(
            self.app_config.auth_base_url
            or self.app_config.extra.get("authorize_url")
            or "https://oauth.taobao.com/authorize"
        )

    def build_auth_url(self, *, state: str) -> str:
        if self.is_mock:
            return ""
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.app_config.app_key,
                "redirect_uri": self.app_config.redirect_uri,
                "state": state,
                "view": "web",
            }
        )
        return f"{self._authorize_url()}?{query}"

    def exchange_code_for_token(
        self,
        *,
        code: str,
        auth_session: dict[str, Any] | None = None,
        callback_payload: dict[str, Any] | None = None,
    ) -> PlatformTokenBundle:
        if self.is_mock:
            suffix = str(code or "mock")[-8:]
            return PlatformTokenBundle(
                access_token=f"mock_tb_access_{suffix}",
                refresh_token=f"mock_tb_refresh_{suffix}",
                expires_in=7200,
                refresh_expires_in=30 * 24 * 3600,
                scope_text="item,trade,refund",
                raw_payload={"mode": "mock", "code": code},
            )
        payload = urlencode(
            {
                "grant_type": "authorization_code",
                "client_id": self.app_config.app_key,
                "client_secret": self.app_config.app_secret,
                "code": code,
                "redirect_uri": self.app_config.redirect_uri,
            }
        ).encode("utf-8")
        req = Request(str(self.app_config.token_url or TAOBAO_TOKEN_URL), data=payload, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded;charset=utf-8")
        try:
            with urlopen(req, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.error(f"淘宝换 token 失败: {exc}")
            raise RuntimeError(f"淘宝换 token 失败: {exc}") from exc
        if data.get("error"):
            raise RuntimeError(str(data.get("error_description") or data.get("error")))
        return PlatformTokenBundle(
            access_token=str(data.get("access_token") or data.get("session_key") or ""),
            refresh_token=str(data.get("refresh_token") or ""),
            expires_in=int(data.get("expires_in") or data.get("expire_in") or 0) or None,
            refresh_expires_in=int(data.get("refresh_expires_in") or data.get("re_expires_in") or 0)
            or None,
            scope_text=str(data.get("scope") or ""),
            raw_payload=data,
        )

    def refresh_token(self, *, refresh_token: str) -> PlatformTokenBundle:
        if self.is_mock:
            suffix = str(refresh_token or "mock")[-8:]
            return PlatformTokenBundle(
                access_token=f"mock_tb_access_{suffix}",
                refresh_token=f"mock_tb_refresh_{suffix}",
                expires_in=7200,
                refresh_expires_in=30 * 24 * 3600,
                scope_text="item,trade,refund",
                raw_payload={"mode": "mock", "refresh_token": refresh_token},
            )
        raise NotImplementedError("淘宝真实 refresh token 流程待接入")

    def fetch_shop_profile(
        self,
        *,
        token_bundle: PlatformTokenBundle,
        auth_session: dict[str, Any] | None = None,
        callback_payload: dict[str, Any] | None = None,
    ) -> PlatformShopProfile:
        if self.is_mock:
            payload = callback_payload or {}
            session_id = str((auth_session or {}).get("id") or "")[-6:] or "000001"
            shop_id = str(payload.get("mock_shop_id") or f"tb_shop_{session_id}")
            shop_name = str(payload.get("mock_shop_name") or f"淘宝测试店铺{session_id}")
            seller_id = str(payload.get("mock_seller_id") or f"tb_seller_{session_id}")
            return PlatformShopProfile(
                external_shop_id=shop_id,
                external_shop_name=shop_name,
                external_seller_id=seller_id,
                auth_subject_name=shop_name,
                shop_type=str(payload.get("mock_shop_type") or "normal"),
                metadata={"mode": "mock", "platform": "taobao"},
        )
        raise NotImplementedError("淘宝真实店铺信息查询待接入")

    def _sign_params(self, params: dict[str, Any]) -> str:
        sign_method = str(params.get("sign_method") or "hmac").lower()
        items = sorted(
            (key, value) for key, value in params.items() if key != "sign" and value is not None
        )
        base = "".join(f"{key}{value}" for key, value in items)
        if sign_method == "md5":
            raw = f"{self.app_config.app_secret}{base}{self.app_config.app_secret}".encode("utf-8")
            return hashlib.md5(raw).hexdigest().upper()
        digest = hmac.new(
            self.app_config.app_secret.encode("utf-8"),
            base.encode("utf-8"),
            hashlib.md5,
        )
        return digest.hexdigest().upper()

    def _top_request(self, *, method: str, session: str, params: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "method": method,
            "app_key": self.app_config.app_key,
            "session": session,
            "timestamp": datetime.now(TAOBAO_TZ).strftime("%Y-%m-%d %H:%M:%S"),
            "format": "json",
            "v": "2.0",
            "sign_method": "hmac",
            **params,
        }
        payload["sign"] = self._sign_params(payload)
        body = urlencode(payload).encode("utf-8")
        req = Request(TAOBAO_ROUTER_URL, data=body, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded;charset=utf-8")
        try:
            with urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.error(f"淘宝 TOP 请求失败 method={method}: {exc}")
            raise RuntimeError(f"淘宝 TOP 请求失败: {exc}") from exc
        if "error_response" in data:
            error = data["error_response"]
            raise RuntimeError(str(error.get("sub_msg") or error.get("msg") or error))
        return data

    def normalize_trade_rows(
        self,
        *,
        trades: list[dict[str, Any]],
        company_id: str,
        data_source_id: str,
        dataset_id: str,
        shop_connection_id: str,
        shop_name: str,
        external_shop_id: str,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for trade in trades:
            tid = str(trade.get("tid") or "").strip()
            if not tid:
                continue
            orders = _coerce_list(trade.get("orders"), "order")
            if not orders:
                orders = [{"oid": tid}]
            biz_date = _biz_date_from_trade(trade)
            for order in orders:
                oid = str(order.get("oid") or tid).strip()
                payload = {
                    "company_id": company_id,
                    "data_source_id": data_source_id,
                    "dataset_id": dataset_id,
                    "shop_connection_id": shop_connection_id,
                    "shop_name": shop_name,
                    "platform_code": self.platform_code,
                    "external_shop_id": external_shop_id,
                    "tid": tid,
                    "oid": oid,
                    "biz_date": biz_date,
                    "trade_status": str(trade.get("status") or ""),
                    "order_status": str(order.get("status") or trade.get("status") or ""),
                    "refund_status": str(order.get("refund_status") or ""),
                    "pay_time": _parse_top_datetime(trade.get("pay_time")),
                    "modified": _parse_top_datetime(order.get("modified") or trade.get("modified")),
                    "end_time": _parse_top_datetime(trade.get("end_time")),
                    "alipay_no": str(trade.get("alipay_no") or ""),
                    "payment": _money(_first_present(trade.get("payment"), trade.get("received_payment"))),
                    "order_payment": _money(
                        _first_present(order.get("payment"), order.get("divide_order_fee"))
                    ),
                    "total_fee": _money(trade.get("total_fee")),
                    "order_total_fee": _money(order.get("total_fee")),
                    "discount_fee": _money(trade.get("discount_fee")),
                    "order_discount_fee": _money(
                        _first_present(order.get("discount_fee"), order.get("part_mjz_discount"))
                    ),
                    "post_fee": _money(trade.get("post_fee")),
                    "commission_fee": _money(trade.get("commission_fee")),
                    "sku_id": str(order.get("sku_id") or ""),
                    "outer_sku_id": str(order.get("outer_sku_id") or ""),
                    "outer_iid": str(order.get("outer_iid") or ""),
                    "num_iid": str(order.get("num_iid") or ""),
                    "title": str(order.get("title") or ""),
                    "sku_properties_name": str(order.get("sku_properties_name") or ""),
                    "quantity": _quantity(order.get("num")),
                }
                rows.append({**payload, "payload": payload})
        return rows

    def _extract_trades(self, data: dict[str, Any], response_key: str) -> tuple[list[dict[str, Any]], bool]:
        response = data.get(response_key) if isinstance(data.get(response_key), dict) else {}
        trades_payload = response.get("trades")
        trades = _coerce_list(trades_payload, "trade")
        return trades, bool(response.get("has_next"))

    def fetch_order_lines(
        self,
        *,
        token_bundle: PlatformTokenBundle,
        mode: str,
        window_start: str,
        window_end: str,
        page_size: int,
        company_id: str,
        data_source_id: str,
        dataset_id: str,
        shop_connection_id: str,
        shop_name: str,
        external_shop_id: str,
    ) -> dict[str, Any]:
        normalized_mode = str(mode or "incremental").strip().lower()
        if normalized_mode == "initial":
            method = "taobao.trades.sold.get"
            response_key = "trades_sold_get_response"
            start_key = "start_created"
            end_key = "end_created"
        else:
            method = "taobao.trades.sold.increment.get"
            response_key = "trades_sold_increment_get_response"
            start_key = "start_modified"
            end_key = "end_modified"

        page_no = 1
        all_rows: list[dict[str, Any]] = []
        while True:
            data = self._top_request(
                method=method,
                session=token_bundle.access_token,
                params={
                    "fields": TAOBAO_ORDER_FIELDS,
                    start_key: window_start,
                    end_key: window_end,
                    "page_no": page_no,
                    "page_size": max(1, min(int(page_size or 100), 100)),
                    "use_has_next": "true",
                },
            )
            trades, has_next = self._extract_trades(data, response_key)
            all_rows.extend(
                self.normalize_trade_rows(
                    trades=trades,
                    company_id=company_id,
                    data_source_id=data_source_id,
                    dataset_id=dataset_id,
                    shop_connection_id=shop_connection_id,
                    shop_name=shop_name,
                    external_shop_id=external_shop_id,
                )
            )
            if not has_next:
                break
            page_no += 1
            if page_no > 500:
                raise RuntimeError("淘宝订单分页超过 500 页，请缩小采集窗口")
        return {"success": True, "rows": all_rows, "healthy": True, "page_count": page_no}


class TmallConnector(TaobaoConnector):
    platform_code = "tmall"

    def fetch_shop_profile(
        self,
        *,
        token_bundle: PlatformTokenBundle,
        auth_session: dict[str, Any] | None = None,
        callback_payload: dict[str, Any] | None = None,
    ) -> PlatformShopProfile:
        profile = super().fetch_shop_profile(
            token_bundle=token_bundle,
            auth_session=auth_session,
            callback_payload=callback_payload,
        )
        return PlatformShopProfile(
            external_shop_id=profile.external_shop_id,
            external_shop_name=profile.external_shop_name.replace("淘宝", "天猫"),
            external_seller_id=profile.external_seller_id,
            auth_subject_name=profile.auth_subject_name.replace("淘宝", "天猫"),
            shop_type="flagship",
            metadata={**profile.metadata, "platform": "tmall"},
        )
