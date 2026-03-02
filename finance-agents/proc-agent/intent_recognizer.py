"""意图识别器模块

根据用户请求识别业务意图类型，支持多种审计数据整理业务和核算业务。
"""

import re
from typing import Dict, List, Optional, Tuple


# 意图定义
class IntentType:
    """业务意图类型枚举"""
    CASH_FUNDS = "cash_funds"                    # 货币资金
    TRANSACTION_ANALYSIS = "transaction_analysis"  # 流水分析
    ACCOUNTS_RECEIVABLE = "accounts_receivable"  # 应收账款
    INVENTORY_ANALYSIS = "inventory_analysis"    # 库存商品
    BANK_ACCOUNT_CHECK = "bank_account_check"    # 开户清单核对
    RECOGNITION_REPORT = "recognition_report"    # 核算报表生成
    DEFAULT = "cash_funds"                       # 默认意图


# 意图关键词映射（越精确的关键词权重越高）
INTENT_KEYWORDS: Dict[str, List[str]] = {
    IntentType.CASH_FUNDS: [
        "货币资金", "现金", "银行存款", "资金明细", "资金核对",
        "货币资金明细表", "资金整理"
    ],
    IntentType.TRANSACTION_ANALYSIS: [
        "流水", "交易明细", "银行流水", "流水分析", "交易分析",
        "异常交易", "流水核对"
    ],
    IntentType.ACCOUNTS_RECEIVABLE: [
        "应收", "账款", "客户往来", "应收账款", "应收分析",
        "往来款", "客户对账"
    ],
    IntentType.INVENTORY_ANALYSIS: [
        "库存", "存货", "商品", "仓储", "库存分析", "存货分析",
        "库存商品", "进销存"
    ],
    IntentType.BANK_ACCOUNT_CHECK: [
        "开户", "清单", "核对", "账户清单", "开户清单",
        "银行账户", "账户核对"
    ],
    IntentType.RECOGNITION_REPORT: [
        # 高优先级关键词（精确匹配得分翻倍）
        "手工凭证", "BI费用明细", "BI损益", "损益毛利", "核算报表",
        "核算明细", "凭证生成报表", "BI损益毛利", "供应商毛利",
        "代运营毛利", "AI自动化逻辑",
        # 中优先级关键词
        "BI费用", "毛利明细", "毛利分析", "费用归集", "凭证报表",
        "BI报表生成", "核算", "手工凭证报表",
    ],
}

# 规则文件映射（相对于 proc-agent 根目录）
RULE_FILE_MAPPING: Dict[str, str] = {
    IntentType.CASH_FUNDS: "references/cash_funds_rule.md",
    IntentType.TRANSACTION_ANALYSIS: "references/transaction_analysis_rule.md",
    IntentType.ACCOUNTS_RECEIVABLE: "references/accounts_receivable_analysis_rule.md",
    IntentType.INVENTORY_ANALYSIS: "references/inventory_analysis_rule.md",
    IntentType.BANK_ACCOUNT_CHECK: "references/bank_account_check_rule.md",
    IntentType.RECOGNITION_REPORT: "skills/recognition/references/recognition_rule.md",
}

# 脚本文件映射（相对于 proc-agent 根目录）
SCRIPT_FILE_MAPPING: Dict[str, str] = {
    IntentType.CASH_FUNDS: "scripts/cash_funds_rule.py",
    IntentType.TRANSACTION_ANALYSIS: "scripts/transaction_analysis_rule.py",
    IntentType.ACCOUNTS_RECEIVABLE: "scripts/accounts_receivable_rule.py",
    IntentType.INVENTORY_ANALYSIS: "scripts/inventory_analysis_rule.py",
    IntentType.BANK_ACCOUNT_CHECK: "scripts/bank_account_check_rule.py",
    IntentType.RECOGNITION_REPORT: "skills/recognition/scripts/recognition_rule.py",
}

# 需要 chat_id 参数的意图集合（recognition 类使用 chat_id 隔离输出目录）
CHAT_ID_REQUIRED_INTENTS = {IntentType.RECOGNITION_REPORT}


def identify_intent(user_request: str) -> Tuple[str, float]:
    """根据用户请求识别业务意图

    参数:
        user_request: 用户的自然语言请求

    返回:
        (意图类型，匹配分数) 的元组

    识别规则:
        1. 提取请求中的关键词
        2. 计算每个意图的匹配分数
        3. 返回匹配分数最高的意图
        4. 如果无匹配，返回默认意图
    """
    if not user_request:
        return IntentType.DEFAULT, 0.0

    # 转为小写进行不区分大小写的匹配
    request_lower = user_request.lower()

    best_intent = IntentType.DEFAULT
    best_score = 0.0

    for intent, keywords in INTENT_KEYWORDS.items():
        score = 0.0
        for keyword in keywords:
            # 精确匹配（整词）
            if re.search(rf'\b{re.escape(keyword)}\b', request_lower, re.IGNORECASE):
                score += 2.0
            # 模糊匹配（包含）
            elif keyword in request_lower:
                score += 1.0

        if score > best_score:
            best_score = score
            best_intent = intent

    # 如果分数低于阈值，使用默认意图
    if best_score < 1.0:
        return IntentType.DEFAULT, 0.0

    return best_intent, best_score


def get_rule_file(intent_type: str) -> Optional[str]:
    """根据意图类型获取规则文件路径

    参数:
        intent_type: 意图类型

    返回:
        规则文件路径，如果不存在则返回 None
    """
    return RULE_FILE_MAPPING.get(intent_type)


def get_script_file(intent_type: str) -> Optional[str]:
    """根据意图类型获取脚本文件路径

    参数:
        intent_type: 意图类型

    返回:
        脚本文件路径，如果不存在则返回 None
    """
    return SCRIPT_FILE_MAPPING.get(intent_type)


def list_available_intents() -> List[Dict[str, str]]:
    """列出所有可用的意图类型

    返回:
        意图列表，每个意图包含 id 和 name
    """
    return [
        {"id": IntentType.CASH_FUNDS, "name": "货币资金整理"},
        {"id": IntentType.TRANSACTION_ANALYSIS, "name": "流水分析"},
        {"id": IntentType.ACCOUNTS_RECEIVABLE, "name": "应收账款分析"},
        {"id": IntentType.INVENTORY_ANALYSIS, "name": "库存商品分析"},
        {"id": IntentType.BANK_ACCOUNT_CHECK, "name": "开户清单核对"},
        {"id": IntentType.RECOGNITION_REPORT, "name": "核算报表生成（BI费用明细+BI损益毛利）"},
    ]
