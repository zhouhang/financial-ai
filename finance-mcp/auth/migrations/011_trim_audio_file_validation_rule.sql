UPDATE rule_detail
SET rule = jsonb_set(
  rule::jsonb,
  '{file_validation_rules,table_schemas}',
  '[
    {
      "table_id": "XIMA_HE_DAN",
      "file_type": ["xls", "xlsx", "csv"],
      "table_name": "喜马合单表",
      "table_type": "source",
      "description": "喜马合单数据表，包含订单汇总和渠道结算信息",
      "is_required": true,
      "column_aliases": {
        "发生+": ["发生加", "收入", "income"],
        "发生-": ["发生减", "支出", "expense"],
        "订单号": ["订单编号", "order_no"],
        "完成时间": ["完成日期", "finish_time"],
        "渠道名称": ["channel_name"],
        "结算类型": ["settlement_type"],
        "订单来源": ["来源", "order_source"],
        "订单类型": ["order_type"],
        "渠道供应商": ["供应商", "channel_supplier"],
        "渠道所属公司": ["所属公司", "channel_company"]
      },
      "max_match_count": 1,
      "required_columns": [
        "完成时间",
        "订单来源",
        "订单号",
        "订单类型",
        "结算类型",
        "渠道所属公司",
        "渠道供应商",
        "渠道名称",
        "发生+",
        "发生-"
      ]
    },
    {
      "table_id": "XIMA_GUAN_WANG",
      "file_type": ["xls", "xlsx", "csv"],
      "table_name": "喜马官网表",
      "table_type": "target",
      "description": "喜马官网订单明细表，包含订单详情和商品信息",
      "is_required": true,
      "column_aliases": {
        "分成比例": ["分成", "share_ratio"],
        "商品金额": ["product_amount", "商品总价"],
        "实付金额": ["actual_amount", "实际支付金额"],
        "支付时间": ["pay_time", "付款时间"],
        "结算状态": ["settlement_status"],
        "喜马订单号": ["订单号", "xima_order_no", "order_no"],
        "合作方分销收入": ["分销收入", "partner_income"],
        "应结算平台金额": ["结算金额", "settlement_amount"]
      },
      "max_match_count": 1,
      "required_columns": [
        "喜马订单号",
        "支付时间",
        "分成比例",
        "合作方分销收入",
        "应结算平台金额",
        "结算状态",
        "商品金额",
        "实付金额"
      ]
    }
  ]'::jsonb
)
WHERE id = 6;
