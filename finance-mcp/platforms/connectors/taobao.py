"""淘宝 / 天猫平台 connector。"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from platforms.base import BasePlatformConnector, PlatformShopProfile, PlatformTokenBundle


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
        raise NotImplementedError("淘宝真实换 token 流程待接入真实平台应用参数")

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
