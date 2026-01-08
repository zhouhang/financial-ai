"""
Schema 加载和验证
"""
import json
import re
from typing import Dict, Any, Optional
from pathlib import Path


class SchemaLoader:
    """Schema 加载器"""
    
    @staticmethod
    def load_from_file(schema_path: str) -> Dict[str, Any]:
        """从文件加载 schema（支持 JSON5 格式的注释）"""
        with open(schema_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 移除单行注释 (// ...)
        content = re.sub(r'//.*?$', '', content, flags=re.MULTILINE)
        
        # 移除多行注释 (/* ... */)
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        
        return json.loads(content)
    
    @staticmethod
    def load_from_dict(schema_dict: Dict[str, Any]) -> Dict[str, Any]:
        """从字典加载 schema"""
        return schema_dict
    
    @staticmethod
    def validate_schema(schema: Dict[str, Any]) -> bool:
        """验证 schema 格式"""
        required_fields = ["version", "data_sources", "key_field_role"]
        
        for field in required_fields:
            if field not in schema:
                raise ValueError(f"Schema 缺少必填字段: {field}")
        
        # 验证数据源
        data_sources = schema.get("data_sources", {})
        if "business" not in data_sources and "finance" not in data_sources:
            raise ValueError("Schema 至少需要定义 business 或 finance 数据源")
        
        # 验证每个数据源的必填字段
        for source_name, source_config in data_sources.items():
            if "file_pattern" not in source_config:
                raise ValueError(f"数据源 {source_name} 缺少 file_pattern")
            if "field_roles" not in source_config:
                raise ValueError(f"数据源 {source_name} 缺少 field_roles")
        
        return True
    
    @staticmethod
    def get_data_cleaning_rules(schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """获取数据清洗规则"""
        return schema.get("data_cleaning_rules")
    
    @staticmethod
    def get_tolerance(schema: Dict[str, Any]) -> Dict[str, Any]:
        """获取容差配置"""
        return schema.get("tolerance", {})
    
    @staticmethod
    def get_custom_validations(schema: Dict[str, Any]) -> list:
        """获取自定义验证规则"""
        return schema.get("custom_validations", [])

