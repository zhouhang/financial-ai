---
name: proc-config
description: 为 Tally 对账方案配置第 2 步生成或修订数据整理配置。仅在需要根据对账目标、左右数据集描述、字段结构、试跑反馈生成 proc 中文说明和 proc JSON 时使用。
---

# Proc Config Skill

先完成以下动作，再输出结果：

1. 阅读 `references/input-contract.md`，理解本轮输入载荷、左右数据集上下文和可回灌的试跑反馈。
2. 阅读 `references/proc-dsl-guardrails.md`，确认只能使用当前 proc 引擎支持的字段、动作和目标表。
3. 需要参考示例时，再阅读 `references/proc-examples.md`。
4. 基于输入载荷生成一份可编辑的中文整理说明 `draft_text` 和一份 `effective_rule_json`。

始终遵守这些要求：

1. 只生成两份整理输出：`left_recon_ready` 和 `right_recon_ready`。
2. `write_dataset.sources[].table` 必须引用本轮输入中真实存在的数据集 `table_name`，禁止留空，禁止写 `unknown`。
3. 中文说明必须写清楚“用了哪些数据集、如何过滤/汇总/映射、最终产出什么字段”，不要写空泛步骤。
4. 上下文里的 `business_name/field_label_map/fields/display_with_raw` 仅用于语义理解，规则 JSON 必须使用 `raw_name`，禁止输出中文字段名。
5. 不要发明 DSL 不存在的动作、字段或函数；如果做不到，写入 `unsupported_points`。
6. 输出前自查一次：中文说明与 `effective_rule_json` 必须表达同一套整理逻辑。

输出目标：

1. 返回结构化结果，至少包含 `draft_text`、`effective_rule_json`、`assumptions`、`change_summary`、`unsupported_points`。
2. `effective_rule_json` 必须可被当前 proc rule validator 接受。
