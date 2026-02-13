"""
文件匹配器 - 根据 schema 中的 file_pattern 匹配文件
"""
import re
import logging
from typing import Dict, List, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class FileMatcher:
    """文件匹配器"""
    
    def __init__(self, schema: Dict):
        self.schema = schema
        self.data_sources = schema.get("data_sources", {})
        logger.info(f"FileMatcher 初始化 - data_sources keys: {list(self.data_sources.keys())}")
        logger.info(f"FileMatcher 初始化 - 完整 schema keys: {list(schema.keys())}")
        for source_name, source_config in self.data_sources.items():
            patterns = source_config.get("file_pattern", [])
            logger.info(f"FileMatcher 初始化 - {source_name} file_pattern: {patterns} (类型: {type(patterns)})")
            logger.info(f"FileMatcher 初始化 - {source_name} 完整配置: {source_config}")
    
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
            logger.info(f"文件匹配器 - 处理文件: {file_path}, 文件名: {file_name}")
            
            # 尝试匹配到各个数据源
            matched_source = None
            logger.info(f"文件匹配器 - 开始匹配文件 {file_name}，可用数据源: {list(self.data_sources.keys())}")
            for source_name, source_config in self.data_sources.items():
                patterns = source_config.get("file_pattern", [])
                logger.info(f"文件匹配器 - 数据源 {source_name} 的模式: {patterns} (类型: {type(patterns)})")
                
                # 详细调试：对每个模式进行匹配测试
                if isinstance(patterns, list):
                    pattern_list = patterns
                elif isinstance(patterns, str):
                    pattern_list = [patterns]
                else:
                    pattern_list = []
                    logger.warning(f"文件匹配器 - 数据源 {source_name} 的模式类型异常: {type(patterns)}")
                
                for p in pattern_list:
                    regex_pattern = self._wildcard_to_regex(p)
                    match_result = re.match(regex_pattern, file_name)
                    logger.info(f"文件匹配器 - 测试模式 '{p}' -> 正则 '{regex_pattern}' vs 文件名 '{file_name}': {match_result is not None}")
                
                if self._match_pattern(file_name, patterns):
                    matched_source = source_name
                    if source_name in matched:
                        matched[source_name].append(file_path)
                    logger.info(f"文件匹配器 - ✅ 文件 {file_name} 匹配到 {source_name}")
                    break
                else:
                    logger.warning(f"文件匹配器 - ❌ 文件 {file_name} 不匹配 {source_name} 的模式 {patterns}")
            
            if not matched_source:
                logger.warning(f"文件匹配器 - 警告：文件 {file_name} 未匹配到任何数据源，可用模式: business={self.data_sources.get('business', {}).get('file_pattern', [])}, finance={self.data_sources.get('finance', {}).get('file_pattern', [])}")
        
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

