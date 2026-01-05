"""
数据清洗器 - 字段映射、数据转换、合并等
支持灵活的规则配置
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
import re
from pathlib import Path


class DataCleaner:
    """数据清洗器"""
    
    def __init__(self, schema: Dict):
        self.schema = schema
        self.data_sources = schema.get("data_sources", {})
        self.cleaning_rules = schema.get("data_cleaning_rules", {})
    
    def load_and_clean(self, source_name: str, file_paths: List[str]) -> pd.DataFrame:
        """
        加载并清洗数据
        
        Args:
            source_name: 数据源名称 (business/finance)
            file_paths: 文件路径列表
        
        Returns:
            清洗后的 DataFrame
        """
        if source_name not in self.data_sources:
            raise ValueError(f"未知的数据源: {source_name}")
        
        source_config = self.data_sources[source_name]
        
        # 加载所有文件
        dfs = []
        for file_path in file_paths:
            df = self._load_file(file_path)
            # 添加文件名信息
            df['__source_file__'] = Path(file_path).name
            dfs.append(df)
        
        if not dfs:
            return pd.DataFrame()
        
        # 合并所有数据
        combined_df = pd.concat(dfs, ignore_index=True)
        
        # 字段映射
        mapped_df = self._map_fields(combined_df, source_config.get("field_roles", {}))
        
        # 数据清洗
        cleaned_df = self._apply_cleaning_rules(mapped_df, source_name, file_paths)
        
        # 删除临时字段
        if '__source_file__' in cleaned_df.columns:
            cleaned_df = cleaned_df.drop(columns=['__source_file__'])
        
        return cleaned_df
    
    def _load_file(self, file_path: str) -> pd.DataFrame:
        """加载文件"""
        if file_path.endswith('.csv'):
            # 尝试不同的编码
            for encoding in ['utf-8', 'gbk', 'gb2312', 'gb18030']:
                try:
                    return pd.read_csv(file_path, encoding=encoding)
                except (UnicodeDecodeError, LookupError):
                    continue
            raise ValueError(f"无法读取文件 {file_path}，编码不支持")
        elif file_path.endswith(('.xlsx', '.xls')):
            return pd.read_excel(file_path)
        else:
            raise ValueError(f"不支持的文件格式: {file_path}")
    
    def _map_fields(self, df: pd.DataFrame, field_roles: Dict[str, Any]) -> pd.DataFrame:
        """
        字段映射 - 将原始字段名映射为统一的角色名
        
        Args:
            df: 原始 DataFrame
            field_roles: 字段角色映射，如 {"order_id": "sup订单号", "amount": ["product_price", "面值"]}
        
        Returns:
            映射后的 DataFrame
        """
        mapped_df = df.copy()
        rename_map = {}
        
        for role, field_names in field_roles.items():
            # 如果是列表，找到第一个存在的字段
            if isinstance(field_names, list):
                for field_name in field_names:
                    if field_name in df.columns:
                        rename_map[field_name] = role
                        break
            elif isinstance(field_names, str):
                if field_names in df.columns:
                    rename_map[field_names] = role
        
        mapped_df = mapped_df.rename(columns=rename_map)
        return mapped_df
    
    def _apply_cleaning_rules(self, df: pd.DataFrame, source_name: str, file_paths: List[str]) -> pd.DataFrame:
        """
        应用数据清洗规则
        
        新的规则结构支持：
        1. field_transforms: 字段级别的转换
        2. row_filters: 行级别的过滤
        3. aggregations: 聚合规则
        4. global_transforms: 全局转换
        """
        cleaned_df = df.copy()
        
        if not self.cleaning_rules:
            return cleaned_df
        
        # 获取适用于当前数据源的规则
        source_rules = self.cleaning_rules.get(source_name, {})
        global_rules = self.cleaning_rules.get("global", {})
        
        # 合并规则（数据源规则优先）
        rules = {**global_rules, **source_rules}
        
        # 1. 行过滤（在转换之前）
        row_filters = rules.get("row_filters", [])
        if row_filters:
            cleaned_df = self._apply_row_filters(cleaned_df, row_filters)
        
        # 2. 字段转换
        field_transforms = rules.get("field_transforms", [])
        if field_transforms:
            cleaned_df = self._apply_field_transforms(cleaned_df, field_transforms, file_paths)
        
        # 3. 聚合
        aggregations = rules.get("aggregations", [])
        if aggregations:
            cleaned_df = self._apply_aggregations(cleaned_df, aggregations)
        
        # 4. 全局转换
        global_transforms = rules.get("global_transforms", [])
        if global_transforms:
            cleaned_df = self._apply_global_transforms(cleaned_df, global_transforms)
        
        # 5. 数据类型转换
        cleaned_df = self._convert_types(cleaned_df)
        
        return cleaned_df
    
    def _apply_row_filters(self, df: pd.DataFrame, filters: List[Dict]) -> pd.DataFrame:
        """
        应用行过滤规则
        
        示例:
        [
            {
                "condition": "row['amount'] > 0",
                "description": "过滤掉金额小于等于0的记录"
            },
            {
                "condition": "row['status'] == '已完成'",
                "description": "只保留已完成的记录"
            }
        ]
        """
        result_df = df.copy()
        
        for filter_rule in filters:
            condition = filter_rule.get("condition")
            if not condition:
                continue
            
            try:
                # 使用 apply 逐行判断
                mask = result_df.apply(lambda row: eval(condition, {"row": row, "pd": pd, "np": np}), axis=1)
                result_df = result_df[mask]
                print(f"应用过滤规则: {filter_rule.get('description', condition)}, 剩余 {len(result_df)} 条记录")
            except Exception as e:
                print(f"过滤规则执行失败: {condition}, 错误: {str(e)}")
        
        return result_df
    
    def _apply_field_transforms(self, df: pd.DataFrame, transforms: List[Dict], file_paths: List[str]) -> pd.DataFrame:
        """
        应用字段转换规则
        
        示例:
        [
            {
                "field": "amount",
                "operation": "divide",
                "value": 100,
                "condition": "file_pattern: *finance*.csv",
                "description": "财务金额单位转换（分->元）"
            },
            {
                "field": "date",
                "operation": "format_date",
                "format": "%Y-%m-%d",
                "description": "统一日期格式"
            },
            {
                "field": "amount",
                "operation": "expr",
                "expression": "row['amount'] * row['quantity']",
                "description": "计算总金额"
            }
        ]
        """
        result_df = df.copy()
        
        for transform in transforms:
            field = transform.get("field")
            operation = transform.get("operation")
            
            if not field or not operation:
                continue
            
            # 检查条件（如文件模式匹配）
            condition = transform.get("condition")
            if condition and condition.startswith("file_pattern:"):
                pattern = condition.split(":", 1)[1].strip()
                if not self._check_file_pattern_match(file_paths, pattern):
                    continue
            
            # 确保字段存在
            if field not in result_df.columns:
                print(f"字段 {field} 不存在，跳过转换")
                continue
            
            try:
                if operation == "divide":
                    value = transform.get("value", 1)
                    result_df[field] = pd.to_numeric(result_df[field], errors='coerce') / value
                
                elif operation == "multiply":
                    value = transform.get("value", 1)
                    result_df[field] = pd.to_numeric(result_df[field], errors='coerce') * value
                
                elif operation == "add":
                    value = transform.get("value", 0)
                    result_df[field] = pd.to_numeric(result_df[field], errors='coerce') + value
                
                elif operation == "subtract":
                    value = transform.get("value", 0)
                    result_df[field] = pd.to_numeric(result_df[field], errors='coerce') - value
                
                elif operation == "round":
                    decimals = transform.get("decimals", 2)
                    result_df[field] = pd.to_numeric(result_df[field], errors='coerce').round(decimals)
                
                elif operation == "abs":
                    result_df[field] = pd.to_numeric(result_df[field], errors='coerce').abs()
                
                elif operation == "format_date":
                    date_format = transform.get("format", "%Y-%m-%d")
                    result_df[field] = pd.to_datetime(result_df[field], errors='coerce').dt.strftime(date_format)
                
                elif operation == "replace":
                    old_value = transform.get("old_value")
                    new_value = transform.get("new_value")
                    result_df[field] = result_df[field].replace(old_value, new_value)
                
                elif operation == "strip":
                    result_df[field] = result_df[field].astype(str).str.strip()
                
                elif operation == "upper":
                    result_df[field] = result_df[field].astype(str).str.upper()
                
                elif operation == "lower":
                    result_df[field] = result_df[field].astype(str).str.lower()
                
                elif operation == "expr":
                    # 自定义表达式
                    expression = transform.get("expression")
                    if expression:
                        result_df[field] = result_df.apply(
                            lambda row: eval(expression, {"row": row, "pd": pd, "np": np}),
                            axis=1
                        )
                
                print(f"应用字段转换: {transform.get('description', f'{field} {operation}')}")
                
            except Exception as e:
                print(f"字段转换失败: {field} {operation}, 错误: {str(e)}")
        
        return result_df
    
    def _apply_aggregations(self, df: pd.DataFrame, aggregations: List[Dict]) -> pd.DataFrame:
        """
        应用聚合规则
        
        示例:
        [
            {
                "group_by": ["order_id", "date"],
                "agg_fields": {
                    "amount": "sum",
                    "quantity": "sum",
                    "status": "first"
                },
                "description": "按订单号和日期聚合"
            }
        ]
        """
        result_df = df.copy()
        
        for agg_config in aggregations:
            group_by = agg_config.get("group_by")
            agg_fields = agg_config.get("agg_fields", {})
            
            if not group_by or not agg_fields:
                continue
            
            # 确保分组字段存在
            if isinstance(group_by, str):
                group_by = [group_by]
            
            missing_fields = [f for f in group_by if f not in result_df.columns]
            if missing_fields:
                print(f"分组字段 {missing_fields} 不存在，跳过聚合")
                continue
            
            try:
                # 构建聚合字典
                agg_dict = {}
                for field, func in agg_fields.items():
                    if field in result_df.columns:
                        agg_dict[field] = func
                
                # 保留其他字段（使用 first）
                other_fields = [col for col in result_df.columns if col not in group_by and col not in agg_dict]
                for field in other_fields:
                    agg_dict[field] = 'first'
                
                result_df = result_df.groupby(group_by, as_index=False).agg(agg_dict)
                print(f"应用聚合: {agg_config.get('description', str(group_by))}, 结果 {len(result_df)} 条记录")
                
            except Exception as e:
                print(f"聚合失败: {str(e)}")
        
        return result_df
    
    def _apply_global_transforms(self, df: pd.DataFrame, transforms: List[Dict]) -> pd.DataFrame:
        """
        应用全局转换
        
        示例:
        [
            {
                "operation": "drop_duplicates",
                "subset": ["order_id"],
                "keep": "first"
            },
            {
                "operation": "sort",
                "by": ["date", "amount"],
                "ascending": [True, False]
            },
            {
                "operation": "drop_na",
                "subset": ["order_id", "amount"]
            }
        ]
        """
        result_df = df.copy()
        
        for transform in transforms:
            operation = transform.get("operation")
            
            try:
                if operation == "drop_duplicates":
                    subset = transform.get("subset")
                    keep = transform.get("keep", "first")
                    result_df = result_df.drop_duplicates(subset=subset, keep=keep)
                    print(f"删除重复记录，剩余 {len(result_df)} 条")
                
                elif operation == "sort":
                    by = transform.get("by")
                    ascending = transform.get("ascending", True)
                    if by:
                        result_df = result_df.sort_values(by=by, ascending=ascending)
                        print(f"排序: {by}")
                
                elif operation == "drop_na":
                    subset = transform.get("subset")
                    result_df = result_df.dropna(subset=subset)
                    print(f"删除空值，剩余 {len(result_df)} 条")
                
                elif operation == "fill_na":
                    value = transform.get("value", 0)
                    subset = transform.get("subset")
                    if subset:
                        result_df[subset] = result_df[subset].fillna(value)
                    else:
                        result_df = result_df.fillna(value)
                    print(f"填充空值: {value}")
                
                elif operation == "reset_index":
                    result_df = result_df.reset_index(drop=True)
                
            except Exception as e:
                print(f"全局转换失败: {operation}, 错误: {str(e)}")
        
        return result_df
    
    def _convert_types(self, df: pd.DataFrame) -> pd.DataFrame:
        """转换数据类型"""
        result_df = df.copy()
        
        # 将 amount 转换为 float
        if "amount" in result_df.columns:
            result_df["amount"] = pd.to_numeric(result_df["amount"], errors='coerce')
        
        # 将 order_id 转换为 str
        if "order_id" in result_df.columns:
            result_df["order_id"] = result_df["order_id"].astype(str)
        
        return result_df
    
    def _check_file_pattern_match(self, file_paths: List[str], pattern: str) -> bool:
        """检查文件路径是否匹配模式"""
        for file_path in file_paths:
            file_name = Path(file_path).name
            regex_pattern = pattern.replace("*", ".*")
            if re.search(regex_pattern, file_name):
                return True
        return False
