# 文件上传工具使用指南

## ✅ 优化完成

`file_upload` 工具已经优化，支持更灵活的文件上传方式。

## 🎯 新功能特性

### 1. **支持多文件上传**
一次可以上传多个文件

### 2. **文件名可选**
- 如果提供 `filename`，直接使用
- 如果不提供，会尝试从 `file_object.name` 中获取
- 如果都没有，会自动推断文件扩展名并生成文件名

### 3. **支持两种数据格式**
- **base64 字符串** (`content`)
- **文件对象** (`file_object`)

### 4. **智能文件类型推断**
根据文件内容的魔术数字自动识别：
- Excel (xlsx): `PK\x03\x04` 开头
- Excel (xls): `D0CF11E0A1B11AE1` 开头
- CSV: 文本格式，包含逗号、制表符或换行符

### 5. **详细的错误处理**
- 每个文件独立处理
- 失败的文件不影响其他文件
- 返回详细的成功和错误信息

## 📝 工具定义

```json
{
  "name": "file_upload",
  "description": "上传文件到服务器，支持单个或多个文件上传。返回上传文件的路径列表。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "files": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "filename": {
              "type": "string",
              "description": "文件名（可选）"
            },
            "content": {
              "type": "string",
              "description": "文件内容（base64 编码，与 file_object 二选一）"
            },
            "file_object": {
              "type": "object",
              "description": "文件对象（与 content 二选一）"
            }
          }
        }
      }
    },
    "required": ["files"]
  }
}
```

## 🔧 使用示例

### 示例 1: 单文件上传（提供文件名）

```json
{
  "tool": "file_upload",
  "arguments": {
    "files": [
      {
        "filename": "业务流水.csv",
        "content": "5Zui5Y+3LGph6YeMLOaXpeacnw..."
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
  "error_count": 0,
  "uploaded_files": [
    {
      "index": 0,
      "original_filename": "业务流水.csv",
      "saved_filename": "f29d970c_业务流水.csv",
      "file_path": "/path/to/uploads/f29d970c_业务流水.csv",
      "file_size": 213557
    }
  ]
}
```

### 示例 2: 多文件上传

```json
{
  "tool": "file_upload",
  "arguments": {
    "files": [
      {
        "filename": "业务流水.csv",
        "content": "base64_content_1"
      },
      {
        "filename": "财务流水.xlsx",
        "content": "base64_content_2"
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
      "saved_filename": "f29d970c_业务流水.csv",
      "file_path": "/path/to/f29d970c_业务流水.csv",
      "file_size": 213557
    },
    {
      "index": 1,
      "original_filename": "财务流水.xlsx",
      "saved_filename": "cd3dae0d_财务流水.xlsx",
      "file_path": "/path/to/cd3dae0d_财务流水.xlsx",
      "file_size": 130896
    }
  ]
}
```

### 示例 3: 不提供文件名（自动推断）

```json
{
  "tool": "file_upload",
  "arguments": {
    "files": [
      {
        "content": "base64_content"
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
  "error_count": 0,
  "uploaded_files": [
    {
      "index": 0,
      "original_filename": "upload_1.csv",
      "saved_filename": "a1b2c3d4_upload_1.csv",
      "file_path": "/path/to/a1b2c3d4_upload_1.csv",
      "file_size": 213557
    }
  ]
}
```

### 示例 4: 使用 file_object

```json
{
  "tool": "file_upload",
  "arguments": {
    "files": [
      {
        "file_object": {
          "name": "对账数据.csv",
          "data": "base64_content"
        }
      }
    ]
  }
}
```

### 示例 5: 混合上传（base64 + file_object）

```json
{
  "tool": "file_upload",
  "arguments": {
    "files": [
      {
        "filename": "文件1.csv",
        "content": "base64_content_1"
      },
      {
        "file_object": {
          "name": "文件2.xlsx",
          "data": "base64_content_2"
        }
      }
    ]
  }
}
```

## ⚠️ 错误处理

### 错误类型 1: content 和 file_object 都为空

```json
{
  "tool": "file_upload",
  "arguments": {
    "files": [
      {
        "filename": "空文件.csv"
      }
    ]
  }
}
```

**返回值**:
```json
{
  "success": false,
  "uploaded_count": 0,
  "error_count": 1,
  "uploaded_files": [],
  "errors": [
    {
      "index": 0,
      "error": "content 和 file_object 不能都为空"
    }
  ]
}
```

### 错误类型 2: 不支持的文件类型

```json
{
  "tool": "file_upload",
  "arguments": {
    "files": [
      {
        "filename": "病毒.exe",
        "content": "base64_content"
      }
    ]
  }
}
```

**返回值**:
```json
{
  "success": false,
  "uploaded_count": 0,
  "error_count": 1,
  "uploaded_files": [],
  "errors": [
    {
      "index": 0,
      "filename": "病毒.exe",
      "error": "不支持的文件类型: .exe"
    }
  ]
}
```

### 错误类型 3: 部分成功

```json
{
  "tool": "file_upload",
  "arguments": {
    "files": [
      {
        "filename": "正常文件.csv",
        "content": "base64_content_1"
      },
      {
        "filename": "错误文件.exe",
        "content": "base64_content_2"
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
  "error_count": 1,
  "uploaded_files": [
    {
      "index": 0,
      "original_filename": "正常文件.csv",
      "saved_filename": "abc123_正常文件.csv",
      "file_path": "/path/to/abc123_正常文件.csv",
      "file_size": 12345
    }
  ],
  "errors": [
    {
      "index": 1,
      "filename": "错误文件.exe",
      "error": "不支持的文件类型: .exe"
    }
  ]
}
```

## 📋 支持的文件类型

- `.csv` - CSV 文件
- `.xlsx` - Excel 2007+ 文件
- `.xls` - Excel 97-2003 文件

## 🔐 安全特性

1. **文件类型验证**: 只允许上传 CSV 和 Excel 文件
2. **文件名清理**: 自动去除路径，只保留文件名
3. **唯一文件名**: 使用 UUID 前缀避免文件名冲突
4. **文件大小**: 受配置限制（默认 100MB）

## 🎯 在对账流程中使用

### 完整的对账流程

```python
# 步骤 1: 上传文件
upload_result = await call_tool("file_upload", {
    "files": [
        {
            "filename": "业务流水.csv",
            "content": business_file_base64
        },
        {
            "filename": "财务流水.xlsx",
            "content": finance_file_base64
        }
    ]
})

# 提取文件路径
file_paths = [f["file_path"] for f in upload_result["uploaded_files"]]

# 步骤 2: 开始对账
reconciliation_result = await call_tool("reconciliation_start", {
    "schema": {
        # ... schema 配置
    },
    "files": file_paths
})

# 步骤 3: 获取结果
task_id = reconciliation_result["task_id"]
result = await call_tool("reconciliation_result", {
    "task_id": task_id
})
```

## 💡 最佳实践

1. **提供文件名**: 虽然文件名可选，但建议提供以便识别
2. **批量上传**: 一次上传所有需要的文件，减少请求次数
3. **错误检查**: 检查返回的 `success` 和 `errors` 字段
4. **保存路径**: 保存返回的 `file_path` 用于后续对账

## 🔄 与旧版本的兼容性

**旧版本**（已废弃）:
```json
{
  "filename": "文件.csv",
  "content": "base64_content"
}
```

**新版本**（推荐）:
```json
{
  "files": [
    {
      "filename": "文件.csv",
      "content": "base64_content"
    }
  ]
}
```

---

**更新时间**: 2026-01-06  
**版本**: 2.0  
**状态**: ✅ 已优化并测试通过

