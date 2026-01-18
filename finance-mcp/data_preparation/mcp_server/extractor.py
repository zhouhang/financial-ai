"""
数据提取器 - 从各种数据源提取数据
阶段1：支持 Excel
阶段2：支持 PDF
阶段3：支持图片 OCR
"""
import pandas as pd
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
import re

logger = logging.getLogger(__name__)


class DataExtractor:
    """数据提取器基类"""
    
    def __init__(self, schema: Dict):
        self.schema = schema
        self.data_sources = schema.get("data_sources", {})
    
    def extract(self, source_id: str, file_path: str) -> pd.DataFrame:
        """
        根据数据源配置提取数据
        
        Args:
            source_id: 数据源ID (如 source_1, source_2)
            file_path: 文件路径
        
        Returns:
            提取的数据 DataFrame
        """
        if source_id not in self.data_sources:
            raise ValueError(f"未知的数据源: {source_id}")
        
        source_config = self.data_sources[source_id]
        source_type = source_config.get("type", "").lower()
        
        # 如果 type 是 excel，但文件是 CSV，自动切换
        file_ext = Path(file_path).suffix.lower()
        if source_type == "excel" and file_ext == ".csv":
            logger.info(f"检测到 CSV 文件，自动切换到 CSV 提取器: {file_path}")
            source_type = "csv"
        
        if source_type == "excel":
            return self._extract_from_excel(file_path, source_config)
        elif source_type == "csv":
            return self._extract_from_csv(file_path, source_config)
        elif source_type == "pdf":
            return self._extract_from_pdf(file_path, source_config)
        elif source_type == "image":
            return self._extract_from_image(file_path, source_config)
        else:
            raise ValueError(f"不支持的数据源类型: {source_type}")
    
    def _extract_from_excel(self, file_path: str, config: Dict) -> pd.DataFrame:
        """从 Excel 文件提取数据"""
        extraction_rules = config.get("extraction_rules", {})
        
        # 读取 Excel
        sheet_name = extraction_rules.get("sheet_name", 0)
        skip_rows = extraction_rules.get("skip_rows", 0)
        
        # 支持多级表头
        multi_index_header = extraction_rules.get("multi_index_header")
        
        try:
            if multi_index_header:
                # 使用多级表头
                df = pd.read_excel(file_path, sheet_name=sheet_name, header=multi_index_header)
                logger.info(f"Excel 读取成功（多级表头）: {file_path}, sheet={sheet_name}, 行数={len(df)}")
                # 将多级列名扁平化：("期初余额", "借方") -> "期初余额_借方"
                if isinstance(df.columns, pd.MultiIndex):
                    new_columns = []
                    seen_cols = {}  # 用于处理重复列名
                    for i, col in enumerate(df.columns.values):
                        if isinstance(col, tuple):
                            # 过滤掉 "Unnamed" 和空值
                            parts = [str(c) for c in col if c and 'Unnamed' not in str(c)]
                            new_col = '_'.join(parts) if parts else str(col[0]) if len(col) > 0 else f'Unnamed_{i}'
                        else:
                            new_col = str(col)
                        
                        # 处理重复列名
                        if new_col in seen_cols:
                            seen_cols[new_col] += 1
                            new_col = f"{new_col}_{seen_cols[new_col]}"
                        else:
                            seen_cols[new_col] = 0
                        
                        new_columns.append(new_col)
                    
                    df.columns = new_columns
                    logger.info(f"多级表头扁平化完成，列名示例: {list(df.columns[:5])}")
            else:
                df = pd.read_excel(file_path, sheet_name=sheet_name, skiprows=skip_rows)
                logger.info(f"Excel 读取成功: {file_path}, sheet={sheet_name}, 行数={len(df)}")
        except Exception as e:
            logger.error(f"Excel 读取失败: {file_path}, 错误: {str(e)}")
            raise
        
        # 应用列映射
        columns_mapping = extraction_rules.get("columns_mapping", {})
        if columns_mapping:
            df = self._apply_column_mapping(df, columns_mapping)
        
        # 应用范围筛选
        range_str = extraction_rules.get("range")
        if range_str:
            df = self._apply_range_filter(df, range_str)
        
        # 应用条件提取
        conditional_extractions = config.get("conditional_extractions")
        if conditional_extractions:
            result_df = self._apply_conditional_extraction(df, conditional_extractions)
            # 如果返回的是筛选后的DataFrame（表格输出），使用它
            # 检查是否是表格输出（通常会有特定的output_type或字段数量减少）
            output_type = conditional_extractions.get("extraction", {}).get("output_type", "value")
            if output_type == "table" and isinstance(result_df, pd.DataFrame):
                df = result_df
                logger.info(f"条件提取返回表格数据: {len(df)} 行 x {len(df.columns)} 列")
        
        # 应用验证规则
        validation_rules = config.get("validation_rules", [])
        if validation_rules:
            df = self._apply_validation(df, validation_rules)
        
        return df
    
    def _extract_from_csv(self, file_path: str, config: Dict) -> pd.DataFrame:
        """从 CSV 文件提取数据"""
        extraction_rules = config.get("extraction_rules", {})
        skip_rows = extraction_rules.get("skip_rows", 0)
        
        # 尝试不同编码
        for encoding in ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'gb18030']:
            try:
                df = pd.read_csv(file_path, encoding=encoding, skiprows=skip_rows)
                logger.info(f"CSV 读取成功: {file_path}, 编码={encoding}, 行数={len(df)}")
                break
            except (UnicodeDecodeError, LookupError):
                continue
        else:
            raise ValueError(f"无法读取 CSV 文件，编码不支持: {file_path}")
        
        # 应用列映射
        columns_mapping = extraction_rules.get("columns_mapping", {})
        if columns_mapping:
            df = self._apply_column_mapping(df, columns_mapping)
        
        return df
    
    def _extract_from_pdf(self, file_path: str, config: Dict) -> pd.DataFrame:
        """从 PDF 文件提取数据（阶段2实现）"""
        raise NotImplementedError("PDF 提取功能将在阶段2实现")
    
    def _extract_from_image(self, file_path: str, config: Dict) -> pd.DataFrame:
        """从图片提取数据（阶段3实现）"""
        raise NotImplementedError("图片 OCR 功能将在阶段3实现")
    
    def _apply_column_mapping(self, df: pd.DataFrame, mapping: Dict) -> pd.DataFrame:
        """
        应用列映射
        mapping 格式: {"A": "date", "B": "amount"} 或 {"原列名": "新列名"}
        支持部分匹配（如 "科目名称" 匹配 "科目名称_Unnamed: 1_level_1"）
        """
        rename_dict = {}
        
        # 处理 Excel 列标识符 (A, B, C...)
        for key, value in mapping.items():
            if len(key) <= 2 and key.isalpha() and key.isupper():
                # Excel 列标识符
                col_index = self._excel_col_to_index(key)
                if col_index < len(df.columns):
                    original_col = df.columns[col_index]
                    rename_dict[original_col] = value
            else:
                # 直接列名映射或部分匹配
                if key in df.columns:
                    rename_dict[key] = value
                else:
                    # 尝试部分匹配（扁平化后的列名可能包含原列名）
                    matching_cols = [col for col in df.columns if str(col).startswith(key) or key in str(col)]
                    if matching_cols:
                        # 取第一个匹配的列
                        rename_dict[matching_cols[0]] = value
                        logger.info(f"列映射部分匹配: '{key}' -> '{matching_cols[0]}' -> '{value}'")
        
        if rename_dict:
            df = df.rename(columns=rename_dict)
            logger.info(f"应用列映射: {len(rename_dict)} 列")
        
        return df
    
    def _apply_range_filter(self, df: pd.DataFrame, range_str: str) -> pd.DataFrame:
        """
        应用范围筛选 (如 "A2:Z1000")
        """
        # 解析范围字符串 "A2:Z1000"
        match = re.match(r"([A-Z]+)(\d+):([A-Z]+)(\d+)", range_str)
        if not match:
            logger.warning(f"无效的范围格式: {range_str}")
            return df
        
        start_col, start_row, end_col, end_row = match.groups()
        start_row = int(start_row) - 1  # 转为0索引
        end_row = int(end_row)
        
        # 行筛选
        df = df.iloc[start_row:end_row]
        
        # 列筛选
        start_col_idx = self._excel_col_to_index(start_col)
        end_col_idx = self._excel_col_to_index(end_col) + 1
        df = df.iloc[:, start_col_idx:end_col_idx]
        
        logger.info(f"应用范围筛选: {range_str}, 结果: {len(df)} 行")
        return df
    
    def _apply_conditional_extraction(self, df: pd.DataFrame, config: Dict) -> pd.DataFrame:
        """
        应用条件提取
        支持复杂的 AND/OR 条件组合
        支持表格输出（output_type: "table"）
        """
        condition = config.get("condition", {})
        extraction = config.get("extraction", {})
        output_type = extraction.get("output_type", "value")
        
        # 评估条件
        mask = self._evaluate_condition(df, condition)
        
        # 筛选满足条件的行
        filtered_df = df[mask].copy()
        
        if output_type == "table":
            # 表格输出：返回筛选后的DataFrame，选择指定字段
            target_fields = extraction.get("target_fields", [])
            if target_fields:
                # 构建要提取的列列表
                cols_to_extract = []
                for field in target_fields:
                    if isinstance(field, str):
                        # 简单字段名
                        if field in filtered_df.columns:
                            cols_to_extract.append(field)
                    elif isinstance(field, dict):
                        # 多级字段：{"field": "期初余额", "sub_field": "借方", "output_field": "opening_balance_debit"}
                        field_name = field.get("field")
                        sub_field = field.get("sub_field")
                        output_field = field.get("output_field", f"{field_name}_{sub_field}")
                        
                        # 查找匹配的列（扁平化后格式："期初余额_借方"）
                        # 查找包含 field_name 和 sub_field 的列
                        matching_cols = [
                            c for c in filtered_df.columns 
                            if field_name in str(c) and sub_field in str(c)
                        ]
                        
                        if matching_cols:
                            # 取第一个匹配的列
                            matched_col = matching_cols[0]
                            filtered_df = filtered_df.rename(columns={matched_col: output_field})
                            cols_to_extract.append(output_field)
                            logger.debug(f"多级字段提取: '{matched_col}' -> '{output_field}'")
                        else:
                            logger.warning(f"未找到匹配的多级字段: {field_name} + {sub_field}")
                
                if cols_to_extract:
                    filtered_df = filtered_df[cols_to_extract]
                    logger.info(f"条件提取（表格）: {config.get('name')}, 满足条件: {len(filtered_df)} 行, 字段: {cols_to_extract}")
                    return filtered_df
        
        # 原有的单值输出逻辑
        target_column = extraction.get("target_column")
        output_field = extraction.get("output_field")
        aggregation = extraction.get("aggregation", "first")
        
        if target_column and target_column in filtered_df.columns:
            # 应用聚合
            if aggregation == "sum":
                value = filtered_df[target_column].sum()
            elif aggregation == "count":
                value = len(filtered_df)
            elif aggregation == "mean":
                value = filtered_df[target_column].mean()
            elif aggregation == "first":
                value = filtered_df[target_column].iloc[0] if len(filtered_df) > 0 else None
            else:
                value = None
            
            # 添加到原始 DataFrame
            if output_field:
                df[output_field] = value
            
            logger.info(f"条件提取: {config.get('name')}, 满足条件: {mask.sum()} 行, 结果: {value}")
        
        return df
    
    def _evaluate_condition(self, df: pd.DataFrame, condition: Dict) -> pd.Series:
        """
        评估条件表达式
        支持: and, or, column_equals, column_empty, column_contains 等
        """
        condition_type = condition.get("type")
        
        if condition_type == "and":
            # AND 条件
            conditions = condition.get("conditions", [])
            mask = pd.Series([True] * len(df), index=df.index)
            for cond in conditions:
                mask = mask & self._evaluate_condition(df, cond)
            return mask
        
        elif condition_type == "or":
            # OR 条件
            conditions = condition.get("conditions", [])
            mask = pd.Series([False] * len(df), index=df.index)
            for cond in conditions:
                mask = mask | self._evaluate_condition(df, cond)
            return mask
        
        elif condition_type == "column_equals":
            # 列值等于
            column = condition.get("column_header")
            value = condition.get("value")
            match_type = condition.get("match_type", "exact")
            
            if column not in df.columns:
                return pd.Series([False] * len(df), index=df.index)
            
            if match_type == "exact":
                return df[column] == value
            elif match_type == "contains":
                return df[column].astype(str).str.contains(str(value), na=False)
            else:
                return df[column] == value
        
        elif condition_type == "column_matches":
            # 正则表达式匹配
            column = condition.get("column_header")
            regex_pattern = condition.get("regex_pattern")
            match_type = condition.get("match_type", "regex")
            
            if column not in df.columns:
                return pd.Series([False] * len(df), index=df.index)
            
            if match_type == "regex":
                return df[column].astype(str).str.match(regex_pattern, na=False)
            else:
                return pd.Series([False] * len(df), index=df.index)
        
        elif condition_type == "column_empty":
            # 列为空
            column = condition.get("column_header")
            empty_check = condition.get("empty_check", True)
            
            if column not in df.columns:
                return pd.Series([True] * len(df), index=df.index)
            
            is_empty = df[column].isna() | (df[column].astype(str).str.strip() == "")
            return is_empty if empty_check else ~is_empty
        
        else:
            # 默认返回全 True
            return pd.Series([True] * len(df), index=df.index)
    
    def _apply_validation(self, df: pd.DataFrame, rules: List[Dict]) -> pd.DataFrame:
        """应用验证规则"""
        for rule in rules:
            rule_type = rule.get("rule")
            fields = rule.get("fields", [])
            
            if rule_type == "not_null":
                # 删除指定字段为空的行
                for field in fields:
                    if field in df.columns:
                        before = len(df)
                        df = df.dropna(subset=[field])
                        after = len(df)
                        if before != after:
                            logger.info(f"验证规则 not_null: 字段 {field}, 删除 {before - after} 行")
        
        return df
    
    @staticmethod
    def _excel_col_to_index(col: str) -> int:
        """将 Excel 列标识符转换为索引 (A=0, B=1, ...)"""
        index = 0
        for char in col:
            index = index * 26 + (ord(char) - ord('A') + 1)
        return index - 1
