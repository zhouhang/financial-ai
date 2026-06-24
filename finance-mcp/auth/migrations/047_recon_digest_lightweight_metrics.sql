-- Trim digest layouts to metrics that the recon result itself reliably yields,
-- removing fields that require platform-specific semantics (pay/settle anchors,
-- T+N aging, refund encoding) which cannot be inferred generically and were
-- silently rendering as fake 0.
--   * 在途 now = left_only net amount (no aging split → no 正常在途/待核查).
--   * 退款 removed: refunded orders are already excluded by the valid-order cohort
--     upstream (proc 订单状态 filter), so a separate 退款 line double-counts.
--   * 回款周期 removed: requires both pay/settle timestamps.
-- Boss view.
UPDATE public.view_layout
SET sections = '[
      {
        "type": "narrative",
        "title": "今日摘要"
      },
      {
        "type": "funnel",
        "title": "资金到账总览（货款口径）",
        "caption": "货款口径",
        "metric_label_map": {
          "receivable_total": "买家实付",
          "settled_total": "已到账",
          "normal_in_transit_amount": "在途（未到账）"
        },
        "stages": [
          {"metric": "receivable_total", "label": "买家实付"},
          {"metric": "settled_total", "label": "已到账"},
          {"metric": "normal_in_transit_amount", "label": "在途（未到账）"}
        ]
      },
      {
        "type": "ranking_table",
        "title": "按店铺拆解",
        "entity": "plan_code",
        "metric_label_map": {
          "net_receivable_total": "应收净额",
          "settled_total": "已到账",
          "normal_in_transit_amount": "在途（未到账）"
        },
        "columns": [
          "net_receivable_total",
          "settled_total",
          "normal_in_transit_amount"
        ],
        "sort": "normal_in_transit_amount desc"
      },
      {
        "type": "locked_placeholder",
        "title": "未解锁指标",
        "items": [
          {
            "metric": "midplatform_gross_profit",
            "label": "中台口径含税毛利",
            "state": "beta",
            "unlock": "按 order_type/form_type 切口径并 beta 校验后解锁"
          },
          {
            "metric": "net_profit",
            "label": "净利润",
            "state": "locked",
            "unlock": "补费用明细+银行流水+经营费用台账"
          }
        ]
      }
    ]'::jsonb,
    updated_at = CURRENT_TIMESTAMP
WHERE domain = 'ecom'
  AND view = 'boss'
  AND version = 1;

-- Finance view: keep counts + diff list (both come straight from the match
-- result); drop 回款周期 and 健康度排名 (need timestamps / refund / aging).
UPDATE public.view_layout
SET sections = '[
      {
        "type": "metric_kpi",
        "title": "对账计数",
        "group_by": "recon_type",
        "group_label_map": {
          "fund": "资金对账",
          "order": "订单对账"
        },
        "metric_label_map": {
          "matched_exact_count": "完全匹配",
          "matched_with_diff_count": "金额差异",
          "source_only_count": "源侧单边",
          "target_only_count": "目标侧单边"
        },
        "metrics": [
          "matched_exact_count",
          "matched_with_diff_count",
          "source_only_count",
          "target_only_count"
        ]
      },
      {
        "type": "diff_list",
        "title": "差异清单",
        "group_by": "recon_type",
        "group_label_map": {
          "fund": "资金对账",
          "order": "订单对账"
        },
        "metric_label_map": {
          "order_no": "订单号",
          "reason_code": "归因",
          "is_true_diff": "是否真差异",
          "left_amount": "源侧金额",
          "right_amount": "目标侧金额",
          "diff_amount": "差异额",
          "processing_status": "处理状态"
        },
        "columns": [
          "order_no",
          "reason_code",
          "is_true_diff",
          "left_amount",
          "right_amount",
          "diff_amount",
          "processing_status"
        ]
      },
      {
        "type": "narrative",
        "title": "对账说明"
      }
    ]'::jsonb,
    updated_at = CURRENT_TIMESTAMP
WHERE domain = 'ecom'
  AND view = 'finance'
  AND version = 1;
