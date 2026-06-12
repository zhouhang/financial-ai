from __future__ import annotations

from tools import execution_exception_detail_hydration, execution_runs


def test_public_exception_bundle_hydrates_legacy_target_only_source_record(monkeypatch) -> None:
    run = {
        "id": "run-1",
        "company_id": "company-1",
        "scheme_code": "scheme-1",
        "run_context_json": {"biz_date": "2026-05-27"},
        "source_snapshot_json": {
            "biz_date": "2026-05-27",
            "collections": [
                {
                    "binding": {
                        "data_source_id": "source-right",
                        "dataset_id": "dataset-right",
                        "dataset_code": "sold-orders",
                        "resource_key": "browser-collection-sold-orders@1",
                        "source_kind": "browser_playbook",
                        "dataset_source_type": "browser_collection_records",
                        "input_plan_target_table": "right_recon_ready",
                    }
                }
            ],
        },
    }
    scheme = {
        "scheme_meta_json": {
            "proc_rule_json": {
                "steps": [
                    {
                        "action": "write_dataset",
                        "target_table": "right_recon_ready",
                        "sources": [
                            {
                                "alias": "source_1",
                                "table": "browser-collection-sold-orders@1",
                            }
                        ],
                        "mappings": [
                            {
                                "target_field": "订单编号",
                                "value": {
                                    "type": "source",
                                    "source": {
                                        "alias": "source_1",
                                        "field": "订单编号",
                                    },
                                },
                            },
                            {
                                "target_field": "买家实付金额",
                                "value": {
                                    "type": "source",
                                    "source": {
                                        "alias": "source_1",
                                        "field": "买家实付金额",
                                    },
                                },
                            },
                        ],
                    }
                ]
            }
        }
    }
    exception = {
        "id": "exception-1",
        "company_id": "company-1",
        "run_id": "run-1",
        "detail_json": {
            "anomaly_type": "target_only",
            "source_ref": "left_recon_ready",
            "target_ref": "right_recon_ready",
            "join_key": [
                {
                    "source_field": "平台订单客户订单号",
                    "target_field": "订单编号",
                    "source_value": None,
                    "target_value": "5118001236570006333",
                }
            ],
            "raw_record": {
                "订单编号": "5118001236570006333",
                "买家实付金额": "0.00",
            },
        },
    }

    def fake_bundle(**_: object) -> dict[str, object]:
        return {
            "run": run,
            "scheme": scheme,
            "run_plan": {},
            "exceptions": [exception],
            "count": 1,
            "total": 1,
            "limit": 100,
            "offset": 0,
        }

    browser_calls: list[dict[str, object]] = []

    def fake_browser_records(**kwargs: object) -> list[dict[str, object]]:
        browser_calls.append(kwargs)
        return [
            {
                "payload": {
                    "订单编号": "5118001236570006333",
                    "订单付款时间": "2026-05-27 12:00:00",
                    "商品标题": "虚拟充值订单",
                    "买家实付金额": "0.00",
                }
            }
        ]

    monkeypatch.setattr(execution_runs.auth_db, "get_public_execution_run_exception_bundle", fake_bundle)
    monkeypatch.setattr(
        execution_exception_detail_hydration.auth_db,
        "list_browser_collection_records",
        fake_browser_records,
    )

    result = execution_runs._run_public_exception_bundle({"run_id": "run-1"})

    detail_json = result["exceptions"][0]["detail_json"]
    assert detail_json["target_record"]["商品标题"] == "虚拟充值订单"
    assert detail_json["target_record"]["订单付款时间"] == "2026-05-27 12:00:00"
    assert browser_calls[0]["filters"] == {"订单编号": "5118001236570006333"}
    assert browser_calls[0]["dataset_id"] == "dataset-right"
    assert browser_calls[0]["biz_date"] == "2026-05-27"


def test_exception_hydration_does_not_cross_biz_date_for_missing_side(monkeypatch) -> None:
    run = {
        "id": "run-1",
        "company_id": "company-1",
        "scheme_code": "scheme-1",
        "run_context_json": {"biz_date": "2026-06-09"},
        "source_snapshot_json": {
            "biz_date": "2026-06-09",
            "collections": [
                {
                    "binding": {
                        "data_source_id": "source-left",
                        "dataset_id": "dataset-left",
                        "dataset_code": "sold-orders",
                        "resource_key": "browser-collection-sold-orders@1",
                        "source_kind": "browser_playbook",
                        "dataset_source_type": "browser_collection_records",
                        "input_plan_target_table": "left_recon_ready",
                    }
                }
            ],
        },
    }
    scheme = {
        "scheme_meta_json": {
            "proc_rule_json": {
                "steps": [
                    {
                        "action": "write_dataset",
                        "target_table": "left_recon_ready",
                        "sources": [
                            {
                                "alias": "source_1",
                                "table": "browser-collection-sold-orders@1",
                            }
                        ],
                        "mappings": [
                            {
                                "target_field": "订单编号",
                                "value": {
                                    "type": "source",
                                    "source": {
                                        "alias": "source_1",
                                        "field": "订单编号",
                                    },
                                },
                            }
                        ],
                    }
                ]
            }
        }
    }
    exception = {
        "id": "exception-1",
        "company_id": "company-1",
        "run_id": "run-1",
        "detail_json": {
            "anomaly_type": "matched_with_diff",
            "source_ref": "left_recon_ready",
            "target_ref": "right_recon_ready",
            "join_key": [
                {
                    "source_field": "订单编号",
                    "target_field": "订单号",
                    "source_value": None,
                    "target_value": "3306514334587002794",
                }
            ],
            "source_record": {"订单编号": None},
        },
    }

    browser_calls: list[dict[str, object]] = []

    def fake_browser_records(**kwargs: object) -> list[dict[str, object]]:
        browser_calls.append(kwargs)
        if kwargs.get("biz_date"):
            return []
        return [
            {
                "payload": {
                    "订单编号": "3306514334587002794",
                    "订单付款时间": "2026-06-08 15:13:48",
                    "买家实付金额": "197.98",
                }
            }
        ]

    monkeypatch.setattr(
        execution_exception_detail_hydration.auth_db,
        "list_browser_collection_records",
        fake_browser_records,
    )

    result = execution_exception_detail_hydration.hydrate_execution_exception_details(
        run=run,
        scheme=scheme,
        exceptions=[exception],
    )

    detail_json = result[0]["detail_json"]
    assert detail_json["source_record"] == {"订单编号": None}
    assert len(browser_calls) == 1
    assert browser_calls[0]["biz_date"] == "2026-06-09"
    assert browser_calls[0]["filters"] == {"订单编号": "3306514334587002794"}
