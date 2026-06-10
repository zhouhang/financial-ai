-- view_layout: generic report section configuration for public digest detail pages.
CREATE TABLE IF NOT EXISTS public.view_layout (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    layout_code varchar(128) NOT NULL,
    domain varchar(32) NOT NULL,
    view varchar(32) NOT NULL,
    sections jsonb DEFAULT '[]'::jsonb NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    status varchar(32) DEFAULT 'active' NOT NULL,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz DEFAULT CURRENT_TIMESTAMP
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'view_layout_unique'
          AND conrelid = 'public.view_layout'::regclass
    ) THEN
        ALTER TABLE ONLY public.view_layout
            ADD CONSTRAINT view_layout_unique UNIQUE (domain, view, version);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_view_layout_domain_view
    ON public.view_layout (domain, view, status, version DESC);

INSERT INTO public.view_layout (layout_code, domain, view, sections, version, status)
VALUES
(
    'ecom_boss_default_v1',
    'ecom',
    'boss',
    '[
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
          "refund_total": "退款",
          "settled_total": "已到账",
          "normal_in_transit_amount": "正常在途",
          "stuck_amount": "待核查"
        },
        "stages": [
          {"metric": "receivable_total", "label": "买家实付"},
          {"metric": "refund_total", "label": "退款"},
          {"metric": "settled_total", "label": "已到账"},
          {"metric": "normal_in_transit_amount", "label": "正常在途"},
          {"metric": "stuck_amount", "label": "待核查"}
        ]
      },
      {
        "type": "ranking_table",
        "title": "按店铺拆解",
        "entity": "plan_code",
        "metric_label_map": {
          "net_receivable_total": "应收净额",
          "settled_total": "已到账",
          "normal_in_transit_amount": "正常在途",
          "stuck_amount": "待核查"
        },
        "columns": [
          "net_receivable_total",
          "settled_total",
          "normal_in_transit_amount",
          "stuck_amount"
        ],
        "sort": "stuck_amount desc"
      },
      {
        "type": "metric_kpi",
        "title": "平台综合扣减",
        "caption": "含手续费/营销，非精确佣金",
        "metric_label_map": {
          "net_deduction_total": "综合扣减额",
          "net_deduction_rate": "综合扣减率"
        },
        "metrics": [
          "net_deduction_total",
          "net_deduction_rate"
        ]
      },
      {
        "type": "ranking_table",
        "title": "扣减率排名",
        "entity": "plan_code",
        "metric_label_map": {
          "net_deduction_total": "综合扣减额",
          "net_deduction_rate": "综合扣减率"
        },
        "columns": [
          "net_deduction_total",
          "net_deduction_rate"
        ],
        "sort": "net_deduction_rate desc"
      },
      {
        "type": "alert_list",
        "title": "钱卡住预警（疑似）",
        "alert_code": "unsettled_amount_aged",
        "drilldown": {
          "source": "canonical",
          "filter": "match_status=left_only & aging>N",
          "metric_label_map": {
            "order_no": "订单号",
            "net_receivable": "净应收",
            "aging_days": "挂账天数"
          },
          "columns": [
            "order_no",
            "net_receivable",
            "aging_days"
          ]
        }
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
    1,
    'active'
)
ON CONFLICT (domain, view, version) DO UPDATE
SET layout_code = EXCLUDED.layout_code,
    sections = EXCLUDED.sections,
    status = EXCLUDED.status,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO public.view_layout (layout_code, domain, view, sections, version, status)
VALUES
(
    'ecom_finance_default_v1',
    'ecom',
    'finance',
    '[
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
        "type": "distribution",
        "title": "回款周期",
        "entity": "plan_code",
        "metric_label_map": {
          "payback_days_avg": "平均回款天数",
          "payback_days_p90": "P90 回款天数"
        },
        "metrics": [
          "payback_days_avg",
          "payback_days_p90"
        ]
      },
      {
        "type": "ranking_table",
        "title": "健康度排名",
        "entity": "plan_code",
        "metric_label_map": {
          "in_transit_ratio": "在途占比",
          "refund_ratio": "退款率",
          "stale_diff_days": "最长挂账天数",
          "health_level": "健康度"
        },
        "columns": [
          "in_transit_ratio",
          "refund_ratio",
          "stale_diff_days",
          "health_level"
        ],
        "sort": "health_level desc"
      },
      {
        "type": "narrative",
        "title": "对账说明"
      }
    ]'::jsonb,
    1,
    'active'
)
ON CONFLICT (domain, view, version) DO UPDATE
SET layout_code = EXCLUDED.layout_code,
    sections = EXCLUDED.sections,
    status = EXCLUDED.status,
    updated_at = CURRENT_TIMESTAMP;
