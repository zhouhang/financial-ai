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
