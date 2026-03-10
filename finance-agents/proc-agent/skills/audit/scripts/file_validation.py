#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件上传合法性校验模块

根据 manual_voucher_sync_rule.json 中定义的 file_validation_rules 规则，
校验用户上传的文件是否符合系统要求的表结构。

校验策略：全量列名精确匹配
- 文件列名集合必须与规则定义的列名集合完全一致
- 如果匹配成功，返回对应的表名
- 如果全部不匹配，则文件不合法

支持的文件格式：Excel (.xlsx, .xls)、CSV (.csv)
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List

import pandas as pd

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 规则文件路径
RULE_FILE_PATH = Path(__file__).parent.parent / "references" / "manual_voucher_sync_rule.json"


@dataclass
class ValidationResult:
    """单个文件的校验结果"""
    file_path: str
    is_valid: bool
    matched_table_id: Optional[str] = None
    matched_table_name: Optional[str] = None
    file_columns: list = field(default_factory=list)
    expected_columns: list = field(default_factory=list)
    missing_columns: list = field(default_factory=list)
    extra_columns: list = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "file_path": self.file_path,
            "is_valid": self.is_valid,
            "matched_table_id": self.matched_table_id,
            "matched_table_name": self.matched_table_name,
            "file_columns": self.file_columns,
            "expected_columns": self.expected_columns,
            "missing_columns": self.missing_columns,
            "extra_columns": self.extra_columns,
            "message": self.message
        }


@dataclass
class BatchValidationResult:
    """批量文件校验结果"""
    total_files: int
    valid_files: int
    invalid_files: int
    all_valid: bool
    results: List[ValidationResult] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "total_files": self.total_files,
            "valid_files": self.valid_files,
            "invalid_files": self.invalid_files,
            "all_valid": self.all_valid,
            "results": [r.to_dict() for r in self.results],
            "summary": self.summary
        }


class FileValidator:
    """文件校验器类"""

    def __init__(self, rule_file_path: Optional[str] = None):
        """
        初始化校验器

        Args:
            rule_file_path: 规则文件路径，默认使用内置路径
        """
        self.rule_file_path = Path(rule_file_path) if rule_file_path else RULE_FILE_PATH
        self.validation_rules = self._load_rules()

    def _load_rules(self) -> dict:
        """加载校验规则"""
        if not self.rule_file_path.exists():
            raise FileNotFoundError(f"规则文件不存在: {self.rule_file_path}")

        with open(self.rule_file_path, 'r', encoding='utf-8') as f:
            rules = json.load(f)

        if "file_validation_rules" not in rules:
            raise ValueError("规则文件中缺少 file_validation_rules 配置")

        return rules["file_validation_rules"]

    def _normalize_column_name(self, col_name: str, config: dict) -> str:
        """
        标准化列名

        Args:
            col_name: 原始列名
            config: 校验配置

        Returns:
            标准化后的列名
        """
        normalized = str(col_name).strip()

        if config.get("ignore_whitespace", True):
            normalized = normalized.replace(" ", "").replace("\t", "")

        if not config.get("case_sensitive", False):
            normalized = normalized.lower()

        return normalized

    def _get_normalized_columns_set(self, columns: list, config: dict) -> set:
        """
        获取标准化后的列名集合

        Args:
            columns: 列名列表
            config: 校验配置

        Returns:
            标准化后的列名集合
        """
        return {self._normalize_column_name(col, config) for col in columns}

    def _build_alias_mapping(self, table_schema: dict, config: dict) -> dict:
        """
        构建别名到标准列名的映射

        Args:
            table_schema: 表结构定义
            config: 校验配置

        Returns:
            别名到标准列名的映射
        """
        alias_map = {}
        for original_col, aliases in table_schema.get("column_aliases", {}).items():
            normalized_original = self._normalize_column_name(original_col, config)
            for alias in aliases:
                normalized_alias = self._normalize_column_name(alias, config)
                alias_map[normalized_alias] = normalized_original
        return alias_map

    def _normalize_file_columns(self, file_columns: list, table_schema: dict, config: dict) -> set:
        """
        将文件列名标准化，并将别名转换为标准列名

        Args:
            file_columns: 文件中的列名
            table_schema: 表结构定义
            config: 校验配置

        Returns:
            标准化后的列名集合
        """
        alias_map = self._build_alias_mapping(table_schema, config)
        normalized_set = set()

        for col in file_columns:
            normalized_col = self._normalize_column_name(col, config)
            # 如果是别名，转换为标准列名
            if normalized_col in alias_map:
                normalized_set.add(alias_map[normalized_col])
            else:
                normalized_set.add(normalized_col)

        return normalized_set

    def _check_exact_match(
        self,
        file_columns: list,
        table_schema: dict,
        config: dict
    ) -> dict:
        """
        检查文件列名是否与表结构精确匹配

        Args:
            file_columns: 文件列名列表
            table_schema: 表结构定义
            config: 校验配置

        Returns:
            匹配结果字典
        """
        # 获取规则定义的标准列名集合
        expected_columns = table_schema.get("all_columns", [])
        expected_set = self._get_normalized_columns_set(expected_columns, config)

        # 将文件列名标准化（包含别名转换）
        file_set = self._normalize_file_columns(file_columns, table_schema, config)

        # 计算差异
        missing_columns = expected_set - file_set  # 缺少的列
        extra_columns = file_set - expected_set    # 多余的列

        # 精确匹配：无缺少列且无多余列
        is_match = len(missing_columns) == 0 and len(extra_columns) == 0

        return {
            "table_id": table_schema["table_id"],
            "table_name": table_schema["table_name"],
            "is_match": is_match,
            "expected_columns": expected_columns,
            "missing_columns": list(missing_columns),
            "extra_columns": list(extra_columns)
        }

    def read_file_columns(self, file_path: str) -> list:
        """
        读取文件列名

        Args:
            file_path: 文件路径

        Returns:
            列名列表
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        ext = file_path.suffix.lower()

        if ext in ['.xlsx', '.xls']:
            df = pd.read_excel(file_path, nrows=0)
        elif ext == '.csv':
            # 尝试多种编码
            for encoding in ['utf-8', 'gbk', 'gb2312', 'utf-8-sig']:
                try:
                    df = pd.read_csv(file_path, nrows=0, encoding=encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise ValueError(f"无法识别文件编码: {file_path}")
        else:
            raise ValueError(f"不支持的文件格式: {ext}，仅支持 .xlsx, .xls, .csv")

        return list(df.columns)

    def validate(self, file_path: str) -> ValidationResult:
        """
        校验单个文件是否合法

        Args:
            file_path: 待校验的文件路径

        Returns:
            ValidationResult 校验结果
        """
        logger.info(f"开始校验文件: {file_path}")

        try:
            # 读取文件列名
            file_columns = self.read_file_columns(file_path)
            logger.info(f"文件列名 ({len(file_columns)}列): {file_columns}")

            if not file_columns:
                return ValidationResult(
                    file_path=file_path,
                    is_valid=False,
                    file_columns=[],
                    message="文件为空或无法读取列名"
                )

            config = self.validation_rules.get("validation_config", {})
            table_schemas = self.validation_rules.get("table_schemas", [])

            # 依次检查每个表结构
            for table_schema in table_schemas:
                match_result = self._check_exact_match(
                    file_columns, table_schema, config
                )

                if match_result["is_match"]:
                    logger.info(f"文件匹配成功: {table_schema['table_name']}")
                    return ValidationResult(
                        file_path=file_path,
                        is_valid=True,
                        matched_table_id=match_result["table_id"],
                        matched_table_name=match_result["table_name"],
                        file_columns=file_columns,
                        expected_columns=match_result["expected_columns"],
                        message=f"文件校验通过，匹配表: {match_result['table_name']}"
                    )
                else:
                    logger.debug(
                        f"表 {table_schema['table_name']} 不匹配 - "
                        f"缺少: {match_result['missing_columns']}, "
                        f"多余: {match_result['extra_columns']}"
                    )

            # 所有表都不匹配
            # 找出最接近匹配的表（便于诊断）
            best_match = None
            min_diff = float('inf')
            for table_schema in table_schemas:
                match_result = self._check_exact_match(
                    file_columns, table_schema, config
                )
                diff_count = len(match_result["missing_columns"]) + len(match_result["extra_columns"])
                if diff_count < min_diff:
                    min_diff = diff_count
                    best_match = match_result

            return ValidationResult(
                file_path=file_path,
                is_valid=False,
                file_columns=file_columns,
                expected_columns=best_match["expected_columns"] if best_match else [],
                missing_columns=best_match["missing_columns"] if best_match else [],
                extra_columns=best_match["extra_columns"] if best_match else [],
                message=(
                    f"文件校验失败，未匹配任何表结构。"
                    f"最接近的表: {best_match['table_name'] if best_match else '无'}，"
                    f"缺少列: {best_match['missing_columns'] if best_match else []}, "
                    f"多余列: {best_match['extra_columns'] if best_match else []}"
                )
            )

        except Exception as e:
            logger.error(f"校验文件时发生错误: {e}")
            return ValidationResult(
                file_path=file_path,
                is_valid=False,
                message=f"校验失败: {str(e)}"
            )

    def validate_batch(self, file_paths: List[str]) -> BatchValidationResult:
        """
        批量校验多个文件

        Args:
            file_paths: 待校验的文件路径列表

        Returns:
            BatchValidationResult 批量校验结果
        """
        logger.info(f"开始批量校验 {len(file_paths)} 个文件")

        results = []
        for file_path in file_paths:
            result = self.validate(file_path)
            results.append(result)

        valid_count = sum(1 for r in results if r.is_valid)
        invalid_count = len(results) - valid_count

        # 生成摘要
        valid_files = [r for r in results if r.is_valid]
        invalid_files = [r for r in results if not r.is_valid]

        summary_parts = []
        if valid_files:
            valid_info = ", ".join([
                f"{Path(r.file_path).name} -> {r.matched_table_name}"
                for r in valid_files
            ])
            summary_parts.append(f"合法文件: {valid_info}")

        if invalid_files:
            invalid_info = ", ".join([Path(r.file_path).name for r in invalid_files])
            summary_parts.append(f"不合法文件: {invalid_info}")

        return BatchValidationResult(
            total_files=len(file_paths),
            valid_files=valid_count,
            invalid_files=invalid_count,
            all_valid=(invalid_count == 0),
            results=results,
            summary="; ".join(summary_parts)
        )


def validate_file(file_path: str, rule_file_path: Optional[str] = None) -> dict:
    """
    校验单个文件的便捷函数

    Args:
        file_path: 待校验的文件路径
        rule_file_path: 规则文件路径（可选）

    Returns:
        校验结果字典
    """
    validator = FileValidator(rule_file_path)
    result = validator.validate(file_path)
    return result.to_dict()


def validate_files(file_paths: List[str], rule_file_path: Optional[str] = None) -> dict:
    """
    批量校验多个文件的便捷函数

    Args:
        file_paths: 待校验的文件路径列表
        rule_file_path: 规则文件路径（可选）

    Returns:
        批量校验结果字典
    """
    validator = FileValidator(rule_file_path)
    result = validator.validate_batch(file_paths)
    return result.to_dict()


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="文件上传合法性校验工具（全量列名精确匹配）")
    parser.add_argument("file_paths", nargs="+", help="待校验的文件路径（支持多个）")
    parser.add_argument(
        "--rule-file",
        help="规则文件路径（可选，默认使用内置规则）"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细输出"
    )

    args = parser.parse_args()

    # 执行校验
    if len(args.file_paths) == 1:
        result = validate_file(args.file_paths[0], args.rule_file)
        results = [result]
        all_valid = result["is_valid"]
    else:
        batch_result = validate_files(args.file_paths, args.rule_file)
        results = batch_result["results"]
        all_valid = batch_result["all_valid"]

    # 输出结果
    if args.verbose:
        if len(args.file_paths) == 1:
            print(json.dumps(results[0], ensure_ascii=False, indent=2))
        else:
            print(json.dumps(batch_result, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*70}")
        print(f"文件校验结果 (共 {len(results)} 个文件)")
        print(f"{'='*70}")

        for result in results:
            file_name = Path(result["file_path"]).name
            status = "✓ 合法" if result["is_valid"] else "✗ 不合法"
            print(f"\n文件: {file_name}")
            print(f"  状态: {status}")

            if result["is_valid"]:
                print(f"  匹配表: {result['matched_table_name']}")
            else:
                if result["missing_columns"]:
                    print(f"  缺少列: {result['missing_columns']}")
                if result["extra_columns"]:
                    print(f"  多余列: {result['extra_columns']}")
                print(f"  说明: {result['message']}")

        print(f"\n{'='*70}")
        print(f"总结: {len([r for r in results if r['is_valid']])} 个合法, "
              f"{len([r for r in results if not r['is_valid']])} 个不合法")
        print(f"{'='*70}\n")

    # 返回退出码
    return 0 if all_valid else 1


if __name__ == "__main__":
    exit(main())
