"""
文件匹配器 - 根据 schema 规则匹配上传的文件到数据源
"""
import re
import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


class FileMatcher:
    """文件匹配器"""
    
    def __init__(self, schema: Dict):
        self.schema = schema
        self.data_sources = schema.get("data_sources", {})
    
    def match_files(self, file_paths: List[str]) -> Dict[str, str]:
        """
        将文件路径匹配到数据源
        
        Args:
            file_paths: 上传的文件路径列表
        
        Returns:
            {source_id: file_path} 映射
        """
        matched = {}
        
        for source_id, source_config in self.data_sources.items():
            file_patterns = source_config.get("file_pattern", [])
            if isinstance(file_patterns, str):
                file_patterns = [file_patterns]
            
            # 尝试匹配文件
            for file_path in file_paths:
                file_name = Path(file_path).name
                
                for pattern in file_patterns:
                    if self._match_pattern(file_name, pattern):
                        matched[source_id] = file_path
                        logger.info(f"文件匹配: {source_id} <- {file_name}")
                        break
                
                if source_id in matched:
                    break
        
        return matched
    
    def _match_pattern(self, filename: str, pattern: str) -> bool:
        """
        匹配文件名模式
        支持通配符 * 和正则表达式
        """
        # 将通配符转换为正则表达式
        regex_pattern = pattern.replace("*", ".*").replace("?", ".")
        
        # 如果 pattern 不是完整的正则表达式，添加开始和结束标记
        if not regex_pattern.startswith("^"):
            regex_pattern = "^" + regex_pattern
        if not regex_pattern.endswith("$"):
            regex_pattern = regex_pattern + "$"
        
        try:
            return bool(re.match(regex_pattern, filename, re.IGNORECASE))
        except re.error as e:
            logger.warning(f"正则表达式错误: {pattern}, 错误: {str(e)}")
            return False
