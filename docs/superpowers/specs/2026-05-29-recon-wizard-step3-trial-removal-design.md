# 新建对账方案第三步去试跑设计

日期: 2026-05-29

## 背景

新建对账方案当前是 3 步向导:

1. 方案目标
2. 数据整理
3. 对账规则

第三步当前提供 `recon` 试跑按钮,并把试跑结果样例展示给用户。保存方案时如果
`reconTrialStatus` 不是 `passed`,还会自动执行一次 `trialReconDraft()` 并要求通过后才保存。

这个设计隐含前提是:样例数据能代表同一业务期间,左右样例里有可匹配记录。但实际创建方案时,
第三步使用的样例数据大概率不是同一批业务数据,左右侧经常对不上。因此试跑结果不能证明匹配字段、
金额口径和业务规则正确,反而容易让用户误解为"对账失败"或"规则不可用"。

## 目标

1. 第三步去掉用户可见的 `recon` 试跑功能。
2. 保存方案不再要求 `recon` 样例试跑通过。
3. 保存前仍拦截明确的规则结构问题:字段缺失、字段配置不完整、`recon_rule_json` 无法生成。
4. 样例数据无匹配不阻止保存,但保存确认文案提示"待真实运行验证"。
5. 持久化元数据不得误写成 `recon` 样例试跑已通过。

## 非目标

1. 不移除第二步 `proc` 试跑。第三步依赖第二步产出的左右整理结果,`proc` 试跑仍是必要门禁。
2. 不改底层 `recon DSL` 和正式执行引擎。
3. 不改运行计划和真实对账执行流程。
4. 不新建一套样例数据生成机制。
5. 不在第三步展示样例对账结果。

## 用户体验

第三步保留:

1. 匹配字段编辑。
2. 对比字段编辑。
3. 查看 JSON。
4. 结构校验状态或错误提示。

第三步移除:

1. `试跑验证` 按钮。
2. `正在试跑对账规则` 加载态。
3. 左右整理结果样例表。
4. 对账结果摘要。
5. 对账差异样例表。

保存确认文案调整为:

```text
当前方案已完成规则结构校验。样例数据不作为对账结果依据,请在首次真实运行后查看异常结果并修正。
确认保存方案吗?
```

如果结构校验失败,仍阻止保存并给出明确问题,例如:

```text
请先配置完整的匹配字段和对比字段。
```

或:

```text
对账规则字段不存在: 左侧字段「订单号」不在第二步输出字段中。
```

## 保存校验语义

保存方案时必须满足:

1. 用户已登录。
2. `proc_rule_json` 存在。
3. 第二步 `procTrialStatus === "passed"`。
4. 当前第三步字段配置可以编译出 `recon_rule_json`。
5. 至少存在一组完整匹配字段对。
6. 至少存在一组完整对比字段对。
7. 每个匹配字段和对比字段都能在第二步对应侧输出字段中找到。

保存方案时不再要求:

1. `reconTrialStatus === "passed"`。
2. 样例对账有匹配记录。
3. 样例对账结果没有差异。

样例无匹配、样例数据业务期间不一致、样例差异较多,都不作为保存阻断条件。

## 数据与状态

`scheme_meta_json.validation_summary.recon` 不再表示样例试跑通过,而表示结构校验完成:

```json
{
  "status": "structure_checked",
  "summary": "已完成对账规则结构校验,待首次真实运行验证"
}
```

顶层兼容字段同步写入:

```json
{
  "recon_trial_status": "structure_checked",
  "recon_trial_summary": "已完成对账规则结构校验,待首次真实运行验证"
}
```

如果现有 TypeScript 类型只允许 `idle | passed | needs_adjustment`,实现时应优先新增独立的保存校验状态,
避免把 `structure_checked` 塞进旧的 `TrialStatus` 后污染现有试跑语义。旧字段需要兼容后端或旧页面时,
可只在保存 payload 的 `scheme_meta_json` 中写入字符串,前端运行时状态继续使用更准确的结构校验状态。

## 组件影响

主要影响:

1. `finance-web/src/components/recon/SchemeWizardReconStep.tsx`
   - 移除 `onTrialRecon`、`trialDisabled`、`isTrialingRecon`、`reconTrialPreview` 等用户试跑 UI 依赖。
   - 保留 JSON 查看入口。
   - 显示结构校验提示,不显示样例试跑结果。
2. `finance-web/src/components/ReconWorkspace.tsx`
   - 保存时不再调用 `trialReconDraft()` 作为 `recon` 门禁。
   - 新增或抽出 `validateReconStructureForSave()` 之类的小 helper,避免继续扩大大文件职责。
   - 保存确认文案改为真实运行验证提示。
   - 保存 payload 的 `validation_summary.recon` 改为结构校验语义。
3. `finance-web/src/components/recon/schemeWizardState.ts`
   - 保存 payload 构造需要支持结构校验摘要。
   - 保持旧草稿状态兼容,避免破坏已有方案回填。

`ReconWorkspace.tsx` 已超过 7000 行,实现时不应继续把大量校验细节堆进主组件。字段存在性、字段对完整性和摘要生成
可以抽成 `finance-web/src/components/recon/reconStructureValidation.ts`。

## 校验 helper 设计

建议新增纯函数:

```ts
validateReconStructureForSave({
  matchFieldPairs,
  compareFieldPairs,
  leftOutputFields,
  rightOutputFields,
  reconRuleJson,
}): {
  ok: boolean;
  message: string;
  details: string[];
}
```

校验规则:

1. `reconRuleJson` 为空时失败。
2. 过滤掉左右字段任一为空的字段对。
3. 完整匹配字段对数量为 0 时失败。
4. 完整对比字段对数量为 0 时失败。
5. 左侧字段必须存在于左侧输出字段名集合。
6. 右侧字段必须存在于右侧输出字段名集合。
7. 对同一字段重复配置不阻断保存,第一版只在需要时作为 warning。

## 测试策略

1. 纯函数单元测试:
   - 完整匹配字段和对比字段通过。
   - 无匹配字段失败。
   - 无对比字段失败。
   - 左侧字段不存在失败。
   - 右侧字段不存在失败。
   - `reconRuleJson` 为空失败。
2. 组件测试:
   - 第三步不再渲染 `试跑验证`。
   - 第三步不再渲染对账样例表和对账结果摘要。
   - `查看 JSON` 仍可用。
3. 保存流程测试:
   - `procTrialStatus === "passed"` 且结构校验通过时,保存不会调用 `/recon/trial` 或设计会话 trial 接口。
   - 结构校验失败时不发起保存请求。
   - 保存请求中的 `validation_summary.recon.status` 是 `structure_checked`。

## 验收标准

1. 新建对账方案第三步看不到 `试跑验证` 按钮。
2. 第三步修改字段后不会出现"请重新试跑对账规则"这类提示。
3. 点击保存时不因为 `reconTrialStatus !== "passed"` 自动触发样例试跑。
4. 字段配置完整且 JSON 可生成时可以保存方案。
5. 字段配置缺失或字段不存在时保存被阻止并显示明确错误。
6. 保存确认文案明确提示首次真实运行后验证。
7. 保存 payload 不把 `recon` 标记为样例试跑通过。
