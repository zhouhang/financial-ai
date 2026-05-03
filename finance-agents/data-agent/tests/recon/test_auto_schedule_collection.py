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
auto_run_service = importlib.import_module("graphs.recon.auto_run_service")


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
    assert "异常详情：仅 FP订单表 存在（交易订单明细表 缺失）" in bot_content


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
