--
-- Migration: Initial schema from tally database
-- Source: PostgreSQL tally database (pg_dump --schema-only)
-- Generated: 2026-02
--
-- Run order: Execute this file on an empty database to create full schema
--

-- =============================================================================
-- 1. Extensions
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;

-- =============================================================================
-- 2. Functions
-- =============================================================================
CREATE OR REPLACE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

-- =============================================================================
-- 3. Base tables (no FK dependencies)
-- =============================================================================

-- company
CREATE TABLE public.company (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    name character varying(255) NOT NULL,
    code character varying(50) NOT NULL,
    max_users integer DEFAULT 100,
    max_departments integer DEFAULT 10,
    enabled_features jsonb DEFAULT '["reconciliation", "data_prep"]'::jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    status character varying(20) DEFAULT 'active'::character varying,
    CONSTRAINT company_status_check CHECK (((status)::text = ANY (ARRAY['active'::text, 'suspended'::text, 'deleted'::text])))
);
COMMENT ON TABLE public.company IS '公司表';
COMMENT ON COLUMN public.company.enabled_features IS '启用的功能列表，JSON数组';

-- admins
CREATE TABLE public.admins (
    id integer NOT NULL,
    username character varying(50) NOT NULL,
    password character varying(255) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);
CREATE SEQUENCE public.admins_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.admins_id_seq OWNED BY public.admins.id;
ALTER TABLE ONLY public.admins ALTER COLUMN id SET DEFAULT nextval('public.admins_id_seq'::regclass);

-- =============================================================================
-- 4. departments (depends on company)
-- =============================================================================
CREATE TABLE public.departments (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    company_id uuid NOT NULL,
    parent_id uuid,
    name character varying(255) NOT NULL,
    code character varying(50) NOT NULL,
    description text,
    settings jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE public.departments IS '部门表，支持层级结构';
COMMENT ON COLUMN public.departments.settings IS '部门配置，如权限、审批流程等';

-- =============================================================================
-- 5. users (depends on company, departments)
-- =============================================================================
CREATE TABLE public.users (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    username character varying(50) NOT NULL,
    password_hash character varying(255) NOT NULL,
    email character varying(255),
    phone character varying(20),
    department_id uuid,
    company_id uuid,
    role character varying(20) DEFAULT 'member'::character varying,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    last_login timestamp with time zone,
    status character varying(20) DEFAULT 'active'::character varying,
    CONSTRAINT users_role_check CHECK (((role)::text = ANY (ARRAY['admin'::text, 'manager'::text, 'member'::text]))),
    CONSTRAINT users_status_check CHECK (((status)::text = ANY (ARRAY['active'::text, 'inactive'::text, 'suspended'::text])))
);
COMMENT ON TABLE public.users IS '用户表';
COMMENT ON COLUMN public.users.role IS 'admin: 管理员, manager: 部门经理, member: 普通成员';

-- =============================================================================
-- 6. audit_logs (depends on users)
-- =============================================================================
CREATE TABLE public.audit_logs (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid,
    action character varying(100) NOT NULL,
    entity_type character varying(50),
    entity_id uuid,
    details jsonb,
    ip_address inet,
    user_agent text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE public.audit_logs IS '审计日志表';

-- =============================================================================
-- 7. conversations (depends on users)
-- =============================================================================
CREATE TABLE public.conversations (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    title text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    status character varying(20) DEFAULT 'active'::character varying
);
COMMENT ON TABLE public.conversations IS 'User chat conversations';

-- =============================================================================
-- 8. messages (depends on conversations)
-- =============================================================================
CREATE TABLE public.messages (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    conversation_id uuid NOT NULL,
    role character varying(20) NOT NULL,
    content text NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb,
    attachments jsonb DEFAULT '[]'::jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE public.messages IS 'Messages within conversations';
COMMENT ON COLUMN public.messages.attachments IS 'Array of file attachments. Format: [{"name": "...", "path": "...", "size": ...}]';

-- =============================================================================
-- 9. reconciliation_rules (depends on users, departments, company)
-- =============================================================================
CREATE TABLE public.reconciliation_rules (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    created_by uuid NOT NULL,
    department_id uuid,
    company_id uuid,
    visibility character varying(20) DEFAULT 'private'::character varying,
    shared_with_users uuid[] DEFAULT ARRAY[]::uuid[],
    rule_template jsonb NOT NULL,
    version character varying(20) DEFAULT '1.0'::character varying,
    use_count integer DEFAULT 0,
    last_used_at timestamp with time zone,
    tags text[] DEFAULT ARRAY[]::text[],
    status character varying(20) DEFAULT 'active'::character varying,
    approved_by uuid,
    approved_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    key_field_role character varying(50) GENERATED ALWAYS AS ((rule_template ->> 'key_field_role'::text)) STORED,
    field_mapping_hash character varying(32),
    CONSTRAINT reconciliation_rules_status_check CHECK (((status)::text = ANY (ARRAY['active'::text, 'archived'::text, 'pending_approval'::text]))),
    CONSTRAINT reconciliation_rules_visibility_check CHECK (((visibility)::text = ANY (ARRAY['private'::text, 'department'::text, 'company'::text])))
);
COMMENT ON TABLE public.reconciliation_rules IS '对账规则表';
COMMENT ON COLUMN public.reconciliation_rules.visibility IS 'private: 仅创建者, department: 部门共享, company: 公司共享';
COMMENT ON COLUMN public.reconciliation_rules.rule_template IS '完整的规则JSON，包含数据源、清洗规则、验证规则等';

-- =============================================================================
-- 10. reconciliation_tasks (depends on reconciliation_rules, users, departments)
-- =============================================================================
CREATE TABLE public.reconciliation_tasks (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    rule_id uuid NOT NULL,
    created_by uuid NOT NULL,
    department_id uuid,
    task_name character varying(255),
    finance_files jsonb,
    business_files jsonb,
    status character varying(20) DEFAULT 'pending'::character varying,
    progress integer DEFAULT 0,
    total_records integer,
    matched_records integer,
    unmatched_finance integer,
    unmatched_business integer,
    amount_mismatch integer,
    other_issues integer,
    result_summary jsonb,
    result_details jsonb,
    error_message text,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT reconciliation_tasks_status_check CHECK (((status)::text = ANY (ARRAY['pending'::text, 'running'::text, 'completed'::text, 'failed'::text, 'cancelled'::text])))
);
COMMENT ON TABLE public.reconciliation_tasks IS '对账任务执行记录';

-- =============================================================================
-- 11. rule_versions (depends on reconciliation_rules)
-- =============================================================================
CREATE TABLE public.rule_versions (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    rule_id uuid NOT NULL,
    version character varying(20) NOT NULL,
    rule_template jsonb NOT NULL,
    created_by uuid,
    change_summary text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE public.rule_versions IS '规则版本历史表';

-- =============================================================================
-- 12. rule_usage_logs (depends on reconciliation_rules, users, departments, reconciliation_tasks)
-- =============================================================================
CREATE TABLE public.rule_usage_logs (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    rule_id uuid NOT NULL,
    user_id uuid NOT NULL,
    department_id uuid,
    task_id uuid,
    action character varying(50),
    result_summary jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE public.rule_usage_logs IS '规则使用日志';

-- =============================================================================
-- 13. Primary keys & unique constraints
-- =============================================================================
-- =============================================================================
ALTER TABLE ONLY public.admins ADD CONSTRAINT admins_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.admins ADD CONSTRAINT admins_username_key UNIQUE (username);
ALTER TABLE ONLY public.company ADD CONSTRAINT company_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.company ADD CONSTRAINT company_code_key UNIQUE (code);
ALTER TABLE ONLY public.departments ADD CONSTRAINT departments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.departments ADD CONSTRAINT departments_company_id_code_key UNIQUE (company_id, code);
ALTER TABLE ONLY public.users ADD CONSTRAINT users_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.users ADD CONSTRAINT users_username_key UNIQUE (username);
ALTER TABLE ONLY public.users ADD CONSTRAINT users_email_key UNIQUE (email);
ALTER TABLE ONLY public.audit_logs ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.conversations ADD CONSTRAINT conversations_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.messages ADD CONSTRAINT messages_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.reconciliation_rules ADD CONSTRAINT reconciliation_rules_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.reconciliation_tasks ADD CONSTRAINT reconciliation_tasks_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.rule_versions ADD CONSTRAINT rule_versions_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.rule_versions ADD CONSTRAINT rule_versions_rule_id_version_key UNIQUE (rule_id, version);
ALTER TABLE ONLY public.rule_usage_logs ADD CONSTRAINT rule_usage_logs_pkey PRIMARY KEY (id);
-- =============================================================================
-- 15. Foreign keys
-- =============================================================================
ALTER TABLE ONLY public.departments ADD CONSTRAINT departments_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.departments ADD CONSTRAINT departments_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.departments(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.users ADD CONSTRAINT users_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.users ADD CONSTRAINT users_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.departments(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.audit_logs ADD CONSTRAINT audit_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.conversations ADD CONSTRAINT conversations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.messages ADD CONSTRAINT messages_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.reconciliation_rules ADD CONSTRAINT reconciliation_rules_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.reconciliation_rules ADD CONSTRAINT reconciliation_rules_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.departments(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.reconciliation_rules ADD CONSTRAINT reconciliation_rules_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.reconciliation_rules ADD CONSTRAINT reconciliation_rules_approved_by_fkey FOREIGN KEY (approved_by) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.reconciliation_tasks ADD CONSTRAINT reconciliation_tasks_rule_id_fkey FOREIGN KEY (rule_id) REFERENCES public.reconciliation_rules(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.reconciliation_tasks ADD CONSTRAINT reconciliation_tasks_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.reconciliation_tasks ADD CONSTRAINT reconciliation_tasks_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.departments(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.rule_versions ADD CONSTRAINT rule_versions_rule_id_fkey FOREIGN KEY (rule_id) REFERENCES public.reconciliation_rules(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.rule_versions ADD CONSTRAINT rule_versions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.rule_usage_logs ADD CONSTRAINT rule_usage_logs_rule_id_fkey FOREIGN KEY (rule_id) REFERENCES public.reconciliation_rules(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.rule_usage_logs ADD CONSTRAINT rule_usage_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.rule_usage_logs ADD CONSTRAINT rule_usage_logs_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.departments(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.rule_usage_logs ADD CONSTRAINT rule_usage_logs_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.reconciliation_tasks(id) ON DELETE SET NULL;

-- =============================================================================
-- 16. Indexes
-- =============================================================================
CREATE INDEX idx_company_code ON public.company USING btree (code);
CREATE INDEX idx_company_status ON public.company USING btree (status);
CREATE INDEX idx_departments_company ON public.departments USING btree (company_id);
CREATE INDEX idx_departments_parent ON public.departments USING btree (parent_id);
CREATE INDEX idx_departments_code ON public.departments USING btree (company_id, code);
CREATE INDEX idx_users_username ON public.users USING btree (username);
CREATE INDEX idx_users_email ON public.users USING btree (email);
CREATE INDEX idx_users_department ON public.users USING btree (department_id);
CREATE INDEX idx_users_company ON public.users USING btree (company_id);
CREATE INDEX idx_users_status ON public.users USING btree (status);
CREATE INDEX idx_audit_user ON public.audit_logs USING btree (user_id);
CREATE INDEX idx_audit_action ON public.audit_logs USING btree (action);
CREATE INDEX idx_audit_created ON public.audit_logs USING btree (created_at DESC);
CREATE INDEX idx_conversations_user_id ON public.conversations USING btree (user_id);
CREATE INDEX idx_conversations_updated_at ON public.conversations USING btree (updated_at DESC);
CREATE INDEX idx_messages_conversation_id ON public.messages USING btree (conversation_id);
CREATE INDEX idx_messages_created_at ON public.messages USING btree (created_at);
CREATE INDEX idx_messages_attachments ON public.messages USING gin (attachments);
CREATE INDEX idx_rules_created_by ON public.reconciliation_rules USING btree (created_by);
CREATE INDEX idx_rules_department ON public.reconciliation_rules USING btree (department_id);
CREATE INDEX idx_rules_company ON public.reconciliation_rules USING btree (company_id);
CREATE INDEX idx_rules_status ON public.reconciliation_rules USING btree (status);
CREATE INDEX idx_rules_visibility ON public.reconciliation_rules USING btree (visibility);
CREATE INDEX idx_rules_key_field ON public.reconciliation_rules USING btree (key_field_role);
CREATE INDEX idx_rules_field_mapping_hash ON public.reconciliation_rules USING btree (field_mapping_hash);
CREATE INDEX idx_rules_tags ON public.reconciliation_rules USING gin (tags);
CREATE INDEX idx_rules_template_gin ON public.reconciliation_rules USING gin (rule_template);
CREATE INDEX idx_tasks_rule ON public.reconciliation_tasks USING btree (rule_id);
CREATE INDEX idx_tasks_created_by ON public.reconciliation_tasks USING btree (created_by);
CREATE INDEX idx_tasks_status ON public.reconciliation_tasks USING btree (status);
CREATE INDEX idx_tasks_created ON public.reconciliation_tasks USING btree (created_at DESC);
CREATE INDEX idx_tasks_result_gin ON public.reconciliation_tasks USING gin (result_summary);
CREATE INDEX idx_rule_versions_rule ON public.rule_versions USING btree (rule_id);
CREATE INDEX idx_rule_versions_created ON public.rule_versions USING btree (created_at DESC);
CREATE INDEX idx_usage_logs_rule ON public.rule_usage_logs USING btree (rule_id);
CREATE INDEX idx_usage_logs_user ON public.rule_usage_logs USING btree (user_id);
CREATE INDEX idx_usage_logs_created ON public.rule_usage_logs USING btree (created_at DESC);

-- =============================================================================
-- 17. Triggers
-- =============================================================================
CREATE TRIGGER update_company_updated_at BEFORE UPDATE ON public.company FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER update_departments_updated_at BEFORE UPDATE ON public.departments FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER update_rules_updated_at BEFORE UPDATE ON public.reconciliation_rules FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER update_tasks_updated_at BEFORE UPDATE ON public.reconciliation_tasks FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- =============================================================================
-- 18. Views
-- =============================================================================
CREATE VIEW public.v_rules_full AS
 SELECT r.id, r.name, r.description, r.visibility, r.version, r.use_count, r.status,
    r.created_at, r.last_used_at, r.key_field_role,
    u.username AS created_by_username,
    d.name AS department_name,
    c.name AS company_name
   FROM (((public.reconciliation_rules r
     LEFT JOIN public.users u ON ((r.created_by = u.id)))
     LEFT JOIN public.departments d ON ((r.department_id = d.id)))
     LEFT JOIN public.company c ON ((r.company_id = c.id)));

CREATE VIEW public.v_task_stats AS
 SELECT date(created_at) AS date,
    count(*) AS total_tasks,
    count(*) FILTER (WHERE ((status)::text = 'completed'::text)) AS completed_tasks,
    count(*) FILTER (WHERE ((status)::text = 'failed'::text)) AS failed_tasks,
    avg(EXTRACT(epoch FROM (completed_at - started_at))) FILTER (WHERE ((status)::text = 'completed'::text)) AS avg_duration_seconds
   FROM public.reconciliation_tasks
  GROUP BY (date(created_at))
  ORDER BY (date(created_at)) DESC;

CREATE VIEW public.v_users_full AS
 SELECT u.id, u.username, u.email, u.phone, u.role, u.status, u.created_at, u.last_login,
    d.name AS department_name,
    d.code AS department_code,
    c.name AS company_name,
    c.code AS company_code
   FROM ((public.users u
     LEFT JOIN public.departments d ON ((u.department_id = d.id)))
     LEFT JOIN public.company c ON ((u.company_id = c.id)));
