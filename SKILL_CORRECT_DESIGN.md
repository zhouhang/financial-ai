# Skill.md 正确使用方式设计

## 问题分析

### 当前错误的实现 ❌
```python
# helpers.py中硬编码
async def _classify_sheets_with_llm(sheets: list, file_path: str) -> dict:
    # 强制加载skill.md
    skill_path = Path(__file__).parent.parent.parent / "skills" / "intelligent-file-analyzer.skill.md"
    if skill_path.exists():
        skill_content = skill_path.read_text()  # 硬编码加载
        # 添加到prompt中
```

**问题**：
- ❌ Agent无法决定是否需要使用这个策略
- ❌ 所有情况都强制使用，增加处理时间和成本
- ❌ 简单场景也要读取和处理skill.md
- ❌ 不符合"agent自主决策"的设计理念

---

## 正确的设计方案

### 方案1: 注册为MCP工具（推荐） ✅

**原理**：将skill.md作为一个可调用的MCP工具，agent根据需要决定是否调用

#### 实现步骤

**Step 1**: 在MCP服务器中注册工具
```python
# finance-mcp/reconciliation/mcp_server/tools.py

async def _get_intelligent_analysis_strategy(args: Dict) -> Dict:
    """获取智能文件分析策略（来自skill.md）

    Args:
        args: {
            "scenario": "multi_sheet" | "multi_file" | "single_file" | "non_standard"
        }

    Returns:
        {
            "success": True,
            "strategy": "策略内容...",
            "scenario": "multi_sheet"
        }
    """
    scenario = args.get("scenario", "multi_sheet")
    skill_path = FINANCE_MCP_DIR.parent / "finance-agents" / "data-agent" / "app" / "skills" / "intelligent-file-analyzer.skill.md"

    if not skill_path.exists():
        return {"success": False, "error": "skill.md不存在"}

    try:
        content = skill_path.read_text(encoding="utf-8")

        # 根据scenario提取对应章节
        strategy_map = {
            "multi_sheet": "### 1. 多Sheet识别与分类",
            "non_standard": "### 2. 非标准格式处理",
            "single_file": "### 3. 单文件数据拆分",
            "multi_file": "### 4. 多文件智能配对"
        }

        section_title = strategy_map.get(scenario)
        if section_title and section_title in content:
            start_idx = content.find(section_title)
            # 找到下一个章节标题
            next_section_idx = content.find("### ", start_idx + len(section_title))
            if next_section_idx > start_idx:
                strategy = content[start_idx:next_section_idx].strip()
            else:
                strategy = content[start_idx:].strip()

            return {
                "success": True,
                "strategy": strategy,
                "scenario": scenario
            }

        return {"success": False, "error": f"未找到{scenario}对应的策略"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# 注册工具
@mcp_server.tool()
async def get_intelligent_analysis_strategy(scenario: str) -> dict:
    """获取智能文件分析策略

    当需要处理复杂文件场景时（多sheet、非标准格式、多文件配对等），
    可以调用此工具获取详细的分析策略指南。

    Args:
        scenario: 场景类型
            - "multi_sheet": 多Sheet识别与分类
            - "non_standard": 非标准格式处理
            - "single_file": 单文件数据拆分
            - "multi_file": 多文件智能配对

    Returns:
        包含策略内容的字典
    """
    return await _get_intelligent_analysis_strategy({"scenario": scenario})
```

**Step 2**: Agent在需要时调用
```python
# helpers.py

async def _classify_sheets_with_llm(sheets: list, file_path: str) -> dict:
    """使用LLM分类sheet类型"""
    from app.tools.mcp_client import call_mcp_tool

    # 优化：限制sheet数量
    MAX_SHEETS_PER_CALL = 15
    # ... (限制逻辑)

    # 构建基础prompt
    prompt = f"""你是财务数据分析专家。分析以下Excel文件的sheet，判断每个sheet的数据类型。

Sheet信息（共{len(sheets_desc)}个）：
{chr(10).join(sheets_desc)}

类型定义：
- business: 业务数据
- finance: 财务数据
- summary: 汇总表
- other: 其他
"""

    # 可选：如果sheet数量多或复杂，agent可以决定调用策略
    # （这个决策逻辑可以放在调用方，而不是这里硬编码）

    try:
        llm = get_llm(temperature=0.1)
        resp = await asyncio.wait_for(
            asyncio.to_thread(llm.invoke, prompt),
            timeout=30.0
        )
        # ... 处理响应
    except:
        # 降级策略
        return _fallback_classify_sheets_by_name(sheets)
```

**Step 3**: 在router_node或main_graph中让agent决定
```python
# nodes.py的file_analysis_node中

# 如果是复杂场景，agent可以决定是否需要策略指导
if complexity_level in ["medium", "complex"]:
    # Option A: 直接在prompt中告诉agent有这个工具可用
    # "如果需要详细的分析策略，可以调用get_intelligent_analysis_strategy工具"

    # Option B: 预先获取策略（由代码决定）
    # strategy = await call_mcp_tool("get_intelligent_analysis_strategy", {"scenario": "multi_sheet"})
    # 然后将strategy传递给LLM
    pass
```

**优点**：
- ✅ Agent可以自主决定是否需要策略
- ✅ 工具描述清晰，agent知道何时使用
- ✅ 可以按需加载不同场景的策略
- ✅ 符合MCP架构，统一管理
- ✅ 可以记录调用日志，便于分析

---

### 方案2: 作为LLM System Prompt的可选增强 ✅

**原理**：在构建LLM prompt时，由调用方决定是否包含skill.md策略

#### 实现步骤

**Step 1**: 创建策略加载辅助函数
```python
# helpers.py

def _load_analysis_strategy(scenario: str) -> str:
    """加载分析策略（可选调用）

    Args:
        scenario: "multi_sheet" | "multi_file" | etc.

    Returns:
        策略文本，如果失败返回空字符串
    """
    try:
        skill_path = Path(__file__).parent.parent.parent / "skills" / "intelligent-file-analyzer.skill.md"
        if not skill_path.exists():
            return ""

        content = skill_path.read_text(encoding="utf-8")
        # ... 提取对应章节
        return strategy_text
    except:
        return ""
```

**Step 2**: 调用方决定是否使用
```python
async def _classify_sheets_with_llm(sheets: list, file_path: str, use_strategy: bool = False) -> dict:
    """使用LLM分类sheet类型

    Args:
        sheets: sheet列表
        file_path: 文件路径
        use_strategy: 是否使用skill.md策略（由调用方决定）
    """

    prompt = f"""..."""

    # 只有明确指定才添加策略
    if use_strategy:
        strategy = _load_analysis_strategy("multi_sheet")
        if strategy:
            prompt += f"\n\n📖 分析策略参考:\n{strategy}"

    # ... 调用LLM
```

**Step 3**: 在调用处根据复杂度决定
```python
# _analyze_multi_sheet_files函数中

# 简单场景（sheet数量少）：不使用策略
if len(sheets) <= 5:
    sheet_types = await _classify_sheets_with_llm(sheets, file_path, use_strategy=False)

# 复杂场景（sheet数量多）：使用策略
else:
    sheet_types = await _classify_sheets_with_llm(sheets, file_path, use_strategy=True)
    logger.info("使用skill.md策略进行多sheet分析")
```

**优点**：
- ✅ 调用方可以控制是否使用策略
- ✅ 简单实现，不需要注册MCP工具
- ✅ 可以根据复杂度动态决定
- ✅ 避免简单场景的性能开销

**缺点**：
- ❌ 决策逻辑分散在代码中
- ❌ 没有统一的工具接口
- ❌ Agent层面感知不到这个能力

---

### 方案3: Agent主动查询（最灵活） ✅

**原理**：让Agent在router_node阶段就意识到有skill可用，主动决定是否查询

#### 实现步骤

**Step 1**: 在SYSTEM_PROMPT中告知agent
```python
# models.py或prompts.py

SYSTEM_PROMPT_WITH_SKILLS = """
你是财务对账助手。

可用能力：
- 标准对账流程：适用于2个标准格式文件
- 智能文件分析：处理复杂场景（多sheet、非标准格式、多文件）
  * 工具：get_intelligent_analysis_strategy
  * 场景：multi_sheet（多sheet）、non_standard（非标准格式）、multi_file（多文件配对）

当用户上传的文件较复杂时，你可以：
1. 先判断复杂度
2. 如果需要，调用get_intelligent_analysis_strategy获取策略
3. 根据策略进行分析
...
"""
```

**Step 2**: Agent自主决策
```python
# router_node或file_analysis_node中

# Agent看到复杂文件后，自主决定：
# "用户上传了包含30个sheet的Excel，这很复杂，我应该调用get_intelligent_analysis_strategy('multi_sheet')获取策略"

# LangGraph会自动处理工具调用
# Agent → 调用get_intelligent_analysis_strategy → 获得策略 → 使用策略分析
```

**优点**：
- ✅ 完全由agent自主决策
- ✅ 最灵活，可以应对各种情况
- ✅ 符合"agent主动性"的设计理念
- ✅ 可以记录agent的决策过程

**缺点**：
- ❌ 需要agent有较强的推理能力
- ❌ 可能增加一次LLM调用
- ❌ 需要更复杂的prompt工程

---

## 推荐方案

### 短期（快速实现）：方案2
- 调用方根据复杂度决定是否使用策略
- 修改`_classify_sheets_with_llm`接受`use_strategy`参数
- 在`_analyze_multi_sheet_files`中根据sheet数量决定

### 长期（最佳实践）：方案1 + 方案3
- 注册为MCP工具（方案1）
- 在system prompt中告知agent（方案3）
- Agent自主决定是否调用

---

## 回滚当前错误实现

需要回滚的代码：
1. `helpers.py:1368-1385` - 删除硬编码的skill.md加载
2. `nodes.py:170` - 删除"[使用skill.md策略]"硬编码提示
3. `finance-mcp/reconciliation/mcp_server/tools.py` - 删除硬编码的策略提示

恢复为agent可选调用的方式。

---

## 您的选择？

请选择您希望实现的方案：
- **方案1**：注册为MCP工具（推荐，最规范）
- **方案2**：可选参数控制（简单快速）
- **方案3**：Agent完全自主（最灵活，需要更好的prompt）
- **混合方案**：方案1+3（长期最佳）

我将根据您的选择进行实现。
