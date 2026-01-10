"""
数据转换器 - 执行数据计算和转换
"""
import pandas as pd
import logging
from typing import Dict, List, Any
import re

logger = logging.getLogger(__name__)


class DataTransformer:
    """数据转换器"""
    
    def __init__(self, schema: Dict):
        self.schema = schema
        self.transformations = schema.get("transformations", [])
        self.computed_data = {}  # 存储计算结果
    
    def transform(self, extracted_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """
        执行所有转换步骤
        
        Args:
            extracted_data: 提取的数据 {source_id: DataFrame}
        
        Returns:
            计算结果字典
        """
        results = {}
        
        for transformation in self.transformations:
            step_id = transformation.get("step_id")
            operation = transformation.get("operation")
            
            try:
                if operation == "sum":
                    result = self._calculate_sum(transformation, extracted_data)
                elif operation == "formula":
                    result = self._calculate_formula(transformation, results)
                elif operation == "aggregate":
                    result = self._calculate_aggregate(transformation, extracted_data)
                else:
                    logger.warning(f"未知的操作类型: {operation}")
                    continue
                
                output_field = transformation.get("output_field")
                if output_field:
                    results[output_field] = result
                    logger.info(f"转换步骤 {step_id}: {output_field} = {result}")
            
            except Exception as e:
                logger.error(f"转换步骤 {step_id} 失败: {str(e)}")
                results[transformation.get("output_field")] = None
        
        return results
    
    def _calculate_sum(self, config: Dict, extracted_data: Dict[str, pd.DataFrame]) -> float:
        """计算求和"""
        input_sources = config.get("input_sources", [])
        input_fields = config.get("input_fields", [])
        filter_condition = config.get("filter_condition")
        
        total = 0.0
        
        for source_id in input_sources:
            if source_id not in extracted_data:
                continue
            
            df = extracted_data[source_id].copy()
            
            # 应用过滤条件
            if filter_condition:
                try:
                    df = df.query(filter_condition)
                except Exception as e:
                    logger.warning(f"过滤条件执行失败: {filter_condition}, 错误: {str(e)}")
            
            # 对指定字段求和
            for field in input_fields:
                if field in df.columns:
                    total += df[field].sum()
        
        # 应用舍入
        rounding = config.get("rounding")
        if rounding is not None:
            total = round(total, rounding)
        
        return total
    
    def _calculate_formula(self, config: Dict, computed_results: Dict[str, Any]) -> float:
        """计算公式"""
        formula = config.get("formula", "")
        
        # 替换公式中的变量 {{variable}} -> value
        def replace_variable(match):
            var_name = match.group(1)
            value = computed_results.get(var_name, 0)
            return str(value)
        
        formula_eval = re.sub(r'\{\{(\w+)\}\}', replace_variable, formula)
        
        try:
            result = eval(formula_eval)
        except Exception as e:
            logger.error(f"公式计算失败: {formula} -> {formula_eval}, 错误: {str(e)}")
            result = 0
        
        # 应用舍入
        rounding = config.get("rounding")
        if rounding is not None:
            result = round(result, rounding)
        
        return result
    
    def _calculate_aggregate(self, config: Dict, extracted_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """计算聚合"""
        input_source = config.get("input_source")
        group_by = config.get("group_by")
        aggregations = config.get("aggregations", [])
        
        if input_source not in extracted_data:
            return pd.DataFrame()
        
        df = extracted_data[input_source].copy()
        
        if not group_by or group_by not in df.columns:
            logger.warning(f"分组字段 {group_by} 不存在")
            return df
        
        # 构建聚合字典
        agg_dict = {}
        for agg_config in aggregations:
            field = agg_config.get("field")
            method = agg_config.get("method", "sum")
            
            if field in df.columns:
                agg_dict[field] = method
        
        if not agg_dict:
            return df
        
        # 执行聚合
        try:
            result_df = df.groupby(group_by, as_index=False).agg(agg_dict)
            logger.info(f"聚合计算: 按 {group_by} 分组, 结果 {len(result_df)} 行")
            return result_df
        except Exception as e:
            logger.error(f"聚合计算失败: {str(e)}")
            return df
