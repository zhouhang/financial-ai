"""平台 connector 抽象。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PlatformAppConfig:
    id: str | None
    company_id: str | None
    platform_code: str
    app_name: str
    app_key: str
    app_secret: str
    app_type: str
    auth_base_url: str
    token_url: str
    refresh_url: str
    redirect_uri: str
    scopes: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    status: str = "active"
    auth_mode: str = "mock"


@dataclass(slots=True)
class PlatformTokenBundle:
    access_token: str
    refresh_token: str = ""
    expires_in: int | None = None
    refresh_expires_in: int | None = None
    scope_text: str = ""
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PlatformShopProfile:
    external_shop_id: str
    external_shop_name: str
    external_seller_id: str = ""
    auth_subject_name: str = ""
    shop_type: str = "normal"
    metadata: dict[str, Any] = field(default_factory=dict)


class BasePlatformConnector(ABC):
    platform_code: str

    def __init__(self, app_config: PlatformAppConfig):
        self.app_config = app_config

    @property
    def is_mock(self) -> bool:
        return self.app_config.auth_mode == "mock"

    @abstractmethod
    def build_auth_url(self, *, state: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def exchange_code_for_token(
        self,
        *,
        code: str,
        auth_session: dict[str, Any] | None = None,
        callback_payload: dict[str, Any] | None = None,
    ) -> PlatformTokenBundle:
        raise NotImplementedError

    @abstractmethod
    def refresh_token(self, *, refresh_token: str) -> PlatformTokenBundle:
        raise NotImplementedError

    @abstractmethod
    def fetch_shop_profile(
        self,
        *,
        token_bundle: PlatformTokenBundle,
        auth_session: dict[str, Any] | None = None,
        callback_payload: dict[str, Any] | None = None,
    ) -> PlatformShopProfile:
        raise NotImplementedError
