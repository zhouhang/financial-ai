"""
Schema 加载器 - 加载和验证数据整理 Schema
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any
import re

logger = logging.getLogger(__name__)


class SchemaLoader:
    """Schema 加载器"""
    
    @staticmethod
    def load_from_file(schema_path: str) -> Dict[str, Any]:
        """从文件加载 schema"""
        schema_file = Path(schema_path)
        
        if not schema_file.exists():
            raise FileNotFoundError(f"Schema 文件不存在: {schema_path}")
        
        # 使用支持注释的加载函数
        return load_json_with_comments(schema_file)
    
    @staticmethod
    def validate_schema(schema: Dict) -> bool:
        """验证 schema 格式（基础验证）"""
        required_fields = ["version", "data_sources"]
        
        for field in required_fields:
            if field not in schema:
                logger.error(f"Schema 缺少必需字段: {field}")
                return False
        
        return True


def load_json_with_comments(file_path: Path) -> Dict:
    """加载 JSON 文件（支持 JSON5 格式的注释）"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 移除多行注释 (/* ... */)
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    
    # 移除单行注释 (//) - 但保留字符串中的 //
    lines = []
    in_string = False
    escape_next = False
    
    for line in content.split('\n'):
        new_line = []
        i = 0
        while i < len(line):
            char = line[i]
            
            if escape_next:
                new_line.append(char)
                escape_next = False
                i += 1
                continue
            
            if char == '\\':
                escape_next = True
                new_line.append(char)
                i += 1
                continue
            
            if char == '"':
                in_string = not in_string
                new_line.append(char)
                i += 1
                continue
            
            # 如果不在字符串中，遇到 // 则移除后面的内容
            if not in_string and char == '/' and i + 1 < len(line) and line[i + 1] == '/':
                break
            
            new_line.append(char)
            i += 1
        
        lines.append(''.join(new_line))
    
    content = '\n'.join(lines)
    
    return json.loads(content)
