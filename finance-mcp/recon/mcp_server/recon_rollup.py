"""Generic canonical projection and rollup helpers for reconciliation digests."""
from __future__ import annotations

from typing import Any

import pandas as pd

CANONICAL_FIELDS = [
    "order_no",
    "receivable_amount",
    "refund_amount",
    "settled_amount",
    "pay_time",
    "settle_time",
]
OPTIONAL_CANONICAL_FIELDS = ["channel", "finish_time", "order_status"]
REQUIRED_CANONICAL_FIELDS = set(CANONICAL_FIELDS)
MONEY_FIELDS = {"receivable_amount", "refund_amount", "settled_amount"}
DATETIME_FIELDS = {"pay_time", "settle_time", "finish_time"}

_COHORT = {"matched_exact", "matched_with_diff", "left_only"}
_SETTLED = {"matched_exact", "matched_with_diff"}
_BUCKET_TO_STATUS = {
    "matched_exact": "matched_exact",
    "matched_with_diff": "matched_with_diff",
    "source_only": "left_only",
    "target_only": "right_only",
}


def validate_rollup_field_mapping(field_mapping: dict[str, Any]) -> None:
    """Validate that the mapping can project all required canonical fields."""
    canonical_cfg = (field_mapping or {}).get("canonical", {})
    missing = sorted(REQUIRED_CANONICAL_FIELDS - set(canonical_cfg))
    if missing:
        raise ValueError(f"missing required canonical fields: {missing}")


def _empty_series(index: pd.Index) -> pd.Series:
    return pd.Series([pd.NA] * len(index), index=index)


def _to_money(series: pd.Series) -> pd.Series:
    cleaned = series.astype(str).str.strip().str.replace(",", "", regex=False)
    cleaned = cleaned.replace({"": pd.NA, "None": pd.NA, "nan": pd.NA, "<NA>": pd.NA})
    return pd.to_numeric(cleaned, errors="coerce")


def _project_field(
    bucket: pd.DataFrame,
    canonical_name: str,
    field_mapping: dict[str, Any],
) -> pd.Series:
    canonical_cfg = (field_mapping or {}).get("canonical", {})
    spec = canonical_cfg.get(canonical_name)
    if not isinstance(spec, dict):
        return _empty_series(bucket.index)
    side = str(spec.get("side") or "").strip()
    source_name = str(spec.get("from") or "").strip()
    col = f"{side}_{source_name}" if side and source_name else ""
    raw = bucket[col] if col and col in bucket.columns else _empty_series(bucket.index)
    if canonical_name in MONEY_FIELDS:
        return _to_money(raw)
    if canonical_name in DATETIME_FIELDS:
        return pd.to_datetime(raw, errors="coerce")
    return raw.astype("object")


def project_bucket_to_canonical(
    bucket: pd.DataFrame,
    match_status: str,
    field_mapping: dict[str, Any],
) -> pd.DataFrame:
    """Project one diff bucket into canonical fields and tag its match status."""
    validate_rollup_field_mapping(field_mapping)
    bucket = bucket if isinstance(bucket, pd.DataFrame) else pd.DataFrame()
    out = pd.DataFrame(index=bucket.index)
    for canonical_name in [*CANONICAL_FIELDS, *OPTIONAL_CANONICAL_FIELDS]:
        out[canonical_name] = _project_field(bucket, canonical_name, field_mapping)
    out["match_status"] = match_status
    return out.reset_index(drop=True)


def _numeric_series(df: pd.DataFrame, key: str) -> pd.Series:
    if key not in df:
        return pd.Series([0.0] * len(df), index=df.index, dtype="float64")
    return pd.to_numeric(df[key], errors="coerce").fillna(0.0)


def _datetime_series(df: pd.DataFrame, key: str) -> pd.Series:
    if key not in df:
        return pd.Series([pd.NaT] * len(df), index=df.index, dtype="datetime64[ns]")
    return pd.to_datetime(df[key], errors="coerce")


def compute_recon_rollup(
    canonical_df: pd.DataFrame,
    as_of_ts: pd.Timestamp,
    stuck_days_n: int,
) -> dict[str, Any]:
    """Compute deterministic recon_period_rollup metrics from canonical rows."""
    df = canonical_df.copy() if isinstance(canonical_df, pd.DataFrame) else pd.DataFrame()
    if df.empty:
        df = pd.DataFrame(columns=CANONICAL_FIELDS + OPTIONAL_CANONICAL_FIELDS + ["match_status"])
    if "match_status" not in df:
        df["match_status"] = ""

    match_status = df["match_status"].astype(str)
    receivable = _numeric_series(df, "receivable_amount")
    refund = _numeric_series(df, "refund_amount")
    settled = _numeric_series(df, "settled_amount")
    net_receivable = (receivable - refund).clip(lower=0.0)

    cohort = match_status.isin(_COHORT)
    settled_mask = match_status.isin(_SETTLED)
    in_transit = match_status.eq("left_only")
    diff_mask = match_status.eq("matched_with_diff")

    as_of_date = pd.Timestamp(as_of_ts).normalize()
    pay_time = _datetime_series(df, "pay_time")
    aging_days = (as_of_date - pay_time.dt.normalize()).dt.days
    normal_mask = in_transit & (aging_days <= int(stuck_days_n))
    stuck_mask = in_transit & (aging_days > int(stuck_days_n))

    settle_time = _datetime_series(df, "settle_time")
    payback_days = (settle_time - pay_time).dt.days
    payback_valid = settled_mask & pay_time.notna() & settle_time.notna()

    net_recv_settled_sum = float(net_receivable[settled_mask].sum())
    net_deduction_total = float((net_receivable[settled_mask] - settled[settled_mask]).sum())

    return {
        "receivable_amount_total": float(receivable[cohort].sum()),
        "refund_amount_total": float(refund[cohort].sum()),
        "net_receivable_amount_total": float(net_receivable[cohort].sum()),
        "settled_amount_total": float(settled[settled_mask].sum()),
        "normal_in_transit_amount_total": float(net_receivable[normal_mask].sum()),
        "stuck_amount_total": float(net_receivable[stuck_mask].sum()),
        "net_deduction_total": net_deduction_total,
        "net_deduction_rate": (
            net_deduction_total / net_recv_settled_sum if net_recv_settled_sum > 0 else None
        ),
        "diff_amount_total": float((net_receivable[diff_mask] - settled[diff_mask]).sum()),
        "cohort_order_count": int(cohort.sum()),
        "settled_order_count": int(settled_mask.sum()),
        "normal_in_transit_count": int(normal_mask.sum()),
        "stuck_order_count": int(stuck_mask.sum()),
        "matched_with_diff_count": int(diff_mask.sum()),
        "source_only_count": int(in_transit.sum()),
        "target_only_count": int(match_status.eq("right_only").sum()),
        "payback_days_sum": float(payback_days[payback_valid].sum()),
        "payback_days_count": int(payback_valid.sum()),
    }


def canonical_from_diff_result(
    diff_result: dict[str, pd.DataFrame],
    field_mapping: dict[str, Any],
) -> pd.DataFrame:
    """Project all diff buckets into a single canonical DataFrame."""
    parts = []
    for bucket_key, match_status in _BUCKET_TO_STATUS.items():
        bucket = diff_result.get(bucket_key)
        if bucket is None or len(bucket) == 0:
            continue
        parts.append(project_bucket_to_canonical(bucket, match_status, field_mapping))
    if not parts:
        return pd.DataFrame(columns=CANONICAL_FIELDS + OPTIONAL_CANONICAL_FIELDS + ["match_status"])
    return pd.concat(parts, ignore_index=True)


def rollup_from_diff_result(
    diff_result: dict[str, pd.DataFrame],
    field_mapping: dict[str, Any],
    as_of_ts: pd.Timestamp,
    stuck_days_n: int,
) -> dict[str, Any]:
    """Project diff buckets into canonical rows and compute rollup metrics."""
    canonical_df = canonical_from_diff_result(diff_result, field_mapping)
    return compute_recon_rollup(canonical_df, as_of_ts=as_of_ts, stuck_days_n=stuck_days_n)
