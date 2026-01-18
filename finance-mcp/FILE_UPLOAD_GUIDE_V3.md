# 文件上传工具使用指南 v3.0

## ✅ 最新优化（v3.0）

`file_upload` 工具已经简化到最简形式，只需传递 `array[file]` 参数，代码自动从文件对象中提取所有信息。

## 🎯 核心特性

### 1. **极简参数**
只需一个参数：`files: array[file]`

### 2. **智能字段识别**
自动识别多种字段名组合：
- **文件名**: `name`, `filename`, `file_name`, `fileName`
- **文件数据**: `data`, `content`, `blob`, `buffer`
- **MIME类型**: `type`, `mimeType`, `mime_type`

### 3. **灵活的数据格式**
- ✅ base64 字符串
- ✅ 二进制数据（bytes）
- ✅ 自动识别并处理

### 4. **自动推断**
- 如果没有文件名，根据内容自动推断扩展名
- 支持 Excel (xlsx/xls) 和 CSV 格式识别

## 📝 工具定义

```json
{
  "name": "file_upload",
  "description": "上传文件到服务器，支持单个或多个文件上传",
  "inputSchema": {
    "type": "object",
    "properties": {
      "files": {
        "type": "array",
        "description": "文件数组，每个元素是一个文件对象",
        "items": {
          "type": "object",
          "description": "文件对象，自动提取文件名和内容"
        }
      }
    },
    "required": ["files"]
  }
}
```

## 🔧 使用示例

### 示例 1: 标准格式（name + data）⭐ 推荐

```json
{
  "tool": "file_upload",
  "arguments": {
    "files": [
      {
        "name": "业务流水.csv",
        "data": "base64_encoded_content"
      },
      {
        "name": "财务流水.xlsx",
        "data": "base64_encoded_content"
      }
    ]
  }
}
```

**返回值**:
```json
{
  "success": true,
  "uploaded_count": 2,
  "error_count": 0,
  "uploaded_files": [
    {
      "index": 0,
      "original_filename": "业务流水.csv",
      "saved_filename": "7fc3d969_业务流水.csv",
      "file_path": "/path/to/7fc3d969_业务流水.csv",
      "file_size": 213557
    },
    {
      "index": 1,
      "original_filename": "财务流水.xlsx",
      "saved_filename": "587029e3_财务流水.xlsx",
      "file_path": "/path/to/587029e3_财务流水.xlsx",
      "file_size": 130896
    }
  ]
}
```

### 示例 2: 使用 filename + content

```json
{
  "tool": "file_upload",
  "arguments": {
    "files": [
      {
        "filename": "数据文件.csv",
        "content": "base64_encoded_content"
      }
    ]
  }
}
```

### 示例 3: 不提供文件名（自动推断）

```json
{
  "tool": "file_upload",
  "arguments": {
    "files": [
      {
        "data": "base64_encoded_content"
      }
    ]
  }
}
```

**返回值**:
```json
{
  "success": true,
  "uploaded_count": 1,
  "uploaded_files": [
    {
      "original_filename": "upload_1.csv",
      "saved_filename": "78546904_upload_1.csv",
      "file_path": "/path/to/78546904_upload_1.csv",
      "file_size": 213557
    }
  ]
}
```

### 示例 4: 包含 MIME 类型

```json
{
  "tool": "file_upload",
  "arguments": {
    "files": [
      {
        "name": "数据.csv",
        "data": "base64_encoded_content",
        "type": "text/csv"
      }
    ]
  }
}
```

**返回值**:
```json
{
  "uploaded_files": [
    {
      "original_filename": "数据.csv",
      "saved_filename": "5bcc05f8_数据.csv",
      "file_path": "/path/to/5bcc05f8_数据.csv",
      "file_size": 213557,
      "mime_type": "text/csv"
    }
  ]
}
```

### 示例 5: 混合字段名

代码会自动识别各种字段名组合：

```json
{
  "tool": "file_upload",
  "arguments": {
    "files": [
      {
        "fileName": "文件1.csv",
        "blob": "base64_content"
      },
      {
        "file_name": "文件2.csv",
        "buffer": "base64_content"
      }
    ]
  }
}
```

### 示例 6: 二进制数据

```json
{
  "tool": "file_upload",
  "arguments": {
    "files": [
      {
        "name": "二进制文件.csv",
        "data": binary_bytes  // Python bytes 对象
      }
    ]
  }
}
```

## 🔍 支持的字段名

### 文件名字段（优先级从高到低）
1. `name`
2. `filename`
3. `file_name`
4. `fileName`

### 数据字段（优先级从高到低）
1. `data`
2. `content`
3. `blob`
4. `buffer`

### MIME 类型字段（可选）
1. `type`
2. `mimeType`
3. `mime_type`

## ⚠️ 错误处理

### 错误 1: 缺少数据字段

```json
{
  "files": [
    {
      "name": "空文件.csv"
      // 缺少 data/content/blob/buffer
    }
  ]
}
```

**返回值**:
```json
{
  "success": false,
  "uploaded_count": 0,
  "error_count": 1,
  "errors": [
    {
      "index": 0,
      "error": "文件对象中缺少数据字段（data/content/blob/buffer）"
    }
  ]
}
```

### 错误 2: base64 解码失败

```json
{
  "files": [
    {
      "name": "文件.csv",
      "data": "invalid_base64_string!!!"
    }
  ]
}
```

**返回值**:
```json
{
  "success": false,
  "error_count": 1,
  "errors": [
    {
      "index": 0,
      "filename": "文件.csv",
      "error": "base64 解码失败: ..."
    }
  ]
}
```

### 错误 3: 不支持的文件类型

```json
{
  "files": [
    {
      "name": "病毒.exe",
      "data": "base64_content"
    }
  ]
}
```

**返回值**:
```json
{
  "success": false,
  "error_count": 1,
  "errors": [
    {
      "index": 0,
      "filename": "病毒.exe",
      "error": "不支持的文件类型: .exe"
    }
  ]
}
```

## 📋 支持的文件类型

- `.csv` - CSV 文件
- `.xlsx` - Excel 2007+ 文件
- `.xls` - Excel 97-2003 文件

## 🎯 完整对账流程

```python
# 步骤 1: 上传文件（简化版）
upload_result = await call_tool("file_upload", {
    "files": [
        {
            "name": "业务流水.csv",
            "data": business_file_base64
        },
        {
            "name": "财务流水.xlsx",
            "data": finance_file_base64
        }
    ]
})

# 检查上传结果
if not upload_result["success"]:
    print("上传失败:", upload_result.get("errors"))
    return

# 提取文件路径
file_paths = [f["file_path"] for f in upload_result["uploaded_files"]]

# 步骤 2: 开始对账
reconciliation_result = await call_tool("reconciliation_start", {
    "schema": {
        "version": "1.0",
        "data_sources": {...},
        "key_field_role": "order_id",
        ...
    },
    "files": file_paths
})

# 步骤 3: 查询状态
task_id = reconciliation_result["task_id"]
while True:
    status = await call_tool("reconciliation_status", {
        "task_id": task_id
    })
    if status["status"] == "completed":
        break
    await asyncio.sleep(2)

# 步骤 4: 获取结果
result = await call_tool("reconciliation_result", {
    "task_id": task_id
})
print(result)
```

## 🔄 版本对比

| 功能 | v1.0 | v2.0 | v3.0 (当前) |
|------|------|------|------------|
| 文件名参数 | 必填 | 可选 | 自动提取 |
| 多文件上传 | ❌ | ✅ | ✅ |
| base64 支持 | ✅ | ✅ | ✅ |
| 二进制支持 | ❌ | ✅ | ✅ |
| 字段名灵活性 | 固定 | 部分灵活 | 完全灵活 |
| 自动类型推断 | ❌ | ✅ | ✅ 增强 |
| MIME 类型 | ❌ | ❌ | ✅ |

**v1.0 (已废弃)**:
```json
{"filename": "必填", "content": "必填"}
```

**v2.0 (已废弃)**:
```json
{"files": [{"filename": "可选", "content": "必填", "file_object": "可选"}]}
```

**v3.0 (当前) ⭐**:
```json
{"files": [{"name": "可选", "data": "必填"}]}
```

## 💡 最佳实践

1. **使用标准字段名**: `name` + `data` 是最推荐的组合
2. **提供文件名**: 虽然可以自动推断，但提供文件名更明确
3. **批量上传**: 一次上传所有文件，减少请求次数
4. **检查返回值**: 务必检查 `success` 和 `errors` 字段
5. **保存文件路径**: 返回的 `file_path` 用于后续对账

## 🔐 安全特性

1. ✅ 文件类型白名单（仅 CSV/Excel）
2. ✅ 文件名安全处理（去除路径）
3. ✅ 唯一文件名生成（UUID 前缀）
4. ✅ 文件大小限制（默认 100MB）
5. ✅ base64 解码验证
6. ✅ 二进制数据支持

## ✅ 测试验证

所有测试场景均通过：
- ✅ 标准格式 (name + data)
- ✅ 其他字段名 (filename + content)
- ✅ 自动推断文件名
- ✅ 包含 MIME 类型
- ✅ 混合字段名 (fileName + blob)
- ✅ 二进制数据 (bytes)
- ✅ 错误处理（缺少数据字段）

---

**更新时间**: 2026-01-06  
**版本**: 3.0  
**状态**: ✅ 已优化并测试通过

