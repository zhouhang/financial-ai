"""对账规则配置解析模块

使用 LLM 解析用户自然语言输入为规则配置 JSON。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _parse_rule_config_json_snippet(user_input: str, current_config_items: list[dict] = None, field_mappings: dict = None) -> dict[str, Any]:
    """使用 LLM 根据 JSON 模板解析用户输入，返回 JSON 片段。
    
    Args:
        user_input: 用户自然语言输入
        current_config_items: 当前已添加的配置项列表
        field_mappings: 字段映射，包含 business 和 finance 的字段映射关系
    
    Returns:
        {
            "action": "add" | "delete" | "update",
            "json_snippet": {...},  # 要添加/更新的JSON片段
            "description": "用户友好的描述"
        }
    """
    from app.utils.llm import get_llm
    
    # 读取JSON模板
    # 从 finance-agents/data-agent/app/graphs/reconciliation/parsers.py 
    # 到 finance-mcp/reconciliation/schemas/direct_sales_schema.json（需 parents[5] 到项目根）
    template_path = Path(__file__).resolve().parents[5] / "finance-mcp" / "reconciliation" / "schemas" / "direct_sales_schema.json"
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            template = json.load(f)
    except Exception as e:
        logger.warning(f"无法读取JSON模板: {e}，使用默认模板")
        template = {}
    
    current_items_desc = ""
    if current_config_items:
        current_items_desc = "\n当前已添加的配置项：\n"
        for i, item in enumerate(current_config_items, 1):
            current_items_desc += f"{i}. {item.get('description', '未知配置')}\n"
    
    # 准备字段映射的详细描述（增强版）
    field_mapping_desc = ""
    business_fields = {}
    finance_fields = {}
    
    if field_mappings:
        biz_fields = field_mappings.get("business", {})
        fin_fields = field_mappings.get("finance", {})
        
        # 构建可用字段的查询表
        for role, field in biz_fields.items():
            if isinstance(field, list):
                for f in field:
                    business_fields[f.lower()] = (role, field)
            else:
                business_fields[field.lower()] = (role, field)
        
        for role, field in fin_fields.items():
            if isinstance(field, list):
                for f in field:
                    finance_fields[f.lower()] = (role, field)
            else:
                finance_fields[field.lower()] = (role, field)
        
        # 构建清晰的字段映射说明
        field_mapping_desc = "\n\n📋 字段映射关系（⚠️ 判断字段所属数据源时，必须以本列表为准，不要依赖示例中的硬编码）：\n"
        field_mapping_desc += "─" * 60 + "\n"
        
        if biz_fields:
            field_mapping_desc += "📁 文件1字段：\n"
            for role, field in biz_fields.items():
                if isinstance(field, list):
                    field_str = " / ".join(field)
                else:
                    field_str = str(field)
                field_mapping_desc += f"   • {role:10} → {field_str}\n"
        
        if fin_fields:
            field_mapping_desc += "📁 文件2字段：\n"
            for role, field in fin_fields.items():
                if isinstance(field, list):
                    field_str = " / ".join(field)
                else:
                    field_str = str(field)
                field_mapping_desc += f"   • {role:10} → {field_str}\n"
    
    # 构建 prompt：使用 replace 替代 f-string 插入 template_json/user_input，
    # 避免 template 中的 JSON（如 {"amount":"sum","date":"first"}）被下游 .format() 误解析为占位符
    template_json = json.dumps(template, ensure_ascii=False, indent=2)[:2000]
    
    # JSON 示例（使用普通字符串避免转义问题）
    # 增强示例，展示两个文件独立处理的重要性
    json_examples = '''配置项模板示例（使用JSON）：

[示例1] 金额容差（全局）：
{"action": "add", "json_snippet": {"tolerance": {"amount_diff_max": 0.1}}, "description": "金额容差：0.1元"}

[示例2] 金额转换（根据字段映射判断：若 product_price 在业务数据则用此格式配置 business，若在财务数据则配置 finance）：
{"action": "add", "json_snippet": {"data_cleaning_rules": {"finance": {"field_transforms": [{"field": "amount", "transform": "float(row.get('product_price', 0)) / 100", "description": "product_price 除以100转换为元"}]}}}, "description": "财务端转换：product_price除以100"}

[示例3] 财务端金额转换（发生- 在财务数据中）：
{"action": "add", "json_snippet": {"data_cleaning_rules": {"finance": {"field_transforms": [{"field": "amount", "transform": "float(row.get('发生-', 0)) / 100 if row.get('发生-') else None", "description": "发生- 除以100转换为元"}]}}}, "description": "财务端转换：发生-除以100"}

[示例4] 用户未指明文件时，默认对两个文件都配置（订单号处理）- 分离format和filter，注意操作顺序：
{"action": "add", "json_snippet": {"data_cleaning_rules": {"business": {"field_transforms": [{"field": "order_id", "transform": "str(row.get('roc_oid', '')).lstrip(\\"'\\")[:21]", "description": "订单号先去单引号再截取21位"}], "row_filters": [{"condition": "str(row.get('order_id', '')).startswith('104')", "description": "仅保留104开头的订单号"}]}, "finance": {"field_transforms": [{"field": "order_id", "transform": "str(row.get('sup订单号', '')).lstrip(\\"'\\")[:21]", "description": "订单号先去单引号再截取21位"}], "row_filters": [{"condition": "str(row.get('order_id', '')).startswith('104')", "description": "仅保留104开头的订单号"}]}}}, "description": "订单号处理：先去单引号再截取21位，仅保留104开头（两个文件）"}

[示例5] 用户明确指定文件1时，只配置 business：
{"action": "add", "json_snippet": {"data_cleaning_rules": {"business": {"field_transforms": [{"field": "order_id", "transform": "str(row.get('roc_oid', '')).lstrip('0')", "description": "删除订单号前导0"}]}}}, "description": "业务文件订单号：删除前导0"}

[示例6] 删除配置（target 必须是用户要删除的具体内容，精确匹配一项）：
{"action": "delete", "target": "金额容差", "description": "删除金额容差配置"}
{"action": "delete", "target": "product_price除以100", "description": "删除product_price除以100的转换"}

[示例7] 聚合类配置（按某字段合并、金额累加等）- 必须放入 aggregations，不能放全局：
- 用户未指定文件 → 放 business.aggregations 和 finance.aggregations
- 用户指定文件1 → 只放 business.aggregations
- 用户指定文件2 → 只放 finance.aggregations
示例（用户未指定，两个都放）：{"action": "add", "json_snippet": {"data_cleaning_rules": {"business": {"aggregations": [{"group_by": "order_id", "agg_fields": {"amount": "sum", "date": "first"}, "description": "按订单号合并，金额累加"}]}, "finance": {"aggregations": [{"group_by": "order_id", "agg_fields": {"amount": "sum", "date": "first"}, "description": "按订单号合并，金额累加"}]}}}, "description": "按订单号合并金额（两个文件）"}'''
    
    # 使用 replace 替代 f-string，避免 template_json 中的 {"amount":"sum","date":"first"} 等
    # 被下游 .format() 误解析为 Invalid format specifier
    prompt = """你是一个对账规则配置助手。请根据JSON模板解析用户的自然语言输入，返回一个JSON片段。

JSON模板结构（参考）：
<<<TEMPLATE_JSON>>>

<<<FIELD_MAPPING_DESC>>><<<CURRENT_ITEMS_DESC>>>

用户的指令：
<<<USER_INPUT>>>

请判断用户的意图：
1. 如果是**添加配置**，返回 action: "add"（每次添加一个逻辑规则，description 对应单一规则）
2. 如果是**删除配置**，返回 action: "delete"，target 必须是**配置项描述中的关键词**（如"product_price除以100"），不要带"删除"等动词前缀
3. 如果是**更新配置**，返回 action: "update"

⚠️ 关键规则 - 数据源识别和隔离（按优先级）：

**🔴 规则1（最高优先级）：用户明确指定文件 - 必须遵守**
- 如果用户说"文件1"或"业务"或"业务数据" → 必须配置到 business，无论字段名如何
- 如果用户说"文件2"或"财务"或"财务数据" → 必须配置到 finance，无论字段名如何
- 用户的明确指定**永远优先于字段名判断**
- 例如：用户说"文件2的product_price除以100" → 即使product_price是业务字段，也要在 finance 配置

**规则2（次优先级）：指明了字段名时，必须根据上方"字段映射关系"判断数据源**
- 当用户**指明了具体字段名**（如 product_price、发生-、roc_oid、sup订单号）时，**必须查看上方"字段映射关系"**：
  * 该字段在"业务数据(文件1)"中 → 只配置到 business
  * 该字段在"财务数据(文件2)"中 → 只配置到 finance
- **不要依赖示例中的字段归属**，用户上传的文件可能与示例不同
- 例如：用户说"product_price除以100" → 若 product_price 在财务数据(文件2)中，则只配置 finance；若在业务数据(文件1)中，则只配置 business

**规则3：未指明文件且未指明具体字段时，默认对两个文件都配置**
- 当用户既没指定文件，也没指明具体字段名（如"订单号处理"、"金额除以100"）时，为 business 和 finance 都配置
- 例如：用户说"订单号去掉开头单引号，截取前21位，保留104开头" → 为两个文件都配置
- 例如：用户说"金额除以100"（未指明具体字段）→ 为两个文件都配置（根据各自字段名写 transform）

**规则3.5：聚合类配置的放置位置（按字段合并、金额累加等）**
- 聚合类配置必须放在 data_cleaning_rules 的 **business.aggregations** 或 **finance.aggregations** 中，绝不能放在全局（tolerance、global 等）
- 放置规则与规则1-4一致：用户未指定文件 → 两个都放；用户指定文件1/业务 → 只放 business；用户指定文件2/财务 → 只放 finance
- 格式：{"group_by": "order_id", "agg_fields": {"amount": "sum", "date": "first"}, "description": "..."}

**规则4：用户明确指定文件时**
- 如果用户说"文件1"或"业务"或"业务数据" → 只配置到 business
- 如果用户说"文件2"或"财务"或"财务数据" → 只配置到 finance
- 如果用户说"两个都"或"两个文件都"或"同时" → 为两个文件都配置

**规则5：分离format和filter - 不要在transform中混合条件逻辑**
- ❌ 错：`"str(row.get('order_id', '')).lstrip(\\"'\\")[:21] if str(row.get('order_id', '')).startswith('104') else row.get('order_id', '')"`
  问题：False分支返回原始值，导致L开头的订单号无法被过滤掉
- ✅ 对：分成两步
  第一步field_transforms：`"str(row.get('order_id', '')).lstrip(\\"'\\")[:21]"` → 只做格式处理
  第二步row_filters：`"str(row.get('order_id', '')).startswith('104')"` → 只做过滤（删除不符条件的行）

**规则5.5：操作顺序很重要 - 字符串处理链的顺序决定结果**
⚠️ **用户说的"先...再..."顺序必须精确转化为代码的"先.method()再.method()"顺序**

- 用户说："先去单引号，再截取前21位" 
  → 代码应该是：`str(row.get('order_id', '')).lstrip("'")[:21]` ✅
  → 不能是：`str(row.get('order_id', '')).[:21].lstrip("'")` ❌

- 用户说："先截取前21位，再做其他处理" 
  → 代码应该是：`str(row.get('order_id', '')).[:21].method()` ✅

关键点：
- `.lstrip("'")` 是删除左侧的单引号，应该在所有其他处理之前
- `[:21]` 是取前21个字符，如果在lstrip之后，就是删除单引号后的前21位

例子对比：
- `"'123456789012345678901234"` (34个字符，包括1个开头单引号)
- `.lstrip("'")[:21]` → `"12345678901234567890"` (20个字符，因为删除单引号后再取21位) ✅
- `[:21].lstrip("'")` → `"'1234567890123456789"` (20个字符，先取21位再删单引号，单引号在最左仍被删除) ❌ 结果不同

**规则6：row_filters的使用（列级过滤vs行级过滤）**

⚠️ **row_filters是用来排除特殊/无关的记录，而不是用来"清理"数据格式**

何时使用row_filters：
- ✅ 财务系统有**特殊的内部记录**需要从对账中排除（如加款单、调账记录）
- ✅ 财务系统中有**特定格式的数据**需要单独处理（如只对104开头的订单做对账，加款单等用特殊格式代替）
- ✓ 财务侧有明确的"不应该参与对账的记录"

何时不应该使用row_filters：
- ❌ **不要用row_filters来统一两个系统的数据格式**
- ❌ **不要对业务数据使用row_filters**（业务系统的数据都是有效的业务数据，不应该被排除）
- ❌ **不要对同一个条件在两个数据源上都应用row_filters**（这会导致无法看出差异）

示例：腾讯异业对账
- 财务系统订单格式：104开头（正常订单）、XZFL开头（加款单）
- 业务系统订单格式：104开头、L开头（不同的业务来源）
- 正确配置：
  • finance：row_filters 删除非104开头（如XZFL加款单）
  • business：**不需要row_filters**，保留所有包括L开头的订单
- 错误配置：
  • 两边都加row_filters"104开头"
  • 结果：L开头的业务订单被删除，无法看出与财务的差异

**规则6.5：禁止输出 custom_validations**
- json_snippet 中不要包含 custom_validations，仅配置 data_cleaning_rules、tolerance 等

**规则7：避免重复规则**
- 检查当前已有的配置项（见上方"当前已添加的配置项"）
- 当用户说的需求已经包含在某个配置项中时，建议用户是否要更新或替换，而不是添加新规则
- 例如：如果已经有"订单号去单引号截取21位"的规则，不要再添加"订单号去单引号截取21位、104开头"
  应该改为更新现有规则或添加行过滤规则

**规则7：根据字段名写 transform 表达式**
- 为 business 配置时，使用业务数据字段列表中的列名（如 roc_oid、product_price）
- 为 finance 配置时，使用财务数据字段列表中的列名（如 sup订单号、发生-）

**规则8：transform 表达式必须使用该数据源的列名**
- 业务数据(business)的列名来自"业务数据字段"列表，如 roc_oid、product_price
- 财务数据(finance)的列名来自"财务数据字段"列表，如 sup订单号、发生-
- ❌ 错：在 finance 的 transform 中使用 row.get('product_price', 0)（product_price 是业务列）
- ✅ 对：在 finance 的 transform 中使用 row.get('发生-', 0)

<<<JSON_EXAMPLES>>>

请返回这个JSON格式的结果（只返回JSON，不要其他文字）：
{{"action": "add|delete|update", "json_snippet": {{...}}, "description": "用户友好的描述"}}"""
    
    # 使用 replace 插入变量，避免 template_json 中的 JSON 花括号被 .format() 误解析
    prompt = prompt.replace("<<<TEMPLATE_JSON>>>", template_json, 1)
    prompt = prompt.replace("<<<FIELD_MAPPING_DESC>>>", field_mapping_desc, 1)
    prompt = prompt.replace("<<<CURRENT_ITEMS_DESC>>>", current_items_desc, 1)
    prompt = prompt.replace("<<<USER_INPUT>>>", user_input, 1)
    prompt = prompt.replace("<<<JSON_EXAMPLES>>>", json_examples, 1)
        
    try:
        llm = get_llm(temperature=0.1)
        resp = llm.invoke(prompt)
        content = resp.content.strip()
        
        # 提取 JSON
        if "```" in content:
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if m:
                content = m.group(1)
        
        parsed = json.loads(content)
        logger.info(f"LLM解析结果: {parsed}")
        return parsed
    
    except Exception as e:
        logger.warning(f"LLM 规则配置解析失败: {e}")
        # 失败则返回空操作
        return {"action": "unknown", "description": f"解析失败: {str(e)}"}


def _parse_rule_config_with_llm(user_input: str, current_config: dict[str, Any] = None) -> dict[str, Any]:
    """使用 LLM 解析用户的自然语言规则配置指令，并合并到当前配置。
    
    ⚠️ 关键：LLM 只返回用户这次提到的字段，然后**合并**到现有配置，避免覆盖之前的设置。
    """
    from app.utils.llm import get_llm
    
    # 准备当前配置的完整描述
    base_config = current_config or {
        "order_id_pattern": None,
        "order_id_transform": None,
        "amount_tolerance": 0.1,
        "check_order_status": True,
    }
    
    current_desc = f"""
当前配置：
- 订单号特征：{base_config.get('order_id_pattern') or '无特殊特征'}
- 订单号转换：{base_config.get('order_id_transform') or '不转换'}
- 金额容差：{base_config.get('amount_tolerance', 0.1)}元
- 检查订单状态：{'是' if base_config.get('check_order_status', True) else '否'}
"""
    
    prompt = f"""你是一个对账规则配置助手。请解析用户的自然语言指令，提取**用户这次提到的字段**。

{current_desc}

用户的指令：
{user_input}

⚠️ 重要：只返回用户**这次明确提到**的字段，未提到的字段不要包含在 JSON 中。

返回 JSON 格式（只包含用户提到的字段）：
{{
  "order_id_pattern": "订单号特征（如'104'），null表示无特征",  // 仅当用户提到时才返回
  "order_id_transform": "订单号转换规则",  // 仅当用户提到时才返回
  "amount_tolerance": 0.2,  // 仅当用户提到时才返回
  "check_order_status": true  // 仅当用户提到时才返回
}}

解析规则：
1. 订单号特征：用户提到"104开头"、"L开头"等时才返回
2. 订单号转换：用户提到"去掉引号"、"截取X位"等时才返回
3. 金额容差：用户提到"容差"、"差异"、"误差"等时才返回
4. 订单状态检查：用户明确说"需要检查"或"不需要检查"时才返回

示例：
- "金额容差改为0.2" → {{"amount_tolerance": 0.2}}  （只返回容差）
- "订单号去掉开头单引号，并截取前21位" → {{"order_id_transform": "去掉开头单引号并截取前21位"}}
- "104开头，容差0.2，不检查状态" → {{"order_id_pattern": "104", "amount_tolerance": 0.2, "check_order_status": false}}
"""
    
    try:
        llm = get_llm(temperature=0.1)
        resp = llm.invoke(prompt)
        content = resp.content.strip()
        
        # 提取 JSON
        if "```" in content:
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if m:
                content = m.group(1)
        
        parsed = json.loads(content)
        
        # ⚠️ 关键：合并到现有配置，而不是替换
        merged_config = base_config.copy()
        
        # 只更新 LLM 返回的字段
        if "order_id_pattern" in parsed:
            merged_config["order_id_pattern"] = parsed["order_id_pattern"]
        if "order_id_transform" in parsed:
            merged_config["order_id_transform"] = parsed["order_id_transform"]
        if "amount_tolerance" in parsed:
            merged_config["amount_tolerance"] = float(parsed["amount_tolerance"])
        if "check_order_status" in parsed:
            merged_config["check_order_status"] = bool(parsed["check_order_status"])
        
        logger.info(f"规则配置合并: 原配置={base_config}, LLM解析={parsed}, 合并后={merged_config}")
        return merged_config
    
    except Exception as e:
        logger.warning(f"LLM 规则配置解析失败: {e}")
        # 失败则返回当前配置
        return base_config
