-- Boss digest tweaks per review: drop the "（未到账）" qualifier on 在途 (老板自明),
-- and remove the 未解锁指标 (locked_placeholder) teaser section.
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
          "normal_in_transit_amount": "在途"
        },
        "stages": [
          {"metric": "receivable_total", "label": "买家实付"},
          {"metric": "settled_total", "label": "已到账"},
          {"metric": "normal_in_transit_amount", "label": "在途"}
        ]
      },
      {
        "type": "ranking_table",
        "title": "按店铺拆解",
        "entity": "plan_code",
        "metric_label_map": {
          "net_receivable_total": "应收净额",
          "settled_total": "已到账",
          "normal_in_transit_amount": "在途"
        },
        "columns": [
          "net_receivable_total",
          "settled_total",
          "normal_in_transit_amount"
        ],
        "sort": "normal_in_transit_amount desc"
      }
    ]'::jsonb,
    updated_at = CURRENT_TIMESTAMP
WHERE domain = 'ecom'
  AND view = 'boss'
  AND version = 1;
