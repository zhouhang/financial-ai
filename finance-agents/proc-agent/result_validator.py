"""结果验证器模块

比较处理结果与参考结果，生成验证报告。
"""

import pandas as pd
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime


class ResultValidator:
    """结果验证器"""

    def __init__(self, base_dir: Optional[Path] = None):
        """初始化结果验证器

        参数:
            base_dir: proc-agent 根目录
        """
        if base_dir is None:
            from . import AUDIT_AGENT_DIR
            base_dir = AUDIT_AGENT_DIR

        self.base_dir = base_dir
        self.validation_dir = base_dir / "result" / "validation"
        self.validation_dir.mkdir(parents=True, exist_ok=True)

    def compare_results(
        self,
        generated_file: str,
        reference_file: str,
        ignore_columns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """比较结果文件

        参数:
            generated_file: 生成的结果文件路径
            reference_file: 参考结果文件路径
            ignore_columns: 忽略的列名列表

        返回:
            比较结果
        """
        try:
            # 加载文件
            gen_df = pd.read_excel(generated_file)
            ref_df = pd.read_excel(reference_file)

            # 忽略指定列
            if ignore_columns:
                gen_df = gen_df.drop(columns=[c for c in ignore_columns if c in gen_df.columns], errors='ignore')
                ref_df = ref_df.drop(columns=[c for c in ignore_columns if c in ref_df.columns], errors='ignore')

            # 检查列是否一致
            gen_cols = set(gen_df.columns)
            ref_cols = set(ref_df.columns)

            column_diff = {
                "only_in_generated": list(gen_cols - ref_cols),
                "only_in_reference": list(ref_cols - gen_cols)
            }

            # 比较共同列
            common_cols = gen_cols & ref_cols
            if not common_cols:
                return {
                    "identical": False,
                    "total_rows": len(gen_df),
                    "matching_rows": 0,
                    "differences": [],
                    "summary": "没有共同的列可以比较",
                    "column_difference": column_diff
                }

            # 逐行比较
            differences = []
            matching_rows = 0

            # 对齐索引
            min_len = min(len(gen_df), len(ref_df))
            gen_df = gen_df.head(min_len).reset_index(drop=True)
            ref_df = ref_df.head(min_len).reset_index(drop=True)

            for idx in range(min_len):
                row_diff = []
                for col in common_cols:
                    gen_val = gen_df.loc[idx, col]
                    ref_val = ref_df.loc[idx, col]

                    # 处理 NaN 值
                    if pd.isna(gen_val) and pd.isna(ref_val):
                        continue

                    if gen_val != ref_val:
                        row_diff.append({
                            "column": col,
                            "generated": gen_val,
                            "reference": ref_val
                        })

                if row_diff:
                    differences.append({
                        "row": idx,
                        "differences": row_diff
                    })
                else:
                    matching_rows += 1

            # 处理行数不一致
            if len(gen_df) != len(ref_df):
                differences.append({
                    "type": "row_count_mismatch",
                    "generated_count": len(gen_df),
                    "reference_count": len(ref_df)
                })

            identical = len(differences) == 0 and len(gen_df) == len(ref_df)

            return {
                "identical": identical,
                "total_rows": min_len,
                "matching_rows": matching_rows,
                "different_rows": len(differences),
                "differences": differences[:100],  # 限制差异数量
                "summary": self._generate_summary(identical, matching_rows, min_len, differences),
                "column_difference": column_diff
            }

        except Exception as e:
            return {
                "identical": False,
                "error": str(e),
                "summary": f"比较失败：{str(e)}"
            }

    def _generate_summary(
        self,
        identical: bool,
        matching_rows: int,
        total_rows: int,
        differences: List[Any]
    ) -> str:
        """生成摘要

        参数:
            identical: 是否完全一致
            matching_rows: 匹配行数
            total_rows: 总行数
            differences: 差异列表

        返回:
            摘要文本
        """
        if identical:
            return f"✅ 结果完全一致（共 {total_rows} 行）"

        match_rate = (matching_rows / total_rows * 100) if total_rows > 0 else 0
        diff_count = len([d for d in differences if d.get("type") != "row_count_mismatch"])
        row_count_diff = next((d for d in differences if d.get("type") == "row_count_mismatch"), None)

        summary_parts = [
            f"❌ 结果存在差异",
            f"匹配率：{match_rate:.1f}% ({matching_rows}/{total_rows} 行)"
        ]

        if row_count_diff:
            summary_parts.append(
                f"行数不一致：生成 {row_count_diff['generated_count']} 行，参考 {row_count_diff['reference_count']} 行"
            )

        if diff_count > 0:
            summary_parts.append(f"数据差异：{diff_count} 行")

        return " | ".join(summary_parts)

    def generate_validation_report(
        self,
        comparison: Dict[str, Any],
        rule_name: str,
        output_path: Optional[Path] = None
    ) -> str:
        """生成验证报告

        参数:
            comparison: 比较结果
            rule_name: 规则名称
            output_path: 输出路径（None 则生成 Markdown 字符串）

        返回:
            验证报告（Markdown 格式）
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        report = f"""# 规则验证报告

**规则名称**: {rule_name}  
**验证时间**: {timestamp}

---

## 验证概况

{comparison.get('summary', '验证失败')}

### 统计信息

| 项目 | 数值 |
|------|------|
| 总行数 | {comparison.get('total_rows', 'N/A')} |
| 匹配行数 | {comparison.get('matching_rows', 'N/A')} |
| 差异行数 | {comparison.get('different_rows', 'N/A')} |
| 匹配率 | {comparison.get('matching_rows', 0) / comparison.get('total_rows', 1) * 100:.1f}% |

"""

        # 列差异
        col_diff = comparison.get('column_difference', {})
        if col_diff.get('only_in_generated') or col_diff.get('only_in_reference'):
            report += """## 列差异

"""
            if col_diff.get('only_in_generated'):
                report += f"**仅存在于生成结果**: {', '.join(col_diff['only_in_generated'])}\n\n"
            if col_diff.get('only_in_reference'):
                report += f"**仅存在于参考结果**: {', '.join(col_diff['only_in_reference'])}\n\n"

        # 详细差异
        differences = comparison.get('differences', [])
        if differences:
            report += """## 详细差异

"""
            # 行数不一致
            row_count_diff = next((d for d in differences if d.get("type") == "row_count_mismatch"), None)
            if row_count_diff:
                report += f"""### 行数不一致

- 生成结果：{row_count_diff['generated_count']} 行
- 参考结果：{row_count_diff['reference_count']} 行

"""

            # 数据差异（限制显示前 20 个）
            data_diffs = [d for d in differences if d.get("type") != "row_count_mismatch"][:20]
            if data_diffs:
                report += """### 数据差异示例

| 行号 | 列名 | 生成值 | 参考值 |
|------|------|--------|--------|
"""
                for diff in data_diffs:
                    row = diff.get('row', 'N/A')
                    for col_diff in diff.get('differences', []):
                        report += f"| {row} | {col_diff['column']} | {col_diff['generated']} | {col_diff['reference']} |\n"

                if len(data_diffs) < len(differences):
                    report += f"\n*还有 {len(differences) - len(data_diffs)} 个差异未显示*\n"

        # 建议
        report += """
## 处理建议

"""
        if comparison.get('identical'):
            report += "✅ 验证通过，规则可以投入使用。\n"
        else:
            report += """⚠️ 验证未通过，建议：

1. 检查规则配置是否正确
2. 检查数据处理逻辑是否符合预期
3. 检查输入数据是否完整
4. 根据差异调整规则后重新验证
"""

        # 保存报告
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report)
            return f"验证报告已保存到：{output_path}"

        return report


# 全局结果验证器实例
_result_validator: Optional[ResultValidator] = None


def get_result_validator(base_dir: Optional[Path] = None) -> ResultValidator:
    """获取结果验证器实例

    参数:
        base_dir: proc-agent 根目录

    返回:
        结果验证器实例
    """
    global _result_validator
    if _result_validator is None:
        _result_validator = ResultValidator(base_dir)
    return _result_validator
