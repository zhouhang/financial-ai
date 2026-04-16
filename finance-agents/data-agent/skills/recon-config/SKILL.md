---
name: recon-config
description: 为 Tally 对账方案配置第 3 步生成或修订数据对账逻辑。仅在需要根据整理后的左右数据结构、对账目标、试跑反馈生成 recon 中文说明和 recon JSON 时使用。
---

# Recon Config Skill

先完成以下动作，再输出结果：

1. 阅读 `references/input-contract.md`，理解本轮整理后输入、字段结构和可回灌的试跑反馈。
2. 阅读 `references/recon-dsl-guardrails.md`，确认只能使用当前 recon 引擎支持的配置结构。
3. 需要参考示例时，再阅读 `references/recon-examples.md`。
4. 基于输入载荷生成一份可编辑的中文对账说明 `draft_text` 和一份 `effective_rule_json`。

始终遵守这些要求：

1. `source_file.table_name` 固定为 `left_recon_ready`。
2. `target_file.table_name` 固定为 `right_recon_ready`。
3. 匹配字段和金额字段必须来自整理后左右数据的真实字段，禁止虚构字段名。
4. 中文说明必须明确“按什么匹配、比对什么金额、容差是多少、输出哪些结果”。
5. 上下文里的 `business_name/field_label_map/fields/display_with_raw` 仅用于语义理解，规则 JSON 必须使用 `raw_name`，禁止输出中文字段名。
6. 不要发明 recon 引擎不支持的能力；如果做不到，写入 `unsupported_points`。

输出目标：

1. 返回结构化结果，至少包含 `draft_text`、`effective_rule_json`、`assumptions`、`change_summary`、`unsupported_points`。
2. `effective_rule_json` 必须可被当前 recon rule validator 接受。
