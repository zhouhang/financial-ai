# AGENTS.md - AI Agent Coding Guidelines

This file provides guidelines for AI agents working in this repository.

## Project Overview

This is a Financial AI system with:
- **finance-mcp/**: Core MCP server (Python FastAPI)
- **finance-agents/data-agent/**: LangGraph-based agent for reconciliation and data preparation
- **finance-web/**: React + TypeScript frontend (Vite)
- **Database**: PostgreSQL (tally) + MySQL (finance-ai)
- **External Services**: Dify (AI orchestration), Tencent LLM

## Build/Lint/Test Commands

### Python (finance-mcp, finance-agents/data-agent)

```bash
# Activate virtual environment
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate

# Run all tests
pytest

# Run a single test file
pytest path/to/test_file.py -v

# Run a single test function
pytest path/to/test_file.py::test_name -v

# Lint (if ruff is installed)
ruff check .
ruff check --fix .
```

### TypeScript/React (finance-web)

```bash
cd /Users/kevin/workspace/financial-ai/finance-web

# Install dependencies
npm install

# Development server
npm run dev

# Build for production
npm run build

# Lint
npm run lint
npm run lint -- --fix

# Type check
npx tsc --noEmit
```

### Starting Services

```bash
# Start all services
cd /Users/kevin/workspace/financial-ai
./START_ALL_SERVICES.sh

# Stop all services
./STOP_ALL_SERVICES.sh
```

Service ports:
- finance-web: http://localhost:5173
- data-agent: http://localhost:8100
- finance-mcp: http://localhost:3335
- Dify: http://localhost

## Code Style Guidelines

### Python

#### Imports
- Standard library first, then third-party, then local
- Use absolute imports from package root
- Group by: `__future__`, stdlib, third-party, local

```python
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from langchain_core.messages import AnyMessage
from pydantic import BaseModel, Field

from app.config import DATABASE_URL
from app.models import AgentState
```

#### Types
- Use type hints for all function signatures
- Use Pydantic `BaseModel` for data validation
- Use `TypedDict` for LangGraph state
- Use `Literal` for union of string literals
- Use `Annotated` for LangChain operators

```python
def save_rule(name: str, type_key: str, schema: dict, description: str = "") -> str:
    ...

class AgentState(TypedDict, total=False):
    messages: Annotated[Sequence[AnyMessage], operator.add]
    thread_id: str
```

#### Naming Conventions
- **Variables/functions**: snake_case `user_id`, `get_connection()`
- **Classes**: PascalCase `ReconciliationEngine`, `FieldMapping`
- **Constants**: UPPER_SNAKE_CASE `MAX_FILE_SIZE`, `DEFAULT_TIMEOUT`
- **Private**: prefix underscore `_internal_method()`
- **Types**: PascalCase (already covered by class naming)

#### Formatting
- Line length: ~100 characters max
- Use Black-compatible formatting
- Use blank lines to separate logical sections
- Use section comments: `# ── Database ─────────────────────────────────────────────`

```python
# ── Database ─────────────────────────────────────────────────────────────────
def _get_conn():
    return psycopg2.connect(DATABASE_URL)


def ensure_tables():
    """如果不存在，则创建 reconciliation_rules 表。"""
    ...
```

#### Error Handling
- Use try/except with specific exception types
- Always log errors with `logger.error(f"Message: {e}")`
- Re-raise after rollback on database errors
- Use context managers for connections

```python
try:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
except Exception as e:
    logger.error(f"操作失败: {e}")
    raise
```

#### Docstrings
- Use triple quotes for docstrings
- Include description, args, returns
- Chinese comments for user-facing messages

```python
def load_rule(name: str) -> Optional[dict[str, Any]]:
    """按名称加载规则。如果未找到则返回 None。
    
    Args:
        name: 规则名称
        
    Returns:
        规则字典，如果未找到则返回 None
    """
```

### TypeScript/JavaScript

#### Imports
- Use ES modules with `import`
- Use `type` keyword for type-only imports

```typescript
import { useCallback, useState } from 'react';
import Sidebar from './components/Sidebar';
import type { Conversation, Message } from './types';
```

#### Types
- Use TypeScript interfaces for object shapes
- Use `type` for unions, aliases
- Export types with `export type`

```typescript
export type MessageRole = 'user' | 'assistant' | 'system';

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
}
```

#### Naming Conventions
- **Variables/functions**: camelCase `userId`, `getConnection()`
- **Components/Types**: PascalCase `Sidebar`, `MessageBubble`
- **Files**: kebab-case or PascalCase for components

#### Formatting
- Use 2-space indentation
- Trailing commas for multi-line objects/arrays
- Single quotes for strings

### General

1. **Service Restart**: After modifying data-agent, finance-mcp, or finance-web code, always restart services:
   ```bash
   ./START_ALL_SERVICES.sh
   ```

2. **Database Config**: Connection strings stored in environment variables or `.env` files. Check:
   - `finance-agents/data-agent/.env`
   - `finance-mcp/db_config.py`

3. **Logging**: Use Python's `logging` module, not print statements
   ```python
   logger = logging.getLogger(__name__)
   logger.info("Action completed")
   logger.error(f"Failed: {e}")
   ```

4. **Environment Variables**: Document any new required env vars in comments

5. **Cursor Rules** (from `.cursorrules`):
   - After modifying data-agent, finance-mcp, or finance-web code, restart services with `./START_ALL_SERVICES.sh`

## File Locations

| Component | Path |
|-----------|------|
| MCP Server | `finance-mcp/unified_mcp_server.py` |
| Data Agent | `finance-agents/data-agent/server.py` |
| Frontend | `finance-web/src/` |
| Data Agent Config | `finance-agents/data-agent/config.py` |
| MCP DB Config | `finance-mcp/db_config.py` |

## Database

- **PostgreSQL** (tally): `localhost:5432` - reconciliation rules, users
- **MySQL** (finance-ai): `localhost:3306` - schemas, files metadata

## Common Tasks

### Running a specific test
```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest path/to/test_file.py::test_name -v
```

### Checking service logs
```bash
tail -f logs/finance-mcp.log
tail -f logs/data-agent.log
tail -f logs/finance-web.log
```

### Health check
```bash
curl http://localhost:8100/health
curl http://localhost:3335/health
```
