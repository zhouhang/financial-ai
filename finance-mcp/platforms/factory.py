"""平台 connector 工厂。"""

from __future__ import annotations

from platforms.base import BasePlatformConnector, PlatformAppConfig
from platforms.connectors.douyin_shop import DouyinShopConnector
from platforms.connectors.taobao import TaobaoConnector, TmallConnector


def build_connector(app_config: PlatformAppConfig) -> BasePlatformConnector:
    if app_config.platform_code == "taobao":
        return TaobaoConnector(app_config)
    if app_config.platform_code == "tmall":
        return TmallConnector(app_config)
    if app_config.platform_code == "douyin_shop":
        return DouyinShopConnector(app_config)
    raise ValueError(f"暂不支持的平台: {app_config.platform_code}")
