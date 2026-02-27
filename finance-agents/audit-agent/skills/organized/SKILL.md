# 审计数据整理 Skill

**版本**: 2.0
**最后更新**: 2026-02-26

---

## 一、Skill 概述

本 skill 是一个通用的数据整理 skill，通过意图分析来调用 `references` 目录下定义的业务规则文件，处理不同的财务数据整理业务。

**核心机制**:
1. **优先调用 Python 脚本**：如果业务类型对应的 Python 脚本存在，直接调用执行
2. **自动生成脚本**：如果 Python 脚本不存在，根据 `references` 下的 MD 规则文件自动生成
3. **统一接口**：提供统一的处理接口，屏蔽底层实现差异

---

## 二、支持的意图类型

| 意图编码 | 意图名称 | 规则文件 | Python 脚本 | 业务描述 |
|----------|----------|----------|-------------|----------|
| `cash_funds` | 货币资金 | `cash_funds_rule.md` | `cash_funds_rule.py` | 货币资金明细表数据整理 |
| `transaction_analysis` | 流水分析 | `transaction_analysis_rule.md` | `transaction_analysis_rule.py` | 银行流水分析 |
| `accounts_receivable` | 应收账款 | `accounts_receivable_analysis_rule.md` | `accounts_receivable_rule.py` | 应收账款分析 |
| `inventory_analysis` | 库存商品 | `inventory_analysis_rule.md` | `inventory_analysis_rule.py` | 库存商品分析 |
| `bank_account_check` | 开户清单核对 | `bank_account_check_rule.md` | `bank_account_check_rule.py` | 银行开户清单核对 |

---

## 三、意图识别规则

### 3.1 关键词匹配

| 意图类型 | 关键词列表 |
|----------|-----------|
| `cash_funds` | 货币资金、现金、银行存款、资金明细、资金核对 |
| `transaction_analysis` | 流水、交易明细、银行流水、流水分析、交易分析 |
| `accounts_receivable` | 应收、账款、客户往来、应收账款、应收分析 |
| `inventory_analysis` | 库存、存货、商品、仓储、库存分析、存货分析 |
| `bank_account_check` | 开户、清单、核对、账户清单、开户清单 |

### 3.2 意图识别流程

```
1. 接收用户请求
   ↓
2. 提取请求中的关键词
   ↓
3. 匹配意图类型
   ↓
4. 加载对应规则文件
   ↓
5. 执行规则定义的处理逻辑
   ↓
6. 返回处理结果
```

### 3.3 意图识别伪代码

```python
def identify_intent(user_request: str) -> str:
    """
    根据用户请求识别业务意图
    
    Args:
        user_request: 用户的请求描述
        
    Returns:
        意图类型编码
    """
    intent_keywords = {
        'cash_funds': ['货币资金', '现金', '银行存款', '资金明细', '资金核对'],
        'transaction_analysis': ['流水', '交易明细', '银行流水', '流水分析', '交易分析'],
        'accounts_receivable': ['应收', '账款', '客户往来', '应收账款', '应收分析'],
        'inventory_analysis': ['库存', '存货', '商品', '仓储', '库存分析', '存货分析'],
        'bank_account_check': ['开户', '清单', '核对', '账户清单', '开户清单']
    }
    
    # 计算每个意图的匹配分数
    scores = {}
    for intent, keywords in intent_keywords.items():
        scores[intent] = sum(1 for keyword in keywords if keyword in user_request)
    
    # 返回匹配分数最高的意图
    if max(scores.values()) > 0:
        return max(scores, key=scores.get)
    
    # 默认返回货币资金意图
    return 'cash_funds'
```

---

## 四、Python 脚本调用机制

### 4.0 规则文件路径映射

```python
RULE_FILE_MAPPING = {
    'cash_funds': 'references/cash_funds_rule.md',
    'transaction_analysis': 'references/transaction_analysis_rule.md',
    'accounts_receivable': 'references/accounts_receivable_analysis_rule.md',
    'inventory_analysis': 'references/inventory_analysis_rule.md',
    'bank_account_check': 'references/bank_account_check_rule.md'
}
```

### 4.1 脚本文件路径映射

```python
SCRIPT_FILE_MAPPING = {
    'cash_funds': 'scripts/cash_funds_rule.py',
    'transaction_analysis': 'scripts/transaction_analysis_rule.py',
    'accounts_receivable': 'scripts/accounts_receivable_rule.py',
    'inventory_analysis': 'scripts/inventory_analysis_rule.py',
    'bank_account_check': 'scripts/bank_account_check_rule.py'
}
```

### 4.2 脚本存在性检查

```python
import os
from pathlib import Path

def check_script_exists(intent_type: str) -> bool:
    """
    检查业务类型对应的 Python 脚本是否存在
    
    Args:
        intent_type: 意图类型编码
        
    Returns:
        True if script exists, False otherwise
    """
    script_path = SCRIPT_FILE_MAPPING.get(intent_type)
    if not script_path:
        return False
    
    # 相对于 skills 目录的完整路径
    skills_dir = Path(__file__).parent
    full_path = skills_dir / script_path
    
    return full_path.exists()
```

### 4.3 Python 脚本调用

```python
import subprocess
import sys
from typing import Dict, Any

def execute_python_script(intent_type: str, input_files: list, output_dir: str = None) -> Dict[str, Any]:
    """
    执行 Python 脚本处理业务数据
    
    Args:
        intent_type: 意图类型编码
        input_files: 输入文件列表
        output_dir: 输出目录（可选）
        
    Returns:
        处理结果字典
    """
    script_path = SCRIPT_FILE_MAPPING.get(intent_type)
    if not script_path:
        raise ValueError(f"未找到意图类型 {intent_type} 对应的脚本配置")
    
    skills_dir = Path(__file__).parent
    full_script_path = skills_dir / script_path
    
    if not full_script_path.exists():
        raise FileNotFoundError(f"脚本文件不存在：{full_script_path}")
    
    # 构建命令
    cmd = [sys.executable, str(full_script_path)]
    
    # 添加输入文件参数
    for f in input_files:
        cmd.extend(['--input', str(f)])
    
    # 添加输出目录参数
    if output_dir:
        cmd.extend(['--output-dir', output_dir])
    
    try:
        # 执行脚本
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=300  # 5 分钟超时
        )
        
        return {
            'status': 'success',
            'stdout': result.stdout,
            'stderr': result.stderr,
            'script': str(full_script_path)
        }
        
    except subprocess.CalledProcessError as e:
        return {
            'status': 'error',
            'error_code': 'SCRIPT_EXECUTION_FAILED',
            'message': f"脚本执行失败：{e.stderr}",
            'script': str(full_script_path)
        }
    except subprocess.TimeoutExpired:
        return {
            'status': 'error',
            'error_code': 'SCRIPT_TIMEOUT',
            'message': f"脚本执行超时（>5 分钟）",
            'script': str(full_script_path)
        }
```

### 4.4 脚本自动生成器

```python
def generate_python_script_from_rule(intent_type: str) -> str:
    """
    根据 references 下的 MD 规则文件自动生成 Python 脚本
    
    Args:
        intent_type: 意图类型编码
        
    Returns:
        生成的脚本文件路径
    """
    # 读取规则文件
    rule_file = RULE_FILE_MAPPING.get(intent_type)
    if not rule_file:
        raise ValueError(f"未找到意图类型 {intent_type} 对应的规则文件")
    
    skills_dir = Path(__file__).parent
    rule_path = skills_dir / rule_file
    
    if not rule_path.exists():
        raise FileNotFoundError(f"规则文件不存在：{rule_path}")
    
    with open(rule_path, 'r', encoding='utf-8') as f:
        rule_content = f.read()
    
    # 解析规则文件，提取关键信息
    rule_info = parse_rule_content(rule_content)
    
    # 生成 Python 脚本模板
    script_template = generate_script_template(rule_info)
    
    # 保存生成的脚本
    script_path = skills_dir / 'scripts' / f"{intent_type}_rule.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(script_template)
    
    print(f"已生成 Python 脚本：{script_path}")
    return str(script_path)


def parse_rule_content(rule_content: str) -> Dict[str, Any]:
    """
    解析 MD 规则文件，提取关键信息
    
    Args:
        rule_content: MD 规则文件内容
        
    Returns:
        规则信息字典
    """
    import re
    
    rule_info = {
        'rule_code': '',
        'version': '',
        'business_type': '',
        'data_sources': [],
        'output_fields': [],
        'processing_rules': [],
        'column_mappings': {}
    }
    
    # 提取规则编码
    match = re.search(r'\*\*规则编码\*\*:\s*`(\w+)`', rule_content)
    if match:
        rule_info['rule_code'] = match.group(1)
    
    # 提取业务类型
    match = re.search(r'\*\*业务类型\*\*:\s*`(\w+)`', rule_content)
    if match:
        rule_info['business_type'] = match.group(1)
    
    # 提取输出字段
    field_pattern = r'\|\s*\d+\s*\|\s*(\w+)\s*\|\s*([^|]+)\s*\|'
    matches = re.findall(field_pattern, rule_content)
    rule_info['output_fields'] = [
        {'field_name': m[0], 'description': m[1].strip()}
        for m in matches
    ]
    
    # 提取数据源识别规则
    if '科目余额表' in rule_content:
        rule_info['data_sources'].append('subject_balance_sheet')
    if '银行对账单' in rule_content:
        rule_info['data_sources'].append('bank_statement')
    if '流水' in rule_content:
        rule_info['data_sources'].append('transaction_flow')
    if '应收' in rule_content:
        rule_info['data_sources'].append('accounts_receivable')
    if '库存' in rule_content:
        rule_info['data_sources'].append('inventory')
    
    return rule_info


def generate_script_template(rule_info: Dict[str, Any]) -> str:
    """
    根据规则信息生成 Python 脚本模板
    
    Args:
        rule_info: 规则信息字典
        
    Returns:
        Python 脚本代码
    """
    template = f'''#!/usr/bin/env python3
"""
{rule_info.get('rule_code', 'Unknown Rule')} - {rule_info.get('business_type', 'Unknown')} 业务处理脚本

自动生成自 references/{rule_info.get('business_type', 'unknown')}_rule.md
版本：{rule_info.get('version', '1.0')}
"""

import pandas as pd
import os
from pathlib import Path
from typing import Dict, List, Optional
import argparse


# ──────────────────────────────────────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / 'data'
RESULT_DIR = BASE_DIR / 'result'

RESULT_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────────────────────
# 数据源识别
# ──────────────────────────────────────────────────────────────────────────────

def identify_data_sources(data_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    识别并加载数据源
    
    支持的数据源：{', '.join(rule_info.get('data_sources', []))}
    """
    data_sources = {{}}
    files = [f for f in data_dir.glob('*.xlsx') if f.is_file()]
    
    # TODO: 根据规则文件实现具体的数据源识别逻辑
    # 参考：references/{rule_info.get('business_type', 'unknown')}_rule.md
    
    return data_sources


# ──────────────────────────────────────────────────────────────────────────────
# 数据处理
# ──────────────────────────────────────────────────────────────────────────────

def process_data(data_sources: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    根据规则处理数据
    
    输出字段：
    {chr(10).join(f"    - {{f['field_name']}}: {{f['description']}}" for f in rule_info.get('output_fields', []))}
    """
    result_df = pd.DataFrame()
    
    # TODO: 根据规则文件实现具体的数据处理逻辑
    # 参考：references/{rule_info.get('business_type', 'unknown')}_rule.md
    
    return result_df


# ──────────────────────────────────────────────────────────────────────────────
# 输出
# ──────────────────────────────────────────────────────────────────────────────

def export_result(df: pd.DataFrame, output_dir: Path) -> None:
    """导出结果"""
    # 导出为 Excel
    excel_path = output_dir / f"{rule_info.get('business_type', 'result')}.xlsx"
    df.to_excel(excel_path, index=False, sheet_name=f"{rule_info.get('business_type', 'Result')}")
    print(f"已导出结果到：{{excel_path}}")
    
    # 导出为 Markdown
    md_path = output_dir / f"{rule_info.get('business_type', 'result')}.md"
    md_content = f"""# {rule_info.get('business_type', 'Result')} 结果表

**生成时间**: {{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}}

## 数据明细

{{df.to_markdown(index=False)}}
"""
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    print(f"已导出结果到：{{md_path}}")


# ──────────────────────────────────────────────────────────────────────────────
# 主函数
# ──────────────────────────────────────────────────────────────────────────────

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='{rule_info.get('rule_code', 'Unknown')} 业务处理')
    parser.add_argument('--input', '-i', nargs='+', help='输入文件路径')
    parser.add_argument('--output-dir', '-o', default=str(RESULT_DIR), help='输出目录')
    
    args = parser.parse_args()
    
    print("="*60)
    print("{rule_info.get('rule_code', 'Unknown Rule')} 业务处理")
    print("="*60)
    
    # 1. 识别并加载数据源
    print("\\n[步骤 1] 识别并加载数据源...")
    data_sources = identify_data_sources(DATA_DIR)
    
    if not data_sources:
        print("错误：未找到任何数据源")
        return
    
    # 2. 处理数据
    print("\\n[步骤 2] 处理数据...")
    result_df = process_data(data_sources)
    
    if len(result_df) == 0:
        print("警告：处理结果为空")
    
    # 3. 导出结果
    print("\\n[步骤 3] 导出结果...")
    output_dir = Path(args.output_dir)
    export_result(result_df, output_dir)
    
    print("\\n" + "="*60)
    print("处理完成")
    print("="*60)


if __name__ == '__main__':
    main()
'''
    
    return template
```

---

## 五、数据处理流程

### 5.1 主处理流程（支持 Python 脚本调用）

```python
def process_data_request(user_request: str, files: list, output_dir: str = None) -> dict:
    """
    处理数据整理请求
    
    Args:
        user_request: 用户请求描述
        files: 上传的文件列表
        output_dir: 输出目录（可选）
        
    Returns:
        处理结果
    """
    # 步骤 1: 识别意图
    intent_type = identify_intent(user_request)
    print(f"识别意图：{intent_type}")
    
    # 步骤 2: 检查 Python 脚本是否存在
    if check_script_exists(intent_type):
        print(f"Python 脚本存在，直接调用：{intent_type}_rule.py")
        # 调用 Python 脚本
        result = execute_python_script(intent_type, files, output_dir)
    else:
        print(f"Python 脚本不存在，检查规则文件...")
        # 检查规则文件是否存在
        rule_file = RULE_FILE_MAPPING.get(intent_type)
        if rule_file and Path(rule_file).exists():
            print(f"规则文件存在，自动生成 Python 脚本...")
            # 自动生成 Python 脚本
            script_path = generate_python_script_from_rule(intent_type)
            # 调用生成的脚本
            result = execute_python_script(intent_type, files, output_dir)
        else:
            # 规则文件也不存在，使用传统的规则解析方式
            print(f"规则文件不存在，使用传统规则解析方式...")
            result = process_with_rule_parser(intent_type, user_request, files)
    
    return result
```

### 5.2 传统规则解析方式（备用方案）

```python
def process_with_rule_parser(intent_type: str, user_request: str, files: list) -> dict:
    """
    当 Python 脚本和规则文件都不存在时，使用传统规则解析方式
    
    Args:
        intent_type: 意图类型编码
        user_request: 用户请求描述
        files: 上传的文件列表
        
    Returns:
        处理结果
    """
    # 加载规则
    rule_config = load_rule_file(intent_type)
    
    # 步骤 3: 识别数据源
    data_sources = identify_data_sources(files, rule_config)
    
    # 步骤 4: 执行数据处理
    result = execute_data_processing(data_sources, rule_config)
    
    # 步骤 5: 生成输出
    output = generate_output(result, rule_config)
    
    return output
```

### 5.2 数据源识别

```python
def identify_data_sources(files: list, rule_config: dict) -> dict:
    """
    根据规则文件识别所需的数据源
    
    Args:
        files: 上传的文件列表
        rule_config: 规则配置
        
    Returns:
        数据源字典
    """
    data_sources = {}
    
    # 读取规则中定义的数据源类型
    source_types = rule_config.get('data_source_types', [])
    
    for file in files:
        file_name = file.name
        file_content = read_file(file)
        
        # 根据规则文件中的数据源识别规则匹配
        for source_type in source_types:
            if match_source_type(file_name, file_content, source_type):
                data_sources[source_type] = file_content
                break
    
    return data_sources
```

### 5.3 数据处理执行

```python
def execute_data_processing(data_sources: dict, rule_config: dict) -> dict:
    """
    执行数据处理逻辑
    
    Args:
        data_sources: 数据源字典
        rule_config: 规则配置
        
    Returns:
        处理结果
    """
    result = {}
    
    # 根据规则配置执行数据处理
    processing_rules = rule_config.get('processing_rules', [])
    
    for rule in processing_rules:
        rule_type = rule.get('type')
        rule_params = rule.get('params', {})
        
        if rule_type == 'filter':
            result = apply_filter(data_sources, rule_params)
        elif rule_type == 'calculate':
            result = apply_calculation(result, rule_params)
        elif rule_type == 'transform':
            result = apply_transformation(result, rule_params)
        elif rule_type == 'aggregate':
            result = apply_aggregation(result, rule_params)
    
    return result
```

---

## 六、输出格式

### 6.1 标准输出结构

```json
{
    "intent_type": "cash_funds",
    "rule_file": "references/cash_funds_rule.md",
    "status": "success",
    "data": {
        "sheet_name": "货币资金明细表",
        "headers": ["序号", "科目名称", "核算项目", "期初金额", "本期借方", "本期贷方", "期末金额", "银行对账单金额", "差异", "账户性质", "备注"],
        "rows": [...],
        "summary": {...}
    },
    "metadata": {
        "processed_at": "2026-02-26T10:00:00Z",
        "source_files": ["科目余额表.xlsx", "银行对账单.xlsx"],
        "record_count": 10
    }
}
```

### 6.2 错误输出结构

```json
{
    "intent_type": "cash_funds",
    "rule_file": "references/cash_funds_rule.md",
    "status": "error",
    "error": {
        "code": "DATA_SOURCE_NOT_FOUND",
        "message": "未找到科目余额表数据源",
        "suggestion": "请上传包含'科目余额表'的文件"
    }
}
```

---

## 七、扩展新业务类型

### 7.1 添加新规则文件

在 `references` 目录下创建新的规则文件，命名格式：`{业务类型}_rule.md`

### 7.2 更新意图映射

在 `intent_keywords` 字典中添加新的意图类型和关键词：

```python
intent_keywords['new_business_type'] = ['关键词 1', '关键词 2', '关键词 3']
```

### 7.3 更新规则文件映射

在 `RULE_FILE_MAPPING` 字典中添加新的映射关系：

```python
RULE_FILE_MAPPING['new_business_type'] = 'references/new_business_type_rule.md'
```

---

## 八、配置参数

### 8.1 意图识别配置

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| min_match_score | 1 | 最小匹配分数 |
| default_intent | cash_funds | 默认意图类型 |
| case_sensitive | False | 是否区分大小写 |

### 8.2 数据处理配置

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| decimal_places | 2 | 金额保留小数位数 |
| date_format | %Y-%m-%d | 日期格式 |
| encoding | utf-8 | 文件编码 |

---

## 九、注意事项

### 9.1 规则文件管理

- 规则文件必须存放在 `references` 目录下
- 规则文件命名必须遵循 `{业务类型}_rule.md` 格式
- 规则文件必须包含规则编码、版本、业务类型等元数据

### 9.2 意图识别优化

- 定期根据实际使用情况优化关键词列表
- 可以引入机器学习模型提高意图识别准确率
- 支持用户自定义意图映射

### 9.3 错误处理

- 未找到匹配意图时，使用默认意图或提示用户澄清
- 数据源缺失时，提供明确的提示信息
- 处理失败时，保留中间结果便于调试

---

## 十、示例

### 10.1 货币资金处理示例（Python 脚本存在）

**用户请求**:
```
请帮我整理货币资金明细表，我有科目余额表和银行对账单
```

**处理流程**:
1. 识别意图：`cash_funds`（匹配关键词"货币资金"）
2. 检查脚本：`scripts/cash_funds_rule.py` 存在 ✅
3. 直接调用 Python 脚本执行
4. 返回结果：货币资金明细表

**代码示例**:
```python
from skills.generic_data_skill import process_data_request

result = process_data_request(
    user_request="请帮我整理货币资金明细表",
    files=["科目余额表.xlsx", "银行对账单.xlsx"]
)

# 输出:
# 识别意图：cash_funds
# Python 脚本存在，直接调用：cash_funds_rule.py
# 已导出货币资金明细表到：result/cash_funds.xlsx
```

### 10.2 货币资金处理示例（Python 脚本不存在，自动生成）

**场景**: 当 `cash_funds_rule.py` 被删除或不存在时

**处理流程**:
1. 识别意图：`cash_funds`
2. 检查脚本：`scripts/cash_funds_rule.py` 不存在 ❌
3. 检查规则文件：`references/cash_funds_rule.md` 存在 ✅
4. 自动生成 Python 脚本
5. 调用生成的脚本执行
6. 返回结果：货币资金明细表

**代码示例**:
```python
result = process_data_request(
    user_request="请帮我整理货币资金明细表",
    files=["科目余额表.xlsx", "银行对账单.xlsx"]
)

# 输出:
# 识别意图：cash_funds
# Python 脚本不存在，检查规则文件...
# 规则文件存在，自动生成 Python 脚本...
# 已生成 Python 脚本：skills/scripts/cash_funds_rule.py
# 已导出货币资金明细表到：result/cash_funds.xlsx
```

### 10.3 流水分析示例

**用户请求**:
```
帮我分析一下银行流水，看看有没有异常交易
```

**处理流程**:
1. 识别意图：`transaction_analysis`（匹配关键词"流水"、"分析"）
2. 检查脚本：`scripts/transaction_analysis_rule.py` 是否存在
   - 存在：直接调用执行
   - 不存在：根据 `references/transaction_analysis_rule.md` 生成
3. 识别数据源：银行流水表
4. 执行处理：异常交易识别、大额交易分析等
5. 返回结果：流水分析报告

### 10.4 应收账款分析示例

**用户请求**:
```
我想看看应收账款的账龄结构和逾期情况
```

**处理流程**:
1. 识别意图：`accounts_receivable`（匹配关键词"应收"、"账龄"）
2. 加载规则：`references/accounts_receivable_analysis_rule.md`
3. 识别数据源：应收账款明细表、客户档案
4. 执行处理：账龄分析、逾期判定、汇总统计
5. 返回结果：应收账款分析报告

---

## 十一、版本历史

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| 1.0 | 2026-02-26 | 初始版本，支持货币资金、流水分析、应收账款、库存商品业务 |
| 2.0 | 2026-02-26 | 新增 Python 脚本调用机制：优先调用现有脚本，不存在时自动生成 |

---

## 十二、附录：完整代码示例

### 12.1 完整调用示例

```python
#!/usr/bin/env python3
"""
通用数据整理 Skill 使用示例
"""

from pathlib import Path
from skills.generic_data_skill import (
    process_data_request,
    identify_intent,
    check_script_exists,
    execute_python_script
)

# 示例 1: 货币资金处理（脚本存在）
def test_cash_funds():
    """测试货币资金处理"""
    files = [
        Path("data/科目余额表.xlsx"),
        Path("data/银行对账单.xlsx")
    ]
    
    result = process_data_request(
        user_request="请帮我整理货币资金明细表",
        files=files,
        output_dir="result"
    )
    
    print(f"处理结果：{result['status']}")
    return result

# 示例 2: 流水分析（脚本不存在时自动生成）
def test_transaction_analysis():
    """测试流水分析"""
    files = [Path("data/银行流水.xlsx")]
    
    # 检查脚本是否存在
    if not check_script_exists('transaction_analysis'):
        print("脚本不存在，将自动生成...")
    
    result = process_data_request(
        user_request="帮我分析一下银行流水",
        files=files,
        output_dir="result"
    )
    
    print(f"处理结果：{result['status']}")
    return result

# 示例 3: 直接调用 Python 脚本
def test_direct_script_call():
    """直接调用 Python 脚本"""
    files = [
        Path("data/科目余额表.xlsx"),
        Path("data/银行对账单.xlsx")
    ]
    
    result = execute_python_script(
        intent_type='cash_funds',
        input_files=files,
        output_dir='result'
    )
    
    print(f"脚本执行结果：{result['status']}")
    return result

if __name__ == '__main__':
    # 运行测试
    test_cash_funds()
    test_transaction_analysis()
    test_direct_script_call()
```
