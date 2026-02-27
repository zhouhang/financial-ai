#!/usr/bin/env python3
"""
货币资金明细表生成脚本

根据 cash_skill.md 的需求说明，从科目余额表和银行对账单中提取数据，
生成货币资金明细表。

功能说明：
1. 从科目余额表中过滤出'库存现金'、'银行存款'、'其他货币资金'相关数据
2. 从银行对账单中读取银行对账单金额
3. 计算差异（期末金额 - 银行对账单金额）
4. 生成货币资金明细表（Markdown 格式）
"""

import pandas as pd
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ──────────────────────────────────────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent  # 指向 data-process 目录
DATA_DIR = BASE_DIR / 'data'
RESULT_DIR = BASE_DIR / 'result'

# 确保结果目录存在
RESULT_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────────────────────────────────────

def find_file_by_pattern(files: List[str], patterns: List[str]) -> Optional[str]:
    """根据模式匹配查找文件"""
    for f in files:
        for pattern in patterns:
            if pattern in f:
                return f
    return None


def is_subject_balance_sheet(file_path: Path) -> bool:
    """判断是否为科目余额表文件"""
    filename = file_path.name
    
    # 文件名包含"科目余额表"
    if '科目余额表' in filename:
        return True
    
    # 读取文件标题检查
    try:
        df = pd.read_excel(file_path, nrows=5)
        all_text = ' '.join([str(col) for col in df.columns])
        
        # 检查是否包含科目余额表特征列
        keywords = ['科目代码', '科目名称', '期初余额', '本期发生额', '期末余额']
        match_count = sum(1 for kw in keywords if kw in all_text)
        
        if match_count >= 3:
            return True
    except Exception as e:
        print(f"检查科目余额表失败 {file_path}: {e}")
    
    return False


def is_bank_statement(file_path: Path) -> bool:
    """判断是否为银行对账单文件"""
    filename = file_path.name
    
    # 文件名包含"银行对账单"
    if '银行对账单' in filename:
        return True
    
    # 读取文件标题检查
    try:
        # 读取第一个 sheet
        df = pd.read_excel(file_path, sheet_name=0, nrows=5)
        all_text = ' '.join([str(col) for col in df.columns])
        
        # 检查是否包含银行对账单特征列
        keywords1 = ['账号', '交易日', '借方金额', '贷方金额', '余额']
        keywords2 = ['发生时间', '账户名', '发生+', '发生-', '备注摘要']
        
        match_count1 = sum(1 for kw in keywords1 if kw in all_text)
        match_count2 = sum(1 for kw in keywords2 if kw in all_text)
        
        if match_count1 >= 3 or match_count2 >= 3:
            return True
    except Exception as e:
        print(f"检查银行对账单失败 {file_path}: {e}")
    
    return False


def extract_bank_info_from_account(account_name: str) -> Tuple[str, str]:
    """从核算项目名称中提取银行名称和账号后 5 位

    示例：
    - 银行账户：中国银行 72515 -> (中国银行，72515)
    - 银行账户：招商银行 10001 -> (招商银行，10001)
    - 银行账户：支付宝 flfq20250902@163.com -> (支付宝，'')  # 无数字账号
    """
    bank_name = ""
    account_suffix = ""

    if pd.isna(account_name) or not account_name:
        print(f"    跳过：核算项目为空")
        return bank_name, account_suffix

    account_name = str(account_name).strip()
    # 清理可能的不可见字符
    account_name = ''.join(c for c in account_name if ord(c) >= 32 or c in '\n\t')
    print(f"    处理核算项目：'{account_name}' (长度={len(account_name)})")

    # 使用更灵活的正则表达式匹配
    # 匹配模式：银行 + 任意字符 + 冒号（全角或半角）+ 银行名称 + 数字
    # \uFF1A 是全角冒号 (：), \u003A 是半角冒号 (:)
    match = re.search(r'银行.*?[\uFF1A\u003A](.*?)(\d{4,})', account_name)
    if match:
        # 提取银行名称（去除数字部分）
        bank_part = match.group(1)
        bank_name = ''.join([c for c in bank_part if not c.isdigit()]).strip()
        # 提取账号后 5 位
        account_num = match.group(2)
        account_suffix = account_num[-5:] if len(account_num) >= 5 else account_num
        print(f"    ✓ 提取银行信息：'{account_name}' -> 银行={bank_name}, 账号后 5 位={account_suffix}")
    else:
        # 没有数字账号（如支付宝等第三方支付）
        match = re.search(r'银行.*?[\uFF1A\u003A](.+)', account_name)
        if match:
            bank_name = match.group(1).strip()
            print(f"    ✓ 提取银行信息：'{account_name}' -> 银行={bank_name}, 无账号")
        else:
            print(f"    跳过：无法解析核算项目")
            # 调试：显示字符串的字节表示
            print(f"      字符串 bytes: {account_name.encode('utf-8')}")

    return bank_name, account_suffix


def round_diff(value: float) -> float:
    """四舍五入保留 2 位小数"""
    return round(value, 2)


# ──────────────────────────────────────────────────────────────────────────────
# 数据加载函数
# ──────────────────────────────────────────────────────────────────────────────

def load_subject_balance_sheet(data_dir: Path) -> Optional[pd.DataFrame]:
    """加载科目余额表"""
    files = [f for f in data_dir.glob('*.xlsx') if f.is_file()]

    # 查找科目余额表文件
    target_file = None
    for f in files:
        if is_subject_balance_sheet(f):
            target_file = f
            break

    if not target_file:
        print("未找到科目余额表文件")
        return None

    print(f"找到科目余额表：{target_file.name}")

    # 先读取前 10 行查看结构
    df_preview = pd.read_excel(target_file, sheet_name=0, header=None, nrows=10)
    print("科目余额表前 10 行预览:")
    for idx in range(min(5, len(df_preview))):
        row_data = df_preview.iloc[idx].tolist()
        print(f"  行{idx}: {row_data[:15]}")  # 显示前 15 列

    # 查找数据起始行（包含"科目代码"的行）
    header_row = None
    for idx in range(min(10, len(df_preview))):
        row_str = ' '.join([str(val) for val in df_preview.iloc[idx].values if pd.notna(val)])
        if '科目代码' in row_str and '科目名称' in row_str:
            header_row = idx
            break

    if header_row is None:
        print("错误：未找到科目余额表表头")
        return None

    print(f"表头位于第 {header_row} 行")

    # 检查是否有二级表头（借方/贷方）
    # 读取表头行和下一行
    header_row_data = df_preview.iloc[header_row].tolist()
    next_row_data = df_preview.iloc[header_row + 1].tolist() if header_row + 1 < len(df_preview) else []
    
    # 检查第二行是否包含"借方"或"贷方"
    has_sub_header = any('借方' in str(v) or '贷方' in str(v) for v in next_row_data if pd.notna(v))
    
    if has_sub_header:
        print("检测到二级表头（借方/贷方），使用多级表头读取...")
        # 使用多级表头读取
        df = pd.read_excel(target_file, sheet_name=0, header=[header_row, header_row + 1])
        
        # 清理多级列名
        new_columns = []
        for col in df.columns:
            if isinstance(col, tuple):
                # 合并两级表头：一级 + 二级
                level1 = str(col[0]) if pd.notna(col[0]) else ''
                level2 = str(col[1]) if pd.notna(col[1]) else ''
                
                # 如果二级是借方或贷方，合并为：一级_借方/贷方
                if level2 in ['借方', '贷方']:
                    new_columns.append(f"{level1}_{level2}")
                elif level2 and level2 != 'nan':
                    new_columns.append(f"{level1}_{level2}")
                else:
                    new_columns.append(level1)
            else:
                new_columns.append(str(col))
        
        df.columns = new_columns
        # 从第 2 行开始（跳过表头行）
        df = df.iloc[1:].reset_index(drop=True)
    else:
        # 单级表头
        df = pd.read_excel(target_file, sheet_name=0, header=header_row)
        # 从第 1 行开始（跳过表头行）
        df = df.iloc[1:].reset_index(drop=True)

    # 清理列名（移除 Unnamed 列）
    df = df.loc[:, ~df.columns.str.contains('^Unnamed', na=False)]
    
    # 简化列名：移除多余的后缀
    simplified_columns = {}
    for col in df.columns:
        # 保留核心列名
        if '科目代码' in col:
            simplified_columns[col] = '科目代码'
        elif '科目名称' in col:
            simplified_columns[col] = '科目名称'
        elif '公司' in col:
            simplified_columns[col] = '公司'
        elif '核算项目' in col:
            simplified_columns[col] = '核算项目'
        elif '年初余额_借方' == col:
            simplified_columns[col] = '年初余额_借方'
        elif '年初余额_贷方' == col:
            simplified_columns[col] = '年初余额_贷方'
        elif '期初余额_借方' == col:
            simplified_columns[col] = '期初余额_借方'
        elif '期初余额_贷方' == col:
            simplified_columns[col] = '期初余额_贷方'
        elif '本期发生额_借方' == col:
            simplified_columns[col] = '本期发生额_借方'
        elif '本期发生额_贷方' == col:
            simplified_columns[col] = '本期发生额_贷方'
        elif '本年累计_借方' == col:
            simplified_columns[col] = '本年累计_借方'
        elif '本年累计_贷方' == col:
            simplified_columns[col] = '本年累计_贷方'
        elif '期末余额_借方' == col:
            simplified_columns[col] = '期末余额_借方'
        elif '期末余额_贷方' in col:
            # 有多个期末余额_贷方列，只保留第一个
            if '期末余额_贷方' not in list(simplified_columns.values()):
                simplified_columns[col] = '期末余额_贷方'
        else:
            simplified_columns[col] = col
    
    df = df.rename(columns=simplified_columns)
    # 删除重复列
    df = df.loc[:, ~df.columns.duplicated()]

    # 删除空行
    df = df.dropna(how='all').reset_index(drop=True)

    print(f"科目余额表列名：{list(df.columns)}")
    print(f"加载完成，共 {len(df)} 条记录")

    # 显示前 3 行数据用于调试
    if len(df) > 0:
        print(f"前 3 行数据预览:")
        print(df.head(3).to_string())

    return df


def load_bank_statements(data_dir: Path) -> Dict[str, pd.DataFrame]:
    """加载所有银行对账单和银行日记账"""
    files = [f for f in data_dir.glob('*.xlsx') if f.is_file()]

    bank_statements = {}

    for f in files:
        if is_bank_statement(f):
            print(f"找到银行对账单文件：{f.name}")

            try:
                xl = pd.ExcelFile(f)

                # 读取所有 sheet
                for sheet_name in xl.sheet_names:
                    # 检查是否为银行对账单 sheet
                    df = pd.read_excel(f, sheet_name=sheet_name)

                    # 检查是否包含银行对账单特征
                    all_cols = ' '.join([str(col) for col in df.columns])

                    # 改进：检查更多银行对账单特征
                    is_statement = (
                        '发生+' in all_cols or 
                        '借方金额' in all_cols or
                        ('账号' in all_cols and '余额' in all_cols) or
                        # 银行日记账特征
                        ('核算项目' in all_cols and '借方' in all_cols and '贷方' in all_cols and '余额' in all_cols)
                    )

                    if is_statement and len(df) > 0:
                        # 这是一个银行对账单/日记账 sheet
                        bank_statements[sheet_name] = df
                        print(f"  - 加载 sheet: {sheet_name} ({len(df)} 行)")

            except Exception as e:
                print(f"读取银行对账单失败 {f.name}: {e}")

    return bank_statements


# ──────────────────────────────────────────────────────────────────────────────
# 数据处理函数
# ──────────────────────────────────────────────────────────────────────────────

def filter_cash_subjects(df: pd.DataFrame) -> pd.DataFrame:
    """过滤出货币资金相关科目"""
    # 货币资金关键词
    cash_keywords = ['库存现金', '银行存款', '其他货币资金']
    
    # 过滤
    mask = df['科目名称'].astype(str).str.contains('|'.join(cash_keywords), na=False)
    filtered_df = df[mask].copy()
    
    print(f"从 {len(df)} 条记录中过滤出 {len(filtered_df)} 条货币资金相关记录")
    
    return filtered_df


def parse_balance_columns(df: pd.DataFrame) -> pd.DataFrame:
    """解析余额列（处理借方/贷方分列的情况）"""
    result_df = df.copy()
    
    # 处理多级表头：可能存在 (期初余额, 借方) 和 (期初余额, 贷方) 的列
    # 重命名多级列名
    new_columns = []
    for col in result_df.columns:
        if isinstance(col, tuple):
            # 多级表头，合并为单个字符串
            col_name = ''.join([str(c) for c in col if pd.notna(c) and str(c) != 'nan'])
            new_columns.append(col_name)
        else:
            new_columns.append(str(col))
    result_df.columns = new_columns
    
    print(f"处理后的列名：{list(result_df.columns)}")  # 只显示前10个
    
    # 查找并合并借方/贷方列
    def find_and_merge_balance(prefix: str) -> Optional[str]:
        """查找并合并借贷方列，返回新列名"""
        debit_cols = [c for c in result_df.columns if prefix in c and ('借方' in c or '借' in c)]
        credit_cols = [c for c in result_df.columns if prefix in c and ('贷方' in c or '贷' in c)]
        
        if debit_cols and credit_cols:
            debit_col = debit_cols[0]
            credit_col = credit_cols[0]
            
            # 计算净额（借方 - 贷方）
            debit_val = pd.to_numeric(result_df[debit_col], errors='coerce').fillna(0)
            credit_val = pd.to_numeric(result_df[credit_col], errors='coerce').fillna(0)
            result_df[prefix] = debit_val - credit_val
            
            print(f"  合并列：{debit_col} - {credit_col} -> {prefix}")
            return prefix
        elif debit_cols:
            # 只有借方列
            result_df[prefix] = pd.to_numeric(result_df[debit_cols[0]], errors='coerce').fillna(0)
            print(f"  使用借方列：{debit_cols[0]} -> {prefix}")
            return prefix
        elif credit_cols:
            # 只有贷方列
            result_df[prefix] = -pd.to_numeric(result_df[credit_cols[0]], errors='coerce').fillna(0)
            print(f"  使用贷方列：{credit_cols[0]} -> {prefix}")
            return prefix
        
        return None
    
    # 处理期初余额
    find_and_merge_balance('期初余额')
    find_and_merge_balance('年初余额')  # 有些表格使用"年初余额"

    # 处理期末余额
    find_and_merge_balance('期末余额')

    # 处理本期发生额 - 关键修复
    # 科目余额表通常有两种格式：
    # 格式 1: 本期发生额（单列，正数表示借方，负数表示贷方）
    # 格式 2: 本期发生额_借方 和 本期发生额_贷方（两列）
    
    # 检查是否有分开的借贷方列（新格式：本期发生额_借方/贷方）
    has_debit_col = '本期发生额_借方' in result_df.columns
    has_credit_col = '本期发生额_贷方' in result_df.columns
    
    if has_debit_col and has_credit_col:
        # 格式 2：分开的借贷方列
        result_df['本期借方'] = pd.to_numeric(result_df['本期发生额_借方'], errors='coerce').fillna(0)
        result_df['本期贷方'] = pd.to_numeric(result_df['本期发生额_贷方'], errors='coerce').fillna(0)
        print(f"  本期借方：本期发生额_借方")
        print(f"  本期贷方：本期发生额_贷方")
    
    else:
        # 格式 1：单列"本期发生额"
        # 查找本期发生额列
        occurrence_cols = [c for c in result_df.columns if '本期发生额' in c and '_借方' not in c and '_贷方' not in c]
        
        if occurrence_cols:
            occurrence_col = occurrence_cols[0]
            print(f"  找到本期发生额列：{occurrence_col}")
            
            # 读取发生额数据
            occurrence_values = pd.to_numeric(result_df[occurrence_col], errors='coerce').fillna(0)
            
            # 根据正负值分离借方和贷方
            # 正数 = 借方，负数 = 贷方（取绝对值）
            result_df['本期借方'] = occurrence_values.apply(lambda x: x if x > 0 else 0)
            result_df['本期贷方'] = occurrence_values.apply(lambda x: abs(x) if x < 0 else 0)
            
            print(f"  从 {occurrence_col} 分离出本期借方和本期贷方")
            
            # 显示示例数据
            sample_data = result_df[['科目名称', '本期借方', '本期贷方']].head(3)
            print(f"  示例数据:\n{sample_data.to_string()}")
        else:
            print(f"  警告：未找到本期发生额相关列")
            print(f"  可用列：{[c for c in result_df.columns if '本期' in c or '发生' in c]}")
            result_df['本期借方'] = 0
            result_df['本期贷方'] = 0

    return result_df


def calculate_bank_statement_amount(account_name: str, bank_statements: Dict[str, pd.DataFrame]) -> float:
    """根据核算项目，从银行对账单中读取期末余额（最后一笔交易的余额列）
    
    严格按照 cash_skill.md 的要求：
    1. 只从"银行对账单"或"自有对账单"sheet 读取数据
    2. 严禁从"日记账"sheet 读取数据
    3. 如果没有可用的银行对账单，返回 0
    
    匹配优先级:
    1. Sheet 名称包含"{银行名称}+ 对账单"
    2. Sheet 名称包含"银行对账单"且账户名称包含银行名称
    3. Sheet 名称包含"自有对账单"且账户名称包含银行名称
    """
    bank_name, account_suffix = extract_bank_info_from_account(account_name)

    if not bank_name and not account_suffix:
        print(f"    跳过：无法从核算项目中提取银行信息")
        return 0.0

    print(f"  查找银行对账单：银行={bank_name}, 账号后 5 位={account_suffix if account_suffix else '(无)'}")

    # ──────────────────────────────────────────────────────────────────────────────
    # 步骤 1: 分类所有 sheet，区分银行对账单和银行日记账
    # ──────────────────────────────────────────────────────────────────────────────
    
    bank_statements_available = []  # 可用的银行对账单
    bank_journals = []  # 银行日记账（严禁使用）
    
    for sheet_name, df in bank_statements.items():
        # 检查是否为银行日记账（企业方的记录，非银行方记录）
        all_cols = ' '.join([str(col) for col in df.columns])
        is_bank_journal = '核算项目' in all_cols and '凭证字号' in all_cols
        
        if is_bank_journal:
            bank_journals.append((sheet_name, df))
            print(f"    识别为银行日记账（不可用）: {sheet_name}")
        else:
            bank_statements_available.append((sheet_name, df))
            print(f"    识别为银行对账单（可用）: {sheet_name}")
    
    # ──────────────────────────────────────────────────────────────────────────────
    # 步骤 2: 如果没有可用的银行对账单，直接返回 0
    # ──────────────────────────────────────────────────────────────────────────────
    
    if not bank_statements_available:
        print(f"    ⚠️ 未找到任何银行对账单，银行对账单金额 = 0")
        return 0.0
    
    # ──────────────────────────────────────────────────────────────────────────────
    # 步骤 3: 按照优先级匹配银行对账单
    # ──────────────────────────────────────────────────────────────────────────────
    
    matched_sheet = None
    
    # 优先级 1: Sheet 名称包含"{银行名称}+ 对账单"
    for sheet_name, df in bank_statements_available:
        if bank_name in sheet_name and '对账单' in sheet_name:
            matched_sheet = (sheet_name, df)
            print(f"    ✓ 优先级 1 匹配：{sheet_name}")
            break
    
    # 优先级 2: Sheet 名称包含"银行对账单"且账户名称或账户类别包含银行名称
    if not matched_sheet:
        for sheet_name, df in bank_statements_available:
            if '银行对账单' in sheet_name:
                # 检查账户名称列或账户类别列
                matched = False
                for col in ['账户名', '账户名称', '账号名称', '账户类别']:
                    if col in df.columns and len(df) > 0:
                        # 检查该列的所有值是否包含银行名称
                        for val in df[col].dropna().unique():
                            if bank_name in str(val):
                                matched_sheet = (sheet_name, df)
                                print(f"    ✓ 优先级 2 匹配：{sheet_name} ({col}={val})")
                                matched = True
                                break
                        if matched:
                            break
                if matched:
                    break
    
    # 优先级 3: Sheet 名称包含"自有对账单"且账户名称或账户类别包含银行名称
    if not matched_sheet:
        for sheet_name, df in bank_statements_available:
            if '自有对账单' in sheet_name:
                # 检查账户名称列或账户类别列
                matched = False
                for col in ['账户名', '账户名称', '账号名称', '账户类别']:
                    if col in df.columns and len(df) > 0:
                        # 检查该列的所有值是否包含银行名称
                        for val in df[col].dropna().unique():
                            if bank_name in str(val):
                                matched_sheet = (sheet_name, df)
                                print(f"    ✓ 优先级 3 匹配：{sheet_name} ({col}={val})")
                                matched = True
                                break
                        if matched:
                            break
                if matched:
                    break
    
    # 如果没有匹配到任何 sheet
    if not matched_sheet:
        print(f"    ✗ 未找到匹配的银行对账单，银行对账单金额 = 0")
        return 0.0
    
    # ──────────────────────────────────────────────────────────────────────────────
    # 步骤 4: 从匹配的银行对账单中读取余额
    # ──────────────────────────────────────────────────────────────────────────────
    
    sheet_name, df = matched_sheet
    print(f"    从 {sheet_name} 中读取银行对账单金额")
    
    # 查找账号列
    account_col = None
    for col in ['账号', '账户类别', '卡号']:
        if col in df.columns:
            account_col = col
            break
    
    # 查找余额列
    balance_col = None
    for col in ['余额', '账户余额', '当前余额', '流水余额']:
        if col in df.columns:
            balance_col = col
            break
    
    if not balance_col:
        print(f"      未找到余额列，可用列：{list(df.columns)[:10]}...")
        print(f"      银行对账单金额 = 0")
        return 0.0
    
    # 过滤出匹配账号后 5 位的记录
    matched_rows = []
    
    if account_col and account_suffix:
        # 有账号列和账号后 5 位，进行精确匹配
        for idx, row in df.iterrows():
            account = str(row.get(account_col, ''))
            # 清理账号字符串（移除引号、空格、特殊字符）
            account = account.strip().strip("'").replace(' ', '').replace(',', '')
            
            # 检查账号匹配（后 5 位或包含）
            if account.endswith(account_suffix) or (account_suffix in account):
                matched_rows.append(row)
        
        if matched_rows:
            print(f"      匹配到 {len(matched_rows)} 条记录（账号后 5 位={account_suffix}）")
        else:
            # 显示该列的所有账号用于调试
            all_accounts = df[account_col].dropna().unique()[:5]
            print(f"      未匹配到账号，该列账号示例：{list(all_accounts)}")
            print(f"      银行对账单金额 = 0")
            return 0.0
    
    elif len(df) > 0:
        # 没有账号列或账号，使用整个 sheet 数据
        print(f"      无账号列，使用整个 sheet 数据（{len(df)} 条记录）")
        matched_rows = [row for _, row in df.iterrows()]
    
    if not matched_rows:
        print(f"      未找到匹配的记录，银行对账单金额 = 0")
        return 0.0
    
    # 取最后一笔交易的余额
    last_row = matched_rows[-1]
    balance_value = last_row.get(balance_col, 0)
    
    # 处理余额值：移除"借"/"贷"标识和千位分隔符
    if isinstance(balance_value, str):
        # 移除"借"/"贷"标识
        balance_value = balance_value.replace('借', '').replace('贷', '')
        # 移除千位分隔符（逗号和空格）
        balance_value = balance_value.replace(',', '').replace(' ', '').strip()
        print(f"      原始余额值：'{last_row.get(balance_col)}' -> 清理后：'{balance_value}'")
    
    # 转换为数值
    ending_balance = pd.to_numeric(balance_value, errors='coerce')
    
    if pd.notna(ending_balance):
        print(f"      ✓ 匹配成功！最后一笔余额 = {ending_balance:.2f}（共 {len(matched_rows)} 笔交易）")
        return float(ending_balance)
    else:
        print(f"      余额列数据无效：{balance_value}，银行对账单金额 = 0")
        return 0.0




def generate_cash_detail_table(subject_df: pd.DataFrame, bank_statements: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """生成货币资金明细表"""
    result_data = []
    
    for idx, row in subject_df.iterrows():
        account_name = row.get('科目名称', '')
        account_project = row.get('核算项目', '')
        
        # 获取余额数据（已经在 parse_balance_columns 中合并计算）
        beginning_balance = pd.to_numeric(row.get('期初余额', row.get('年初余额', 0)), errors='coerce') or 0
        debit_amount = pd.to_numeric(row.get('本期借方', 0), errors='coerce') or 0
        credit_amount = pd.to_numeric(row.get('本期贷方', 0), errors='coerce') or 0
        ending_balance = pd.to_numeric(row.get('期末余额', 0), errors='coerce') or 0
        
        # 如果是银行存款，从银行对账单读取期末余额
        bank_statement_amount = 0.0
        if '银行存款' in account_name:
            # 准备传递给匹配函数的参数
            match_param = account_project if pd.notna(account_project) and account_project else account_name
            print(f"\n处理银行存款：{account_name}")
            print(f"  核算项目：{account_project if pd.notna(account_project) else '(空)'}")
            print(f"  匹配参数：{match_param}")
            bank_statement_amount = calculate_bank_statement_amount(
                match_param,
                bank_statements
            )
        
        # 计算差异
        diff = round_diff(ending_balance - bank_statement_amount)
        
        # 确定账户性质
        account_type = "现金" if '库存现金' in account_name else ("其他货币资金" if '其他货币资金' in account_name else "银行存款")
        
        # 添加到结果
        result_data.append({
            '序号': len(result_data) + 1,
            '科目名称': account_name,
            '核算项目': account_project if pd.notna(account_project) else '-',
            '期初金额': round_diff(beginning_balance),
            '本期借方': round_diff(debit_amount),
            '本期贷方': round_diff(credit_amount),
            '期末金额': round_diff(ending_balance),
            '银行对账单金额': round_diff(bank_statement_amount),
            '差异': diff,
            '账户性质': account_type,
            '备注': '-'
        })
    
    return pd.DataFrame(result_data)


# ──────────────────────────────────────────────────────────────────────────────
# 输出函数
# ──────────────────────────────────────────────────────────────────────────────

def export_to_markdown(df: pd.DataFrame, output_path: Path) -> None:
    """导出为 Markdown 格式"""
    # 转换为 Markdown 表格
    markdown_table = df.to_markdown(index=False)
    
    # 添加标题和说明
    content = f"""# 货币资金明细表

**生成时间**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}

## 明细表数据

{markdown_table}

## 汇总统计

- **总记录数**: {len(df)}
- **期初金额合计**: {df['期初金额'].sum():,.2f}
- **期末金额合计**: {df['期末金额'].sum():,.2f}
- **银行对账单金额合计**: {df['银行对账单金额'].sum():,.2f}
- **差异合计**: {df['差异'].sum():,.2f}

## 数据说明

1. 数据来源：科目余额表、银行对账单
2. 差异 = 期末金额 - 银行对账单金额
3. 银行对账单金额从对应银行的对账单中读取本期余额
"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"已导出货币资金明细表到：{output_path}")


def export_to_excel(df: pd.DataFrame, output_path: Path) -> None:
    """导出为 Excel 格式"""
    df.to_excel(output_path, index=False, sheet_name='货币资金明细表')
    print(f"已导出货币资金明细表到：{output_path}")


# ──────────────────────────────────────────────────────────────────────────────
# 主函数
# ──────────────────────────────────────────────────────────────────────────────

def main():
    """主函数：执行货币资金明细表生成流程"""
    print("="*60)
    print("货币资金明细表生成脚本")
    print("="*60)
    
    # 1. 加载科目余额表
    print("\n[步骤 1] 加载科目余额表...")
    subject_df = load_subject_balance_sheet(DATA_DIR)
    
    if subject_df is None or len(subject_df) == 0:
        print("错误：未找到科目余额表数据")
        return
    
    print(f"加载完成，共 {len(subject_df)} 条记录")
    
    # 2. 加载银行对账单
    print("\n[步骤 2] 加载银行对账单...")
    bank_statements = load_bank_statements(DATA_DIR)
    
    if not bank_statements:
        print("警告：未找到银行对账单数据")
        bank_statements = {}
    
    # 3. 过滤货币资金科目
    print("\n[步骤 3] 过滤货币资金科目...")
    cash_subjects = filter_cash_subjects(subject_df)
    
    if len(cash_subjects) == 0:
        print("错误：未找到货币资金相关科目")
        return
    
    # 4. 解析余额列
    print("\n[步骤 4] 解析余额列...")
    cash_subjects = parse_balance_columns(cash_subjects)
    
    # 5. 生成货币资金明细表
    print("\n[步骤 5] 生成货币资金明细表...")
    detail_df = generate_cash_detail_table(cash_subjects, bank_statements)
    
    print(f"生成完成，共 {len(detail_df)} 条明细记录")
    
    # 6. 导出结果
    print("\n[步骤 6] 导出结果...")
    
    # 导出为 Markdown
    md_output = RESULT_DIR / '货币资金明细表.md'
    export_to_markdown(detail_df, md_output)
    
    # 导出为 Excel
    excel_output = RESULT_DIR / '货币资金明细表.xlsx'
    export_to_excel(detail_df, excel_output)
    
    # 7. 显示结果预览
    print("\n" + "="*60)
    print("结果预览（前 10 条记录）:")
    print("="*60)
    print(detail_df.head(10).to_string(index=False))
    
    print("\n" + "="*60)
    print("脚本执行完成!")
    print("="*60)


if __name__ == '__main__':
    main()
