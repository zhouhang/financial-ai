from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RECON_DIR = ROOT / "graphs" / "recon"
AUTO_SCHEME_DIR = RECON_DIR / "auto_scheme_run"

sys.path.insert(0, str(ROOT))

from services.notifications.models import (  # noqa: E402
    BotMessageResult,
    NotificationChannelConfig,
    NotificationUser,
    ReminderResult,
    TodoRecord,
    TodoResult,
    UserResolveResult,
    UnifiedTodoStatus,
)


def _ensure_package(name: str, path: Path) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module
    return module


_ensure_package("graphs.recon", RECON_DIR)
auto_scheme_package = _ensure_package("graphs.recon.auto_scheme_run", AUTO_SCHEME_DIR)


async def _unused_run_auto_scheme_run_graph(*args: object, **kwargs: object) -> dict[str, object]:
    raise AssertionError("run_auto_scheme_run_graph should not be called in this test module")


auto_scheme_package.run_auto_scheme_run_graph = _unused_run_auto_scheme_run_graph

nodes = importlib.import_module("graphs.recon.auto_scheme_run.nodes")
routers = importlib.import_module("graphs.recon.auto_scheme_run.routers")
auto_run_service = importlib.import_module("graphs.recon.auto_run_service")


def _channel_config() -> NotificationChannelConfig:
    return NotificationChannelConfig(
        id="channel-001",
        company_id="company-001",
        provider="dingtalk_dws",
        channel_code="default",
        name="默认钉钉",
        robot_code="robot",
        is_default=True,
        is_enabled=True,
    )


class _BatchNotifyAdapter:
    provider = "dingtalk_dws"

    def __init__(self) -> None:
        self.reminder_calls: list[dict[str, object]] = []
        self.bot_calls: list[dict[str, object]] = []

    def resolve_user(self, *, user_id: str = "", mobile: str = "", keyword: str = "") -> UserResolveResult:
        user = NotificationUser(
            user_id=user_id or "ding-user-001",
            display_name=keyword or "周行",
            mobile=mobile,
        )
        return UserResolveResult(
            success=True,
            provider=self.provider,
            users=[user],
            resolved_user=user,
        )

    def send_bot_message(
        self,
        *,
        content: str,
        to_user_id: str,
        content_type: str = "text",
        title: str = "",
        bot_id: str = "",
        conversation_id: str = "",
    ) -> BotMessageResult:
        self.bot_calls.append(
            {
                "content": content,
                "to_user_id": to_user_id,
                "content_type": content_type,
                "title": title,
                "bot_id": bot_id,
                "conversation_id": conversation_id,
            }
        )
        return BotMessageResult(
            success=True,
            provider=self.provider,
            message_id=f"msg-{len(self.bot_calls)}",
            receiver_user_id=to_user_id,
        )

    def send_reminder(
        self,
        *,
        title: str,
        content: str,
        todo_title: str = "",
        assignee_user_id: str = "",
        mobile: str = "",
        keyword: str = "",
        due_time: str = "",
        source_id: str = "",
        operator_user_id: str = "",
    ) -> ReminderResult:
        self.reminder_calls.append(
            {
                "title": title,
                "content": content,
                "todo_title": todo_title,
                "assignee_user_id": assignee_user_id,
                "mobile": mobile,
                "keyword": keyword,
                "due_time": due_time,
                "source_id": source_id,
                "operator_user_id": operator_user_id,
            }
        )
        todo = TodoRecord(
            todo_id=f"todo-{len(self.reminder_calls)}",
            title=todo_title,
            assignee_user_id=assignee_user_id,
            status=UnifiedTodoStatus.OPEN,
        )
        return ReminderResult(
            success=True,
            provider=self.provider,
            bot_result=BotMessageResult(
                success=True,
                provider=self.provider,
                message_id=f"msg-reminder-{len(self.reminder_calls)}",
                receiver_user_id=assignee_user_id,
            ),
            todo_result=TodoResult(success=True, provider=self.provider, todo=todo),
            assignee_user_id=assignee_user_id,
        )


def test_plan_dataset_binding_uses_raw_date_field_from_scheme_meta() -> None:
    binding = {
        "role_code": "right_1",
        "data_source_id": "source-001",
        "resource_key": "public.ods_yxst_fp_orders_di_o",
        "filter_config": {"query": {"display_date_field": "订单更新时间"}},
        "mapping_config": {
            "table_name": "public.ods_yxst_fp_orders_di_o",
            "dataset_source_type": "collection_records",
        },
    }
    scheme_meta = {
        "dataset_bindings": {
            "right": [
                {
                    "dataset_id": "dataset-right",
                    "data_source_id": "source-001",
                    "resource_key": "public.ods_yxst_fp_orders_di_o",
                }
            ]
        },
        "right_output_fields": [
            {
                "outputName": "订单更新时间",
                "sourceField": "updated_at",
                "semanticRole": "time_field",
                "sourceDatasetId": "dataset-right",
            }
        ],
    }

    normalized = nodes._build_plan_binding_from_dataset_binding(
        binding=binding,
        left_time_semantic="",
        right_time_semantic="订单更新时间",
        scheme_meta=scheme_meta,
    )

    assert normalized is not None
    assert normalized["query"]["date_field"] == "updated_at"
    assert normalized["query"]["display_date_field"] == "订单更新时间"


def test_check_dataset_ready_schedule_collects_before_recon(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_collect(auth_token: str, source_id: str, **kwargs: object) -> dict[str, object]:
        calls.append(("collect", {"auth_token": auth_token, "source_id": source_id, **kwargs}))
        return {"success": True, "job": {"id": "job-001"}}

    async def fake_list(auth_token: str, source_id: str, **kwargs: object) -> dict[str, object]:
        calls.append(("list", {"auth_token": auth_token, "source_id": source_id, **kwargs}))
        return {
            "success": True,
            "dataset_id": "dataset-001",
            "resource_key": "orders",
            "record_count": 2,
            "records": [{"item_key": "1"}, {"item_key": "2"}],
        }

    monkeypatch.setattr(nodes, "data_source_trigger_dataset_collection", fake_collect)
    monkeypatch.setattr(nodes, "data_source_list_collection_records", fake_list)

    state = {
        "auth_token": "token",
        "recon_ctx": {
            "biz_date": "2026-04-25",
            "run_context": {"trigger_type": "schedule"},
            "plan_input_bindings": [
                {
                    "data_source_id": "source-001",
                    "dataset_id": "dataset-001",
                    "table_name": "orders_ready",
                    "resource_key": "orders",
                    "required": True,
                }
            ],
        },
    }

    result = asyncio.run(nodes.check_dataset_ready_node(state))
    bind_result = nodes.bind_ready_collection_node(result)
    recon_ctx = bind_result["recon_ctx"]

    assert [item[0] for item in calls] == ["collect", "list"]
    assert calls[0][1]["trigger_mode"] == "scheduled"
    assert recon_ctx["missing_bindings"] == []
    assert recon_ctx["ready_collections"][0]["collection_records"]["record_count"] == 2
    assert recon_ctx["collection_attempts"][0]["success"] is True
    assert recon_ctx["collection_attempts"][0]["error"] == ""
    assert recon_ctx["source_collection_json"]["collection_attempts"][0]["success"] is True


def test_check_dataset_ready_collection_failure_blocks_stale_records(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_collect(auth_token: str, source_id: str, **kwargs: object) -> dict[str, object]:
        calls.append("collect")
        return {"success": False, "error": "upstream timeout"}

    async def fake_list(auth_token: str, source_id: str, **kwargs: object) -> dict[str, object]:
        calls.append("list")
        return {
            "success": True,
            "dataset_id": "dataset-001",
            "resource_key": "orders",
            "record_count": 9,
            "records": [{"item_key": "stale"}],
        }

    monkeypatch.setattr(nodes, "data_source_trigger_dataset_collection", fake_collect)
    monkeypatch.setattr(nodes, "data_source_list_collection_records", fake_list)

    state = {
        "auth_token": "token",
        "recon_ctx": {
            "biz_date": "2026-04-25",
            "run_context": {"trigger_type": "schedule"},
            "plan_input_bindings": [
                {
                    "data_source_id": "source-001",
                    "dataset_id": "dataset-001",
                    "table_name": "orders_ready",
                    "resource_key": "orders",
                    "required": True,
                }
            ],
        },
    }

    result = asyncio.run(nodes.check_dataset_ready_node(state))
    recon_ctx = result["recon_ctx"]

    assert calls == ["collect"]
    assert recon_ctx["ready_collections"] == []
    assert recon_ctx["missing_bindings"][0]["error"] == "先同步失败：upstream timeout"


def test_check_dataset_ready_rerun_queues_browser_verification_when_binding_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_collect(auth_token: str, source_id: str, **kwargs: object) -> dict[str, object]:
        calls.append(("collect", {"auth_token": auth_token, "source_id": source_id, **kwargs}))
        return {
            "success": False,
            "queued": False,
            "failure_type": "browser_binding_unavailable",
            "collection_driver": "browser_playbook_remote",
            "error_code": "RISK_VERIFICATION",
            "error": "浏览器采集店铺状态不可用: profile_status=risk_blocked",
        }

    async def fake_retry_verification(
        auth_token: str,
        source_id: str,
        **kwargs: object,
    ) -> dict[str, object]:
        calls.append(("retry_verification", {"auth_token": auth_token, "source_id": source_id, **kwargs}))
        return {
            "success": True,
            "status": "verification_pending",
            "verification_sync_job_id": "verification-job-001",
            "verification_biz_date": "2026-04-25",
            "message": "浏览器任务已重新下发到采集机，请等待任务状态更新",
        }

    async def stale_list(auth_token: str, source_id: str, **kwargs: object) -> dict[str, object]:
        raise AssertionError("browser unavailable rerun must not read stale records")

    monkeypatch.setattr(nodes, "data_source_trigger_dataset_collection", fake_collect)
    monkeypatch.setattr(nodes, "data_source_retry_browser_playbook_verification", fake_retry_verification)
    monkeypatch.setattr(nodes, "data_source_list_collection_records", stale_list)

    state = {
        "auth_token": "token",
        "recon_ctx": {
            "biz_date": "2026-04-25",
            "run_context": {"trigger_type": "rerun"},
            "plan_input_bindings": [
                {
                    "data_source_id": "source-browser",
                    "dataset_id": "dataset-browser",
                    "table_name": "browser_orders_ready",
                    "resource_key": "browser_orders",
                    "required": True,
                    "collection_driver": "browser_playbook_remote",
                    "dataset_source_type": "browser_collection_records",
                }
            ],
        },
    }

    ready_result = asyncio.run(nodes.check_dataset_ready_node(state))
    validated_result = nodes.validate_dataset_completeness_node(ready_result)
    recon_ctx = validated_result["recon_ctx"]

    assert [item[0] for item in calls] == ["collect", "retry_verification"]
    assert calls[0][1]["trigger_mode"] == "retry"
    assert calls[1][1]["verification_biz_date"] == "2026-04-25"
    assert calls[1][1]["dataset_id"] == "dataset-browser"
    assert recon_ctx["waiting_data"] is True
    assert recon_ctx["failed_stage"] == "data_waiting"
    assert recon_ctx["waiting_datasets"] == [
        {
            "data_source_id": "source-browser",
            "dataset_id": "dataset-browser",
            "resource_key": "browser_orders",
            "biz_date": "2026-04-25",
        }
    ]
    assert recon_ctx["collection_job_ids"] == ["verification-job-001"]
    assert recon_ctx["missing_bindings"][0]["collection_job_id"] == "verification-job-001"
    assert "浏览器采集店铺状态不可用" not in recon_ctx["failed_reason"]


def test_check_dataset_ready_skips_keyset_lookup_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_collect(auth_token: str, source_id: str, **kwargs: object) -> dict[str, object]:
        calls.append(("collect", {"auth_token": auth_token, "source_id": source_id, **kwargs}))
        return {"success": True, "job": {"id": "job-lookup"}}

    async def fake_list(auth_token: str, source_id: str, **kwargs: object) -> dict[str, object]:
        calls.append(("list", {"auth_token": auth_token, "source_id": source_id, **kwargs}))
        return {
            "success": True,
            "dataset_id": "dataset-lookup",
            "resource_key": "lookup_orders",
            "record_count": 3,
            "records": [{"item_key": "1"}],
        }

    monkeypatch.setattr(nodes, "data_source_trigger_dataset_collection", fake_collect)
    monkeypatch.setattr(nodes, "data_source_list_collection_records", fake_list)

    state = {
        "auth_token": "token",
        "recon_ctx": {
            "biz_date": "2026-04-25",
            "run_context": {"trigger_type": "manual"},
            "plan_input_bindings": [
                {
                    "data_source_id": "source-001",
                    "dataset_id": "dataset-lookup",
                    "table_name": "lookup_orders",
                    "resource_key": "lookup_orders",
                    "required": True,
                    "input_plan_read_mode": "by_key_set",
                    "input_plan_apply_biz_date_filter": False,
                }
            ],
        },
    }

    result = asyncio.run(nodes.check_dataset_ready_node(state))
    recon_ctx = result["recon_ctx"]

    assert [item[0] for item in calls] == ["list"]
    assert calls[0][1]["biz_date"] == ""
    assert recon_ctx["missing_bindings"] == []
    assert recon_ctx["ready_collections"][0]["collection_records"]["record_count"] == 3


def test_check_dataset_ready_skips_manual_seed_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_collect(auth_token: str, source_id: str, **kwargs: object) -> dict[str, object]:
        calls.append("collect")
        return {"success": False, "error": "should not collect"}

    async def fake_list(auth_token: str, source_id: str, **kwargs: object) -> dict[str, object]:
        calls.append("list")
        return {
            "success": True,
            "dataset_id": "dataset-seed",
            "resource_key": "seed_orders",
            "record_count": 2,
            "records": [{"item_key": "1"}],
        }

    monkeypatch.setattr(nodes, "data_source_trigger_dataset_collection", fake_collect)
    monkeypatch.setattr(nodes, "data_source_list_collection_records", fake_list)

    state = {
        "auth_token": "token",
        "recon_ctx": {
            "biz_date": "2026-04-25",
            "run_context": {"trigger_type": "manual"},
            "plan_input_bindings": [
                {
                    "data_source_id": "source-001",
                    "dataset_id": "dataset-seed",
                    "table_name": "seed_orders",
                    "resource_key": "seed_orders",
                    "required": True,
                    "dataset_extract_config": {"mode": "manual_seed"},
                }
            ],
        },
    }

    result = asyncio.run(nodes.check_dataset_ready_node(state))
    recon_ctx = result["recon_ctx"]

    assert calls == ["list"]
    assert recon_ctx["missing_bindings"] == []


def test_auto_scheme_graph_persists_recon_result_without_source_only_suppression_node() -> None:
    graph = routers.build_auto_scheme_run_graph()

    assert "apply_alipay_fund_source_only_suppression_node" not in graph.nodes
    assert ("scheme_execution_graph", "persist_auto_run_node") in graph.edges


def test_summary_notification_uses_recon_counts_without_alipay_suppression() -> None:
    ctx = {
        "run_plan": {"plan_name": "泰斯支付宝对账"},
        "run_context": {"biz_date": "2026-04-30"},
        "recon_result_summary_json": {
            "matched_exact": 136,
            "source_only": 69,
            "target_only": 0,
            "matched_with_diff": 0,
        },
        "source_collection_json": {
            "collections": [
                {"binding": {"role_code": "left_1", "dataset_name": "交易订单明细表"}},
                {"binding": {"role_code": "right_1", "dataset_name": "支付宝资金账单 - 测试商户"}},
            ]
        },
    }

    _, content = nodes._compose_run_summary_notification_text(
        ctx=ctx,
        anomalies=[],
        threshold=20,
        explosion=False,
        detail_url="https://dev.tallyai.cn/recon/runs/run-001/exceptions",
    )

    assert "待处理差异：\n69 条" in content
    assert "仅 交易订单明细表 存在（支付宝资金账单 - 测试商户 缺失）：69 条" in content
    assert "非支付宝支付" not in content


def test_runtime_summary_written_to_execution_run_artifacts() -> None:
    ctx = {
        "biz_date": "2026-05-20",
        "run_context": {
            "queue_job_id": "queue-001",
            "queue_started_at": "2026-05-21T04:00:01+08:00",
            "queue_finished_at": "2026-05-21T04:01:15+08:00",
        },
        "source_collection_json": {
            "collections": [
                {
                    "binding": {"side": "left", "dataset_name": "交易订单明细表"},
                    "collection_records": {"record_count": 205},
                    "job": {"metrics": {"collection_timing": {"total_seconds": 38.42}}},
                },
                {
                    "binding": {"side": "right", "dataset_name": "支付宝资金账单"},
                    "collection_records": {"record_count": 136},
                    "job": {"metrics": {"collection_timing": {"total_seconds": 31.06}}},
                },
            ]
        },
        "recon_observation": {
            "summary": {"matched_exact": 136, "matched_with_diff": 0, "source_only": 69, "target_only": 0},
            "artifacts": {},
            "anomaly_items": [],
        },
        "runtime_metrics": {
            "preparation": [
                {"side": "left", "target_table": "left_recon_ready", "row_count": 205, "duration_seconds": 4.18},
                {"side": "right", "target_table": "right_recon_ready", "row_count": 136, "duration_seconds": 3.77},
            ],
            "reconciliation": {"duration_seconds": 2.24},
        },
    }

    summary = nodes._build_runtime_summary(ctx)  # noqa: SLF001

    assert summary["biz_date"] == "2026-05-20"
    assert summary["queue"]["job_id"] == "queue-001"
    assert summary["queue"]["duration_seconds"] == 74
    assert summary["collections"][0]["business_name"] == "交易订单明细表"
    assert summary["collections"][0]["row_count"] == 205
    assert summary["collections"][0]["duration_seconds"] == 38.42
    assert summary["preparation"][1]["business_name"] == "支付宝资金账单"
    assert summary["preparation"][1]["row_count"] == 136
    assert summary["reconciliation"]["duration_seconds"] == 2.24


def test_runtime_summary_prefers_collection_job_metrics_over_sample_counts() -> None:
    ctx = {
        "biz_date": "2026-05-20",
        "source_collection_json": {
            "collections": [
                {
                    "binding": {"role_code": "left_1", "dataset_name": "交易订单明细表"},
                    "collection_records": {"record_count": 1},
                },
                {
                    "binding": {"role_code": "right_1", "dataset_name": "支付宝资金账单"},
                    "collection_records": {"record_count": 0},
                },
            ],
            "collection_attempts": [
                {
                    "binding": {"role_code": "left_1", "dataset_name": "交易订单明细表"},
                    "job": {
                        "metrics": {
                            "row_count": 91852,
                            "collection_timing": {"total_seconds": 64.816416},
                        }
                    },
                },
                {
                    "binding": {"role_code": "right_1", "dataset_name": "支付宝资金账单"},
                    "job": {
                        "metrics": {
                            "row_count": 329,
                            "collection_timing": {"total_seconds": 1.249467},
                        }
                    },
                },
            ],
        },
        "runtime_metrics": {},
    }

    summary = nodes._build_runtime_summary(ctx)  # noqa: SLF001

    assert summary["collections"][0]["row_count"] == 91852
    assert summary["collections"][0]["duration_seconds"] == 64.816416
    assert summary["collections"][1]["row_count"] == 329
    assert summary["collections"][1]["duration_seconds"] == 1.249467


def test_runtime_summary_uses_browser_checkpoint_when_job_metrics_absent() -> None:
    ctx = {
        "biz_date": "2026-05-27",
        "source_collection_json": {
            "collections": [
                {
                    "binding": {"role_code": "left_1", "dataset_name": "tb0131100248-店铺订单"},
                    "collection_records": {"record_count": 0},
                },
                {
                    "binding": {"role_code": "right_1", "dataset_name": "tb0131100248-收支账单"},
                    "collection_records": {"record_count": 0},
                },
            ],
            "collection_attempts": [
                {
                    "binding": {"role_code": "left_1", "dataset_name": "tb0131100248-店铺订单"},
                    "job": {
                        "started_at": "2026-05-28T09:40:02.832897+08:00",
                        "completed_at": "2026-05-28T09:41:19.024757+08:00",
                        "checkpoint_after": {
                            "browser_collection_summary": {
                                "record_count": 461,
                                "quality_summary": {"row_count": 461},
                                "records": {"input_count": 461, "upserted_count": 461},
                            }
                        },
                    },
                },
                {
                    "binding": {"role_code": "right_1", "dataset_name": "tb0131100248-收支账单"},
                    "job": {
                        "started_at": "2026-05-28T09:41:19.054214+08:00",
                        "completed_at": "2026-05-28T09:49:30.307656+08:00",
                        "checkpoint_after": {
                            "browser_collection_summary": {
                                "record_count": 456,
                                "quality_summary": {"row_count": 456},
                                "records": {"input_count": 456, "upserted_count": 456},
                            }
                        },
                    },
                },
            ],
        },
        "runtime_metrics": {},
    }

    summary = nodes._build_runtime_summary(ctx)  # noqa: SLF001

    assert summary["collections"][0]["row_count"] == 461
    assert summary["collections"][0]["duration_seconds"] == 76.19186
    assert summary["collections"][1]["row_count"] == 456
    assert summary["collections"][1]["duration_seconds"] == 491.253442


def test_collection_count_from_result_reads_browser_checkpoint_after_summary() -> None:
    result = {
        "success": True,
        "job": {
            "checkpoint_after": {
                "browser_collection_summary": {
                    "record_count": 456,
                    "quality_summary": {"row_count": 456},
                    "records": {"input_count": 456, "upserted_count": 456},
                }
            }
        },
    }

    assert nodes._collection_count_from_result(result) == 456  # noqa: SLF001


def test_trigger_and_wait_collection_enriches_completed_job_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_calls: list[str] = []

    async def fake_trigger_collection(**kwargs: object) -> dict[str, object]:
        return {
            "success": True,
            "queued": False,
            "job": {"id": "job-001", "status": "success"},
        }

    async def fake_get_sync_job(
        auth_token: str,
        sync_job_id: str,
        *,
        mode: str = "real",
    ) -> dict[str, object]:
        get_calls.append(sync_job_id)
        return {
            "success": True,
            "job": {
                "id": sync_job_id,
                "status": "success",
                "metrics": {
                    "row_count": 91852,
                    "collection_timing": {"total_seconds": 64.816416},
                },
            },
        }

    monkeypatch.setattr(nodes, "_trigger_collection", fake_trigger_collection)
    monkeypatch.setattr(nodes, "data_source_get_sync_job", fake_get_sync_job)

    result = asyncio.run(
        nodes._trigger_and_wait_collection(  # noqa: SLF001
            auth_token="token",
            source_id="source-001",
            dataset_id="dataset-001",
            resource_key="orders",
            biz_date="2026-05-20",
            trigger_mode="manual",
        )
    )

    assert get_calls == ["job-001"]
    assert result["success"] is True
    assert result["job"]["metrics"]["row_count"] == 91852
    assert result["job"]["metrics"]["collection_timing"]["total_seconds"] == 64.816416


def test_runtime_summary_notification_patch_preserves_existing_artifacts() -> None:
    artifacts = {"output_files": ["a.xlsx"], "runtime_summary": {"biz_date": "2026-05-20"}}
    patched = nodes._merge_runtime_summary_notification(  # noqa: SLF001
        artifacts,
        {
            "status": "sent",
            "summary_recipient": {"name": "张小毅", "identifier": "072007534524160438"},
            "message_id": "msg-001",
            "error": "",
        },
    )

    assert patched["output_files"] == ["a.xlsx"]
    assert patched["runtime_summary"]["biz_date"] == "2026-05-20"
    assert patched["runtime_summary"]["summary_notification"]["status"] == "sent"
    assert patched["runtime_summary"]["summary_notification"]["recipient_name"] == "张小毅"


def test_alipay_fund_source_only_creates_execution_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    created_payloads: list[dict[str, object]] = []

    async def fake_call_mcp_tool(name: str, payload: dict[str, object]) -> dict[str, object]:
        if name == "execution_run_exception_bulk_create":
            exceptions = list(payload.get("exceptions", []))
            for exc in exceptions:
                created_payloads.append({"name": name, "payload": exc})
            return {"success": True, "created": len(exceptions)}
        return {"success": True}

    monkeypatch.setattr(nodes, "call_mcp_tool", fake_call_mcp_tool)
    ctx = {
        "execution_run_record": {"id": "run-001"},
        "scheme_code": "scheme-001",
        "source_collection_json": {
            "collections": [
                {"binding": {"role_code": "left_1", "dataset_name": "交易订单明细表"}},
                {
                    "binding": {
                        "role_code": "right_1",
                        "dataset_name": "支付宝资金账单 - 测试商户",
                        "resource_key": "alipay_bill:signcustomer:shop-001",
                    }
                },
            ]
        },
        "recon_observation": {
            "summary": {
                "matched_exact": 10,
                "matched_with_diff": 0,
                "source_only": 2,
                "target_only": 0,
                "has_anomaly": True,
            },
            "anomaly_items": [
                {"item_id": "source-1", "anomaly_type": "source_only"},
                {"item_id": "source-2", "anomaly_type": "source_only"},
            ],
        },
        "anomaly_items": [
            {"item_id": "source-1", "anomaly_type": "source_only"},
            {"item_id": "source-2", "anomaly_type": "source_only"},
        ],
    }
    result = asyncio.run(nodes.create_exception_tasks_node({"auth_token": "token", "recon_ctx": ctx}))

    assert result["recon_ctx"]["anomaly_items"] == [
        {"item_id": "source-1", "anomaly_type": "source_only"},
        {"item_id": "source-2", "anomaly_type": "source_only"},
    ]
    assert [item["payload"]["anomaly_type"] for item in created_payloads] == [
        "source_only",
        "source_only",
    ]
    assert result["recon_ctx"]["exception_created_count"] == 2


def test_execute_auto_task_run_schedule_collects_before_recon(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_task_get(auth_token: str, auto_task_id: str) -> dict[str, object]:
        return {
            "success": True,
            "task": {
                "id": auto_task_id,
                "task_name": "日结对账",
                "rule_code": "merchant_recon_rule",
                "auto_create_exceptions": False,
                "input_bindings": [
                    {
                        "data_source_id": "source-001",
                        "dataset_id": "dataset-001",
                        "table_name": "orders_ready",
                        "resource_key": "orders",
                        "required": True,
                    }
                ],
            },
        }

    async def fake_collect(auth_token: str, source_id: str, **kwargs: object) -> dict[str, object]:
        captured["collect"] = {"auth_token": auth_token, "source_id": source_id, **kwargs}
        return {"success": True, "job": {"id": "job-001"}}

    async def fake_list(auth_token: str, source_id: str, **kwargs: object) -> dict[str, object]:
        captured["list"] = {"auth_token": auth_token, "source_id": source_id, **kwargs}
        return {
            "success": True,
            "dataset_id": "dataset-001",
            "resource_key": "orders",
            "record_count": 1,
            "records": [{"item_key": "1"}],
        }

    async def fake_run_create(auth_token: str, payload: dict[str, object]) -> dict[str, object]:
        captured["run_create"] = payload
        return {"success": True, "run": {"id": "run-001"}}

    async def fake_run_job_create(auth_token: str, payload: dict[str, object]) -> dict[str, object]:
        return {"success": True, "run_job": {"id": "job-001"}}

    async def fake_run_update(auth_token: str, auto_run_id: str, payload: dict[str, object]) -> dict[str, object]:
        return {"success": True, "run": {"id": auto_run_id, **payload}}

    async def fake_rule(auth_token: str, rule_code: str) -> dict[str, object]:
        return {
            "success": True,
            "data": {
                "rule": {"rule_name": "商户对账规则", "rules": []},
            },
        }

    async def fake_pipeline(**kwargs: object) -> dict[str, object]:
        return {
            "ok": True,
            "execution_result": {"success": True},
            "recon_observation": {"summary": {}, "anomaly_items": []},
        }

    async def fake_run_get(auth_token: str, auto_run_id: str) -> dict[str, object]:
        return {"success": True, "run": {"id": auto_run_id}}

    async def fake_run_job_update(auth_token: str, run_job_id: str, payload: dict[str, object]) -> dict[str, object]:
        return {"success": True, "run_job": {"id": run_job_id, **payload}}

    monkeypatch.setattr(auto_run_service, "recon_auto_task_get", fake_task_get)
    monkeypatch.setattr(auto_run_service, "data_source_trigger_dataset_collection", fake_collect)
    monkeypatch.setattr(auto_run_service, "data_source_list_collection_records", fake_list)
    monkeypatch.setattr(auto_run_service, "recon_auto_run_create", fake_run_create)
    monkeypatch.setattr(auto_run_service, "recon_auto_run_job_create", fake_run_job_create)
    monkeypatch.setattr(auto_run_service, "recon_auto_run_update", fake_run_update)
    monkeypatch.setattr(auto_run_service, "get_file_validation_rule", fake_rule)
    monkeypatch.setattr(auto_run_service, "execute_headless_recon_pipeline", fake_pipeline)
    monkeypatch.setattr(auto_run_service, "recon_auto_run_get", fake_run_get)
    monkeypatch.setattr(auto_run_service, "recon_auto_run_job_update", fake_run_job_update)

    result = asyncio.run(
        auto_run_service.execute_auto_task_run(
            auth_token="token",
            auto_task_id="task-001",
            biz_date="2026-04-25",
            trigger_mode="schedule",
        )
    )

    assert result["success"] is True
    assert captured["collect"]["trigger_mode"] == "scheduled"
    assert captured["run_create"]["source_snapshot_json"]["collection_attempts"][0]["success"] is True


def test_execute_auto_task_run_manual_collects_before_recon(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_task_get(auth_token: str, auto_task_id: str) -> dict[str, object]:
        return {
            "success": True,
            "task": {
                "id": auto_task_id,
                "task_name": "手工对账",
                "rule_code": "merchant_recon_rule",
                "auto_create_exceptions": False,
                "input_bindings": [
                    {
                        "data_source_id": "source-001",
                        "dataset_id": "dataset-001",
                        "table_name": "orders_ready",
                        "resource_key": "orders",
                        "required": True,
                    }
                ],
            },
        }

    async def fake_collect(auth_token: str, source_id: str, **kwargs: object) -> dict[str, object]:
        captured["collect"] = {"auth_token": auth_token, "source_id": source_id, **kwargs}
        return {"success": True, "job": {"id": "job-001"}}

    async def fake_list(auth_token: str, source_id: str, **kwargs: object) -> dict[str, object]:
        return {
            "success": True,
            "dataset_id": "dataset-001",
            "resource_key": "orders",
            "record_count": 1,
            "records": [{"item_key": "1"}],
        }

    async def fake_run_create(auth_token: str, payload: dict[str, object]) -> dict[str, object]:
        return {"success": True, "run": {"id": "run-001"}}

    async def fake_run_job_create(auth_token: str, payload: dict[str, object]) -> dict[str, object]:
        return {"success": True, "run_job": {"id": "job-001"}}

    async def fake_run_update(auth_token: str, auto_run_id: str, payload: dict[str, object]) -> dict[str, object]:
        return {"success": True, "run": {"id": auto_run_id, **payload}}

    async def fake_rule(auth_token: str, rule_code: str) -> dict[str, object]:
        return {
            "success": True,
            "data": {
                "rule": {"rule_name": "商户对账规则", "rules": []},
            },
        }

    async def fake_pipeline(**kwargs: object) -> dict[str, object]:
        return {
            "ok": True,
            "execution_result": {"success": True},
            "recon_observation": {"summary": {}, "anomaly_items": []},
        }

    async def fake_run_get(auth_token: str, auto_run_id: str) -> dict[str, object]:
        return {"success": True, "run": {"id": auto_run_id}}

    async def fake_run_job_update(auth_token: str, run_job_id: str, payload: dict[str, object]) -> dict[str, object]:
        return {"success": True, "run_job": {"id": run_job_id, **payload}}

    monkeypatch.setattr(auto_run_service, "recon_auto_task_get", fake_task_get)
    monkeypatch.setattr(auto_run_service, "data_source_trigger_dataset_collection", fake_collect)
    monkeypatch.setattr(auto_run_service, "data_source_list_collection_records", fake_list)
    monkeypatch.setattr(auto_run_service, "recon_auto_run_create", fake_run_create)
    monkeypatch.setattr(auto_run_service, "recon_auto_run_job_create", fake_run_job_create)
    monkeypatch.setattr(auto_run_service, "recon_auto_run_update", fake_run_update)
    monkeypatch.setattr(auto_run_service, "get_file_validation_rule", fake_rule)
    monkeypatch.setattr(auto_run_service, "execute_headless_recon_pipeline", fake_pipeline)
    monkeypatch.setattr(auto_run_service, "recon_auto_run_get", fake_run_get)
    monkeypatch.setattr(auto_run_service, "recon_auto_run_job_update", fake_run_job_update)

    result = asyncio.run(
        auto_run_service.execute_auto_task_run(
            auth_token="token",
            auto_task_id="task-001",
            biz_date="2026-04-25",
            trigger_mode="manual",
        )
    )

    assert result["success"] is True
    assert captured["collect"]["trigger_mode"] == "manual"


def test_normalize_execution_trigger_type_preserves_manual_and_rerun() -> None:
    assert nodes._normalize_execution_trigger_type("manual") == "manual"
    assert nodes._normalize_execution_trigger_type("manual_trigger") == "manual"
    assert nodes._normalize_execution_trigger_type("rerun") == "rerun"
    assert nodes._normalize_execution_trigger_type("retry") == "rerun"
    assert nodes._normalize_execution_trigger_type("schedule") == "schedule"


def test_exception_reminder_uses_base_dataset_names_and_hides_type_line() -> None:
    scheme = {
        "scheme_name": "店铺对账",
        "scheme_meta_json": {
            "left_sources": [
                {
                    "dataset_id": "lookup-dataset",
                    "dataset_name": "支付宝订单数据",
                    "resource_key": "public.alipay_order_detail",
                },
                {
                    "dataset_id": "base-dataset",
                    "dataset_name": "FP订单表",
                    "resource_key": "public.ods_yxst_fp_orders_di_o",
                },
            ],
            "right_sources": [
                {
                    "dataset_id": "right-dataset",
                    "dataset_name": "交易订单明细表",
                    "resource_key": "public.ods_yxst_trd_order_di_o",
                }
            ],
            "input_plan_json": {
                "plans": [
                    {
                        "side": "left",
                        "target_table": "left_recon_ready",
                        "datasets": [
                            {
                                "dataset_id": "lookup-dataset",
                                "resource_key": "public.alipay_order_detail",
                                "read_mode": "by_key_set",
                            },
                            {
                                "dataset_id": "base-dataset",
                                "resource_key": "public.ods_yxst_fp_orders_di_o",
                                "read_mode": "base",
                            },
                        ],
                    },
                    {
                        "side": "right",
                        "target_table": "right_recon_ready",
                        "datasets": [
                            {
                                "dataset_id": "right-dataset",
                                "resource_key": "public.ods_yxst_trd_order_di_o",
                                "read_mode": "base",
                            }
                        ],
                    },
                ]
            },
        },
    }
    exception = {
        "anomaly_type": "source_only",
        "summary": "仅 左侧数据 存在（右侧数据 缺失）",
        "detail_json": {
            "join_key": [{"source_field": "order_no", "source_value": "SO-001"}],
        },
    }

    todo_title, _, bot_content = nodes._compose_execution_exception_reminder_text(
        run_plan={"plan_name": "每天9点半对账"},
        scheme=scheme,
        biz_date="2026-05-02",
        exception=exception,
    )

    assert "FP订单表" in todo_title
    assert "交易订单明细表" in todo_title
    assert "支付宝订单数据" not in todo_title
    assert "异常类型" not in bot_content
    assert "左侧数据" not in bot_content
    assert "右侧数据" not in bot_content
    assert "源数据" not in bot_content
    assert "目标数据" not in bot_content
    assert "异常详情：\n仅 FP订单表 存在（交易订单明细表 缺失）" in bot_content


def test_legacy_exception_reminder_replaces_source_target_labels() -> None:
    todo_title, _, bot_content = auto_run_service._compose_reminder_text(
        {"task_name": "Tally"},
        {"biz_date": "2026-05-02"},
        {
            "anomaly_type": "target_only",
            "summary": "仅 目标数据 存在（源数据 缺失）",
            "detail_json": {
                "join_key": [{"target_field": "order_no", "target_value": "SO-002"}],
            },
        },
        left_name="FP订单表",
        right_name="交易订单明细表",
    )

    assert "交易订单明细表" in todo_title
    assert "FP订单表" in todo_title
    assert "异常类型" not in bot_content
    assert "源数据" not in bot_content
    assert "目标数据" not in bot_content
    assert "异常详情：仅 交易订单明细表 存在（FP订单表 缺失）" in bot_content


def test_exception_summary_rebuilds_from_context_and_includes_compare_field() -> None:
    item = {
        "anomaly_type": "target_only",
        "summary": "仅 public.ods_yxst_trd_order_di_o 存在（public.ods_jd_sold_fuyou_mongo_o 缺失）：订单ID=800266249859653",
        "join_key": [
            {
                "source_field": "订单ID",
                "target_field": "订单ID",
                "source_value": None,
                "target_value": "800266249859653",
            }
        ],
        "compare_values": [
            {
                "name": "金额",
                "source_field": "金额",
                "target_field": "金额",
                "source_value": None,
                "target_value": "99.90",
            }
        ],
        "raw_record": {"订单ID": "800266249859653", "金额": "99.90"},
    }

    summary = nodes._build_anomaly_summary(
        "target_only",
        item,
        left_name="福游京东店铺订单",
        right_name="交易订单明细表",
        field_labels={"订单ID": "订单ID", "金额": "金额"},
    )

    assert "public." not in summary
    assert "左侧独有" not in summary
    assert "右侧独有" not in summary
    assert "交易订单明细表" in summary
    assert "福游京东店铺订单" in summary
    assert "订单ID=800266249859653" in summary
    assert "金额：交易订单明细表 99.90" in summary


def test_summary_only_notification_uses_base_dataset_names() -> None:
    _, content = nodes._compose_run_summary_notification_text(
        ctx={
            "run_plan": {"plan_name": "每天9点半对账"},
            "scheme": {
                "scheme_name": "店铺对账",
                "scheme_meta_json": {
                    "input_plan_json": {
                        "plans": [
                            {
                                "side": "left",
                                "target_table": "left_recon_ready",
                                "datasets": [
                                    {
                                        "table": "public.ods_jd_sold_fuyou_mongo_o",
                                        "resource_key": "public.ods_jd_sold_fuyou_mongo_o",
                                        "read_mode": "base",
                                    }
                                ],
                            },
                            {
                                "side": "right",
                                "target_table": "right_recon_ready",
                                "datasets": [
                                    {
                                        "table": "public.ods_yxst_trd_order_di_o",
                                        "resource_key": "public.ods_yxst_trd_order_di_o",
                                        "read_mode": "base",
                                    }
                                ],
                            },
                        ]
                    }
                },
            },
            "biz_date": "2026-05-02",
            "recon_result_summary_json": {
                "source_only": 1,
                "target_only": 2,
                "matched_with_diff": 3,
                "matched_exact": 4,
            },
            "ready_collections": [
                {
                    "binding": {
                        "role_code": "left_1",
                        "input_plan_target_table": "left_recon_ready",
                        "dataset_name": "福游京东店铺订单",
                        "resource_key": "public.ods_jd_sold_fuyou_mongo_o",
                        "query": {"date_field": "pt", "display_date_field": "分区日期"},
                    },
                    "collection_records": {"records": [{"payload": {"pt": "20260502"}}]},
                },
                {
                    "binding": {
                        "role_code": "right_1",
                        "input_plan_target_table": "right_recon_ready",
                        "dataset_name": "交易订单明细表",
                        "resource_key": "public.ods_yxst_trd_order_di_o",
                        "query": {"date_field": "order_time", "display_date_field": "订单时间"},
                    },
                    "collection_records": {"records": [{"payload": {"order_time": "2026-05-02 10:00:00"}}]},
                },
            ],
        },
        anomalies=[
            {"anomaly_type": "source_only"},
            {"anomaly_type": "target_only"},
            {"anomaly_type": "matched_with_diff"},
        ],
        threshold=10,
        explosion=True,
    )

    assert "异常类型" not in content
    assert "左侧独有" not in content
    assert "右侧独有" not in content
    assert "源数据" not in content
    assert "目标数据" not in content
    assert "public." not in content
    assert "异常统计" not in content
    assert "仅 福游京东店铺订单 存在（交易订单明细表 缺失）" in content
    assert "仅 交易订单明细表 存在（福游京东店铺订单 缺失）" in content
    assert content.count("仅 福游京东店铺订单 存在（交易订单明细表 缺失）") == 1
    assert content.count("仅 交易订单明细表 存在（福游京东店铺订单 缺失）") == 1


def test_summary_only_notification_uses_source_collection_names_when_ready_ctx_missing() -> None:
    _, content = nodes._compose_run_summary_notification_text(
        ctx={
            "run_plan": {"plan_name": "搜卡京东订单对账 2026-05-03"},
            "scheme": {
                "scheme_name": "搜卡京东订单对账",
                "scheme_meta_json": {
                    "input_plan_json": {
                        "plans": [
                            {
                                "side": "left",
                                "target_table": "left_recon_ready",
                                "datasets": [
                                    {
                                        "table": "public.ods_jd_sold_fuyou_mongo_o",
                                        "resource_key": "public.ods_jd_sold_fuyou_mongo_o",
                                        "read_mode": "base",
                                    }
                                ],
                            },
                            {
                                "side": "right",
                                "target_table": "right_recon_ready",
                                "datasets": [
                                    {
                                        "table": "public.ods_yxst_trd_order_di_o",
                                        "resource_key": "public.ods_yxst_trd_order_di_o",
                                        "read_mode": "base",
                                    }
                                ],
                            },
                        ]
                    }
                },
            },
            "biz_date": "2026-05-02",
            "recon_result_summary_json": {
                "source_only": 31,
                "target_only": 74522,
                "matched_with_diff": 0,
                "matched_exact": 0,
            },
            "source_collection_json": {
                "collections": [
                    {
                        "binding": {
                            "role_code": "left_1",
                            "input_plan_target_table": "left_recon_ready",
                            "dataset_name": "福游京东店铺订单",
                            "resource_key": "public.ods_jd_sold_fuyou_mongo_o",
                            "query": {"date_field": "pt", "display_date_field": "PT"},
                        },
                        "collection_records": {"sample_records": [{"payload": {"pt": "20260502"}}]},
                    },
                    {
                        "binding": {
                            "role_code": "right_1",
                            "input_plan_target_table": "right_recon_ready",
                            "dataset_name": "交易订单明细表",
                            "resource_key": "public.ods_yxst_trd_order_di_o",
                            "query": {"date_field": "create_date", "display_date_field": "创建日期"},
                        },
                        "collection_records": {
                            "sample_records": [
                                {"payload": {"create_date": "2026-05-02T01:02:10.540000+08:00"}}
                            ]
                        },
                    },
                ]
            },
        },
        anomalies=[
            {"anomaly_type": "target_only"} for _ in range(2)
        ] + [{"anomaly_type": "source_only"}],
        threshold=50,
        explosion=True,
    )

    assert "public." not in content
    assert "异常统计" not in content
    assert "- 仅 福游京东店铺订单 存在（交易订单明细表 缺失）：31 条" in content
    assert "- 仅 交易订单明细表 存在（福游京东店铺订单 缺失）：74522 条" in content
    assert content.count("仅 福游京东店铺订单 存在（交易订单明细表 缺失）") == 1
    assert content.count("仅 交易订单明细表 存在（福游京东店铺订单 缺失）") == 1


def test_update_rerun_exception_verification_closes_resolved_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_get(auth_token: str, exception_id: str) -> dict[str, object]:
        captured["get"] = {"auth_token": auth_token, "exception_id": exception_id}
        return {
            "success": True,
            "exception": {
                "id": exception_id,
                "feedback_json": {"todo_id": "todo-001"},
            },
        }

    async def fake_update(auth_token: str, exception_id: str, payload: dict[str, object]) -> dict[str, object]:
        captured["update"] = {
            "auth_token": auth_token,
            "exception_id": exception_id,
            "payload": payload,
        }
        return {"success": True, "exception": {"id": exception_id, **payload}}

    monkeypatch.setattr(nodes, "execution_run_exception_get", fake_get)
    monkeypatch.setattr(nodes, "execution_run_exception_update", fake_update)

    state = {
        "auth_token": "token",
        "recon_ctx": {
            "run_context": {
                "rerun_exception_id": "exception-001",
                "rerun_from_run_id": "run-old",
            },
            "execution_run_record": {
                "id": "run-new",
                "execution_status": "success",
            },
            "anomaly_items": [],
        },
    }

    result = asyncio.run(nodes.update_rerun_exception_verification_node(state))
    payload = captured["update"]["payload"]

    assert payload["processing_status"] == "verified_closed"
    assert payload["fix_status"] == "fixed"
    assert payload["is_closed"] is True
    assert payload["feedback_json"]["todo_id"] == "todo-001"
    assert payload["feedback_json"]["verify_run_id"] == "run-new"
    assert payload["feedback_json"]["verify_anomaly_count"] == 0
    assert result["recon_ctx"]["rerun_exception_verification"]["id"] == "exception-001"


def test_update_rerun_exception_verification_reopens_when_anomaly_remains(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_get(auth_token: str, exception_id: str) -> dict[str, object]:
        return {"success": True, "exception": {"id": exception_id, "feedback_json": {}}}

    async def fake_update(auth_token: str, exception_id: str, payload: dict[str, object]) -> dict[str, object]:
        captured["payload"] = payload
        return {"success": True, "exception": {"id": exception_id, **payload}}

    monkeypatch.setattr(nodes, "execution_run_exception_get", fake_get)
    monkeypatch.setattr(nodes, "execution_run_exception_update", fake_update)

    state = {
        "auth_token": "token",
        "recon_ctx": {
            "run_context": {"rerun_exception_id": "exception-001"},
            "execution_run_record": {"id": "run-new", "execution_status": "success"},
            "anomaly_items": [{"anomaly_type": "matched_with_diff"}],
        },
    }

    asyncio.run(nodes.update_rerun_exception_verification_node(state))
    payload = captured["payload"]

    assert payload["processing_status"] == "reopened"
    assert payload["fix_status"] == "pending"
    assert payload["is_closed"] is False
    assert payload["feedback_json"]["verify_anomaly_count"] == 1


def test_create_exception_tasks_node_persists_all_anomalies_when_explosion_threshold_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """超过 explosion_threshold 时，全量差异都应落库（不再采样截断）。"""
    created_payloads: list[dict[str, object]] = []
    update_payloads: list[dict[str, object]] = []

    async def fake_call_mcp_tool(name: str, payload: dict[str, object]) -> dict[str, object]:
        if name == "execution_run_exception_bulk_create":
            exceptions = list(payload.get("exceptions", []))
            for exc in exceptions:
                created_payloads.append(exc)
            return {"success": True, "created": len(exceptions)}
        if name == "execution_run_update":
            update_payloads.append(payload)
            return {
                "success": True,
                "run": {
                    "id": payload["run_id"],
                    "artifacts_json": payload["artifacts_json"],
                },
            }
        raise AssertionError(f"unexpected MCP tool: {name}")

    monkeypatch.setattr(nodes, "call_mcp_tool", fake_call_mcp_tool)

    n = 55
    anomalies = [
        {
            "item_id": f"run-001:1:source_only:{index}",
            "anomaly_type": "source_only",
            "join_key": [{"source_field": "订单号", "source_value": f"ORD-{index}"}],
            "compare_values": [],
            "raw_record": {"订单号": f"ORD-{index}"},
        }
        for index in range(1, n + 1)
    ]
    state = {
        "auth_token": "token",
        "recon_ctx": {
            "execution_run_record": {"id": "run-001"},
            "scheme_code": "scheme-001",
            "run_plan": {
                "owner_mapping_json": {
                    "default_owner": {
                        "name": "周行",
                        "identifier": "ding-user-001",
                    }
                },
                "plan_meta_json": {
                    "notify_policy": {
                        "explosion_threshold": 10,
                        "sample_exception_limit": 3,
                    }
                },
            },
            "scheme": {
                "scheme_meta_json": {
                    "left_sources": [{"dataset_name": "交易订单明细表"}],
                    "right_sources": [{"dataset_name": "支付宝资金账单"}],
                }
            },
            "anomaly_items": anomalies,
        },
    }

    result = asyncio.run(nodes.create_exception_tasks_node(state))
    recon_ctx = result["recon_ctx"]

    # 全量落库：55 条全部写入，不截断到 sample_exception_limit=3
    assert len(created_payloads) == n
    assert recon_ctx["exception_created_count"] == n
    assert recon_ctx["exception_creation_limited"] is False
    assert recon_ctx["exception_total_count"] == n
    assert recon_ctx["exception_created_sample_count"] == n
    assert recon_ctx["auto_notify_policy"]["explosion"] is True
    assert recon_ctx["auto_notify_policy"]["created_exception_sample_limit"] == n
    # 未采样，enabled 应为 False
    assert recon_ctx["exception_sampling"]["enabled"] is False
    assert recon_ctx["exception_sampling"]["threshold"] == 10
    assert recon_ctx["exception_sampling"]["total_count"] == n
    assert recon_ctx["exception_sampling"]["sample_count"] == n


def test_create_exception_tasks_node_does_not_update_run_for_sampling_when_full_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全量落库模式下，create_exception_tasks_node 不再为采样写 execution_run_update。"""
    update_payloads: list[dict[str, object]] = []
    create_payloads: list[dict[str, object]] = []

    async def fake_call_mcp_tool(name: str, payload: dict[str, object]) -> dict[str, object]:
        if name == "execution_run_exception_bulk_create":
            exceptions = list(payload.get("exceptions", []))
            for exc in exceptions:
                create_payloads.append(exc)
            return {"success": True, "created": len(exceptions)}
        if name == "execution_run_update":
            update_payloads.append(payload)
            return {
                "success": True,
                "run": {
                    "id": payload["run_id"],
                    "artifacts_json": payload["artifacts_json"],
                },
            }
        raise AssertionError(f"unexpected MCP tool: {name}")

    monkeypatch.setattr(nodes, "call_mcp_tool", fake_call_mcp_tool)

    n = 7
    anomalies = [
        {"item_id": f"anomaly-{index}", "anomaly_type": "source_only"}
        for index in range(1, n + 1)
    ]
    state = {
        "auth_token": "token",
        "recon_ctx": {
            "execution_run_record": {
                "id": "run-001",
                "artifacts_json": {
                    "runtime_summary": {
                        "queue": {"job_id": "queue-001"},
                        "summary_notification": {"status": "sent"},
                    }
                },
            },
            "scheme_code": "scheme-001",
            "run_plan": {
                "owner_mapping_json": {
                    "default_owner": {"name": "周行", "identifier": "ding-user-001"}
                },
                "plan_meta_json": {
                    "notify_policy": {
                        "explosion_threshold": 3,
                        "sample_exception_limit": 2,
                    }
                },
            },
            "anomaly_items": anomalies,
        },
    }

    result = asyncio.run(nodes.create_exception_tasks_node(state))

    # 全量落库：7 条全部写入，不截断到 sample_exception_limit=2
    assert len(create_payloads) == n
    # 不再为采样持久化 execution_run_update
    assert len(update_payloads) == 0
    # ctx 中采样元数据 enabled=False
    recon_ctx = result["recon_ctx"]
    assert recon_ctx["exception_sampling"]["enabled"] is False
    assert recon_ctx["exception_sampling"]["total_count"] == n
    assert recon_ctx["exception_sampling"]["sample_count"] == n


def test_create_exception_tasks_node_persists_all_with_owner_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全量落库模式下，owner_mapping 正确应用到每一条差异，4 条全部写入。

    bulk 响应带回 [{id, anomaly_key}]，create_exception_tasks_node 应还原
    created_exceptions 列表（含 exception_id / owner_identifier），以便
    maybe_auto_notify_node 正确分组发催办。
    """
    create_payloads: list[dict[str, object]] = []
    _exc_counter = {"n": 0}

    async def fake_call_mcp_tool(name: str, payload: dict[str, object]) -> dict[str, object]:
        if name == "execution_run_exception_bulk_create":
            exceptions = list(payload.get("exceptions", []))
            returned_refs: list[dict[str, object]] = []
            for exc in exceptions:
                create_payloads.append(exc)
                _exc_counter["n"] += 1
                returned_refs.append(
                    {"id": f"exc-{_exc_counter['n']}", "anomaly_key": exc["anomaly_key"]}
                )
            return {"success": True, "created": len(exceptions), "exceptions": returned_refs}
        if name == "execution_run_update":
            return {
                "success": True,
                "run": {
                    "id": payload["run_id"],
                    "artifacts_json": payload["artifacts_json"],
                },
            }
        raise AssertionError(f"unexpected MCP tool: {name}")

    monkeypatch.setattr(nodes, "call_mcp_tool", fake_call_mcp_tool)

    anomalies = [
        {"item_id": "source-1", "anomaly_type": "source_only", "summary": "仅订单表存在"},
        {"item_id": "source-2", "anomaly_type": "source_only", "summary": "仅订单表存在"},
        {"item_id": "target-1", "anomaly_type": "target_only", "summary": "仅账单存在"},
        {"item_id": "target-2", "anomaly_type": "target_only", "summary": "仅账单存在"},
    ]
    state = {
        "auth_token": "token",
        "recon_ctx": {
            "execution_run_record": {"id": "run-001", "artifacts_json": {}},
            "scheme_code": "scheme-001",
            "run_plan": {
                "owner_mapping_json": {
                    "default_owner": {"name": "默认责任人", "identifier": "owner-default"},
                    "anomaly_type_to_owner": {
                        "source_only": {"name": "订单责任人", "identifier": "owner-source"},
                    },
                    "mappings": [
                        {
                            "anomaly_types": ["target_only"],
                            "keywords": ["账单"],
                            "owner": {"name": "账单责任人", "identifier": "owner-target"},
                        }
                    ],
                },
                "plan_meta_json": {
                    "notify_policy": {
                        "explosion_threshold": 1,
                        # sample_exception_limit 配置了 2，但全量模式下不截断
                        "sample_exception_limit": 2,
                    }
                },
            },
            "anomaly_items": anomalies,
        },
    }

    result = asyncio.run(nodes.create_exception_tasks_node(state))
    recon_ctx = result["recon_ctx"]

    # 全量 4 条全部写入（旧代码会按 sample_limit=2 截断，只写 2 条）
    assert len(create_payloads) == 4
    owner_identifiers = [payload["owner_identifier"] for payload in create_payloads]
    assert owner_identifiers.count("owner-source") == 2
    assert owner_identifiers.count("owner-target") == 2
    owner_names = [payload["owner_name"] for payload in create_payloads]
    assert "订单责任人" in owner_names
    assert "账单责任人" in owner_names
    for payload in create_payloads:
        assert not any(str(key).startswith("_exception_") for key in payload["detail_json"])

    assert recon_ctx["exception_created_count"] == 4

    # created_exceptions 必须非空，且每条包含 exception_id 和 owner 字段
    created_exceptions = recon_ctx["created_exceptions"]
    assert len(created_exceptions) == 4, (
        f"created_exceptions 应有 4 条，实际 {len(created_exceptions)}"
    )
    for item in created_exceptions:
        assert item.get("exception_id"), f"缺少 exception_id: {item}"
        exc = item.get("exception") or {}
        assert exc.get("owner_identifier"), f"缺少 owner_identifier: {item}"

    # 按 owner_identifier 统计分布（各 2 条）
    owner_identifiers_in_refs = [
        (item.get("exception") or {}).get("owner_identifier")
        for item in created_exceptions
    ]
    assert owner_identifiers_in_refs.count("owner-source") == 2
    assert owner_identifiers_in_refs.count("owner-target") == 2


def test_create_exception_and_notify_node_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """create_exception_tasks_node → maybe_auto_notify_node 的接口约定不断裂。

    当 bulk 响应返回 exceptions 列表时，create 节点产出的 created_exceptions 应非空，
    喂给 notify 节点后不走 skipped_no_exception 分支。
    """
    _exc_counter = {"n": 0}

    async def fake_call_mcp_tool(name: str, payload: dict[str, object]) -> dict[str, object]:
        if name == "execution_run_exception_bulk_create":
            exceptions = list(payload.get("exceptions", []))
            returned_refs: list[dict[str, object]] = []
            for exc in exceptions:
                _exc_counter["n"] += 1
                returned_refs.append(
                    {"id": f"exc-{_exc_counter['n']}", "anomaly_key": exc["anomaly_key"]}
                )
            return {"success": True, "created": len(exceptions), "exceptions": returned_refs}
        # maybe_auto_notify_node 会调 _send_run_summary_notification → summary notification
        return {"success": True}

    monkeypatch.setattr(nodes, "call_mcp_tool", fake_call_mcp_tool)
    # stub out channel-config and DingTalk notify so notify node doesn't fail on missing env
    monkeypatch.setattr(nodes, "load_company_channel_config_by_id", lambda channel_id: None)

    anomalies = [
        {"item_id": f"a-{i}", "anomaly_type": "source_only", "summary": f"差异 {i}"}
        for i in range(3)
    ]
    state = {
        "auth_token": "token",
        "recon_ctx": {
            "execution_run_record": {"id": "run-c-001"},
            "scheme_code": "scheme-c-001",
            "run_plan": {
                "owner_mapping_json": {
                    "default_owner": {"name": "财务", "identifier": "owner-c-001"}
                },
                "plan_meta_json": {
                    "notify_policy": {"explosion_threshold": 1000}
                },
            },
            "anomaly_items": anomalies,
        },
    }

    create_result = asyncio.run(nodes.create_exception_tasks_node(state))
    created_exceptions = create_result["recon_ctx"]["created_exceptions"]

    # 核心约定：created_exceptions 非空，且每条含 exception_id
    assert created_exceptions, "create 节点产出的 created_exceptions 不应为空"
    for item in created_exceptions:
        assert item.get("exception_id"), f"缺少 exception_id: {item}"
        exc = item.get("exception") or {}
        assert exc.get("owner_identifier"), f"缺少 owner_identifier: {item}"

    # 喂给 maybe_auto_notify_node，验证不走 skipped_no_exception
    notify_state = {**state, "recon_ctx": create_result["recon_ctx"]}
    notify_result = asyncio.run(nodes.maybe_auto_notify_node(notify_state))
    notify_ctx = notify_result["recon_ctx"]

    assert notify_ctx.get("auto_notify_status") != "skipped_no_exception", (
        "maybe_auto_notify_node 不应走 skipped_no_exception，"
        f"实际 auto_notify_status={notify_ctx.get('auto_notify_status')!r}"
    )


def test_create_exception_tasks_node_persists_all_anomalies_without_sampling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全量落库：250条差异用批量工具(bulk_create)持久化，不走逐条单条工具。

    断言：
    - call_mcp_tool 调用次数 = ceil(250/500) = 1 次批量调用
    - 单次调用的 exceptions 长度 = 250
    - recon_ctx 的 exception_created_count = 250
    - exception_creation_limited 不为 True
    """
    bulk_calls: list[dict[str, object]] = []
    update_payloads: list[dict[str, object]] = []

    async def fake_call_mcp_tool(name: str, payload: dict[str, object]) -> dict[str, object]:
        if name == "execution_run_exception_bulk_create":
            bulk_calls.append(payload)
            exceptions = list(payload.get("exceptions", []))
            return {
                "success": True,
                "created": len(exceptions),
            }
        if name == "execution_run_update":
            update_payloads.append(payload)
            return {
                "success": True,
                "run": {
                    "id": payload["run_id"],
                    "artifacts_json": payload["artifacts_json"],
                },
            }
        raise AssertionError(f"unexpected MCP tool: {name}")

    monkeypatch.setattr(nodes, "call_mcp_tool", fake_call_mcp_tool)

    # 250 条异常 > explosion_threshold(100)，触发爆炸路径；数量 < 500(批大小)所以仅1批
    n = 250
    anomalies = [
        {
            "item_id": f"run-full:{idx}:source_only:{idx}",
            "anomaly_type": "source_only",
            "join_key": [{"source_field": "订单号", "source_value": f"ORD-{idx}"}],
            "compare_values": [],
            "raw_record": {"订单号": f"ORD-{idx}"},
        }
        for idx in range(1, n + 1)
    ]
    state = {
        "auth_token": "token",
        "recon_ctx": {
            "execution_run_record": {"id": "run-full-001"},
            "scheme_code": "scheme-full-001",
            "run_plan": {
                "owner_mapping_json": {
                    "default_owner": {
                        "name": "财务负责人",
                        "identifier": "ding-user-full",
                    }
                },
                "plan_meta_json": {
                    "notify_policy": {
                        # threshold < n so explosion is triggered
                        "explosion_threshold": 100,
                        # no explicit sample_exception_limit → falls back to default 200
                    }
                },
            },
            "scheme": {
                "scheme_meta_json": {
                    "left_sources": [{"dataset_name": "交易订单明细表"}],
                    "right_sources": [{"dataset_name": "支付宝资金账单"}],
                }
            },
            "anomaly_items": anomalies,
        },
    }

    result = asyncio.run(nodes.create_exception_tasks_node(state))
    recon_ctx = result["recon_ctx"]

    # 必须走批量工具，不走逐条工具
    import math
    expected_bulk_calls = math.ceil(n / 500)  # 250/500 → 1 次
    assert len(bulk_calls) == expected_bulk_calls, (
        f"期望 {expected_bulk_calls} 次批量调用，实际 {len(bulk_calls)} 次"
    )
    # 第一批包含全部 250 条
    assert len(bulk_calls[0]["exceptions"]) == n, (
        f"批量调用的 exceptions 长度应为 {n}，实际 {len(bulk_calls[0]['exceptions'])}"
    )
    assert recon_ctx["exception_created_count"] == n
    assert recon_ctx["exception_total_count"] == n
    # explosion 触发了，但不应有截断标记
    assert recon_ctx.get("exception_creation_limited") is not True, (
        "全量落库模式下不应设置 exception_creation_limited=True"
    )


def test_create_exception_tasks_node_chunk_boundary_501(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """501 条差异应触发 2 次 bulk MCP 调用（500 + 1）。"""
    bulk_calls: list[dict[str, object]] = []
    _counter: dict[str, int] = {"n": 0}

    async def fake_call_mcp_tool(name: str, payload: dict[str, object]) -> dict[str, object]:
        if name == "execution_run_exception_bulk_create":
            chunk = list(payload.get("exceptions", []))
            refs: list[dict[str, object]] = []
            for exc in chunk:
                _counter["n"] += 1
                refs.append({"id": str(_counter["n"]), "anomaly_key": exc["anomaly_key"]})
            bulk_calls.append({"size": len(chunk)})
            return {"success": True, "created": len(chunk), "exceptions": refs}
        return {"success": True}

    monkeypatch.setattr(nodes, "call_mcp_tool", fake_call_mcp_tool)

    n = 501
    anomalies = [
        {"item_id": f"a-{i}", "anomaly_type": "source_only", "summary": f"差异 {i}"}
        for i in range(1, n + 1)
    ]
    state = {
        "auth_token": "token",
        "recon_ctx": {
            "execution_run_record": {"id": "run-chunk-001"},
            "scheme_code": "scheme-chunk-001",
            "run_plan": {
                "owner_mapping_json": {
                    "default_owner": {"name": "财务", "identifier": "owner-chunk"}
                },
                "plan_meta_json": {"notify_policy": {"explosion_threshold": 1000}},
            },
            "anomaly_items": anomalies,
        },
    }

    result = asyncio.run(nodes.create_exception_tasks_node(state))
    recon_ctx = result["recon_ctx"]

    assert len(bulk_calls) == 2, (
        f"501 条应分 2 次 bulk 调用（500+1），实际 {len(bulk_calls)} 次: {bulk_calls}"
    )
    assert bulk_calls[0]["size"] == 500
    assert bulk_calls[1]["size"] == 1
    assert recon_ctx["exception_created_count"] == n
    assert len(recon_ctx["created_exceptions"]) == n


def test_resolve_notify_policy_prefers_notify_policy_sample_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RECON_AUTO_NOTIFY_EXPLOSION_LIMIT", "9")

    policy = nodes._resolve_notify_policy(
        {
            "plan_meta_json": {
                "reminder_policy_json": {
                    "explosion_threshold": 50,
                    "explosion_sample_limit": 10,
                },
                "notify_policy": {
                    "explosion_threshold": 1000,
                    "sample_exception_limit": 200,
                },
            }
        }
    )

    assert policy == {
        "explosion_threshold": 1000,
        "sample_exception_limit": 200,
        "explosion_sample_limit": 200,
    }


def test_resolve_notify_policy_keeps_legacy_reminder_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RECON_AUTO_NOTIFY_EXPLOSION_LIMIT", raising=False)

    policy = nodes._resolve_notify_policy(
        {
            "plan_meta_json": {
                "reminder_policy": {
                    "explosion_threshold": 300,
                    "explosion_sample_limit": 40,
                }
            }
        }
    )

    assert policy["explosion_threshold"] == 300
    assert policy["sample_exception_limit"] == 40
    assert policy["explosion_sample_limit"] == 40


def test_resolve_notify_policy_prefers_notify_policy_across_aliases() -> None:
    policy = nodes._resolve_notify_policy(
        {
            "plan_meta_json": {
                "reminder_policy": {
                    "explosion_threshold": 300,
                    "sample_exception_limit": 50,
                },
                "notify_policy": {
                    "explosion_sample_limit": 20,
                },
            }
        }
    )

    assert policy["explosion_threshold"] == 300
    assert policy["sample_exception_limit"] == 20
    assert policy["explosion_sample_limit"] == 20


def test_resolve_notify_policy_uses_defaults_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RECON_AUTO_NOTIFY_EXPLOSION_LIMIT", raising=False)
    monkeypatch.delenv("RECON_EXCEPTION_SAMPLE_LIMIT", raising=False)

    policy = nodes._resolve_notify_policy({})

    assert policy == {
        "explosion_threshold": 1000,
        "sample_exception_limit": 200,
        "explosion_sample_limit": 200,
    }


def test_resolve_notify_policy_invalid_values_fall_back_to_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RECON_AUTO_NOTIFY_EXPLOSION_LIMIT", "0")
    monkeypatch.setenv("RECON_EXCEPTION_SAMPLE_LIMIT", "-5")

    policy = nodes._resolve_notify_policy(
        {
            "plan_meta_json": {
                "notify_policy": {
                    "explosion_threshold": 0,
                    "sample_exception_limit": -20,
                },
            }
        }
    )

    assert policy == {
        "explosion_threshold": 1000,
        "sample_exception_limit": 200,
        "explosion_sample_limit": 200,
    }


def test_resolve_notify_policy_uses_sample_limit_env_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RECON_AUTO_NOTIFY_EXPLOSION_LIMIT", raising=False)
    monkeypatch.setenv("RECON_EXCEPTION_SAMPLE_LIMIT", "25")

    policy = nodes._resolve_notify_policy(
        {
            "plan_meta_json": {
                "notify_policy": {
                    "explosion_threshold": 500,
                }
            }
        }
    )

    assert policy["explosion_threshold"] == 500
    assert policy["sample_exception_limit"] == 25
    assert policy["explosion_sample_limit"] == 25


def test_maybe_auto_notify_node_groups_exceptions_by_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _BatchNotifyAdapter()
    updated_payloads: list[tuple[str, dict[str, object]]] = []

    async def fake_update(auth_token: str, exception_id: str, payload: dict[str, object]) -> dict[str, object]:
        updated_payloads.append((exception_id, payload))
        return {
            "success": True,
            "exception": {
                "id": exception_id,
                **payload,
            },
        }

    monkeypatch.setattr(nodes, "load_company_channel_config_by_id", lambda channel_id: _channel_config())
    monkeypatch.setattr(nodes, "get_notification_adapter", lambda **kwargs: adapter)
    monkeypatch.setattr(nodes, "execution_run_exception_update", fake_update)
    monkeypatch.setenv("TALLY_PUBLIC_WEB_BASE_URL", "https://dev.tallyai.cn")

    created_exceptions = [
        {
            "exception_id": f"exception-{index}",
            "exception": {
                "id": f"exception-{index}",
                "run_id": "run-001",
                "anomaly_type": "source_only",
                "owner_name": "周行",
                "owner_identifier": "ding-user-001",
                "owner_contact_json": {},
                "summary": f"异常 {index}",
                "detail_json": {
                    "join_key": [{"source_field": "订单号", "source_value": f"ORD-{index}"}],
                    "compare_values": [],
                },
                "feedback_json": {},
            },
        }
        for index in range(1, 4)
    ]
    state = {
        "auth_token": "token",
        "recon_ctx": {
            "execution_run_record": {"id": "run-001"},
            "run_plan": {
                "plan_name": "泰斯支付宝对账",
                "channel_config_id": "channel-001",
                "plan_meta_json": {
                    "summary_recipient": {
                        "display_name": "汇总人",
                        "user_id": "summary-user",
                    }
                },
            },
            "scheme": {
                "scheme_name": "泰斯支付宝对账方案",
                "scheme_meta_json": {
                    "input_plan_json": {
                        "plans": [
                            {
                                "side": "left",
                                "target_table": "left_recon_ready",
                                "datasets": [{"resource_key": "public.ods_taesi_orders"}],
                            },
                            {
                                "side": "right",
                                "target_table": "right_recon_ready",
                                "datasets": [{"resource_key": "public.ods_alipay_signcustomer"}],
                            },
                        ]
                    }
                },
            },
            "biz_date": "2026-05-11",
            "ready_collections": [
                {
                    "binding": {
                        "role_code": "left_1",
                        "input_plan_target_table": "left_recon_ready",
                        "dataset_name": "交易订单明细表",
                    },
                },
                {
                    "binding": {
                        "role_code": "right_1",
                        "input_plan_target_table": "right_recon_ready",
                        "dataset_name": "支付宝资金账单 - 武汉泰斯网络科技有限公司-婉美de承诺",
                    },
                },
            ],
            "anomaly_items": [{"anomaly_type": "source_only"} for _ in created_exceptions],
            "created_exceptions": created_exceptions,
            "auto_notify_policy": {"explosion_threshold": 1, "explosion": True},
            "exception_sampling": {
                "enabled": True,
                "total_count": 1200,
                "sample_count": 3,
                "sample_limit": 200,
                "threshold": 1,
            },
        },
    }

    result = asyncio.run(nodes.maybe_auto_notify_node(state))
    recon_ctx = result["recon_ctx"]

    assert recon_ctx["auto_notify_status"] == "sent"
    assert recon_ctx["auto_notify_result"]["sent"] == 3
    assert len(adapter.reminder_calls) == 1
    assert adapter.reminder_calls[0]["assignee_user_id"] == "ding-user-001"
    assert "你有3条异常待处理" in str(adapter.reminder_calls[0]["todo_title"])
    owner_content = str(adapter.reminder_calls[0]["content"])
    assert "[查看差异](https://dev.tallyai.cn/recon/runs/run-001/exceptions?owner=ding-user-001)" in str(
        owner_content
    )
    assert "数据集 A" not in owner_content
    assert "数据集 B" not in owner_content
    assert "仅 交易订单明细表 存在（支付宝资金账单 - 武汉泰斯网络科技有限公司-婉美de承诺 缺失）" in owner_content
    assert len(adapter.bot_calls) == 1
    assert adapter.bot_calls[0]["content_type"] == "markdown"
    summary_content = str(adapter.bot_calls[0]["content"])
    assert "执行完成，待处理异常已催办责任人「周行」" in summary_content
    assert "待处理异常已按责任人聚合催办" not in summary_content
    assert "如异常数量或类型不符合预期，请检查方案配置或数据日期范围。" not in summary_content
    assert "异常明细：\n已创建全部 3 条差异明细" in summary_content
    assert "[查看差异](https://dev.tallyai.cn/recon/runs/run-001/exceptions)" in str(
        summary_content
    )
    assert len(updated_payloads) == 3
    for _exception_id, payload in updated_payloads:
        feedback_json = payload["feedback_json"]
        assert isinstance(feedback_json, dict)
        assert feedback_json["batch_source"] == "run_owner"
        assert feedback_json["batch_run_id"] == "run-001"
        assert feedback_json["batch_todo_id"] == "todo-1"
        assert feedback_json["public_detail_url"].endswith(
            "/recon/runs/run-001/exceptions?owner=ding-user-001"
        )


def test_create_exception_tasks_node_dedupes_anomaly_key_before_bulk_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """批量落库前按 anomaly_key 去重：250 条中 3 条重复 key，bulk 收到的数量 = 247。

    Postgres execute_values ON CONFLICT DO UPDATE 遇重复 key 会报
    "command cannot affect row a second time"导致整批失败；
    去重必须在分 chunk 之前完成，以避免跨 chunk 时依然带重复 key。
    """
    bulk_calls: list[list[str]] = []  # 每次调用收集到的 anomaly_key 列表

    async def fake_call_mcp_tool(name: str, payload: dict[str, object]) -> dict[str, object]:
        if name == "execution_run_exception_bulk_create":
            keys = [str(exc["anomaly_key"]) for exc in payload.get("exceptions", [])]
            bulk_calls.append(keys)
            return {"success": True, "created": len(keys)}
        return {"success": True}

    monkeypatch.setattr(nodes, "call_mcp_tool", fake_call_mcp_tool)

    # 250 条 anomaly，其中 3 条与已有 key 重复（item_id 索引 1、51、101 与 0、50、100 相同）
    base_anomalies = [
        {"item_id": f"run-dedup:{idx}", "anomaly_type": "source_only"}
        for idx in range(250)
    ]
    # 注入 3 条重复 item_id（与索引 0、50、100 完全一样）
    duplicates = [
        {"item_id": "run-dedup:0", "anomaly_type": "source_only"},
        {"item_id": "run-dedup:50", "anomaly_type": "source_only"},
        {"item_id": "run-dedup:100", "anomaly_type": "source_only"},
    ]
    anomalies = base_anomalies + duplicates  # total 253, unique 250

    state = {
        "auth_token": "token",
        "recon_ctx": {
            "execution_run_record": {"id": "run-dedup-001"},
            "scheme_code": "scheme-dedup",
            "run_plan": {
                "owner_mapping_json": {
                    "default_owner": {"name": "财务", "identifier": "owner-dedup"}
                },
                "plan_meta_json": {"notify_policy": {"explosion_threshold": 1000}},
            },
            "anomaly_items": anomalies,
        },
    }

    result = asyncio.run(nodes.create_exception_tasks_node(state))
    recon_ctx = result["recon_ctx"]

    # 有且仅有 1 次 bulk 调用（250 条 < 500 批大小）
    assert len(bulk_calls) == 1, f"期望 1 次 bulk 调用，实际 {len(bulk_calls)} 次"
    received_keys = bulk_calls[0]

    # 去重后 250 条（253 - 3 重复）
    assert len(received_keys) == 250, (
        f"去重后应传 250 条，实际 {len(received_keys)} 条"
    )
    # bulk 调用中无重复 key
    assert len(set(received_keys)) == len(received_keys), (
        "bulk_create 收到的 exceptions 中存在重复 anomaly_key"
    )
    # ctx 计数与实际落库数一致
    assert recon_ctx["exception_created_count"] == 250


def test_create_exception_tasks_node_logs_error_on_chunk_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """chunk 调用失败时应记录 error 日志，包含 run_id / chunk 序号 / 错误信息 / 丢弃条数。

    成功的 chunk 仍正常计入 created_count。
    """
    import logging

    call_count = {"n": 0}

    async def fake_call_mcp_tool(name: str, payload: dict[str, object]) -> dict[str, object]:
        if name == "execution_run_exception_bulk_create":
            call_count["n"] += 1
            # 第 1 chunk (idx=0) 成功，第 2 chunk (idx=1) 失败
            if call_count["n"] == 1:
                return {"success": True, "created": len(list(payload.get("exceptions", [])))}
            return {"success": False, "error": "ON CONFLICT DO UPDATE command cannot affect row"}
        return {"success": True}

    monkeypatch.setattr(nodes, "call_mcp_tool", fake_call_mcp_tool)

    # 501 条 → 2 chunks (500 + 1)
    n = 501
    anomalies = [
        {"item_id": f"log-{i}", "anomaly_type": "source_only"}
        for i in range(n)
    ]
    state = {
        "auth_token": "token",
        "recon_ctx": {
            "execution_run_record": {"id": "run-log-001"},
            "scheme_code": "scheme-log",
            "run_plan": {
                "owner_mapping_json": {
                    "default_owner": {"name": "财务", "identifier": "owner-log"}
                },
                "plan_meta_json": {"notify_policy": {"explosion_threshold": 1000}},
            },
            "anomaly_items": anomalies,
        },
    }

    with caplog.at_level(logging.ERROR, logger="graphs.recon.auto_scheme_run.nodes"):
        result = asyncio.run(nodes.create_exception_tasks_node(state))

    recon_ctx = result["recon_ctx"]

    # 第 2 chunk 失败 → 应有 error 日志
    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert error_records, "chunk 失败时应记录 error 日志"
    error_text = error_records[0].getMessage()
    assert "run-log-001" in error_text, f"日志应包含 run_id，实际: {error_text!r}"
    assert "ON CONFLICT" in error_text, f"日志应包含错误信息，实际: {error_text!r}"

    # chunk 0 成功 → created=500；chunk 1 失败 → created 不增加
    assert recon_ctx["exception_created_count"] == 500
