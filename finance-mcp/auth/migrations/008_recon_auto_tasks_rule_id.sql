-- 008: 为 recon_auto_tasks 补充 rule_id 字段
-- 背景：
--   自动对账任务接口与 DB 读写已使用 rule_id，
--   但部分已升级环境中 recon_auto_tasks 早期版本未包含该列。
-- 目标：
--   增量补齐字段，保证 create/update/list/get 兼容。

ALTER TABLE IF EXISTS public.recon_auto_tasks
    ADD COLUMN IF NOT EXISTS rule_id character varying(120) DEFAULT ''::character varying NOT NULL;
