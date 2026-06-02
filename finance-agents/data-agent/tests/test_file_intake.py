from __future__ import annotations

import sys
from pathlib import Path

DATA_AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(DATA_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(DATA_AGENT_ROOT))

from utils.file_intake import build_upload_name_maps, prepare_logical_upload_files


def test_oss_logical_upload_ref_is_mapped_without_local_file() -> None:
    logical_file = {
        "file_path": "/uploads/oss/company-1/a.csv",
        "display_name": "orders.csv",
        "original_filename": "orders.csv",
        "is_logical_split": False,
    }

    display_name_to_ref, ref_to_display_name = build_upload_name_maps([logical_file])

    assert display_name_to_ref["orders.csv"] == "/uploads/oss/company-1/a.csv"
    assert ref_to_display_name["/uploads/oss/company-1/a.csv"] == "orders.csv"


def test_oss_logical_upload_ref_with_columns_is_accepted_without_local_file() -> None:
    logical_file = {
        "file_path": "/uploads/oss/company-1/a.csv",
        "display_name": "orders.csv",
        "original_filename": "orders.csv",
        "columns": ["订单号", "金额"],
        "has_data_rows": True,
    }
    file_rule = {
        "file_validation_rules": {
            "validation_config": {},
            "table_schemas": [
                {
                    "table_name": "订单表",
                    "file_type": ["csv"],
                    "required_columns": ["订单号", "金额"],
                }
            ],
        }
    }

    result = prepare_logical_upload_files([logical_file], file_rule=file_rule)

    assert result["kept_count"] == 1
    assert result["logical_uploaded_files"][0]["file_path"] == "/uploads/oss/company-1/a.csv"
    assert result["files_with_columns"] == [
        {"file_name": "orders.csv", "columns": ["订单号", "金额"]}
    ]


def test_oss_logical_upload_ref_without_columns_does_not_resolve_local_file() -> None:
    result = prepare_logical_upload_files(
        [
            {
                "file_path": "/uploads/oss/company-1/a.csv",
                "display_name": "orders.csv",
                "original_filename": "orders.csv",
            }
        ],
        file_rule=None,
    )

    assert result["kept_count"] == 0
    assert result["prefilter_summary"][0]["file_path"] == "/uploads/oss/company-1/a.csv"
    assert result["prefilter_summary"][0]["reason_code"] == "empty_header"
