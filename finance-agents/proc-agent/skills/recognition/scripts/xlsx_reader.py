"""XLSX 文件读取工具

用于读取 doc/AI分析底稿原表 目录下的模板文件：
1. 手工凭证原表
2. BI费用明细表
3. BI损益毛利明细表
4. 收入类型与收入明细
5. 关联公司表

并提供数据同步规则处理功能。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# ── 路径配置 ──────────────────────────────────────────────────────────────────

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent.parent
DOC_DIR = PROJECT_ROOT / "finance-agents" / "proc-agent" / "doc" / "AI分析底稿原表"
REFERENCES_DIR = Path(__file__).parent.parent / "references"

# ── 文件路径常量 ───────────────────────────────────────────────────────────────

VOUCHER_FILE = DOC_DIR / "手工凭证原表202507月.xlsx"
BI_EXPENSE_FILE = DOC_DIR / "BI费用明细表202507月.xlsx"
BI_PROFIT_FILE = DOC_DIR / "BI损益毛利明细表原表202507月.xlsx"
REVENUE_TYPE_FILE = DOC_DIR / "收入类型与收入明细.xlsx"

# ── 读取函数 ───────────────────────────────────────────────────────────────────


def read_voucher_template(file_path: Optional[str] = None) -> pd.DataFrame:
    """读取手工凭证原表模板。
    
    Args:
        file_path: 可选，自定义文件路径。默认使用模板文件。
        
    Returns:
        DataFrame，包含手工凭证数据
    """
    path = Path(file_path) if file_path else VOUCHER_FILE
    logger.info(f"读取手工凭证原表: {path}")
    
    df = pd.read_excel(path, dtype=str)
    df = df.dropna(how="all").reset_index(drop=True)
    
    logger.info(f"手工凭证原表读取完成，共 {len(df)} 行，列: {list(df.columns)}")
    return df


def read_bi_expense_template(file_path: Optional[str] = None) -> Tuple[pd.DataFrame, Optional[pd.DataFrame]]:
    """读取BI费用明细表模板及同步规则。
    
    Args:
        file_path: 可选，自定义文件路径。默认使用模板文件。
        
    Returns:
        (数据DataFrame, 同步规则DataFrame或None)
    """
    path = Path(file_path) if file_path else BI_EXPENSE_FILE
    logger.info(f"读取BI费用明细表: {path}")
    
    xl = pd.ExcelFile(path)
    sheet_names = xl.sheet_names
    logger.info(f"Sheets: {sheet_names}")
    
    # 读取数据sheet（第一个sheet）
    data_sheet = sheet_names[0]
    df_data = pd.read_excel(path, sheet_name=data_sheet, dtype=str)
    df_data = df_data.dropna(how="all").reset_index(drop=True)
    
    # 尝试读取同步规则sheet
    df_rules = None
    if "同步规则" in sheet_names:
        df_rules = pd.read_excel(path, sheet_name="同步规则", dtype=str)
        df_rules = df_rules.dropna(how="all").reset_index(drop=True)
    
    logger.info(f"BI费用明细表读取完成，数据 {len(df_data)} 行，列: {list(df_data.columns)}")
    return df_data, df_rules


def read_bi_profit_template(file_path: Optional[str] = None) -> Tuple[pd.DataFrame, Optional[pd.DataFrame]]:
    """读取BI损益毛利明细表模板及同步规则。
    
    Args:
        file_path: 可选，自定义文件路径。默认使用模板文件。
        
    Returns:
        (数据DataFrame, 同步规则DataFrame或None)
    """
    path = Path(file_path) if file_path else BI_PROFIT_FILE
    logger.info(f"读取BI损益毛利明细表: {path}")
    
    xl = pd.ExcelFile(path)
    sheet_names = xl.sheet_names
    logger.info(f"Sheets: {sheet_names}")
    
    # 读取数据sheet（第一个sheet）
    data_sheet = sheet_names[0]
    df_data = pd.read_excel(path, sheet_name=data_sheet, dtype=str)
    df_data = df_data.dropna(how="all").reset_index(drop=True)
    
    # 尝试读取同步规则sheet
    df_rules = None
    if "同步规则" in sheet_names:
        df_rules = pd.read_excel(path, sheet_name="同步规则", dtype=str)
        df_rules = df_rules.dropna(how="all").reset_index(drop=True)
    
    logger.info(f"BI损益毛利明细表读取完成，数据 {len(df_data)} 行，列: {list(df_data.columns)}")
    return df_data, df_rules


def read_revenue_type_reference(file_path: Optional[str] = None) -> pd.DataFrame:
    """读取收入类型与收入明细参考表。
    
    Args:
        file_path: 可选，自定义文件路径。默认使用模板文件。
        
    Returns:
        DataFrame，包含科目名称到收入类型/明细的映射
    """
    path = Path(file_path) if file_path else REVENUE_TYPE_FILE
    logger.info(f"读取收入类型与收入明细: {path}")
    
    df = pd.read_excel(path, dtype=str)
    df = df.dropna(how="all").reset_index(drop=True)
    
    logger.info(f"收入类型参考表读取完成，共 {len(df)} 行")
    return df


def read_related_companies_reference() -> set:
    """读取关联公司列表。
    
    Returns:
        set，包含所有关联公司名称
    """
    ref_file = REFERENCES_DIR / "related_companies.md"
    
    if not ref_file.exists():
        logger.warning(f"关联公司参考文件不存在: {ref_file}")
        return set()
    
    companies = set()
    with open(ref_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    # 解析markdown表格
    lines = content.split("\n")
    in_table = False
    for line in lines:
        line = line.strip()
        if line.startswith("|") and "公司名称" not in line and "-" not in line:
            # 提取公司名称（去除首尾空格和|）
            parts = line.split("|")
            if len(parts) >= 2:
                company = parts[1].strip()
                if company and company != "公司名称":
                    companies.add(company)
    
    logger.info(f"关联公司参考表读取完成，共 {len(companies)} 家公司")
    return companies


def read_revenue_type_mapping() -> Dict[str, Dict[str, str]]:
    """读取收入类型映射字典。
    
    Returns:
        dict，键为科目名称，值为{"收入类型": ..., "收入明细": ...}
    """
    ref_file = REFERENCES_DIR / "revenue_type_reference.md"
    
    if not ref_file.exists():
        logger.warning(f"收入类型参考文件不存在: {ref_file}")
        return {}
    
    mapping = {}
    with open(ref_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    # 解析markdown表格
    lines = content.split("\n")
    for line in lines:
        line = line.strip()
        if line.startswith("|") and "科目名称" not in line and "-" not in line:
            parts = line.split("|")
            if len(parts) >= 4:
                subject = parts[1].strip()
                revenue_type = parts[2].strip()
                revenue_detail = parts[3].strip()
                if subject and subject != "科目名称":
                    mapping[subject] = {
                        "收入类型": revenue_type,
                        "收入明细": revenue_detail,
                    }
    
    logger.info(f"收入类型映射读取完成，共 {len(mapping)} 条映射")
    return mapping


# ── 同步规则处理 ───────────────────────────────────────────────────────────────


def parse_expense_sync_rules(df_rules: Optional[pd.DataFrame] = None) -> List[Dict[str, Any]]:
    """解析BI费用明细表的同步规则。
    
    如果未提供df_rules，则从默认文件读取。
    
    Returns:
        规则列表，每条规则包含：
        - target_col: 目标列名（BI费用明细表列）
        - source_col: 源列名（手工凭证表列）
        - rule: 规则说明
    """
    if df_rules is None:
        _, df_rules = read_bi_expense_template()
    
    if df_rules is None:
        logger.warning("未找到同步规则sheet")
        return []
    
    rules = []
    # 查找包含"费用表列"和"手工凭证列"的行
    for _, row in df_rules.iterrows():
        values = [str(v) if pd.notna(v) else "" for v in row.values]
        # 查找规则行（通常包含列名映射）
        if len(values) >= 4:
            target_col = values[2] if len(values) > 2 else ""
            source_col = values[3] if len(values) > 3 else ""
            rule_desc = values[4] if len(values) > 4 else ""
            
            if target_col and target_col != "费用表列":
                rules.append({
                    "target_col": target_col,
                    "source_col": source_col,
                    "rule": rule_desc,
                })
    
    logger.info(f"解析到 {len(rules)} 条同步规则")
    return rules


def get_expense_filter_subjects() -> List[str]:
    """获取费用明细表过滤的科目列表。
    
    根据同步规则中的总体规则，返回需要过滤的科目名称关键词。
    
    Returns:
        科目名称关键词列表
    """
    return [
        "研发支出_费用化支出",
        "主营业务成本_直接服务费",
        "主营业务成本_工资性支出",
        "其他业务收入",
        "其他业务成本",
        "管理费用",
        "销售费用",
        "财务费用",
        "营业外收入",
        "营业外支出",
        "投资收益",
        "资产减值损失",
        "所得税",
    ]


def is_expense_subject(subject_name: str) -> bool:
    """判断科目是否为费用类科目（用于BI费用明细表）。
    
    Args:
        subject_name: 科目名称
        
    Returns:
        bool，是否为费用类科目
    """
    subject = str(subject_name)
    
    # 管理费用需要剔除研发费子科目
    if "管理费用" in subject:
        if "管理费用_研发费" in subject or "管理费用-研发费" in subject:
            return False
        return True
    
    # 其他费用科目
    expense_keywords = [
        "研发支出_费用化支出",
        "主营业务成本_直接服务费",
        "主营业务成本_工资性支出",
        "其他业务收入",
        "其他业务成本",
        "销售费用",
        "财务费用",
        "营业外收入",
        "营业外支出",
        "投资收益",
        "资产减值损失",
        "所得税",
    ]
    
    return any(kw in subject for kw in expense_keywords)


def is_income_cost_subject(subject_name: str) -> bool:
    """判断科目是否为收入成本类科目（用于BI损益毛利明细表）。
    
    Args:
        subject_name: 科目名称
        
    Returns:
        bool，是否为收入成本类科目
    """
    subject = str(subject_name)
    
    income_cost_keywords = [
        "主营业务收入",
        "主营业务成本_销售成本",
        "主营业务成本-销售成本",
        "主营业务成本_技术服务成本",
        "主营业务成本-技术服务成本",
    ]
    
    return any(kw in subject for kw in income_cost_keywords)


# ── 数据转换工具 ───────────────────────────────────────────────────────────────


def clean_amount(value: Any) -> float:
    """清洗金额字段，返回浮点数（空/NaN 返回 0.0）。"""
    if value is None:
        return 0.0
    s = str(value).strip()
    if s in ("", "-", "nan", "NaN", "None"):
        return 0.0
    s = s.replace(",", "").replace("，", "")
    match = re.search(r"-?[\d.]+", s)
    return float(match.group()) if match else 0.0


def parse_tax_rate(rate_str: str) -> float:
    """解析税率字符串为浮点数。
    
    Args:
        rate_str: 税率字符串，如 "6%", "13%"
        
    Returns:
        税率小数，如 0.06, 0.13
    """
    s = str(rate_str).strip()
    if not s:
        return 0.0
    
    # 匹配百分比格式
    match = re.search(r"([\d.]+)\s*%", s)
    if match:
        return float(match.group(1)) / 100.0
    
    # 匹配纯数字格式
    match = re.search(r"[\d.]+", s)
    if match:
        v = float(match.group())
        return v / 100.0 if v > 1 else v
    
    return 0.0


def get_tax_rate_from_subject(subject_name: str) -> float:
    """从科目名称后缀推断税率。
    
    Args:
        subject_name: 科目名称
        
    Returns:
        税率小数
    """
    s = str(subject_name)
    
    # 检查后缀
    for suffix, rate in [
        ("-13%", 0.13), ("_13%", 0.13),
        ("-9%", 0.09), ("_9%", 0.09),
        ("-3%", 0.03), ("_3%", 0.03),
        ("-1%", 0.01), ("_1%", 0.01),
    ]:
        if s.endswith(suffix):
            return rate
    
    return 0.06  # 默认6%


def parse_summary(summary: str) -> Dict[str, str]:
    """解析摘要字段。
    
    格式：调整类型&客户+供应商+商户号(客户)+商户号(供应商)+税率
    
    Args:
        summary: 摘要字符串
        
    Returns:
        解析后的字典
    """
    s = str(summary).strip()
    adj_type = ""
    rest = s
    
    if "&" in s:
        idx = s.index("&")
        adj_type = s[:idx].strip()
        rest = s[idx + 1:]
    
    plus_parts = [p.strip() for p in rest.split("+")]
    
    return {
        "调整类型": adj_type,
        "客户": plus_parts[0] if len(plus_parts) > 0 else "",
        "供应商": plus_parts[1] if len(plus_parts) > 1 else "",
        "商户号_客户": plus_parts[2] if len(plus_parts) > 2 else "",
        "商户号_供应商": plus_parts[3] if len(plus_parts) > 3 else "",
        "税率字符串": plus_parts[4] if len(plus_parts) > 4 else "",
    }


def get_subject_parts(subject_name: str) -> Tuple[str, str, str]:
    """按 _ 或 - 分列科目名称为三级。
    
    Args:
        subject_name: 科目名称
        
    Returns:
        (一级科目, 二级科目, 三级科目)
    """
    s = str(subject_name)
    # 先尝试按 _ 分割，如果没有则按 - 分割
    if "_" in s:
        parts = s.split("_")
    elif "-" in s:
        parts = s.split("-")
    else:
        parts = [s]
    
    level1 = parts[0] if len(parts) > 0 else ""
    level2 = parts[1] if len(parts) > 1 else ""
    level3 = parts[2] if len(parts) > 2 else ""
    
    return level1, level2, level3


# ── 主函数 ─────────────────────────────────────────────────────────────────────


def main():
    """命令行入口，用于测试读取功能。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    
    print("=" * 60)
    print("XLSX 文件读取测试")
    print("=" * 60)
    
    # 1. 读取手工凭证
    print("\n1. 手工凭证原表")
    print("-" * 40)
    df_voucher = read_voucher_template()
    print(f"行数: {len(df_voucher)}")
    print(f"列名: {list(df_voucher.columns)}")
    print(f"前3行:\n{df_voucher.head(3)}")
    
    # 2. 读取BI费用明细表
    print("\n2. BI费用明细表")
    print("-" * 40)
    df_expense, df_expense_rules = read_bi_expense_template()
    print(f"数据行数: {len(df_expense)}")
    print(f"列名: {list(df_expense.columns)}")
    if df_expense_rules is not None:
        print(f"同步规则行数: {len(df_expense_rules)}")
    
    # 3. 读取BI损益毛利明细表
    print("\n3. BI损益毛利明细表")
    print("-" * 40)
    df_profit, df_profit_rules = read_bi_profit_template()
    print(f"数据行数: {len(df_profit)}")
    print(f"列名: {list(df_profit.columns)}")
    
    # 4. 读取收入类型映射
    print("\n4. 收入类型与收入明细")
    print("-" * 40)
    df_revenue = read_revenue_type_reference()
    print(f"行数: {len(df_revenue)}")
    print(f"列名: {list(df_revenue.columns)}")
    print(f"前5行:\n{df_revenue.head(5)}")
    
    # 5. 读取关联公司
    print("\n5. 关联公司列表")
    print("-" * 40)
    companies = read_related_companies_reference()
    print(f"公司数量: {len(companies)}")
    print(f"示例: {list(companies)[:5]}")
    
    # 6. 读取收入类型映射字典
    print("\n6. 收入类型映射字典")
    print("-" * 40)
    mapping = read_revenue_type_mapping()
    print(f"映射数量: {len(mapping)}")
    for k, v in list(mapping.items())[:3]:
        print(f"  {k} -> {v}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
