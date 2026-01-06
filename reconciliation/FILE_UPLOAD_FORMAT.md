# 文件上传格式说明

## ✅ 支持的标准格式

根据用户要求，`file_upload` 工具现在完美支持以下格式：

```json
{
  "files": [
    {
      "filename": "业务流水.csv",
      "size": 213557,
      "base64": "5Zui5Y+3LGph6YeMLOaXpeacnw...",
      "type": "text/csv"
    },
    {
      "filename": "财务流水.xlsx",
      "size": 130896,
      "base64": "UEsDBBQABgAIAAAAIQBi7p1o...",
      "type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    }
  ]
}
```

## 📋 字段说明

### 必填字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `filename` | string | 文件名（包含扩展名） |
| `base64` | string | base64 编码的文件内容 |

### 可选字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `size` | number | 文件大小（字节数），用于验证 |
| `type` | string | MIME 类型，如 "text/csv" 或 "application/octet-stream" |

## 🔍 字段识别优先级

代码会自动识别多种字段名：

### 文件名字段（按优先级）
1. `filename` ⭐ 推荐
2. `name`
3. `file_name`
4. `fileName`

### 数据字段（按优先级）
1. `base64` ⭐ 推荐
2. `data`
3. `content`
4. `blob`
5. `buffer`

### MIME 类型字段（按优先级）
1. `type` ⭐ 推荐
2. `mimeType`
3. `mime_type`

## 📊 返回值

### 成功响应

```json
{
  "success": true,
  "uploaded_count": 2,
  "error_count": 0,
  "uploaded_files": [
    {
      "index": 0,
      "original_filename": "业务流水.csv",
      "saved_filename": "b298c56c_业务流水.csv",
      "file_path": "/path/to/uploads/b298c56c_业务流水.csv",
      "file_size": 213557,
      "mime_type": "text/csv",
      "size_provided": 213557
    },
    {
      "index": 1,
      "original_filename": "财务流水.xlsx",
      "saved_filename": "369ca566_财务流水.xlsx",
      "file_path": "/path/to/uploads/369ca566_财务流水.xlsx",
      "file_size": 130896,
      "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "size_provided": 130896
    }
  ]
}
```

### 大小不一致警告

如果提供的 `size` 与实际解码后的大小不一致（差异超过100字节），会返回警告：

```json
{
  "uploaded_files": [
    {
      "original_filename": "文件.csv",
      "file_size": 213557,
      "size_provided": 1024,
      "size_warning": "提供的大小 1024 与实际大小 213557 不一致"
    }
  ]
}
```

### 错误响应

```json
{
  "success": false,
  "uploaded_count": 0,
  "error_count": 1,
  "uploaded_files": [],
  "errors": [
    {
      "index": 0,
      "error": "文件对象中缺少数据字段（base64/data/content/blob/buffer）"
    }
  ]
}
```

## 🎯 使用示例

### 示例 1: 标准格式上传

```python
import base64

# 读取文件
with open("业务流水.csv", "rb") as f:
    file_content = f.read()
    file_size = len(file_content)
    base64_content = base64.b64encode(file_content).decode('utf-8')

# 调用 MCP 工具
result = await call_tool("file_upload", {
    "files": [
        {
            "filename": "业务流水.csv",
            "size": file_size,
            "base64": base64_content,
            "type": "text/csv"
        }
    ]
})

# 检查结果
if result["success"]:
    file_path = result["uploaded_files"][0]["file_path"]
    print(f"文件已上传: {file_path}")
```

### 示例 2: 批量上传

```python
files_to_upload = []

for file_path in ["业务流水.csv", "财务流水.xlsx"]:
    with open(file_path, "rb") as f:
        content = f.read()
        files_to_upload.append({
            "filename": file_path,
            "size": len(content),
            "base64": base64.b64encode(content).decode('utf-8'),
            "type": "text/csv" if file_path.endswith(".csv") else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        })

result = await call_tool("file_upload", {
    "files": files_to_upload
})
```

### 示例 3: 简化版（只传必填字段）

```python
result = await call_tool("file_upload", {
    "files": [
        {
            "filename": "简单文件.csv",
            "base64": base64_content
        }
    ]
})
```

## 🔄 兼容性

### 新格式（v4.0）⭐ 推荐

```json
{
  "filename": "文件.csv",
  "size": 1024,
  "base64": "base64_content",
  "type": "text/csv"
}
```

### 旧格式（仍然支持）

```json
{
  "name": "文件.csv",
  "data": "base64_content"
}
```

```json
{
  "filename": "文件.csv",
  "content": "base64_content"
}
```

所有格式都能正常工作，代码会自动识别！

## 📋 支持的文件类型

- `.csv` - CSV 文件
- `.xlsx` - Excel 2007+ 文件
- `.xls` - Excel 97-2003 文件

## 🔐 安全特性

1. ✅ 文件类型白名单验证
2. ✅ base64 解码验证
3. ✅ 文件大小验证（可选）
4. ✅ 文件名安全处理
5. ✅ UUID 唯一文件名生成

## 💡 最佳实践

1. **使用标准字段名**: `filename` + `base64` + `size` + `type`
2. **提供文件大小**: 用于验证上传完整性
3. **提供 MIME 类型**: 便于系统识别和处理
4. **批量上传**: 一次上传多个文件提高效率
5. **检查返回值**: 验证 `success` 字段和 `size_warning`

## 📝 完整对账流程

```python
# 步骤 1: 读取并编码文件
files_data = []
for file_path in ["业务流水.csv", "财务流水.csv"]:
    with open(file_path, "rb") as f:
        content = f.read()
        files_data.append({
            "filename": Path(file_path).name,
            "size": len(content),
            "base64": base64.b64encode(content).decode('utf-8'),
            "type": "text/csv"
        })

# 步骤 2: 上传文件
upload_result = await call_tool("file_upload", {
    "files": files_data
})

if not upload_result["success"]:
    print("上传失败:", upload_result.get("errors"))
    exit(1)

# 步骤 3: 提取文件路径
file_paths = [f["file_path"] for f in upload_result["uploaded_files"]]

# 步骤 4: 开始对账
reconciliation_result = await call_tool("reconciliation_start", {
    "schema": {
        # ... schema 配置
    },
    "files": file_paths
})

task_id = reconciliation_result["task_id"]

# 步骤 5: 等待完成并获取结果
# ...
```

## ⚠️ 注意事项

1. **文件大小**: base64 编码后的字符串会比原始文件大约增加 33%
2. **大小验证**: 允许 100 字节的误差范围
3. **MIME 类型**: 如果不提供，文件仍然可以上传，但建议提供
4. **字段顺序**: JSON 对象的字段顺序不重要

---

**更新时间**: 2026-01-06  
**版本**: 4.0  
**状态**: ✅ 已优化并测试通过

