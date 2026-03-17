-- =============================================================================
-- Migration: 004_reconciliation_result_storage
-- Description: 对账结果存储 - 支持多组文件对账、操作人追踪、差异处理状态管理
-- Created: 2026-03
-- =============================================================================

-- =============================================================================
-- 1. reconciliation_sessions - 对账会话表
-- 一次对账操作对应一个会话，记录操作人和时间
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.reconciliation_sessions (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    task_id uuid,                                    -- 关联的对账任务（可选，兼容现有流程）
    rule_id uuid,                                    -- 关联的对账规则
    
    -- 操作人信息
    operator_id uuid NOT NULL,                       -- 操作人（创建会话的用户）
    department_id uuid,                              -- 所属部门
    
    -- 会话信息
    session_name character varying(255),             -- 会话名称（如：2026年3月销售对账）
    session_type character varying(50) DEFAULT 'standard',  -- 会话类型：standard/audit/custom
    status character varying(20) DEFAULT 'pending',  -- 状态：pending/running/completed/cancelled
    
    -- 时间追踪
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    
    -- 汇总统计
    total_file_groups integer DEFAULT 0,             -- 文件组数量
    total_records integer DEFAULT 0,                 -- 总记录数
    total_issues integer DEFAULT 0,                  -- 总差异数
    processed_issues integer DEFAULT 0,              -- 已处理差异数
    
    -- 元数据
    notes text,                                      -- 备注
    tags text[] DEFAULT ARRAY[]::text[],
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT reconciliation_sessions_pkey PRIMARY KEY (id),
    CONSTRAINT reconciliation_sessions_status_check CHECK (
        ((status)::text = ANY (ARRAY['pending'::text, 'running'::text, 'completed'::text, 'cancelled'::text]))
    ),
    CONSTRAINT reconciliation_sessions_session_type_check CHECK (
        ((session_type)::text = ANY (ARRAY['standard'::text, 'audit'::text, 'custom'::text]))
    )
);

COMMENT ON TABLE public.reconciliation_sessions IS '对账会话表 - 一次对账操作对应一个会话';
COMMENT ON COLUMN public.reconciliation_sessions.task_id IS '关联的对账任务ID（兼容现有流程）';
COMMENT ON COLUMN public.reconciliation_sessions.operator_id IS '操作人ID';
COMMENT ON COLUMN public.reconciliation_sessions.session_type IS 'standard: 标准对账, audit: 审计对账, custom: 自定义';

-- 外键约束
ALTER TABLE public.reconciliation_sessions 
ADD CONSTRAINT reconciliation_sessions_task_id_fkey 
FOREIGN KEY (task_id) REFERENCES public.reconciliation_tasks(id) ON DELETE SET NULL;

ALTER TABLE public.reconciliation_sessions 
ADD CONSTRAINT reconciliation_sessions_rule_id_fkey 
FOREIGN KEY (rule_id) REFERENCES public.reconciliation_rules(id) ON DELETE SET NULL;

ALTER TABLE public.reconciliation_sessions 
ADD CONSTRAINT reconciliation_sessions_operator_id_fkey 
FOREIGN KEY (operator_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE public.reconciliation_sessions 
ADD CONSTRAINT reconciliation_sessions_department_id_fkey 
FOREIGN KEY (department_id) REFERENCES public.departments(id) ON DELETE SET NULL;

-- 索引
CREATE INDEX idx_sessions_operator_id ON public.reconciliation_sessions USING btree (operator_id);
CREATE INDEX idx_sessions_rule_id ON public.reconciliation_sessions USING btree (rule_id);
CREATE INDEX idx_sessions_status ON public.reconciliation_sessions USING btree (status);
CREATE INDEX idx_sessions_created_at ON public.reconciliation_sessions USING btree (created_at DESC);
CREATE INDEX idx_sessions_department_id ON public.reconciliation_sessions USING btree (department_id);

-- 触发器：自动更新 updated_at
CREATE TRIGGER update_reconciliation_sessions_updated_at
BEFORE UPDATE ON public.reconciliation_sessions
FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- =============================================================================
-- 2. reconciliation_file_groups - 文件组表
-- 一个会话可包含多组文件（业务文件 + 财务文件）
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.reconciliation_file_groups (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    session_id uuid NOT NULL,
    
    -- 文件组信息
    group_name character varying(255),               -- 文件组名称（如：销售数据组、退货数据组）
    group_order integer DEFAULT 0,                   -- 显示顺序
    
    -- 文件信息
    business_files jsonb DEFAULT '[]'::jsonb,        -- 业务文件列表 [{name, path, size, ...}]
    finance_files jsonb DEFAULT '[]'::jsonb,         -- 财务文件列表 [{name, path, size, ...}]
    
    -- 该组的对账摘要
    total_business_records integer DEFAULT 0,        -- 业务记录总数
    total_finance_records integer DEFAULT 0,         -- 财务记录总数
    matched_records integer DEFAULT 0,               -- 匹配记录数
    unmatched_records integer DEFAULT 0,             -- 差异记录数
    
    -- 分类统计
    issues_by_type jsonb DEFAULT '{}'::jsonb,        -- 按类型统计差异数 {amount_mismatch: 5, missing_in_finance: 3}
    
    -- 状态
    status character varying(20) DEFAULT 'pending',  -- pending/processing/completed/failed
    error_message text,
    
    -- 时间
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT reconciliation_file_groups_pkey PRIMARY KEY (id),
    CONSTRAINT reconciliation_file_groups_status_check CHECK (
        ((status)::text = ANY (ARRAY['pending'::text, 'processing'::text, 'completed'::text, 'failed'::text]))
    )
);

COMMENT ON TABLE public.reconciliation_file_groups IS '对账文件组表 - 一组业务+财务文件的对账';
COMMENT ON COLUMN public.reconciliation_file_groups.business_files IS '业务文件列表，JSON数组格式';
COMMENT ON COLUMN public.reconciliation_file_groups.finance_files IS '财务文件列表，JSON数组格式';
COMMENT ON COLUMN public.reconciliation_file_groups.issues_by_type IS '按问题类型统计差异数';

-- 外键约束
ALTER TABLE public.reconciliation_file_groups 
ADD CONSTRAINT reconciliation_file_groups_session_id_fkey 
FOREIGN KEY (session_id) REFERENCES public.reconciliation_sessions(id) ON DELETE CASCADE;

-- 索引
CREATE INDEX idx_file_groups_session_id ON public.reconciliation_file_groups USING btree (session_id);
CREATE INDEX idx_file_groups_status ON public.reconciliation_file_groups USING btree (status);

-- 触发器
CREATE TRIGGER update_reconciliation_file_groups_updated_at
BEFORE UPDATE ON public.reconciliation_file_groups
FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- =============================================================================
-- 3. reconciliation_result_records - 对账差异记录表
-- 存储每条差异的详细数据，支持动态列和处理状态追踪
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.reconciliation_result_records (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    file_group_id uuid NOT NULL,
    
    -- 核心字段（固定）
    order_id character varying(255),                 -- 订单号/主键值
    issue_type character varying(50),                -- 问题类型：amount_mismatch/missing_in_finance/...
    detail text,                                     -- 详情描述
    
    -- 主要金额字段（用于快速查询和统计，存储最重要的比较金额）
    business_amount numeric(18,2),                   -- 业务侧金额
    finance_amount numeric(18,2),                    -- 财务侧金额
    amount_diff numeric(18,2),                       -- 金额差异
    
    -- 多字段比较值（JSONB，存储所有需要比较的字段）
    comparison_values jsonb DEFAULT '{}'::jsonb,     -- 多字段比较值
    
    -- 动态字段（存储规则定义的额外列）
    extra_data jsonb DEFAULT '{}'::jsonb,            -- 动态列数据 {column_name: value, ...}
    
    -- 原始数据（可选，用于追溯）
    business_raw jsonb,                              -- 业务侧原始记录
    finance_raw jsonb,                               -- 财务侧原始记录
    
    -- 合并键信息（当使用多个键时）
    key_fields jsonb DEFAULT '{}'::jsonb,            -- 合并键字段 {field_name: value, ...}
    
    -- 行索引
    row_index integer,                               -- 用于排序
    
    -- ========== 处理状态追踪 ==========
    process_status character varying(20) DEFAULT 'pending',  -- pending/processing/resolved/ignored/escalated
    processed_by uuid,                               -- 处理人ID
    processed_at timestamp with time zone,           -- 处理时间
    process_result character varying(50),            -- 处理结果：fixed/explained/accepted/disputed
    process_notes text,                              -- 处理备注
    
    -- 审核状态（可选）
    review_status character varying(20),             -- pending_review/approved/rejected
    reviewed_by uuid,                                -- 审核人ID
    reviewed_at timestamp with time zone,            -- 审核时间
    review_notes text,                               -- 审核备注
    
    -- 时间戳
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT reconciliation_result_records_pkey PRIMARY KEY (id),
    CONSTRAINT reconciliation_result_records_process_status_check CHECK (
        ((process_status)::text = ANY (ARRAY[
            'pending'::text, 'processing'::text, 'resolved'::text, 
            'ignored'::text, 'escalated'::text
        ]))
    ),
    CONSTRAINT reconciliation_result_records_process_result_check CHECK (
        ((process_result)::text IS NULL OR 
         (process_result)::text = ANY (ARRAY[
            'fixed'::text, 'explained'::text, 'accepted'::text, 
            'disputed'::text, 'other'::text
         ]))
    ),
    CONSTRAINT reconciliation_result_records_review_status_check CHECK (
        ((review_status)::text IS NULL OR 
         (review_status)::text = ANY (ARRAY['pending_review'::text, 'approved'::text, 'rejected'::text]))
    )
);

COMMENT ON TABLE public.reconciliation_result_records IS '对账差异记录表 - 存储每条差异的详细数据';
COMMENT ON COLUMN public.reconciliation_result_records.business_amount IS '业务侧主要金额（用于统计和快速查询）';
COMMENT ON COLUMN public.reconciliation_result_records.finance_amount IS '财务侧主要金额（用于统计和快速查询）';
COMMENT ON COLUMN public.reconciliation_result_records.amount_diff IS '金额差异值（business_amount - finance_amount）';
COMMENT ON COLUMN public.reconciliation_result_records.comparison_values IS '多字段比较值，格式: {"字段名": {"target": 目标值, "source": 源值, "diff": 差异, "match": true/false, "target_col": 列名, "source_col": 列名}}';
COMMENT ON COLUMN public.reconciliation_result_records.extra_data IS '动态列数据，存储规则定义的额外字段';
COMMENT ON COLUMN public.reconciliation_result_records.key_fields IS '合并键字段，当使用多个键时存储所有键值对';
COMMENT ON COLUMN public.reconciliation_result_records.process_status IS 'pending: 待处理, processing: 处理中, resolved: 已解决, ignored: 已忽略, escalated: 已升级';
COMMENT ON COLUMN public.reconciliation_result_records.process_result IS 'fixed: 已修正, explained: 已说明, accepted: 已接受, disputed: 有争议';

-- 外键约束
ALTER TABLE public.reconciliation_result_records 
ADD CONSTRAINT reconciliation_result_records_file_group_id_fkey 
FOREIGN KEY (file_group_id) REFERENCES public.reconciliation_file_groups(id) ON DELETE CASCADE;

ALTER TABLE public.reconciliation_result_records 
ADD CONSTRAINT reconciliation_result_records_processed_by_fkey 
FOREIGN KEY (processed_by) REFERENCES public.users(id) ON DELETE SET NULL;

ALTER TABLE public.reconciliation_result_records 
ADD CONSTRAINT reconciliation_result_records_reviewed_by_fkey 
FOREIGN KEY (reviewed_by) REFERENCES public.users(id) ON DELETE SET NULL;

-- 索引
CREATE INDEX idx_result_records_file_group_id ON public.reconciliation_result_records USING btree (file_group_id);
CREATE INDEX idx_result_records_order_id ON public.reconciliation_result_records USING btree (order_id);
CREATE INDEX idx_result_records_issue_type ON public.reconciliation_result_records USING btree (issue_type);
CREATE INDEX idx_result_records_process_status ON public.reconciliation_result_records USING btree (process_status);
CREATE INDEX idx_result_records_processed_by ON public.reconciliation_result_records USING btree (processed_by);
CREATE INDEX idx_result_records_extra_data ON public.reconciliation_result_records USING gin (extra_data);
CREATE INDEX idx_result_records_created_at ON public.reconciliation_result_records USING btree (created_at);

-- 触发器
CREATE TRIGGER update_reconciliation_result_records_updated_at
BEFORE UPDATE ON public.reconciliation_result_records
FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- =============================================================================
-- 4. reconciliation_result_columns - 对账结果列定义表
-- 存储动态列的元数据，用于前端渲染表头
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.reconciliation_result_columns (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    session_id uuid NOT NULL,
    
    -- 列定义
    column_name character varying(100) NOT NULL,     -- 列名（英文，对应 extra_data 中的 key）
    display_name character varying(100),             -- 显示名（中文）
    column_type character varying(50) DEFAULT 'text',-- 数据类型：text/number/date/amount
    column_order integer DEFAULT 0,                  -- 显示顺序
    is_visible boolean DEFAULT true,                 -- 是否显示
    is_required boolean DEFAULT false,               -- 是否必填
    width integer,                                   -- 列宽度（像素）
    
    -- 格式化配置
    format_config jsonb DEFAULT '{}'::jsonb,         -- 格式化配置 {decimal_places: 2, prefix: '¥', ...}
    
    -- 验证规则
    validation_rules jsonb DEFAULT '{}'::jsonb,      -- 验证规则 {min: 0, max: 100, pattern: '...'}
    
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT reconciliation_result_columns_pkey PRIMARY KEY (id),
    CONSTRAINT reconciliation_result_columns_session_name_unique UNIQUE (session_id, column_name)
);

COMMENT ON TABLE public.reconciliation_result_columns IS '对账结果列定义表 - 存储动态列的元数据';
COMMENT ON COLUMN public.reconciliation_result_columns.format_config IS '格式化配置，如小数位数、前缀等';
COMMENT ON COLUMN public.reconciliation_result_columns.validation_rules IS '验证规则，用于输入校验';

-- 外键约束
ALTER TABLE public.reconciliation_result_columns 
ADD CONSTRAINT reconciliation_result_columns_session_id_fkey 
FOREIGN KEY (session_id) REFERENCES public.reconciliation_sessions(id) ON DELETE CASCADE;

-- 索引
CREATE INDEX idx_result_columns_session_id ON public.reconciliation_result_columns USING btree (session_id);

-- =============================================================================
-- 5. reconciliation_process_history - 差异处理历史表
-- 记录差异处理的完整历史轨迹
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.reconciliation_process_history (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    record_id uuid NOT NULL,                         -- 关联的差异记录
    
    -- 操作信息
    action character varying(50) NOT NULL,           -- 操作类型：status_change/note_add/review/etc
    old_status character varying(20),                -- 原状态
    new_status character varying(20),                -- 新状态
    
    -- 操作内容
    content text,                                    -- 操作内容/备注
    
    -- 操作人
    operator_id uuid NOT NULL,
    
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT reconciliation_process_history_pkey PRIMARY KEY (id)
);

COMMENT ON TABLE public.reconciliation_process_history IS '差异处理历史表 - 记录差异处理的完整历史轨迹';
COMMENT ON COLUMN public.reconciliation_process_history.action IS '操作类型：status_change(状态变更)/note_add(添加备注)/review(审核)/assign(分配)';

-- 外键约束
ALTER TABLE public.reconciliation_process_history 
ADD CONSTRAINT reconciliation_process_history_record_id_fkey 
FOREIGN KEY (record_id) REFERENCES public.reconciliation_result_records(id) ON DELETE CASCADE;

ALTER TABLE public.reconciliation_process_history 
ADD CONSTRAINT reconciliation_process_history_operator_id_fkey 
FOREIGN KEY (operator_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- 索引
CREATE INDEX idx_process_history_record_id ON public.reconciliation_process_history USING btree (record_id);
CREATE INDEX idx_process_history_operator_id ON public.reconciliation_process_history USING btree (operator_id);
CREATE INDEX idx_process_history_created_at ON public.reconciliation_process_history USING btree (created_at DESC);

-- =============================================================================
-- 6. Views - 视图
-- =============================================================================

-- 对账会话完整视图（包含操作人、部门信息）
CREATE OR REPLACE VIEW public.v_reconciliation_sessions_full AS
SELECT 
    s.id, s.session_name, s.session_type, s.status,
    s.total_file_groups, s.total_records, s.total_issues, s.processed_issues,
    s.started_at, s.completed_at, s.notes, s.tags, s.created_at, s.updated_at,
    r.id AS rule_id, r.name AS rule_name,
    u.id AS operator_id, u.username AS operator_name,
    d.id AS department_id, d.name AS department_name,
    c.id AS company_id, c.name AS company_name
FROM public.reconciliation_sessions s
LEFT JOIN public.reconciliation_rules r ON s.rule_id = r.id
LEFT JOIN public.users u ON s.operator_id = u.id
LEFT JOIN public.departments d ON s.department_id = d.id
LEFT JOIN public.company c ON u.company_id = c.id;

COMMENT ON VIEW public.v_reconciliation_sessions_full IS '对账会话完整视图';

-- 差异记录完整视图（包含处理人、文件组信息）
CREATE OR REPLACE VIEW public.v_reconciliation_records_full AS
SELECT 
    rec.id, rec.order_id, rec.issue_type, rec.detail, 
    rec.business_amount, rec.finance_amount, rec.amount_diff,
    rec.comparison_values, rec.key_fields, rec.extra_data,
    rec.business_raw, rec.finance_raw,
    rec.process_status, rec.process_result, rec.process_notes, 
    rec.processed_at, rec.review_status, rec.reviewed_at, rec.review_notes,
    rec.row_index, rec.created_at, rec.updated_at,
    fg.id AS file_group_id, fg.group_name,
    fg.business_files, fg.finance_files,
    s.id AS session_id, s.session_name,
    r.id AS rule_id, r.name AS rule_name,
    pu.id AS processed_by_id, pu.username AS processed_by_name,
    rvu.id AS reviewed_by_id, rvu.username AS reviewed_by_name,
    op.id AS operator_id, op.username AS operator_name
FROM public.reconciliation_result_records rec
JOIN public.reconciliation_file_groups fg ON rec.file_group_id = fg.id
JOIN public.reconciliation_sessions s ON fg.session_id = s.id
LEFT JOIN public.reconciliation_rules r ON s.rule_id = r.id
LEFT JOIN public.users pu ON rec.processed_by = pu.id
LEFT JOIN public.users rvu ON rec.reviewed_by = rvu.id
LEFT JOIN public.users op ON s.operator_id = op.id;

COMMENT ON VIEW public.v_reconciliation_records_full IS '差异记录完整视图';

-- 差异处理统计视图
CREATE OR REPLACE VIEW public.v_issue_process_stats AS
SELECT 
    s.id AS session_id,
    s.session_name,
    COUNT(rec.id) AS total_issues,
    COUNT(*) FILTER (WHERE rec.process_status = 'pending') AS pending_issues,
    COUNT(*) FILTER (WHERE rec.process_status = 'processing') AS processing_issues,
    COUNT(*) FILTER (WHERE rec.process_status = 'resolved') AS resolved_issues,
    COUNT(*) FILTER (WHERE rec.process_status = 'ignored') AS ignored_issues,
    COUNT(*) FILTER (WHERE rec.process_status = 'escalated') AS escalated_issues,
    ROUND(
        COUNT(*) FILTER (WHERE rec.process_status IN ('resolved', 'ignored')) * 100.0 / 
        NULLIF(COUNT(*), 0), 1
    ) AS process_rate
FROM public.reconciliation_sessions s
LEFT JOIN public.reconciliation_file_groups fg ON s.id = fg.session_id
LEFT JOIN public.reconciliation_result_records rec ON fg.id = rec.file_group_id
GROUP BY s.id, s.session_name;

COMMENT ON VIEW public.v_issue_process_stats IS '差异处理统计视图';

-- =============================================================================
-- Migration complete
-- =============================================================================
