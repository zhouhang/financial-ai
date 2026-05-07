from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from tools import data_sources


def test_resolve_collection_driver_prefers_explicit_collection_config() -> None:
    source = {"source_kind": "platform_oauth", "provider_code": "alipay"}
    dataset = {
        "extract_config": {"collection_driver": "wrong_driver"},
        "meta": {
            "catalog_profile": {
                "collection_config": {
                    "collection_driver": "alipay_bill_download_import",
                },
            }
        },
    }

    assert data_sources._resolve_collection_driver(source, dataset) == "alipay_bill_download_import"


def test_resolve_collection_driver_keeps_taobao_platform_order_lines_compatibility() -> None:
    source = {"source_kind": "platform_oauth", "provider_code": "taobao"}
    dataset = {
        "extract_config": {
            "storage": "platform_order_lines",
            "platform_code": "taobao",
        },
    }

    assert data_sources._resolve_collection_driver(source, dataset) == "taobao_order_api"


def test_resolve_collection_driver_defaults_database_to_db_query() -> None:
    source = {"source_kind": "database", "provider_code": "postgres"}
    dataset = {"extract_config": {"storage": "dataset_collection_records"}}

    assert data_sources._resolve_collection_driver(source, dataset) == "db_query"


def test_resolve_collection_driver_defaults_alipay_platform_oauth() -> None:
    source = {"source_kind": "platform_oauth", "provider_code": "alipay"}
    dataset = {"extract_config": {"storage": "alipay_bill_lines"}}

    assert data_sources._resolve_collection_driver(source, dataset) == "alipay_bill_download_import"
