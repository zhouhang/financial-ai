"""
对账引擎 - 核心对账逻辑
"""
import pandas as pd
from typing import Dict, List, Optional
from .models import ReconciliationIssue, ReconciliationSummary, ReconciliationMetadata
from .data_cleaner import DataCleaner
from .file_matcher import FileMatcher
from datetime import datetime


class ReconciliationEngine:
    """对账引擎"""
    
    def __init__(self, schema: Dict):
        self.schema = schema
        self.file_matcher = FileMatcher(schema)
        self.data_cleaner = DataCleaner(schema)
        self.key_field_role = schema.get("key_field_role", "order_id")
        self.tolerance = schema.get("tolerance", {})
        self.custom_validations = schema.get("custom_validations", [])
    
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
        
        # 2. 加载和清洗数据
        business_df = pd.DataFrame()
        finance_df = pd.DataFrame()
        
        if matched_files.get("business"):
            business_df = self.data_cleaner.load_and_clean("business", matched_files["business"])
        
        if matched_files.get("finance"):
            finance_df = self.data_cleaner.load_and_clean("finance", matched_files["finance"])
        
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
            "summary": summary,
            "issues": issues,
            "metadata": metadata
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
            
            # 检查是否存在
            if biz_records.empty and not fin_records.empty:
                issues.append(ReconciliationIssue(
                    order_id=order_id,
                    issue_type="missing_in_business",
                    business_value=None,
                    finance_value=self._get_record_value(fin_records, "amount"),
                    detail=f"财务系统存在，业务台账无此订单记录"
                ))
                continue
            
            if fin_records.empty and not biz_records.empty:
                issues.append(ReconciliationIssue(
                    order_id=order_id,
                    issue_type="missing_in_finance",
                    business_value=self._get_record_value(biz_records, "amount"),
                    finance_value=None,
                    detail=f"业务台账存在，财务系统无此订单记录"
                ))
                continue
            
            # 两边都存在，执行详细对账
            record_issues = self._check_record(order_id, biz_records, fin_records)
            issues.extend(record_issues)
        
        return issues
    
    def _check_record(self, order_id: str, biz_records: pd.DataFrame, fin_records: pd.DataFrame) -> List[ReconciliationIssue]:
        """检查单条记录"""
        issues = []
        
        # 获取第一条记录作为代表
        biz = biz_records.iloc[0].to_dict() if not biz_records.empty else {}
        fin = fin_records.iloc[0].to_dict() if not fin_records.empty else {}
        
        # 1. 检查自定义验证规则
        for validation in self.custom_validations:
            issue = self._apply_custom_validation(order_id, biz, fin, validation)
            if issue:
                issues.append(issue)
                # 如果是 skipped，不再检查其他规则
                if issue.issue_type == "skipped":
                    return issues
        
        # 2. 检查金额
        if "amount" in biz and "amount" in fin:
            amount_issue = self._check_amount(order_id, biz, fin)
            if amount_issue:
                issues.append(amount_issue)
        
        # 3. 检查日期
        if "date" in biz and "date" in fin:
            date_issue = self._check_date(order_id, biz, fin)
            if date_issue:
                issues.append(date_issue)
        
        return issues
    
    def _apply_custom_validation(self, order_id: str, biz: Dict, fin: Dict, validation: Dict) -> Optional[ReconciliationIssue]:
        """应用自定义验证规则"""
        try:
            condition_expr = validation.get("condition_expr", "")
            if not condition_expr:
                return None
            
            # 执行条件表达式
            # 注意：这里使用 eval 有安全风险，生产环境应该使用更安全的表达式解析器
            result = eval(condition_expr, {"biz": biz, "fin": fin, "abs": abs, "float": float, "str": str})
            
            if result:
                # 生成详细信息
                detail_template = validation.get("detail_template", "")
                try:
                    detail = detail_template.format(biz=biz, fin=fin)
                except:
                    detail = detail_template
                
                return ReconciliationIssue(
                    order_id=order_id,
                    issue_type=validation.get("issue_type", "custom"),
                    business_value=self._get_dict_value(biz, "amount"),
                    finance_value=self._get_dict_value(fin, "amount"),
                    detail=detail
                )
        except Exception as e:
            # 验证规则执行失败，记录但不中断
            print(f"自定义验证规则执行失败: {validation.get('name')}, 错误: {str(e)}")
        
        return None
    
    def _check_amount(self, order_id: str, biz: Dict, fin: Dict) -> Optional[ReconciliationIssue]:
        """检查金额"""
        try:
            biz_amount = float(biz.get("amount", 0))
            fin_amount = float(fin.get("amount", 0))
            
            max_diff = self.tolerance.get("amount_diff_max", 0.0)
            diff = abs(biz_amount - fin_amount)
            
            if diff > max_diff:
                return ReconciliationIssue(
                    order_id=order_id,
                    issue_type="amount_mismatch",
                    business_value=f"{biz_amount:.2f}",
                    finance_value=f"{fin_amount:.2f}",
                    detail=f"业务金额 {biz_amount:.2f} vs 财务金额 {fin_amount:.2f}，差额 {diff:.2f} 超出容差 {max_diff}"
                )
        except (ValueError, TypeError):
            pass
        
        return None
    
    def _check_date(self, order_id: str, biz: Dict, fin: Dict) -> Optional[ReconciliationIssue]:
        """检查日期"""
        biz_date = str(biz.get("date", ""))
        fin_date = str(fin.get("date", ""))
        
        date_format = self.tolerance.get("date_format", "%Y-%m-%d")
        
        # 尝试格式化日期进行比较
        try:
            if biz_date and fin_date:
                biz_dt = pd.to_datetime(biz_date)
                fin_dt = pd.to_datetime(fin_date)
                
                biz_formatted = biz_dt.strftime(date_format)
                fin_formatted = fin_dt.strftime(date_format)
                
                if biz_formatted != fin_formatted:
                    return ReconciliationIssue(
                        order_id=order_id,
                        issue_type="date_mismatch",
                        business_value=biz_date,
                        finance_value=fin_date,
                        detail=f"业务交易时间 {biz_date} 与财务记录 {fin_date} 不一致"
                    )
        except:
            pass
        
        return None
    
    def _generate_summary(self, business_df: pd.DataFrame, finance_df: pd.DataFrame, issues: List[ReconciliationIssue]) -> ReconciliationSummary:
        """生成对账摘要"""
        total_business = len(business_df) if not business_df.empty else 0
        total_finance = len(finance_df) if not finance_df.empty else 0
        
        # 统计有问题的记录数
        unmatched = len([i for i in issues if i.issue_type not in ["skipped"]])
        matched = max(total_business, total_finance) - unmatched
        
        return ReconciliationSummary(
            total_business_records=total_business,
            total_finance_records=total_finance,
            matched_records=max(0, matched),
            unmatched_records=unmatched
        )
    
    def _get_record_value(self, records: pd.DataFrame, field: str) -> Optional[str]:
        """获取记录的字段值"""
        if records.empty or field not in records.columns:
            return None
        return str(records.iloc[0][field])
    
    def _get_dict_value(self, d: Dict, field: str) -> Optional[str]:
        """获取字典的字段值"""
        value = d.get(field)
        return str(value) if value is not None else None

