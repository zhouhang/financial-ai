# PostgreSQL 中喜马、西福、腾讯异业的 rule_template 查询结果

---

## 1. 喜马

### data_sources
| 数据源 | 字段映射 (field_roles) | 文件匹配 (file_pattern) |
|--------|------------------------|--------------------------|
| **business** | order_id: 第三方订单号<br>amount: 应结算平台金额<br>date: 支付时间 | 官网_*.xlsb, 官网_*.xlsm, 官网_*.xlsx, 官网_*.csv, 官网_*.xls |
| **finance** | order_id: sup订单号<br>amount: 发生-<br>date: 完成时间 | 合单_*.xlsx, 合单_*.csv, 合单_*.xls, 合单_*.xlsb, 合单_*.xlsm |

### tolerance
- date_format: %Y-%m-%d
- amount_diff_max: 0.1

### data_cleaning_rules
- **global**: 全局去重 (order_id)

### custom_validations
- missing_in_business, missing_in_finance, amount_mismatch

### rule_config_text
```
业务文件：金额保留2位小数
业务文件：订单号去除首尾空格
业务文件：订单号去掉开头单引号，并截取前21位
业务文件：相同的订单号按金额累加合并
财务文件：金额取绝对值
财务文件：金额保留2位小数
财务文件：订单号去除首尾空格
财务文件：订单号去掉开头单引号，并截取前21位
财务文件：相同的订单号按金额累加合并
```

---

## 2. 西福

### data_sources
| 数据源 | 字段映射 (field_roles) | 文件匹配 (file_pattern) |
|--------|------------------------|--------------------------|
| **business** | order_id: sp订单号<br>amount: 销售额<br>date: 订单时间<br>status: 状态 | 1767597466118_*.csv, *.xlsb, *.xls, *.xlsx, *.xlsm |
| **finance** | order_id: sup订单号<br>amount: 发生-<br>date: 完成时间<br>status: null | ads_finance_d_inc_channel_details_20260105152012277_0_*.xlsx, *.csv, *.xlsb, *.xls, *.xlsm |

### tolerance
- date_format: %Y-%m-%d
- amount_diff_max: 0.1

### data_cleaning_rules
- **global**: 全局去重 (order_id)
- **business**: 行过滤(104开头)、金额保留2位、订单号strip/截取21位、按订单号合并、删除空订单号
- **finance**: 行过滤(104开头)、金额取绝对值/保留2位、订单号strip/截取21位、按订单号合并、删除空记录

### custom_validations
- missing_in_business, missing_in_finance, amount_mismatch, order_status_mismatch

---

## 3. 腾讯异业

### data_sources
| 数据源 | 字段映射 (field_roles) | 文件匹配 (file_pattern) |
|--------|------------------------|--------------------------|
| **business** | order_id: roc_oid<br>amount: product_price<br>date: ftran_time<br>status: result, provide_result | 2025-12-01~2025-12-01对账流水_*.xlsb, *.xlsm, *.xlsx, *.csv, *.xls |
| **finance** | order_id: sup订单号<br>amount: 发生-<br>date: 完成时间 | ads_finance_d_inc_channel_details_20260105133821735_0_*.xlsb, *.csv, *.xls, *.xlsx, *.xlsm |

### tolerance
- date_format: %Y-%m-%d
- amount_diff_max: 0.1

### data_cleaning_rules
- **global**: 全局去重 (order_id)
- **business**: 金额保留2位、订单号strip/截取21位/转字符串、product_price除以100转元、按订单号合并、删除空订单号
- **finance**: 金额取绝对值/保留2位、订单号strip/截取21位/转字符串、按订单号合并、删除空记录

### custom_validations
- missing_in_business, missing_in_finance, amount_mismatch, order_status_mismatch

---

## 完整 JSON 已保存至
`/Users/kevin/.cursor/projects/Users-kevin-workspace-financial-ai/agent-tools/761308b8-1592-4923-81c6-f019edf9228f.txt`
