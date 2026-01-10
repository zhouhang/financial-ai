"""
数据整理处理引擎 - 协调整个数据处理流程
"""
import logging
import time
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

from .models import ProcessingResult, ProcessingStep, ProcessingMetadata
from .extractor import DataExtractor
from .transformer import DataTransformer
from .template_writer import TemplateWriter
from .file_matcher import FileMatcher

logger = logging.getLogger(__name__)


class ProcessingEngine:
    """数据整理处理引擎"""
    
    def __init__(self, schema: Dict):
        self.schema = schema
        self.extractor = DataExtractor(schema)
        self.transformer = DataTransformer(schema)
        self.template_writer = TemplateWriter(schema)
        self.file_matcher = FileMatcher(schema)
        
        # 工作流控制
        self.workflow_controls = schema.get("workflow_controls", {})
        self.error_handling = self.workflow_controls.get("error_handling", {})
        self.max_errors = self.error_handling.get("max_errors", 999)
        self.error_count = 0
        
        # 处理步骤记录
        self.steps: List[ProcessingStep] = []
    
    def process(self, file_paths: List[str], output_dir: str, report_dir: str = None) -> ProcessingResult:
        """
        执行完整的数据整理流程
        
        Args:
            file_paths: 上传的文件路径列表
            output_dir: 输出目录
            report_dir: 报告目录
        
        Returns:
            处理结果
        """
        start_time = time.time()
        task_id = f"proc_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{id(self) & 0xFFFFFF:06x}"
        
        try:
            # 1. 文件匹配
            matched_files = self._match_files(file_paths)
            
            # 2. 数据提取
            extracted_data = self._extract_data(matched_files)
            
            # 3. 数据转换
            calculation_results = self._transform_data(extracted_data)
            
            # 4. 写入模板
            output_file = self._write_output(extracted_data, calculation_results, output_dir)
            
            # 5. 生成详细报告
            if report_dir:
                self._generate_report(task_id, matched_files, extracted_data, calculation_results, report_dir)
            
            # 6. 生成结果
            execution_time = time.time() - start_time
            metadata = ProcessingMetadata(
                project_name=self.schema.get("metadata", {}).get("project_name", "数据整理"),
                rule_version=self.schema.get("version", "1.0"),
                execution_time_seconds=round(execution_time, 2)
            )
            
            result = ProcessingResult(
                task_id=task_id,
                status="success",
                output_file=output_file,
                metadata=metadata,
                steps=self.steps
            )
            
            logger.info(f"数据整理完成: task_id={task_id}, 耗时={execution_time:.2f}秒")
            return result
        
        except Exception as e:
            logger.error(f"数据整理失败: {str(e)}", exc_info=True)
            return ProcessingResult(
                task_id=task_id,
                status="failed",
                error=str(e),
                steps=self.steps
            )
    
    def _generate_report(
        self,
        task_id: str,
        matched_files: Dict[str, str],
        extracted_data: Dict[str, Any],
        calculation_results: Dict[str, Any],
        report_dir: str
    ):
        """生成详细报告"""
        import json
        
        report = {
            "task_id": task_id,
            "timestamp": datetime.now().isoformat(),
            "schema_version": self.schema.get("version", "1.0"),
            "project_name": self.schema.get("metadata", {}).get("project_name", ""),
            
            "files_processed": {
                source_id: Path(file_path).name
                for source_id, file_path in matched_files.items()
            },
            
            "data_extraction": {
                source_id: {
                    "records": len(df) if hasattr(df, '__len__') else 0,
                    "columns": list(df.columns) if hasattr(df, 'columns') else []
                }
                for source_id, df in extracted_data.items()
            },
            
            "calculations": calculation_results,
            
            "processing_steps": [step.to_dict() for step in self.steps],
            
            "summary": {
                "total_steps": len(self.steps),
                "completed_steps": len([s for s in self.steps if s.status == "completed"]),
                "failed_steps": len([s for s in self.steps if s.status == "failed"])
            }
        }
        
        report_file = Path(report_dir) / f"{task_id}_report.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        logger.info(f"详细报告已生成: {report_file}")
    
    def _match_files(self, file_paths: List[str]) -> Dict[str, str]:
        """匹配文件到数据源"""
        step = ProcessingStep(
            step_name="文件匹配",
            step_type="file_matching",
            status="processing",
            start_time=datetime.now().isoformat()
        )
        self.steps.append(step)
        
        try:
            matched = self.file_matcher.match_files(file_paths)
            step.status = "completed"
            step.end_time = datetime.now().isoformat()
            step.details = {"matched_files": matched}
            logger.info(f"文件匹配完成: {len(matched)} 个数据源")
            return matched
        except Exception as e:
            step.status = "failed"
            step.error_message = str(e)
            self._handle_error("file_matching", e)
            raise
    
    def _extract_data(self, matched_files: Dict[str, str]) -> Dict[str, Any]:
        """提取数据"""
        step = ProcessingStep(
            step_name="数据提取",
            step_type="extraction",
            status="processing",
            start_time=datetime.now().isoformat()
        )
        self.steps.append(step)
        
        extracted_data = {}
        total_records = 0
        
        try:
            for source_id, file_path in matched_files.items():
                try:
                    logger.info(f"提取数据: {source_id} <- {file_path}")
                    df = self.extractor.extract(source_id, file_path)
                    extracted_data[source_id] = df
                    total_records += len(df)
                except Exception as e:
                    error_action = self._handle_error("extraction", e)
                    if error_action == "skip_and_log":
                        logger.warning(f"跳过数据源 {source_id}: {str(e)}")
                        continue
                    else:
                        raise
            
            step.status = "completed"
            step.end_time = datetime.now().isoformat()
            step.records_processed = total_records
            step.details = {
                "sources_processed": len(extracted_data),
                "total_records": total_records
            }
            logger.info(f"数据提取完成: {len(extracted_data)} 个数据源, {total_records} 条记录")
            return extracted_data
        
        except Exception as e:
            step.status = "failed"
            step.error_message = str(e)
            raise
    
    def _transform_data(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """转换数据"""
        step = ProcessingStep(
            step_name="数据转换",
            step_type="transformation",
            status="processing",
            start_time=datetime.now().isoformat()
        )
        self.steps.append(step)
        
        try:
            results = self.transformer.transform(extracted_data)
            step.status = "completed"
            step.end_time = datetime.now().isoformat()
            step.details = {"calculated_fields": list(results.keys())}
            logger.info(f"数据转换完成: {len(results)} 个计算字段")
            return results
        except Exception as e:
            step.status = "failed"
            step.error_message = str(e)
            error_action = self._handle_error("calculation", e)
            if error_action.startswith("use_default:"):
                default_value = float(error_action.split(":")[1])
                logger.warning(f"计算失败，使用默认值: {default_value}")
                return {"error": default_value}
            raise
    
    def _write_output(
        self,
        extracted_data: Dict[str, Any],
        calculation_results: Dict[str, Any],
        output_dir: str
    ) -> str:
        """写入输出文件"""
        step = ProcessingStep(
            step_name="写入输出",
            step_type="output",
            status="processing",
            start_time=datetime.now().isoformat()
        )
        self.steps.append(step)
        
        try:
            # 获取模板文件路径（简化：假设模板在 schemas 目录）
            template_file = self.schema.get("template_mapping", {}).get("template_file", "template.xlsx")
            template_path = Path(output_dir).parent / "schemas" / "data_preparation" / template_file
            
            # 如果没有模板，创建一个简单的输出文件
            if not template_path.exists():
                logger.warning(f"模板文件不存在: {template_path}, 创建简单输出")
                output_file = self._create_simple_output(extracted_data, calculation_results, output_dir)
            else:
                output_file = self.template_writer.write_to_template(
                    str(template_path),
                    output_dir,
                    calculation_results,
                    extracted_data
                )
            
            step.status = "completed"
            step.end_time = datetime.now().isoformat()
            step.details = {"output_file": output_file}
            logger.info(f"输出文件创建完成: {output_file}")
            return output_file
        
        except Exception as e:
            step.status = "failed"
            step.error_message = str(e)
            raise
    
    def _create_simple_output(
        self,
        extracted_data: Dict[str, Any],
        calculation_results: Dict[str, Any],
        output_dir: str
    ) -> str:
        """创建简单的输出文件（当没有模板时）"""
        import pandas as pd
        from datetime import datetime
        
        output_filename = f"data_preparation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        output_path = Path(output_dir) / output_filename
        
        with pd.ExcelWriter(str(output_path), engine='openpyxl') as writer:
            # 写入计算结果
            if calculation_results:
                calc_df = pd.DataFrame([calculation_results])
                calc_df.to_excel(writer, sheet_name='计算结果', index=False)
            
            # 写入提取的数据
            for source_id, df in extracted_data.items():
                if isinstance(df, pd.DataFrame):
                    sheet_name = source_id[:31]  # Excel sheet name 最多31字符
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        return str(output_path)
    
    def _handle_error(self, error_type: str, error: Exception) -> str:
        """
        处理错误
        
        Args:
            error_type: 错误类型 (extraction, calculation, etc.)
            error: 异常对象
        
        Returns:
            错误处理动作 (skip_and_log, use_default:0, 等)
        """
        self.error_count += 1
        
        # 检查是否超过最大错误数
        if self.error_count > self.max_errors:
            logger.error(f"错误次数超过最大限制: {self.max_errors}")
            raise Exception(f"错误次数超过最大限制: {self.max_errors}")
        
        # 根据错误类型返回处理动作
        if error_type == "extraction":
            return self.error_handling.get("on_extraction_error", "raise")
        elif error_type == "calculation":
            return self.error_handling.get("on_calculation_error", "raise")
        else:
            return "raise"
