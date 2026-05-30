-- 待处理异常的部分索引：支撑调度器周期性同步钉钉待办状态。
--
-- 调度器查询「仍 pending、未关闭、已建待办」的异常批次时，过去 processing_status
-- 上无索引会全表顺序扫描；表越大越慢。部分索引只收录 pending 且未关闭的行，
-- 而 pending 是过渡态（处理完即离开），索引体积与「在途待处理条数」成正比、
-- 与表总量无关，使该查询代价稳定在 O(pending)。
CREATE INDEX IF NOT EXISTS idx_execution_run_exceptions_pending_open
    ON public.execution_run_exceptions USING btree (run_id, owner_identifier)
    WHERE processing_status = 'pending' AND is_closed = false;
