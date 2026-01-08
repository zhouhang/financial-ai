"""
对账引擎 - 核心对账逻辑
"""
import pandas as pd
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional
from .models import ReconciliationIssue, ReconciliationSummary, ReconciliationMetadata
from .data_cleaner import DataCleaner
from .file_matcher import FileMatcher
from datetime import datetime

logger = logging.getLogger(__name__)


class ReconciliationEngine:
    """对账引擎"""
    
    def __init__(self, schema: Dict):
        self.schema = schema
        self.file_matcher = FileMatcher(schema)
        self.data_cleaner = DataCleaner(schema)
        self.key_field_role = schema.get("key_field_role", "order_id")
        self.tolerance = schema.get("tolerance", {})
        self.custom_validations = schema.get("custom_validations", [])
        # 文件名信息（在 reconcile 时设置）
        self.business_file_names: List[str] = []
        self.finance_file_names: List[str] = []
    
    def reconcile(self, file_paths: List[str]) -> Dict:
        """
        执行对账
        
        Args:
            file_paths: 上传的文件路径列表
        
        Returns:
            对账结果字典
        """
        # 1. 文件匹配
        matched_files = self.file_matcher.match_files(file_paths)
        
        # 提取文件名（用于 detail 中显示）
        self.business_file_names = [Path(fp).name for fp in matched_files.get("business", [])]
        self.finance_file_names = [Path(fp).name for fp in matched_files.get("finance", [])]
        
        # 调试日志
        logger.info(f"对账引擎 - 输入文件路径: {file_paths}")
        logger.info(f"对账引擎 - 文件匹配结果: business={len(matched_files.get('business', []))}, finance={len(matched_files.get('finance', []))}")
        
        # 2. 加载和清洗数据
        business_df = pd.DataFrame()
        finance_df = pd.DataFrame()
        
        if matched_files.get("business"):
            logger.info(f"对账引擎 - 开始清洗业务数据，文件: {matched_files['business']}")
            business_df = self.data_cleaner.load_and_clean("business", matched_files["business"])
            logger.info(f"对账引擎 - 业务数据清洗完成，记录数: {len(business_df)}")
        else:
            logger.warning(f"对账引擎 - 警告：没有匹配到业务文件")
        
        if matched_files.get("finance"):
            logger.info(f"对账引擎 - 开始清洗财务数据，文件: {matched_files['finance']}")
            finance_df = self.data_cleaner.load_and_clean("finance", matched_files["finance"])
            logger.info(f"对账引擎 - 财务数据清洗完成，记录数: {len(finance_df)}")
        else:
            logger.warning(f"对账引擎 - 警告：没有匹配到财务文件")
        
        # 3. 执行对账
        issues = self._perform_reconciliation(business_df, finance_df)
        
        # 4. 生成摘要
        summary = self._generate_summary(business_df, finance_df, issues)
        
        # 5. 生成元数据
        metadata = ReconciliationMetadata(
            business_file_count=len(matched_files.get("business", [])),
            finance_file_count=len(matched_files.get("finance", [])),
            rule_version=self.schema.get("version", "1.0"),
            processed_at=datetime.now().isoformat()
        )
        
        return {
            "summary": summary.to_dict(),
            "issues": [issue.to_dict() for issue in issues],
            "metadata": metadata.to_dict()
        }
    
    def _perform_reconciliation(self, business_df: pd.DataFrame, finance_df: pd.DataFrame) -> List[ReconciliationIssue]:
        """执行对账逻辑"""
        issues = []
        
        if business_df.empty and finance_df.empty:
            return issues
        
        # 确保关键字段存在
        if self.key_field_role not in business_df.columns and not business_df.empty:
            raise ValueError(f"业务数据缺少关键字段: {self.key_field_role}")
        if self.key_field_role not in finance_df.columns and not finance_df.empty:
            raise ValueError(f"财务数据缺少关键字段: {self.key_field_role}")
        
        # 获取所有订单ID
        business_ids = set(business_df[self.key_field_role].astype(str)) if not business_df.empty else set()
        finance_ids = set(finance_df[self.key_field_role].astype(str)) if not finance_df.empty else set()
        
        all_ids = business_ids | finance_ids
        
        # 逐条对账
        for order_id in all_ids:
            biz_records = business_df[business_df[self.key_field_role].astype(str) == order_id] if not business_df.empty else pd.DataFrame()
            fin_records = finance_df[finance_df[self.key_field_role].astype(str) == order_id] if not finance_df.empty else pd.DataFrame()
            
            # 获取记录字典（如果存在）
            biz = biz_records.iloc[0].to_dict() if not biz_records.empty else {}
            fin = fin_records.iloc[0].to_dict() if not fin_records.empty else {}
            
            # 标记是否存在
            biz_exists = not biz_records.empty
            fin_exists = not fin_records.empty
            
            # 执行所有自定义验证规则（按顺序检查，一旦满足条件就停止）
            for validation in self.custom_validations:
                issue = self._apply_custom_validation(
                    order_id, 
                    biz, 
                    fin, 
                    validation,
                    biz_exists=biz_exists,
                    fin_exists=fin_exists,
                    biz_records=biz_records,
                    fin_records=fin_records
                )
                if issue:
                    issues.append(issue)
                    # 只要满足任何一个 custom_validation 条件，就停止后续检查
                    break
        
        return issues
    
    
    def _apply_custom_validation(
        self, 
        order_id: str, 
        biz: Dict, 
        fin: Dict, 
        validation: Dict,
        biz_exists: bool = True,
        fin_exists: bool = True,
        biz_records: pd.DataFrame = None,
        fin_records: pd.DataFrame = None
    ) -> Optional[ReconciliationIssue]:
        """应用自定义验证规则"""
        try:
            condition_expr = validation.get("condition_expr", "")
            if not condition_expr:
                return None
            
            # 准备 eval 环境，包含 biz, fin, biz_exists, fin_exists 等变量
            # 将 tolerance 中的配置项添加到 eval 环境
            tolerance = self.tolerance
            eval_env = {
                "biz": biz,
                "fin": fin,
                "biz_exists": biz_exists,
                "fin_exists": fin_exists,
                "abs": abs,
                "float": float,
                "str": str,
                "pd": pd,
                "len": len,
                "tolerance": tolerance,
                # 为了兼容性，直接将常用配置项添加到环境中
                "amount_diff_max": tolerance.get("amount_diff_max", 0.0),
                "date_format": tolerance.get("date_format", "%Y-%m-%d"),
            }
            
            # 执行条件表达式
            # 注意：这里使用 eval 有安全风险，生产环境应该使用更安全的表达式解析器
            result = eval(condition_expr, eval_env)
            
            if result:
                # 获取文件名
                business_file_name = ", ".join(self.business_file_names) if self.business_file_names else "业务文件"
                finance_file_name = ", ".join(self.finance_file_names) if self.finance_file_names else "财务文件"
                
                # 生成详细信息
                detail_template = validation.get("detail_template", "")
                
                # 先替换文件名占位符 {biz_file} 和 {fin_file}
                detail_template = detail_template.replace("{biz_file}", business_file_name)
                detail_template = detail_template.replace("{fin_file}", finance_file_name)
                
                # 替换常见的业务描述词为文件名
                replacements = {
                    "对账流水": business_file_name,
                    "供应商账单": finance_file_name,
                    "业务台账": business_file_name,
                    "财务系统": finance_file_name,
                    "业务数据": business_file_name,
                    "财务数据": finance_file_name,
                    "业务文件": business_file_name,
                    "财务文件": finance_file_name,
                    "业务": business_file_name,
                    "财务": finance_file_name,
                }
                
                for old, new in replacements.items():
                    detail_template = detail_template.replace(old, new)
                
                # 准备格式化参数，计算常用的值
                format_kwargs = {
                    "biz": biz,
                    "fin": fin,
                }
                
                # 如果涉及金额差值，预先计算（从 detail_template 中使用的字段自动识别）
                # 尝试从 detail_template 中提取字段名，如果包含 {biz[amount]} 或 {fin[amount]}，则计算差值
                if biz_exists and fin_exists and "{biz[amount]" in detail_template and "{fin[amount]" in detail_template:
                    try:
                        # 从 biz 和 fin 中提取 amount 字段（字段名已在 condition_expr 和 detail_template 中定义）
                        biz_amount = float(biz.get("amount", 0)) if "amount" in biz else 0
                        fin_amount = float(fin.get("amount", 0)) if "amount" in fin else 0
                        amount_diff = abs(biz_amount - fin_amount)
                        # amount_diff_max 为非必配置项，默认为 0.0
                        max_diff = self.tolerance.get("amount_diff_max", 0.0)
                        format_kwargs["amount_diff"] = amount_diff
                        format_kwargs["amount_diff_formatted"] = f"{amount_diff:.2f}"
                        format_kwargs["amount_diff_max"] = max_diff
                    except:
                        pass
                
                # 格式化 detail
                try:
                    detail = detail_template.format(**format_kwargs)
                except Exception as e:
                    # 如果格式化失败，尝试简单的替换
                    try:
                        detail = detail_template.format(biz=biz, fin=fin)
                    except:
                        detail = detail_template
                
                # 确定业务值和财务值（从 detail_template 和 condition_expr 中自动提取字段名）
                # 优先从 detail_template 中提取（如 {biz[amount]}），如果没有则从 condition_expr 中提取（如 biz.get('amount')）
                business_value = None
                finance_value = None
                
                # 从 detail_template 中提取字段名（查找 {biz[...]} 和 {fin[...]} 格式）
                biz_field_match = re.search(r'\{biz\[(\w+)\]', detail_template)
                fin_field_match = re.search(r'\{fin\[(\w+)\]', detail_template)
                
                # 如果 detail_template 中没有，尝试从 condition_expr 中提取（查找 biz.get('xxx') 或 fin.get('xxx')）
                business_value_field = None
                finance_value_field = None
                
                if biz_field_match:
                    business_value_field = biz_field_match.group(1)
                else:
                    # 从 condition_expr 中提取 biz.get('xxx') 或 biz['xxx'] 格式
                    biz_get_match = re.search(r"biz\.get\(['\"](\w+)['\"]", condition_expr)
                    biz_key_match = re.search(r"biz\[['\"](\w+)['\"]", condition_expr)
                    if biz_get_match:
                        business_value_field = biz_get_match.group(1)
                    elif biz_key_match:
                        business_value_field = biz_key_match.group(1)
                    else:
                        # 如果都没有，尝试从所有 custom_validations 中提取最常用的字段（如 amount）
                        # 遍历所有规则的 detail_template 和 condition_expr，找出最常用的字段
                        common_field = self._extract_common_field()
                        business_value_field = common_field
                
                if fin_field_match:
                    finance_value_field = fin_field_match.group(1)
                else:
                    # 从 condition_expr 中提取 fin.get('xxx') 或 fin['xxx'] 格式
                    fin_get_match = re.search(r"fin\.get\(['\"](\w+)['\"]", condition_expr)
                    fin_key_match = re.search(r"fin\[['\"](\w+)['\"]", condition_expr)
                    if fin_get_match:
                        finance_value_field = fin_get_match.group(1)
                    elif fin_key_match:
                        finance_value_field = fin_key_match.group(1)
                    else:
                        # 如果都没有，尝试从所有 custom_validations 中提取最常用的字段
                        common_field = self._extract_common_field()
                        finance_value_field = common_field
                
                if biz_exists and business_value_field:
                    business_value = self._get_dict_value(biz, business_value_field)
                if fin_exists and finance_value_field:
                    finance_value = self._get_dict_value(fin, finance_value_field)
                
                return ReconciliationIssue(
                    order_id=order_id,
                    issue_type=validation.get("issue_type", "custom"),
                    business_value=business_value,
                    finance_value=finance_value,
                    detail=detail
                )
        except Exception as e:
            # 验证规则执行失败，记录但不中断
            logger.error(f"自定义验证规则执行失败: {validation.get('name')}, 错误: {str(e)}")
        
        return None
    
    
    def _generate_summary(self, business_df: pd.DataFrame, finance_df: pd.DataFrame, issues: List[ReconciliationIssue]) -> ReconciliationSummary:
        """生成对账摘要"""
        total_business = len(business_df) if not business_df.empty else 0
        total_finance = len(finance_df) if not finance_df.empty else 0
        
        # 从 custom_validations 中自动推断：哪些 issue_type 表示"未匹配"（缺失记录）
        # 检查条件表达式是否包含 "not biz_exists" 或 "not fin_exists"
        unmatched_issue_types = set()
        for validation in self.custom_validations:
            condition_expr = validation.get("condition_expr", "")
            if "not biz_exists" in condition_expr or "not fin_exists" in condition_expr:
                issue_type = validation.get("issue_type")
                if issue_type:
                    unmatched_issue_types.add(issue_type)
        
        # 统计未匹配的记录数（根据配置的 issue_type）
        unmatched_count = len([i for i in issues if i.issue_type in unmatched_issue_types])
        
        # 匹配记录数 = 总记录数 - 未匹配记录数
        # 方式1：业务总数 - 业务中未匹配的（仅业务存在，财务不存在）
        business_unmatched = len([i for i in issues 
                                  if i.issue_type in unmatched_issue_types 
                                  and (i.business_value is not None and i.finance_value is None)])
        matched_via_business = total_business - business_unmatched
        
        # 方式2：财务总数 - 财务中未匹配的（仅财务存在，业务不存在）
        finance_unmatched = len([i for i in issues 
                                if i.issue_type in unmatched_issue_types 
                                and (i.business_value is None and i.finance_value is not None)])
        matched_via_finance = total_finance - finance_unmatched
        
        # 取两者中的较小值（更保守）
        matched = min(matched_via_business, matched_via_finance)
        
        # 汇总业务/财务文件名（可能有多个，用逗号拼接）
        business_file_name = ", ".join(self.business_file_names) if self.business_file_names else ""
        finance_file_name = ", ".join(self.finance_file_names) if self.finance_file_names else ""
        
        return ReconciliationSummary(
            total_business_records=total_business,
            total_finance_records=total_finance,
            matched_records=max(0, matched),
            unmatched_records=unmatched_count,
            business_file=business_file_name,
            finance_file=finance_file_name,
        )
    
    def _extract_common_field(self) -> Optional[str]:
        """从所有 custom_validations 中提取最常用的字段名（用于作为默认值）"""
        field_counts = {}
        
        # 优先字段列表（amount 字段优先级最高）
        priority_fields = ["amount", "price", "money", "value"]
        
        for validation in self.custom_validations:
            # 从 detail_template 中提取字段名
            detail_template = validation.get("detail_template", "")
            for match in re.finditer(r'\{biz\[(\w+)\]', detail_template):
                field = match.group(1)
                field_counts[field] = field_counts.get(field, 0) + 1
            
            for match in re.finditer(r'\{fin\[(\w+)\]', detail_template):
                field = match.group(1)
                field_counts[field] = field_counts.get(field, 0) + 1
            
            # 从 condition_expr 中提取字段名
            condition_expr = validation.get("condition_expr", "")
            for match in re.finditer(r"[bf]iz\.get\(['\"](\w+)['\"]", condition_expr):
                field = match.group(1)
                field_counts[field] = field_counts.get(field, 0) + 1
        
        # 优先返回 priority_fields 中出现的字段
        for priority_field in priority_fields:
            if priority_field in field_counts:
                return priority_field
        
        # 如果没有优先字段，返回出现次数最多的字段
        if field_counts:
            return max(field_counts.items(), key=lambda x: x[1])[0]
        
        return None  # 如果都没有找到，返回 None
    
    def _get_record_value(self, records: pd.DataFrame, field: str) -> Optional[str]:
        """获取记录的字段值"""
        if records.empty or field not in records.columns:
            return None
        return str(records.iloc[0][field])
    
    def _get_dict_value(self, d: Dict, field: str) -> Optional[str]:
        """获取字典的字段值"""
        value = d.get(field)
        return str(value) if value is not None else None

