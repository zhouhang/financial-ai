"""
文件匹配器 - 根据 schema 中的 file_pattern 匹配文件
"""
import re
import logging
from typing import Any, Dict, List
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


class FileMatcher:
    """文件匹配器"""
    
    def __init__(self, schema: Dict):
        self.schema = schema
        self.data_sources = schema.get("data_sources", {})
        self.last_match_report: Dict[str, Any] = {
            "matched": {"business": [], "finance": []},
            "unmatched_files": [],
            "ambiguous_files": [],
            "expected_field_roles": {
                "business": self.data_sources.get("business", {}).get("field_roles", {}),
                "finance": self.data_sources.get("finance", {}).get("field_roles", {}),
            },
        }
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
        unmatched_files: List[Dict[str, Any]] = []
        ambiguous_files: List[Dict[str, Any]] = []

        for file_path in file_paths:
            file_name = Path(file_path).name
            logger.info(f"文件匹配器 - 处理文件: {file_path}, 文件名: {file_name}")

            headers = self._read_headers(file_path)
            if headers is None:
                unmatched_files.append({
                    "file_name": file_name,
                    "reason": "无法读取文件表头",
                    "file_path": file_path,
                })
                logger.warning(f"文件匹配器 - 无法读取文件表头: {file_name}")
                continue

            logger.info(f"文件匹配器 - 开始匹配文件 {file_name}，可用数据源: {list(self.data_sources.keys())}")

            strong_matches: List[Dict[str, Any]] = []
            fallback_matches: List[Dict[str, Any]] = []
            source_diagnostics: Dict[str, Any] = {}

            for source_name, source_config in self.data_sources.items():
                patterns = source_config.get("file_pattern", [])
                field_roles = source_config.get("field_roles", {})

                pattern_match = self._match_pattern(file_name, patterns)
                role_match, role_diag = self._match_field_roles(headers, field_roles)

                source_diagnostics[source_name] = {
                    "pattern_match": pattern_match,
                    "field_roles_match": role_match,
                    "missing_roles": role_diag.get("missing_roles", {}),
                }

                if pattern_match and role_match:
                    strong_matches.append({"source": source_name, "reason": "pattern+header"})
                elif role_match:
                    # 文件名无法匹配时，允许用表头兜底匹配
                    fallback_matches.append({"source": source_name, "reason": "header_only"})

            matched_source = None
            if len(strong_matches) == 1:
                matched_source = strong_matches[0]["source"]
            elif len(strong_matches) > 1:
                ambiguous_files.append({
                    "file_name": file_name,
                    "candidates": [m["source"] for m in strong_matches],
                    "reason": "多个数据源同时满足文件名和表头匹配",
                    "diagnostics": source_diagnostics,
                })
                logger.warning(f"文件匹配器 - 文件 {file_name} 匹配歧义（strong）: {strong_matches}")
                continue
            else:
                if len(fallback_matches) == 1:
                    matched_source = fallback_matches[0]["source"]
                    logger.info(f"文件匹配器 - 文件 {file_name} 文件名未命中，使用表头兜底匹配到 {matched_source}")
                elif len(fallback_matches) > 1:
                    ambiguous_files.append({
                        "file_name": file_name,
                        "candidates": [m["source"] for m in fallback_matches],
                        "reason": "文件名未命中且表头可匹配多个数据源",
                        "diagnostics": source_diagnostics,
                    })
                    logger.warning(f"文件匹配器 - 文件 {file_name} 匹配歧义（fallback）: {fallback_matches}")
                    continue

            if matched_source:
                if matched_source in matched:
                    matched[matched_source].append(file_path)
                logger.info(f"文件匹配器 - ✅ 文件 {file_name} 匹配到 {matched_source}")
            else:
                unmatched_files.append({
                    "file_name": file_name,
                    "reason": "文件名和表头均无法匹配到任何数据源",
                    "diagnostics": source_diagnostics,
                    "file_path": file_path,
                })
                logger.warning(
                    f"文件匹配器 - 警告：文件 {file_name} 未匹配到任何数据源，"
                    f"可用模式: business={self.data_sources.get('business', {}).get('file_pattern', [])}, "
                    f"finance={self.data_sources.get('finance', {}).get('file_pattern', [])}"
                )

        self.last_match_report = {
            "matched": matched,
            "unmatched_files": unmatched_files,
            "ambiguous_files": ambiguous_files,
            "expected_field_roles": {
                "business": self.data_sources.get("business", {}).get("field_roles", {}),
                "finance": self.data_sources.get("finance", {}).get("field_roles", {}),
            },
        }

        return matched

    def get_last_match_report(self) -> Dict[str, Any]:
        """获取最近一次匹配的详细报告。"""
        return self.last_match_report
    
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

    def _match_field_roles(self, headers: List[str], field_roles: Dict[str, Any]) -> tuple[bool, Dict[str, Any]]:
        """检查 field_roles 是否与文件表头完全匹配。

        规则：
        - role 值为字符串：该列名必须存在
        - role 值为数组：数组中至少一个列名存在
        """
        header_set = set(headers)
        missing_roles: Dict[str, Any] = {}

        for role, expected in field_roles.items():
            if isinstance(expected, list):
                if not any(col in header_set for col in expected):
                    missing_roles[role] = expected
            else:
                if expected not in header_set:
                    missing_roles[role] = expected

        return len(missing_roles) == 0, {"missing_roles": missing_roles}

    def _read_headers(self, file_path: str) -> List[str] | None:
        """读取文件表头，CSV 兼容多编码。"""
        lower_path = file_path.lower()

        try:
            if lower_path.endswith(".csv"):
                encodings = ["utf-8", "utf-8-sig", "gbk", "gb2312", "gb18030", "latin1"]
                for enc in encodings:
                    try:
                        df = pd.read_csv(file_path, encoding=enc, nrows=0, index_col=False)
                        return [str(c) for c in df.columns]
                    except Exception:
                        continue

                # 可选的编码探测兜底
                try:
                    import chardet  # type: ignore

                    with open(file_path, "rb") as f:
                        raw = f.read(65536)
                    detected = chardet.detect(raw).get("encoding")
                    if detected:
                        df = pd.read_csv(file_path, encoding=detected, nrows=0, index_col=False)
                        return [str(c) for c in df.columns]
                except Exception:
                    pass

                return None

            # Excel 类型只读取表头
            if lower_path.endswith((".xlsx", ".xls", ".xlsm", ".xlsb")):
                df = pd.read_excel(file_path, nrows=0, index_col=False)
                return [str(c) for c in df.columns]

            return None
        except Exception as e:
            logger.warning(f"读取文件表头失败: {file_path}, 错误: {e}")
            return None
