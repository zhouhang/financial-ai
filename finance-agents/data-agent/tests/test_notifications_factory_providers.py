from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from services.notifications import get_notification_adapter
from services.notifications.feishu_lark import FeishuLarkCliAdapter
from services.notifications.models import NotificationChannelConfig


def test_factory_creates_feishu_adapter():
    cfg = NotificationChannelConfig(company_id="c1", provider="feishu",
                                    client_id="app", client_secret="sec", robot_code="oc_chat")
    adapter = get_notification_adapter(provider="feishu", channel_config=cfg)
    assert isinstance(adapter, FeishuLarkCliAdapter)
    assert adapter._company_id == "c1"
    assert adapter._target_chat == "oc_chat"
    assert adapter._app_id == "app"


def test_factory_wechat_work_still_unsupported():
    # 企微本轮搁置:仍应抛 ValueError(不引入半成品分支)
    cfg = NotificationChannelConfig(company_id="c1", provider="wechat_work")
    with pytest.raises(ValueError):
        get_notification_adapter(provider="wechat_work", channel_config=cfg)


def test_registry_registers_dingtalk_and_feishu():
    from services.notifications.service import create_default_registry
    registry = create_default_registry()
    registry.create("dingtalk_dws")  # 钉钉无回归
    registry.create("feishu")
    with pytest.raises(ValueError):
        registry.create("wechat_work")
