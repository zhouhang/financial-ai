# 聊天记录顺序修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让聊天会话历史的消息严格按发生顺序加载,修复同一轮 AI 多条回复乱序的问题。

**Architecture:** 给 `messages` 表新增全局单调自增列 `seq`,作为唯一权威排序依据;`get_messages` 改为按 `seq` 排序。新消息从此 100% 按插入顺序排列,历史数据按 `created_at + ctid` 近似回填。

**Tech Stack:** PostgreSQL(迁移 SQL)、Python(`finance-mcp/auth/db.py`)、pytest(`finance-mcp/qa/`)。

**设计文档:** `docs/superpowers/specs/2026-05-18-chat-message-ordering-fix-design.md`

---

## 文件结构

- `finance-mcp/auth/migrations/030_messages_seq_ordering.sql` — 新建。新增 `seq` 列、回填、序列默认值、排序索引。
- `finance-mcp/auth/migrations/README.md` — 修改。登记 `030` 迁移。
- `finance-mcp/auth/db.py` — 修改。`get_messages` 的两处 `ORDER BY` 改为按 `seq` 排序。
- `finance-mcp/qa/messages_ordering_spec.py` — 新建。集成测试:验证 `get_messages` 按插入顺序返回、与 `created_at` 无关。

---

## Task 1: 新增并应用数据库迁移 030

**Files:**
- Create: `finance-mcp/auth/migrations/030_messages_seq_ordering.sql`
- Modify: `finance-mcp/auth/migrations/README.md`

- [ ] **Step 1: 创建迁移 SQL 文件**

创建 `finance-mcp/auth/migrations/030_messages_seq_ordering.sql`,内容:

```sql
-- 030_messages_seq_ordering.sql
-- 为 messages 表新增全局单调自增列 seq,作为权威排序依据。
-- 根因:created_at 在同一轮多条助手消息的紧凑保存循环里会落到同一微秒,
--       而 id 是随机 UUID,ORDER BY created_at 遇并列时排序不确定。

-- 1) 新增可空列
ALTER TABLE public.messages ADD COLUMN seq BIGINT;

-- 2) 回填历史数据:按 created_at + ctid 推断插入顺序
--    messages 表只追加不更新,ctid 物理顺序≈插入顺序
WITH ordered AS (
  SELECT id, row_number() OVER (ORDER BY created_at ASC, ctid ASC) AS rn
  FROM public.messages
)
UPDATE public.messages m SET seq = ordered.rn
FROM ordered WHERE m.id = ordered.id;

-- 3) 建序列并接为默认值
CREATE SEQUENCE public.messages_seq_seq OWNED BY public.messages.seq;
SELECT setval('public.messages_seq_seq',
              COALESCE((SELECT MAX(seq) FROM public.messages), 0) + 1, false);
ALTER TABLE public.messages ALTER COLUMN seq SET DEFAULT nextval('public.messages_seq_seq');
ALTER TABLE public.messages ALTER COLUMN seq SET NOT NULL;

-- 4) 排序索引,匹配 get_messages 的查询模式
CREATE INDEX idx_messages_conversation_seq ON public.messages (conversation_id, seq);
```

- [ ] **Step 2: 应用迁移到本地数据库**

迁移文件依赖项目自身的数据库连接配置(`db_config`)。用项目内置的 `_execute_sql_script` 应用:

Run:
```bash
cd finance-mcp && python -c "from auth.db import _execute_sql_script, _migration_path; _execute_sql_script(_migration_path('030_messages_seq_ordering.sql'))"
```
Expected: 无报错,无输出(成功时静默)。

- [ ] **Step 3: 验证 seq 列已存在**

Run:
```bash
cd finance-mcp && python -c "from auth.db import _column_exists; print(_column_exists('messages', 'seq'))"
```
Expected: 输出 `True`

- [ ] **Step 4: 在迁移 README 登记 030**

修改 `finance-mcp/auth/migrations/README.md`,在执行顺序列表第 29 项(`29. **029_clean_alipay_semantic_profiles.sql** ...`)之后新增一行:

```markdown
30. **030_messages_seq_ordering.sql** - 为 messages 表新增单调自增 seq 列,修复聊天记录加载顺序乱序
```

- [ ] **Step 5: 提交**

```bash
git add finance-mcp/auth/migrations/030_messages_seq_ordering.sql finance-mcp/auth/migrations/README.md
git commit -m "feat: add messages.seq column for deterministic chat ordering"
```

---

## Task 2: 修改 get_messages 按 seq 排序并加集成测试

**前置条件:** Task 1 已完成,本地数据库已应用迁移 030(`messages.seq` 列存在)。

**Files:**
- Test: `finance-mcp/qa/messages_ordering_spec.py`
- Modify: `finance-mcp/auth/db.py:1411` 与 `finance-mcp/auth/db.py:1422`(`get_messages` 内两处 `ORDER BY`)

- [ ] **Step 1: 写失败测试**

创建 `finance-mcp/qa/messages_ordering_spec.py`,内容:

```python
from __future__ import annotations

from datetime import datetime, timedelta

import psycopg2
import pytest

from auth.db import create_conversation, delete_conversation, get_conn, get_messages


def _first_user_id() -> str | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users LIMIT 1")
            row = cur.fetchone()
            return str(row[0]) if row else None


def test_get_messages_orders_by_seq_not_created_at() -> None:
    """get_messages 必须按插入顺序(seq)返回消息,与 created_at 无关。

    构造场景:按 msg-0..msg-4 顺序插入,但把 created_at 故意设为递减。
    旧实现 ORDER BY created_at ASC 会把顺序反转;
    修复后 ORDER BY seq ASC 应保持插入顺序。
    这同时覆盖了真实根因——多条消息 created_at 并列时排序不确定。
    """
    try:
        user_id = _first_user_id()
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        pytest.skip("数据库不可用，跳过会话顺序集成测试")

    if not user_id:
        pytest.skip("users 表为空，无法创建测试会话")

    conv = create_conversation(user_id, "ordering-spec")
    assert conv is not None
    conv_id = str(conv["id"])

    try:
        base = datetime(2026, 1, 1, 12, 0, 0)
        with get_conn() as conn:
            with conn.cursor() as cur:
                for i in range(5):
                    cur.execute(
                        """INSERT INTO messages (conversation_id, role, content, created_at)
                           VALUES (%s, %s, %s, %s)""",
                        (conv_id, "assistant", f"msg-{i}", base - timedelta(minutes=i)),
                    )
            conn.commit()

        messages = get_messages(conv_id)
        contents = [m["content"] for m in messages]
        assert contents == [f"msg-{i}" for i in range(5)]
    finally:
        delete_conversation(conv_id, user_id)
```

说明:
- 测试用纯文本内容 `msg-0`..`msg-4`,可通过 `get_messages` 内 `should_display_message` 过滤(不以 `{` `[` `<` 或 ```` ``` ```` 开头,非 system 角色)。
- 测试自带清理:`finally` 中 `delete_conversation` 会级联删除消息。
- 数据库不可用或 `users` 表为空时 `pytest.skip`,不算失败。

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
cd finance-mcp && python -m pytest qa/messages_ordering_spec.py -v
```
Expected: FAIL。断言报错形如 `assert ['msg-4', 'msg-3', 'msg-2', 'msg-1', 'msg-0'] == ['msg-0', 'msg-1', 'msg-2', 'msg-3', 'msg-4']`(旧实现按 `created_at` 升序把顺序反转了)。

- [ ] **Step 3: 修改 get_messages 的排序**

修改 `finance-mcp/auth/db.py` 的 `get_messages` 函数。该函数内有两段 SQL(主查询含 `attachments` 列,旧版兼容查询不含)。把两处的 `ORDER BY created_at ASC` 都改为 `ORDER BY seq ASC`。

主查询(原约 1411 行):
```python
                    cur.execute(
                        """SELECT id, conversation_id, role, content, metadata, attachments, created_at
                           FROM messages
                           WHERE conversation_id = %s
                           ORDER BY seq ASC
                           LIMIT %s OFFSET %s""",
                        (conversation_id, limit, offset)
                    )
```

旧版兼容查询(原约 1422 行):
```python
                    cur.execute(
                        """SELECT id, conversation_id, role, content, metadata, created_at
                           FROM messages
                           WHERE conversation_id = %s
                           ORDER BY seq ASC
                           LIMIT %s OFFSET %s""",
                        (conversation_id, limit, offset)
                    )
```

其余逻辑(`should_display_message` 过滤、字段序列化等)不变。

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
cd finance-mcp && python -m pytest qa/messages_ordering_spec.py -v
```
Expected: PASS(`test_get_messages_orders_by_seq_not_created_at` 通过)。

- [ ] **Step 5: 运行 qa 全量测试确认无回归**

Run:
```bash
cd finance-mcp && python -m pytest qa/ -v
```
Expected: 全部 PASS(或与改动前一致;新增测试通过,既有测试不受影响)。

- [ ] **Step 6: 提交**

```bash
git add finance-mcp/auth/db.py finance-mcp/qa/messages_ordering_spec.py
git commit -m "fix: order chat messages by seq to preserve send order"
```

---

## 部署说明

迁移 `030_messages_seq_ordering.sql` 须在**每个环境**(本地、测试、生产)部署新代码前应用——`get_messages` 改为 `ORDER BY seq` 后依赖 `seq` 列存在。按 `finance-mcp/auth/migrations/README.md` 的常规流程,在该环境执行迁移 030 即可。

---

## Self-Review

- **Spec 覆盖:**
  - 「新增 seq 列 + 回填 + 序列 + 索引」→ Task 1 Step 1。
  - 「`get_messages` 改 ORDER BY」→ Task 2 Step 3。
  - 「`save_message` / `server.py` / 前端不改」→ 计划未涉及,符合 spec。
  - 「测试两个场景:保留插入顺序、created_at 并列仍正确」→ Task 2 的单个测试用 created_at 递减、插入顺序递增,严格覆盖「排序依据为 seq、与 created_at 无关」,并列只是「created_at 不可信」的子情形,已被涵盖。
  - 「不修改 001 基线」→ Task 1 只新建 030,符合。
- **占位符扫描:** 无 TBD/TODO,所有步骤含具体内容与命令。
- **类型一致性:** `conv_id` 全程为 `str`;`get_messages` 返回项用 `m["content"]` 访问,与 `db.py` 中 `RealDictCursor` 返回的 dict 一致。
