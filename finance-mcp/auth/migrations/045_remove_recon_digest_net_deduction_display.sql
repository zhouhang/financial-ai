-- Hide net deduction metrics from the standard boss digest layout until fee detail
-- data is collected. Runtime bundle filtering also protects existing/custom layouts.
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
    updated_at = CURRENT_TIMESTAMP
WHERE domain = 'ecom'
  AND view = 'boss'
  AND version = 1
  AND layout_code = 'ecom_boss_default_v1';
