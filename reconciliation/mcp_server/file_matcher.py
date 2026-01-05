"""
文件匹配器 - 根据 schema 中的 file_pattern 匹配文件
"""
import re
from typing import Dict, List, Tuple
from pathlib import Path


class FileMatcher:
    """文件匹配器"""
    
    def __init__(self, schema: Dict):
        self.schema = schema
        self.data_sources = schema.get("data_sources", {})
    
    def match_files(self, file_paths: List[str]) -> Dict[str, List[str]]:
        """
        将文件匹配到对应的数据源
        
        Returns:
            {
                "business": [file_path1, file_path2, ...],
                "finance": [file_path3, ...]
            }
        """
        matched = {
            "business": [],
            "finance": []
        }
        
        for file_path in file_paths:
            file_name = Path(file_path).name
            
            # 尝试匹配到各个数据源
            for source_name, source_config in self.data_sources.items():
                if self._match_pattern(file_name, source_config.get("file_pattern")):
                    if source_name in matched:
                        matched[source_name].append(file_path)
                    break
        
        return matched
    
    def _match_pattern(self, file_name: str, pattern) -> bool:
        """
        匹配文件名与模式
        
        Args:
            file_name: 文件名
            pattern: 字符串模式或模式列表
        
        Returns:
            是否匹配
        """
        if isinstance(pattern, str):
            patterns = [pattern]
        elif isinstance(pattern, list):
            patterns = pattern
        else:
            return False
        
        for p in patterns:
            # 将通配符模式转换为正则表达式
            regex_pattern = self._wildcard_to_regex(p)
            if re.match(regex_pattern, file_name):
                return True
        
        return False
    
    def _wildcard_to_regex(self, pattern: str) -> str:
        """
        将通配符模式转换为正则表达式
        
        Examples:
            "*.csv" -> ".*\\.csv$"
            "ads_*_details_*.csv" -> "ads_.*_details_.*\\.csv$"
            "[0-9].csv" -> "[0-9]\\.csv$"
        """
        # 转义特殊字符，但保留 * 和 []
        pattern = pattern.replace(".", "\\.")
        pattern = pattern.replace("*", ".*")
        
        # 确保完整匹配
        if not pattern.startswith("^"):
            pattern = "^" + pattern
        if not pattern.endswith("$"):
            pattern = pattern + "$"
        
        return pattern

