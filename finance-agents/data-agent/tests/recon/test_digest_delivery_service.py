from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RECON_DIR = ROOT / "graphs" / "recon"

sys.path.insert(0, str(ROOT))


def _ensure_package(name: str, path: Path) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module
    return module


_ensure_package("graphs.recon", RECON_DIR)

service = importlib.import_module("graphs.recon.auto_run_service")
models = importlib.import_module("services.notifications.models")


def _ready_finalize_result() -> dict:
    return {
        "success": True,
        "ready_count": 1,
        "results": [
            {
                "status": "ready",
                "subscription": {
                    "id": "sub-001",
                    "company_id": "company-001",
                    "domain": "ecom",
                    "view": "boss",
                    "channel_config_id": "channel-001",
                    "recipient_json": {"user_id": "u1", "display_name": "老板"},
                },
                "digest": {
                    "id": "digest-001",
                    "period_start": "2026-06-05",
                    "structured": {
                        "totals": {
                            "receivable_total": 100,
                            "refund_total": 10,
                            "settled_total": 80,
                            "normal_in_transit_amount": 5,
                            "stuck_amount": 5,
                            "net_deduction_total": 10,
                        }
                    },
                    "narrative": "日报说明",
                },
            }
        ],
    }


def test_compose_finance_digest_message_omits_unavailable_net_deduction_metric() -> None:
    title, content = service._compose_digest_message(
        digest={
            "period_start": "2026-06-05",
            "structured": {
                "totals": {
                    "matched_with_diff_count": 2,
                    "source_only_count": 1,
                    "target_only_count": 0,
                    "normal_in_transit_amount": 5,
                    "refund_total": 10,
                    "stuck_amount": 3,
                    "net_deduction_total": 99,
                }
            },
            "narrative": "日报说明",
        },
        subscription={"view": "finance"},
        detail_url="https://www.tallyai.cn/recon/digests/token/finance",
    )

    assert title == "2026-06-05 对账明细"
    assert "资金归因" in content
    assert "综合扣减" not in content
    assert "¥99" not in content
    assert "查看差异清单/导出底稿" in content


def test_compose_digest_message_drops_refund_and_stuck_metrics() -> None:
    # 日报展示已去掉「退款」「待核查」，发送的消息也必须去掉，两个 view 都不能出现。
    totals = {
        "receivable_total": 100,
        "refund_total": 10,
        "settled_total": 80,
        "normal_in_transit_amount": 5,
        "stuck_amount": 3,
        "matched_with_diff_count": 2,
        "source_only_count": 1,
        "target_only_count": 0,
    }
    digest = {"period_start": "2026-06-05", "structured": {"totals": totals}, "narrative": "日报说明"}

    for view in ("boss", "finance"):
        _title, content = service._compose_digest_message(
            digest=digest,
            subscription={"view": view},
            detail_url="https://www.tallyai.cn/recon/digests/token/x",
        )
        assert "退款" not in content, f"view={view} 消息仍含退款"
        assert "待核查" not in content, f"view={view} 消息仍含待核查"


@pytest.mark.asyncio
async def test_finalize_and_deliver_digest_dry_run_does_not_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_finalize(*args, **kwargs):
        result = _ready_finalize_result()
        result["results"][0]["digest"] = {}
        result["results"][0]["structured"] = {
            "totals": {
                "receivable_total": 100,
                "refund_total": 10,
                "settled_total": 80,
                "normal_in_transit_amount": 5,
                "stuck_amount": 5,
                "net_deduction_total": 10,
            }
        }
        result["results"][0]["narrative"] = "日报说明"
        return result

    monkeypatch.setattr(service, "recon_digest_finalize_daily", fake_finalize)
    monkeypatch.setattr(
        service,
        "get_notification_adapter",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not send")),
    )

    result = await service.finalize_and_deliver_daily_digest(
        auth_token="token",
        company_id="company-001",
        biz_date="2026-06-05",
        view="boss",
        dry_run=True,
    )

    assert result["deliveries"][0]["status"] == "dry_run"
    assert "查看完整明细" in result["deliveries"][0]["content"]
    assert "综合扣减" not in result["deliveries"][0]["content"]


@pytest.mark.asyncio
async def test_finalize_and_deliver_digest_sends_and_records_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAdapter:
        provider = "dingtalk_dws"

        def send_bot_message(self, **kwargs):
            sent_calls.append(kwargs)
            return models.BotMessageResult(
                success=True,
                provider=self.provider,
                message="ok",
                message_id="msg-001",
            )

    sent_calls: list[dict] = []
    delivery_calls: list[dict] = []
    link_calls: list[dict] = []

    async def fake_finalize(*args, **kwargs):
        return _ready_finalize_result()

    async def fake_link(auth_token, payload):
        link_calls.append(payload)
        return {"success": True, "url": "https://www.tallyai.cn/recon/digests/token/boss"}

    async def fake_record(auth_token, payload):
        delivery_calls.append(payload)
        return {"success": True, "delivery": {"status": payload["status"]}}

    monkeypatch.setattr(service, "recon_digest_finalize_daily", fake_finalize)
    monkeypatch.setattr(service, "recon_digest_detail_link_create", fake_link)
    monkeypatch.setattr(service, "recon_digest_delivery_record", fake_record)
    monkeypatch.setattr(
        service,
        "load_company_channel_config_by_id",
        lambda *, channel_id: models.NotificationChannelConfig(
            id=channel_id,
            company_id="company-001",
            provider="dingtalk_dws",
            robot_code="robot-001",
        ),
    )
    monkeypatch.setattr(service, "get_notification_adapter", lambda **kwargs: FakeAdapter())

    result = await service.finalize_and_deliver_daily_digest(
        auth_token="token",
        company_id="company-001",
        biz_date="2026-06-05",
        view="boss",
    )

    assert result["delivered_count"] == 1
    assert sent_calls[0]["to_user_id"] == "u1"
    assert sent_calls[0]["content_type"] == "markdown"
    assert "综合扣减" not in sent_calls[0]["content"]
    assert link_calls[0]["company_id"] == "company-001"
    assert delivery_calls[0]["status"] == "sent"
    assert delivery_calls[0]["message_id"] == "msg-001"
