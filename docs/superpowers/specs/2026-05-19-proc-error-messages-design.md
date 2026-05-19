# 数据整理报错提示友好化设计

日期:2026-05-19

## 问题

数据整理(proc)执行失败时,展示给用户的"详细错误"经常只有一个字段名。实例:

```
规则：逾期统计数据整理
错误摘要：数据整理执行失败
详细错误:

'公司'
```

技术和财务用户都无法据此定位问题。`'公司'` 实际是 pandas 列访问失败抛出的裸 `KeyError`,`str(KeyError('公司'))` 就等于 `"'公司'"`。

## 根因

- `proc/mcp_server/proc_rule.py` 顶层 `except Exception as e` 直接把 `str(e)` 放进返回结果的 `errors` / `message`(steps 路径约 464-475 行,merge 路径约 625-628 行)。
- `proc/mcp_server/steps_runtime.py` 中大量 `df[col]`、`groupby` 等列访问在列名不存在时抛裸 `KeyError`,逃逸后只剩字段名。
- 报错的"规则 / 错误摘要 / 详细错误"模板由 LLM agent 根据 proc 返回的 `{message, errors}` 拼装。LLM 只能照搬它拿到的内容——内容为空,展示就为空。
- steps_runtime 另有约 60 处 `raise ValueError(...)`,多数带细节,但用 `alias`、`step_id`、`source_alias`、`value.type` 等内部术语,财务用户看不懂。

修复必须在源头:让 proc 后端抛出/返回的错误本身就带原因。展示层(LLM)不改。

## 方案

仅改 `finance-mcp/proc/` 后端,产出结构化的成品错误文本(摘要 / 原因 / 建议三段),由现有 LLM 照常渲染。

报错区分两类,提示策略不同:

- **类①——用户可修的数据问题**(文件缺列、日期格式错等):提示具体怎么改。
- **类②——规则配置 bug**(不支持的 action、循环依赖等,只有规则作者/管理员能改):提示"规则配置有误,请联系管理员",不让财务用户白费劲。

采用分层做法:自定义异常 + 列访问守卫 + 顶层兜底翻译。

## 组件设计

### 1. 领域异常(`steps_runtime.py` 顶部,与 `FormulaEvaluationError` 并列)

```
ProcRuntimeError(Exception)        # 基类
├─ ProcUserDataError               # 类①:用户可修的数据问题
└─ ProcRuleConfigError             # 类②:规则配置 bug
```

每个异常携带三个结构化字段:

- `summary` — 一句话:什么失败了。
- `cause` — 为什么失败。
- `suggestion` — 怎么办。

`__str__` 返回格式化的三段文本。类别由异常子类区分,无需额外字段。

### 2. 上下文 helper(`StepsProcRuntime` 方法)

- `_rule_display_name()` → `rule_data.get("name")`,回退 `rule_code`。
- `_describe_table(table_name)` → 若 `table_name` 在 `self.table_file_map` 中,返回 `文件「<文件名>」`;否则返回 `中间结果「<表名>」`(中间结果是规则前序步骤产出的结果表,非上传文件)。
- `_require_columns(df, columns, table_name)` → 检查 `columns` 是否都在 `df.columns` 中;有缺失则抛 `ProcUserDataError`,文案套用下方"缺列"模板,缺多列时一次性列全。

### 3. 列访问守卫的落点

在"列名来自规则、对应上传文件列"的关键访问点改用 `_require_columns`,而非逐个 `df[col]` 都包:

- `groupby` 分组字段(约 563 行)
- 聚合字段(约 551 行)
- `filter` / `match` 的 key 字段
- `lookup` 字段
- 日期函数字段(约 1550 行)
- `primary_key` 字段

### 4. `steps_runtime.py` 约 60 处 `raise` 的归类改造

逐处归类,替换为对应领域异常:

**类② → `ProcRuleConfigError`**(技术细节进 `cause`,`suggestion` 统一为"联系管理员"):
`不支持的 step action`、`steps 依赖无法解析(可能存在循环依赖)`、`不支持的 row_write_mode / filter.type / aggregate operator / value.type / function`、`reference_filter / lookup / aggregate 缺少必填配置`、`导出列配置无效`、`公式包含不支持的语法 / 函数 / 标识符` 等。

**类① → `ProcUserDataError`**(套业务文案模板):
`表 '...' 未在上传文件或中间结果中找到`、`earliest_date 字段不存在 / 无可用日期`、`无法解析日期值 / 月份值`、`月份超出范围`、`不支持的文件格式`、`文件不存在` 等。

**保持原样:**
- `_FastPathNotSupported` 是内部控制流(快路径降级),不是错误,不动。
- `FormulaEvaluationError` 已有 `_build_formula_context_error` 富化上下文,保留其逻辑;仅在最终归类时区分:公式引用了不存在的列 → 类①,公式本身语法错 → 类②。

### 5. `proc_rule.py` 顶层兜底

steps 路径(约 464-475 行)与 merge 路径(约 625-628 行)的 `except` 后按异常类型分流:

- `ProcRuntimeError` 子类 → 用其 `summary / cause / suggestion` 渲染三段。
- 裸 `KeyError`(守卫未覆盖的漏网之鱼) → 兜底译为类①:`数据整理找不到列「<key>」`(此处拿不到文件名,但好过裸字段名)。
- 其它未知异常 → 类②:`系统执行出错,请联系管理员`,`str(e)` 仅写入日志。

返回结构:`message` 与 `errors` 改为格式化好的三段文本(proc 后端产出成品字符串,LLM 照渲)。

`merge_rule.py` 内若有面向用户的 `raise`,同样按上述两类归类改造。

## 报错文案模板

**类① 缺列:**
- summary:`规则「逾期统计数据整理」无法处理文件「借方-计提单明细」`
- cause:`该规则需要文件「借方-计提单明细」包含列「公司」,但文件中没有这一列。`
- suggestion:`请确认上传的文件含有「公司」列;若列名相近,检查是否有多余空格或命名不一致。`
- 多列缺失时,cause 一次性列全所有缺失列名。

**类① 日期/月份解析失败:**
- summary:`规则「X」无法解析日期`
- cause:`文件「Y」的列「Z」中,值「2026/13/01」不是有效日期。`
- suggestion:`请检查该列的日期格式是否规范。`

**类② 通用:**
- summary:`规则「X」配置有误`
- cause:保留技术细节(如 `不支持的 step action: xxx`),供管理员排查。
- suggestion:`这是规则配置问题,请联系管理员核对规则后重试。`

最终展示文本格式(三段):

```
数据整理失败:<summary>

原因:<cause>
建议:<suggestion>
```

## 测试

在 `finance-mcp/qa/`(与 `runtime_steps_spec.py` 同目录)新增测试:

1. **类① 缺列**:构造一条引用了 CSV 中不存在列的 steps 规则,跑 `StepsProcRuntime`,断言抛 `ProcUserDataError`,且文案同时包含规则名、文件名、缺失列名。
2. **类② 配置错**:构造一条含 `不支持的 step action` 的规则,断言抛 `ProcRuleConfigError`。
3. **顶层兜底**:断言一个守卫未覆盖、逃逸的裸 `KeyError` 经 `proc_rule` 处理后,被译为包含列名的类①文案,而非裸字段名。

## 范围

- 仅改 `finance-mcp/proc/`:`steps_runtime.py`、`proc_rule.py`、`merge_rule.py`。
- 不改 agent、不改前端、不改报错展示模板(展示仍由 LLM 渲染)。
- `_FastPathNotSupported` 内部控制流不动。

## 范围之外

- 不做执行前的"预校验/一次性列出所有缺列"(从任意 step 配置静态推导所需列复杂且易漏,YAGNI)。
- 不在 agent 侧加固定渲染模板(若后续发现 LLM 改写错误文本造成问题,再作为独立后续步骤处理)。
