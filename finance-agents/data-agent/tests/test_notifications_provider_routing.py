from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.notifications import get_notification_adapter
from services.notifications.dingtalk_dws import DingTalkDwsAdapter
from services.notifications.feishu_lark import FeishuLarkCliAdapter
from services.notifications.models import NotificationChannelConfig


def test_feishu_provider_driven_by_channel_config():
    """模拟 recon: provider 来自 channel_config.provider。"""
    cfg = NotificationChannelConfig(company_id="c1", provider="feishu",
                                    client_id="id", client_secret="sec", robot_code="oc_target")
    adapter = get_notification_adapter(provider=cfg.provider, channel_config=cfg)
    assert isinstance(adapter, FeishuLarkCliAdapter)
    assert adapter.provider == "feishu"


def test_dingtalk_routing_unchanged():
    """钉钉无回归:同一工厂入口仍返回钉钉适配器。"""
    cfg = NotificationChannelConfig(company_id="c1", provider="dingtalk_dws",
                                    client_id="cid", client_secret="sec", robot_code="robot")
    adapter = get_notification_adapter(provider=cfg.provider, channel_config=cfg)
    assert isinstance(adapter, DingTalkDwsAdapter)
    assert adapter.provider == "dingtalk_dws"
