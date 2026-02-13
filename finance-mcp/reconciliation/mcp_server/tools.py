"""
MCP 工具定义
"""
import json
import uuid
import logging
from pathlib import Path
from typing import Dict, Any, List
from mcp import Tool
from .task_manager import TaskManager
from .config import UPLOAD_DIR, ALLOWED_EXTENSIONS, SCHEMA_DIR, RECONCILIATION_SCHEMAS_FILE, BASE_DIR, FINANCE_MCP_DIR
from .schema_loader import SchemaLoader
import re

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(FINANCE_MCP_DIR / 'reconciliation_mcp.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# 全局任务管理器
task_manager = TaskManager()


def load_json_with_comments(file_path: Path) -> Dict:
    """加载 JSON 文件（支持 JSON5 格式的注释）"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 移除多行注释 (/* ... */) - 先处理多行注释
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    
    # 移除单行注释 (// ...) - 但保留字符串中的 //
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
                break  # 移除该行剩余部分
            
            new_line.append(char)
            i += 1
        
        lines.append(''.join(new_line))
    
    content = '\n'.join(lines)
    
    return json.loads(content)


def create_tools() -> List[Tool]:
    """创建所有 MCP 工具"""
    return [
        Tool(
            name="reconciliation_start",
            description="开始对账任务。根据对账类型自动获取配置，系统会异步执行对账并返回任务 ID。",
            inputSchema={
                "type": "object",
                "properties": {
                    "reconciliation_type": {
                        "type": "string",
                        "description": "对账类型中文名称，例如：直销对账"
                    },
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要对账的文件路径列表"
                    }
                },
                "required": ["reconciliation_type", "files"]
            }
        ),
        Tool(
            name="reconciliation_status",
            description="查询对账任务状态",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "任务 ID"
                    }
                },
                "required": ["task_id"]
            }
        ),
        Tool(
            name="reconciliation_result",
            description="获取对账结果",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "任务 ID"
                    }
                },
                "required": ["task_id"]
            }
        ),
        Tool(
            name="reconciliation_list_tasks",
            description="列出所有对账任务",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="file_upload",
            description="上传文件并保存到服务器，支持多个文件上传。返回上传文件的路径列表。",
            inputSchema={
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "description": "文件数组，每个元素包含 filename, content (base64编码)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "filename": {
                                    "type": "string",
                                    "description": "文件名"
                                },
                                "content": {
                                    "type": "string",
                                    "description": "文件内容（base64编码）"
                                }
                            },
                            "required": ["filename", "content"]
                        }
                    }
                },
                "required": ["files"]
            }
        ),
        Tool(
            name="get_reconciliation",
            description="根据对账类型获取对账配置和回调地址",
            inputSchema={
                "type": "object",
                "properties": {
                    "reconciliation_type": {
                        "type": "string",
                        "description": "对账类型中文名称，例如：直销对账"
                    }
                },
                "required": ["reconciliation_type"]
            }
        ),
        Tool(
            name="analyze_files",
            description="分析已上传的文件，返回文件的列信息、行数、样本数据和文件类型（business/finance）。需要先通过 file_upload 上传文件。",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要分析的文件路径列表（由 file_upload 返回的路径）"
                    }
                },
                "required": ["file_paths"]
            }
        ),
        # 注意：list/save/update/delete_reconciliation_rule 已移至 auth/tools.py
        # 由 auth 模块统一处理（带权限控制）
    ]


async def handle_tool_call(tool_name: str, arguments: Dict[str, Any]) -> Any:
    """处理工具调用"""
    
    if tool_name == "reconciliation_start":
        return await _reconciliation_start(arguments)
    
    elif tool_name == "reconciliation_status":
        return await _reconciliation_status(arguments)
    
    elif tool_name == "reconciliation_result":
        return await _reconciliation_result(arguments)
    
    elif tool_name == "reconciliation_list_tasks":
        return await _reconciliation_list_tasks(arguments)
    
    elif tool_name == "file_upload":
        return await _file_upload(arguments)
    
    elif tool_name == "get_reconciliation":
        return await _get_reconciliation(arguments)
    
    elif tool_name == "analyze_files":
        return await _analyze_files(arguments)
    
    else:
        return {"error": f"未知的工具: {tool_name}"}


async def _reconciliation_start(args: Dict) -> Dict:
    """开始对账任务"""
    try:
        reconciliation_type = args.get("reconciliation_type")
        files = args.get("files", [])
        
        if not reconciliation_type:
            return {"error": "缺少 reconciliation_type 参数"}
        
        # 1. 读取配置文件，获取 schema 和 callback_url
        if not RECONCILIATION_SCHEMAS_FILE.exists():
            return {"error": f"配置文件不存在: {RECONCILIATION_SCHEMAS_FILE}"}
        
        config = load_json_with_comments(RECONCILIATION_SCHEMAS_FILE)
        
        # 2. 查找匹配的对账类型
        types = config.get("types", [])
        matched_type = None
        
        for type_config in types:
            if type_config.get("name_cn") == reconciliation_type:
                matched_type = type_config
                break
        
        if not matched_type:
            available_types = [t.get("name_cn") for t in types if t.get("name_cn")]
            return {
                "error": f"未找到对账类型: {reconciliation_type}",
                "available_types": available_types
            }
        
        # 3. 获取 schema_path 和 callback_url
        schema_path_config = matched_type.get("schema_path")
        callback_url = matched_type.get("callback_url", "")
        
        if not schema_path_config:
            return {"error": f"配置缺少 schema_path: {reconciliation_type}"}
        
        # 4. 读取 schema 文件
        # schema_path 格式: direct_sales_schema.json (只包含文件名)
        # SCHEMA_DIR 已经指向 reconciliation/schemas
        if schema_path_config.startswith('/'):
            # 绝对路径，去掉开头的 / 
            schema_path_config = schema_path_config.lstrip('/')
            # 如果包含 schemas/ 前缀，去掉它
            if schema_path_config.startswith('schemas/reconciliation/'):
                schema_path_config = schema_path_config.replace('schemas/reconciliation/', '', 1)
            schema_path = SCHEMA_DIR / schema_path_config
        elif schema_path_config.startswith('schemas/'):
            # 相对路径，去掉 schemas/ 前缀
            schema_path_config = schema_path_config.replace('schemas/reconciliation/', '').replace('schemas/', '')
            schema_path = SCHEMA_DIR / schema_path_config
        else:
            # 只有文件名，与 SCHEMA_DIR 拼接
            schema_path = SCHEMA_DIR / schema_path_config
        
        if not schema_path.exists():
            return {
                "error": f"Schema 文件不存在: {schema_path}",
                "schema_path": schema_path_config
            }
        
        schema = load_json_with_comments(schema_path)
        
        # 5. 验证 schema
        SchemaLoader.validate_schema(schema)
        
        # 6. 验证文件并转换为绝对路径
        absolute_files = []
        for file_path in files:
            # 将相对路径转换为绝对路径
            if file_path.startswith('/uploads/'):
                # 去掉开头的 / 并与 FINANCE_MCP_DIR 拼接（因为 uploads 在 finance-mcp 目录下）
                abs_path = FINANCE_MCP_DIR / file_path.lstrip('/')
            elif file_path.startswith('uploads/'):
                # 相对路径，直接与 FINANCE_MCP_DIR 拼接
                abs_path = FINANCE_MCP_DIR / file_path
            elif str(file_path).startswith(str(UPLOAD_DIR)):
                # 如果已经是 UPLOAD_DIR 的绝对路径
                abs_path = Path(file_path)
            else:
                # 假设是绝对路径或其他格式
                abs_path = Path(file_path)
                # 如果不是绝对路径，尝试相对 UPLOAD_DIR
                if not abs_path.is_absolute():
                    abs_path = UPLOAD_DIR / file_path
            
            if not abs_path.exists():
                return {"error": f"文件不存在: {file_path} (解析路径: {abs_path})"}
            
            absolute_files.append(str(abs_path))
        
        # 7. 创建任务（使用绝对路径，传入 callback_url）
        task_id = await task_manager.create_task(schema, absolute_files, callback_url if callback_url else None)
        
        return {
            "task_id": task_id,
            "status": "pending",
            "message": "对账任务已创建，正在处理中"
        }
    
    except Exception as e:
        return {"error": f"创建任务失败: {str(e)}"}


async def _reconciliation_status(args: Dict) -> Dict:
    """查询任务状态"""
    task_id = args.get("task_id")
    
    task = await task_manager.get_task(task_id)
    if not task:
        return {"error": f"任务不存在: {task_id}"}
    
    return {
        "task_id": task.task_id,
        "status": task.status.value,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat()
    }


async def _reconciliation_result(args: Dict) -> Dict:
    """获取对账结果"""
    task_id = args.get("task_id")
    
    task = await task_manager.get_task(task_id)
    if not task:
        return {"error": f"任务不存在: {task_id}"}
    
    if task.status != "completed" and task.status.value != "completed":
        return {
            "task_id": task.task_id,
            "status": task.status.value,
            "message": "任务尚未完成"
        }
    
    if task.result:
        return task.result.to_dict()
    else:
        return {"error": "结果不可用"}


async def _reconciliation_list_tasks(args: Dict) -> Dict:
    """列出所有任务"""
    tasks = await task_manager.list_tasks()
    
    return {
        "tasks": [
            {
                "task_id": task.task_id,
                "status": task.status.value,
                "created_at": task.created_at.isoformat(),
                "updated_at": task.updated_at.isoformat()
            }
            for task in tasks
        ]
    }


async def _file_upload(args: Dict) -> Dict:
    """接收文件并保存（支持多文件，content 为 base64 编码）"""
    try:
        import base64
        from datetime import datetime
        import chardet
        
        files = args.get("files", [])
        if not files:
            return {"error": "files 参数不能为空"}
        
        uploaded_files = []
        errors = []
        
        # 创建按日期分类的上传目录
        now = datetime.now()
        date_dir = UPLOAD_DIR / str(now.year) / str(now.month) / str(now.day)
        date_dir.mkdir(parents=True, exist_ok=True)
        
        for idx, file_obj in enumerate(files):
            try:
                # 提取文件信息
                filename = file_obj.get("filename")
                content_b64 = file_obj.get("content")
                
                # 验证必填字段
                if not filename:
                    errors.append({
                        "index": idx,
                        "error": "缺少 filename 字段"
                    })
                    continue
                
                if not content_b64:
                    errors.append({
                        "index": idx,
                        "filename": filename,
                        "error": "缺少 content 字段"
                    })
                    continue
                
                # 验证文件扩展名
                file_ext = Path(filename).suffix.lower()
                if file_ext not in ALLOWED_EXTENSIONS:
                    errors.append({
                        "index": idx,
                        "filename": filename,
                        "error": f"不支持的文件类型: {file_ext}"
                    })
                    continue
                
                # 解码 base64
                try:
                    file_content = base64.b64decode(content_b64)
                except Exception as e:
                    errors.append({
                        "index": idx,
                        "filename": filename,
                        "error": f"base64 解码失败: {str(e)}"
                    })
                    continue
                
                # 保存文件到日期目录
                safe_filename = Path(filename).name  # 只取文件名，去除路径
                file_path = date_dir / safe_filename
                
                # 如果文件已存在，添加时间戳
                if file_path.exists():
                    timestamp = datetime.now().strftime("%H%M%S")
                    name_parts = safe_filename.rsplit('.', 1)
                    if len(name_parts) == 2:
                        safe_filename = f"{name_parts[0]}_{timestamp}.{name_parts[1]}"
                    else:
                        safe_filename = f"{safe_filename}_{timestamp}"
                    file_path = date_dir / safe_filename
                
                # 对文本文件（CSV、TXT）进行编码转换，确保保存为 UTF-8
                text_extensions = ['.csv', '.txt', '.tsv']
                if file_ext in text_extensions:
                    try:
                        logger.info(f"[编码转换] 开始处理文件: {filename}")
                        logger.info(f"[编码转换] 文件扩展名: {file_ext}")
                        logger.info(f"[编码转换] 原始文件大小: {len(file_content)} 字节")
                        
                        # 检测原始编码
                        detected = chardet.detect(file_content)
                        encoding = detected.get('encoding', 'utf-8')
                        confidence = detected.get('confidence', 0)
                        
                        logger.info(f"[编码转换] 检测到编码: {encoding}, 置信度: {confidence:.2%}")
                        
                        # 如果检测不出编码或置信度低，尝试常见编码
                        if not encoding or confidence < 0.7:
                            logger.info(f"[编码转换] 置信度低，尝试常见编码...")
                            for try_encoding in ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin1']:
                                try:
                                    file_content.decode(try_encoding)
                                    encoding = try_encoding
                                    logger.info(f"[编码转换] 使用编码: {encoding}")
                                    break
                                except (UnicodeDecodeError, LookupError):
                                    continue
                        
                        # 解码后重新编码为 UTF-8 保存
                        if encoding:
                            try:
                                text_content = file_content.decode(encoding)
                                file_content = text_content.encode('utf-8-sig')  # 使用 UTF-8 with BOM
                                logger.info(f"[编码转换] ✅ 成功转换: {encoding} → UTF-8-sig")
                                logger.info(f"[编码转换] 转换后大小: {len(file_content)} 字节")
                            except (UnicodeDecodeError, LookupError) as e:
                                # 如果解码失败，保持原样
                                logger.error(f"[编码转换] ❌ 解码失败: {str(e)}")
                        else:
                            logger.warning(f"[编码转换] ⚠️ 未检测到编码，保持原样")
                    except Exception as e:
                        # 编码转换失败，保持原样
                        logger.error(f"[编码转换] ❌ 转换异常 ({filename}): {str(e)}")
                
                # 保存文件
                with open(file_path, 'wb') as f:
                    f.write(file_content)
                
                # 构建相对路径（相对于 UPLOAD_DIR）
                relative_path = file_path.relative_to(UPLOAD_DIR.parent)
                
                # 添加到成功列表
                uploaded_files.append({
                    "original_filename": filename,
                    "file_path": f"/{relative_path.as_posix()}"
                })
            
            except Exception as e:
                errors.append({
                    "index": idx,
                    "filename": file_obj.get("filename", "unknown"),
                    "error": f"处理失败: {str(e)}"
                })
        
        # 返回结果
        if not uploaded_files:
            return {
                "success": False,
                "uploaded_count": 0,
                "uploaded_files": [],
                "errors": errors
            }
        
        result = {
            "success": True,
            "uploaded_count": len(uploaded_files),
            "uploaded_files": uploaded_files
        }
        
        if errors:
            result["errors"] = errors
            result["error_count"] = len(errors)
        
        return result
    
    except Exception as e:
        return {"error": f"文件上传失败: {str(e)}"}


def _guess_file_extension(content: bytes) -> str:
    """根据文件内容推断文件扩展名"""
    # 检查文件头（魔术数字）
    if len(content) < 4:
        return ".csv"  # 默认为 CSV
    
    # Excel (xlsx) - PK\x03\x04
    if content[:4] == b'PK\x03\x04':
        # 进一步检查是否是 xlsx
        if b'xl/' in content[:2000] or b'[Content_Types].xml' in content[:2000]:
            return ".xlsx"
        return ".xlsx"  # 默认为 xlsx
    
    # Excel (xls) - D0CF11E0A1B11AE1
    if len(content) >= 8 and content[:8] == b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1':
        return ".xls"
    
    # CSV - 尝试检测是否是文本（检查更多内容）
    try:
        # 尝试解码前 5000 字节
        test_content = content[:5000]
        decoded = test_content.decode('utf-8')
        # 检查是否包含常见的 CSV 特征
        if ',' in decoded or '\t' in decoded or '\n' in decoded:
            return ".csv"
        return ".txt"
    except:
        try:
            test_content = content[:5000]
            decoded = test_content.decode('gbk')
            if ',' in decoded or '\t' in decoded or '\n' in decoded:
                return ".csv"
            return ".txt"
        except:
            pass
    
    # 默认返回 CSV（因为对账系统主要处理 CSV/Excel）
    return ".csv"



async def _get_reconciliation(args: Dict) -> Dict:
    """根据对账类型获取对账配置"""
    try:
        reconciliation_type = args.get("reconciliation_type")
        
        if not reconciliation_type:
            return {
                "schema": {},
                "callback_url": "",
                "error": "缺少 reconciliation_type 参数"
            }
        
        # 读取配置文件
        if not RECONCILIATION_SCHEMAS_FILE.exists():
            return {
                "schema": {},
                "callback_url": "",
                "error": f"配置文件不存在: {RECONCILIATION_SCHEMAS_FILE}"
            }
        
        config = load_json_with_comments(RECONCILIATION_SCHEMAS_FILE)
        
        # 查找匹配的类型
        types = config.get("types", [])
        matched_type = None
        
        for type_config in types:
            if type_config.get("name_cn") == reconciliation_type:
                matched_type = type_config
                break
        
        if not matched_type:
            # 没有匹配到，返回空结构
            return {
                "schema": {},
                "callback_url": ""
            }
        
        # 获取 schema_path 和 callback_url
        schema_path_config = matched_type.get("schema_path")
        callback_url = matched_type.get("callback_url", "")
        type_key = matched_type.get("type_key")
        
        if not schema_path_config:
            return {
                "schema": {},
                "callback_url": callback_url,
                "error": f"配置缺少 schema_path: {reconciliation_type}"
            }
        
        # 读取 schema 文件
        # schema_path 格式: /schemas/direct_sales_schema.json 或 schemas/direct_sales_schema.json
        if schema_path_config.startswith('/'):
            # 绝对路径，去掉开头的 / 并与 BASE_DIR 拼接
            schema_path = BASE_DIR / schema_path_config.lstrip('/')
        elif schema_path_config.startswith('schemas/'):
            # 相对路径，与 BASE_DIR 拼接
            schema_path = BASE_DIR / schema_path_config
        else:
            # 只有文件名，与 SCHEMA_DIR 拼接
            schema_path = SCHEMA_DIR / schema_path_config
        
        if not schema_path.exists():
            return {
                "schema": {},
                "callback_url": callback_url,
                "error": f"Schema 文件不存在: {schema_path}"
            }
        
        schema = load_json_with_comments(schema_path)
        
        # 返回新的结构：schema 和 callback_url 分离
        return {
            "schema": schema,
            "callback_url": callback_url
        }
    
    except Exception as e:
        return {
            "schema": {},
            "callback_url": "",
            "error": f"获取对账配置失败: {str(e)}"
        }


async def _analyze_files(args: Dict) -> Dict:
    """分析已上传的文件，返回文件列信息、行数、样本数据和文件类型判断"""
    try:
        import pandas as pd
        import chardet
        import json
        import os
        from langchain_openai import ChatOpenAI
        
        file_paths = args.get("file_paths", [])
        if not file_paths:
            return {"error": "file_paths 参数不能为空"}
        
        analyses = []
        
        # 第一步：读取每个文件的基本信息
        for file_path in file_paths:
            # 转换为绝对路径
            if file_path.startswith("/"):
                full_path = FINANCE_MCP_DIR / file_path.lstrip("/")
            else:
                full_path = FINANCE_MCP_DIR / file_path
            
            # 验证文件是否存在
            if not full_path.exists():
                analyses.append({
                    "filename": Path(file_path).name,
                    "file_path": file_path,
                    "error": f"文件不存在: {file_path}"
                })
                continue
            
            # 验证文件扩展名
            file_ext = full_path.suffix.lower()
            if file_ext not in ALLOWED_EXTENSIONS:
                analyses.append({
                    "filename": full_path.name,
                    "file_path": file_path,
                    "error": f"不支持的文件类型: {file_ext}"
                })
                continue
            
            # 读取文件
            try:
                if file_ext == ".csv":
                    # CSV 文件，检测编码
                    raw = full_path.read_bytes()
                    det = chardet.detect(raw[:10000])
                    enc = det.get("encoding") or "utf-8"
                    df = pd.read_csv(full_path, encoding=enc, index_col=False)
                else:
                    # Excel 文件
                    df = pd.read_excel(full_path, index_col=False)
                
                # 提取样本数据
                sample = df.head(5).fillna("").to_dict(orient="records")
                safe_sample = []
                for row in sample:
                    safe_sample.append({k: str(v) for k, v in row.items()})
                
                # 从文件路径中提取原始文件名（去掉时间戳后缀）
                # 例如：filename_163045.csv → filename.csv
                original_name = full_path.name
                # 检查是否有时间戳后缀（格式：_HHMMSS）
                import re
                match = re.match(r'(.+)_(\d{6})(\.\w+)$', original_name)
                if match:
                    original_name = match.group(1) + match.group(3)
                
                analyses.append({
                    "filename": full_path.name,  # 系统文件名（带时间戳）
                    "original_filename": original_name,  # 原始文件名（不带时间戳）
                    "file_path": file_path,
                    "columns": list(df.columns),
                    "row_count": len(df),
                    "sample_data": safe_sample,
                    "guessed_source": None  # 稍后由 LLM 填充
                })
                
            except Exception as e:
                analyses.append({
                    "filename": full_path.name,
                    "file_path": file_path,
                    "error": f"文件读取失败: {str(e)}"
                })
        
        # 第二步：使用 LLM 判断文件类型
        valid_analyses = [a for a in analyses if "error" not in a]
        if valid_analyses:
            try:
                # 构建 prompt
                files_desc = []
                for i, a in enumerate(valid_analyses):
                    cols_str = ", ".join(a.get("columns", [])[:20])
                    sample_str = ""
                    for row in a.get("sample_data", [])[:2]:
                        sample_str += "    " + str(row) + "\n"
                    files_desc.append(
                        f"文件{i+1}: {a['filename']}\n"
                        f"  列名: {cols_str}\n"
                        f"  行数: {a.get('row_count', 0)}\n"
                        f"  示例数据:\n{sample_str}"
                    )
                
                prompt = (
                    "你是一个财务数据分析专家。以下是用户上传的文件信息，"
                    "请判断每个文件属于哪种数据源类型。\n\n"
                    "类型说明：\n"
                    "- business: 业务数据（如订单流水、销售记录、交易明细等，通常包含订单号、商品、销售额等字段）\n"
                    "- finance: 财务数据（如财务账单、对账单、银行流水、发票等，通常包含财务科目、借贷金额等字段）\n\n"
                    + "\n".join(files_desc)
                    + "\n\n请严格按以下 JSON 格式回复，不要添加其他内容：\n"
                    '{"results": [{"filename": "文件名", "source": "business 或 finance", "reason": "简短理由"}]}'
                )
                
                # 调用 LLM（使用环境变量配置）
                llm_provider = os.getenv("LLM_PROVIDER", "deepseek").lower()
                
                if llm_provider == "deepseek":
                    api_key = os.getenv("DEEPSEEK_API_KEY", "")
                    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
                    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
                elif llm_provider == "qwen":
                    api_key = os.getenv("QWEN_API_KEY", "")
                    base_url = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
                    model = os.getenv("QWEN_MODEL", "qwen-plus")
                else:  # openai
                    api_key = os.getenv("OPENAI_API_KEY", "")
                    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
                    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
                
                if not api_key:
                    logger.warning(f"LLM API Key 未配置 ({llm_provider})，跳过文件类型判断")
                    return {
                        "success": True,
                        "analyses": analyses
                    }
                
                llm = ChatOpenAI(
                    temperature=0.1,
                    model=model,
                    api_key=api_key,
                    base_url=base_url
                )
                resp = llm.invoke(prompt)
                content = resp.content.strip()
                
                # 提取 JSON
                if "```" in content:
                    import re
                    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
                    if m:
                        content = m.group(1)
                
                parsed = json.loads(content)
                results = parsed.get("results", [])
                
                # 将结果写回 analyses
                result_map = {r["filename"]: {"source": r["source"], "reason": r.get("reason", "")} for r in results}
                for a in valid_analyses:
                    if a["filename"] in result_map:
                        a["guessed_source"] = result_map[a["filename"]]["source"]
                        a["source_reason"] = result_map[a["filename"]]["reason"]
            
            except Exception as e:
                logger.warning(f"LLM 文件类型判断失败: {e}")
                # 不影响主流程，只是 guessed_source 为 None
        
        return {
            "success": True,
            "analyses": analyses
        }
    
    except Exception as e:
        logger.error(f"文件分析失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"文件分析失败: {str(e)}"
        }

# 注意：数据库操作工具（list/save/update/delete_reconciliation_rule）
# 已移至 auth/tools.py，由认证模块统一管理
