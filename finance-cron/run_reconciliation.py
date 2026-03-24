#!/usr/bin/env python3
"""
Cron-triggered recon runner.

It reads a config file describing the rule, the dataset inputs, and
the target data-agent internal API, then issues a single POST request
to start the headless recon.

TODO:
  - implement `fetch_dataset_payload` when the real data sources are known,
    honoring idempotency keys and retry policy.
  - persist run metadata/results for observability.
  - secure the internal auth token (e.g. service token rotation).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import requests
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("finance-cron")


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_payload(config: dict[str, Any]) -> dict[str, Any]:
    """
    Assemble the request that will be POSTed to data-agent.
    At this stage the dataset payloads are treated as-is; future
    implementation should resolve the dataset references to
    concrete data handles or snapshots.
    """
    return {
        "rule_code": config["rule_code"],
        "rule_id": config.get("rule_id", ""),
        "trigger_type": config.get("trigger_type", "cron"),
        "entry_mode": config.get("entry_mode", "dataset"),
        "run_context": config.get("run_context", {}),
        "recon_inputs": config.get("recon_inputs", []),
    }


def call_data_agent(payload: dict[str, Any], api_settings: dict[str, Any]) -> dict[str, Any]:
    url = api_settings["url"]
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_settings.get('auth_token', '')}",
    }
    timeout = api_settings.get("timeout_seconds", 30)
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Trigger a headless reconciliation run.")
    parser.add_argument("--config", type=Path, default=Path("config/cron_config.yaml"), help="YAML config path")
    args = parser.parse_args()

    config = load_config(args.config)
    payload = build_payload(config)

    logger.info("payload ready, submitting to data-agent internal recon API")
    try:
        result = call_data_agent(payload, config["api"])
    except Exception as exc:  # pragma: no cover
        logger.error("failed to call data-agent recon API", exc_info=exc)
        return 1

    logger.info("recon API returned: %s", json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
