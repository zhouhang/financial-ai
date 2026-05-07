"""平台 connector 工厂。"""

from __future__ import annotations

from platforms.base import BasePlatformConnector, PlatformAppConfig
from platforms.connectors.douyin_shop import DouyinShopConnector
from platforms.connectors.taobao import TaobaoConnector


def build_connector(app_config: PlatformAppConfig) -> BasePlatformConnector:
    if app_config.platform_code in {"taobao", "tmall"}:
        return TaobaoConnector(app_config)
    if app_config.platform_code == "douyin_shop":
        return DouyinShopConnector(app_config)
    raise ValueError(f"暂不支持的平台: {app_config.platform_code}")
