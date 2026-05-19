# 聊天记录顺序修复设计

日期:2026-05-18

## 问题

Tally 聊天页面加载历史会话时,同一轮对话中 AI 一次回复的**多条消息**之间,显示顺序与生成顺序不一致。表现稳定:每次刷新都是同样的错误顺序;同一轮内「用户提问 → AI 回复」的大顺序正确。

## 根因

`messages` 表缺少能反映**插入顺序**的确定性字段。

- `messages.id` 是随机 `uuid_generate_v4()`,无法作为排序兜底。
- `messages.created_at` 默认取 `CURRENT_TIMESTAMP`(事务开始时间)。服务端在一轮结束时用紧凑循环连续保存多条助手消息(`finance-agents/data-agent/server.py:1141-1146`),相邻 INSERT 间隔在微秒级,会落到**同一个微秒时间戳**。
- `finance-mcp/auth/db.py` 的 `get_messages` 使用 `ORDER BY created_at ASC`。遇到并列的时间戳时没有确定性兜底字段,Postgres 按物理扫描顺序返回——对固定的物理布局是稳定的,但与插入顺序无关。因此「顺序固定错、刷新一致」。

前端不参与排序:`finance-web/src/hooks/useConversations.ts` 的 `convertConversation` 仅按 API 返回的数组顺序映射消息。

## 方案

给 `messages` 表新增一个全局单调自增列 `seq`,作为唯一权威排序依据。`get_messages` 改为按 `seq` 排序。

历史数据不要求精确还原(已乱序轮次的真实顺序信息已丢失);回填只需给出一个不劣于现状的近似顺序。新消息从此 100% 按插入顺序排列。

### 数据库迁移 — `finance-mcp/auth/migrations/030_messages_seq_ordering.sql`

```sql
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

说明:

- `030` 为下一个迁移编号(当前最大为 `029`)。
- 不修改 `001_initial_schema.sql`——它是基线快照,新部署会顺序应用全部迁移,改它会导致重复定义。
- 回填用 `created_at, ctid`:对追加型表,`ctid` 物理顺序近似插入顺序,可在并列时间戳内给出稳定区分。这是历史数据能做到的最佳近似;不追求精确还原。
- `idx_messages_conversation_seq` 与新查询模式 `WHERE conversation_id = ? ORDER BY seq ASC LIMIT ?` 精确对应,使数据库直接返回有序结果、省去内存排序步骤。

### 代码改动

**`finance-mcp/auth/db.py` — `get_messages`**

两处 SQL 的 `ORDER BY created_at ASC` 均改为 `ORDER BY seq ASC`(含 `attachments` 列的主查询,以及不含该列的旧版兼容查询)。其余逻辑不变。

**`save_message`(`finance-mcp/auth/db.py`)**

无需改动。INSERT 语句不写 `seq` 列,数据库默认 `nextval` 自动按插入顺序填充。

**`finance-agents/data-agent/server.py` — 保存循环**

无需改动。该循环本就按生成顺序逐条 `await mcp_save_message(...)`,`seq` 随之单调递增。

**前端**

无需改动。`convertConversation` 按数组顺序映射,后端 `get_messages` 已保证返回顺序正确。

## 测试

在 `finance-mcp/qa/` 新增一个 spec:

1. 向一个会话连续保存「1 条 user + 多条 assistant」消息,调用 `get_messages`,断言返回顺序与保存顺序完全一致。
2. 构造多条 `created_at` 相同的消息,验证 `get_messages` 仍按 `seq` 给出确定且正确的顺序——即覆盖根因场景(并列时间戳)。

## 范围之外

- 不还原历史已乱序轮次的真实顺序(信息已丢失)。
- 不删除现有 `idx_messages_created_at` 索引(虽然 `get_messages` 不再用它排序,清理属独立事项)。
- 不改动前端、不改动消息保存的调用流程。
