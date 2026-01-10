# file_upload 工具 - Dify 集成版

## ✅ 优化说明

`file_upload` 工具已优化为直接从 Dify API 下载文件，无需手动处理 base64 编码。

## 📋 新格式

### 请求格式

```json
{
  "files": [
    {
      "filename": "2025-12-01~2025-12-01对账流水.csv",
      "size": 656084,
      "related_id": "81d354ee-aeff-48ec-8f85-18c4fee306c6",
      "mime_type": "text/csv"
    }
  ],
  "count": 1
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `filename` | string | ✅ | 文件名（含扩展名） |
| `related_id` | string | ✅ | Dify 文件 ID |
| `size` | number | ❌ | 文件大小（字节） |
| `mime_type` | string | ❌ | MIME 类型 |
| `count` | number | ❌ | 文件数量（顶层字段） |

### 返回格式

```json
{
  "success": true,
  "uploaded_count": 1,
  "uploaded_files": [
    {
      "original_filename": "2025-12-01~2025-12-01对账流水.csv",
      "file_path": "/uploads/2026/1/6/2025-12-01~2025-12-01对账流水.csv"
    }
  ]
}
```

## 🔧 工作原理

### 1. 文件下载

工具会从 Dify API 下载文件：

```
GET http://localhost/v1/files/{related_id}/preview
Authorization: Bearer app-pffBjBphPBhbrSwz8mxku2R3
```

### 2. 文件保存

文件按日期目录保存：

```
/uploads/2026/1/6/文件名.csv
         ^^^^ ^ ^
         年   月 日
```

### 3. 路径返回

返回相对路径，用于后续对账：

```
/uploads/2026/1/6/2025-12-01~2025-12-01对账流水.csv
```

## 📊 配置常量

在 `mcp_server/tools.py` 中：

```python
# Dify API 配置
DIFY_BASE_URL = "http://localhost"
DIFY_API_TOKEN = "app-pffBjBphPBhbrSwz8mxku2R3"
```

**重要**: 根据您的实际环境修改这些值！

### 常见配置

| 环境 | DIFY_BASE_URL | 说明 |
|------|---------------|------|
| Docker 本地 | `http://localhost` | 默认配置 |
| Docker Compose | `http://dify-api` | 容器间通信 |
| 自定义端口 | `http://localhost:5001` | 指定端口 |
| 云服务器 | `http://your-ip:5001` | 公网地址 |

## 🎯 Dify 工作流配置

### 方案 1: 直接使用（推荐）

Dify 文件上传后，直接调用 MCP 工具：

```
1. 用户上传文件 → sys.files

2. 代码节点: 提取文件信息
   输入: sys
   输出: {
     "files": [
       {
         "filename": sys.files[0].filename,
         "related_id": sys.files[0].related_id,
         "size": sys.files[0].size,
         "mime_type": sys.files[0].mime_type
       }
     ],
     "count": sys.files.length
   }

3. MCP 工具: file_upload
   参数: {{代码节点.output}}

4. MCP 工具: reconciliation_start
   参数: {
     "schema": {...},
     "files": {{file_upload.uploaded_files[*].file_path}}
   }
```

### 方案 2: 使用代码节点转换

如果需要更灵活的处理，可以使用代码节点：

```python
def main(sys):
    """从 Dify sys.files 提取信息"""
    sys_files = sys.get("files", [])
    
    if not sys_files:
        return {"files": [], "count": 0}
    
    files = []
    for file_obj in sys_files:
        files.append({
            "filename": file_obj.get("filename"),
            "related_id": file_obj.get("related_id"),
            "size": file_obj.get("size", 0),
            "mime_type": file_obj.get("mime_type", "text/csv")
        })
    
    return {
        "files": files,
        "count": len(files)
    }
```

## 📝 完整示例

### 输入（Dify sys.files）

```json
{
  "sys.files": [
    {
      "dify_model_identity": "__dify__file__",
      "extension": ".csv",
      "filename": "2025-12-01~2025-12-01对账流水.csv",
      "id": null,
      "mime_type": "text/csv",
      "related_id": "81d354ee-aeff-48ec-8f85-18c4fee306c6",
      "remote_url": "/files/81d354ee-aeff-48ec-8f85-18c4fee306c6/file-preview?...",
      "size": 656084,
      "tenant_id": "f42ef5f9-ef49-4e41-af26-d2a5f84f9bac",
      "transfer_method": "local_file",
      "type": "document",
      "url": "/files/81d354ee-aeff-48ec-8f85-18c4fee306c6/file-preview?..."
    }
  ]
}
```

### 转换后（传给 file_upload）

```json
{
  "files": [
    {
      "filename": "2025-12-01~2025-12-01对账流水.csv",
      "size": 656084,
      "related_id": "81d354ee-aeff-48ec-8f85-18c4fee306c6",
      "mime_type": "text/csv"
    }
  ],
  "count": 1
}
```

### 返回（file_upload 结果）

```json
{
  "success": true,
  "uploaded_count": 1,
  "uploaded_files": [
    {
      "original_filename": "2025-12-01~2025-12-01对账流水.csv",
      "file_path": "/uploads/2026/1/6/2025-12-01~2025-12-01对账流水.csv"
    }
  ]
}
```

## 🔍 错误处理

### 常见错误

#### 1. 下载文件失败 (HTTP 404)

```json
{
  "success": false,
  "errors": [
    {
      "index": 0,
      "filename": "test.csv",
      "error": "下载文件失败: HTTP 404"
    }
  ]
}
```

**原因**: 
- `related_id` 不正确
- 文件已过期或被删除
- Dify API 地址错误

**解决**: 
- 检查 `related_id` 是否正确
- 确认 `DIFY_BASE_URL` 配置正确
- 验证 API token 是否有效

#### 2. 认证失败 (HTTP 401)

```json
{
  "error": "下载文件失败: HTTP 401"
}
```

**原因**: API token 不正确或已失效

**解决**: 更新 `DIFY_API_TOKEN` 常量

#### 3. 不支持的文件类型

```json
{
  "errors": [
    {
      "filename": "test.exe",
      "error": "不支持的文件类型: .exe"
    }
  ]
}
```

**支持的文件类型**: `.csv`, `.xlsx`, `.xls`

#### 4. 缺少必填字段

```json
{
  "errors": [
    {
      "index": 0,
      "error": "缺少 filename 字段"
    }
  ]
}
```

**解决**: 确保提供 `filename` 和 `related_id`

## ⚙️ 高级配置

### 修改 Dify 配置

编辑 `reconciliation/mcp_server/tools.py`:

```python
async def _file_upload(args: Dict) -> Dict:
    """从 Dify 下载文件并保存（支持多文件）"""
    try:
        import httpx
        from datetime import datetime
        
        # 🔧 在这里修改配置
        DIFY_BASE_URL = "http://your-dify-server"
        DIFY_API_TOKEN = "your-api-token"
        
        # ... 其余代码
```

### 自定义保存路径

如果需要修改保存路径格式，编辑：

```python
# 当前格式: /uploads/2026/1/6/文件名.csv
date_dir = UPLOAD_DIR / str(now.year) / str(now.month) / str(now.day)

# 自定义格式: /uploads/2026-01-06/文件名.csv
date_dir = UPLOAD_DIR / now.strftime("%Y-%m-%d")

# 自定义格式: /uploads/202601/文件名.csv
date_dir = UPLOAD_DIR / now.strftime("%Y%m")
```

## 🧪 测试

运行测试脚本：

```bash
cd /Users/kevin/workspace/financial-ai/reconciliation
source ../.venv/bin/activate
python test_file_upload_dify.py
```

## 📚 相关文档

- Dify 文件 API: https://docs.dify.ai/api/files
- MCP 服务器配置: `DIFY_SETUP.md`
- 对账流程: `README.md`

## 🆚 版本对比

### v4.0 (Base64 版本)

```json
{
  "files": [{
    "filename": "test.csv",
    "base64": "long_base64_string...",
    "size": 656084,
    "type": "text/csv"
  }]
}
```

**优点**: 不依赖外部 API  
**缺点**: 需要手动编码，传输体积大

### v5.0 (Dify API 版本) ⭐ 当前

```json
{
  "files": [{
    "filename": "test.csv",
    "related_id": "file-id",
    "size": 656084,
    "mime_type": "text/csv"
  }]
}
```

**优点**: 
- 无需 base64 编码
- 传输体积小
- 直接集成 Dify
- 按日期自动分类

**缺点**: 依赖 Dify API

---

**更新时间**: 2026-01-06  
**版本**: 5.0  
**状态**: ✅ 已优化并测试通过

