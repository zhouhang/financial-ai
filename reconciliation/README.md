# Reconciliation MCP Server

基于 Schema 配置驱动的通用对账系统，支持通过 MCP 协议进行文件对账。

## 功能特性

### 🎯 核心功能

1. **Schema 配置驱动** - 无需修改代码，仅通过 JSON schema 配置即可实现新的对账逻辑
2. **异步任务处理** - 支持长时间运行的对账任务，不阻塞主线程
3. **智能文件匹配** - 根据正则表达式自动分类上传的文件到 business/finance
4. **灵活字段映射** - 统一不同数据源的字段名称
5. **数据清洗规则** - 支持求和、单位转换、日期格式化等
6. **自定义验证** - 通过表达式定义业务规则
7. **回调通知** - 任务完成后自动回调指定地址

### 🛠️ 可用工具

| 工具名称 | 描述 |
|---------|------|
| `reconciliation_start` | 开始对账任务 |
| `reconciliation_status` | 查询任务状态 |
| `reconciliation_result` | 获取对账结果 |
| `reconciliation_list_tasks` | 列出所有任务 |
| `file_upload` | 上传文件 |

## 快速开始

### 1. 安装依赖

```bash
cd /Users/kevin/workspace/financial-ai
pip install -r requirements.txt
```

### 2. 启动服务

```bash
cd reconciliation
python mcp_sse_server.py
```

服务将在 `http://localhost:3335` 启动。

### 3. 配置 Dify

在 Dify 的 MCP 设置中添加：

- **服务器地址**: `http://localhost:3335/sse`
- **如果 Dify 在 Docker 中**: `http://host.docker.internal:3335/sse`

### 4. 使用示例

#### 4.1 上传文件

```json
{
  "tool": "file_upload",
  "arguments": {
    "filename": "业务流水.csv",
    "content": "base64_encoded_content"
  }
}
```

#### 4.2 开始对账

```json
{
  "tool": "reconciliation_start",
  "arguments": {
    "schema": {
      "version": "1.0",
      "description": "供应商对账",
      "data_sources": {
        "business": {
          "file_pattern": "*业务*.csv",
          "field_roles": {
            "order_id": "订单号",
            "amount": "金额",
            "date": "日期"
          }
        },
        "finance": {
          "file_pattern": "*财务*.csv",
          "field_roles": {
            "order_id": "单号",
            "amount": "到账金额",
            "date": "到账日期"
          }
        }
      },
      "key_field_role": "order_id",
      "tolerance": {
        "amount_diff_max": 1.0,
        "date_format": "%Y-%m-%d"
      }
    },
    "files": [
      "/path/to/uploaded/file1.csv",
      "/path/to/uploaded/file2.csv"
    ],
    "callback_url": "https://your-callback-url.com/notify"
  }
}
```

#### 4.3 查询状态

```json
{
  "tool": "reconciliation_status",
  "arguments": {
    "task_id": "task_abc123"
  }
}
```

#### 4.4 获取结果

```json
{
  "tool": "reconciliation_result",
  "arguments": {
    "task_id": "task_abc123"
  }
}
```

## Schema 配置说明

### 基本结构

```json
{
  "version": "1.0",
  "description": "对账描述",
  "data_sources": { ... },
  "key_field_role": "order_id",
  "tolerance": { ... },
  "data_cleaning_rules": { ... },
  "custom_validations": [ ... ]
}
```

### 数据源配置 (data_sources)

```json
"data_sources": {
  "business": {
    "file_pattern": ["*业务*.csv", "*流水*.xlsx"],
    "field_roles": {
      "order_id": ["订单号", "单号"],
      "amount": "金额",
      "date": "日期"
    }
  },
  "finance": {
    "file_pattern": "ads_finance_*.csv",
    "field_roles": {
      "order_id": "sup订单号",
      "amount": "到账金额",
      "date": "完成时间"
    }
  }
}
```

- `file_pattern`: 支持通配符和正则表达式
- `field_roles`: 字段映射，支持多个候选字段名（数组）

### 容差配置 (tolerance)

```json
"tolerance": {
  "amount_diff_max": 2.0,
  "date_format": "%Y-%m-%d"
}
```

- `amount_diff_max`: 金额差异容差
- `date_format`: 日期比较格式

### 数据清洗规则 (data_cleaning_rules)

#### 金额单位转换

```json
"amount_conversion": {
  "divide_by_100": {
    "file_patterns": ["*finance*.csv"],
    "fields": ["amount"]
  }
}
```

#### 重复数据聚合

```json
"aggregate_duplicates": {
  "group_by": "order_id",
  "aggregations": {
    "amount": "sum",
    "date": "first"
  }
}
```

### 自定义验证规则 (custom_validations)

```json
"custom_validations": [
  {
    "name": "skip_test_customer",
    "condition_expr": "biz.get('客户') == '测试客户'",
    "issue_type": "skipped",
    "detail_template": "测试客户，跳过校验"
  },
  {
    "name": "amount_mismatch",
    "condition_expr": "abs(float(biz.get('amount', 0)) - float(fin.get('amount', 0))) > 2.0",
    "issue_type": "amount_mismatch",
    "detail_template": "业务金额 {biz[amount]}，财务金额 {fin[amount]}"
  }
]
```

- `condition_expr`: Python 表达式，`biz` 为业务记录，`fin` 为财务记录
- `issue_type`: 问题类型
- `detail_template`: 问题详情模板，支持字段插值

## 对账结果格式

```json
{
  "task_id": "task_123456",
  "status": "completed",
  "summary": {
    "total_business_records": 1250,
    "total_finance_records": 1240,
    "matched_records": 1200,
    "unmatched_records": 50
  },
  "issues": [
    {
      "order_id": "ROC987654321",
      "issue_type": "amount_mismatch",
      "business_value": "5000.00",
      "finance_value": "4998.50",
      "detail": "业务金额 5000.00 vs 财务金额 4998.50，差额 1.50 超出容差 1.00"
    }
  ],
  "metadata": {
    "business_file_count": 2,
    "finance_file_count": 1,
    "rule_version": "1.0",
    "processed_at": "2025-04-05T14:30:00Z"
  }
}
```

## 模块结构

```
reconciliation/
├── mcp_server/
│   ├── __init__.py
│   ├── config.py              # 配置常量
│   ├── models.py              # 数据模型
│   ├── schema_loader.py       # Schema 加载和验证
│   ├── file_matcher.py        # 文件匹配器
│   ├── data_cleaner.py        # 数据清洗器
│   ├── reconciliation_engine.py # 对账引擎
│   ├── task_manager.py        # 异步任务管理
│   └── tools.py               # MCP 工具定义
├── mcp_sse_server.py          # 服务器入口
├── schemas/                   # Schema 示例
│   └── example_schema.json
├── uploads/                   # 上传文件目录
├── results/                   # 结果输出目录
└── README.md                  # 文档

```

## 扩展对账逻辑

要添加新的对账场景，只需创建新的 schema 配置文件，**无需修改任何代码**！

示例：供应商充值流水对账

```json
{
  "version": "1.0",
  "description": "供应商充值流水对账",
  "data_sources": {
    "finance": {
      "file_pattern": "ads_finance_*.csv",
      "field_roles": {
        "order_id": "sup订单号",
        "amount": "发生-",
        "date": "完成时间"
      }
    },
    "business": {
      "file_pattern": ["*对账流水.csv"],
      "field_roles": {
        "order_id": "roc_oid",
        "amount": "product_price",
        "date": "statis_date"
      }
    }
  },
  "key_field_role": "order_id",
  "tolerance": {
    "amount_diff_max": 2.0
  }
}
```

## 注意事项

1. **文件编码**: 支持 UTF-8, GBK, GB2312, GB18030
2. **文件大小**: 默认限制 100MB
3. **任务超时**: 默认 1 小时
4. **并发任务**: 默认最多 5 个
5. **安全性**: 自定义验证使用 `eval()`，生产环境建议替换为安全的表达式解析器

## 技术栈

- **MCP**: Model Context Protocol
- **Pandas**: 数据处理
- **Starlette**: ASGI Web 框架
- **Uvicorn**: ASGI 服务器
- **httpx**: 异步 HTTP 客户端

## License

MIT

