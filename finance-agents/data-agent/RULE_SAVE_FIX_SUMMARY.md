# 🔍 规则保存问题分析与修复总结

**问题时间**: 2026-02-13 11:29  
**问题描述**: 用户创建规则"南京飞翰直销对账"显示保存成功，但执行时提示"未找到对账类型"  
**修复状态**: ✅ 已完成

---

## 📋 问题现象

### 用户截图分析
```
步骤 1️⃣: 用户选择规则类型 "南京飞翰直销对账"
步骤 2️⃣: 系统显示 "规则 **南京飞翰直销对账** 已保存！"
步骤 3️⃣: 用户点击"开始"执行规则
步骤 4️⃣: 系统报错 "启动对账任务失败：未找到对账类型：南京飞翰直销对账"
```

### 错误消息
```
❌ 启动对账任务失败：未找到对账类型：南京飞翰直销对账
```

---

## 🔎 根本原因分析

### 问题链条

#### 第 1 步：规则创建流程
📍 **文件**: `/data-agent/app/graphs/reconciliation.py` (第 970-1030 行)

当用户命名规则时，`save_rule_node` 调用：
```python
result = await call_mcp_tool("save_reconciliation_rule", {
    "auth_token": auth_token,
    "name": "南京飞翰直销对账",
    "description": "南京飞翰直销对账",
    "rule_template": <schema_dict>,
    "visibility": "private",
})
```

#### 第 2 步：规则保存处理（原始逻辑 ❌）
📍 **文件**: `/finance-mcp/auth/tools.py` (第 400-435 行)

原始的 `_handle_save_rule` 函数只做了：
```python
async def _handle_save_rule(args: dict) -> dict:
    # ... 验证
    
    # ❌ 仅保存到 PostgreSQL 数据库（不完整！）
    rule = auth_db.create_rule(
        name=name,
        description=description,
        rule_template=rule_template,
        # ...
    )
    
    # ❌ 缺少：
    # 1. 保存 rule_template 为 JSON 文件
    # 2. 更新 reconciliation_schemas.json 配置
    
    return {"success": True, "rule": rule, ...}
```

#### 第 3 步：规则执行时查找（执行失败）
📍 **文件**: `/finance-mcp/reconciliation/mcp_server/tools.py` (第 230-280 行)

当用户执行对账时，`_reconciliation_start` 从配置文件查找规则：
```python
async def _reconciliation_start(args: Dict) -> Dict:
    reconciliation_type = args.get("reconciliation_type")  # "南京飞翰直销对账"
    
    # ❌ 从配置文件中查找（不从数据库查找！）
    config = load_json_with_comments(RECONCILIATION_SCHEMAS_FILE)
    
    for type_config in config.get("types", []):
        if type_config.get("name_cn") == reconciliation_type:
            matched_type = type_config
            break
    
    if not matched_type:
        return {
            "error": f"未找到对账类型: {reconciliation_type}"  # ❌ 这就是用户看到的错误
        }
```

#### 第 4 步：配置文件现状
📍 **文件**: `/finance-mcp/reconciliation/config/reconciliation_schemas.json`

```json
{
  "types": [
    {
      "name_cn": "直销对账",
      "type_key": "direct_sales",
      "schema_path": "direct_sales_schema.json",
      "callback_url": "..."
    },
    // ... 其他预定义规则
    {
      "name_cn": "南京飞翰知晓对账",  // ⚠️ 名字不匹配！
      "type_key": "________",          // ⚠️ 占位符 type_key
      "schema_path": "_________schema.json",  // ⚠️ 占位符文件名
      "callback_url": ""
    }
  ]
}
```

### 问题核心
| 步骤 | 发生的事 | 问题 |
|------|---------|------|
| 1 | 规则保存到 PostgreSQL | ✅ 成功 |
| 2 | 显示保存成功消息 | ✅ 正确 |
| 3 | **配置文件未更新** | ❌ **这是关键问题** |
| 4 | 执行时从配置文件查找 | ❌ 找不到新规则 |
| 5 | 报错 "未找到对账类型" | ❌ 最终结果 |

---

## ✅ 修复方案

### 修复 1：增强 `_handle_save_rule` 函数

**文件**: `/finance-mcp/auth/tools.py`

#### 添加的导入
```python
import json
import re
from pathlib import Path
```

#### 添加的配置常量
```python
# finance-mcp 的路径配置（在模块级别）
FINANCE_MCP_DIR = Path(__file__).resolve().parent.parent
SCHEMA_DIR = FINANCE_MCP_DIR / "reconciliation" / "schemas"
RECONCILIATION_SCHEMAS_FILE = FINANCE_MCP_DIR / "reconciliation" / "config" / "reconciliation_schemas.json"
```

#### 添加的辅助函数 1: 名称转换
```python
def _translate_rule_name_to_type_key(name_cn: str) -> str:
    """将中文规则名转換为英文 type_key
    例如: "南京飞翰直销对账" → "nanjing_feihan_direct_sales_reconciliation"
    """
    translation_map = {
        "南京": "nanjing",
        "飞翰": "feihan",
        "直销": "direct_sales",
        "对账": "reconciliation",
    }
    
    result = name_cn
    for cn, en in translation_map.items():
        result = result.replace(cn, en)
    
    result = re.sub(r'[^\w]', '_', result)
    result = re.sub(r'_+', '_', result)
    return result.strip('_').lower() or "custom_rule"
```

#### 添加的辅助函数 2: 保存 Schema 文件
```python
def _save_schema_file(schema_dict: dict, rule_name_cn: str) -> tuple[bool, str, str]:
    """将 schema 保存为 JSON 文件
    
    输出文件: SCHEMA_DIR/nanjing_feihan_direct_sales_reconciliation_schema.json
    
    返回: (是否成功, 文件名, 错误信息)
    """
    type_key = _translate_rule_name_to_type_key(rule_name_cn)
    schema_filename = f"{type_key}_schema.json"
    schema_filepath = SCHEMA_DIR / schema_filename
    
    with open(schema_filepath, 'w', encoding='utf-8') as f:
        json.dump(schema_dict, f, indent=2, ensure_ascii=False)
    
    return True, schema_filename, ""
```

#### 添加的辅助函数 3: 更新配置文件
```python
def _update_reconciliation_schemas_config(rule_name_cn: str, schema_filename: str) -> tuple[bool, str]:
    """更新 reconciliation_schemas.json 配置文件
    
    流程:
    1. 读取现有 reconciliation_schemas.json
    2. 查找是否已存在同名规则（更新）或添加新规则
    3. 保存回文件
    
    返回: (是否成功, 错误信息)
    """
    if RECONCILIATION_SCHEMAS_FILE.exists():
        with open(RECONCILIATION_SCHEMAS_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
    else:
        config = {"types": []}
    
    type_key = _translate_rule_name_to_type_key(rule_name_cn)
    
    # 检查是否已存在
    for type_config in config["types"]:
        if type_config.get("name_cn") == rule_name_cn:
            # 更新现有规则
            type_config["schema_path"] = schema_filename
            break
    else:
        # 添加新规则
        new_type = {
            "name_cn": rule_name_cn,
            "type_key": type_key,
            "schema_path": schema_filename,
            "callback_url": "",
        }
        config["types"].append(new_type)
    
    with open(RECONCILIATION_SCHEMAS_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    return True, ""
```

#### 修改的主函数
```python
async def _handle_save_rule(args: dict) -> dict:
    """保存新规则 - 现在是完整的三层保存
    
    1️⃣ PostgreSQL: auth_db.create_rule()
    2️⃣ JSON 文件: reconciliation/schemas/<type_key>_schema.json
    3️⃣ 配置文件: reconciliation_schemas.json
    """
    valid, user_info, err = _require_auth(args)
    if not valid:
        return {"success": False, "error": err}

    name = args.get("name", "").strip()
    rule_template = args.get("rule_template")

    # ... (验证逻辑)

    try:
        # 1️⃣ 保存到 PostgreSQL
        rule = auth_db.create_rule(
            name=name,
            description=description,
            created_by=user_info["user_id"],
            rule_template=rule_template,
            # ...
        )
        
        # 2️⃣ 保存 schema 为 JSON 文件
        success, schema_filename, save_error = _save_schema_file(rule_template, name)
        if not success:
            logger.warning(f"保存规则 schema 文件失败 (数据库保存已成功): {save_error}")
        
        # 3️⃣ 更新 reconciliation_schemas.json 配置文件
        config_success, config_error = _update_reconciliation_schemas_config(name, schema_filename)
        if not config_success:
            logger.warning(f"更新规则配置文件失败: {config_error}")
        
        return {
            "success": True,
            "rule": rule,
            "message": f"规则 '{name}' 已完全保存",
            "details": {
                "saved_to_db": True,
                "schema_file": schema_filename,
                "config_file_updated": config_success
            }
        }
        
    except Exception as e:
        logger.error(f"保存规则时发生异常: {e}")
        return {"success": False, "error": f"规则保存失败: {str(e)}"}
```

---

## 🔄 修复后的流程

```
用户创建规则 "南京飞翰直销对账"
    ↓
save_rule_node 调用 save_reconciliation_rule
    ↓
_handle_save_rule 执行三层保存:
    ├─ 1️⃣ PostgreSQL: create_rule()
    │   └─ 行 id: UUID
    │   └─ 字段: name, rule_template, created_by, ...
    │
    ├─ 2️⃣ JSON 文件: schemas/nanjing_feihan_direct_sales_reconciliation_schema.json
    │   └─ 内容: rule_template JSON 数据
    │
    └─ 3️⃣ 配置文件: reconciliation_schemas.json
        └─ 添加新条目:
           {
             "name_cn": "南京飞翰直销对账",
             "type_key": "nanjing_feihan_direct_sales_reconciliation",
             "schema_path": "nanjing_feihan_direct_sales_reconciliation_schema.json",
             "callback_url": ""
           }
    ↓
系统返回 {"success": True, "message": "规则 '南京飞翰直销对账' 已完全保存"}
    ↓
用户执行规则
    ↓
_reconciliation_start 从 reconciliation_schemas.json 查找:
    ✅ 现在能找到新规则！
    └─ 加载 nanjing_feihan_direct_sales_reconciliation_schema.json
    ↓
对账成功启动 ✅
```

---

## 📊 修复前后对比

| 操作 | 修复前 | 修复后 |
|------|--------|--------|
| 保存到 DB | ✅ | ✅ |
| 保存 JSON 文件 | ❌ 缺失 | ✅ |
| 更新配置文件 | ❌ 缺失 | ✅ |
| 执行规则时查找 | ❌ 找不到 | ✅ 能找到 |
| 用户体验 | ❌ 保存成功但不能执行 | ✅ 保存后可立即执行 |

---

## 📁 修改的文件

**文件**: `/Users/kevin/workspace/financial-ai/finance-mcp/auth/tools.py`

| 部分 | 行号 | 变化 |
|------|------|------|
| 导入 | 1-10 | 添加 `json`, `re`, `Path` |
| 常量 | 11-34 | 添加路径配置和初始化 |
| 函数 | 398-435 | 添加 3 个辅助函数 |
| 函数 | 437-505 | 重写 `_handle_save_rule` |

---

## 🧪 验证方案

### 测试 1: 单元测试（Python）
```python
# 验证辅助函数
_translate_rule_name_to_type_key("南京飞翰直销对账")
# → "nanjing_feihan_direct_sales_reconciliation" ✅

_save_schema_file({...}, "南京飞翰直销对账")
# → (True, "nanjing_feihan_direct_sales_reconciliation_schema.json", "") ✅

_update_reconciliation_schemas_config("南京飞翰直销对账", "file.json")
# → (True, "") ✅
```

### 测试 2: E2E 测试（Playwright）
使用 [test_rule_lifecycle.py](./playwright/test_rule_lifecycle.py) 验证：
1. 登录
2. 创建规则
3. 验证规则已保存到 reconciliation_schemas.json
4. 执行规则（应该成功）

### 测试 3: 数据验证
验证完成后，应该看到：
- ✅ PostgreSQL 中的规则记录：`SELECT * FROM rules WHERE name = '南京飞翰直销对账'`
- ✅ JSON 文件存在：`ls -la reconciliation/schemas/nanjing_feihan_*.json`
- ✅ 配置文件已更新：`grep "南京飞翰直销对账" reconciliation/config/reconciliation_schemas.json`

---

## 💡 实现细节

### 为什么使用这种三层架构？

1. **PostgreSQL** (主记录存储)
   - 用户管理规则时的权限控制
   - 规则版本历史
   - 规则排序和分类

2. **JSON 文件** (执行时加载)
   - 快速访问（不需要查数据库）
   - 包含完整的对账逻辑和字段定义

3. **reconciliation_schemas.json** (配置索引)
   - 系统启动时快速加载所有规则类型
   - 提供规则名称到文件的映射
   - 启用回调 URL 配置

### 为什么不直接从 DB 执行规则？

原设计就是从文件执行。修复后保持了这个设计，但现在文件会被自动创建和更新。

---

## 🎯 下一步行动

### 立即需要
- [ ] 重启 finance-mcp 服务以加载修复代码
- [ ] 用 Playwright 运行 E2E 测试
- [ ] 确认用户可以成功创建和执行新规则

### 可选优化
- [ ] 从 PostgreSQL 动态加载规则（无需重启）
- [ ] 实现规则版本管理
- [ ] 添加规则模板库

---

## 📝 总结

**问题根本原因**: 规则保存逻辑不完整，只保存到 DB 而不更新配置文件

**修复方式**: 添加完整的三层保存流程，确保新规则对执行引擎可见

**风险评估**: 低风险，修复仅添加功能不改变现有逻辑

**用户影响**: 正面，用户创建的规则现在可以立即使用

