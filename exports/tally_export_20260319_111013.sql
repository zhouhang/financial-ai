--
-- PostgreSQL database dump
--

-- Dumped from database version 16.9 (Homebrew)
-- Dumped by pg_dump version 16.9 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

ALTER TABLE ONLY public.users DROP CONSTRAINT users_department_id_fkey;
ALTER TABLE ONLY public.users DROP CONSTRAINT users_company_id_fkey;
ALTER TABLE ONLY public.user_tasks DROP CONSTRAINT user_tasks_user_id_fkey;
ALTER TABLE ONLY public.rule_versions DROP CONSTRAINT rule_versions_rule_id_fkey;
ALTER TABLE ONLY public.rule_versions DROP CONSTRAINT rule_versions_created_by_fkey;
ALTER TABLE ONLY public.rule_usage_logs DROP CONSTRAINT rule_usage_logs_user_id_fkey;
ALTER TABLE ONLY public.rule_usage_logs DROP CONSTRAINT rule_usage_logs_task_id_fkey;
ALTER TABLE ONLY public.rule_usage_logs DROP CONSTRAINT rule_usage_logs_rule_id_fkey;
ALTER TABLE ONLY public.rule_usage_logs DROP CONSTRAINT rule_usage_logs_department_id_fkey;
ALTER TABLE ONLY public.rule_detail DROP CONSTRAINT rule_detail_task_id_fkey;
ALTER TABLE ONLY public.reconciliation_tasks DROP CONSTRAINT reconciliation_tasks_rule_id_fkey;
ALTER TABLE ONLY public.reconciliation_tasks DROP CONSTRAINT reconciliation_tasks_department_id_fkey;
ALTER TABLE ONLY public.reconciliation_tasks DROP CONSTRAINT reconciliation_tasks_created_by_fkey;
ALTER TABLE ONLY public.reconciliation_rules DROP CONSTRAINT reconciliation_rules_department_id_fkey;
ALTER TABLE ONLY public.reconciliation_rules DROP CONSTRAINT reconciliation_rules_created_by_fkey;
ALTER TABLE ONLY public.reconciliation_rules DROP CONSTRAINT reconciliation_rules_company_id_fkey;
ALTER TABLE ONLY public.reconciliation_rules DROP CONSTRAINT reconciliation_rules_approved_by_fkey;
ALTER TABLE ONLY public.messages DROP CONSTRAINT messages_conversation_id_fkey;
ALTER TABLE ONLY public.departments DROP CONSTRAINT departments_parent_id_fkey;
ALTER TABLE ONLY public.departments DROP CONSTRAINT departments_company_id_fkey;
ALTER TABLE ONLY public.conversations DROP CONSTRAINT conversations_user_id_fkey;
ALTER TABLE ONLY public.audit_logs DROP CONSTRAINT audit_logs_user_id_fkey;
DROP TRIGGER update_users_updated_at ON public.users;
DROP TRIGGER update_tasks_updated_at ON public.reconciliation_tasks;
DROP TRIGGER update_rules_updated_at ON public.reconciliation_rules;
DROP TRIGGER update_departments_updated_at ON public.departments;
DROP TRIGGER update_company_updated_at ON public.company;
DROP INDEX public.unique_rule_code;
DROP INDEX public.idx_users_username;
DROP INDEX public.idx_users_status;
DROP INDEX public.idx_users_email;
DROP INDEX public.idx_users_department;
DROP INDEX public.idx_users_company;
DROP INDEX public.idx_user_tasks_user_id;
DROP INDEX public.idx_user_tasks_task_code;
DROP INDEX public.idx_usage_logs_user;
DROP INDEX public.idx_usage_logs_rule;
DROP INDEX public.idx_usage_logs_created;
DROP INDEX public.idx_tasks_status;
DROP INDEX public.idx_tasks_rule;
DROP INDEX public.idx_tasks_result_gin;
DROP INDEX public.idx_tasks_created_by;
DROP INDEX public.idx_tasks_created;
DROP INDEX public.idx_rules_visibility;
DROP INDEX public.idx_rules_template_gin;
DROP INDEX public.idx_rules_tags;
DROP INDEX public.idx_rules_status;
DROP INDEX public.idx_rules_key_field;
DROP INDEX public.idx_rules_field_mapping_hash;
DROP INDEX public.idx_rules_department;
DROP INDEX public.idx_rules_created_by;
DROP INDEX public.idx_rules_company;
DROP INDEX public.idx_rule_versions_rule;
DROP INDEX public.idx_rule_versions_created;
DROP INDEX public.idx_rule_detail_user_id;
DROP INDEX public.idx_rule_detail_task_id;
DROP INDEX public.idx_rule_detail_rule_code;
DROP INDEX public.idx_rule_detail_name;
DROP INDEX public.idx_messages_created_at;
DROP INDEX public.idx_messages_conversation_id;
DROP INDEX public.idx_messages_attachments;
DROP INDEX public.idx_guest_tokens_token;
DROP INDEX public.idx_guest_tokens_session;
DROP INDEX public.idx_guest_tokens_expires;
DROP INDEX public.idx_departments_parent;
DROP INDEX public.idx_departments_company;
DROP INDEX public.idx_departments_code;
DROP INDEX public.idx_conversations_user_id;
DROP INDEX public.idx_conversations_updated_at;
DROP INDEX public.idx_company_status;
DROP INDEX public.idx_company_code;
DROP INDEX public.idx_audit_user;
DROP INDEX public.idx_audit_created;
DROP INDEX public.idx_audit_action;
ALTER TABLE ONLY public.users DROP CONSTRAINT users_username_key;
ALTER TABLE ONLY public.users DROP CONSTRAINT users_pkey;
ALTER TABLE ONLY public.users DROP CONSTRAINT users_email_key;
ALTER TABLE ONLY public.user_tasks DROP CONSTRAINT user_tasks_pkey;
ALTER TABLE ONLY public.rule_versions DROP CONSTRAINT rule_versions_rule_id_version_key;
ALTER TABLE ONLY public.rule_versions DROP CONSTRAINT rule_versions_pkey;
ALTER TABLE ONLY public.rule_usage_logs DROP CONSTRAINT rule_usage_logs_pkey;
ALTER TABLE ONLY public.rule_detail DROP CONSTRAINT rule_code;
ALTER TABLE ONLY public.reconciliation_tasks DROP CONSTRAINT reconciliation_tasks_pkey;
ALTER TABLE ONLY public.reconciliation_rules DROP CONSTRAINT reconciliation_rules_pkey;
ALTER TABLE ONLY public.messages DROP CONSTRAINT messages_pkey;
ALTER TABLE ONLY public.guest_auth_tokens DROP CONSTRAINT guest_auth_tokens_pkey;
ALTER TABLE ONLY public.departments DROP CONSTRAINT departments_pkey;
ALTER TABLE ONLY public.departments DROP CONSTRAINT departments_company_id_code_key;
ALTER TABLE ONLY public.conversations DROP CONSTRAINT conversations_pkey;
ALTER TABLE ONLY public.company DROP CONSTRAINT company_pkey;
ALTER TABLE ONLY public.company DROP CONSTRAINT company_code_key;
ALTER TABLE ONLY public.rule_detail DROP CONSTRAINT bus_file_rules_pkey;
ALTER TABLE ONLY public.audit_logs DROP CONSTRAINT audit_logs_pkey;
ALTER TABLE ONLY public.admins DROP CONSTRAINT admins_username_key;
ALTER TABLE ONLY public.admins DROP CONSTRAINT admins_pkey;
ALTER TABLE public.admins ALTER COLUMN id DROP DEFAULT;
DROP VIEW public.v_users_full;
DROP VIEW public.v_task_stats;
DROP VIEW public.v_rules_full;
DROP TABLE public.users;
DROP TABLE public.user_tasks;
DROP TABLE public.rule_versions;
DROP TABLE public.rule_usage_logs;
DROP TABLE public.rule_detail;
DROP TABLE public.reconciliation_tasks;
DROP TABLE public.reconciliation_rules;
DROP TABLE public.messages;
DROP TABLE public.guest_auth_tokens;
DROP TABLE public.departments;
DROP TABLE public.conversations;
DROP TABLE public.company;
DROP TABLE public.audit_logs;
DROP SEQUENCE public.admins_id_seq;
DROP TABLE public.admins;
DROP FUNCTION public.update_updated_at_column();
DROP EXTENSION "uuid-ossp";
DROP EXTENSION pgcrypto;
--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';


--
-- Name: update_updated_at_column(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: admins; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.admins (
    id integer NOT NULL,
    username character varying(50) NOT NULL,
    password character varying(255) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: admins_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.admins_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: admins_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.admins_id_seq OWNED BY public.admins.id;


--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: -
--

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


--
-- Name: TABLE audit_logs; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.audit_logs IS '审计日志表';


--
-- Name: company; Type: TABLE; Schema: public; Owner: -
--

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
    CONSTRAINT company_status_check CHECK (((status)::text = ANY (ARRAY[('active'::character varying)::text, ('suspended'::character varying)::text, ('deleted'::character varying)::text])))
);


--
-- Name: COLUMN company.enabled_features; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.company.enabled_features IS '启用的功能列表，JSON数组';


--
-- Name: conversations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conversations (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    title text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    status character varying(20) DEFAULT 'active'::character varying
);


--
-- Name: TABLE conversations; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.conversations IS 'User chat conversations';


--
-- Name: departments; Type: TABLE; Schema: public; Owner: -
--

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


--
-- Name: TABLE departments; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.departments IS '部门表，支持层级结构';


--
-- Name: COLUMN departments.settings; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.departments.settings IS '部门配置，如权限、审批流程等';


--
-- Name: guest_auth_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.guest_auth_tokens (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    token character varying(64) NOT NULL,
    session_id character varying(64),
    usage_count integer DEFAULT 0,
    max_usage integer DEFAULT 3,
    ip_address inet,
    user_agent text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamp with time zone NOT NULL
);


--
-- Name: TABLE guest_auth_tokens; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.guest_auth_tokens IS '游客临时认证token表';


--
-- Name: COLUMN guest_auth_tokens.token; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.guest_auth_tokens.token IS '唯一token值';


--
-- Name: COLUMN guest_auth_tokens.session_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.guest_auth_tokens.session_id IS '关联的会话ID';


--
-- Name: COLUMN guest_auth_tokens.usage_count; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.guest_auth_tokens.usage_count IS '已使用次数';


--
-- Name: COLUMN guest_auth_tokens.max_usage; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.guest_auth_tokens.max_usage IS '最大使用次数';


--
-- Name: COLUMN guest_auth_tokens.ip_address; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.guest_auth_tokens.ip_address IS '用户IP地址';


--
-- Name: COLUMN guest_auth_tokens.expires_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.guest_auth_tokens.expires_at IS '过期时间';


--
-- Name: messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.messages (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    conversation_id uuid NOT NULL,
    role character varying(20) NOT NULL,
    content text NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb,
    attachments jsonb DEFAULT '[]'::jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: TABLE messages; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.messages IS 'Messages within conversations';


--
-- Name: COLUMN messages.attachments; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.messages.attachments IS 'Array of file attachments associated with this message. Format: [{"name": "...", "path": "...", "size": ...}]';


--
-- Name: reconciliation_rules; Type: TABLE; Schema: public; Owner: -
--

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
    CONSTRAINT reconciliation_rules_status_check CHECK (((status)::text = ANY (ARRAY[('active'::character varying)::text, ('archived'::character varying)::text, ('pending_approval'::character varying)::text]))),
    CONSTRAINT reconciliation_rules_visibility_check CHECK (((visibility)::text = ANY (ARRAY[('private'::character varying)::text, ('department'::character varying)::text, ('company'::character varying)::text])))
);


--
-- Name: TABLE reconciliation_rules; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.reconciliation_rules IS '对账规则表';


--
-- Name: COLUMN reconciliation_rules.visibility; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.reconciliation_rules.visibility IS 'private: 仅创建者, department: 部门共享, company: 公司共享';


--
-- Name: COLUMN reconciliation_rules.rule_template; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.reconciliation_rules.rule_template IS '完整的规则JSON，包含数据源、清洗规则、验证规则等';


--
-- Name: reconciliation_tasks; Type: TABLE; Schema: public; Owner: -
--

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
    CONSTRAINT reconciliation_tasks_status_check CHECK (((status)::text = ANY (ARRAY[('pending'::character varying)::text, ('running'::character varying)::text, ('completed'::character varying)::text, ('failed'::character varying)::text, ('cancelled'::character varying)::text])))
);


--
-- Name: TABLE reconciliation_tasks; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.reconciliation_tasks IS '对账任务执行记录';


--
-- Name: rule_detail; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rule_detail (
    id integer NOT NULL,
    rule_code character varying(64),
    rule jsonb,
    remark character varying(256),
    rule_type character varying(20),
    user_id uuid,
    name character varying(255),
    task_id integer
);


--
-- Name: COLUMN rule_detail.rule_code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.rule_detail.rule_code IS '规则编码';


--
-- Name: COLUMN rule_detail.rule; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.rule_detail.rule IS 'rule_json内容';


--
-- Name: COLUMN rule_detail.rule_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.rule_detail.rule_type IS 'bus.业务规则;file.文件规则';


--
-- Name: rule_usage_logs; Type: TABLE; Schema: public; Owner: -
--

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


--
-- Name: TABLE rule_usage_logs; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.rule_usage_logs IS '规则使用日志';


--
-- Name: rule_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rule_versions (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    rule_id uuid NOT NULL,
    version character varying(20) NOT NULL,
    rule_template jsonb NOT NULL,
    created_by uuid,
    change_summary text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: TABLE rule_versions; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.rule_versions IS '规则版本历史表';


--
-- Name: user_tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_tasks (
    id integer NOT NULL,
    user_id uuid,
    task_code character varying(255) NOT NULL,
    task_name character varying(255) NOT NULL,
    description text
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

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
    CONSTRAINT users_role_check CHECK (((role)::text = ANY (ARRAY[('admin'::character varying)::text, ('manager'::character varying)::text, ('member'::character varying)::text]))),
    CONSTRAINT users_status_check CHECK (((status)::text = ANY (ARRAY[('active'::character varying)::text, ('inactive'::character varying)::text, ('suspended'::character varying)::text])))
);


--
-- Name: TABLE users; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.users IS '用户表';


--
-- Name: COLUMN users.role; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.users.role IS 'admin: 管理员, manager: 部门经理, member: 普通成员';


--
-- Name: v_rules_full; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_rules_full AS
 SELECT r.id,
    r.name,
    r.description,
    r.visibility,
    r.version,
    r.use_count,
    r.status,
    r.created_at,
    r.last_used_at,
    r.key_field_role,
    u.username AS created_by_username,
    d.name AS department_name,
    c.name AS company_name
   FROM (((public.reconciliation_rules r
     LEFT JOIN public.users u ON ((r.created_by = u.id)))
     LEFT JOIN public.departments d ON ((r.department_id = d.id)))
     LEFT JOIN public.company c ON ((r.company_id = c.id)));


--
-- Name: v_task_stats; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_task_stats AS
 SELECT date(created_at) AS date,
    count(*) AS total_tasks,
    count(*) FILTER (WHERE ((status)::text = 'completed'::text)) AS completed_tasks,
    count(*) FILTER (WHERE ((status)::text = 'failed'::text)) AS failed_tasks,
    avg(EXTRACT(epoch FROM (completed_at - started_at))) FILTER (WHERE ((status)::text = 'completed'::text)) AS avg_duration_seconds
   FROM public.reconciliation_tasks
  GROUP BY (date(created_at))
  ORDER BY (date(created_at)) DESC;


--
-- Name: v_users_full; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_users_full AS
 SELECT u.id,
    u.username,
    u.email,
    u.phone,
    u.role,
    u.status,
    u.created_at,
    u.last_login,
    d.name AS department_name,
    d.code AS department_code,
    c.name AS company_name,
    c.code AS company_code
   FROM ((public.users u
     LEFT JOIN public.departments d ON ((u.department_id = d.id)))
     LEFT JOIN public.company c ON ((u.company_id = c.id)));


--
-- Name: admins id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admins ALTER COLUMN id SET DEFAULT nextval('public.admins_id_seq'::regclass);


--
-- Data for Name: admins; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.admins (id, username, password, created_at) FROM stdin;
1	admin	92925488b28ab12584ac8fcaa8a27a0f497b2c62940c8f4fbc8ef19ebc87c43e	2026-02-19 10:27:27.267257
\.


--
-- Data for Name: audit_logs; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.audit_logs (id, user_id, action, entity_type, entity_id, details, ip_address, user_agent, created_at) FROM stdin;
\.


--
-- Data for Name: company; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.company (id, name, code, max_users, max_departments, enabled_features, created_at, updated_at, status) FROM stdin;
00000000-0000-0000-0000-000000000001	示例公司	DEMO_COMPANY	1000	100	["reconciliation", "data_prep"]	2026-02-10 16:11:16.32517+08	2026-02-10 16:11:16.32517+08	active
ef39a863-6ab7-4f99-bb78-236170d38117	武汉岚晨网络科技有限公司	COMP_83035BAF	100	10	["reconciliation", "data_prep"]	2026-02-19 16:30:56.871353+08	2026-02-25 10:18:15.898601+08	active
c2a4b2b8-2afd-41ae-91ab-23df1ac97fc1	测试部	COMP_3BE8A888	100	10	["reconciliation", "data_prep"]	2026-03-04 15:32:19.755906+08	2026-03-04 15:32:19.755906+08	active
\.


--
-- Data for Name: conversations; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.conversations (id, user_id, title, created_at, updated_at, status) FROM stdin;
d64aadc1-818f-4643-8267-b8bfc48cbf25	00000000-0000-0000-0000-000000000003	规则列表	2026-03-05 15:24:20.880403	2026-03-18 19:50:01.743037	active
\.


--
-- Data for Name: departments; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.departments (id, company_id, parent_id, name, code, description, settings, created_at, updated_at) FROM stdin;
00000000-0000-0000-0000-000000000002	00000000-0000-0000-0000-000000000001	\N	财务部	FINANCE	财务对账部门	{}	2026-02-10 16:11:16.327623+08	2026-02-10 16:11:16.327623+08
063eae86-62ee-43f9-ac81-7776c25ecb7c	ef39a863-6ab7-4f99-bb78-236170d38117	\N	资产部	DEPT_3EF4E97B	\N	{}	2026-02-19 16:31:29.88011+08	2026-02-25 10:18:30.09625+08
4a0127f2-98ae-4769-a9c1-5de3334af801	ef39a863-6ab7-4f99-bb78-236170d38117	\N	核算部	DEPT_7CD78C2B	\N	{}	2026-02-19 16:40:06.467791+08	2026-02-25 10:18:30.09625+08
3f3cd4fd-eca3-4783-8273-cd94c284d4c7	c2a4b2b8-2afd-41ae-91ab-23df1ac97fc1	\N	测试一组	DEPT_E48C5851	\N	{}	2026-03-04 15:32:38.377629+08	2026-03-04 15:32:38.377629+08
\.


--
-- Data for Name: guest_auth_tokens; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.guest_auth_tokens (id, token, session_id, usage_count, max_usage, ip_address, user_agent, created_at, expires_at) FROM stdin;
7f415bb3-c88a-4827-9bf1-5be401079374	c_KuWlMvgFy1cyptIYzl6ySlL4I7RwKu5Kxfdj3n8xs	guest_unknown	0	3	\N	\N	2026-02-25 13:57:12.522898+08	2026-03-04 13:57:12.503664+08
cf508916-0b90-4e03-b3ed-d93723a95844	LbBusgllyUyqCrRczzQ6t2q8MwCLFc2jpcSi9ZoTatw	guest_unknown	0	3	\N	\N	2026-02-25 13:57:24.255981+08	2026-03-04 13:57:24.242829+08
882b7448-4a65-4d74-95c9-f3522c5c1495	moddI_xCaUD_VoFOQVCwaq-eN2g_LmgOFYXIr7tr1p8	guest_unknown	0	3	\N	\N	2026-02-25 13:57:42.674008+08	2026-03-04 13:57:42.659466+08
05993f39-cca9-41be-b90b-66e8df14b655	Xb9IbQzpy0E1e2P_mAsv29Hxc9pXN9af1kbXu5_imqo	guest_unknown	0	3	\N	\N	2026-02-25 13:58:26.586299+08	2026-03-04 13:58:26.575033+08
859e8373-8712-4d85-a384-8937b7f7b596	UscqjNQbaE_OEXOSfaILnnRp-MvAhyaL4eSsZ1FkLmE	guest_unknown	0	3	\N	\N	2026-02-25 14:03:25.013326+08	2026-03-04 14:03:24.995077+08
eee168a5-3240-4e7b-9b49-4bef4368f733	sz-sXta99ZKTIYxHlUPI7_9FrPzI_ui0gvgBEef5rPM	guest_unknown	0	3	\N	\N	2026-02-25 14:18:35.914517+08	2026-03-04 14:18:35.894232+08
99768dad-174b-40f1-9ba3-b4fce28aeb04	dJAbJOf2AJhm2ozi-YFJI_22lXq2ewOF3bMOw0QbdIU	guest_unknown	0	3	\N	\N	2026-02-25 14:22:14.952831+08	2026-03-04 14:22:14.937345+08
e4c63a2c-75f1-40fc-8cd3-6fd2bd2e6790	krh9dCwyMPPdMmp4AhpzClG-sCruYF371__QZZA9B6M	guest_unknown	0	3	\N	\N	2026-02-25 14:46:42.401171+08	2026-03-04 14:46:42.386714+08
4b8ccac7-273a-4ce3-882b-90a08645d4e5	K-8GKyQcSLL5Mfy5CrcT-hNvQDhzuW3IkIYySRKAPHY	guest_unknown	0	3	\N	\N	2026-02-25 15:01:21.484661+08	2026-03-04 15:01:21.471691+08
e574f376-52c1-4161-a989-3f25f2cc04ca	mRfuuXUWC6FEGEgJYK9Wir6xpC43v4IXsnvH0GLKW7k	guest_unknown	0	3	\N	\N	2026-02-25 15:03:52.077429+08	2026-03-04 15:03:52.063231+08
2ad084f6-bb1c-42bc-84c6-8c92725db52c	kcdFZdMmSBeAusJYc_lV5_9TGr0igCQcQlmUOfhvKYs	guest_unknown	0	3	\N	\N	2026-02-25 15:06:45.543925+08	2026-03-04 15:06:45.523547+08
71c22150-05f2-4a14-8b04-0e7466a7475a	xol0lxgk8A-Ye_F_0wm6jgGrfVvIng4e9WuIOOPAtvA	guest_unknown	0	3	\N	\N	2026-02-25 15:13:31.659822+08	2026-03-04 15:13:31.642672+08
5a832bc2-8f35-4b8d-bd85-df6a741bc3f2	HhP5_xUPSYba5tadaD4FvHfSWY7NMhPbHPneKMpFdXU	guest_unknown	0	3	\N	\N	2026-02-25 15:23:55.657705+08	2026-03-04 15:23:55.623237+08
316e18e1-e4b0-4323-a9dd-abfbb5039eba	JQA2u8Hw9aj4U_Sr7HtE1iGkV5cd-DXrspZ1CGpIbYg	guest_unknown	0	3	\N	\N	2026-02-25 15:27:55.382301+08	2026-03-04 15:27:55.369728+08
00e38082-1079-4eac-a86a-e7a32d32c13a	M4ee0MGwYH_fKfPoUdt8dNAY55s_JRnM6uaxSvI9m_k	guest_unknown	0	3	\N	\N	2026-02-25 15:30:56.199946+08	2026-03-04 15:30:56.185236+08
421e73ec-72eb-4b54-9e01-95e37e645a29	IMVRQfTtRAKpAZGE1e3jBHbIPDtU42-Dn9v0lgRqRW8	guest_unknown	0	3	\N	\N	2026-02-25 15:32:35.630741+08	2026-03-04 15:32:35.614046+08
eca9d26d-2276-407d-b7f1-eed0f2212518	PNb4LjVPARdtwO8CsN1V8NdSzaU3JtO2bZhzCkhpIa0	guest_unknown	0	3	\N	\N	2026-02-25 15:36:36.395692+08	2026-03-04 15:36:36.38211+08
edc00aaa-8b7a-4201-a237-46ee8e6cdfeb	yWs7Wyzt2fYVF7An9OJA5ovW_hISyqTgfSZZtdR9gXI	guest_unknown	0	3	\N	\N	2026-02-25 15:40:40.776053+08	2026-03-04 15:40:40.759277+08
bbade219-459d-465c-92f2-72ef15e789d1	qrP_kCb4_NMZ-mbqirkY41uD3Qb1MValvo-3MgksEpY	guest_unknown	0	3	\N	\N	2026-02-25 15:46:19.785871+08	2026-03-04 15:46:19.770735+08
e0c24262-0fed-4387-a3c6-bf9cbdb0c79b	_j1xkwZOe2oyNFc5w3RzGnNkEyYDl3rI79_5pO_BzbE	guest_unknown	0	3	\N	\N	2026-02-25 15:50:19.469289+08	2026-03-04 15:50:19.395383+08
2cd2dc00-093c-4d8d-8c79-c4e00397192c	S-AVpNonpp8souy-TM3xJzyRoDiS-CqPtGp7pY_VRdE	guest_unknown	0	3	\N	\N	2026-02-25 15:53:50.261166+08	2026-03-04 15:53:50.244803+08
9419f190-9783-4ee1-ba57-7bf54a3aeb2e	HL-akb8ZtbKi8lCtW_wCFNzd4TMVl2n6PnQJFI3NGBE	guest_unknown	0	3	\N	\N	2026-02-25 15:55:50.17893+08	2026-03-04 15:55:50.165856+08
0e2d9a53-ea4b-4848-a5a3-43df5e258567	RmuzN_YhaIyzc45kzSPYbhQ7BBO9c_7XkGtlbzWPgPI	guest_unknown	0	3	\N	\N	2026-02-25 15:58:29.047693+08	2026-03-04 15:58:29.031317+08
ddd8dc90-a5f3-4f3d-8b75-40e4daae36af	E5IZAMeQhUnFHnB-oo16d19nx7ToLo5LDOfyqHCB9I4	guest_unknown	0	3	\N	\N	2026-02-25 16:05:01.608067+08	2026-03-04 16:05:01.586208+08
5f7be537-005f-4d49-9e47-327bfd062e91	F5hXRdE2W1lEpULI7bNER_Lpr7wNgVb-F50F8n8VhjE	guest_unknown	0	3	\N	\N	2026-02-25 16:19:30.002855+08	2026-03-04 16:19:29.984739+08
aa012933-a367-4313-a90b-c08cf445717a	M1Q2nlc2_ZhKhn4fO7FWocCPehWuV3nQ7uQTbdwrYrQ	guest_unknown	0	3	\N	\N	2026-02-25 16:24:40.505696+08	2026-03-04 16:24:40.488209+08
f35d78d3-49d1-43e6-9a1c-78f3e31c5b1c	QzZO1yYwBtiADjT2Wy16e_borOekdmAAhZWdTMEcIa8	guest_unknown	0	3	\N	\N	2026-02-25 16:31:47.736228+08	2026-03-04 16:31:47.713772+08
d3ad4582-68f4-456c-b796-bba9dd439f97	xL4SDqIGNHFJRVwTeuqT23PudtnTNvse-fJHt4cLoW0	guest_unknown	0	3	\N	\N	2026-02-25 16:44:52.597119+08	2026-03-04 16:44:52.447911+08
4123ee07-8272-4071-90ee-2acaf38de5a5	mTKk54FAhnQ_aFlbit0g5md-PNa4u1zN_g7p5wp09RY	guest_unknown	0	3	\N	\N	2026-02-25 16:53:55.998626+08	2026-03-04 16:53:55.98554+08
3bfd7428-b98a-4dc8-bf21-37078a19d795	KLwf7B1KvYJls_dzW35xj81qy_qy_VJFqToqCd5Jdlk	guest_unknown	0	3	\N	\N	2026-02-25 17:09:21.288984+08	2026-03-04 17:09:21.27362+08
28562076-9375-4bf4-be2b-15c42a88c8f0	A8AALgZIdhtmkep52bn1RC8UU3Cd2ik_tJg2zQpTOqg	guest_unknown	0	3	\N	\N	2026-02-25 17:21:24.266485+08	2026-03-04 17:21:24.25408+08
bbabee89-8a01-4b03-8ac7-cc4e22fc781b	rNODnpA5WAoMO7RwtxgkRyUKF8mtTR0vqsj3dxkNORc	guest_unknown	0	3	\N	\N	2026-02-25 17:45:57.014632+08	2026-03-04 17:45:57.004488+08
f7e335c7-5e7e-4684-99c1-76eb2ac3e4d1	xC6yQv6w4AQ8rNzoNOW6g1OQS9RkpojNoNH-LNveEd4	guest_unknown	0	3	\N	\N	2026-02-25 17:58:38.692394+08	2026-03-04 17:58:38.683727+08
e4ab0d7f-6cde-4d80-acaa-f626a4b9168c	52tGLIVTierU0k20gI2djWTvdMbyVpMychHYGfjhEFw	guest_unknown	0	3	\N	\N	2026-02-25 18:14:22.014646+08	2026-03-04 18:14:22.004946+08
e7835576-1194-42cd-89b9-46437e377ab3	59zld16DEF0W4h8mG7UPRtOStOw5eIxZ5jbJcVachn8	guest_unknown	0	3	\N	\N	2026-02-25 18:16:05.939074+08	2026-03-04 18:16:05.93131+08
f2853e29-41ad-4a57-b144-1f4c329b23fc	2egrzLRA9PPqKHHFIIi-LM6hquhR_eRmjeIEOQZXmv4	guest_unknown	0	3	\N	\N	2026-02-25 18:21:01.684636+08	2026-03-04 18:21:01.662163+08
4c23640f-1d0b-45ec-ae25-56899106f03c	hPedRiAOCs93fxSB5Ii8aTt_Vmg8Rd4EBcbf2zNzjgU	guest_unknown	0	3	\N	\N	2026-02-25 18:35:26.432455+08	2026-03-04 18:35:26.412801+08
c3f3b862-9b5f-4f79-bdde-01177d33b3a2	nrUQAdzz3rhHhupq4l50gghCXxS9W3bgWkPlbjRYelE	guest_unknown	0	3	\N	\N	2026-02-25 18:41:16.700272+08	2026-03-04 18:41:16.661587+08
acc4b81a-dfba-4c60-8ea3-37c3357f79b8	PMo8pxy5ghyKgfjV-1cRv0AR0B63-kUC2ZCJdRhRiw0	guest_unknown	0	3	\N	\N	2026-02-25 19:21:40.522269+08	2026-03-04 19:21:40.502037+08
1527e8dd-f3f8-4b42-8cf6-5acdc2050ecf	5eelV1VIe3sG28T2Qh_BJQgqqgz807ktpCnf9A7LoRc	guest_unknown	0	3	\N	\N	2026-02-25 19:35:21.102465+08	2026-03-04 19:35:21.083811+08
d37923e3-7f8c-4998-8922-c692d92ef2fc	8MSBnPAo4o8wG3Gby0y-m7uuaGX4XYZgaPqFSkkp6LM	guest_unknown	0	3	\N	\N	2026-02-25 19:52:43.645898+08	2026-03-04 19:52:43.629247+08
f86af0ba-0bec-45f3-87f3-74d4fe0eeb0e	e_bZlKqez5lYobOL_J-i2aenUQQCZh9GivdwApa3pAI	guest_unknown	0	3	\N	\N	2026-02-26 11:14:12.482276+08	2026-03-05 11:14:12.472197+08
d1154930-b91f-4c76-9b0e-2c43b944bec0	QvOiQ1TRIWacW1bCW9Y838tPLuViX-0ZuWtnyghtzJU	guest_unknown	0	3	\N	\N	2026-02-26 12:11:05.509627+08	2026-03-05 12:11:05.50176+08
edefbd1e-ba04-4659-83d2-2160cc56c676	UHYEpVFrY5wQMhx-rlN3utG-a2p2nIrnaItcK6zHcNk	guest_unknown	0	3	\N	\N	2026-02-26 12:16:11.668469+08	2026-03-05 12:16:11.653558+08
8f6be9ba-aa32-4024-952d-45d23a14aa40	qD3kTn78WLfpPdbesQtHwkx7Unw5dTRgppDXVRNnZa0	guest_unknown	0	3	\N	\N	2026-02-26 13:37:18.917919+08	2026-03-05 13:37:18.90459+08
7dc8336c-649a-4a4b-b429-dabdca665923	x5KSrunuzs4az6TkFoMG74V6E_LSYPYsUwLrDjEWw-o	guest_unknown	0	3	\N	\N	2026-02-26 13:41:09.118946+08	2026-03-05 13:41:09.104147+08
120d06dc-a76d-4001-968e-e6b2fd405a54	yVHP09HdHWnF9F5MsUNX8Q40RiloqiNZcfcQ2ZzJLEE	guest_unknown	0	3	\N	\N	2026-02-26 13:46:40.807773+08	2026-03-05 13:46:40.790405+08
8137b74a-ab18-4685-8840-a95c83fe0ffb	kpiCYg6yJJo8QybTlGJ19R85NlS-tDm6YXQU_h9_XBA	guest_unknown	0	3	\N	\N	2026-02-26 13:53:18.28024+08	2026-03-05 13:53:18.269195+08
12034d00-e3b2-400b-a07b-df124bb04dd2	YQrkNZRpxfC_QOI7en8WLpYyOSKRTgdkJKsTwYgeAPs	guest_unknown	0	3	\N	\N	2026-02-26 14:01:55.125293+08	2026-03-05 14:01:54.808816+08
7b1d9b73-77fe-4fc0-97ce-2000f920d317	JSXq8iBRqdS6hmPik_LDB_uost13517Y_ClTc04rS74	guest_unknown	0	3	\N	\N	2026-02-26 14:06:12.370161+08	2026-03-05 14:06:12.352427+08
2881f944-61f8-4e55-90ab-280b0f85d245	WTq_djzXMulh_t_EVFKU46FTRqCZix3DBhyH321Hh4Y	guest_unknown	0	3	\N	\N	2026-02-26 14:23:57.910933+08	2026-03-05 14:23:57.892926+08
ac5b2c17-a631-48b0-89b6-2aaa5e76d34c	S6CRxRanMsYVWtUmWUG3RmXWaU3KgD5CnjTghoMs8As	guest_unknown	0	3	\N	\N	2026-02-26 14:44:44.820535+08	2026-03-05 14:44:44.806883+08
8f4d9e72-f998-478d-9f6a-a48f5fb1ebae	Gl8nS5hk8yFTmvHBVgFnX6IsyJbuq_e4r3l0vN_oGiU	guest_unknown	0	3	\N	\N	2026-02-26 14:48:06.279903+08	2026-03-05 14:48:06.260059+08
19c81640-84f0-433c-b816-89bc1258d750	XMjOOMdP5gnqFj1_vUHelvW8ob-D2WjylB94JhYxbcU	guest_unknown	0	3	\N	\N	2026-02-26 14:51:18.803147+08	2026-03-05 14:51:18.779722+08
d723159b-439b-45e7-be48-98c9a657040f	s0XGTn_JRlz_kCN_dzVZqdQIpPtlvAi2kRA4m37PZsE	guest_unknown	0	3	\N	\N	2026-02-26 15:05:41.84881+08	2026-03-05 15:05:41.819933+08
b130f3a1-552a-4105-a691-dcfb498cc426	zuaIqmcdh67NjmuwbpqgiCCIN8IT375LxDR5aQtfS3w	guest_unknown	0	3	\N	\N	2026-02-26 15:08:20.387507+08	2026-03-05 15:08:20.374146+08
d6b79e60-24a9-4b80-939e-29dcbd7447a8	zjH89QO3PvndFxxHhpuz-7WwgSGyFmfV1uRvePZ-l5w	guest_unknown	0	3	\N	\N	2026-02-26 15:18:05.084171+08	2026-03-05 15:18:04.931603+08
2066833e-0e8f-4ee7-a80f-92fbb209add5	MqTvisWueTZVIDiAXDZOa7CFrLqDCNAr5XYWEu9SQec	guest_unknown	0	3	\N	\N	2026-02-26 15:26:16.080134+08	2026-03-05 15:26:16.066882+08
8e7b10a3-adec-41e8-b031-f0efa1790ff1	UrrvfFVXmb0pGE0yM3ld1T1mIxwPvHYEJSVxGo1N2Vw	guest_unknown	0	3	\N	\N	2026-02-26 15:28:40.171582+08	2026-03-05 15:28:40.157416+08
f56c1ed0-e6e2-48de-a389-062dbd3b63f3	yqLYL1W-IdPNpqKa6Ao4_7toktrBriHYVYD8a7sFAr4	guest_unknown	0	3	\N	\N	2026-02-26 15:36:24.21273+08	2026-03-05 15:36:24.19114+08
059a82c7-120f-4d6b-a27c-e6ebf8ee83af	ulBGVNzef_dA7SqVPAww-mQBc2cOgE-dKt6mOVFG7wQ	guest_unknown	0	3	\N	\N	2026-02-26 15:53:43.316544+08	2026-03-05 15:53:43.274036+08
7c5d0eb2-50bd-44cd-bf96-b3056980387a	ua8S3LLHZsXGsta1or2WtgMWGRKJ9ndVhDKnPXzOUTQ	guest_unknown	0	3	\N	\N	2026-02-26 15:56:49.231152+08	2026-03-05 15:56:49.222876+08
b41ae547-bd99-4d21-8afa-2f59a5da3593	NsGVWP8c4nTKE0tSsJZqlfnHxL5uOCKsxdsSq5ZPb-s	guest_unknown	0	3	\N	\N	2026-02-26 16:04:48.072682+08	2026-03-05 16:04:48.054188+08
c2e31b91-68e3-4118-b082-13eb1405768c	9MWi8DbNYCTpOJl-V_Rp-xmwDsnGk9X94bFwp9Hh9EM	guest_unknown	0	3	\N	\N	2026-02-26 16:39:52.756178+08	2026-03-05 16:39:52.746842+08
418b1c7b-b4e4-4c49-a623-ce8daf12b458	rhrsz_9BPgt_WYmLpcayXTqzPW-8MuE-g3SBNfg97Dc	guest_unknown	0	3	\N	\N	2026-02-26 16:48:13.526803+08	2026-03-05 16:48:13.500126+08
8184d896-0ef0-4ccd-8dca-126f1c952713	vmVT0zVuEl9iWWVcBTUKmBlqfF3g_cIru6JW7Mx9XNg	guest_unknown	0	3	\N	\N	2026-02-26 19:31:03.935679+08	2026-03-05 19:31:03.925461+08
a95cceec-471d-4929-84cd-069f746dc31d	jJEliHRH_fW3OqkqDuhFKoDA2jqc-Wz86ke6IiTa6tY	guest_unknown	0	3	\N	\N	2026-02-26 19:34:30.867943+08	2026-03-05 19:34:30.843266+08
69c05b20-4c6d-4b2d-947f-f4cb088b93df	rx9wmaf_hHEsjTMF6K8lw5alJpDm3wXyrRnp2ZsBN34	guest_unknown	0	3	\N	\N	2026-02-26 19:37:35.270672+08	2026-03-05 19:37:35.263714+08
0b8317bc-54f3-4561-ae1e-0e147fbbda11	CfvuAUpvpVkvzdib_gdx-M4ol_37Fsy9kZp33DOvL6s	guest_unknown	0	3	\N	\N	2026-02-26 20:26:35.227062+08	2026-03-05 20:26:35.218063+08
66abdde8-bd2b-42bb-9200-4aea24be2f36	FBpzQr4QN6y8uNsg25D73B5valLsCFq29LOuDTDPxug	guest_unknown	0	3	\N	\N	2026-02-27 18:02:43.697778+08	2026-03-06 18:02:43.679901+08
e2321ab2-7007-4059-8e41-2389581fde39	F_2ckzKeV5TkIf702Pr46FlK4CH6Yb32doSENWhptmU	guest_unknown	0	3	\N	\N	2026-02-27 18:03:01.54961+08	2026-03-06 18:03:01.534576+08
03dd1c67-7223-4fd4-b133-42de98e7866a	TrHHfeCTc3Z-B84j0ZJvzswm1_4dZUedn8Nhp14fPSs	guest_unknown	0	3	\N	\N	2026-02-28 09:52:29.630483+08	2026-03-07 09:52:29.619344+08
84260c2e-92f2-44c0-8c74-4aa3cdfc1dbe	OX1zQTjtTsKEnIXn1H2IWyNmfENicO7qmtld2fT8crc	guest_unknown	0	3	\N	\N	2026-02-28 10:16:19.95128+08	2026-03-07 10:16:19.933235+08
69af2cee-6808-4481-9c4c-13c98d7b0c9e	Fg5fAajKvUb9EznWYjT8f0vGJGsWIbsSTk3AlMGhiY4	guest_unknown	0	3	\N	\N	2026-02-28 10:16:55.140282+08	2026-03-07 10:16:55.132073+08
3af7e28d-93ca-472d-8014-aeb70a703235	vZPVimfblBLALnDmfI_g6_0IDuP3yJpuiZA181pGdvg	guest_unknown	0	3	\N	\N	2026-02-28 10:27:50.533851+08	2026-03-07 10:27:50.514342+08
4eb28307-593f-4317-8ebb-8b21546b366b	zsVxrfK5zaDMNYNLeArxQIR2W_O1CRJ1Fl9soukZFbw	guest_unknown	0	3	\N	\N	2026-02-28 10:28:13.427514+08	2026-03-07 10:28:13.414723+08
c3ef3777-3a43-4ba0-a39b-4656b64fa023	AftsicdCtpf0cL9CSlX2xrVurHhhzxhFebmRf6gRoPA	guest_unknown	0	3	\N	\N	2026-02-28 10:50:50.422205+08	2026-03-07 10:50:50.404684+08
5d5fe46d-983f-4910-8eb2-bb5c5e652ac3	pt1tHK3Pkfh7zPWGGg39hp2zFEXFoczTUuekl4rmwSY	guest_unknown	0	3	\N	\N	2026-02-28 10:56:25.328647+08	2026-03-07 10:56:25.314215+08
099a2f3e-d4ab-49f9-9a8e-1752cc4c2304	xDeJ6X04gh6sCBfOfqgBGQ-gzrGSRclc0MuB4y3Ima8	guest_unknown	0	3	\N	\N	2026-02-28 10:56:52.309453+08	2026-03-07 10:56:52.302052+08
f38f23be-c92d-403f-89b5-2a4c6ca9d64f	dPhLlLLsGHdA8GmD7T9yT8IPAfwmFNKRDt31Ab4HPF8	guest_unknown	0	3	\N	\N	2026-02-28 10:58:53.651203+08	2026-03-07 10:58:53.638178+08
bae06d81-58f5-4191-b92d-3b2a8d3a210a	S6XeWLTrwpgUxpo7y9j4VuEo4PUJRPo7mpTmSyWQ9nk	guest_unknown	0	3	\N	\N	2026-02-28 11:01:48.013078+08	2026-03-07 11:01:47.99847+08
87881cc4-f0b3-4ec4-ab5b-c35175cc6b7d	1Y-0lZlYdgkFe0fIL73cjdkO3h7j9Otan8ANX2AKQWg	guest_unknown	0	3	\N	\N	2026-02-28 11:02:23.974978+08	2026-03-07 11:02:23.967096+08
c01813cc-5b9f-4349-b820-067731003d4b	FWW4AIoCKcNcRvGd9yfI_qiCw2QJeIkHuHCv6WPQJms	guest_unknown	0	3	\N	\N	2026-02-28 11:28:20.652599+08	2026-03-07 11:28:20.634511+08
0aa7fdad-6740-45e4-8226-cfea66b7040f	S8i99HQL0gUuFvNsmE7bkSD5K9hPi1R66d-2JedPd-I	guest_unknown	0	3	\N	\N	2026-02-28 11:35:51.445542+08	2026-03-07 11:35:51.436418+08
1847ecb1-3620-4a36-a16d-85576679cdc2	Qsr5_qhgX8_kuzLrSBuafvIyfUszNgwQfL_apnMR22Q	guest_unknown	0	3	\N	\N	2026-02-28 11:37:45.734863+08	2026-03-07 11:37:45.723222+08
2869730c-1119-405d-a506-19d8acf15a8e	fBcgujMPvt0kI8bThOjE-VPdi2GOPj8SnEjMjVv8zPM	guest_unknown	0	3	\N	\N	2026-02-28 11:52:24.758089+08	2026-03-07 11:52:24.74662+08
1479a38e-c98d-4917-b011-0ed2fce2d7cd	4gppfRu1KIyrcUDLIgKPS5ePKZPcTxk18KQ27fjVNtY	guest_unknown	0	3	\N	\N	2026-02-28 12:11:21.80426+08	2026-03-07 12:11:21.790146+08
51819bb8-fade-4637-9737-629dcfd45c67	64JodPI3IZqvATZqAnCpNnCVFch12av24TPujOhWvKU	guest_unknown	0	3	\N	\N	2026-02-28 12:25:14.720482+08	2026-03-07 12:25:14.710066+08
4b8bb365-6101-487c-b344-b604ff6f6a2c	AjHOLtMnSkd4ezXxXihm-KMz8ra6muxOHzZ4Hxoqryc	guest_unknown	0	3	\N	\N	2026-02-28 12:25:37.828723+08	2026-03-07 12:25:37.821024+08
aa16078b-5166-481f-b9a4-187e1ed049cd	5G-7SPaAwnRR2AVJM4HgLML7aeXlUfEioj0yv3djr_k	guest_unknown	0	3	\N	\N	2026-02-28 12:25:47.561501+08	2026-03-07 12:25:47.554618+08
112b051f-0202-463f-b056-b9fee34b1102	SBgMAGhQr7qPlblj4Mqesgn8iMtyPfhb1VBDExQE8Eg	guest_unknown	0	3	\N	\N	2026-02-28 14:26:46.742525+08	2026-03-07 14:26:46.707432+08
700dc442-7da6-4419-8391-f4cc8c83be45	6_t4ZBqTCfdJbAk0GsIYISJlYWvl4PZ7fXELe40ppaw	guest_unknown	0	3	\N	\N	2026-02-28 14:27:36.335228+08	2026-03-07 14:27:36.321607+08
bdf8dc02-64ea-4d67-a880-a2cdc06a0240	MoziGvC8hr1n5WHy3KdJIlW62qve_JkwrtR0P6_X32s	guest_unknown	0	3	\N	\N	2026-02-28 15:33:13.523173+08	2026-03-07 15:33:13.51025+08
b68335b1-e491-4880-bb0c-f640952c51fa	PBzzHqQHYuLoVQ7X2CBzzqV37cNyS_izEPQDY3X3n08	guest_unknown	0	3	\N	\N	2026-02-28 15:33:29.942712+08	2026-03-07 15:33:29.934752+08
2b60dff5-107b-4dda-b129-8bbf802b21c0	wVoHlBu2Vra3O3TgxZZDU2BWAUT74r62WAui0Cynnx0	guest_unknown	0	3	\N	\N	2026-02-28 15:34:25.054711+08	2026-03-07 15:34:25.041608+08
45e9d12e-54f3-44e2-85b2-780ce14a96c2	cGcCqUsYjtmfYnFB4f76Yw5bHMaRXC_7IibKVdiGuZk	guest_unknown	0	3	\N	\N	2026-02-28 15:36:41.07555+08	2026-03-07 15:36:41.068273+08
adc6279d-1500-4897-89fa-e592614fa708	-TYJo7LBcqaLbfmepYPWubrfwwkE1R5XX2FzFvbIS_o	guest_unknown	0	3	\N	\N	2026-02-28 16:33:55.021434+08	2026-03-07 16:33:55.001115+08
d0099197-4402-4c21-ba60-3226e7028869	Fzf_C2zvOMP03dmlpQePRc2G0N_2CBgcj0HQJ_8eZM0	guest_unknown	0	3	\N	\N	2026-02-28 16:39:07.895122+08	2026-03-07 16:39:07.882551+08
2700b5e0-66c5-432e-9c99-eb82f8245bf2	D5vPMl-hbQLItVDF-CLaw9QioctacNwMUCYOYuqHsZo	guest_unknown	0	3	\N	\N	2026-02-28 16:48:21.526063+08	2026-03-07 16:48:21.514934+08
76dcb7ae-2d2c-440e-b664-29fcc39a77a9	ZNCW0oIaMW85LvFF1OF1mn9QVHAoj0WPp-41ow1-QYQ	guest_unknown	0	3	\N	\N	2026-02-28 17:16:17.713908+08	2026-03-07 17:16:17.702834+08
7d7b08e2-b440-47d1-b783-e5d25b0c7687	RU3KoccepbDvFOdvG0fvXi14Zw_LL_XeM4HsFesrrBE	guest_unknown	0	3	\N	\N	2026-02-28 17:34:41.301231+08	2026-03-07 17:34:41.291004+08
4b157783-9871-4b83-9692-287f5afb47b0	_PRFfd8hUC_V3w2Jd8j7iPotDE3KWWqzjKki-tov8CU	guest_unknown	0	3	\N	\N	2026-02-28 17:35:02.359937+08	2026-03-07 17:35:02.341353+08
e2fe5531-1dba-4820-bcca-1fcf5c74320d	tOEtfH2lu51B6-aNoOMDsoDBokhMqC3PN9omNpXIdps	guest_unknown	0	3	\N	\N	2026-02-28 17:57:07.134599+08	2026-03-07 17:57:07.096861+08
e8c93822-a381-455b-a189-58cf8fd17f48	e-lkeYduVjx-NW4zDsL_d0c-1MAqlYdFsqGL6b2fdjk	guest_unknown	0	3	\N	\N	2026-02-28 18:00:23.493073+08	2026-03-07 18:00:23.477494+08
7731695c-51a4-47f8-a4be-469da61cf666	l7nhpvGJPU7NdahmzNoelUC7FEkM1D9_D-TKejykQkM	guest_unknown	0	3	\N	\N	2026-02-28 18:01:23.634333+08	2026-03-07 18:01:23.624577+08
e4a698ea-194f-4f90-b3c2-2f97c17c208f	sx__CUe8yZ1womM33ol7LYaZ6K1MmwWmjy3Mi5A_n_k	guest_unknown	0	3	\N	\N	2026-02-28 18:19:28.644757+08	2026-03-07 18:19:28.627056+08
a596b92a-91cc-4fa8-870d-a6f761a99615	osGnd3bI-AoiQiS7Lb1tVDmOYgRRG-EcbUAYSy06Fao	guest_unknown	0	3	\N	\N	2026-02-28 18:32:58.70808+08	2026-03-07 18:32:58.69432+08
5a220d4e-e6b1-4875-9f37-c129fe8225b8	YGx4CDbUB6cqP9bpIbbgq2ne0dwn9vWkG51bZq_FiL4	guest_unknown	0	3	\N	\N	2026-02-28 18:49:39.830587+08	2026-03-07 18:49:39.819771+08
4d454692-b3a2-4785-81a2-07a942bad8c1	bdaBqB3myoYSgADUZJN5lXiaDTqILSbluifRh3TrElE	guest_unknown	0	3	\N	\N	2026-02-28 19:14:16.068461+08	2026-03-07 19:14:16.052039+08
293d4afc-7e3e-4675-808f-cd12f41ece0e	MO5IJHWtjAHBEY8aQGB3smGH2304UqUDQ3JiRJKJ484	guest_unknown	0	3	\N	\N	2026-02-28 19:14:38.787677+08	2026-03-07 19:14:38.7797+08
445c857e-d6ea-4174-b532-ad19e92b4cea	EZnW3_Fz92lN9Tp1EGrxeRXLwDSmBqF_ca1SOZfOkpM	guest_unknown	0	3	\N	\N	2026-02-28 19:24:05.593721+08	2026-03-07 19:24:05.581923+08
9f3b2db2-57bf-4515-afa9-66bef3c85c4e	I960NfA0Kn14TxK7ND_merlQ76kp1BCuzieLmRf6Nxo	guest_unknown	0	3	\N	\N	2026-02-28 22:32:55.258078+08	2026-03-07 22:32:55.239+08
06ba1ede-5e4b-4120-885e-d77dbb5681c3	rneW6nb9fSBLiR3Y3RIXnqYU9WYzBF6Z6q39F9N64kw	guest_unknown	0	3	\N	\N	2026-02-28 22:38:26.733552+08	2026-03-07 22:38:26.713449+08
91607cf9-a8c0-4b43-8c6b-7946ffe2d545	abI_HSH7T8POxLL_v4wwi3zX1bRT7L4A7TdKYc5nLGY	guest_unknown	0	3	\N	\N	2026-02-28 22:41:54.269526+08	2026-03-07 22:41:54.253564+08
bf812f9a-4964-4ae7-9c12-ddbd14608ff5	-KgD_tPoVj0q2XknYYL5T1cFvyRYw0f-4PjMZzg8aco	guest_unknown	0	3	\N	\N	2026-02-28 22:43:13.385806+08	2026-03-07 22:43:13.369877+08
d94020c9-9c28-4cde-a0b9-ab622f51d08a	pXwJNNztwglZ-U3abwjUSlkqDIk4d2VazlJD44DdgJA	guest_unknown	0	3	\N	\N	2026-03-02 10:37:05.962475+08	2026-03-09 10:37:05.942035+08
20b08b97-5b74-437f-99ad-e1f7a5d3e269	0q4EIobDzh1pL9dLBJ4gUbkOXeq_W70o-MXrd6jnMLE	guest_unknown	0	3	\N	\N	2026-03-02 13:24:38.440037+08	2026-03-09 13:24:38.426406+08
dc5c2f3a-52cc-4fb7-b5dd-d211dd930dec	SRWHuCtMZoqZbOeWWXhy3pc7LXWt_4tEvN1XVGgDyek	guest_unknown	0	3	\N	\N	2026-03-02 13:30:37.696165+08	2026-03-09 13:30:37.67987+08
8047158c-7515-46f1-b975-70d3d3dab73d	pUFmgBtTxrPqIPS8nRIcgplM7B1yos_LOZN5aS7nKPE	guest_unknown	0	3	\N	\N	2026-03-02 16:13:04.154565+08	2026-03-09 16:13:04.139235+08
cacec38b-6a3d-4460-996c-0c7b344eb72c	Y6adhCSu9415LL3ZFikTPhqWfMR0vVtL6YriHyWX8b4	guest_unknown	0	3	\N	\N	2026-03-03 09:37:36.708418+08	2026-03-10 09:37:36.698213+08
b79307e3-4431-413c-a732-f6df7aeb9ed2	drAHYT-ymzPDjDEr_KhfwoWT_xL070iTZmNPq8_yXLQ	guest_unknown	0	3	\N	\N	2026-03-03 09:45:42.865272+08	2026-03-10 09:45:42.852863+08
eb890f87-6198-4e7f-bde1-d51ac5d35173	gXcmqWDbyXYUpAl_J8MP5LWVRIvO16ArkEJLdYaFQxI	guest_unknown	0	3	\N	\N	2026-03-03 09:52:26.830587+08	2026-03-10 09:52:26.819299+08
025e6c23-5563-43d6-ac31-78a099b8f38d	KfRLW67BO86TXOE_qyGV5hnkaEyYuXVOJsVO95AGjjg	guest_unknown	0	3	\N	\N	2026-03-03 10:11:38.06505+08	2026-03-10 10:11:38.05636+08
6a6f48aa-d07c-4bea-94b5-34da7d11b3f1	EiHIsCyOipNjmJgZ3dgAjKfU8N199Algjb9X_TyAzj8	guest_unknown	0	3	\N	\N	2026-03-03 10:20:42.916972+08	2026-03-10 10:20:42.900872+08
926592b2-4b40-4a12-bc3a-6d7ba5e2d4ed	XLt45_4J0EgIbPtr4iFA1hqxZNduMH5yKLbBxqOHPog	guest_unknown	0	3	\N	\N	2026-03-03 10:29:00.352249+08	2026-03-10 10:29:00.343381+08
d6831116-1815-4aae-9941-da5a8080cf7d	s3ddIpWdk6YbSUzxzFG-8lVdv1MxLlk3U_XpFcREmC8	guest_unknown	0	3	\N	\N	2026-03-03 10:30:00.32748+08	2026-03-10 10:30:00.318903+08
4f41dbda-04bc-438a-87e8-430964c456bf	ylksZ-edzpifXInsMm9yPwjrsUbadIgjLbXJ-EM50OQ	guest_unknown	0	3	\N	\N	2026-03-03 10:30:27.694069+08	2026-03-10 10:30:27.683194+08
f7839f61-5256-496a-9a80-3afa6ad76c17	EC0-8IIItOgSgDD2Q7PO7rakXJlOIsytI4ZU7VTu8nc	guest_unknown	0	3	\N	\N	2026-03-03 13:46:09.577765+08	2026-03-10 13:46:09.568604+08
386979ce-e1dd-4f6c-9884-4c5625cdcc3a	O9r3r1QJK3qfiQWu-RDI2zppf_Q7YXHexB4pOv6KfzE	guest_unknown	0	3	\N	\N	2026-03-03 13:52:37.392566+08	2026-03-10 13:52:37.373532+08
bee5102c-04f5-46c5-8812-a172aa01e6aa	uUTN9UyYI8h6UJWS7p8vNtPCxv_vTRF0M94kq5n5D48	guest_unknown	0	3	\N	\N	2026-03-03 14:17:11.140039+08	2026-03-10 14:17:11.126124+08
716e5649-c431-48e4-b7fe-3c20798f808c	HsPfP2_Gn_YjVNMrTu5sGQe0srjBsYqDxpWMM150ye8	guest_unknown	0	3	\N	\N	2026-03-03 14:27:33.773632+08	2026-03-10 14:27:33.753049+08
8919172c-9de0-4a75-80f2-6aa0b835d4d4	CWC_54ZL8xZUakLXtlrP_FQjb8yANph5VDSmfjx5sS8	guest_unknown	0	3	\N	\N	2026-03-03 14:31:52.046168+08	2026-03-10 14:31:52.037195+08
0b18b562-92d5-414b-b0d7-16fe038c4836	8ZvPiMXe4Z_Flh8cUsUrSQZLww4dFS-NOKxXqSgU1xY	guest_unknown	0	3	\N	\N	2026-03-03 14:37:31.174524+08	2026-03-10 14:37:31.160639+08
31f62acf-349d-495e-aa7d-de7bc258ba9c	PmwbSzaF7-UqqT7fEMVmD4EiPXmTy-wXubAXdqTeM3k	guest_unknown	0	3	\N	\N	2026-03-03 15:09:14.587674+08	2026-03-10 15:09:14.577722+08
2e45edbe-3174-401a-a92a-cfe8f9d5470f	KdZ9GD6jLqNeCwn8eH7QsrN2qU9zXfp46GBA9CNbULw	guest_unknown	0	3	\N	\N	2026-03-03 15:12:44.723339+08	2026-03-10 15:12:44.701102+08
dbe31806-76bb-4bdd-8edd-fabab148ffad	kVGgXO6K1DrFY09YP3hGmPjmcvAZqByjA7nCjkepnKE	guest_unknown	0	3	\N	\N	2026-03-03 15:36:49.857878+08	2026-03-10 15:36:49.850243+08
0a6f9d24-d8c2-466b-8903-665a39baa621	LVb6YhJXtacxcx61wjlhMEBEqhbcBhSyElzcaxEelnM	e2e_match_test_session_2	0	3	127.0.0.1	codex-e2e-test	2026-03-04 11:48:49.232424+08	2026-03-11 11:48:49.162458+08
c465e3bd-7d1a-4c6b-be5a-f1955dfb75f8	kRAZFSDa3_52L-x3ZnGtAQiv6SSNhN61Q5-3BDWjXe4	e2e_match_test_session_fmt	0	3	127.0.0.1	codex-e2e-test	2026-03-04 11:49:16.897554+08	2026-03-11 11:49:16.858767+08
d1ffa96c-c50c-4f90-b6ca-bbde42c7527a	uWNvQC6hfB0tnY02bYxYUasER6J7AJvsJd3i6RFaJzU	e2e_match_test_session_3	0	3	127.0.0.1	codex-e2e-test	2026-03-04 11:50:13.675672+08	2026-03-11 11:50:13.631911+08
a5c43212-f546-460e-8aa0-11ad99a1a342	z0r2-WMN07N6prt2ew7RYjuHtBv5QpMDrQCBZqXVAbA	guest_unknown	0	3	\N	\N	2026-03-05 15:32:34.442594+08	2026-03-12 15:32:34.435714+08
769db4cf-1ca1-4ddd-97ed-292e2606448d	sNILcR_8X5V3UYcF4wQje-dSRYc-3-RQu74t_WPKobY	guest_unknown	0	3	\N	\N	2026-03-05 15:32:51.524456+08	2026-03-12 15:32:51.513473+08
96e18595-0662-48b3-99ea-5c180ae5f810	QJAXyFn6a4oO-WtSvldhbO9ru2bYCRyaS-QDV4V6a3U	guest_unknown	0	3	\N	\N	2026-03-05 15:33:20.599645+08	2026-03-12 15:33:20.592561+08
bde3d07e-5387-46b0-9244-7be4804cf71e	gew6dVqOkC5hsk-GKAtnBIyRvxf0wZ0zw_icWyHE-yY	guest_unknown	0	3	\N	\N	2026-03-05 15:41:19.803491+08	2026-03-12 15:41:19.789343+08
07bb10c3-dfbc-4379-a6a4-77edf914c0f3	bGIWNFMFNW0PYt7SoElv43qKkeXwhmz8ZURGBoPod8o	guest_unknown	0	3	\N	\N	2026-03-05 15:52:39.186621+08	2026-03-12 15:52:39.173584+08
5e7bf5c9-1e6b-484e-a9ce-c4f4654c1957	AeP3mo6a862njUJxK6LxrdFwPyLGI7itkPotUaMe-Xg	guest_unknown	0	3	\N	\N	2026-03-05 15:56:23.221401+08	2026-03-12 15:56:23.206479+08
2b72d573-ea50-4f5d-8a53-67cfa1dccc42	8OzIT0qxUCAO6o8brfhLlnb0rLWtuUcbAnKE5GTBemE	guest_unknown	0	3	\N	\N	2026-03-05 16:00:31.07861+08	2026-03-12 16:00:31.067853+08
175435f9-4d32-43ff-9b1b-651aa47fbd70	kT-NSNgarC_sUVhKVm_oZ50KM_chORGAANc_Jsford8	guest_unknown	0	3	\N	\N	2026-03-05 16:05:29.628898+08	2026-03-12 16:05:29.620932+08
e0d7b2ab-15df-459a-8319-db9d2792b92e	xyumH96YF97R5n08g2NTlr6lfdmt8Bu4ioFavJMoPmo	guest_unknown	0	3	\N	\N	2026-03-05 16:12:55.79065+08	2026-03-12 16:12:55.778899+08
b9a75ed5-4418-4688-a5b4-a92b55c41aa2	CNBLMRKVF7Cqu4bIFzYHzB6hNEOF7XMn3A8IohO-L2E	guest_unknown	0	3	\N	\N	2026-03-05 16:13:33.060989+08	2026-03-12 16:13:33.0487+08
44107750-2174-4955-841a-2d2a784aa4bd	t1VpDYHFD_CYeyZBQgffi_KTZuVXGYZorX4assiKYxY	guest_unknown	0	3	\N	\N	2026-03-05 16:14:14.704701+08	2026-03-12 16:14:14.696716+08
d9e3316e-6175-48b6-bf69-ca9eb2f8e022	67X5HWjC9FgEPqMPL5qnJmzLZU1UnpqDYnoVMim1nso	guest_unknown	0	3	\N	\N	2026-03-05 16:18:20.604356+08	2026-03-12 16:18:20.592208+08
fff740c7-9e50-4370-9955-9541ebc08914	IRQdkY2T6VYt7DFAA4Y6Gg4QGC7dPDDi2Zm3uXNTukw	guest_unknown	0	3	\N	\N	2026-03-05 16:26:52.206518+08	2026-03-12 16:26:52.189377+08
354f6e43-4298-4c19-9326-8f7dc7c58d2e	m7pJo_F3LwlRqg4VA6sW08RmPcWiDIvVwYpP4XaKcyI	guest_unknown	0	3	\N	\N	2026-03-05 16:28:47.801304+08	2026-03-12 16:28:47.793757+08
bebb9b1d-10a2-4359-bad1-c967adcc27f7	RlRm9d3rrzmhgRD2soMDuK1Xc_dSdn9S8NB4RiU28I8	guest_unknown	0	3	\N	\N	2026-03-05 16:36:52.5302+08	2026-03-12 16:36:52.518977+08
1de510f4-f091-43b7-8848-1c493b1d8265	Je2YeDYwZs7P29Qs0T-M5cQ3yIDKsvtqqziky2TCBrQ	guest_unknown	0	3	\N	\N	2026-03-05 16:37:30.155088+08	2026-03-12 16:37:30.146913+08
241e7821-b05d-4ffa-a64c-17a75e9318ff	PgG2fBU_ox-xm-QzD5dopeQSCApwOCpybHzi2K4DGso	guest_unknown	0	3	\N	\N	2026-03-06 09:12:40.551349+08	2026-03-13 09:12:40.529108+08
a15ead48-925d-4eec-9c09-c0f54e0e5fef	SuRtUsLGwF9974ADlxTeaHuGyTS6HhxFXNxjTTAVNgE	guest_unknown	0	3	\N	\N	2026-03-06 10:34:58.308955+08	2026-03-13 10:34:58.300511+08
9ef737b3-1734-44ee-a5b1-3e82b6d6cec6	qG9nDREcSzOxzyT8uA2My8mO_kT-EeYK0WAGqilnSZE	guest_unknown	0	3	\N	\N	2026-03-06 11:01:55.501083+08	2026-03-13 11:01:55.491536+08
0a388eae-b2a7-4cd4-8479-aa4324820c6a	o41gXlhIHufHgQPr5TFlHbV3HUctflWX-m23zA1fb04	guest_unknown	0	3	\N	\N	2026-03-08 10:33:18.777722+08	2026-03-15 10:33:18.759842+08
a2efd14b-9673-44c5-8b75-bb1409b0918d	dvaAzQ4r0gDSnOi7pwSNtQOI74n2YCZt5aQvIKkH8_w	guest_unknown	0	3	\N	\N	2026-03-14 08:08:42.296563+08	2026-03-21 08:08:42.205396+08
\.


--
-- Data for Name: messages; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.messages (id, conversation_id, role, content, metadata, attachments, created_at) FROM stdin;
63187e8e-10b8-49d7-9fb8-58846ba4ca10	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	喜马	{}	[]	2026-03-05 15:24:41.033657
14623df8-cc0e-415b-aef3-d1a8dbbea938	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 官网_152552.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:30:10.468924
3aaf357e-c278-4004-9036-7c2d61b1101e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 官网_152552.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:31:04.6829
6e97d15f-33ec-48f8-8601-81f00e806511	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 官网_152552.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:31:46.331641
3c9a627c-33a0-4f22-9089-a8c71781a5c6	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「xxx」已删除	{}	[]	2026-03-05 16:42:32.515944
dd2346f1-30f4-42a7-9fd3-69e0e1305181	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	保存	{}	[]	2026-03-05 16:44:17.541953
58d8aeb7-a856-461b-8aea-e1d74408b64c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试1」的编辑...	{}	[]	2026-03-05 16:46:17.893724
6f05890b-3d3b-462d-b756-e473047c9530	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:46:31.85604
67c69fae-9df5-4a5e-ab72-bdd3233de570	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	添加sp订单号与sup订单号匹配	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_165657.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx", "size": 0}]	2026-03-05 16:58:45.502063
1184e961-9d84-4c4d-99c5-799de50bde76	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:01:56.413722
94e6a74e-cc97-41c7-8920-d1ff0bbec829	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx`	{}	[]	2026-03-05 17:07:16.844445
f0412c28-ca53-46c0-9364-18ce1e91518e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:08:43.15961
a4330100-2fa7-4db4-983b-c827593ecdd6	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-05 17:10:44.906046
e6ff7ff8-69b7-4dbc-a9c2-31ddcc0d4066	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ➕ 文件1 添加 订单时间	{}	[]	2026-03-05 17:19:05.633212
1f39e4bd-8c5d-4b56-ac71-1c3763712b3a	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	确认	{}	[]	2026-03-06 10:40:48.439578
09368006-203f-4d85-a189-59ba3873dd59	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	编辑西福	{}	[]	2026-03-06 10:47:16.055486
2ad5aa11-e425-4535-91b4-244663bc620c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 【西福商管】话费（欧飞）  官网.xlsx\n- 【西福商管】话费（欧飞）  合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-06 10:47:59.785932
b818b616-42e4-4c3d-acca-373b5b97f8a6	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **【西福商管】话费（欧飞）  官网_104542.xlsx:** 508条\n- **【西福商管】话费（欧飞）  合单_104543.xlsx:** 504条\n- **匹配成功:** 0条\n- **异常记录:** 1012条\n- **匹配率:** 0%\n\n**异常明细 (1012条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104260302093718667945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260228231428159849 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303172934595945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260305120849546264 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303114540229594 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030217342172965 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301171240138729 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030207223701836 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030420291944922 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217252694649 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030321464186558 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030218331756844 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260304180917679932 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030417113803887 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260305103845549035 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260302155726326794 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030515443350773 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301090038307113 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030317023515890 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217471700846 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n\n（共1012条，仅列前20条）	{}	[]	2026-03-06 11:10:48.440268
aa659fa7-986c-4e63-90ef-ae93e4a1f237	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **【西福商管】话费（欧飞）  官网_104542.xlsx:** 508条\n- **【西福商管】话费（欧飞）  合单_104543.xlsx:** 504条\n- **匹配成功:** 0条\n- **异常记录:** 1012条\n- **匹配率:** 0%\n\n**异常明细 (1012条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104260302093718667945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260228231428159849 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303172934595945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260305120849546264 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303114540229594 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030217342172965 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301171240138729 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030207223701836 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030420291944922 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217252694649 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030321464186558 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030218331756844 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260304180917679932 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030417113803887 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260305103845549035 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260302155726326794 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030515443350773 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301090038307113 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030317023515890 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217471700846 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n\n（共1012条，仅列前20条）	{}	[]	2026-03-06 11:11:49.867738
a3f6e038-499f-4879-9ecb-403d5404e42d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	❌ 未找到规则「西福欧飞」，请检查规则名称是否正确。	{}	[]	2026-03-06 11:12:25.341372
f27001e5-af62-4927-a02f-891784ee5537	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-06 11:12:49.127758
e8858b37-81e5-4499-b32d-9d40cbe659b9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「喜马」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 15:24:41.106277
7f4c2f5e-6ed8-42a0-90c9-ebcd6a14d0a0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 1767597466118.csv\n- ads_finance_d_inc_channel_details_20260105152012277_0.csv\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:30:10.493818
f078ba15-47c1-4db9-b085-17b92a5589e9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 1767597466118.csv\n- ads_finance_d_inc_channel_details_20260105152012277_0.csv\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:31:04.705937
354375ed-afdb-45cf-ac0e-4404b3bb9b1e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 1767597466118.csv\n- ads_finance_d_inc_channel_details_20260105152012277_0.csv\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:31:46.356462
b3058f4f-b552-479f-83a6-debddf89de30	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	确认	{}	[]	2026-03-05 16:42:36.166361
a757e583-5f86-4724-96ab-c94245375ed8	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **xxx**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:44:17.566221
5880def2-200b-4dc4-9fef-7f98488fd63e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `ads_finance_d_inc_channel_details_20260105152012277_0_164535.xlsx`	{}	[]	2026-03-05 16:46:17.918349
40161903-ecb4-4f38-9497-b40d382868ce	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  🚫 文件1 从 order_id 中移除列别名: sp订单号	{}	[]	2026-03-05 16:46:31.87596
b6e93f3c-3c0f-4ad6-8e26-f8ec473e2b32	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，已退出对账流程。如果您需要其他帮助，随时告诉我。	{}	[]	2026-03-05 16:58:45.528858
8b37b3eb-0a77-4080-a932-65d13480a667	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ❌ 文件1 删除 order_id 字段\n  ❌ 文件2 删除 order_id 字段	{}	[]	2026-03-05 17:01:56.452378
5655e534-d934-4310-89cc-ab592c2af104	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_165634.xlsx`\n- `主营业务收入-上期2024_165634.xlsx`	{}	[]	2026-03-05 17:07:16.919103
70727eb1-de13-4390-b893-9f84df2aed0c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx`	{}	[]	2026-03-05 17:08:43.19721
d66d5c43-ab9f-46b2-ba25-9db937d80d72	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 17:10:44.930582
7b57c218-d89a-429a-8dd9-9573a0fb9feb	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 17:19:05.656623
1ec32d60-e517-4dab-9dbc-19367305e47b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-06 10:40:48.463594
650fd635-7c46-473b-b753-62e7981c6858	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-06 10:47:16.079858
4fa65bf7-13ea-4dc5-ad6a-b0ef5380ce09	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-06 10:47:59.809056
a1af9aef-c080-41c6-a3c7-1a5b6cec5ff4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	❌ 未找到规则「西福欧飞」，请检查规则名称是否正确。	{}	[]	2026-03-06 11:10:48.473511
4cf9a969-7406-4151-8a7e-e0dd39271c91	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	❌ 未找到规则「西福欧飞」，请检查规则名称是否正确。	{}	[]	2026-03-06 11:11:49.893671
53043ce7-c1a8-4270-a4da-18d4af2dc18b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-06 11:12:25.366715
f9d47f36-8fb7-499c-bbda-1eeacd6a8357	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	已上传 2 个文件，请处理。	{}	[{"name": null, "path": "/uploads/2026/3/5/主营业务收入-本期2025_152455.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/主营业务收入-上期2024_152455.xlsx", "size": 0}]	2026-03-05 15:25:07.873914
20219f9e-ca90-4540-b040-d1c952a213e4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **官网_152735.xlsx:** 6489条\n- **合单_152735.xlsx:** 6479条\n- **匹配成功:** 6479条\n- **异常记录:** 10条\n- **匹配率:** 99.85%\n\n**异常明细 (10条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| L26012422340153819700 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012116163721519400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260124070644706639 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012123094296319400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260121215420799296 | 官网_152735.xlsx金额 53.099999999999994 vs 合单_152735.xlsx金额 70.8，差额 17.70 超出容差 0.1 |\n| L26011211340303919100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012119191879219100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260123134427719478 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012218172999819300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012014530342619300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |	{}	[]	2026-03-05 15:30:10.518789
fdb65811-8aff-41eb-88de-61feec4443a7	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **官网_152735.xlsx:** 6489条\n- **合单_152735.xlsx:** 6479条\n- **匹配成功:** 6479条\n- **异常记录:** 10条\n- **匹配率:** 99.85%\n\n**异常明细 (10条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| L26012422340153819700 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012116163721519400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260124070644706639 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012123094296319400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260121215420799296 | 官网_152735.xlsx金额 53.099999999999994 vs 合单_152735.xlsx金额 70.8，差额 17.70 超出容差 0.1 |\n| L26011211340303919100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012119191879219100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260123134427719478 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012218172999819300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012014530342619300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |	{}	[]	2026-03-05 15:31:04.727602
bbace8a8-9426-4e93-9232-95ede7f14cd5	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-05 15:31:46.386078
c9c4a28f-5d65-4aee-bbc0-fc7b02204366	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试1」的编辑...	{}	[]	2026-03-05 16:42:36.189987
ab1a6d21-ef17-4f2d-8d45-5de7a336b68a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「xxx」已删除	{}	[]	2026-03-05 16:44:17.592429
bbf7160a-8e58-4826-9db3-a11502c7965a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉订单号去除收尾空格	{}	[]	2026-03-05 16:46:17.943155
2bd2eeb1-0976-4a35-883c-ea5dcd3f3c9e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-05 16:46:31.898501
80a237d0-5b58-4b21-b2e4-7c10247308f0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ➕ 文件1 添加 order_id: sp订单号\n  ➕ 文件2 添加 order_id: sup订单号	{}	[]	2026-03-05 16:58:45.555289
fc3df652-dcff-4ffb-a4af-63252aa27c3f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-05 17:01:56.482265
53d3c72e-a4e5-447f-9c12-599c19de1cca	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 17:07:16.966234
6db3edbd-e64a-4afe-a7ec-28c07f3d87a3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_165634.xlsx`\n- `主营业务收入-上期2024_165634.xlsx`	{}	[]	2026-03-05 17:08:43.230127
dd47139b-7539-4c0f-8ef4-55c6c159a14b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **1767597466118_170019.xlsx:** 1870条\n- **ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx:** 1864条\n- **匹配成功:** 1856条\n- **异常记录:** 22条\n- **匹配率:** 99.2%\n\n**异常明细 (22条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104251231234638768479 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260122162512658451 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260112081844177428 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104250730101120956853 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260112204110375695 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231231337736997 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131046426087 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260107124023245524 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231234226418848 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131017217568 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260120182524246431 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260120154831859614 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231233717277112 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104251130171618989036 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260121232312235785 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260111131034425031 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260110211042376700 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260111131015059724 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104250730102122996149 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260122234015356232 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231234629088856 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131030607475 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |	{}	[]	2026-03-05 17:10:44.954365
5987803f-a7e9-4145-9388-c00c01ef697a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-05 17:19:05.701979
68c347ff-69bd-4a0f-9a6a-aeec33628c50	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:40:48.489472
b930c210-fc25-4e8d-a485-cc899addc2c0	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	确认	{}	[]	2026-03-06 10:47:19.747125
0cdb749c-97a4-48a7-a469-19dca749a2ba	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-06 10:47:59.831231
525a24f2-2051-473c-9bb0-14fe08a0fcfe	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-06 11:10:48.507387
62fc5c9f-c450-41c7-b833-6e331904a487	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-06 11:11:49.918377
79d68d5b-7602-44d4-aeb9-b84022b2a061	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-06 11:12:25.394925
a37bb58f-9518-4d21-9767-910979eef5df	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:25:07.941671
45b61af9-5a7b-4b47-bf2c-750cc0ae766e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 合单_152700.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:30:10.54351
bd190b2e-469e-459d-9a5e-88f5cb1d7756	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 合单_152700.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:31:04.748754
906e0e6d-6a52-45fe-b876-27954034cd21	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **官网_152735.xlsx:** 6489条\n- **合单_152735.xlsx:** 6479条\n- **匹配成功:** 6479条\n- **异常记录:** 10条\n- **匹配率:** 99.85%\n\n**异常明细 (10条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| L26012422340153819700 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012116163721519400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260124070644706639 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012123094296319400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260121215420799296 | 官网_152735.xlsx金额 53.099999999999994 vs 合单_152735.xlsx金额 70.8，差额 17.70 超出容差 0.1 |\n| L26011211340303919100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012119191879219100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260123134427719478 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012218172999819300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012014530342619300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |	{}	[]	2026-03-05 15:31:46.434746
a355312c-f131-4b18-9ddb-812970277339	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **xxx**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:42:36.213324
ba444186-f7f6-4455-9414-3315761321ba	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「测试1」已更新！	{}	[]	2026-03-05 16:44:17.613715
55218c55-700f-4084-966f-6398c8aaa908	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-05 16:46:17.964992
fcd7771e-92ae-47f4-a1fd-410608aa9e1c	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	你好	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_164535.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_164535.xlsx", "size": 0}]	2026-03-05 16:51:07.259212
c554d37b-4577-44b0-ba7e-b1d7d30d3134	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:58:45.590502
ff5fe9cb-acac-4cb6-a6c9-0ae4b78c1ce3	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	很好	{}	[]	2026-03-05 17:02:11.761263
7898ff05-3c13-4c33-bc7d-5cb2c7334f56	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-05 17:07:17.002136
5a4ea841-9e3e-4795-9f65-2257cb3b9405	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 17:08:43.264771
2ebeb274-e483-416a-bc4d-fd3380802828	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 17:10:44.981185
95a599bb-5b18-4d9e-8f52-99683d9c31ff	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	确认	{}	[]	2026-03-05 17:19:11.994069
2a657524-231e-4d6f-8d3d-bac44b9aa0a4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-06 10:40:48.5123
aedf5cf5-95f6-475a-b813-9035863c0ab5	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留104开头的订单号	{}	[]	2026-03-06 10:47:19.774853
59c0ac8a-2a86-4f89-80be-b79c307163e4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留103开头的订单号	{}	[]	2026-03-06 10:47:59.8537
ab7b67fc-7054-4bad-9770-c6d50df97f56	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-06 11:10:48.544801
1f359117-40c4-44af-aca9-45b96757b6f0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-06 11:11:49.943553
ade8f9a7-9558-48a3-b1e5-2c147d44cdc6	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 【西福商管】话费（欧飞）  官网.xlsx\n- 【西福商管】话费（欧飞）  合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据\n\n✅ 对账完成\n\n**对账概览**\n- **【西福商管】话费（欧飞）  官网_104542.xlsx:** 508条\n- **【西福商管】话费（欧飞）  合单_104543.xlsx:** 504条\n- **匹配成功:** 0条\n- **异常记录:** 1012条\n- **匹配率:** 0%\n\n**异常明细 (1012条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104260302093718667945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260228231428159849 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303172934595945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260305120849546264 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303114540229594 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030217342172965 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301171240138729 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030207223701836 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030420291944922 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217252694649 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030321464186558 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030218331756844 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260304180917679932 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030417113803887 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260305103845549035 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260302155726326794 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030515443350773 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301090038307113 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030317023515890 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217471700846 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n\n（共1012条，仅列前20条）	{}	[]	2026-03-06 11:12:25.422248
3a322659-32b3-4d38-9d4a-97ec68c52bed	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 【西福商管】话费（欧飞）  官网.xlsx\n- 【西福商管】话费（欧飞）  合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据\n\n✅ 对账完成\n\n**对账概览**\n- **【西福商管】话费（欧飞）  官网_104542.xlsx:** 508条\n- **【西福商管】话费（欧飞）  合单_104543.xlsx:** 504条\n- **匹配成功:** 0条\n- **异常记录:** 1012条\n- **匹配率:** 0%\n\n**异常明细 (1012条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104260302093718667945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260228231428159849 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303172934595945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260305120849546264 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303114540229594 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030217342172965 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301171240138729 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030207223701836 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030420291944922 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217252694649 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030321464186558 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030218331756844 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260304180917679932 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030417113803887 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260305103845549035 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260302155726326794 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030515443350773 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301090038307113 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030317023515890 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217471700846 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n\n（共1012条，仅列前20条）	{}	[]	2026-03-06 11:12:49.153121
4e0475e0-39fc-482f-97ce-d772ab37e9e0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「喜马」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 15:25:07.980889
47cd817b-d012-45ef-884b-cb240070158d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `1767597466118_152522.csv`	{}	[]	2026-03-05 15:30:10.574463
4537f900-d860-42a1-9111-b527095ba26f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉订单号去除收尾空格	{}	[]	2026-03-05 15:31:04.769288
8b74f8f6-2bbe-467e-834d-ae34b1195799	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 合单_152700.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:31:46.459703
4f99984f-619b-43f1-aa47-cd57bf0bdd8a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-05 16:42:36.235989
c9eac21f-ee9d-43ff-8138-861790637290	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试1」的编辑...	{}	[]	2026-03-05 16:44:17.636633
90393e86-d2ff-46af-bc49-bdea831e1589	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 16:46:17.988625
0dd1473c-7bf0-49ff-9ca7-6a6f08a1c08d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 未能解析修改，请更具体描述。\n\n> 将sp订单号与sup订单号匹配	{}	[]	2026-03-05 16:51:07.28448
4f30701e-d7cd-4d77-80d1-9f441cd91c69	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 16:58:45.632803
9529efae-e204-4dc8-bf03-ef78a049c9fe	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	很高兴对账顺利完成！匹配率达到了99.2%，结果很不错。\n\n如果您需要查看详细的对账报告、导出结果，或者想调整规则以进一步提高匹配率，随时告诉我。	{}	[]	2026-03-05 17:02:11.819228
2d5a93e9-f9f7-45f7-a813-aced8cd9d855	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:07:17.069494
43bd7f1e-c228-4953-a9eb-649d38873ba3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-05 17:08:43.297211
a900e159-8116-4d60-aa2b-f9607d8e801c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:10:45.003846
6d4b6990-98c0-473a-b09c-c9e9056a0758	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 17:19:12.018922
af9cba3f-8021-4a87-ad87-6310af0afe36	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	去掉订单号以104开头	{}	[]	2026-03-06 10:41:17.952116
dd89f580-9de3-4dcf-86cf-685812d82f3e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 【西福商管】话费（欧飞）  官网.xlsx\n- 【西福商管】话费（欧飞）  合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-06 10:47:19.804185
f346cf38-015b-4a43-9abd-70a384bf1bbc	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:47:59.878403
53dbdbaf-c692-45a1-8235-9ff83fac72b0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 【西福商管】话费（欧飞）  官网.xlsx\n- 【西福商管】话费（欧飞）  合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据\n\n✅ 对账完成\n\n**对账概览**\n- **【西福商管】话费（欧飞）  官网_104542.xlsx:** 508条\n- **【西福商管】话费（欧飞）  合单_104543.xlsx:** 504条\n- **匹配成功:** 0条\n- **异常记录:** 1012条\n- **匹配率:** 0%\n\n**异常明细 (1012条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104260302093718667945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260228231428159849 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303172934595945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260305120849546264 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303114540229594 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030217342172965 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301171240138729 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030207223701836 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030420291944922 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217252694649 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030321464186558 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030218331756844 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260304180917679932 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030417113803887 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260305103845549035 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260302155726326794 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030515443350773 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301090038307113 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030317023515890 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217471700846 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n\n（共1012条，仅列前20条）	{}	[]	2026-03-06 11:10:48.578572
c94a557e-a985-4749-ae2c-d4d13e881486	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ✏️ 文件2 修改 sup订单号	{}	[]	2026-03-06 11:11:49.971
1b344268-3553-4212-a628-217f9113d0df	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:12:25.448292
f56ee619-477f-479e-b430-ce94cc81acda	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:12:49.178261
d58b1b45-4dff-4463-a831-386bd91c987b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_152455.xlsx`\n- `主营业务收入-上期2024_152455.xlsx`	{}	[]	2026-03-05 15:25:08.02001
649bfff9-8a21-4dc3-8690-393f4171c1f9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **真腾讯异业**\n• **喜马**	{}	[]	2026-03-05 15:30:10.615125
883a2ac9-670a-4aea-91bf-720df3bb4a09	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `1767597466118_152522.csv`	{}	[]	2026-03-05 15:31:04.788452
7a5776ee-f7c9-4b2a-8a29-ea4297bdb226	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `1767597466118_152522.csv`	{}	[]	2026-03-05 15:31:46.483292
55ad8f96-d69b-42a0-bab7-2c71b61e2c32	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「xxx」已删除	{}	[]	2026-03-05 16:42:36.259609
f4bef325-7678-4b7d-a789-12682454a647	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-05 16:44:17.659529
881e5ed6-4ac5-4ec9-a46e-c5de68476f28	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **xxx**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:46:18.012505
771f07bc-271a-4dd5-8ddd-c37e3bcc2f55	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「xxx」已删除	{}	[]	2026-03-05 16:51:07.307764
46f371c9-04d4-40bd-ad19-761d1faf9761	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 16:58:45.659581
3daf82d2-06cc-4568-b942-a589da489f19	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	创建新规则	{}	[]	2026-03-05 17:02:38.436909
73c35831-afd1-4719-b45c-74a8c18a8779	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ❌ 文件1 删除 order_id 字段\n  ❌ 文件2 删除 order_id 字段	{}	[]	2026-03-05 17:07:17.11702
f3bd0215-a95f-4662-acb7-f97a62d56e2c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:08:43.329658
bb08e022-26f2-4281-9962-6ae57a44f5bb	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx`	{}	[]	2026-03-05 17:10:45.027495
f5604fa6-133d-4767-97ee-fc44bc819591	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-05 17:19:12.043468
fb3e334b-f99a-4d92-82bc-6722810b1dff	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-06 10:41:17.983098
c30c6ee9-e7b8-46f5-87db-884cbffb0890	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-06 10:47:19.827486
0e7b2cd6-7ca2-41ea-8fc7-5605f394dc4b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉进保留104开头的订单	{}	[]	2026-03-06 10:47:59.902151
729c6ba8-9a42-4a87-b8c8-84e2affdc489	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:10:48.609791
1643e5f8-1bfc-4a7e-b82b-e7667aeb5a5d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福欧飞」已删除	{}	[]	2026-03-06 11:12:25.475312
5b361acd-5238-4a0c-b9fd-066732490a0e	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	已上传 2 个文件，请处理。	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_152522.csv", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_152523.csv", "size": 0}]	2026-03-05 15:25:39.37863
0f2bb3f8-bfb3-47b2-a107-9a0d21d42e0e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「喜马」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 15:30:10.639921
72f61ac3-6399-469e-b4e5-122d5a344dbc	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **真腾讯异业**\n• **喜马**	{}	[]	2026-03-05 15:31:04.809147
42085d6d-45c3-4236-8661-928cd6c765e0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **真腾讯异业**\n• **喜马**	{}	[]	2026-03-05 15:31:46.506908
3d3d9260-ef6a-4b5b-933d-d86efd366d13	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	去掉金额保留2位小数	{}	[]	2026-03-05 16:42:47.655109
40ea82ef-6ead-4075-b247-ab7cd62fa039	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	规则列表	{}	[]	2026-03-05 16:44:31.087924
a9d4a3c5-4280-4313-b9da-df354a36ba30	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:46:18.037145
a2f57c90-0d45-464c-a938-3549fa6819d9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉金额保留2位小数	{}	[]	2026-03-05 16:51:07.328647
8baee85f-76be-4a45-a661-b879117fef7b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx`	{}	[]	2026-03-05 16:58:45.687999
bf274ac1-75a3-4342-b254-33494b162d60	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🎯 **开始创建新的对账规则**\n\n我会引导你完成以下4个步骤：\n\n1️⃣ 上传并分析文件 - 分析文件结构和列名\n\n2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）\n\n3️⃣ 配置规则参数 - 设置容差、订单号特征等\n\n4️⃣ 预览并保存 - 查看规则效果并保存\n\n请先上传需要对账的文件（文件1和文件2各一个 Excel/CSV 文件）。	{}	[]	2026-03-05 17:02:38.565226
35aa3887-b9d5-4023-8962-e958565600e8	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	很高兴对账顺利完成！匹配率达到了99.2%，结果很不错。\n\n如果您需要查看详细的对账报告、导出结果，或者想调整规则以进一步提高匹配率，随时告诉我。	{}	[]	2026-03-05 17:07:17.149162
fd9ba4a3-807e-45bb-b817-246c8bb90cff	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ❌ 文件1 删除 order_id 字段\n  ❌ 文件2 删除 order_id 字段	{}	[]	2026-03-05 17:08:43.360196
45debf12-cd6a-4a9f-9f0b-b58cb2892445	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_165634.xlsx`\n- `主营业务收入-上期2024_165634.xlsx`	{}	[]	2026-03-05 17:10:45.049964
65c8b4a8-2afb-4623-b143-7df8b0a7c0f3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-05 17:19:12.066641
3efd3b34-4e41-4a4c-b97f-139261786346	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:41:18.01551
56ed9699-6739-4813-93d2-83eab23b7f58	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-06 10:47:19.8531
0da845ae-0f3f-464a-9ed0-fe1a89d51ad8	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉订单号以104开头	{}	[]	2026-03-06 10:47:59.926791
bd1bbd10-1125-49b8-a92a-cb6fec06a8d6	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福欧飞」已删除	{}	[]	2026-03-06 11:10:48.644525
4f2980b5-52fa-473d-b0fc-b82cc1c58d66	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 【西福商管】话费（欧飞）  官网.xlsx\n- 【西福商管】话费（欧飞）  合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据\n\n✅ 对账完成\n\n**对账概览**\n- **【西福商管】话费（欧飞）  官网_104542.xlsx:** 508条\n- **【西福商管】话费（欧飞）  合单_104543.xlsx:** 504条\n- **匹配成功:** 0条\n- **异常记录:** 1012条\n- **匹配率:** 0%\n\n**异常明细 (1012条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104260302093718667945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260228231428159849 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303172934595945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260305120849546264 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303114540229594 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030217342172965 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301171240138729 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030207223701836 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030420291944922 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217252694649 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030321464186558 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030218331756844 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260304180917679932 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030417113803887 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260305103845549035 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260302155726326794 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030515443350773 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301090038307113 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030317023515890 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217471700846 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n\n（共1012条，仅列前20条）	{}	[]	2026-03-06 11:11:49.998047
69ccdc99-98ac-42d3-bf21-3d752de57c94	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-06 11:12:25.500798
f2f628b3-1342-42cd-98b0-7baf5ffbec26	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福欧飞」已删除	{}	[]	2026-03-06 11:12:49.20404
dfbfb92c-12c4-40c3-b7d6-bff8bff9c84f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `1767597466118_152522.csv`	{}	[]	2026-03-05 15:25:39.614269
53039c85-fd5e-476c-afc9-de66440dba63	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ➕ 文件1 添加 order_id: 订单号\n  ➕ 文件2 添加 order_id: 订单号	{}	[]	2026-03-05 15:30:10.665665
6bc3cc19-4961-4233-a26f-d23063ada93e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「喜马」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 15:31:04.829219
a4ed3ae1-14ba-45ad-9d99-0abefc69d628	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「喜马」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 15:31:46.531704
2debbf70-5d8c-4f60-aaae-387e0ab35274	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉金额保留2位小数	{}	[]	2026-03-05 16:42:47.681687
b7cda9d5-7ad6-4ecc-b649-5bb763686e49	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:44:31.112522
8990cb87-5135-4da0-8892-22fc230740e0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  🚫 文件1 从 order_id 中移除列别名: sp订单号	{}	[]	2026-03-05 16:46:18.060449
82be6539-8028-46fd-89a8-6e26cc3bf985	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-05 16:51:07.349283
fa5ea7f8-c45b-4f45-bbaf-1582f229f96e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_165634.xlsx`\n- `主营业务收入-上期2024_165634.xlsx`	{}	[]	2026-03-05 16:58:45.711639
990d874a-8f4a-4771-9c5f-dcf2e00b0b0a	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	已上传 2 个文件，请处理。	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_170247.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx", "size": 0}]	2026-03-05 17:03:04.282399
d3bc5241-8be9-4477-8e23-b08adb2458c5	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-05 17:07:17.183189
1992c0bc-f6ee-4cb8-9e6e-5527c4b80ce9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	很高兴对账顺利完成！匹配率达到了99.2%，结果很不错。\n\n如果您需要查看详细的对账报告、导出结果，或者想调整规则以进一步提高匹配率，随时告诉我。	{}	[]	2026-03-05 17:08:43.394875
65758371-141f-435e-9b9e-1c40e8308efc	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 17:10:45.074319
4648e209-7ec6-4cbc-8ca2-847d4049c254	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	增加金额取绝对值	{}	[]	2026-03-05 17:19:29.658418
836e325c-95db-415f-9df2-0115beb4e1b4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉订单号以104开头	{}	[]	2026-03-06 10:41:18.041174
0f09e8ad-c932-4da3-90c2-4b776d1c11ad	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留103开头的订单号	{}	[]	2026-03-06 10:47:19.878376
553f6574-8253-4546-9fd2-a82206895d6b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **【西福商管】话费（欧飞）  官网_104542.xlsx:** 508条\n- **【西福商管】话费（欧飞）  合单_104543.xlsx:** 504条\n- **匹配成功:** 0条\n- **异常记录:** 1012条\n- **匹配率:** 0%\n\n**异常明细 (1012条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104260302093718667945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260228231428159849 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303172934595945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260305120849546264 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303114540229594 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030217342172965 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301171240138729 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030207223701836 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030420291944922 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217252694649 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030321464186558 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030218331756844 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260304180917679932 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030417113803887 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260305103845549035 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260302155726326794 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030515443350773 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301090038307113 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030317023515890 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217471700846 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n\n（共1012条，仅列前20条）	{}	[]	2026-03-06 10:47:59.948835
9fbc8475-45b4-4c92-b8a6-7b3f1a66eb2b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-06 11:10:48.676548
bfa76a75-1923-4151-ae8b-fc934c698864	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:11:50.023988
f2941a24-1fe8-468e-815d-38629fd0987a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:12:25.527539
14a08f74-1fd3-4d93-98ab-b1e3f0eac306	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-06 11:12:49.230228
5d4e9071-f3c8-4345-b009-3c8d9f42348d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 1767597466118.csv\n- ads_finance_d_inc_channel_details_20260105152012277_0.csv\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:25:39.647023
9d544f30-2068-4d29-82ee-23d381db95d6	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	将订单号替换成sp订单号	{}	[]	2026-03-05 15:30:28.126094
840ecd61-0cf7-4e62-a303-193e40a464c4	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	去掉金额取绝对值	{}	[]	2026-03-05 15:31:17.790279
add52808-a40d-46d6-971e-257d0c053033	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	保存	{}	[]	2026-03-05 15:31:48.801722
cb3a582a-155a-4fb4-b0b8-b07552ec566f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试1」的编辑...	{}	[]	2026-03-05 16:42:47.709697
a39f8387-1b18-4fc1-ad70-99f0be21bf7c	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	删除测试1	{}	[]	2026-03-05 16:44:35.954783
e8ae3d52-ad24-4c3f-a432-7e2ef4e2cff0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-05 16:46:18.082392
d3c8fff2-26fc-4823-8764-8a6e635b9d4f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ➕ 文件1 添加 order_id: sp订单号	{}	[]	2026-03-05 16:51:07.371237
43ca970d-6adb-4fda-b201-89a6117dfa7f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 16:58:45.736387
6667620b-499b-4714-b66d-871a636e7c51	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-05 17:03:04.330221
9f8f36b1-623c-41fb-996f-d703c22a17f7	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	确认	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_170247.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx", "size": 0}]	2026-03-05 17:07:22.920509
348e95ab-d58f-40ea-8c85-7bbd2307bf07	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-05 17:08:43.425192
a7ff8d35-86f2-45b7-b787-85d7626a6a44	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-05 17:10:45.099182
dd85d822-748a-4e57-916f-02bc5f3d667a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：金额取绝对值\n\n> 增加金额取绝对值	{}	[]	2026-03-05 17:19:29.685493
a7cc4709-3989-4f72-bcc6-b22026a59914	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	去掉进保留104开头的订单	{}	[]	2026-03-06 10:41:47.894077
cf47f589-30a1-4e08-ae0e-a1b91e5c07f4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:47:19.90942
a2d7ae63-ec14-4674-a7a1-84d7f06b4963	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：仅保留104开头的订单号（两个文件）\n\n> 订单号以104开头	{}	[]	2026-03-06 10:47:59.971312
77e266e0-99eb-4205-a20e-5fa6dca15ac7	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:10:48.709366
691880af-4835-4db3-86ba-7df63cb8e26a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福欧飞」已删除	{}	[]	2026-03-06 11:11:50.045112
f9579694-e422-40d2-8f8b-71c2aef1a57e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：金额保留1位小数（两个文件）\n\n> 添加金额保留1位小数	{}	[]	2026-03-06 11:12:25.550522
adbfff0c-8e5c-4107-8659-76e394a13e75	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:12:49.256366
841739f7-03f3-482e-aed8-9f760cf52740	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	已上传 2 个文件，请处理。	{}	[{"name": null, "path": "/uploads/2026/3/5/官网_152552.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/合单_152552.xlsx", "size": 0}]	2026-03-05 15:25:54.602165
17f95162-1f2c-4184-b977-528161bdeebd	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 15:30:28.152042
12b6c568-ddc8-499d-a6d6-ad1d7ad20fd9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 15:31:17.816344
38cd9389-5343-4147-8137-59765b999860	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 15:31:48.837814
956b4980-e971-4c34-8d69-721735c446e6	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **xxx**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:42:47.735575
a9785340-0c20-4b7f-8d89-8564a19373ce	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「测试1」已删除	{}	[]	2026-03-05 16:44:35.978656
a2b52b90-160a-470d-9f0a-f86fbc5bf0bb	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	我的规则列表	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_164535.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_164535.xlsx", "size": 0}]	2026-03-05 16:46:26.82056
ee07e031-dbb3-49cc-ad21-0460ea281a4f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:51:07.392828
ee83ecfc-6e74-4b78-934a-8b6540af8f69	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 16:58:45.76152
c6497ae6-a7b2-41bd-92fa-21d6d051ab2f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🎯 **开始创建新的对账规则**\n\n我会引导你完成以下4个步骤：\n\n1️⃣ 上传并分析文件 - 分析文件结构和列名\n\n2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）\n\n3️⃣ 配置规则参数 - 设置容差、订单号特征等\n\n4️⃣ 预览并保存 - 查看规则效果并保存\n\n请先上传需要对账的文件（文件1和文件2各一个 Excel/CSV 文件）。	{}	[]	2026-03-05 17:03:04.370008
2d61d000-9e89-47b4-b81e-6fb530839421	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。接下来配置对账规则。	{}	[]	2026-03-05 17:07:22.948409
248356d8-0265-4dbc-99f4-2b78b4bfd7aa	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	确认	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_170247.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx", "size": 0}]	2026-03-05 17:08:46.146772
914f3b5f-5e3e-4efe-9191-d1389078250b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:10:45.123793
720a684c-b5c4-44e8-9285-ff2b266da738	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 17:19:29.710596
f07d5889-097d-4b3f-b6d1-f61be610b5d3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-06 10:41:47.92071
a612f9ff-65c1-42b8-9b07-64330d8ab575	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉进保留104开头的订单	{}	[]	2026-03-06 10:47:19.962564
78892acf-dbd7-498d-8834-83948f9c3cd1	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-06 10:48:00.019943
27046d2a-fc5e-4d3a-9f20-22c07aa6726e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-06 11:10:48.741706
a958d931-c915-4c6d-b4cb-ee06f2109df7	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-06 11:11:50.067505
c5dc9ee3-8960-4f2e-a607-bfbed431ee89	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-06 11:12:25.571715
d448ffe9-64d0-4957-adc8-81bd3d5cf0f5	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-06 11:12:49.279542
8320d2cd-09c2-4c28-a915-c973a0a854c4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 官网_152552.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:25:54.659863
8ba5f147-9272-45b0-abe0-300263494f32	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:30:28.186713
c5a579a7-7a4a-416a-8f4f-310135d5727c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:31:17.84163
36949e02-2fdd-4762-8e15-a9079a8bd541	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:31:48.873358
e52ed90a-f64f-4d0c-8ad0-c0a9d57e10f4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「xxx」已删除	{}	[]	2026-03-05 16:42:47.760596
f4e546cc-deef-481b-8aee-be1bf496b090	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	我的规则列表	{}	[]	2026-03-05 16:44:45.64545
4c8c005c-c2c9-4374-951d-c4486d2e0786	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 未能解析修改，请更具体描述。\n\n> 将sp订单号与sup订单号匹配	{}	[]	2026-03-05 16:46:26.845806
329fad9a-e935-4172-a452-9fd21067b946	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「测试1」已删除	{}	[]	2026-03-05 16:51:07.414247
91a10b5c-50d0-494e-996f-effb64f3f09a	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	确认	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_165657.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx", "size": 0}]	2026-03-05 16:59:33.964234
9d623358-080c-4785-a271-e12913d35d9f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，已退出对账流程。如果您需要其他帮助，随时告诉我。	{}	[]	2026-03-05 17:03:04.415327
c0ff91ed-bd31-4145-87ba-1eaa73d79a90	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-05 17:07:22.980376
896b69c6-7776-46ad-987f-7fa9ed2649a3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-05 17:08:46.183881
4de5c06c-e3e9-4f9d-977c-4f3245240cfc	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ❌ 文件1 删除 order_id 字段\n  ❌ 文件2 删除 order_id 字段	{}	[]	2026-03-05 17:10:45.152
f70b25b5-8b2b-494d-8288-8b151472e3b6	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-05 17:19:29.73635
f4e5bd11-844d-4ce1-ad2e-7753df07675e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:41:47.944658
8df80c98-1047-429c-820d-15aff66c6088	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉订单号以104开头	{}	[]	2026-03-06 10:47:19.989471
64856c9b-37f1-4e3e-9d84-d9616b0b5a73	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-06 10:48:00.056732
62d5226b-777f-4d88-a5e8-8441a5c85cdc	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	编辑喜马	{}	[]	2026-03-06 11:10:51.940568
b4efcd53-2274-425d-a3d4-f66220e457a9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:11:50.089758
e03dcdd6-656a-47cd-bcb1-b4deea21f182	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	确认	{}	[]	2026-03-06 11:12:36.863016
625c062d-97d6-4d1c-b003-118ee884b282	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	规则列表	{}	[]	2026-03-06 11:13:00.749056
d441555b-efa5-42aa-9631-373b2743de9b	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	已上传 2 个文件，请处理。	{}	[{"name": null, "path": "/uploads/2026/3/5/官网_152700.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/合单_152700.xlsx", "size": 0}]	2026-03-05 15:27:02.882519
ba715259-12ff-4ca6-b19b-0af48a3bb0b1	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	不客气！很高兴能帮到你。😊\n\n对账结果显示匹配率高达 **99.85%**，只有10条异常记录，整体数据质量非常好。\n\n**主要异常类型：**\n1. **官网有但合单无**（7条）- 可能是订单未同步或状态不一致\n2. **金额差异**（3条）- 金额差异超出容差范围\n\n如果需要进一步分析这些异常订单，或者需要导出对账报告，随时告诉我！	{}	[]	2026-03-05 15:30:28.221436
62a96bab-09b4-402e-b4fb-f2eabc4243b3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	不客气！很高兴能帮到你。😊\n\n对账结果显示匹配率高达 **99.85%**，只有10条异常记录，整体数据质量非常好。\n\n**主要异常类型：**\n1. **官网有但合单无**（7条）- 可能是订单未同步或状态不一致\n2. **金额差异**（3条）- 金额差异超出容差范围\n\n如果需要进一步分析这些异常订单，或者需要导出对账报告，随时告诉我！	{}	[]	2026-03-05 15:31:17.865289
45f1cfce-d546-4397-bdde-68c2b95ee407	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	不客气！很高兴能帮到你。😊\n\n对账结果显示匹配率高达 **99.85%**，只有10条异常记录，整体数据质量非常好。\n\n**主要异常类型：**\n1. **官网有但合单无**（7条）- 可能是订单未同步或状态不一致\n2. **金额差异**（3条）- 金额差异超出容差范围\n\n如果需要进一步分析这些异常订单，或者需要导出对账报告，随时告诉我！	{}	[]	2026-03-05 15:31:48.899179
8d7288ce-631b-4e3c-9c65-f3920845d507	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	去掉金额保留2位小数	{}	[]	2026-03-05 16:42:56.920037
c30f21ee-4121-45a5-9d95-03532ca98914	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:44:45.674107
4143288c-35c5-4497-a63c-6ed7d0e2a61e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「xxx」已删除	{}	[]	2026-03-05 16:46:26.869434
8f53c26e-8d34-46c7-bbea-8e2d9f2184a3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 16:51:07.437921
0acf4e16-7e5e-46eb-9438-af5c89094637	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-05 16:59:34.049159
85e33f73-ac6c-41f9-b4f5-0fb9c9386b30	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📊 **文件展示如下（数据仅展示前三条）**\n\n**1767597466118.xlsx** (1870行)\n| 订单编号 | sp订单号 | 商品编号 | 商品名称 | 充值账号 | 面值 | 购买数量 | 销售额 | 成本 | 利润 | 状态 | 操作人 | 接收短信手机 | 接收邮箱 | 订单时间 | 处理时间 | 员工编号 |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n| S2601225264074 | 104260122234015356232 | 152216 | 陕西联通手机快充200元 | 18602921164 | 200 | 1 | 212.6 | 0 | 0 | 成功 | 美团外卖项目 |   |   | 2026-01-22 23:40:26 | 2026-01-23 09:17:08 | A211209003 |\n| S2601225250790 | 104260122223743327540 | 141709 | 山东移动手机快充200元 | 15764265987 | 200 | 1 | 212.6 | 0 | 0 | 成功 | 美团外卖项目 |   |   | 2026-01-22 22:37:36 | 2026-01-22 22:40:58 | A211209003 |\n| S2601225240682 | 104260122215745858775 | 151703 | 山东联通手机快充50元 | 13034560607 | 50 | 1 | 53.15 | 0 | 0 | 成功 | 美团外卖项目 |   |   | 2026-01-22 21:57:23 | 2026-01-22 21:58:08 | A211209003 |\n\n**ads_finance_d_inc_channel_details_20260105152012277_0.xlsx** (1867行)\n| 完成时间 | 订单来源 | 订单号 | sup订单号 | 合单订单号 | 订单类型 | 结算类型 | 渠道所属公司 | 渠道供应商 | 渠道名称 | 渠道账号 | 发生+ | 发生- | 商品大类 | 公司id | 渠道id | 供应商id | 退款订单号 | 提交时间 | 分区 |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n| '2026-01-18 15:13:39.947000 | 直储订单充值 | '26011712568862901120 | '104260118143436596251 | '26011712568862901120 | 自营 | 先结 | 西藏福禄网络科技有限公司 | 南京飞翰网络科技有限公司 | 【西福商管】话费（欧飞） | 13247139559 |  | 53.15 | 通信 | 412de534-0fad-4a40-b30b-4bff45e099ce | e3b03b16-18f1-4ecb-8dcb-59cce78fd935 | 2a03be9f-365a-11e8-b9f0-0242ac110002 |  | '2026-01-18 14:34:02.699000 | 20260118 |\n| '2026-01-18 15:04:29.826000 | 直储订单充值 | '26011737623708181704 | '104260118143442126753 | '26011737623708181704 | 自营 | 先结 | 西藏福禄网络科技有限公司 | 南京飞翰网络科技有限公司 | 【西福商管】话费（欧飞） | 13247139559 |  | 53.15 | 通信 | 412de534-0fad-4a40-b30b-4bff45e099ce | e3b03b16-18f1-4ecb-8dcb-59cce78fd935 | 2a03be9f-365a-11e8-b9f0-0242ac110002 |  | '2026-01-18 14:34:02.709000 | 20260118 |\n| '2026-01-18 14:31:50.863000 | 直储订单充值 | '26011743094726850813 | '104260118141618279517 | '26011743094726850813 | 自营 | 先结 | 西藏福禄网络科技有限公司 | 南京飞翰网络科技有限公司 | 【西福商管】话费（欧飞） | 13247139559 |  | 53.15 | 通信 | 412de534-0fad-4a40-b30b-4bff45e099ce | e3b03b16-18f1-4ecb-8dcb-59cce78fd935 | 2a03be9f-365a-11e8-b9f0-0242ac110002 |  | '2026-01-18 14:16:47.735000 | 20260118 |	{}	[]	2026-03-05 17:03:04.458858
a5fc19a1-dc0c-4759-8c10-558ab65bcca6	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🎯 **开始创建新的对账规则**\n\n我会引导你完成以下4个步骤：\n\n1️⃣ 上传并分析文件 - 分析文件结构和列名\n\n2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）\n\n3️⃣ 配置规则参数 - 设置容差、订单号特征等\n\n4️⃣ 预览并保存 - 查看规则效果并保存\n\n请先上传需要对账的文件（文件1和文件2各一个 Excel/CSV 文件）。	{}	[]	2026-03-05 17:07:23.009225
8039c694-5e93-4dba-8c7a-d16047df8a59	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🎯 **开始创建新的对账规则**\n\n我会引导你完成以下4个步骤：\n\n1️⃣ 上传并分析文件 - 分析文件结构和列名\n\n2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）\n\n3️⃣ 配置规则参数 - 设置容差、订单号特征等\n\n4️⃣ 预览并保存 - 查看规则效果并保存\n\n请先上传需要对账的文件（文件1和文件2各一个 Excel/CSV 文件）。	{}	[]	2026-03-05 17:08:46.215454
749c7001-96c8-450c-96a3-9fd5b6820aa8	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	很高兴对账顺利完成！匹配率达到了99.2%，结果很不错。\n\n如果您需要查看详细的对账报告、导出结果，或者想调整规则以进一步提高匹配率，随时告诉我。	{}	[]	2026-03-05 17:10:45.178808
89f4dbae-b8b7-417e-9e88-5f4028facf79	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	增加订单号以104开头	{}	[]	2026-03-05 17:19:58.407293
be2fbf8d-6ee3-4290-9531-84a387c208d3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉进保留104开头的订单	{}	[]	2026-03-06 10:41:47.968793
6c802d50-6954-406a-bf6f-dc8bf4394c47	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **【西福商管】话费（欧飞）  官网_104542.xlsx:** 508条\n- **【西福商管】话费（欧飞）  合单_104543.xlsx:** 504条\n- **匹配成功:** 0条\n- **异常记录:** 1012条\n- **匹配率:** 0%\n\n**异常明细 (1012条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104260302093718667945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260228231428159849 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303172934595945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260305120849546264 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303114540229594 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030217342172965 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301171240138729 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030207223701836 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030420291944922 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217252694649 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030321464186558 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030218331756844 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260304180917679932 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030417113803887 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260305103845549035 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260302155726326794 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030515443350773 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301090038307113 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030317023515890 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217471700846 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n\n（共1012条，仅列前20条）	{}	[]	2026-03-06 10:47:20.014097
dd36cca6-1d9e-4f41-a4d3-fed819a5a92e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-06 10:48:00.08284
664fa8fa-08d3-4ef2-879e-517c6e96b809	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「喜马」的编辑...	{}	[]	2026-03-06 11:10:51.968126
3d4b67f7-6b5e-496a-9177-3c368264a2e2	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-06 11:11:50.111169
0692bce9-24c4-4c97-b8d9-ed3e38a42d6c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「喜马」的编辑...	{}	[]	2026-03-06 11:12:36.892011
3b84b604-57ee-48a0-a92f-92c8971e514c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:13:00.779459
52ad4f0f-4201-4c29-9ff2-ec91257d0a5e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 合单_152700.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:27:02.918452
8e4e8b19-f103-4eee-b82c-1c5ab460a5ea	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_152455.xlsx`\n- `主营业务收入-上期2024_152455.xlsx`	{}	[]	2026-03-05 15:30:28.246735
9fefb131-b53f-4cbf-89ef-ae2079f7a852	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_152455.xlsx`\n- `主营业务收入-上期2024_152455.xlsx`	{}	[]	2026-03-05 15:31:17.893228
49300f2b-deaf-4462-9232-bc40f26a6057	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_152455.xlsx`\n- `主营业务收入-上期2024_152455.xlsx`	{}	[]	2026-03-05 15:31:48.926654
86a356a5-fe0b-405d-896a-8403e52f2b1f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉金额保留2位小数	{}	[]	2026-03-05 16:42:56.951034
a97d60c2-a5b0-4e6d-9962-513f96c19868	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	西福	{}	[]	2026-03-05 16:45:04.478439
d2a9dbc9-61c7-496e-a9a9-54cc6ba95763	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉金额保留2位小数	{}	[]	2026-03-05 16:46:26.89329
73030416-da1f-422b-9046-479fec494c21	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，返回规则配置。	{}	[]	2026-03-05 16:51:07.459978
d46b62f1-7600-4474-ac12-f37b9d7e0a02	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，已退出对账流程。如果您需要其他帮助，随时告诉我。	{}	[]	2026-03-05 16:59:34.113836
e3078c77-0330-46ef-bdcd-5e888b27566c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ➕ 文件1 添加 order_id: sp订单号\n  ➕ 文件2 添加 order_id: sup订单号	{}	[]	2026-03-05 17:03:04.49431
1561be50-65ef-42c4-b02f-4a8cc29d2e7b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，已退出对账流程。如果您需要其他帮助，随时告诉我。	{}	[]	2026-03-05 17:07:23.051187
e0c16798-2cd6-4d11-9ae2-e79fee6b2d20	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，已退出对账流程。如果您需要其他帮助，随时告诉我。	{}	[]	2026-03-05 17:08:46.246764
6c3f4742-826d-4af2-99f4-6070b751894f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-05 17:10:45.202632
d265ddc8-f94b-4be7-bc02-5f9b122f41f3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：仅保留104开头的订单号（两个文件）\n\n> 增加订单号以104开头	{}	[]	2026-03-05 17:19:58.432955
00707c55-be7e-4f61-ad27-6760841f2bbd	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	删除仅保留104开头的订单号	{}	[]	2026-03-06 10:42:30.760755
cbadc48d-d1cd-438c-ad96-830776ab26d1	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-06 10:47:20.038189
c3c7c0eb-650a-4657-a935-13aaf17c3637	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:48:00.106167
e065a34e-14d9-4493-bb65-441eb915c8f5	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	把sup订单号替换成sp订单号	{}	[]	2026-03-06 11:11:25.579185
687a399b-1963-4c92-a0e2-2ad1d2123daf	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	确认	{}	[]	2026-03-06 11:11:53.341527
d259d730-9f53-4f89-8133-382e3bc0dfb4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	❌ 启动对账任务失败：规则不存在: 西福欧飞	{}	[]	2026-03-06 11:12:36.917505
df083c21-2eb1-4bcb-bd75-3a4198225d37	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	规则列表	{}	[]	2026-03-06 13:33:56.876024
115085a6-20d8-4a64-b187-d487fbbdb2f5	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	已上传 2 个文件，请处理。	{}	[{"name": null, "path": "/uploads/2026/3/18/官网_103744.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/18/合单_103744.xlsx", "size": 0}]	2026-03-18 10:37:50.066058
e757411b-bc3c-4743-a1a4-8dec6b89c014	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	已上传 2 个文件，请处理。	{}	[{"name": null, "path": "/uploads/2026/3/5/官网_152735.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/合单_152735.xlsx", "size": 0}]	2026-03-05 15:28:44.365692
fd1bb0dc-ac82-426b-9200-2262d11f04f6	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 官网.xlsx\n- 合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:30:28.269672
46492ec6-6827-4b70-8dec-df60b7fa60b3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 官网.xlsx\n- 合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:31:17.917564
9b5c6c74-803d-42a7-84b3-07bad96bf100	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 官网.xlsx\n- 合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:31:48.951799
ed0845d0-3998-49c1-8252-095e5214d822	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试1」的编辑...	{}	[]	2026-03-05 16:42:56.977836
d48528fa-6623-4d2b-bb63-8d9c5ffe89c4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 16:45:04.511576
77bc1533-d6e4-4c33-bbef-a2501049f185	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-05 16:46:26.919943
8735add4-13c0-490d-aa55-5d8fe6299aff	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉金额取绝对值	{}	[]	2026-03-05 16:51:07.482927
f9bfce06-f09e-4ba1-88a4-d66cdc09fdae	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:59:34.184062
6a15ccfd-89e3-4008-8ea5-b708d0a25efa	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-05 17:03:04.523331
a97339e5-f07f-41b7-bdbf-abebde1861cc	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ➕ 文件1 添加 order_id: sp订单号\n  ➕ 文件2 添加 order_id: sup订单号	{}	[]	2026-03-05 17:07:23.082586
aef1af12-45e5-49f8-945d-5472c24c54b2	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。正在生成规则并预览效果...	{}	[]	2026-03-05 17:08:46.281747
71aebc21-2257-4c0a-b640-1cb1cff214fe	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	测试	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_170247.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx", "size": 0}]	2026-03-05 17:10:49.300481
568da208-8275-49b8-8f40-a2f43c6ed2cb	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 17:19:58.459276
1ac2f54d-7984-4f54-8916-51f70fbdf014	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-06 10:42:30.784481
cd05da36-3edf-4c9c-b062-24804d249aa3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-06 10:47:20.062418
2cf6ba58-764a-4bbe-bc1a-029bf971c5e6	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福欧飞」已删除	{}	[]	2026-03-06 10:48:00.130899
41fcf8d2-c8bc-496a-a098-b54e66b9ebfe	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「喜马」的编辑...	{}	[]	2026-03-06 11:11:25.607861
9dc9e182-06a6-4e1d-9d4a-1ff9ec991076	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「喜马」的编辑...	{}	[]	2026-03-06 11:11:53.366498
59118a2f-b9f6-49a7-8c46-f61c51bdefb0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:12:36.94217
d5b9fcf0-4f18-4aa2-aa25-d3001b871e19	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 13:33:56.911299
e7e7d3f1-6824-4eb9-aca0-cf6e67831d31	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📊 **开始对账执行任务**\n\n已选择规则：**审计对账（audio_recon）**\n已上传文件：2 个\n\n正在校验文件并加载规则...	{}	[]	2026-03-18 10:37:50.164118
a0f6cb00-e206-4306-ada0-0f902bce91bb	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **官网_152735.xlsx:** 6489条\n- **合单_152735.xlsx:** 6479条\n- **匹配成功:** 6479条\n- **异常记录:** 10条\n- **匹配率:** 99.85%\n\n**异常明细 (10条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| L26012422340153819700 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012116163721519400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260124070644706639 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012123094296319400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260121215420799296 | 官网_152735.xlsx金额 53.099999999999994 vs 合单_152735.xlsx金额 70.8，差额 17.70 超出容差 0.1 |\n| L26011211340303919100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012119191879219100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260123134427719478 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012218172999819300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012014530342619300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |	{}	[]	2026-03-05 15:28:44.410666
017870c0-c174-422e-b9e3-802b96a0c07b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 官网_152552.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:30:28.289812
e0c8c80c-6cc4-4869-a397-6d3bf3e0fa59	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 官网_152552.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:31:17.942135
1121090f-3f27-4d59-8491-0270c1fc1ed0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-05 15:31:48.976886
587a6d30-abf9-4e94-ba42-e1002f862e43	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **xxx**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:42:57.003024
ef8e07fa-2538-4db1-82bb-b8710c130d16	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	已上传 2 个文件，请处理。	{}	[{"name": null, "path": "/uploads/2026/3/5/主营业务收入-本期2025_164510.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/主营业务收入-上期2024_164511.xlsx", "size": 0}]	2026-03-05 16:45:23.095326
90959da1-5618-4781-8f83-9349b1ab90a2	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ➕ 文件1 添加 order_id: sp订单号	{}	[]	2026-03-05 16:46:26.945176
830d9ad3-5249-437d-be75-66f1f353cc15	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 16:51:07.508193
099c7f7c-53ba-49f6-95c0-88296f837968	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 16:59:34.22949
67b87784-833a-4912-9dff-5715245a7e8e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 17:03:04.555843
79c9ce86-2bf1-4489-bb57-178c0077b4fc	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-05 17:07:23.111954
a24776d9-2b3d-4858-8088-cd0f6d49d05f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ➕ 文件1 添加 order_id: sp订单号\n  ➕ 文件2 添加 order_id: sup订单号	{}	[]	2026-03-05 17:08:46.312625
299c7d49-6d1b-4c29-9f58-17113aa7010f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-05 17:10:49.325178
a443668d-3dbb-489a-bc9d-26e1c0d5f252	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-05 17:19:58.486339
1a52b286-93bb-48bd-8d7f-bf71e7aee99a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:42:30.809893
51a5b209-9d71-4909-9637-32371296e527	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-06 10:47:20.086011
61ed4d66-b464-47cf-a452-7f5578b4e18e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-06 10:48:00.15635
459f1e51-1685-46ae-ad93-76ffe6fe2282	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	❌ 启动对账任务失败：规则不存在: 西福欧飞	{}	[]	2026-03-06 11:11:25.646401
e25bae99-d081-4c18-9a62-44cfe8e3c379	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	❌ 启动对账任务失败：规则不存在: 西福欧飞	{}	[]	2026-03-06 11:11:53.393235
1540f99f-2d3b-4819-9ed4-da47c01ab989	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留104开头的订单号	{}	[]	2026-03-06 11:12:36.967637
44108418-97b2-4cea-9340-803668cc70d6	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	删除西福欧飞	{}	[]	2026-03-06 13:34:05.001088
8255ab7b-2d58-44b6-8d44-1bed903a2fb3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	文件校验通过。\n\n**文件识别结果：**\n✅ **已匹配：**\n- **官网_103744.xlsx** → 喜马官网表\n- **合单_103744.xlsx** → 喜马合单表	{}	[]	2026-03-18 10:37:50.243016
518d7cf8-eb66-44d1-8a8c-dbbe7a2915d9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 官网.xlsx\n- 合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:28:44.443631
62ef3775-ffc8-4dec-aedc-6cdae281d5b5	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 1767597466118.csv\n- ads_finance_d_inc_channel_details_20260105152012277_0.csv\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:30:28.309165
5772f409-1077-4402-a837-ca9cc4f3b924	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 1767597466118.csv\n- ads_finance_d_inc_channel_details_20260105152012277_0.csv\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:31:17.964452
e2551440-acac-439a-b658-6f3b1867dbad	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 官网_152552.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:31:49.001225
145ab721-62ff-4cdd-be13-5c5c60425160	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「xxx」已删除	{}	[]	2026-03-05 16:42:57.027605
11e89a60-7cd7-463e-966d-1573d93d0177	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 未能解析修改，请更具体描述。\n\n> 将sp订单号与sup订单号匹配	{}	[]	2026-03-05 16:45:23.121864
a5284b4c-9f9d-40e4-a01c-62fe7ce405ec	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:46:26.96986
6d594ef2-51cf-4c38-86a5-3b0bf0bf91b1	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_164510.xlsx`\n- `主营业务收入-上期2024_164511.xlsx`	{}	[]	2026-03-05 16:51:07.530058
d3e0d15a-25fb-4de8-8741-9664bdb42df6	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 16:59:34.28994
f2d0d713-5a9e-4d2c-be7c-3c8da821855d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **1767597466118_170019.xlsx:** 1870条\n- **ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx:** 1864条\n- **匹配成功:** 1856条\n- **异常记录:** 22条\n- **匹配率:** 99.2%\n\n**异常明细 (22条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104251231234638768479 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260122162512658451 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260112081844177428 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104250730101120956853 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260112204110375695 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231231337736997 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131046426087 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260107124023245524 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231234226418848 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131017217568 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260120182524246431 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260120154831859614 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231233717277112 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104251130171618989036 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260121232312235785 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260111131034425031 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260110211042376700 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260111131015059724 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104250730102122996149 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260122234015356232 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231234629088856 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131030607475 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |	{}	[]	2026-03-05 17:03:04.586784
43f406f5-4542-47a1-b68b-bcb3a42422da	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 17:07:23.14021
fb1234ec-56fb-40ae-85c6-f5bc4969422f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-05 17:08:46.342895
096f1f3b-b15a-432b-86d2-f5391577be02	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🎯 **开始创建新的对账规则**\n\n我会引导你完成以下4个步骤：\n\n1️⃣ 上传并分析文件 - 分析文件结构和列名\n\n2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）\n\n3️⃣ 配置规则参数 - 设置容差、订单号特征等\n\n4️⃣ 预览并保存 - 查看规则效果并保存\n\n请先上传需要对账的文件（文件1和文件2各一个 Excel/CSV 文件）。	{}	[]	2026-03-05 17:10:49.346699
5688a7e3-70e4-4bc9-a31c-fb4fcc24da41	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	增加金额保留2位小数	{}	[]	2026-03-05 17:20:10.339183
a5ea3ce3-e75f-4097-a13d-a0646b54da3f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留104开头的订单号	{}	[]	2026-03-06 10:42:30.833903
0254b2d1-2603-4641-977a-555e26fc9ae6	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:47:20.110919
830fce63-02d6-478d-a565-0085cc5d8850	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	规则列表	{}	[]	2026-03-06 10:48:15.006905
b6da5daa-7687-4ec5-9fa6-c0a4fdea4acf	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:11:25.672028
f550da0d-4076-4e2d-aca1-e1c7ce429341	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:11:53.423202
28d25704-3615-452c-9e67-3af739d34e1c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-06 11:12:36.995164
7feedd40-71f6-4c7f-9d4c-f2a9e147c6ff	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	❌ 未找到规则「西福欧飞」，请检查规则名称是否正确。	{}	[]	2026-03-06 13:34:05.029893
e53e08b4-5cad-4210-bfca-67a94425c25b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	对账任务已完成。\n\n**规则：** 审计对账（audio_recon）\n\n**对账文件：**\n1. **喜马-26合单与官网数据核对**：`合单_103744.xlsx` ↔ `官网_103744.xlsx`\n\n**统计：**\n- 匹配记录：6463 条\n- 差异记录：48 条\n\n**数据差异：**\n- 匹配但有差异: 37 条\n- 源文件独有: 1 条\n- 目标文件独有: 10 条\n\n- [详细差异报告 1](http://localhost:3335/output/recon/喜马-26合单与官网数据核对_核对结果_20260318_103749.xlsx)：喜马-26合单与官网数据核对_核对结果_20260318_103749.xlsx\n\n如需进一步分析或有疑问，请告知。	{}	[]	2026-03-18 10:37:50.330277
c93c0ed1-0171-4770-9371-4965e381f42f	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	谢谢你，很不错的结果	{}	[]	2026-03-05 15:29:28.877931
53dd80e2-7a62-4f33-8774-2bc8ae6d9fef	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **官网_152735.xlsx:** 6489条\n- **合单_152735.xlsx:** 6479条\n- **匹配成功:** 6479条\n- **异常记录:** 10条\n- **匹配率:** 99.85%\n\n**异常明细 (10条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| L26012422340153819700 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012116163721519400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260124070644706639 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012123094296319400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260121215420799296 | 官网_152735.xlsx金额 53.099999999999994 vs 合单_152735.xlsx金额 70.8，差额 17.70 超出容差 0.1 |\n| L26011211340303919100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012119191879219100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260123134427719478 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012218172999819300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012014530342619300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |	{}	[]	2026-03-05 15:30:28.329008
e1160da1-9f16-44ec-80c9-54d60e1fed34	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **官网_152735.xlsx:** 6489条\n- **合单_152735.xlsx:** 6479条\n- **匹配成功:** 6479条\n- **异常记录:** 10条\n- **匹配率:** 99.85%\n\n**异常明细 (10条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| L26012422340153819700 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012116163721519400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260124070644706639 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012123094296319400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260121215420799296 | 官网_152735.xlsx金额 53.099999999999994 vs 合单_152735.xlsx金额 70.8，差额 17.70 超出容差 0.1 |\n| L26011211340303919100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012119191879219100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260123134427719478 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012218172999819300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012014530342619300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |	{}	[]	2026-03-05 15:31:17.986032
71dbf805-2167-4b96-9fba-8a5e68746230	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 1767597466118.csv\n- ads_finance_d_inc_channel_details_20260105152012277_0.csv\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:31:49.032039
45d6bd29-6b39-438c-8e4c-8655954facf7	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	去掉首尾空格	{}	[]	2026-03-05 16:43:04.629228
c30af7d6-2e55-44ca-82c5-222ad81f0eea	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「xxx」已删除	{}	[]	2026-03-05 16:45:23.146932
a9f8fa80-8079-4d49-860f-09f4b2786256	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「测试1」已删除	{}	[]	2026-03-05 16:46:26.991986
5d0ab82a-136a-430f-9ee1-e7c6f6681659	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：订单号去除首尾空格\n\n> 去掉首尾空格	{}	[]	2026-03-05 16:51:07.552441
3b8f2cfb-6865-4dac-9574-706cc725c1b1	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx`	{}	[]	2026-03-05 16:59:34.352046
d5fab16a-7463-4fec-b37c-0599edf4be7c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 17:03:04.617113
e6d5407f-580e-4ceb-8a0e-96b15dd7a96d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **1767597466118_170019.xlsx:** 1870条\n- **ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx:** 1864条\n- **匹配成功:** 1856条\n- **异常记录:** 22条\n- **匹配率:** 99.2%\n\n**异常明细 (22条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104251231234638768479 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260122162512658451 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260112081844177428 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104250730101120956853 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260112204110375695 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231231337736997 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131046426087 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260107124023245524 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231234226418848 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131017217568 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260120182524246431 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260120154831859614 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231233717277112 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104251130171618989036 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260121232312235785 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260111131034425031 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260110211042376700 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260111131015059724 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104250730102122996149 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260122234015356232 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231234629088856 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131030607475 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |	{}	[]	2026-03-05 17:07:23.165205
05284457-cfef-44b5-a186-240092a5c183	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 17:08:46.376316
128b365f-7ce5-459b-866b-0dfdada39534	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，已退出对账流程。如果您需要其他帮助，随时告诉我。	{}	[]	2026-03-05 17:10:49.371161
58c722d1-33bd-4b4f-9fef-d23825e01689	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：金额保留2位小数（两个文件）\n\n> 增加金额保留2位小数	{}	[]	2026-03-05 17:20:10.3692
bee20041-9315-42a3-8313-ea397959e8a7	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	删除仅保留104开头的订单号	{}	[]	2026-03-06 10:42:52.826106
4f02f2ca-d5cd-4a28-bb16-222dd9993486	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福欧飞」已删除	{}	[]	2026-03-06 10:47:20.137746
71b86794-9e48-462f-bb0e-d4723afd1d91	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:48:15.03639
19546848-cbdc-4f1f-84bd-2e92793a9518	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留104开头的订单号	{}	[]	2026-03-06 11:11:25.700618
4c902010-8e82-40bc-ba98-1bd369d003f0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留104开头的订单号	{}	[]	2026-03-06 11:11:53.451849
9df06089-0be6-4279-b558-1248cb51dfe4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留103开头的订单号	{}	[]	2026-03-06 11:12:37.021346
a7cfd050-98a4-4574-8625-c914522bf7c6	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	腾讯异业	{}	[]	2026-03-06 13:46:14.988829
4420c157-58ac-4d41-98a8-0e8e9b17b4a8	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	你好	{}	[{"name": null, "path": "/uploads/2026/3/18/官网_103744.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/18/合单_103744.xlsx", "size": 0}]	2026-03-18 19:49:48.578318
35cfe048-ebaa-443c-b57b-d8603d6ab6a5	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	不客气！很高兴能帮到你。😊\n\n对账结果显示匹配率高达 **99.85%**，只有10条异常记录，整体数据质量非常好。\n\n**主要异常类型：**\n1. **官网有但合单无**（7条）- 可能是订单未同步或状态不一致\n2. **金额差异**（3条）- 金额差异超出容差范围\n\n如果需要进一步分析这些异常订单，或者需要导出对账报告，随时告诉我！	{}	[]	2026-03-05 15:29:28.903214
bfb213e3-f73e-4a71-abeb-17b64f357a65	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 合单_152700.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:30:28.348905
81a02fe3-fb38-43b8-bfd5-5331a3491161	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 合单_152700.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:31:18.006305
e37b8051-f804-4de9-8ed3-aa7bf711b8e4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **官网_152735.xlsx:** 6489条\n- **合单_152735.xlsx:** 6479条\n- **匹配成功:** 6479条\n- **异常记录:** 10条\n- **匹配率:** 99.85%\n\n**异常明细 (10条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| L26012422340153819700 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012116163721519400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260124070644706639 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012123094296319400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260121215420799296 | 官网_152735.xlsx金额 53.099999999999994 vs 合单_152735.xlsx金额 70.8，差额 17.70 超出容差 0.1 |\n| L26011211340303919100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012119191879219100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260123134427719478 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012218172999819300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012014530342619300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |	{}	[]	2026-03-05 15:31:49.057713
9618e4b0-f647-495d-ac57-ddcb87d39653	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：订单号去除首尾空格\n\n> 去掉首尾空格	{}	[]	2026-03-05 16:43:04.6572
ceda94db-6dbc-4e1b-bbb3-7958256d8248	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉金额保留2位小数	{}	[]	2026-03-05 16:45:23.17198
5e757289-cc43-4bfc-b06f-fb244c4889a3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 16:46:27.017753
7a77be87-335e-4b48-9cdd-621afb7e9718	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉订单号去除首尾空格	{}	[]	2026-03-05 16:51:07.574025
7f8d242c-cb54-4bd5-a74b-7b4868773e94	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_165634.xlsx`\n- `主营业务收入-上期2024_165634.xlsx`	{}	[]	2026-03-05 16:59:34.410462
cd1e24cc-4274-4df3-b50f-8068d7ea19d5	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:03:04.64807
a77b349e-1e23-407e-a2b3-724b3138f8fc	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 17:07:23.191979
0da75ec7-03f3-4f1c-a8b1-4a71070df536	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **1767597466118_170019.xlsx:** 1870条\n- **ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx:** 1864条\n- **匹配成功:** 1856条\n- **异常记录:** 22条\n- **匹配率:** 99.2%\n\n**异常明细 (22条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104251231234638768479 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260122162512658451 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260112081844177428 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104250730101120956853 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260112204110375695 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231231337736997 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131046426087 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260107124023245524 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231234226418848 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131017217568 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260120182524246431 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260120154831859614 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231233717277112 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104251130171618989036 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260121232312235785 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260111131034425031 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260110211042376700 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260111131015059724 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104250730102122996149 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260122234015356232 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231234629088856 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131030607475 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |	{}	[]	2026-03-05 17:08:46.409016
5629d29e-3522-4276-9de7-cdc6d01f767e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ➕ 文件1 添加 order_id: sp订单号\n  ➕ 文件2 添加 order_id: sup订单号	{}	[]	2026-03-05 17:10:49.395622
b119d1b8-7774-48d4-b4a0-93aff8b86600	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 17:20:10.398551
0a74e478-5199-4899-9e9b-085076e17618	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-06 10:42:52.851128
9fcc26e0-2750-4303-a9c9-83e5f8615a44	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-06 10:47:20.163251
e8dc5cef-9889-4991-bfcd-6cb00bb55cfc	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	使用西福	{}	[]	2026-03-06 10:48:52.92754
354cd60c-d3bf-46b8-ba64-d3f4eb1e1673	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-06 11:11:25.730474
ecb7b2f1-21a3-4956-86c9-41e728ea578e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-06 11:11:53.481455
55cb1356-59cb-4ed9-83c0-c0ac4fa02f52	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福欧飞」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-06 11:12:37.046826
c914065c-1d8b-4da6-bff1-c6a315457700	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「腾讯异业」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-06 13:46:15.018756
8e7dfea2-e727-4130-ba2f-8fed8a846a25	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	规则列表	{}	[]	2026-03-05 15:29:42.261488
09559fe9-d528-422e-bac0-e73a7c9b6d99	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ✏️ 文件1 修改 order_id: sp订单号\n  ✏️ 文件2 修改 order_id: sp订单号	{}	[]	2026-03-05 15:30:28.373304
0c0a3ede-c4ae-42ec-beb9-84a9ccd707c6	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `1767597466118_152522.csv`	{}	[]	2026-03-05 15:31:18.026251
c67514a3-4932-4d1f-bdfe-b7f80f72d8ac	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 合单_152700.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:31:49.082226
cba2bb8e-87f7-4d87-971d-0622d56f5af9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试1」的编辑...	{}	[]	2026-03-05 16:43:04.685406
3bf3efc1-c8c8-4617-b4d2-723bdba7b76a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-05 16:45:23.195744
b4193cef-71d4-4bea-8cc3-51485038a969	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，返回规则配置。	{}	[]	2026-03-05 16:46:27.047336
b5562fe5-ac44-4a03-9cf9-3994975dd116	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「测试1」已更新！	{}	[]	2026-03-05 16:51:07.595936
9064f0a7-4114-4ea5-817d-9040a565bffa	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 16:59:34.459118
1e7dfa08-7616-4dd9-a55b-771d25f80be2	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx`	{}	[]	2026-03-05 17:03:04.677575
a2769b07-c9b9-403c-9041-9a7cc4d9b71e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:07:23.217153
641351fc-4b45-454b-bdf5-e9a111b60949	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 17:08:46.437945
a3907f32-9809-48c8-a224-b1186938bde5	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-05 17:10:49.417917
d88b60dc-28ee-4518-b938-6298d053ea84	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-05 17:20:10.426477
70437c5e-a601-4abb-abe4-a6175585bd54	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:42:52.877564
07f0b983-2702-4326-ab4b-cab60445c44f	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	订单号以104开头	{}	[]	2026-03-06 10:47:45.517787
3547adca-574a-4a36-87bf-64163f9e061b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-06 10:48:52.954365
a283cce0-8a81-4cb5-bf3d-32e999647feb	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留103开头的订单号	{}	[]	2026-03-06 11:11:25.759867
7b042463-b9e8-49e1-ba33-10e15ecaeda1	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留103开头的订单号	{}	[]	2026-03-06 11:11:53.510833
e5f5b853-685b-44e7-ba65-999abfaa460f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉订单号以104开头	{}	[]	2026-03-06 11:12:37.073422
4a5ecebd-f4a1-43a8-98df-c1e122ca11f3	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	已上传 2 个文件，请处理。	{}	[{"name": null, "path": "/uploads/2026/3/6/2025-12-01~2025-12-01对账流水_134657.csv", "size": 0}, {"name": null, "path": "/uploads/2026/3/6/ads_finance_d_inc_channel_details_20260105133821735_0_134657.csv", "size": 0}]	2026-03-06 13:47:05.540067
dc441c24-d68e-41cd-b42c-699d3084c9c2	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📊 **开始对账执行任务**\n\n已选择规则：**审计对账（audio_recon）**\n已上传文件：2 个\n\n正在校验文件并加载规则...	{}	[]	2026-03-18 19:49:48.655588
ed67ba3a-1fdc-403b-9f15-7662e96ab399	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **真腾讯异业**\n• **喜马**	{}	[]	2026-03-05 15:29:42.288924
9be287dd-177e-43ed-a4bd-fbb626149f47	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `1767597466118_152522.csv`	{}	[]	2026-03-05 15:30:28.397476
66afbf28-0c53-40d5-bbb7-ef55befb68ab	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **真腾讯异业**\n• **喜马**	{}	[]	2026-03-05 15:31:18.046472
818d2da4-fc4e-47e2-a7d3-21635217dbef	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `1767597466118_152522.csv`	{}	[]	2026-03-05 15:31:49.134838
1c477913-f846-4776-9356-ad1a1f562390	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **xxx**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:43:04.708989
dfefc3a6-ae4e-48b3-a673-e60330c10826	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ➕ 文件1 添加 order_id: sp订单号	{}	[]	2026-03-05 16:45:23.221865
f63353a8-6e06-417a-936c-3d758080d9e8	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉金额取绝对值	{}	[]	2026-03-05 16:46:27.074258
784e171a-4093-41a6-9ddc-b11123d5b113	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试1」的编辑...	{}	[]	2026-03-05 16:51:07.618481
bdb43203-bd1b-4caf-ab80-6e517c85eeac	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 16:59:34.502007
2ff69b20-feea-452c-bbfa-0852a97e227a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_165634.xlsx`\n- `主营业务收入-上期2024_165634.xlsx`	{}	[]	2026-03-05 17:03:04.707203
60a84ec3-12e4-4c18-aa1a-fa3ee508d15e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx`	{}	[]	2026-03-05 17:07:23.243194
47fd0530-449d-42a7-b960-76cf6bcb5e54	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:08:46.469223
7c51a493-d8c4-4fc4-8b64-a316642b64ad	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 17:10:49.440324
628b7536-1ac1-4b35-922a-8e764c601c78	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	确认	{}	[]	2026-03-05 17:20:14.690331
61057463-099d-4657-8f91-37dc59614c9e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留104开头的订单号	{}	[]	2026-03-06 10:42:52.90514
a01da12a-1c7b-4fe2-b7e0-66e747aec284	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留104开头的订单号	{}	[]	2026-03-06 10:47:45.543665
555297f7-45b1-4a0c-9a27-99f5304ad88d	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	已上传 2 个文件，请处理。	{}	[{"name": null, "path": "/uploads/2026/3/6/【西福商管】话费（欧飞）  官网_104900.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/6/【西福商管】话费（欧飞）  合单_104901.xlsx", "size": 0}]	2026-03-06 10:49:43.805298
811d137b-b17a-430b-b4d7-2b36e410ee43	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	编辑西福	{}	[]	2026-03-05 15:29:49.792225
330e8076-454c-40f8-929f-1c4deffeac51	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **真腾讯异业**\n• **喜马**	{}	[]	2026-03-05 15:30:28.420554
9a0f5bf8-9d5b-4618-b2dc-a2e30a075ad4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉金额取绝对值	{}	[]	2026-03-05 15:31:18.066579
bfa4ddea-01c0-4d6a-991f-a9fb890ef695	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-05 15:31:49.157014
41477fd1-8210-4958-8454-28ceaa2aca4c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「xxx」已删除	{}	[]	2026-03-05 16:43:04.732759
9c704e6b-75b7-4443-ab24-c22435ef4f34	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:45:23.243814
7ba424c1-f4b7-4525-9bf9-f16e3d097ced	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 16:46:27.09791
8d511e72-38e0-46b6-a387-fe9528ae5f7a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `ads_finance_d_inc_channel_details_20260105152012277_0_164535.xlsx`	{}	[]	2026-03-05 16:51:07.641575
2d4f8f8d-cdc1-4f55-9432-dba18ebde6e4	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	确认	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_165657.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx", "size": 0}]	2026-03-05 16:59:43.796629
353e459e-1e43-4d43-9969-c76db5e7c4d3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 17:03:04.737807
5d753dfc-a1bc-4886-bef2-2b85fd20c109	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_165634.xlsx`\n- `主营业务收入-上期2024_165634.xlsx`	{}	[]	2026-03-05 17:07:23.267856
aa96cb7e-1f11-45f6-b066-1f3e7c42ffe1	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx`	{}	[]	2026-03-05 17:08:46.538665
bf74f96c-b5a4-4b40-8504-ace62a02b63b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **1767597466118_170019.xlsx:** 1870条\n- **ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx:** 1864条\n- **匹配成功:** 1856条\n- **异常记录:** 22条\n- **匹配率:** 99.2%\n\n**异常明细 (22条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104251231234638768479 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260122162512658451 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260112081844177428 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104250730101120956853 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260112204110375695 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231231337736997 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131046426087 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260107124023245524 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231234226418848 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131017217568 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260120182524246431 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260120154831859614 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231233717277112 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104251130171618989036 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260121232312235785 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260111131034425031 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260110211042376700 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260111131015059724 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104250730102122996149 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260122234015356232 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231234629088856 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131030607475 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |	{}	[]	2026-03-05 17:10:49.46249
07c8809f-a50a-4621-abb9-8fd55c77e366	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-05 17:20:14.715544
85706c4d-b9bf-4b4f-a1d5-6e7ce0833484	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	删除仅保留103开头的订单号	{}	[]	2026-03-06 10:43:32.068731
9ed661b3-97f3-4092-87ce-7aaad9fb0d52	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 【西福商管】话费（欧飞）  官网.xlsx\n- 【西福商管】话费（欧飞）  合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-06 10:47:45.570259
a1d4fb3a-e815-4e60-a8f9-12d903d2b208	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 【西福商管】话费（欧飞）  官网.xlsx\n- 【西福商管】话费（欧飞）  合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据\n\n✅ 对账完成\n\n**对账概览**\n- **【西福商管】话费（欧飞）  官网_104542.xlsx:** 508条\n- **【西福商管】话费（欧飞）  合单_104543.xlsx:** 504条\n- **匹配成功:** 0条\n- **异常记录:** 1012条\n- **匹配率:** 0%\n\n**异常明细 (1012条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104260302093718667945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260228231428159849 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303172934595945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260305120849546264 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303114540229594 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030217342172965 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301171240138729 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030207223701836 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030420291944922 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217252694649 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030321464186558 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030218331756844 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260304180917679932 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030417113803887 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260305103845549035 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260302155726326794 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030515443350773 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301090038307113 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030317023515890 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217471700846 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n\n（共1012条，仅列前20条）	{}	[]	2026-03-06 10:49:43.873876
04c87927-e22e-4d85-9a7b-ea2c231f5997	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已删除	{}	[]	2026-03-06 11:12:37.107066
cd65d970-80dd-4f03-931e-b32f03c95390	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 15:29:49.817884
d372314e-f537-431d-9b5b-82c123bc2346	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「喜马」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 15:30:28.440065
61dd5a14-cbb9-4d32-b81c-50243a1ada76	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「喜马」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 15:31:18.085748
82c4341e-7e59-410e-b154-b7de3e6940b2	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **真腾讯异业**\n• **喜马**	{}	[]	2026-03-05 15:31:49.176149
77d00fea-6956-4bfd-a806-b17b57e38f13	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	去掉订单号去除首尾空格	{}	[]	2026-03-05 16:43:19.833799
84ff792f-ae38-4130-8316-651ec9f53557	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「测试1」已删除	{}	[]	2026-03-05 16:45:23.268682
322d8961-e1b0-4b02-bef5-11077f10908a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_164510.xlsx`\n- `主营业务收入-上期2024_164511.xlsx`	{}	[]	2026-03-05 16:46:27.1217
fef88b44-2d9b-4fb6-9407-dc177be4fc10	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉订单号去除收尾空格	{}	[]	2026-03-05 16:51:07.664942
8ece86c1-3670-434e-9242-11444c0c9c6f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，已退出对账流程。如果您需要其他帮助，随时告诉我。	{}	[]	2026-03-05 16:59:43.839201
ace64978-a099-4b8b-848e-aee4bba5ffe0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-05 17:03:04.769112
2498891e-e01e-4626-85eb-97d61c7362c9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 17:07:23.293584
7c4fa40b-cf6f-4e0f-9c72-44a2a9d1296a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_165634.xlsx`\n- `主营业务收入-上期2024_165634.xlsx`	{}	[]	2026-03-05 17:08:46.571293
333ebadc-5579-41d7-90c9-2bd6c1cdb0f6	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 17:10:49.4841
e46537cc-fcaa-417a-bb1c-a537648e2093	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 17:20:14.738377
7a4c0443-1295-4e62-a80d-5f4008e87f60	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-06 10:43:32.094095
f1a60c1b-910a-427c-93dc-07b9cadfc353	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-06 10:47:45.597291
858e5664-5156-465c-890d-e10c59119492	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	删除西福	{}	[{"name": null, "path": "/uploads/2026/3/6/【西福商管】话费（欧飞）  官网_104900.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/6/【西福商管】话费（欧飞）  合单_104901.xlsx", "size": 0}]	2026-03-06 10:49:59.231369
f8ba8705-0c1d-462d-b76b-2335cf0b9563	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福欧飞」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-06 11:11:25.789725
dc54470c-f7ba-4585-af07-2cf04c6b6265	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福欧飞」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-06 11:11:53.538129
b7bf498c-5de7-4e5f-95ec-57bbda9ca1b7	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 【西福商管】话费（欧飞）  官网.xlsx\n- 【西福商管】话费（欧飞）  合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-06 11:12:37.132002
68c43d84-cb85-453b-8ef8-cd1f55976293	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：腾讯异业\n- 腾讯异业_财务.xlsx\n- 腾讯异业_业务.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据\n\n✅ 对账完成\n\n**对账概览**\n- **腾讯异业_财务_104544.xlsx:** 100条\n- **腾讯异业_业务_104545.xlsx:** 100条\n- **匹配成功:** 100条\n- **异常记录:** 0条\n- **匹配率:** 100%\n\n🎉 完美匹配！所有记录均核对一致。	{}	[]	2026-03-06 13:47:05.566753
9512e01b-9e4b-4dbd-90d6-ce5d0c63703a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	对账任务已完成。\n\n**规则：** 审计对账（audio_recon）\n\n**对账文件：**\n1. **喜马-26合单与官网数据核对**：`合单_103744.xlsx` ↔ `官网_103744.xlsx`\n\n**统计：**\n- 匹配记录：6463 条\n- 差异记录：48 条\n\n**数据差异：**\n- 匹配但有差异: 37 条\n- 源文件独有: 1 条\n- 目标文件独有: 10 条\n\n- [详细差异报告 1](http://localhost:3335/output/recon/喜马-26合单与官网数据核对_核对结果_20260318_194948.xlsx)：喜马-26合单与官网数据核对_核对结果_20260318_194948.xlsx\n\n如需进一步分析或有疑问，请告知。	{}	[]	2026-03-18 19:49:48.729032
33a55da1-aef2-4fd1-82ed-38c03f5ed41d	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	增加订单号	{}	[]	2026-03-05 15:29:54.529801
42049248-15ae-409d-8822-ba120240d856	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	确认	{}	[]	2026-03-05 15:30:30.99903
0aae628b-4cd3-4f61-9496-461d84bbd574	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	去掉金额保留2位小数	{}	[]	2026-03-05 15:31:28.336446
e1ade168-36a4-4c02-bbf7-c39311f1f5f9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「喜马」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 15:31:49.197132
eb48cdad-5f8f-47b5-873d-dcb49225ba84	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉订单号去除首尾空格	{}	[]	2026-03-05 16:43:19.858491
ad49e719-e30e-4f5f-b619-819b25509642	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，返回规则配置。	{}	[]	2026-03-05 16:45:23.294058
5a63b3f3-c2f4-480e-a04c-5f348eb26d64	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：订单号去除首尾空格\n\n> 去掉首尾空格	{}	[]	2026-03-05 16:46:27.144471
9bd99e1b-6627-47be-a3b7-c4985cdbd200	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-05 16:51:07.689782
5ab8a402-b121-4ecb-8241-137de1b1c6b0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-05 16:59:43.886563
b54afbc7-6ef8-4661-b24a-5417578c1ec3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:03:04.800452
6709f054-c022-427b-abf1-8659764932fd	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-05 17:07:23.319124
e2eab1f3-4960-4956-9c6d-451ceb4130dd	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 17:08:46.603598
4d7c047d-53c3-4c89-a1f3-5fd98970a0aa	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:10:49.508171
c0b576b9-83fb-4cfa-b285-0b981a1aaacf	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-05 17:20:14.761652
f3695d0a-131b-411c-ad06-104de8dd3355	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:43:32.118529
74dec58f-9b8a-44d2-a11d-eeec44e33793	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-06 10:47:45.621979
85515c01-35fc-4765-bdb1-b971fe82ffbc	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已删除	{}	[]	2026-03-06 10:49:59.257522
234da997-36a9-42d3-b17a-aff9f889edec	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉订单号以104开头	{}	[]	2026-03-06 11:11:25.81787
a466317a-5654-4a20-ad7d-c4b290cd1678	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉订单号以104开头	{}	[]	2026-03-06 11:11:53.564967
bcf2de3c-264d-4f16-b84b-98177c93a05f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-06 11:12:37.158935
f020f6e6-86f5-4b80-952b-0db52dcd1f54	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	你好	{}	[]	2026-03-06 16:00:41.136065
4b2f8c9f-f261-40ad-b429-f3de69ff274e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	文件校验通过。\n\n**文件识别结果：**\n✅ **已匹配：**\n- **官网_103744.xlsx** → 喜马官网表\n- **合单_103744.xlsx** → 喜马合单表	{}	[]	2026-03-18 19:49:48.825951
a736df88-6133-44e9-bd00-0a955f9b5f29	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 15:29:54.553794
af34b43f-e7f9-4a51-b463-11d1a0407c34	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 15:30:31.025858
06f7368a-cbad-42da-9b85-98f90b49c37e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 15:31:28.360653
cf187e7e-50fd-4278-8e84-32b0c759c2b6	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	规则列表	{}	[]	2026-03-05 15:31:58.937861
29f86414-4495-46cb-95ad-f9274a9e9908	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试1」的编辑...	{}	[]	2026-03-05 16:43:19.881885
41fb92ae-77d8-43c4-8a03-c37747f8c9d8	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉金额取绝对值	{}	[]	2026-03-05 16:45:23.318823
22ac6248-1c64-4e60-ad1c-0c856ca72a3f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉订单号去除首尾空格	{}	[]	2026-03-05 16:46:27.166794
4fdf77af-fc0a-4a90-a4b6-66ca4b4a1d95	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 16:51:07.712131
dd5dcf7e-a536-4ffb-b44c-4527ed31475c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:59:43.934228
7638f0f8-b844-4ee0-9a43-6b271575707b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ❌ 文件1 删除 order_id 字段\n  ❌ 文件2 删除 order_id 字段	{}	[]	2026-03-05 17:03:04.82971
65cbf2a9-02b6-4c38-81b8-6a0406ea8399	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:07:23.345864
413f2ec1-651a-43f0-8a5c-14fb8f8e769a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-05 17:08:46.636668
f91ff21f-98cd-4b78-8030-0b0ea0309cc8	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx`	{}	[]	2026-03-05 17:10:49.53182
aa5aae79-524a-43a8-9e44-67e4a7982897	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	保存	{}	[]	2026-03-05 17:20:18.948014
0981680a-ef16-4d27-bf98-d81223c300f6	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留103开头的订单号	{}	[]	2026-03-06 10:43:32.142991
61872262-46cc-4c64-8c71-41132f01ba69	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留103开头的订单号	{}	[]	2026-03-06 10:47:45.647982
f13485e0-6a54-49c4-8567-d53d01cd9a33	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	删除西福欧飞	{}	[]	2026-03-06 10:50:09.795963
8df76e6a-1553-4e97-9199-bc7db8cbce82	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已删除	{}	[]	2026-03-06 11:11:25.893014
5e6b74d5-f531-4e38-8dc2-a42028f51c92	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已删除	{}	[]	2026-03-06 11:11:53.593854
407603f8-bf87-4ce1-a038-190b70398bb1	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：仅保留104开头的订单号（两个文件）\n\n> 订单号以104开头	{}	[]	2026-03-06 11:12:37.185564
2c87189c-9342-40ec-9676-d45ca09307c4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	你好！有什么可以帮助你的吗？	{}	[]	2026-03-06 16:00:41.263889
41358143-e78c-496d-9ce6-c11e1be78036	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	对账任务已完成。\n\n**规则：** 审计对账（audio_recon）\n\n**对账文件：**\n1. **喜马-26合单与官网数据核对**：`合单_103744.xlsx` ↔ `官网_103744.xlsx`\n\n**统计：**\n- 匹配记录：6463 条\n- 差异记录：48 条\n\n**数据差异：**\n- 匹配但有差异: 37 条\n- 源文件独有: 1 条\n- 目标文件独有: 10 条\n\n- [详细差异报告 1](http://localhost:3335/output/recon/喜马-26合单与官网数据核对_核对结果_20260318_103749.xlsx)：喜马-26合单与官网数据核对_核对结果_20260318_103749.xlsx\n\n如需进一步分析或有疑问，请告知。	{}	[]	2026-03-18 19:49:48.894743
903fc432-b0cd-426c-848a-938cbbcd7677	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:29:54.579609
ac0fbae0-5dac-485e-955a-1bdbd7bcbfb9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:30:31.057465
7d333bf8-e9dd-4dfd-96f0-2830d5a86a9e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:31:28.386471
0210ec88-f40f-442f-9e39-e8ad946f5731	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **真腾讯异业**\n• **喜马**	{}	[]	2026-03-05 15:31:58.962223
d8cafcaf-627f-44a8-bdce-65fd36819326	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **xxx**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:43:19.90608
b68d5c1b-e43e-461c-a75b-9de559c25d30	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 16:45:23.343057
d88938b9-0569-49cd-8b9c-e12ac5ab20ea	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「测试1」已更新！	{}	[]	2026-03-05 16:46:27.187492
cd9d83b9-4763-48cb-a3bc-d2dd4ac76584	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **xxx**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:51:07.734834
1caa7737-5496-43f7-b3be-79ec7253c2f3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 16:59:43.974507
400f6bf8-a8d5-4c07-8e90-d7b63a6976f9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	很高兴对账顺利完成！匹配率达到了99.2%，结果很不错。\n\n如果您需要查看详细的对账报告、导出结果，或者想调整规则以进一步提高匹配率，随时告诉我。	{}	[]	2026-03-05 17:03:04.860234
1dad0efe-9bc8-4ab5-9d71-d489b5d99303	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ❌ 文件1 删除 order_id 字段\n  ❌ 文件2 删除 order_id 字段	{}	[]	2026-03-05 17:07:23.369918
b96baa30-d8a5-4802-80f9-d6bac514d450	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:08:46.668893
4497c466-0771-4d82-8a95-2249aad2f61a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_165634.xlsx`\n- `主营业务收入-上期2024_165634.xlsx`	{}	[]	2026-03-05 17:10:49.554294
83d2096d-ed29-44da-888d-a0814995ff1a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-05 17:20:18.973612
465752e7-fbf2-45a8-9e13-1095a9fb4639	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	确认	{}	[]	2026-03-06 10:43:43.336814
cac36f3b-b6e9-4598-99cb-af2425275188	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:47:45.675148
a008b7eb-cce0-43ff-8738-d652a6a57ff2	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福欧飞」已删除	{}	[]	2026-03-06 10:50:09.824894
10f197e6-1dcf-4812-9897-3608a188dd4e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 【西福商管】话费（欧飞）  官网.xlsx\n- 【西福商管】话费（欧飞）  合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-06 11:11:25.922542
9fb146ce-bb23-4437-803f-dfe1215148e7	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 【西福商管】话费（欧飞）  官网.xlsx\n- 【西福商管】话费（欧飞）  合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-06 11:11:53.61871
155b8248-cc28-450e-9e2b-320b89e9a89a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉进保留104开头的订单	{}	[]	2026-03-06 11:12:37.212257
d9758d37-a2a8-4b3b-b6fc-b416988f6d9a	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	？？	{}	[{"name": null, "path": "/uploads/2026/3/18/官网_103744.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/18/合单_103744.xlsx", "size": 0}]	2026-03-18 19:50:01.394573
521497c0-680f-4225-9131-52060d9ac934	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	不客气！很高兴能帮到你。😊\n\n对账结果显示匹配率高达 **99.85%**，只有10条异常记录，整体数据质量非常好。\n\n**主要异常类型：**\n1. **官网有但合单无**（7条）- 可能是订单未同步或状态不一致\n2. **金额差异**（3条）- 金额差异超出容差范围\n\n如果需要进一步分析这些异常订单，或者需要导出对账报告，随时告诉我！	{}	[]	2026-03-05 15:29:54.601383
198dd0bd-a355-40de-9c27-5b44dc1bd93a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	不客气！很高兴能帮到你。😊\n\n对账结果显示匹配率高达 **99.85%**，只有10条异常记录，整体数据质量非常好。\n\n**主要异常类型：**\n1. **官网有但合单无**（7条）- 可能是订单未同步或状态不一致\n2. **金额差异**（3条）- 金额差异超出容差范围\n\n如果需要进一步分析这些异常订单，或者需要导出对账报告，随时告诉我！	{}	[]	2026-03-05 15:30:31.081124
86834062-b8ac-44f3-a6f5-7b7c1c274476	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	不客气！很高兴能帮到你。😊\n\n对账结果显示匹配率高达 **99.85%**，只有10条异常记录，整体数据质量非常好。\n\n**主要异常类型：**\n1. **官网有但合单无**（7条）- 可能是订单未同步或状态不一致\n2. **金额差异**（3条）- 金额差异超出容差范围\n\n如果需要进一步分析这些异常订单，或者需要导出对账报告，随时告诉我！	{}	[]	2026-03-05 15:31:28.410777
98bddeec-dd5c-4d66-b1f2-98d4daa2498b	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	规则列表	{}	[]	2026-03-05 16:04:55.332248
5578c8a1-66b8-4c90-a573-e2a928950fcd	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「xxx」已删除	{}	[]	2026-03-05 16:43:19.933502
45a2b8d3-f97c-4381-94e2-58cec79f2f55	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_164510.xlsx`\n- `主营业务收入-上期2024_164511.xlsx`	{}	[]	2026-03-05 16:45:23.36717
710bd019-4aac-494b-90f2-7ef213b75bd3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试1」的编辑...	{}	[]	2026-03-05 16:46:27.212284
9698c14f-c191-463a-929b-7560d3480c26	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:51:07.756909
f05e3f64-dc4b-4422-b933-86aefbf0f7ed	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 16:59:44.017836
b9ab681a-14a3-4d76-87f3-c9e8e5a2a89a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-05 17:03:04.898565
c5378889-a6cb-45f1-9aad-331c96814c62	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	很高兴对账顺利完成！匹配率达到了99.2%，结果很不错。\n\n如果您需要查看详细的对账报告、导出结果，或者想调整规则以进一步提高匹配率，随时告诉我。	{}	[]	2026-03-05 17:07:23.39539
fa906976-34d5-4059-aa38-79055dba64a4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ❌ 文件1 删除 order_id 字段\n  ❌ 文件2 删除 order_id 字段	{}	[]	2026-03-05 17:08:46.70164
a72a7fe4-40db-441d-8f48-1c83602ac551	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 17:10:49.576055
05bfa1a0-6b27-4399-bcc9-27c2287414ab	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-05 17:20:18.996892
97bafe9e-6e93-4614-a41f-72e936d718f3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-06 10:43:43.358541
c61bf825-b25e-4d62-915b-2a234d87a808	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉进保留104开头的订单	{}	[]	2026-03-06 10:47:45.700387
455bba43-181f-4da5-9998-d3820430ece2	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	规则列表	{}	[]	2026-03-06 10:50:16.611817
47953fcf-41af-4540-956e-d3384c64c894	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-06 11:11:25.949578
49a2abb5-627f-43d3-8b83-da4adb1e6e18	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-06 11:11:53.646353
777d1755-09c8-4422-beea-05e1c6945e3f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **【西福商管】话费（欧飞）  官网_104542.xlsx:** 508条\n- **【西福商管】话费（欧飞）  合单_104543.xlsx:** 504条\n- **匹配成功:** 0条\n- **异常记录:** 1012条\n- **匹配率:** 0%\n\n**异常明细 (1012条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104260302093718667945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260228231428159849 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303172934595945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260305120849546264 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303114540229594 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030217342172965 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301171240138729 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030207223701836 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030420291944922 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217252694649 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030321464186558 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030218331756844 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260304180917679932 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030417113803887 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260305103845549035 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260302155726326794 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030515443350773 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301090038307113 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030317023515890 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217471700846 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n\n（共1012条，仅列前20条）	{}	[]	2026-03-06 11:12:37.24053
fc70899f-87ed-44c9-a258-1ddf36df3046	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	对账任务已完成。\n\n**规则：** 审计对账（audio_recon）\n\n**对账文件：**\n1. **喜马-26合单与官网数据核对**：`合单_103744.xlsx` ↔ `官网_103744.xlsx`\n\n**统计：**\n- 匹配记录：6463 条\n- 差异记录：48 条\n\n**数据差异：**\n- 匹配但有差异: 37 条\n- 源文件独有: 1 条\n- 目标文件独有: 10 条\n\n- [详细差异报告 1](http://localhost:3335/output/recon/喜马-26合单与官网数据核对_核对结果_20260318_195000.xlsx)：喜马-26合单与官网数据核对_核对结果_20260318_195000.xlsx\n\n如需进一步分析或有疑问，请告知。	{}	[]	2026-03-18 19:50:01.468659
b7f02d29-bf2b-4598-926b-ffa716582099	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_152455.xlsx`\n- `主营业务收入-上期2024_152455.xlsx`	{}	[]	2026-03-05 15:29:54.62329
f1f273c5-1861-4574-99bc-1bbd9905c2a0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_152455.xlsx`\n- `主营业务收入-上期2024_152455.xlsx`	{}	[]	2026-03-05 15:30:31.105442
720869fd-4a08-4b4d-9be6-1f9c25a5ac9e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_152455.xlsx`\n- `主营业务收入-上期2024_152455.xlsx`	{}	[]	2026-03-05 15:31:28.436396
82470398-2ad7-41c0-826b-efff9868bb2d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **真腾讯异业**\n• **喜马**	{}	[]	2026-03-05 16:04:55.358598
95068385-eb1c-4f24-9ec8-d4b83023d0cf	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	去掉订单号去除首尾空格	{}	[]	2026-03-05 16:43:24.469119
b470a33a-4ea8-4529-a117-eed252ce4a0c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：订单号去除首尾空格\n\n> 去掉首尾空格	{}	[]	2026-03-05 16:45:23.393385
1d3db870-86a7-4486-935b-1fc28f16b84b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `ads_finance_d_inc_channel_details_20260105152012277_0_164535.xlsx`	{}	[]	2026-03-05 16:46:27.236249
dabdf32b-c881-438d-889c-78546c7e5bee	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  🚫 文件1 从 order_id 中移除列别名: sp订单号	{}	[]	2026-03-05 16:51:07.78786
6119c7de-fa5b-44ae-9fe7-900cf18894d2	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx`	{}	[]	2026-03-05 16:59:44.058613
1112c3ea-4204-480b-b3bc-b760ad20aea3	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	去掉订单编号、订单号	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_170247.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx", "size": 0}]	2026-03-05 17:03:42.634044
661d8c85-d39a-49a7-958e-27ee4c7cdd75	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-05 17:07:23.420302
2687d565-5017-4c28-a53a-41d35298e897	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 官网.xlsx\n- 合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:29:54.647479
2b83d144-253e-4adc-af54-bba402c6af22	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 官网.xlsx\n- 合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:30:31.126705
33b29597-e83e-4e13-a586-da228d5a5e3b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 官网.xlsx\n- 合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:31:28.459835
08088ec4-cb65-42bf-932a-fc6c730d1727	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	删除真腾讯异业	{}	[]	2026-03-05 16:05:07.466163
1309e78b-66f3-49eb-b748-f406b535ad86	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉订单号去除首尾空格	{}	[]	2026-03-05 16:43:24.502859
38e5b211-2060-4b47-bc6f-e689ef2d32d7	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉订单号去除首尾空格	{}	[]	2026-03-05 16:45:23.417914
c6d3ac67-c305-4ee4-a945-39a4082f0548	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉订单号去除收尾空格	{}	[]	2026-03-05 16:46:27.260184
d721d98a-dfdc-4b21-9132-6045286d0f9f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-05 16:51:07.842048
cf1852b1-6462-425f-8a9f-e9ed79364de8	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_165634.xlsx`\n- `主营业务收入-上期2024_165634.xlsx`	{}	[]	2026-03-05 16:59:44.105514
2064d9d6-dc9f-43f6-8074-15d9ca00b26c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-05 17:03:42.732095
e672a215-08d7-477f-af93-796f8d279029	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	订单号去掉前单引号，并截取前21位	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_170247.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx", "size": 0}]	2026-03-05 17:08:28.897915
d3f7ef18-4aa3-4eec-af30-efb9a1695674	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	很高兴对账顺利完成！匹配率达到了99.2%，结果很不错。\n\n如果您需要查看详细的对账报告、导出结果，或者想调整规则以进一步提高匹配率，随时告诉我。	{}	[]	2026-03-05 17:08:46.733954
880d7033-0e70-4a53-96cc-e15efe8cd72f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-05 17:10:49.598778
6f814bf4-e17a-4d5c-a328-08acb2047c96	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 17:20:19.019808
123f9bcb-1479-4ba4-b222-ef28e1dfe894	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-06 10:43:43.382695
1e303d1a-97fe-41d5-9649-08d1409baa10	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉订单号以104开头	{}	[]	2026-03-06 10:47:45.728615
f66dbf88-64b9-4977-8a89-ef2859e02608	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:50:16.637707
3186b994-18a8-4e2c-8bf6-4d3f1bd38cfb	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：仅保留104开头的订单号（两个文件）\n\n> 订单号以104开头	{}	[]	2026-03-06 11:11:25.975745
2e4549dc-0fd0-402d-a994-735a9c94cdd5	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：仅保留104开头的订单号（两个文件）\n\n> 订单号以104开头	{}	[]	2026-03-06 11:11:53.670057
1c728a0d-1f9d-466f-be95-03acfc2218d4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	❌ 未找到规则「西福欧飞」，请检查规则名称是否正确。	{}	[]	2026-03-06 11:12:37.26642
c4b3d4f1-d468-4135-8758-fff3fb6896e1	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	文件校验通过。\n\n**文件识别结果：**\n✅ **已匹配：**\n- **官网_103744.xlsx** → 喜马官网表\n- **合单_103744.xlsx** → 喜马合单表	{}	[]	2026-03-18 19:50:01.532484
e17b0bef-b15c-4166-a5d5-d4f8ea14a22c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 官网_152552.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:29:54.670005
4da6c2aa-ee48-4379-924b-9a4777b8550e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 官网_152552.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:30:31.14865
f6435291-5a80-4560-bb6b-a6654eb73d25	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 官网_152552.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:31:28.482294
ac64ab2e-2951-4405-b9d8-a9b43e7e83a2	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「真腾讯异业」已删除	{}	[]	2026-03-05 16:05:07.491656
d7b8b39b-f5db-4e8c-9439-0c091f2deb64	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试1」的编辑...	{}	[]	2026-03-05 16:43:24.528697
e09b1005-72e6-49f3-bc3f-c2177de10346	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「测试1」已更新！	{}	[]	2026-03-05 16:45:23.443699
5679e9e6-fba2-4ef8-a739-4fca34e57c4d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-05 16:46:27.283839
2494ddc8-7590-4ea0-9201-5142038f0c65	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	规则列表	{}	[]	2026-03-05 16:56:15.718664
96953065-b646-44e0-95e7-3a7496e0deca	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 16:59:44.149218
615ab7df-7b73-4fa7-9f60-3eba0d852be1	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🎯 **开始创建新的对账规则**\n\n我会引导你完成以下4个步骤：\n\n1️⃣ 上传并分析文件 - 分析文件结构和列名\n\n2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）\n\n3️⃣ 配置规则参数 - 设置容差、订单号特征等\n\n4️⃣ 预览并保存 - 查看规则效果并保存\n\n请先上传需要对账的文件（文件1和文件2各一个 Excel/CSV 文件）。	{}	[]	2026-03-05 17:03:42.822663
6e10336f-6657-4529-be4f-f8467e13138a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-05 17:08:28.931349
3023bdcc-2a75-4634-be3e-8be348dd3814	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-05 17:08:46.764337
a73b30c3-04cf-4531-a0f5-97021137b813	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:10:49.637786
40f4c557-a2c3-44c4-a437-6b0c938e9f27	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-05 17:20:19.043139
4a7186e3-34b0-4b39-a370-f83d91488f64	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:43:43.403159
0438cc05-1b75-4b12-a87c-a727ba57aa0d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **【西福商管】话费（欧飞）  官网_104542.xlsx:** 508条\n- **【西福商管】话费（欧飞）  合单_104543.xlsx:** 504条\n- **匹配成功:** 0条\n- **异常记录:** 1012条\n- **匹配率:** 0%\n\n**异常明细 (1012条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104260302093718667945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260228231428159849 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303172934595945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260305120849546264 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303114540229594 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030217342172965 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301171240138729 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030207223701836 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030420291944922 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217252694649 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030321464186558 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030218331756844 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260304180917679932 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030417113803887 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260305103845549035 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260302155726326794 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030515443350773 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301090038307113 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030317023515890 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217471700846 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n\n（共1012条，仅列前20条）	{}	[]	2026-03-06 10:47:45.752243
413252d2-e5c2-46c3-bcfe-ad5753e71865	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	删除西福欧飞	{}	[]	2026-03-06 10:50:27.216245
e9afda22-de1a-4b85-b050-d64426c757e8	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉进保留104开头的订单	{}	[]	2026-03-06 11:11:26.001383
2ca96dce-d820-4491-bb11-5c6a97a3d9a6	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉进保留104开头的订单	{}	[]	2026-03-06 11:11:53.695957
50a5c84a-4bfc-4bbb-892c-a86c304d28f3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-06 11:12:37.292093
4410d5e4-3cea-4c3b-8ade-056a1c4b4f04	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📊 **开始对账执行任务**\n\n已选择规则：**审计对账（audio_recon）**\n已上传文件：2 个\n\n正在校验文件并加载规则...	{}	[]	2026-03-18 19:50:01.59834
ad185558-67ce-439e-bedd-8546903e51c8	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 1767597466118.csv\n- ads_finance_d_inc_channel_details_20260105152012277_0.csv\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:29:54.692787
bc414be5-99d7-4b43-b9b8-771b08614ac4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 1767597466118.csv\n- ads_finance_d_inc_channel_details_20260105152012277_0.csv\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:30:31.170435
6f293aac-29b0-4b9c-b607-dc4c1b936f01	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 1767597466118.csv\n- ads_finance_d_inc_channel_details_20260105152012277_0.csv\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:31:28.505724
4d63c3c1-a458-4338-94c9-54bf4109e2db	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	规则列表	{}	[]	2026-03-05 16:05:18.502118
ba2bdfae-6bda-42bf-a6a7-144a24b062b8	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **xxx**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:43:24.555856
67d8345e-5e75-4bc5-9213-a06aaeb281ba	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试1」的编辑...	{}	[]	2026-03-05 16:45:23.468099
e740da24-495f-4e4b-a88c-86091a908d2e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 16:46:27.307697
5b70d5b8-e455-41a7-a637-1fdaac44146d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:56:15.74764
218d87c0-f0dc-4f30-9ded-c76f05186305	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 16:59:44.203863
0102bf12-c119-46d8-aa25-647b40299621	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，已退出对账流程。如果您需要其他帮助，随时告诉我。	{}	[]	2026-03-05 17:03:42.878794
f434b8e4-ccb9-47a7-a052-92eff91c68ae	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🎯 **开始创建新的对账规则**\n\n我会引导你完成以下4个步骤：\n\n1️⃣ 上传并分析文件 - 分析文件结构和列名\n\n2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）\n\n3️⃣ 配置规则参数 - 设置容差、订单号特征等\n\n4️⃣ 预览并保存 - 查看规则效果并保存\n\n请先上传需要对账的文件（文件1和文件2各一个 Excel/CSV 文件）。	{}	[]	2026-03-05 17:08:28.96591
4c87ea86-143a-49fc-8dd9-f83917da54b0	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	确认	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_170247.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx", "size": 0}]	2026-03-05 17:09:46.965256
6723229f-8f27-499a-a377-f405ef6ccb52	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则已保存为「测试」！您可以在后续对账中直接使用此规则。	{}	[]	2026-03-05 17:10:49.664586
2f9ea663-b9ac-476e-8cd9-1ab4e9ac402c	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	规则列表	{}	[]	2026-03-05 17:20:26.468559
3b6158ce-a990-4d0d-9439-cafb965cdeca	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	保存	{}	[]	2026-03-06 10:43:51.008513
6ef546b4-f320-4c9d-a148-6a13625095d7	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：仅保留104开头的订单号（两个文件）\n\n> 订单号以104开头	{}	[]	2026-03-06 10:47:45.778679
49b341bd-96e1-418f-bc12-6ff4e7966060	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福欧飞」已删除	{}	[]	2026-03-06 10:50:27.243429
fee365ec-9953-4930-9a20-ef4e71f9df46	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **【西福商管】话费（欧飞）  官网_104542.xlsx:** 508条\n- **【西福商管】话费（欧飞）  合单_104543.xlsx:** 504条\n- **匹配成功:** 0条\n- **异常记录:** 1012条\n- **匹配率:** 0%\n\n**异常明细 (1012条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104260302093718667945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260228231428159849 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303172934595945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260305120849546264 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303114540229594 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030217342172965 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301171240138729 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030207223701836 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030420291944922 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217252694649 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030321464186558 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030218331756844 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260304180917679932 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030417113803887 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260305103845549035 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260302155726326794 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030515443350773 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301090038307113 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030317023515890 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217471700846 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n\n（共1012条，仅列前20条）	{}	[]	2026-03-06 11:11:26.029626
ced2b6f5-aedf-45d1-9c35-8554195cb391	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **【西福商管】话费（欧飞）  官网_104542.xlsx:** 508条\n- **【西福商管】话费（欧飞）  合单_104543.xlsx:** 504条\n- **匹配成功:** 0条\n- **异常记录:** 1012条\n- **匹配率:** 0%\n\n**异常明细 (1012条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104260302093718667945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260228231428159849 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303172934595945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260305120849546264 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303114540229594 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030217342172965 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301171240138729 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030207223701836 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030420291944922 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217252694649 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030321464186558 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030218331756844 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260304180917679932 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030417113803887 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260305103845549035 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260302155726326794 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030515443350773 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301090038307113 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030317023515890 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217471700846 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n\n（共1012条，仅列前20条）	{}	[]	2026-03-06 11:11:53.721494
dfe38d00-fdbf-42d6-97b8-ac3435853f61	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-06 11:12:37.316365
6dc19ea3-7d8d-461b-ac4d-a55d1a12c9e7	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	对账任务已完成。\n\n**规则：** 审计对账（audio_recon）\n\n**对账文件：**\n1. **喜马-26合单与官网数据核对**：`合单_103744.xlsx` ↔ `官网_103744.xlsx`\n\n**统计：**\n- 匹配记录：6463 条\n- 差异记录：48 条\n\n**数据差异：**\n- 匹配但有差异: 37 条\n- 源文件独有: 1 条\n- 目标文件独有: 10 条\n\n- [详细差异报告 1](http://localhost:3335/output/recon/喜马-26合单与官网数据核对_核对结果_20260318_194948.xlsx)：喜马-26合单与官网数据核对_核对结果_20260318_194948.xlsx\n\n如需进一步分析或有疑问，请告知。	{}	[]	2026-03-18 19:50:01.665394
5d0714fb-4652-4fae-b0a9-60a5893dab3f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **官网_152735.xlsx:** 6489条\n- **合单_152735.xlsx:** 6479条\n- **匹配成功:** 6479条\n- **异常记录:** 10条\n- **匹配率:** 99.85%\n\n**异常明细 (10条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| L26012422340153819700 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012116163721519400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260124070644706639 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012123094296319400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260121215420799296 | 官网_152735.xlsx金额 53.099999999999994 vs 合单_152735.xlsx金额 70.8，差额 17.70 超出容差 0.1 |\n| L26011211340303919100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012119191879219100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260123134427719478 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012218172999819300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012014530342619300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |	{}	[]	2026-03-05 15:29:54.715715
bb5cf114-a36d-44ee-8341-28c16bd65d49	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **官网_152735.xlsx:** 6489条\n- **合单_152735.xlsx:** 6479条\n- **匹配成功:** 6479条\n- **异常记录:** 10条\n- **匹配率:** 99.85%\n\n**异常明细 (10条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| L26012422340153819700 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012116163721519400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260124070644706639 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012123094296319400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260121215420799296 | 官网_152735.xlsx金额 53.099999999999994 vs 合单_152735.xlsx金额 70.8，差额 17.70 超出容差 0.1 |\n| L26011211340303919100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012119191879219100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260123134427719478 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012218172999819300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012014530342619300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |	{}	[]	2026-03-05 15:30:31.190019
9673065f-9350-47cc-8fd0-b66d52a642af	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **官网_152735.xlsx:** 6489条\n- **合单_152735.xlsx:** 6479条\n- **匹配成功:** 6479条\n- **异常记录:** 10条\n- **匹配率:** 99.85%\n\n**异常明细 (10条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| L26012422340153819700 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012116163721519400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260124070644706639 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012123094296319400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260121215420799296 | 官网_152735.xlsx金额 53.099999999999994 vs 合单_152735.xlsx金额 70.8，差额 17.70 超出容差 0.1 |\n| L26011211340303919100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012119191879219100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260123134427719478 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012218172999819300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012014530342619300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |	{}	[]	2026-03-05 15:31:28.526793
1386e70e-feb8-439e-9ea9-f68e2a2036b3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:05:18.527827
8fa9ad30-cd00-404b-a54b-668a5824b64c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「xxx」已删除	{}	[]	2026-03-05 16:43:24.582507
a0728356-d800-4419-a3fe-fd291a44fb0d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉订单号去除收尾空格	{}	[]	2026-03-05 16:45:23.544962
72a4040e-5d73-45e8-a007-e4dadbe0347a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **xxx**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:46:27.333247
1e9023e1-83ef-42e6-917a-99ae1fb5dd75	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	西福	{}	[]	2026-03-05 16:56:18.596108
e99d9063-f7ca-4d2b-b495-acd06dee4500	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	保存	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_165657.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx", "size": 0}]	2026-03-05 16:59:49.13229
c571fabe-5add-4acc-99a6-c22c02f5a1d8	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ➕ 文件1 添加 order_id: sp订单号\n  ➕ 文件2 添加 order_id: sup订单号	{}	[]	2026-03-05 17:03:42.934446
ee9034e0-1bef-4170-a1f7-9d125974be81	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，已退出对账流程。如果您需要其他帮助，随时告诉我。	{}	[]	2026-03-05 17:08:28.998493
1ef923f4-3d26-4a8e-9359-f2f50b732cef	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-05 17:09:46.999554
2d5ac39b-2ab2-444a-84f8-d89ffeb5fccd	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ❌ 文件1 删除 order_id 字段\n  ❌ 文件2 删除 order_id 字段	{}	[]	2026-03-05 17:10:49.694503
511f74df-597e-4d0e-9608-8dd076ab11f9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-05 17:20:26.492384
ca97f090-b056-4e56-83f0-ce7ade489198	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-06 10:43:51.031366
2c50b61b-35a1-4a9e-9c0c-4ea30c4c3c4c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-06 10:47:45.808183
2b4df1f1-c37b-4beb-88f0-b58bae6d0e6d	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	删除西福欧飞	{}	[]	2026-03-06 10:50:36.787438
4056bf8a-d8d2-4200-8fa0-6cbcf78f4053	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	❌ 未找到规则「西福欧飞」，请检查规则名称是否正确。	{}	[]	2026-03-06 11:11:26.054094
8ed389ca-0bb5-4689-9173-a4b3ff496cf4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	❌ 未找到规则「西福欧飞」，请检查规则名称是否正确。	{}	[]	2026-03-06 11:11:53.752098
88075163-ec8a-4d1f-aa7e-cbae348f969c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 【西福商管】话费（欧飞）  官网.xlsx\n- 【西福商管】话费（欧飞）  合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据\n\n✅ 对账完成\n\n**对账概览**\n- **【西福商管】话费（欧飞）  官网_104542.xlsx:** 508条\n- **【西福商管】话费（欧飞）  合单_104543.xlsx:** 504条\n- **匹配成功:** 0条\n- **异常记录:** 1012条\n- **匹配率:** 0%\n\n**异常明细 (1012条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104260302093718667945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260228231428159849 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303172934595945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260305120849546264 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303114540229594 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030217342172965 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301171240138729 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030207223701836 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030420291944922 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217252694649 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030321464186558 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030218331756844 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260304180917679932 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030417113803887 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260305103845549035 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260302155726326794 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030515443350773 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301090038307113 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030317023515890 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217471700846 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n\n（共1012条，仅列前20条）	{}	[]	2026-03-06 11:12:37.342263
4dfdb709-0a06-44d6-9d09-c207db002009	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 合单_152700.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:29:54.740388
945357ad-c993-452a-9080-879f9743e2be	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 合单_152700.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:30:31.212368
8a1601b9-8eb1-4a38-aa8d-d0f17de0c9f0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉金额保留2位小数	{}	[]	2026-03-05 15:31:28.54786
b2dd8dc7-c613-4b28-bf03-3c29148ddf57	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	规则列表	{}	[]	2026-03-05 16:41:01.09854
6e2c599e-0612-41ca-860c-f5074693f718	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	去掉金额取绝对值	{}	[]	2026-03-05 16:43:34.292179
b8964b01-7ca1-488a-a40a-af6b9d8dd035	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-05 16:45:23.573621
ea5c9bf0-ea46-4870-91e3-78c5156cea8f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:46:27.354918
566dae80-c014-48e6-af96-544ff5e82ada	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 16:56:18.621122
44e9e7c7-ecec-4ee2-95c0-d49e45b29736	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，已退出对账流程。如果您需要其他帮助，随时告诉我。	{}	[]	2026-03-05 16:59:49.196079
83648590-1c82-494c-86d0-1be829ff4be9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-05 17:03:42.974857
c473f746-7a4e-4e39-86c8-00c5477e42a0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ➕ 文件1 添加 order_id: sp订单号\n  ➕ 文件2 添加 order_id: sup订单号	{}	[]	2026-03-05 17:08:29.031697
a7d33925-d57f-4d7a-b0d4-ffba4afa4198	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 17:09:47.030064
5f7de543-6739-4fd8-abe2-523fb0b7b10a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	很高兴对账顺利完成！匹配率达到了99.2%，结果很不错。\n\n如果您需要查看详细的对账报告、导出结果，或者想调整规则以进一步提高匹配率，随时告诉我。	{}	[]	2026-03-05 17:10:49.720566
98de1286-28a1-4da8-8f4a-4542c9eaad35	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	西福	{}	[]	2026-03-05 17:21:12.845662
7655e348-3731-4790-9f6a-dafaa1387c7a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:43:51.059993
73fb8fb8-34ca-4dbc-a172-7fc00e88ec07	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-06 10:47:45.83156
5e828dde-1c92-4c6a-b1f2-5cc5b1c6e8c1	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	❌ 未找到规则「西福欧飞」，请检查规则名称是否正确。	{}	[]	2026-03-06 10:50:36.813026
9c1a3c50-d0be-45c8-a762-324b9168c069	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-06 11:11:26.079618
f7cc95d2-f79f-47f9-a3e2-4b73cbd3a2a2	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-06 11:11:53.781477
8251d6a3-8365-49bd-96be-a4d7f41c79a4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:12:37.366537
3d5b0936-6c44-4b6c-994a-96ca021364ad	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	对账任务已完成。\n\n**规则：** 审计对账（audio_recon）\n\n**对账文件：**\n1. **喜马-26合单与官网数据核对**：`合单_103744.xlsx` ↔ `官网_103744.xlsx`\n\n**统计：**\n- 匹配记录：6463 条\n- 差异记录：48 条\n\n**数据差异：**\n- 匹配但有差异: 37 条\n- 源文件独有: 1 条\n- 目标文件独有: 10 条\n\n- [详细差异报告 1](http://localhost:3335/output/recon/喜马-26合单与官网数据核对_核对结果_20260318_103749.xlsx)：喜马-26合单与官网数据核对_核对结果_20260318_103749.xlsx\n\n如需进一步分析或有疑问，请告知。	{}	[]	2026-03-18 19:50:01.743037
ff9992a7-1495-490b-aa47-bd084051cdd0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `1767597466118_152522.csv`	{}	[]	2026-03-05 15:29:54.763028
46b15f92-434f-4573-b490-f844078e5b37	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `1767597466118_152522.csv`	{}	[]	2026-03-05 15:30:31.232364
6e539530-7eda-4a01-9512-ec587ca6fabf	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 合单_152700.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:31:28.572391
436d2ae1-67c6-4c5d-95dc-2d5624443386	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **xxx**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:41:01.129674
82accca1-a32d-456e-8e9e-70f57e7668c0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试1」的编辑...	{}	[]	2026-03-05 16:43:34.324416
393b8e6b-9e21-47c7-824f-7520df4e6a1b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 16:45:23.602232
961d6924-71e4-430c-998a-c8d6c9be793d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  🚫 文件1 从 order_id 中移除列别名: sp订单号	{}	[]	2026-03-05 16:46:27.374762
575cd760-9bd8-42fd-a57a-8257081c492a	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	已上传 2 个文件，请处理。	{}	[{"name": null, "path": "/uploads/2026/3/5/主营业务收入-本期2025_165634.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/主营业务收入-上期2024_165634.xlsx", "size": 0}]	2026-03-05 16:56:45.839573
0f631937-6379-4176-b02e-e3a1dd7bc03f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:59:49.248848
bbb22397-10b6-4f3b-a327-df017f11ab10	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 17:03:43.020794
f2867f46-8e80-4597-bdd5-bfbecb2ee7c0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-05 17:08:29.063684
8fbe0465-38bc-4c3f-b968-dd6a9cfd9ddc	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx`	{}	[]	2026-03-05 17:09:47.058422
416e1f62-3919-467b-9ae7-725cd6e1fa0e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-05 17:10:49.745548
1f29730c-efb3-4399-937d-64774a58b9e4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 17:21:12.871103
597542c3-2465-466e-8d01-722f265640af	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-06 10:43:51.083004
078c7485-d315-4304-a442-05bd24bb484e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-06 10:47:45.895429
c7a12bec-ff57-49e7-845f-ce3a847e28c6	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	规则列表	{}	[]	2026-03-06 10:50:44.610708
ccf5365a-e524-4dc8-bdbb-c2d02e1afc88	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-06 11:11:26.10662
e724a81b-72c7-425c-a59f-afb3c9591b8f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-06 11:11:53.80504
a9096b05-b3fc-46c5-ba67-f53cf0c01841	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福欧飞」已删除	{}	[]	2026-03-06 11:12:37.397209
7b3ae632-f0a2-41d5-846f-1b37a0431236	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **真腾讯异业**\n• **喜马**	{}	[]	2026-03-05 15:29:54.784872
6ec7342a-ff6d-422d-877b-00f44db2300a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **真腾讯异业**\n• **喜马**	{}	[]	2026-03-05 15:30:31.252845
ace0f32d-067f-4eb9-9d8d-11426ba4ce8c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `1767597466118_152522.csv`	{}	[]	2026-03-05 15:31:28.597222
44e73011-a3f7-41e3-a910-3eac2a7ac6a8	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	删除xxx	{}	[]	2026-03-05 16:41:12.191881
b4e3e016-f126-4055-8f03-f64140f6f56f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **xxx**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:43:34.355097
dfbdb32a-afa5-4ff3-b68d-6bf8582e3658	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **xxx**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:45:23.628621
2f6c585b-d482-47a1-9f04-e78826707e97	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-05 16:46:27.395413
4ce3a585-33a8-4bd3-8248-e0b2ef081760	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 16:56:45.865541
73ea33ea-5f87-4ca4-b83d-3f8dfad862f9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 16:59:49.29663
cb917b9f-572d-488a-a20a-6a6dab0889f5	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **1767597466118_170019.xlsx:** 1870条\n- **ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx:** 1864条\n- **匹配成功:** 1856条\n- **异常记录:** 22条\n- **匹配率:** 99.2%\n\n**异常明细 (22条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104251231234638768479 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260122162512658451 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260112081844177428 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104250730101120956853 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260112204110375695 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231231337736997 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131046426087 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260107124023245524 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231234226418848 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131017217568 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260120182524246431 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260120154831859614 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231233717277112 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104251130171618989036 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260121232312235785 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260111131034425031 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260110211042376700 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260111131015059724 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104250730102122996149 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260122234015356232 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231234629088856 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131030607475 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |	{}	[]	2026-03-05 17:03:43.13454
edad7ce0-5be7-435e-9c3e-010a54137146	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 17:08:29.097438
d4471486-a0ca-470d-af3f-3b4820cbc909	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🎯 **开始创建新的对账规则**\n\n我会引导你完成以下4个步骤：\n\n1️⃣ 上传并分析文件 - 分析文件结构和列名\n\n2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）\n\n3️⃣ 配置规则参数 - 设置容差、订单号特征等\n\n4️⃣ 预览并保存 - 查看规则效果并保存\n\n请先上传需要对账的文件（文件1和文件2各一个 Excel/CSV 文件）。	{}	[]	2026-03-05 17:09:47.08333
7f5d0203-6388-4181-9908-09221c77f0ee	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	规则列表	{}	[]	2026-03-05 17:11:00.804067
e38687bf-0cd6-455b-b622-fed5531ddc03	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	已上传 2 个文件，请处理。	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_172119.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx", "size": 0}]	2026-03-05 17:22:36.019919
0cc2f201-b594-461c-86d5-1fd38d6e45ec	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-06 10:43:51.107776
4ce45105-ab7d-43aa-abc1-bd0a66e5b210	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:47:45.924474
2a0c2c4f-853a-44a0-9380-8e5adb742cb0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:50:44.638249
dcb407b7-1689-4172-bc14-0281ffc53c47	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 【西福商管】话费（欧飞）  官网.xlsx\n- 【西福商管】话费（欧飞）  合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据\n\n✅ 对账完成\n\n**对账概览**\n- **【西福商管】话费（欧飞）  官网_104542.xlsx:** 508条\n- **【西福商管】话费（欧飞）  合单_104543.xlsx:** 504条\n- **匹配成功:** 0条\n- **异常记录:** 1012条\n- **匹配率:** 0%\n\n**异常明细 (1012条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104260302093718667945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260228231428159849 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303172934595945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260305120849546264 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303114540229594 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030217342172965 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301171240138729 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030207223701836 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030420291944922 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217252694649 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030321464186558 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030218331756844 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260304180917679932 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030417113803887 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260305103845549035 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260302155726326794 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030515443350773 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301090038307113 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030317023515890 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217471700846 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n\n（共1012条，仅列前20条）	{}	[]	2026-03-06 11:11:26.135658
474c683d-7968-4d73-9128-8e4ed3bed8b9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 【西福商管】话费（欧飞）  官网.xlsx\n- 【西福商管】话费（欧飞）  合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据\n\n✅ 对账完成\n\n**对账概览**\n- **【西福商管】话费（欧飞）  官网_104542.xlsx:** 508条\n- **【西福商管】话费（欧飞）  合单_104543.xlsx:** 504条\n- **匹配成功:** 0条\n- **异常记录:** 1012条\n- **匹配率:** 0%\n\n**异常明细 (1012条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104260302093718667945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260228231428159849 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303172934595945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260305120849546264 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303114540229594 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030217342172965 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301171240138729 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030207223701836 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030420291944922 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217252694649 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030321464186558 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030218331756844 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260304180917679932 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030417113803887 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260305103845549035 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260302155726326794 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030515443350773 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301090038307113 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030317023515890 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217471700846 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n\n（共1012条，仅列前20条）	{}	[]	2026-03-06 11:11:53.83212
3db64833-3128-4a00-a9f6-cc5c8f32dee7	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-06 11:12:37.419652
2a8f0a5c-b0d9-4605-a50c-02af878b0753	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「喜马」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 15:29:54.806622
a1ec8e1c-7d2a-4c26-bccb-d5fef5d29f7d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「喜马」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 15:30:31.273892
3a45e014-6784-4542-af3f-b8177306dcc5	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **真腾讯异业**\n• **喜马**	{}	[]	2026-03-05 15:31:28.620028
a7cfbc82-f58d-40c1-864c-0e9eff60b677	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「xxx」已删除	{}	[]	2026-03-05 16:41:12.219694
59e63089-a81b-42a2-b98c-8852f21dfe75	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉金额取绝对值	{}	[]	2026-03-05 16:43:34.382129
ca93fd9e-3a92-49ae-ab90-374125432515	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:45:23.656805
22905b91-5396-4e48-912e-68c4a600a204	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	你好啊	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_164535.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_164535.xlsx", "size": 0}]	2026-03-05 16:46:31.341692
e2992a97-34a0-4128-ae2a-59ef53371f06	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 16:56:45.890621
e9ae83ad-9c60-4ae0-bd01-db67c6964e9b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 16:59:49.339361
95bcf1e9-0947-430e-9f24-739c1b551190	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已根据你的调整意见更新字段映射：\n\n  🚫 文件1 从 order_id 中移除列别名: 订单编号\n  🚫 文件2 从 order_id 中移除列别名: 订单号	{}	[]	2026-03-05 17:03:43.174426
5d2d85de-6dd0-4b08-b8ff-9791a4d0e4b7	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **1767597466118_170019.xlsx:** 1870条\n- **ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx:** 1864条\n- **匹配成功:** 1856条\n- **异常记录:** 22条\n- **匹配率:** 99.2%\n\n**异常明细 (22条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104251231234638768479 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260122162512658451 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260112081844177428 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104250730101120956853 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260112204110375695 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231231337736997 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131046426087 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260107124023245524 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231234226418848 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131017217568 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260120182524246431 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260120154831859614 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231233717277112 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104251130171618989036 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260121232312235785 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260111131034425031 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260110211042376700 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260111131015059724 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104250730102122996149 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260122234015356232 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231234629088856 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131030607475 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |	{}	[]	2026-03-05 17:08:29.130339
eb4fc3cf-d0a0-4eb6-bb5a-515bfd31d02c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，已退出对账流程。如果您需要其他帮助，随时告诉我。	{}	[]	2026-03-05 17:09:47.109724
fff05f29-2d2c-4d04-9562-caa0d2346107	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**\n• **测试**	{}	[]	2026-03-05 17:11:00.830491
698e44a7-199b-470f-a666-5ec96dded8e1	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **1767597466118_172119.xlsx:** 1870条\n- **ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx:** 1864条\n- **匹配成功:** 1856条\n- **异常记录:** 22条\n- **匹配率:** 99.2%\n\n**异常明细 (22条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104260112081844177428 | 1767597466118_172119.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx无此订单记录 |\n| 104251231231337736997 | ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx存在，1767597466118_172119.xlsx无此订单记录 |\n| 104260112204110375695 | 1767597466118_172119.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx无此订单记录 |\n| 104260122162512658451 | 1767597466118_172119.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx无此订单记录 |\n| 104260111131017217568 | 1767597466118_172119.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx无此订单记录 |\n| 104251231234629088856 | ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx存在，1767597466118_172119.xlsx无此订单记录 |\n| 104260111131046426087 | 1767597466118_172119.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx无此订单记录 |\n| 104251231234638768479 | ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx存在，1767597466118_172119.xlsx无此订单记录 |\n| 104251231233717277112 | ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx存在，1767597466118_172119.xlsx无此订单记录 |\n| 104260122234015356232 | 1767597466118_172119.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx无此订单记录 |\n| 104260110211042376700 | 1767597466118_172119.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx无此订单记录 |\n| 104260111131015059724 | 1767597466118_172119.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx无此订单记录 |\n| 104260120154831859614 | 1767597466118_172119.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx无此订单记录 |\n| 104260111131030607475 | 1767597466118_172119.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx无此订单记录 |\n| 104260107124023245524 | 1767597466118_172119.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx无此订单记录 |\n| 104250730101120956853 | ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx存在，1767597466118_172119.xlsx无此订单记录 |\n| 104260111131034425031 | 1767597466118_172119.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx无此订单记录 |\n| 104250730102122996149 | ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx存在，1767597466118_172119.xlsx无此订单记录 |\n| 104251231234226418848 | ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx存在，1767597466118_172119.xlsx无此订单记录 |\n| 104260120182524246431 | 1767597466118_172119.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx无此订单记录 |\n| 104260121232312235785 | 1767597466118_172119.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx无此订单记录 |\n| 104251130171618989036 | ads_finance_d_inc_channel_details_20260105152012277_0_172119.xlsx存在，1767597466118_172119.xlsx无此订单记录 |	{}	[]	2026-03-05 17:22:36.052029
a5399f56-a487-453a-b325-3ae9d35c8b43	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	规则列表	{}	[]	2026-03-06 10:44:03.119549
a99ea7bc-9eba-4c6d-afab-55a296cbe3a2	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福欧飞」已删除	{}	[]	2026-03-06 10:47:45.95148
2c7df3cd-47fd-4e4c-b64d-98433c2fcc57	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	规则列表	{}	[]	2026-03-06 10:57:06.576758
3c8da930-1803-41ec-aacb-0b4d0a58d7e5	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:11:26.179306
86b34c39-b5d5-490b-ac1a-5644ea7bed2c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:11:53.85971
044d1253-c0a6-489c-b58d-d812ddd2fdc8	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:12:37.44544
ac14b3e4-1939-4c6e-bc89-9c814efe45ec	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 未能解析修改，请更具体描述。\n\n> 增加订单号	{}	[]	2026-03-05 15:29:54.829269
07665601-47fe-4c28-8a00-4c27ebf6ea81	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-05 15:30:31.295684
910c0685-efa3-4886-8fcb-d7f50fe0feb1	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「喜马」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 15:31:28.643861
6b60b012-bacb-482c-9c71-d9d7fd10ca7a	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	编辑测试1	{}	[]	2026-03-05 16:41:17.014122
4fa4e226-0a22-4a72-b718-7153d64e3f20	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「xxx」已删除	{}	[]	2026-03-05 16:43:34.407437
49a34cfd-155c-47ce-aaf9-3c074d119e1a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  🚫 文件1 从 order_id 中移除列别名: sp订单号	{}	[]	2026-03-05 16:45:23.683858
484683a3-190b-4174-9cbf-b1bf43228f08	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 未能解析修改，请更具体描述。\n\n> 将sp订单号与sup订单号匹配	{}	[]	2026-03-05 16:46:31.365461
eaaebfe2-aa60-44ba-9ae1-dd5131521dbd	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_165634.xlsx`\n- `主营业务收入-上期2024_165634.xlsx`	{}	[]	2026-03-05 16:56:45.917039
03f5f237-e92c-4dd8-90f6-96ca69403f26	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx`	{}	[]	2026-03-05 16:59:49.379574
49f0b357-8693-4683-afa0-3950b9eb9a3e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 17:03:43.21279
d00e74f6-425e-48c6-810b-476734197b74	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 17:08:29.163194
eb451414-a005-41f9-ba18-a997c256f8ca	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 17:09:47.135665
6deafc47-9644-446a-a47c-58349908c4aa	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	编辑测试	{}	[]	2026-03-05 17:11:06.592811
22a2dc0c-7732-47c1-94b1-501e82184015	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ➕ 文件1 添加 订单时间	{}	[]	2026-03-05 17:22:36.096924
2628b015-b1d5-49c8-9f4c-3b16458d6d7a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:44:03.145886
8f9e2d82-1d86-44be-971f-d8c2c776433e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-06 10:47:45.975575
3125b680-d666-4e8d-9e31-41aaf49a4db7	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:57:06.611783
34f795da-397b-47e1-895d-8d1ee6eb1439	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福欧飞」已删除	{}	[]	2026-03-06 11:11:26.203295
376f71ac-cb14-4bb3-aa34-52f70484997e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福欧飞」已删除	{}	[]	2026-03-06 11:11:53.886457
f9886e56-ff55-4995-ba94-e580089223d6	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-06 11:12:37.470897
264345f7-6277-4598-90b0-d306a94f21e4	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	增加订单号	{}	[]	2026-03-05 15:30:00.653878
369ed9cf-991a-4079-928d-a47a2bb143cd	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	两个文件去掉金额保留2位小时	{}	[]	2026-03-05 15:30:45.309479
004705f6-189b-4ecb-bde7-370a97e207aa	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	去掉去订单号去除首尾空格	{}	[]	2026-03-05 15:31:42.950506
ac6d2337-5cfa-40c7-b88d-ef4a77acc9e9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试1」的编辑...	{}	[]	2026-03-05 16:41:17.039873
78ca9f7f-90d4-49c6-a50e-19dc62368f40	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	确认	{}	[]	2026-03-05 16:43:37.617612
81a36487-1938-4546-9d53-710cefbbf52f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-05 16:45:23.716687
ab8a9f8b-a15c-47ec-877c-06acef628279	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「xxx」已删除	{}	[]	2026-03-05 16:46:31.388206
ddb1bdce-5ffe-4543-8c9e-d38b412b2181	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:56:45.96297
d52477b5-43fd-4253-8f1f-ba4e5ead0c8f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_165634.xlsx`\n- `主营业务收入-上期2024_165634.xlsx`	{}	[]	2026-03-05 16:59:49.419321
50107fca-1c8e-44fd-a440-f40bc69aa7ae	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:03:43.25312
428347b9-673b-4d24-b136-77cbf8df9365	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:08:29.196143
e103901d-4de3-43e0-acaf-acd0b8dcfd33	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **1767597466118_170247.xlsx:** 1870条\n- **ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx:** 1864条\n- **匹配成功:** 1856条\n- **异常记录:** 22条\n- **匹配率:** 99.2%\n\n**异常明细 (22条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104251231234638768479 | ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx存在，1767597466118_170247.xlsx无此订单记录 |\n| 104260122162512658451 | 1767597466118_170247.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx无此订单记录 |\n| 104260112081844177428 | 1767597466118_170247.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx无此订单记录 |\n| 104250730101120956853 | ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx存在，1767597466118_170247.xlsx无此订单记录 |\n| 104260112204110375695 | 1767597466118_170247.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx无此订单记录 |\n| 104251231231337736997 | ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx存在，1767597466118_170247.xlsx无此订单记录 |\n| 104260111131046426087 | 1767597466118_170247.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx无此订单记录 |\n| 104260107124023245524 | 1767597466118_170247.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx无此订单记录 |\n| 104251231234226418848 | ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx存在，1767597466118_170247.xlsx无此订单记录 |\n| 104260111131017217568 | 1767597466118_170247.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx无此订单记录 |\n| 104260120182524246431 | 1767597466118_170247.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx无此订单记录 |\n| 104260120154831859614 | 1767597466118_170247.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx无此订单记录 |\n| 104251231233717277112 | ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx存在，1767597466118_170247.xlsx无此订单记录 |\n| 104251130171618989036 | ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx存在，1767597466118_170247.xlsx无此订单记录 |\n| 104260121232312235785 | 1767597466118_170247.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx无此订单记录 |\n| 104260111131034425031 | 1767597466118_170247.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx无此订单记录 |\n| 104260110211042376700 | 1767597466118_170247.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx无此订单记录 |\n| 104260111131015059724 | 1767597466118_170247.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx无此订单记录 |\n| 104250730102122996149 | ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx存在，1767597466118_170247.xlsx无此订单记录 |\n| 104260122234015356232 | 1767597466118_170247.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx无此订单记录 |\n| 104251231234629088856 | ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx存在，1767597466118_170247.xlsx无此订单记录 |\n| 104260111131030607475 | 1767597466118_170247.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx无此订单记录 |	{}	[]	2026-03-05 17:09:47.16244
a2b82f42-668a-4990-ac4e-fb0fcf3e4dc9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试」的编辑...	{}	[]	2026-03-05 17:11:06.619327
2e36aabc-51c5-463c-a9f0-509c9266e3f8	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-05 17:22:36.136554
0f39fcd8-5984-47e5-8378-ddbc363836e3	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	删除西福欧飞	{}	[]	2026-03-06 10:45:26.275827
0dc45fd4-c2a4-4ada-ab9b-4e2ff26850ac	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	确认	{}	[]	2026-03-06 10:47:54.812227
46a1a348-4946-4ef1-882e-6498e8024da8	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	规则列表	{}	[]	2026-03-06 11:09:00.322845
55e8fd00-472d-45db-ab83-5d5ada4c63d5	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ✏️ 文件2 修改 sp订单号	{}	[]	2026-03-06 11:11:26.22969
6897516e-2f7c-45bc-a7cd-e965b67d3015	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-06 11:11:53.910479
8e28a8d7-2aec-4e69-9763-06159cdce851	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	保存	{}	[]	2026-03-06 11:12:48.519674
3524da1b-bdbd-42e5-b078-d12aa5180be0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 15:30:00.677329
4046fdcf-16be-412e-abcf-e2b999914483	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 15:30:45.333827
7682155b-9584-464d-993a-ccee98c13c77	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 15:31:42.976082
910c864c-2423-4d32-90af-3264b7008762	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	去掉sp订单号为订单号	{}	[]	2026-03-05 16:41:38.014638
3a46074e-e051-4f02-b3dc-8d980e90299b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-05 16:43:37.641868
eeab1963-a39d-4bea-bc55-eebe1a81f6b3	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	已上传 2 个文件，请处理。	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_164535.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_164535.xlsx", "size": 0}]	2026-03-05 16:45:50.963447
ed5e68e7-bbfe-4ca8-9a4a-62e8eeedf7e7	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉金额保留2位小数	{}	[]	2026-03-05 16:46:31.412539
79f7f87a-7297-4733-9155-6c2646f0becd	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	已上传 2 个文件，请处理。	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_165657.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx", "size": 0}]	2026-03-05 16:57:12.886933
b8f297df-345f-4e31-b144-32e40de69af0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 16:59:49.45834
9771bdad-f978-43c0-94f4-8af0591b993e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx`	{}	[]	2026-03-05 17:03:43.292262
24e6877e-0e41-47e8-9bcd-51c70f75441e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx`	{}	[]	2026-03-05 17:08:29.228291
88993972-0831-4529-ab70-f3618f5aa469	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ❌ 文件1 删除 order_id 字段\n  ❌ 文件2 删除 order_id 字段	{}	[]	2026-03-05 17:09:47.187299
8d506dc3-8d6a-457d-a972-6adf1e4e9ed9	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	编辑测试	{}	[]	2026-03-05 17:13:12.02835
d6dc2744-1b20-44dd-a133-aa28f52001d4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：金额保留2位小数（两个文件）\n\n> 增加金额保留2位小数	{}	[]	2026-03-05 17:22:36.176994
bc3741dd-8462-4137-b83f-8630733c1641	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福欧飞」已删除	{}	[]	2026-03-06 10:45:26.304577
23800eff-6008-45a3-9f20-e9dd1c323a08	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留104开头的订单号	{}	[]	2026-03-06 10:47:54.834948
07c51540-be0f-4b49-8eaa-b6a76e0da356	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:09:00.350919
d879fadb-ea34-45fd-b6a2-bf456461e625	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-06 11:11:26.257921
a708605d-04ff-4f7b-b8e4-9e7acaf2c960	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:11:53.931498
05befd10-d9e9-4172-8c06-54e74e9e98bb	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「喜马」的编辑...	{}	[]	2026-03-06 11:12:48.549349
3d22108d-6609-449f-bc4e-60962e21a7a0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:30:00.702096
0037882f-d5e5-4544-8ae9-f82763fe4d5e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:30:45.358777
5b91c185-5371-4915-bfcf-30391ed56277	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:31:43.000708
78f6b488-2819-4f9b-a646-79ea5ee26712	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  🚫 文件1 从 order_id 中移除列别名: sp订单号	{}	[]	2026-03-05 16:41:38.040511
9cbb9898-1a12-49e7-a94e-c53b09c8009b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试1」的编辑...	{}	[]	2026-03-05 16:43:37.664676
566c4bb0-d8ba-42ec-a372-f1fa454bc27f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `ads_finance_d_inc_channel_details_20260105152012277_0_164535.xlsx`	{}	[]	2026-03-05 16:45:50.990706
6199b7e9-9a25-49f2-8caf-6f65692754a2	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-05 16:46:31.435701
b83d1ea4-1f08-469e-91b2-0379e16f46c1	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx`	{}	[]	2026-03-05 16:57:12.914737
869cf642-87a0-4444-9090-a99e72a1cf50	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-05 16:59:49.517595
278b8097-04eb-4302-abd7-b7711bfde979	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_165634.xlsx`\n- `主营业务收入-上期2024_165634.xlsx`	{}	[]	2026-03-05 17:03:43.324621
fe40213c-242d-415c-9c22-e5702f826163	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_165634.xlsx`\n- `主营业务收入-上期2024_165634.xlsx`	{}	[]	2026-03-05 17:08:29.25956
dc116216-6bd8-4fc9-9873-66f7be0d2a07	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	很高兴对账顺利完成！匹配率达到了99.2%，结果很不错。\n\n如果您需要查看详细的对账报告、导出结果，或者想调整规则以进一步提高匹配率，随时告诉我。	{}	[]	2026-03-05 17:09:47.212141
478d9ec5-d4ca-4c65-bdb1-e2594aefa5ae	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试」的编辑...\n\n✅ 已更新：\n\n  ❌ 文件1 删除 order_id 字段\n  ❌ 文件2 删除 order_id 字段\n\n✅ 已更新：\n\n  ➕ 文件1 添加 order_id: sp订单号\n  ➕ 文件2 添加 order_id: sup订单号\n\n✅ 字段映射已确认。\n\n✅ 规则配置已确认。\n\n正在保存...\n\n✅ 规则「测试」已更新！	{}	[]	2026-03-05 17:13:12.05288
f8d8e0e9-8361-4443-a281-285a66ca5bc4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-05 17:22:36.210799
6b3cc071-801d-41be-bb99-433c96211591	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	使用西福	{}	[]	2026-03-06 10:45:34.345437
de197a03-9f25-4b09-b644-d9d8f1657609	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	我的规则列表	{}	[]	2026-03-06 11:09:26.933592
e52fd655-608f-4243-861b-2e9df598fde1	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	不客气！很高兴能帮到你。😊\n\n对账结果显示匹配率高达 **99.85%**，只有10条异常记录，整体数据质量非常好。\n\n**主要异常类型：**\n1. **官网有但合单无**（7条）- 可能是订单未同步或状态不一致\n2. **金额差异**（3条）- 金额差异超出容差范围\n\n如果需要进一步分析这些异常订单，或者需要导出对账报告，随时告诉我！	{}	[]	2026-03-05 15:30:00.726611
e3554143-8752-45f9-bd54-9d64e6e09f14	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	不客气！很高兴能帮到你。😊\n\n对账结果显示匹配率高达 **99.85%**，只有10条异常记录，整体数据质量非常好。\n\n**主要异常类型：**\n1. **官网有但合单无**（7条）- 可能是订单未同步或状态不一致\n2. **金额差异**（3条）- 金额差异超出容差范围\n\n如果需要进一步分析这些异常订单，或者需要导出对账报告，随时告诉我！	{}	[]	2026-03-05 15:30:45.385437
e13dcbb1-3864-4d1b-8429-0e380c37bbdb	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	不客气！很高兴能帮到你。😊\n\n对账结果显示匹配率高达 **99.85%**，只有10条异常记录，整体数据质量非常好。\n\n**主要异常类型：**\n1. **官网有但合单无**（7条）- 可能是订单未同步或状态不一致\n2. **金额差异**（3条）- 金额差异超出容差范围\n\n如果需要进一步分析这些异常订单，或者需要导出对账报告，随时告诉我！	{}	[]	2026-03-05 15:31:43.026018
1490eb92-14a3-4349-9286-f955b2d07f91	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试1」的编辑...	{}	[]	2026-03-05 16:41:38.065853
87eea35b-7ce7-4bd2-be9d-4f1bea9a4f6a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **xxx**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:43:37.68833
05f8bd23-66d8-40bc-b7d1-5b1ff3c7abcb	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 16:45:51.013751
1f18192b-3a23-4ec0-b164-2275f5ee59b8	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ➕ 文件1 添加 order_id: sp订单号	{}	[]	2026-03-05 16:46:31.458299
b186b8f9-293d-4a30-864b-6310cdb5aa5e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 16:57:12.940481
04e31445-52b6-496a-bfcf-76dd9e62a443	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 16:59:49.560625
6c75f359-a7d7-471a-bd4a-353d35a86335	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 17:03:43.355436
59e0271b-67f2-4466-ba46-0c40682c3900	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 17:08:29.292554
986bc53f-0dbc-46ac-bac8-875a64959809	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则确认完毕，正在执行对账...	{}	[]	2026-03-05 17:09:47.238621
33c8d07b-9409-49ab-aec2-19e07df9fb6e	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	规则列表	{}	[]	2026-03-05 17:13:34.055098
c5c56676-3644-46ff-9002-6a2782ec3848	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 17:22:36.237566
963c3095-5b31-4b3b-a375-d9fb0a197af4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-06 10:45:34.37115
8f63c9c1-2df4-48c5-8d1c-0ef163af8802	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 【西福商管】话费（欧飞）  官网.xlsx\n- 【西福商管】话费（欧飞）  合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-06 10:47:54.857923
d2a1b2d0-905d-4149-8f51-868ce22656ea	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:09:26.962911
214f5658-5a64-46de-99ac-dca2a5d5e7ed	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:11:26.283371
687157b5-8ac7-4e96-90ad-5617ee6bb34f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-06 11:11:53.955584
e5e16b59-e990-4450-a0bf-77bb1f1f67be	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	❌ 启动对账任务失败：规则不存在: 西福欧飞	{}	[]	2026-03-06 11:12:48.583509
93d93c1b-c7e5-401c-a5f6-6e0a198e7a56	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_152455.xlsx`\n- `主营业务收入-上期2024_152455.xlsx`	{}	[]	2026-03-05 15:30:00.755572
e2120296-ac90-437e-ac4a-109d34c2f78c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_152455.xlsx`\n- `主营业务收入-上期2024_152455.xlsx`	{}	[]	2026-03-05 15:30:45.409989
76d92677-2884-4a73-9145-016200b7250b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_152455.xlsx`\n- `主营业务收入-上期2024_152455.xlsx`	{}	[]	2026-03-05 15:31:43.052154
56fe3c6f-b758-4bd3-bdcb-916e5a318c43	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **xxx**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:41:38.089962
ffc0dd72-ff3b-494f-8028-ff16e16c0b6b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「xxx」已删除	{}	[]	2026-03-05 16:43:37.710237
10158cd0-7fb2-4a4d-939d-643a8b411870	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	我的规则列表	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_164535.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_164535.xlsx", "size": 0}]	2026-03-05 16:46:17.503561
4a5219b7-ba04-4415-88f6-2c2de2fa1977	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:46:31.480796
e4b357ab-6f09-44d2-b08e-0eba1625d6ec	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	退出吧，先不对账了	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_165657.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx", "size": 0}]	2026-03-05 16:57:20.277457
c4d8ffff-1580-4819-aead-2216383c958c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-05 16:59:49.624594
562f2a69-316e-4e35-a855-e3e88c8ef545	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-05 17:03:43.387523
359507f4-f448-47c1-8a42-4b877301c009	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-05 17:08:29.326154
2337bc69-29ad-458d-815c-58bac38f4420	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ➕ 文件1 添加 order_id: sp订单号\n  ➕ 文件2 添加 order_id: sup订单号	{}	[]	2026-03-05 17:09:47.265702
371c43d0-ae7a-40cb-8e91-cfccbbbec806	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**\n• **测试**	{}	[]	2026-03-05 17:13:34.078365
a4434c37-a517-4d9c-ad73-981b4fbfcd4c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-05 17:22:36.268105
052f43f6-1909-45e9-ad65-7a2048bb09ad	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	已上传 2 个文件，请处理。	{}	[{"name": null, "path": "/uploads/2026/3/6/【西福商管】话费（欧飞）  官网_104542.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/6/【西福商管】话费（欧飞）  合单_104543.xlsx", "size": 0}]	2026-03-06 10:46:38.559143
ab5e02de-9519-40a0-bd0c-b5dc133da9ec	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-06 10:47:54.887032
9dab32c5-0653-4093-8df9-761a39074972	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	西福欧飞	{}	[]	2026-03-06 11:09:43.527739
566b650f-eb41-4bf5-8c07-40e7144c8a59	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-06 11:11:26.306996
fc7b2de9-7b86-47e7-b662-3aab150e7d4d	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	添加金额保留1位小数	{}	[]	2026-03-06 11:12:24.922874
8bf4728b-cb1e-4eb2-adfe-19d350f9f1d7	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:12:48.623781
9e76062a-addd-41c7-85ed-9843a8de2eb7	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 官网.xlsx\n- 合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:30:00.779858
bc29437c-14a5-4254-86a6-03f88dd5246b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 官网.xlsx\n- 合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:30:45.433403
1b485a9e-cd08-4853-847d-9de9ccd0f23b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 官网.xlsx\n- 合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:31:43.076206
56bf0854-cc3d-4e94-bd7e-7daf2b1a9304	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「xxx」已删除	{}	[]	2026-03-05 16:41:38.115262
97b9de21-44dd-47f6-b6ba-47cd2e3cba40	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	调整	{}	[]	2026-03-05 16:43:44.996411
2f8ab269-70fa-4f5b-8ca0-b1db28eaf638	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 未能解析修改，请更具体描述。\n\n> 将sp订单号与sup订单号匹配	{}	[]	2026-03-05 16:46:17.526819
eb2dc3e8-3cab-4141-a5c1-b095fab9c873	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「测试1」已删除	{}	[]	2026-03-05 16:46:31.501305
a8705400-1078-4d5d-bcb3-fc669c8a4605	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，已退出对账流程。如果您需要其他帮助，随时告诉我。	{}	[]	2026-03-05 16:57:20.303556
0a7af2fb-f50d-4be6-b621-393d2f2add11	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	媳妇	{}	[]	2026-03-05 16:59:55.178238
f5635c10-5db9-4f75-9dfa-8783eecada7a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:03:43.417475
364b947a-147a-4c17-af4b-5ca4cbec029e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加配置：订单号去掉前单引号，并截取前21位\n\n> 订单号去掉前单引号，并截取前21位\n\n当前配置：\n  1. 📁 1767597466118.xlsx 订单号去掉前单引号，并截取前21位\n  2. 📁 ads_finance_d_inc_channel_details_20260105152012277_0.xlsx 订单号去掉前单引号，并截取前21位	{}	[]	2026-03-05 17:08:29.358486
390be30c-bf90-42ee-a576-16b6ab30f173	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **1767597466118_170019.xlsx:** 1870条\n- **ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx:** 1864条\n- **匹配成功:** 1856条\n- **异常记录:** 22条\n- **匹配率:** 99.2%\n\n**异常明细 (22条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104251231234638768479 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260122162512658451 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260112081844177428 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104250730101120956853 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260112204110375695 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231231337736997 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131046426087 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260107124023245524 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231234226418848 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131017217568 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260120182524246431 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260120154831859614 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231233717277112 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104251130171618989036 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260121232312235785 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260111131034425031 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260110211042376700 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260111131015059724 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104250730102122996149 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260122234015356232 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231234629088856 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131030607475 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |	{}	[]	2026-03-05 17:09:47.289962
d459b0f1-1991-4155-ac05-3b822c239974	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	删除测试	{}	[]	2026-03-05 17:13:44.800074
d0bb8b73-1a70-4f32-81c6-35fa6344c91f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-05 17:22:36.301401
02cb2671-1d95-4eb0-be56-f30a8814c3f2	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留104开头的订单号	{}	[]	2026-03-06 10:46:38.584608
1ddf45e6-1b8e-4d1b-b162-e558cc8b7f69	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-06 10:47:54.91255
dc230ca3-387f-4566-a46e-6f0dad519d25	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福欧飞」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-06 11:09:43.563441
c2a96252-c652-4c12-9ff9-5bbcc3d2e3bf	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	把sp订单号改成sup订单号	{}	[]	2026-03-06 11:11:49.414725
ee49c8a2-c9e5-4658-876f-467804bcc473	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「喜马」的编辑...	{}	[]	2026-03-06 11:12:24.949593
102abe2a-ccd1-4156-85cd-836736e4a030	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「喜马」已更新！	{}	[]	2026-03-06 11:12:48.659002
da749a28-a25e-4fb1-81fa-74d0afcdeb04	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 官网_152552.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:30:00.804618
cc686896-d8d2-4aac-97a4-90f71dbc0e7d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 官网_152552.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:30:45.454854
fcf70f9b-82b6-40b2-979f-5cfe234045c4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 官网_152552.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:31:43.101691
14ea1a17-8e67-4ef9-8867-55890005a485	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	将sp订单号与sup订单号匹配	{}	[]	2026-03-05 16:42:05.517559
263bc383-52b9-4fa5-8f89-7fd09aa43de6	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，返回规则配置。	{}	[]	2026-03-05 16:43:45.020628
4e52f508-7a97-465f-bfed-f391fcea3159	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「xxx」已删除	{}	[]	2026-03-05 16:46:17.547836
e14508ea-011b-4e73-b433-cbb9a0232d01	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 16:46:31.52579
dedbebde-0c24-4bb9-8b93-85f78f853eb4	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	我的规则列表	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_165657.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx", "size": 0}]	2026-03-05 16:57:27.402617
f08fd73d-d6a0-46bc-a40c-131eac0689a3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 16:59:55.249857
dc94e2ce-ba1c-45ef-90f9-ab5e57acfb28	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ❌ 文件1 删除 order_id 字段\n  ❌ 文件2 删除 order_id 字段	{}	[]	2026-03-05 17:03:43.4452
3161a28f-0aef-40a3-859a-0a549f330e37	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:08:29.391544
8d7db253-4399-4e45-964d-e3af7f025fa1	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:09:47.316504
9b98ea81-c3bd-49b7-a4d5-00139b472af9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 正在删除规则「测试」...\n\n✅ 规则「测试」已删除！\n\n📋 **当前规则列表**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 17:13:44.824117
0526df7e-22b7-4b5c-8497-92bc958a8f6d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 17:22:36.331016
11976e74-3d60-41c7-ab14-e6c30408ca4d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 【西福商管】话费（欧飞）  官网.xlsx\n- 【西福商管】话费（欧飞）  合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-06 10:46:38.609217
47d13796-5531-46af-87fe-ea56529da79d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留103开头的订单号	{}	[]	2026-03-06 10:47:54.935872
4125a82d-37b9-4103-a741-4c2ce074ee80	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	已上传 2 个文件，请处理。	{}	[{"name": null, "path": "/uploads/2026/3/6/【西福商管】话费（欧飞）  官网_110956.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/6/【西福商管】话费（欧飞）  合单_110956.xlsx", "size": 0}]	2026-03-06 11:10:48.014365
448e4963-ecb9-482e-b872-2868f94ddfa5	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「喜马」的编辑...	{}	[]	2026-03-06 11:11:49.446978
8b3f3b8f-9149-4a50-8d06-e76b213073e8	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	❌ 启动对账任务失败：规则不存在: 西福欧飞	{}	[]	2026-03-06 11:12:24.977923
b8b7e54f-47e1-4173-ad74-2d784557a96d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留104开头的订单号	{}	[]	2026-03-06 11:12:48.688977
24f263a0-e7d6-4fd2-9c06-7fadf51b0d40	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 1767597466118.csv\n- ads_finance_d_inc_channel_details_20260105152012277_0.csv\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:30:00.832621
570f8de9-15a0-4ea0-9ba1-a5a78031a931	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 1767597466118.csv\n- ads_finance_d_inc_channel_details_20260105152012277_0.csv\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:30:45.477271
2ec09e89-a5fe-4110-ba9e-f065102a9f63	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉去订单号去除首尾空格	{}	[]	2026-03-05 15:31:43.12631
8b3f5740-ead8-4a74-9a77-2df8836303f5	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 未能解析修改，请更具体描述。\n\n> 将sp订单号与sup订单号匹配	{}	[]	2026-03-05 16:42:05.542244
653b3b99-d0a5-4550-be71-8ca6faeb5ade	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试1」的编辑...	{}	[]	2026-03-05 16:43:45.045312
68ef9cc2-b1b4-4e17-a5e6-f89422c06188	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉金额保留2位小数	{}	[]	2026-03-05 16:46:17.572412
ae9dd627-a400-477d-a5d2-9ae818468d3c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，返回规则配置。	{}	[]	2026-03-05 16:46:31.548884
b273465b-217e-4cb1-acc0-b93863248ff8	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:57:27.4293
6b5fe1b3-05ee-4cc8-a592-236ed87f1ed0	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	已上传 2 个文件，请处理。	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_170019.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx", "size": 0}]	2026-03-05 17:01:55.660817
0a582f39-3643-4d40-8ead-11a5d06679fa	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	很高兴对账顺利完成！匹配率达到了99.2%，结果很不错。\n\n如果您需要查看详细的对账报告、导出结果，或者想调整规则以进一步提高匹配率，随时告诉我。	{}	[]	2026-03-05 17:03:43.471667
848d9d61-853c-4049-aa57-b1e8d4e71169	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ❌ 文件1 删除 order_id 字段\n  ❌ 文件2 删除 order_id 字段	{}	[]	2026-03-05 17:08:29.425963
20e9714b-8384-4334-b591-bc10f3201fc9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-05 17:09:47.341758
7c7a47c6-68f0-4577-9a30-b8e42fddec46	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	规则列表	{}	[]	2026-03-05 17:13:58.763445
26c9c47c-d635-419e-98df-b27967410682	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  🚫 文件1 移除列别名: 订单时间	{}	[]	2026-03-05 17:22:36.363638
c2d58840-779d-4fec-aede-a7896ac47d79	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-06 10:46:38.632857
3bcdbc35-b4b6-417e-97bc-9fef9069b757	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:47:54.959069
242f666d-3547-43c4-841c-55c9d5421abe	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	❌ 启动对账任务失败：规则不存在: 西福欧飞	{}	[]	2026-03-06 11:10:48.049864
9b2bb470-eb04-45b3-b6f1-dc96b01460a1	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	❌ 启动对账任务失败：规则不存在: 西福欧飞	{}	[]	2026-03-06 11:11:49.478478
a5f9a8f7-4bf8-4634-ac8c-392b0611a226	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:12:25.009626
40d738b7-0cfa-4c51-8a75-345b49e6d365	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-06 11:12:48.720188
e30ed885-4e1c-498b-9ee4-d6bf2fdb741f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **官网_152735.xlsx:** 6489条\n- **合单_152735.xlsx:** 6479条\n- **匹配成功:** 6479条\n- **异常记录:** 10条\n- **匹配率:** 99.85%\n\n**异常明细 (10条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| L26012422340153819700 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012116163721519400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260124070644706639 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012123094296319400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260121215420799296 | 官网_152735.xlsx金额 53.099999999999994 vs 合单_152735.xlsx金额 70.8，差额 17.70 超出容差 0.1 |\n| L26011211340303919100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012119191879219100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260123134427719478 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012218172999819300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012014530342619300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |	{}	[]	2026-03-05 15:30:00.856642
3dace1f5-2296-41c9-930d-1867ff49fcef	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **官网_152735.xlsx:** 6489条\n- **合单_152735.xlsx:** 6479条\n- **匹配成功:** 6479条\n- **异常记录:** 10条\n- **匹配率:** 99.85%\n\n**异常明细 (10条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| L26012422340153819700 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012116163721519400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260124070644706639 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012123094296319400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260121215420799296 | 官网_152735.xlsx金额 53.099999999999994 vs 合单_152735.xlsx金额 70.8，差额 17.70 超出容差 0.1 |\n| L26011211340303919100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012119191879219100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260123134427719478 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012218172999819300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012014530342619300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |	{}	[]	2026-03-05 15:30:45.500619
77150d31-eb6d-4792-bd2d-8d75f0561129	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 1767597466118.csv\n- ads_finance_d_inc_channel_details_20260105152012277_0.csv\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:31:43.149008
0c57ff09-34ce-4685-908b-9f05c0298d9c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试1」的编辑...	{}	[]	2026-03-05 16:42:05.56584
55d978ea-452e-487e-a506-7a74dba5a6a2	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **xxx**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:43:45.069789
fdd65ef8-699b-4674-aaee-e771242216f4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-05 16:46:17.598082
94483411-77bb-4d2a-9825-4074e3e3b8c1	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉金额取绝对值	{}	[]	2026-03-05 16:46:31.573559
2e434999-db26-488a-9f65-23975e336a5d	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	编辑西福	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_165657.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx", "size": 0}]	2026-03-05 16:57:34.39684
703dd3fd-02d1-4199-b85a-1b5ea16155c0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-05 17:01:55.702104
7e87c987-4870-44f1-b1ef-a57626f00fc5	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-05 17:03:43.500547
57572370-ff6c-4c64-82ff-767be769accf	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	很高兴对账顺利完成！匹配率达到了99.2%，结果很不错。\n\n如果您需要查看详细的对账报告、导出结果，或者想调整规则以进一步提高匹配率，随时告诉我。	{}	[]	2026-03-05 17:08:29.45584
e9bdb722-f594-4f7a-96a0-3f0ac035c1ed	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：新规则_待确认\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:09:47.367919
581a46ea-52e2-403c-9eed-83941399dfda	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 17:13:58.78878
94e6ce3b-57c6-47ac-b929-5a565f0b7c61	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：仅保留104开头的订单号（两个文件）\n\n> 增加订单号以104开头	{}	[]	2026-03-05 17:22:36.388
e0784008-5f1a-432d-9984-586fb3ac41e2	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-06 10:46:38.655585
3dd8d2a1-1d9a-4926-853f-c1f6cded3b06	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉进保留104开头的订单	{}	[]	2026-03-06 10:47:54.98515
3855f83b-e43d-4394-ae00-0528ee7eeb07	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:10:48.081749
26b33f7e-379c-4369-ada2-846d9e48059b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 11:11:49.507731
8101361c-8af3-46f9-bab8-9dfb71540ad7	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留104开头的订单号	{}	[]	2026-03-06 11:12:25.037994
97a37990-7e06-4b62-ac33-2381360e44d1	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留103开头的订单号	{}	[]	2026-03-06 11:12:48.750022
64611c26-c1c2-4a6c-bf80-5d3d643b29e7	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 合单_152700.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:30:01.016928
d35b6928-ba87-49b1-b1f7-5256bd35a707	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 合单_152700.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:30:45.524657
1ab6ab0f-287b-4436-8262-0887b18dcdb0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **官网_152735.xlsx:** 6489条\n- **合单_152735.xlsx:** 6479条\n- **匹配成功:** 6479条\n- **异常记录:** 10条\n- **匹配率:** 99.85%\n\n**异常明细 (10条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| L26012422340153819700 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012116163721519400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260124070644706639 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012123094296319400 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260121215420799296 | 官网_152735.xlsx金额 53.099999999999994 vs 合单_152735.xlsx金额 70.8，差额 17.70 超出容差 0.1 |\n| L26011211340303919100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012119191879219100 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| 104260123134427719478 | 官网_152735.xlsx金额 18.0 vs 合单_152735.xlsx金额 24.0，差额 6.00 超出容差 0.1 |\n| L26012218172999819300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |\n| L26012014530342619300 | 官网_152735.xlsx存在，合单_152735.xlsx无此订单记录 |	{}	[]	2026-03-05 15:31:43.168681
eac67e06-f066-4647-983f-2d13656e9639	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **xxx**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:42:05.590969
d25f8791-0258-4c19-8022-cfd3a1834411	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「xxx」已删除	{}	[]	2026-03-05 16:43:45.092937
4b2d483b-1680-45df-a80a-b8ee655e457d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ➕ 文件1 添加 order_id: sp订单号	{}	[]	2026-03-05 16:46:17.619723
6f0a569c-dee0-4250-bf53-f860a1ba1c23	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 16:46:31.596489
ae74a733-f4d5-4872-9617-d9756435f581	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 16:57:34.422068
7cbe1fec-f444-4f2c-9786-715c62625a4a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，已退出对账流程。如果您需要其他帮助，随时告诉我。	{}	[]	2026-03-05 17:01:55.770342
cb2412a9-2eaa-40c5-8347-1c28e5071343	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	去掉发生+	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_170247.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx", "size": 0}]	2026-03-05 17:07:16.31513
6260080e-73b9-4f4e-82da-5d1ca79ee8d2	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-05 17:08:29.485972
d1aa75b9-931d-4526-b472-77c2866a0aaf	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 17:09:47.395956
3d5924af-cded-4bca-9eff-cc9c8bb9358e	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	编辑西福	{}	[]	2026-03-05 17:14:07.903487
f9c600b9-a492-45e1-bcbd-a21b80665943	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：金额取绝对值\n\n> 增加金额取绝对值	{}	[]	2026-03-05 17:22:36.416968
7593aa18-967e-4a00-9250-967f37558f1a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留103开头的订单号	{}	[]	2026-03-06 10:46:38.678757
f6e2b59e-f317-48d8-a1e9-2e58ab6f8fbb	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉订单号以104开头	{}	[]	2026-03-06 10:47:55.015334
84871df7-9566-4bc9-a361-b3d8324af1e1	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留104开头的订单号	{}	[]	2026-03-06 11:10:48.113749
218415b6-3d79-4d9f-a818-481e00e611af	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留104开头的订单号	{}	[]	2026-03-06 11:11:49.53537
30792883-49fe-4025-970b-29f4e1ddebc8	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-06 11:12:25.064869
3cff1eeb-81b1-49a2-a156-5d2439c4ac2d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福欧飞」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-06 11:12:48.776056
0106e8e7-d32d-4a15-9209-f0fa218dd513	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `1767597466118_152522.csv`	{}	[]	2026-03-05 15:30:01.050487
b4e9653b-1b36-4e08-998f-019db91a92ff	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `1767597466118_152522.csv`	{}	[]	2026-03-05 15:30:45.547104
da7d13c8-ba31-47e5-8278-b8ff6ba3664a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 检测到文件 合单_152700.xlsx 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单号</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">日期</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">状态</th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240101</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-01</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">已完成</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240102</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-02</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2000.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">待确认</td>\n    </tr>\n    <tr>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">20240103</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">2024-01-03</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">1500.00</td>\n      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">处理中</td>\n    </tr>\n  </tbody>\n</table>	{}	[]	2026-03-05 15:31:43.190994
641d1610-8e0e-413a-997f-e58058dc46cb	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「xxx」已删除	{}	[]	2026-03-05 16:42:05.615083
40605951-392a-4318-a4db-9b75ffb7b712	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	去掉订单号去除收尾空格	{}	[]	2026-03-05 16:43:58.450228
3b02fbf3-765b-472a-a12d-11d26acd64d4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:46:17.643289
4d8be5bc-512d-4731-87cf-f4e3a305f7db	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_164510.xlsx`\n- `主营业务收入-上期2024_164511.xlsx`	{}	[]	2026-03-05 16:46:31.620123
2f688d3e-43e2-4b79-86f9-34b8283f3fa6	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	去掉sp订单号	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_165657.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx", "size": 0}]	2026-03-05 16:57:48.719396
ccf9d41c-6c6a-4e80-850c-ec780bd1edd4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ➕ 文件1 添加 order_id: sp订单号\n  ➕ 文件2 添加 order_id: sup订单号	{}	[]	2026-03-05 17:01:55.923637
ab991884-0be7-4240-ad75-22c6fc31bffd	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已根据你的调整意见更新字段映射：\n\n  🚫 文件2 从 amount 中移除列别名: 发生+	{}	[]	2026-03-05 17:07:16.34913
9cb9cca1-405e-4c24-86c5-57f2efc4df06	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	相同订单号按金额累加合并	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_170247.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx", "size": 0}]	2026-03-05 17:08:42.839508
8f445917-4cf2-4236-9282-a801c36880db	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_165634.xlsx`\n- `主营业务收入-上期2024_165634.xlsx`	{}	[]	2026-03-05 17:09:47.42228
802e668a-e086-47db-90f9-f8ff7a378595	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 17:14:07.927972
bb68d503-7587-4efc-8948-76594cb21f31	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-05 17:22:36.441035
925916ae-5c43-4c55-bbaf-ac1582af2472	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **西福欧飞**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:46:38.70124
159d72f1-1b62-4960-8548-375fbf1f0432	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **真腾讯异业**\n• **喜马**	{}	[]	2026-03-05 15:30:01.080659
2ce52cda-bce1-4121-bebe-043c7e0c68fd	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **真腾讯异业**\n• **喜马**	{}	[]	2026-03-05 15:30:45.568793
5ad263be-e813-4cd9-aedc-36e11a6b717d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `1767597466118_152522.csv`	{}	[]	2026-03-05 15:31:43.214411
20de4c81-367c-4389-8df9-e90c5c984330	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	将sp订单号与sup订单号匹配	{}	[]	2026-03-05 16:42:18.256931
7b5ee16e-8eff-4fea-be4b-8733c4b19ef9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉订单号去除收尾空格	{}	[]	2026-03-05 16:43:58.4755
e86a976a-7a95-4ddf-a418-429bb3f56ce7	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「测试1」已删除	{}	[]	2026-03-05 16:46:17.66832
ff9aeeb4-6bc3-454f-8bfd-73d92be4abe2	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：订单号去除首尾空格\n\n> 去掉首尾空格	{}	[]	2026-03-05 16:46:31.642365
9a99953d-3c9c-4240-b799-062fe6e93ac5	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，已退出对账流程。如果您需要其他帮助，随时告诉我。	{}	[]	2026-03-05 16:57:48.747391
41c7dadb-fa4c-4488-9155-0604d2c9bb9b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-05 17:01:55.965151
de8e0b77-cd0d-4f18-ae4b-24f11f2bd740	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-05 17:07:16.505312
06b50742-cb49-436d-93ff-f4acac05ea6b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-05 17:08:42.873602
fa7fef1b-7b12-4947-9855-636d63e9a302	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-05 17:09:47.44932
7b9a235d-aa15-40c1-b69c-e02906cf1c06	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	规则列表	{}	[]	2026-03-05 17:18:21.826101
c346f414-7ef3-45f2-873b-3f47af8a340e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:22:36.47269
b058d46e-1a12-4f6d-8263-37e254ddcb5a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉进保留104开头的订单	{}	[]	2026-03-06 10:46:38.724534
c9cf92aa-885d-4308-a68b-6a86b75a347e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **【西福商管】话费（欧飞）  官网_104542.xlsx:** 508条\n- **【西福商管】话费（欧飞）  合单_104543.xlsx:** 504条\n- **匹配成功:** 0条\n- **异常记录:** 1012条\n- **匹配率:** 0%\n\n**异常明细 (1012条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104260302093718667945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260228231428159849 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303172934595945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260305120849546264 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303114540229594 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030217342172965 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301171240138729 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030207223701836 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030420291944922 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217252694649 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030321464186558 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030218331756844 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260304180917679932 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030417113803887 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260305103845549035 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260302155726326794 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030515443350773 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301090038307113 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030317023515890 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217471700846 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n\n（共1012条，仅列前20条）	{}	[]	2026-03-06 10:47:55.03926
67b67122-4f44-4e42-a71a-6595f573d81e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-06 11:10:48.146836
7740f68e-4a26-4473-a339-1652d0fde6bc	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-06 11:11:49.563008
21ee0c23-8f1b-4cdc-a13d-f1ad7bf961ad	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留103开头的订单号	{}	[]	2026-03-06 11:12:25.089904
4dd65cab-6736-4403-87b2-b6c2f46b5729	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉订单号以104开头	{}	[]	2026-03-06 11:12:48.811423
8eaa10f9-2505-41b1-b16f-d998c3f48f6e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「喜马」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 15:30:01.133943
e7b3627a-b2a0-4f14-9ed1-a71af6c234a2	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「喜马」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 15:30:45.59196
311e808e-8db2-4914-a425-226daeb79279	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **真腾讯异业**\n• **喜马**	{}	[]	2026-03-05 15:31:43.236455
5ac7dff0-a4b4-4440-8f51-e3c7d8f63445	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 未能解析修改，请更具体描述。\n\n> 将sp订单号与sup订单号匹配	{}	[]	2026-03-05 16:42:18.281413
c3dd933e-08bf-4e46-9fc1-a882e609db9f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试1」的编辑...	{}	[]	2026-03-05 16:43:58.501611
cc23ee11-2063-4f84-9154-9ecf1eda1a85	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 16:46:17.691351
94c4b6a1-5ad2-4577-b7e5-793ea6d8dae6	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉订单号去除首尾空格	{}	[]	2026-03-05 16:46:31.664716
0d508960-f151-4b7c-a5f3-d3ea33e3aa4d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:57:48.774821
4c84b0e1-7915-478a-a657-f1400fc0515e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 17:01:56.001708
4c3ee43f-cf6c-474e-be5b-98d2aa6f0b07	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🎯 **开始创建新的对账规则**\n\n我会引导你完成以下4个步骤：\n\n1️⃣ 上传并分析文件 - 分析文件结构和列名\n\n2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）\n\n3️⃣ 配置规则参数 - 设置容差、订单号特征等\n\n4️⃣ 预览并保存 - 查看规则效果并保存\n\n请先上传需要对账的文件（文件1和文件2各一个 Excel/CSV 文件）。	{}	[]	2026-03-05 17:07:16.536764
e0753651-0584-4a8b-acd3-2b8f41e383c6	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🎯 **开始创建新的对账规则**\n\n我会引导你完成以下4个步骤：\n\n1️⃣ 上传并分析文件 - 分析文件结构和列名\n\n2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）\n\n3️⃣ 配置规则参数 - 设置容差、订单号特征等\n\n4️⃣ 预览并保存 - 查看规则效果并保存\n\n请先上传需要对账的文件（文件1和文件2各一个 Excel/CSV 文件）。	{}	[]	2026-03-05 17:08:42.906318
20cfb975-c54c-4217-9ec4-026118ae88d4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:09:47.477771
4f84f8fd-eae6-40eb-8ce8-3ec77454f728	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-05 17:18:21.851765
8f0c0684-467c-4027-a757-4be3210f1b3e	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	你太棒了	{}	[]	2026-03-05 17:23:05.028097
3ec46ca3-2695-4af2-a47f-0a2ae7f95094	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉订单号以104开头	{}	[]	2026-03-06 10:46:38.74833
da44434a-ea96-4f6e-b3c0-5400d3a058b8	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-06 10:47:55.064379
801ceb29-f4e0-4d8d-a950-3df4b19d44f8	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留103开头的订单号	{}	[]	2026-03-06 11:10:48.178164
801b12d2-c79e-4102-9117-2ff62e0be65f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留103开头的订单号	{}	[]	2026-03-06 11:11:49.590779
761a450d-0659-4b9a-bde1-6158eda97da2	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福欧飞」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-06 11:12:25.120718
064e60a1-44f0-4dfa-837b-9ba4b1297833	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已删除	{}	[]	2026-03-06 11:12:48.841348
e503b3e2-85d0-4a36-b80a-9a6c584ace34	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	⚠️ 未能解析修改，请更具体描述。\n\n> 增加订单号	{}	[]	2026-03-05 15:30:01.175993
a00e5123-52c4-411d-b4e2-7de320d4a178	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 两个文件去掉金额保留2位小时	{}	[]	2026-03-05 15:30:45.611453
3a2731e1-25d7-4b21-9d4d-64f85c73758b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「喜马」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 15:31:43.257592
f8e81f14-c49a-4889-9931-048d3307f4c7	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试1」的编辑...	{}	[]	2026-03-05 16:42:18.307337
f180b49a-e569-4264-bb21-9c6a688666dd	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **xxx**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:43:58.52658
3a52cad5-7cc9-4845-a82b-9d572034135a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，返回规则配置。	{}	[]	2026-03-05 16:46:17.713921
6f811206-b8b4-4995-a2a5-535c8e88e8c2	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「测试1」已更新！	{}	[]	2026-03-05 16:46:31.695294
aa966be6-b163-4cc3-bd90-57dd406cdeab	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 16:57:48.800909
3f15c926-be77-487f-afe8-d13c7203d9ed	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **1767597466118_170019.xlsx:** 1870条\n- **ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx:** 1864条\n- **匹配成功:** 1856条\n- **异常记录:** 22条\n- **匹配率:** 99.2%\n\n**异常明细 (22条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104251231234638768479 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260122162512658451 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260112081844177428 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104250730101120956853 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260112204110375695 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231231337736997 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131046426087 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260107124023245524 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231234226418848 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131017217568 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260120182524246431 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260120154831859614 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231233717277112 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104251130171618989036 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260121232312235785 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260111131034425031 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260110211042376700 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260111131015059724 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104250730102122996149 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260122234015356232 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231234629088856 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131030607475 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |	{}	[]	2026-03-05 17:01:56.036725
23dbd0c2-6395-4452-b9a0-2081212407f7	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，已退出对账流程。如果您需要其他帮助，随时告诉我。	{}	[]	2026-03-05 17:07:16.572594
e17d7b5f-9457-46a3-8714-ba84fd6efc20	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，已退出对账流程。如果您需要其他帮助，随时告诉我。	{}	[]	2026-03-05 17:08:42.937563
0e413d73-bb7b-452c-8b6f-9ea0e15eb64e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已更新！	{}	[]	2026-03-05 17:09:47.550092
ba2df8e2-6ccd-4ffd-826f-123d460d4c79	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	编辑西福	{}	[]	2026-03-05 17:18:27.751278
b6df6f07-2459-4dd3-945a-c46bfb818f2b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	谢谢夸奖！😊 很高兴能帮到你。如果还有其他对账需求，随时告诉我！	{}	[]	2026-03-05 17:23:05.055781
7d6f8ca4-2c76-46b4-bb1e-49c3aec74f66	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **【西福商管】话费（欧飞）  官网_104542.xlsx:** 508条\n- **【西福商管】话费（欧飞）  合单_104543.xlsx:** 504条\n- **匹配成功:** 0条\n- **异常记录:** 1012条\n- **匹配率:** 0%\n\n**异常明细 (1012条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104260302093718667945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260228231428159849 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303172934595945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260305120849546264 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303114540229594 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030217342172965 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301171240138729 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030207223701836 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030420291944922 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217252694649 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030321464186558 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030218331756844 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260304180917679932 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030417113803887 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260305103845549035 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260302155726326794 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030515443350773 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301090038307113 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030317023515890 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217471700846 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n\n（共1012条，仅列前20条）	{}	[]	2026-03-06 10:46:38.773468
7eff5abb-2f40-46a4-a131-6dc64004d497	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-06 10:47:55.088157
9e6c40ac-5bfb-4f36-80af-750df5a676e0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福欧飞」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-06 11:10:48.209312
55581a1a-3390-4237-9ab8-cc0c36c563f3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福欧飞」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-06 11:11:49.621485
57281900-593d-4c96-bbe3-1882712739c2	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉订单号以104开头	{}	[]	2026-03-06 11:12:25.147875
c2f729d3-74db-4c45-b2ed-67dc3aff1734	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 【西福商管】话费（欧飞）  官网.xlsx\n- 【西福商管】话费（欧飞）  合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-06 11:12:48.882331
4d9fb5ff-4aad-45dc-9ad1-f09b437e34d0	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	添加订单号	{}	[]	2026-03-05 15:30:10.302709
a2ec7066-6cc7-4b0c-ba33-31fee45d293e	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	去掉订单号去除收尾空格	{}	[]	2026-03-05 15:31:04.534527
62343917-45aa-459e-9fc5-cc44a9f8f1fa	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	确认	{}	[]	2026-03-05 15:31:46.18007
96719633-5816-41af-9197-5ef79b1d482e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **xxx**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:42:18.331889
cd966046-77b3-4962-ae6b-c2825bd36b9e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「xxx」已删除	{}	[]	2026-03-05 16:43:58.550554
8ea42fde-891c-4fc6-9164-8f853765108c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉金额取绝对值	{}	[]	2026-03-05 16:46:17.738649
db9cc2e7-6b91-4d33-b67b-ea52835997f3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试1」的编辑...	{}	[]	2026-03-05 16:46:31.72029
540f18ce-6a1e-4b75-9863-b98ffe6ec767	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 16:57:48.827793
b9bfabac-7bc2-4393-b064-8dd2077d52f8	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 17:01:56.115961
fabf0cdc-318a-4e24-931c-089850b1d02a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ➕ 文件1 添加 order_id: sp订单号\n  ➕ 文件2 添加 order_id: sup订单号	{}	[]	2026-03-05 17:07:16.610897
6b17075f-3771-477b-b301-78c35025f952	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加配置：相同订单号按金额累加合并\n\n> 相同订单号按金额累加合并\n\n当前配置：\n  1. 📁 1767597466118.xlsx 订单号去掉前单引号，并截取前21位\n  2. 📁 ads_finance_d_inc_channel_details_20260105152012277_0.xlsx 订单号去掉前单引号，并截取前21位\n  3. 📁 1767597466118.xlsx 相同订单号按金额累加合并\n  4. 📁 ads_finance_d_inc_channel_details_20260105152012277_0.xlsx 相同订单号按金额累加合并	{}	[]	2026-03-05 17:08:42.969615
fafb1bd9-9fc7-429a-abfa-c08dd9f9a94e	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	保存	{}	[{"name": null, "path": "/uploads/2026/3/5/1767597466118_170247.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/5/ads_finance_d_inc_channel_details_20260105152012277_0_170248.xlsx", "size": 0}]	2026-03-05 17:10:44.770715
eb0f848e-6197-4408-bf51-113cfde6a161	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 17:18:27.779499
5230edfe-0428-4887-9e02-93da7ad9b36d	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	规则列表	{}	[]	2026-03-05 17:23:11.195521
32a0e233-f41f-4146-b005-bf6947caf29c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-06 10:46:38.798346
acc60827-a17d-4852-abe9-38889dc12165	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-06 10:47:55.112309
32d2b42c-dc58-4b6d-b964-ba441583e949	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉订单号以104开头	{}	[]	2026-03-06 11:10:48.242034
a9f1f0a2-754e-4202-ad1c-cebea1356c1e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉订单号以104开头	{}	[]	2026-03-06 11:11:49.646471
983acc2f-8622-459a-b199-76888080ccc1	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已删除	{}	[]	2026-03-06 11:12:25.173387
1668eb56-0a35-43e8-bbf1-2fbf819f41ed	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-06 11:12:48.949378
b0d74c26-a5c5-4cb8-bd1e-710c1dc97c31	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 15:30:10.328821
9a8dd422-ee4d-4c8c-93f7-4c8492e5ac71	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 15:31:04.55892
126afd79-2c10-49ba-9273-be4a897013db	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 15:31:46.20331
e82261b1-e67d-49f7-b07c-ccdc054ddb75	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「xxx」已删除	{}	[]	2026-03-05 16:42:18.358174
8e13f9f8-61b3-4a8c-aaba-2f6f73080bc9	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	确认	{}	[]	2026-03-05 16:44:13.699701
11a2afc5-deb2-47cb-8dea-f427f58426ad	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 16:46:17.760912
2276dfe3-c43c-4d19-88b0-bd8bb9da4985	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `ads_finance_d_inc_channel_details_20260105152012277_0_164535.xlsx`	{}	[]	2026-03-05 16:46:31.744585
c4014698-fcc6-4274-8a27-c0f3486d735c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx`	{}	[]	2026-03-05 16:57:48.852691
ab7bc644-4f53-48a5-999a-1d174d40bdf9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:01:56.187668
399ee75d-8f20-4f41-a3c9-eaa39419098e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-05 17:07:16.645887
f79c6b7e-d11d-4faf-9d66-61d1e3dca262	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ➕ 文件1 添加 order_id: sp订单号\n  ➕ 文件2 添加 order_id: sup订单号	{}	[]	2026-03-05 17:08:42.999921
8968d40a-5deb-4a7d-b180-506c586eb485	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-05 17:10:44.793872
41470963-0aa1-4585-8134-40d809fe5510	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	去掉订单时间	{}	[]	2026-03-05 17:18:43.142664
43cd86e9-a8e9-46f0-92ed-8241ac8f150c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-05 17:23:11.229814
d5030238-796b-482e-ac3d-643bf26e51e2	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-06 10:46:38.82142
c186879b-c0cf-4e4a-b639-b7ac096f0ba7	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:47:55.134546
2914a1db-8a2c-40e8-bd1a-8d3dab45bcc3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已删除	{}	[]	2026-03-06 11:10:48.275074
0b0f365b-e92d-4100-808b-c0d2bcf1963f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福」已删除	{}	[]	2026-03-06 11:11:49.675466
8a5db310-324e-45da-b98f-82d3f637444c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 【西福商管】话费（欧飞）  官网.xlsx\n- 【西福商管】话费（欧飞）  合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-06 11:12:25.206308
7867aaa2-ce6b-4281-844e-2a6806a9d3c3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：仅保留104开头的订单号（两个文件）\n\n> 订单号以104开头	{}	[]	2026-03-06 11:12:48.994319
2114bfac-0864-4b9e-8e84-f536e9534454	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:30:10.358502
1982f020-0cfd-422e-b87a-d37c82c0cfad	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:31:04.583518
70c93689-730c-4b9f-ab3a-420d6f65beac	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:31:46.226094
82eed7f5-fce1-47da-afd0-2b3bcfe5b8ff	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	增加sp订单号与sup订单号匹配	{}	[]	2026-03-05 16:42:32.418033
490b0271-6b14-4cd6-8637-6a77812b227a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-05 16:44:13.724061
645d2e27-76a9-44e9-9991-23ef34327468	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_164510.xlsx`\n- `主营业务收入-上期2024_164511.xlsx`	{}	[]	2026-03-05 16:46:17.784071
468f7e43-2f7e-4206-a112-86c9ec26a33c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉订单号去除收尾空格	{}	[]	2026-03-05 16:46:31.767809
4b343a80-d6f3-48d8-a55a-c7a1b8310fa3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_165634.xlsx`\n- `主营业务收入-上期2024_165634.xlsx`	{}	[]	2026-03-05 16:57:48.88045
32eda41c-be05-4914-9520-3d26c8eac09a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `ads_finance_d_inc_channel_details_20260105152012277_0_165657.xlsx`	{}	[]	2026-03-05 17:01:56.241053
ede169d0-52f1-4d1a-8e0d-b283ee67241c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 17:07:16.680344
95c66c89-ec02-40e9-a6d8-483f6cfce2f4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-05 17:08:43.033115
6ed9605a-833e-4915-a7c1-8cec6da2b12a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🎯 **开始创建新的对账规则**\n\n我会引导你完成以下4个步骤：\n\n1️⃣ 上传并分析文件 - 分析文件结构和列名\n\n2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）\n\n3️⃣ 配置规则参数 - 设置容差、订单号特征等\n\n4️⃣ 预览并保存 - 查看规则效果并保存\n\n请先上传需要对账的文件（文件1和文件2各一个 Excel/CSV 文件）。	{}	[]	2026-03-05 17:10:44.815635
80e6c9d2-0bcc-4251-a6a5-11d87ac6a23f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 17:18:43.167075
d7691178-ee8a-4ff2-b22b-fe8a7a311ab7	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	我的规则列表	{}	[]	2026-03-06 10:40:33.66631
8c7b3d22-877b-4710-8294-84b644ada5a9	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则配置已确认。	{}	[]	2026-03-06 10:46:38.843207
acf5bedf-0071-4b83-b67c-1ad3a474622c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福欧飞」已删除	{}	[]	2026-03-06 10:47:55.157262
60c61c74-f605-495d-89d9-8a9273fac9da	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 【西福商管】话费（欧飞）  官网.xlsx\n- 【西福商管】话费（欧飞）  合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-06 11:10:48.305948
335d2cc0-6742-465f-96da-31a27fdea9ea	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 【西福商管】话费（欧飞）  官网.xlsx\n- 【西福商管】话费（欧飞）  合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-06 11:11:49.758967
85e170cb-ee24-48a3-9dad-b49d8f2f473e	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-06 11:12:25.237055
819f8bbb-6b74-412d-ba96-3a474bef66f2	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉进保留104开头的订单	{}	[]	2026-03-06 11:12:49.022222
5846dce6-fce0-4f8f-a7d7-45d068330b39	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	不客气！很高兴能帮到你。😊\n\n对账结果显示匹配率高达 **99.85%**，只有10条异常记录，整体数据质量非常好。\n\n**主要异常类型：**\n1. **官网有但合单无**（7条）- 可能是订单未同步或状态不一致\n2. **金额差异**（3条）- 金额差异超出容差范围\n\n如果需要进一步分析这些异常订单，或者需要导出对账报告，随时告诉我！	{}	[]	2026-03-05 15:30:10.391719
8baa032a-0d5a-482d-be8f-93db280a5940	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	不客气！很高兴能帮到你。😊\n\n对账结果显示匹配率高达 **99.85%**，只有10条异常记录，整体数据质量非常好。\n\n**主要异常类型：**\n1. **官网有但合单无**（7条）- 可能是订单未同步或状态不一致\n2. **金额差异**（3条）- 金额差异超出容差范围\n\n如果需要进一步分析这些异常订单，或者需要导出对账报告，随时告诉我！	{}	[]	2026-03-05 15:31:04.606604
65e93c4e-2c68-4581-bb46-7f17a2392d07	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	不客气！很高兴能帮到你。😊\n\n对账结果显示匹配率高达 **99.85%**，只有10条异常记录，整体数据质量非常好。\n\n**主要异常类型：**\n1. **官网有但合单无**（7条）- 可能是订单未同步或状态不一致\n2. **金额差异**（3条）- 金额差异超出容差范围\n\n如果需要进一步分析这些异常订单，或者需要导出对账报告，随时告诉我！	{}	[]	2026-03-05 15:31:46.249553
416eb508-d5df-4cd8-97a3-31083f00a615	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ➕ 文件1 添加 order_id: sp订单号	{}	[]	2026-03-05 16:42:32.442968
deef046c-1641-42e0-b5f8-08ef165d91b6	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试1」的编辑...	{}	[]	2026-03-05 16:44:13.747866
43afdf91-29fa-449b-97dd-9264edc2ea9f	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：订单号去除首尾空格\n\n> 去掉首尾空格	{}	[]	2026-03-05 16:46:17.805962
cef3b9cf-23f9-47f2-abcc-38939469aeea	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-05 16:46:31.789567
e267beae-ee1d-44eb-a380-97e312c89152	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 16:57:48.906005
37f1f04d-af7d-453a-9841-489e12cac800	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「西福」匹配\n\n西福规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">订单时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">销售额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sp订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_165634.xlsx`\n- `主营业务收入-上期2024_165634.xlsx`	{}	[]	2026-03-05 17:01:56.284025
432e24a8-dfce-4b07-b942-cb7e33897490	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **1767597466118_170019.xlsx:** 1870条\n- **ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx:** 1864条\n- **匹配成功:** 1856条\n- **异常记录:** 22条\n- **匹配率:** 99.2%\n\n**异常明细 (22条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104251231234638768479 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260122162512658451 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260112081844177428 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104250730101120956853 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260112204110375695 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231231337736997 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131046426087 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260107124023245524 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231234226418848 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131017217568 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260120182524246431 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260120154831859614 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231233717277112 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104251130171618989036 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260121232312235785 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260111131034425031 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260110211042376700 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260111131015059724 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104250730102122996149 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260122234015356232 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231234629088856 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131030607475 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |	{}	[]	2026-03-05 17:07:16.714567
7261ee9c-e080-4882-b7f4-4feef8a1ed69	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 17:08:43.064766
3a7797b2-1172-4ece-8db0-11aed4f2898a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，已退出对账流程。如果您需要其他帮助，随时告诉我。	{}	[]	2026-03-05 17:10:44.839054
d6c4c979-3f7d-4077-8a8f-5068af8f7cae	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  🚫 文件1 移除列别名: 订单时间	{}	[]	2026-03-05 17:18:43.190936
85fa3138-bb84-40c9-8be4-543ad5f45a25	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:40:33.701986
b505dc00-9e82-4859-a247-32dadb9ace6a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福欧飞**\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-06 10:46:38.867802
50e1f929-8314-49fb-9bf0-7505fdc24cfd	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-06 10:47:55.181561
7d5433b4-8e0a-4272-9f5e-6fcd6aeb1fe4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-06 11:10:48.339195
a7089935-0470-45a1-9076-29ab6fbb7207	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-06 11:11:49.78661
70f50700-d039-4a87-809f-5c2742764106	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：仅保留104开头的订单号（两个文件）\n\n> 订单号以104开头	{}	[]	2026-03-06 11:12:25.26531
843b98ae-c474-430d-aaf4-28c77ea46fdd	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **【西福商管】话费（欧飞）  官网_104542.xlsx:** 508条\n- **【西福商管】话费（欧飞）  合单_104543.xlsx:** 504条\n- **匹配成功:** 0条\n- **异常记录:** 1012条\n- **匹配率:** 0%\n\n**异常明细 (1012条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104260302093718667945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260228231428159849 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303172934595945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260305120849546264 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303114540229594 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030217342172965 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301171240138729 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030207223701836 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030420291944922 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217252694649 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030321464186558 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030218331756844 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260304180917679932 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030417113803887 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260305103845549035 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260302155726326794 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030515443350773 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301090038307113 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030317023515890 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217471700846 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n\n（共1012条，仅列前20条）	{}	[]	2026-03-06 11:12:49.050059
c63ce2b3-5c15-4061-8936-91c3463645a4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_152455.xlsx`\n- `主营业务收入-上期2024_152455.xlsx`	{}	[]	2026-03-05 15:30:10.41981
55c8722d-a153-4bfe-9895-75a1f7b0bdcc	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_152455.xlsx`\n- `主营业务收入-上期2024_152455.xlsx`	{}	[]	2026-03-05 15:31:04.633132
78fe9057-b9d0-4ac6-bdaf-2a94bd4af72d	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	### ❌ 上传文件列名未能与「喜马」匹配\n\n喜马规则要求文件列名如下\n\n#### 文件1列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">支付时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">应结算平台金额</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">第三方订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 文件2列名要求\n<table class="text-sm min-w-max">\n  <thead>\n    <tr class="bg-gray-50">\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">完成时间</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">发生-</th>\n      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">sup订单号</th>\n    </tr>\n  </thead>\n</table>\n\n#### 未匹配文件：\n- `主营业务收入-本期2025_152455.xlsx`\n- `主营业务收入-上期2024_152455.xlsx`	{}	[]	2026-03-05 15:31:46.280149
eddb769e-28d5-4730-b0d2-0c42f2e815ed	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「测试1」的编辑...	{}	[]	2026-03-05 16:42:32.467409
4408c08d-d599-4164-83cc-56183a7640c3	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **xxx**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:44:13.770543
080c6746-4ff6-4c3c-82c8-e528582771c6	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 去掉订单号去除首尾空格	{}	[]	2026-03-05 16:46:17.828905
0163da8b-8411-4253-ad19-247fae94b611	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 16:46:31.81022
3fa97b60-3745-422c-9c9a-871d5e5d8357	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 主营业务收入-本期2025.xlsx\n- 主营业务收入-上期2024.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 16:57:48.929621
e7c36e58-f1a7-4761-b0d4-037ca113567c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-05 17:01:56.329978
6aac8719-a4c5-4dc6-97cc-aeb0cb9013c4	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 17:07:16.755715
c8c726e3-e21b-41dd-aa55-7e71a84bd1bd	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **1767597466118_170019.xlsx:** 1870条\n- **ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx:** 1864条\n- **匹配成功:** 1856条\n- **异常记录:** 22条\n- **匹配率:** 99.2%\n\n**异常明细 (22条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104251231234638768479 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260122162512658451 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260112081844177428 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104250730101120956853 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260112204110375695 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231231337736997 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131046426087 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260107124023245524 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231234226418848 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131017217568 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260120182524246431 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260120154831859614 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231233717277112 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104251130171618989036 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260121232312235785 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260111131034425031 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260110211042376700 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104260111131015059724 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104250730102122996149 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260122234015356232 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |\n| 104251231234629088856 | ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx存在，1767597466118_170019.xlsx无此订单记录 |\n| 104260111131030607475 | 1767597466118_170019.xlsx存在，ads_finance_d_inc_channel_details_20260105152012277_0_170020.xlsx无此订单记录 |	{}	[]	2026-03-05 17:08:43.097432
d1eb1342-40a9-47a5-9225-73196a966474	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	请输入规则名称，将为您保存为个人规则。	{}	[]	2026-03-05 17:10:44.861309
56e54b5b-f87f-4c82-8ed9-509806018d02	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **腾讯异业**\n• **喜马**	{}	[]	2026-03-05 17:18:43.217055
50189d6c-8aa9-4514-8a29-fc2dde497e67	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	编辑西福	{}	[]	2026-03-06 10:40:44.575702
93bdad7d-e845-449a-9aa0-1519fc8d5258	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「西福欧飞」已删除	{}	[]	2026-03-06 10:46:38.941579
d37481fb-63e8-48f7-b1db-a5492afbde1e	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	保存	{}	[]	2026-03-06 10:47:59.736863
40c5d679-ee85-410e-81bc-069d327fb103	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：仅保留104开头的订单号（两个文件）\n\n> 订单号以104开头	{}	[]	2026-03-06 11:10:48.374678
6b2fe4d5-956e-4a35-b2aa-940af898c709	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：仅保留104开头的订单号（两个文件）\n\n> 订单号以104开头	{}	[]	2026-03-06 11:11:49.811425
5e7b4823-6946-4150-9137-ce96cf60616c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉进保留104开头的订单	{}	[]	2026-03-06 11:12:25.288479
e45ee482-832e-4e6c-b03b-17c74d619a24	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	❌ 未找到规则「西福欧飞」，请检查规则名称是否正确。	{}	[]	2026-03-06 11:12:49.078008
4a231372-c187-42a0-b12d-e48b07c8354c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 官网.xlsx\n- 合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:30:10.444185
2258c6d3-2a19-4402-b891-0c126c312e39	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 官网.xlsx\n- 合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:31:04.658687
e0ac1560-67c5-44bb-b5ab-5fab4cbce793	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：喜马\n- 官网.xlsx\n- 合单.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 15:31:46.303591
e5ac119a-946e-45d9-8254-bdf8a118c667	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **xxx**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:42:32.49085
07ce493f-8b70-467b-ada7-430a6cb4357c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「xxx」已删除	{}	[]	2026-03-05 16:44:13.793267
c276591b-5a28-45b7-975b-5ef2fbc23aa0	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 规则「测试1」已更新！	{}	[]	2026-03-05 16:46:17.86473
897789cd-7f84-405b-bd01-3200c30337ab	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **测试1**\n• **xxx**\n• **腾讯异业**\n• **西福**\n• **喜马**	{}	[]	2026-03-05 16:46:31.831976
40eb34eb-5984-4abc-94ed-2a810af603fe	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ❌ 文件1 删除 order_id 字段\n  ❌ 文件2 删除 order_id 字段	{}	[]	2026-03-05 16:57:48.953838
2892a213-6ae1-41cf-a7c8-8b1898760b33	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-05 17:01:56.366617
d925f9f9-6e28-4a7a-a709-8c6e4b758051	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🚀 对账任务已启动\n\n- 规则：西福\n- 1767597466118.xlsx\n- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx\n\n⏳ 正在执行对账，预计需要 10-60 秒\n\n进度：开始加载数据	{}	[]	2026-03-05 17:07:16.803609
d2f2bc19-9af2-4344-b60b-12c1df46c0fe	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	好的，将使用规则「西福」进行对账。\n\n✨ 请上传对账文件（文件1和文件2各一个）	{}	[]	2026-03-05 17:08:43.129364
a7d433f0-f016-4b03-9a08-7dcb3967ebb7	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已更新：\n\n  ➕ 文件1 添加 order_id: sp订单号\n  ➕ 文件2 添加 order_id: sup订单号	{}	[]	2026-03-05 17:10:44.883505
7afd2219-385d-4a3d-bfe4-fe7c2997a850	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	添加订单时间与完成时间匹配	{}	[]	2026-03-05 17:19:05.607001
ce2d88a5-cffe-4203-80fa-2f4c91221111	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📝 正在加载规则「西福」的编辑...	{}	[]	2026-03-06 10:40:44.601437
321e2955-d880-4033-9b8a-4401c480110b	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 字段映射已确认。	{}	[]	2026-03-06 10:46:38.968404
e5c9dd6d-4bc2-4bd4-a7ab-f7a3fba550ca	d64aadc1-818f-4643-8267-b8bfc48cbf25	user	规则列表	{}	[]	2026-03-05 15:24:20.945855
d8bc8796-e3d5-4ea5-ab85-e95d32642145	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	📋 **我的对账规则列表**\n\n• **西福**\n• **真腾讯异业**\n• **喜马**	{}	[]	2026-03-05 15:24:20.997336
7478226a-4d34-4495-a770-f26d4453d157	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	🗑️ 已删除匹配的配置\n\n> 删除仅保留104开头的订单号	{}	[]	2026-03-06 10:47:59.760139
50d1e764-37b3-4734-adf4-97c711616a6c	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉进保留104开头的订单	{}	[]	2026-03-06 11:10:48.40769
74b4bf3e-e55e-4b31-acb1-8bc7932162f8	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 已添加：财务数据：仅保留104开头的订单号\n\n> 去掉进保留104开头的订单	{}	[]	2026-03-06 11:11:49.839503
42ef7593-51c3-4ae8-b6cd-6e241d57643a	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	✅ 对账完成\n\n**对账概览**\n- **【西福商管】话费（欧飞）  官网_104542.xlsx:** 508条\n- **【西福商管】话费（欧飞）  合单_104543.xlsx:** 504条\n- **匹配成功:** 0条\n- **异常记录:** 1012条\n- **匹配率:** 0%\n\n**异常明细 (1012条)**\n\n| 异常订单号 | 异常原因 |\n|-----------|----------|\n| 104260302093718667945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260228231428159849 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303172934595945 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260305120849546264 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260303114540229594 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030217342172965 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301171240138729 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030207223701836 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030420291944922 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217252694649 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030321464186558 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030218331756844 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260304180917679932 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030417113803887 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260305103845549035 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 104260302155726326794 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030515443350773 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 104260301090038307113 | 【西福商管】话费（欧飞）  合单_104543.xlsx存在，【西福商管】话费（欧飞）  官网_104542.xlsx无此订单记录 |\n| 10426030317023515890 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n| 10426030217471700846 | 【西福商管】话费（欧飞）  官网_104542.xlsx存在，【西福商管】话费（欧飞）  合单_104543.xlsx无此订单记录 |\n\n（共1012条，仅列前20条）	{}	[]	2026-03-06 11:12:25.313951
f0e6d872-a3bd-4765-a35e-28e9471bf4c5	d64aadc1-818f-4643-8267-b8bfc48cbf25	assistant	正在保存...	{}	[]	2026-03-06 11:12:49.103235
\.


--
-- Data for Name: reconciliation_rules; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.reconciliation_rules (id, name, description, created_by, department_id, company_id, visibility, shared_with_users, rule_template, version, use_count, last_used_at, tags, status, approved_by, approved_at, created_at, updated_at, field_mapping_hash) FROM stdin;
3a6650f8-3c0c-49b5-a124-1ff6c87c8b46	测试认证规则	更新后的描述	3b593fbd-d0cd-48b8-99f1-fd9274f4059d	00000000-0000-0000-0000-000000000002	00000000-0000-0000-0000-000000000001	company	{}	{"version": "1.0", "description": "测试认证规则", "data_sources": {"finance": {}, "business": {}}}	1.0	0	\N	{测试,认证}	archived	\N	\N	2026-02-12 17:08:15.339339+08	2026-02-12 17:08:15.526847+08	\N
1679ef06-df15-437b-9dc3-e5721f7f2db8	西福商管欧飞	西福商管欧飞	00000000-0000-0000-0000-000000000003	00000000-0000-0000-0000-000000000002	00000000-0000-0000-0000-000000000001	private	{}	{"version": "1.0", "tolerance": {"date_format": "%Y-%m-%d", "amount_diff_max": 0.1}, "description": "西福商管欧飞", "data_sources": {"finance": {"field_roles": {"date": "完成时间", "amount": "发生-", "order_id": ["sup订单号"]}, "file_pattern": ["【西福商管】话费（欧飞）  合单_*.xlsx", "【西福商管】话费（欧飞）  合单_*.xlsb", "【西福商管】话费（欧飞）  合单_*.csv", "【西福商管】话费（欧飞）  合单_*.xls", "【西福商管】话费（欧飞）  合单_*.xlsm"]}, "business": {"field_roles": {"date": "订单时间", "amount": "销售额", "order_id": ["sp订单号"]}, "file_pattern": ["【西福商管】话费（欧飞）  官网_*.csv", "【西福商管】话费（欧飞）  官网_*.xlsb", "【西福商管】话费（欧飞）  官网_*.xlsm", "【西福商管】话费（欧飞）  官网_*.xls", "【西福商管】话费（欧飞）  官网_*.xlsx"]}}, "key_field_role": "order_id", "rule_config_text": "去掉订单号前单引号，并截取订单号前21位\\n相同的订单号按金额累加合并\\n仅保留104开头的订单号", "custom_validations": [{"name": "missing_in_business", "issue_type": "missing_in_business", "display_name": "业务缺失检测", "condition_expr": "fin_exists and not biz_exists", "detail_template": "{fin_file}存在，{biz_file}无此订单记录"}, {"name": "missing_in_finance", "issue_type": "missing_in_finance", "display_name": "财务缺失检测", "condition_expr": "biz_exists and not fin_exists", "detail_template": "{biz_file}存在，{fin_file}无此订单记录"}, {"name": "amount_mismatch", "issue_type": "amount_mismatch", "display_name": "金额差异检测", "condition_expr": "biz_exists and fin_exists and biz.get('amount') is not None and fin.get('amount') is not None and abs(float(biz.get('amount', 0)) - float(fin.get('amount', 0))) > amount_diff_max", "detail_template": "{biz_file}金额 {biz[amount]} vs {fin_file}金额 {fin[amount]}，差额 {amount_diff_formatted} 超出容差 {amount_diff_max}"}], "field_mapping_text": "业务: order_id->sp订单号, amount->销售额, date->订单时间\\n财务: order_id->sup订单号, amount->发生-, date->完成时间", "data_cleaning_rules": {"global": {"global_transforms": [{"keep": "first", "subset": ["order_id"], "operation": "drop_duplicates", "description": "全局去重"}]}, "finance": {"row_filters": [{"condition": "str(row.get('order_id', '')).startswith('104')", "description": "仅保留104开头的订单号"}], "aggregations": [{"group_by": "order_id", "agg_fields": {"date": "first", "amount": "sum"}, "description": "相同订单号按金额累加合并"}], "field_transforms": [{"field": "amount", "operation": "abs", "description": "金额取绝对值"}, {"field": "amount", "decimals": 2, "operation": "round", "description": "金额保留2位小数"}, {"field": "order_id", "operation": "strip", "description": "订单号去除首尾空格"}, {"field": "order_id", "transform": "str(row.get('order_id', '')).lstrip(\\"'\\")[:21] if pd.notna(row.get('order_id', '')) else row.get('order_id', '')", "description": "订单号先去单引号再截取前21位"}], "global_transforms": [{"subset": ["order_id", "amount"], "operation": "drop_na", "description": "删除关键字段为空的记录"}]}, "business": {"row_filters": [], "aggregations": [{"group_by": "order_id", "agg_fields": {"date": "first", "amount": "sum"}, "description": "相同订单号按金额累加合并"}], "field_transforms": [{"field": "amount", "decimals": 2, "operation": "round", "description": "金额保留2位小数"}, {"field": "order_id", "operation": "strip", "description": "订单号去除首尾空格"}, {"field": "order_id", "transform": "str(row.get('order_id', '')).lstrip(\\"'\\")[:21] if pd.notna(row.get('order_id', '')) else row.get('order_id', '')", "description": "订单号先去单引号再截取前21位"}], "global_transforms": [{"subset": ["order_id"], "operation": "drop_na", "description": "删除订单号为空的记录"}]}}}	1.0	0	\N	{}	active	\N	\N	2026-03-06 11:08:41.625126+08	2026-03-06 11:08:41.625126+08	7fe0d171d468f2fd9c8c04eb3e84a033
f4a64307-b136-4fc8-9e48-2d63219d9073	喜马	喜马	00000000-0000-0000-0000-000000000003	00000000-0000-0000-0000-000000000002	00000000-0000-0000-0000-000000000001	private	{}	{"version": "1.0", "tolerance": {"date_format": "%Y-%m-%d", "amount_diff_max": 0.1}, "description": "喜马", "data_sources": {"finance": {"field_roles": {"date": "完成时间", "amount": ["发生-"], "order_id": "sup订单号"}, "file_pattern": ["合单_*.xlsx", "合单_*.csv", "合单_*.xls", "合单_*.xlsb", "合单_*.xlsm"]}, "business": {"field_roles": {"date": "支付时间", "amount": ["应结算平台金额"], "order_id": ["第三方订单号"]}, "file_pattern": ["官网_*.xlsb", "官网_*.xlsm", "官网_*.xlsx", "官网_*.csv", "官网_*.xls"]}}, "key_field_role": "order_id", "rule_config_text": "官网_*.xlsb：订单号去掉前面的单引号，并截取前21位\\n官网_*.xlsb：相同订单号按金额累加合并\\n合单_*.xlsx：订单号去掉前面的单引号，并截取前21位\\n合单_*.xlsx：相同订单号按金额累加合并\\n添加金额保留1位小数", "custom_validations": [{"name": "missing_in_business", "issue_type": "missing_in_business", "condition_expr": "fin_exists and not biz_exists", "detail_template": "{fin_file}存在，{biz_file}无此订单记录"}, {"name": "missing_in_finance", "issue_type": "missing_in_finance", "condition_expr": "biz_exists and not fin_exists", "detail_template": "{biz_file}存在，{fin_file}无此订单记录"}, {"name": "amount_mismatch", "issue_type": "amount_mismatch", "condition_expr": "biz_exists and fin_exists and biz.get('amount') is not None and fin.get('amount') is not None and abs(float(biz.get('amount', 0)) - float(fin.get('amount', 0))) > amount_diff_max", "detail_template": "{biz_file}金额 {biz[amount]} vs {fin_file}金额 {fin[amount]}，差额 {amount_diff_formatted} 超出容差 {amount_diff_max}"}], "field_mapping_text": "业务: date->支付时间, amount->应结算平台金额, order_id->第三方订单号\\n财务: date->完成时间, amount->发生-, order_id->sup订单号", "data_cleaning_rules": {"global": {"global_transforms": [{"keep": "first", "subset": ["order_id"], "operation": "drop_duplicates", "description": "全局去重"}]}, "finance": {"aggregations": [{"group_by": "order_id", "agg_fields": {"date": "first", "amount": "sum"}, "description": "相同订单号按金额累加合并"}], "field_transforms": [{"field": "order_id", "operation": "expr", "expression": "str(row.get('order_id', '')).lstrip(\\"'\\")[:21] if pd.notna(row.get('order_id', '')) else row.get('order_id', '')", "description": "订单号去掉前面的单引号，并截取前21位"}, {"field": "amount", "decimals": 1, "operation": "round", "description": "金额保留1位小数"}]}, "business": {"aggregations": [{"group_by": "order_id", "agg_fields": {"date": "first", "amount": "sum"}, "description": "相同订单号按金额累加合并"}], "field_transforms": [{"field": "order_id", "operation": "expr", "expression": "str(row.get('order_id', '')).lstrip(\\"'\\")[:21] if pd.notna(row.get('order_id', '')) else row.get('order_id', '')", "description": "订单号去掉前面的单引号，并截取前21位"}, {"field": "amount", "decimals": 1, "operation": "round", "description": "金额保留1位小数"}]}}}	1.0	0	\N	{}	active	\N	\N	2026-03-06 11:12:48.448372+08	2026-03-06 11:12:48.448372+08	98f51d95bba9c295c0a459ad548ab61b
f9cfceaa-8554-4cae-b930-c068d48e1720	腾讯异业	真腾讯异业	00000000-0000-0000-0000-000000000003	00000000-0000-0000-0000-000000000002	00000000-0000-0000-0000-000000000001	private	{}	{"version": "1.0", "tolerance": {"date_format": "%Y-%m-%d", "amount_diff_max": 0.1}, "description": "真腾讯异业", "data_sources": {"finance": {"field_roles": {"date": "完成时间", "amount": ["发生-"], "order_id": ["sup订单号"]}, "file_pattern": ["ads_finance_d_inc_channel_details_20260105133821735_0_*.xlsm", "ads_finance_d_inc_channel_details_20260105133821735_0_*.xls", "ads_finance_d_inc_channel_details_20260105133821735_0_*.xlsb", "ads_finance_d_inc_channel_details_20260105133821735_0_*.csv", "ads_finance_d_inc_channel_details_20260105133821735_0_*.xlsx"]}, "business": {"field_roles": {"date": ["ftran_time"], "amount": "product_price", "order_id": ["roc_oid"]}, "file_pattern": ["2025-12-01~2025-12-01对账流水_*.xlsx", "2025-12-01~2025-12-01对账流水_*.csv", "2025-12-01~2025-12-01对账流水_*.xls", "2025-12-01~2025-12-01对账流水_*.xlsm", "2025-12-01~2025-12-01对账流水_*.xlsb"]}}, "key_field_role": "order_id", "rule_config_text": "去掉订单号前单引号，并截取前21位\\n订单号以104开头\\n相同订单号按金额累加合并\\nproduct_price除以100", "custom_validations": [{"name": "missing_in_business", "issue_type": "missing_in_business", "display_name": "业务缺失检测", "condition_expr": "fin_exists and not biz_exists", "detail_template": "{fin_file}存在，{biz_file}无此订单记录"}, {"name": "missing_in_finance", "issue_type": "missing_in_finance", "display_name": "财务缺失检测", "condition_expr": "biz_exists and not fin_exists", "detail_template": "{biz_file}存在，{fin_file}无此订单记录"}, {"name": "amount_mismatch", "issue_type": "amount_mismatch", "display_name": "金额差异检测", "condition_expr": "biz_exists and fin_exists and biz.get('amount') is not None and fin.get('amount') is not None and abs(float(biz.get('amount', 0)) - float(fin.get('amount', 0))) > amount_diff_max", "detail_template": "{biz_file}金额 {biz[amount]} vs {fin_file}金额 {fin[amount]}，差额 {amount_diff_formatted} 超出容差 {amount_diff_max}"}], "field_mapping_text": "业务: order_id->roc_oid, amount->product_price, date->ftran_time\\n财务: order_id->sup订单号, amount->发生-, date->完成时间", "data_cleaning_rules": {"global": {"global_transforms": [{"keep": "first", "subset": ["order_id"], "operation": "drop_duplicates", "description": "全局去重"}]}, "finance": {"row_filters": [{"condition": "str(row.get('order_id', '')).startswith('104')", "description": "仅保留104开头的订单号"}], "aggregations": [{"group_by": "order_id", "agg_fields": {"date": "first", "amount": "sum"}, "description": "相同订单号按金额累加合并"}], "field_transforms": [{"field": "amount", "operation": "abs", "description": "金额取绝对值"}, {"field": "amount", "decimals": 2, "operation": "round", "description": "金额保留2位小数"}, {"field": "order_id", "operation": "strip", "description": "订单号去除首尾空格"}, {"field": "order_id", "operation": "expr", "expression": "str(row.get('order_id', '')).lstrip(\\"'\\")[:21] if pd.notna(row.get('order_id', '')) else row.get('order_id', '')", "description": "订单号去掉前面的单引号，并截取前21位"}], "global_transforms": [{"subset": ["order_id", "amount"], "operation": "drop_na", "description": "删除关键字段为空的记录"}]}, "business": {"row_filters": [], "aggregations": [{"group_by": "order_id", "agg_fields": {"date": "first", "amount": "sum"}, "description": "相同订单号按金额累加合并"}], "field_transforms": [{"field": "amount", "decimals": 2, "operation": "round", "description": "金额保留2位小数"}, {"field": "order_id", "operation": "strip", "description": "订单号去除首尾空格"}, {"field": "order_id", "operation": "expr", "expression": "str(row.get('order_id', '')).lstrip(\\"'\\")[:21] if pd.notna(row.get('order_id', '')) else row.get('order_id', '')", "description": "订单号去掉前面的单引号，并截取前21位"}, {"field": "amount", "transform": "float(row.get('amount', 0)) / 100 if pd.notna(row.get('amount', 0)) else None", "description": "product_price除以100"}], "global_transforms": [{"subset": ["order_id"], "operation": "drop_na", "description": "删除订单号为空的记录"}]}}}	1.0	0	\N	{}	active	\N	\N	2026-03-05 16:04:42.885487+08	2026-03-05 16:04:42.885487+08	1f0d824a28c893000cdc0b5c3a476264
\.


--
-- Data for Name: reconciliation_tasks; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.reconciliation_tasks (id, rule_id, created_by, department_id, task_name, finance_files, business_files, status, progress, total_records, matched_records, unmatched_finance, unmatched_business, amount_mismatch, other_issues, result_summary, result_details, error_message, started_at, completed_at, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: rule_detail; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.rule_detail (id, rule_code, rule, remark, rule_type, user_id, name, task_id) FROM stdin;
2	verif_recog	{"rules": [{"merge": {"output": {"description": "合并完成后，将新生成文件路径与合并后文件路径一并返回给调用侧", "return_fields": [{"key": "generated_file_path", "description": "本次规则执行生成的新文件路径"}, {"key": "merged_file_path", "description": "新文件与目标文件合并后生成的结果文件路径"}]}, "enabled": true, "description": "将规则生成的新文件内容与已上传的目标文件进行合并，生成最终合并文件", "merge_strategy": {"type": "append_rows", "description": "将新生成文件的行追加到已有目标文件的行之后，形成合并数据集", "column_mismatch_policy": {"policy": "union_columns", "description": "当新文件与 merge 目标文件的列数量不一致时，取两者列的并集，缺失列填充空值", "fill_missing_value": null}}, "target_file_match": {"match_by": "target_table", "description": "根据上传文件列表，查找与 target_table 名称匹配的已有文件作为 merge 目标", "match_field": "BI费用明细表"}}, "rule_id": "SYNC_ROL_001", "version": "1.0", "description": "手工凭证表同步到BI费用明细表（手工类）的字段映射规则", "target_table": "BI费用明细表（手工类）", "global_filter": {"values": ["研发支出_费用化支出", "主营业务成本_直接服务费", "主营业务成本_工资性支出", "其他业务收入", "其他业务成本", "管理费用", "销售费用", "财务费用", "营业外收入", "营业外支出", "投资收益", "资产减值损失", "所得税"], "operator": "starts_with", "description": "从手工凭证表中过滤相关数据的总体规则", "source_column": "科目名称", "exclude_values": ["管理费用-研发费"]}, "source_tables": "手工凭证表", "field_mappings": [{"rule_type": "direct_mapping", "source_field": "业务时间", "target_field": "日期"}, {"rule_type": "direct_mapping", "source_field": "公司名称", "target_field": "所属公司"}, {"value": null, "rule_type": "constant", "target_field": "客户"}, {"value": null, "rule_type": "constant", "target_field": "店铺_平台"}, {"value": "手工凭证", "rule_type": "constant", "target_field": "数据来源"}, {"rule_type": "direct_mapping", "source_field": "凭证号", "target_field": "rp单据"}, {"rule_type": "direct_mapping", "source_field": "行政组织", "target_field": "行政中心"}, {"rule_type": "direct_mapping", "source_field": "行政组织", "target_field": "利润中心"}, {"delimiter": "_", "rule_type": "extract", "description": "从科目名称中按_截取一级科目", "source_field": "科目名称", "target_field": "eas一级科目", "extract_level": 1}, {"delimiter": "_", "rule_type": "extract", "description": "从科目名称中按_截取二级科目", "source_field": "科目名称", "target_field": "费用二级项目", "extract_level": 2}, {"delimiter": "_", "rule_type": "extract", "description": "从科目名称中按_截取三级科目", "source_field": "科目名称", "target_field": "费用三级项目", "extract_level": 3}, {"value": null, "rule_type": "constant", "target_field": "账单上提取规则"}, {"value": null, "rule_type": "constant", "target_field": "是否归属店铺费用"}, {"value": null, "rule_type": "constant", "target_field": "是否参与综合店铺分摊"}, {"formula": "round(eas不含税金额 * (1 + 税率), 2)", "rule_type": "formula", "depends_on": ["eas不含税金额", "税率"], "description": "eas含税金额 = eas不含税金额 * (1+税率)，结果保留2位小数，该列为计算列", "is_computed": true, "target_field": "eas含税金额"}, {"formula": "round(借方发生额 + 贷方发生额, 2)", "rule_type": "formula", "description": "eas不含税金额 = 借方发生额 + 贷方发生额，结果保留2位小数，其中借方发生额和贷方发生额的值来自来手工凭证表", "target_field": "eas不含税金额", "source_fields": [{"field": "借方发生额", "source_table": "手工凭证表"}, {"field": "贷方发生额", "source_table": "手工凭证表"}]}, {"formula": "round(eas含税金额 - eas不含税金额, 2)", "rule_type": "formula", "depends_on": ["eas含税金额", "eas不含税金额"], "description": "eas税额 = eas含税金额 - eas不含税金额，结果保留2位小数，该列为计算列", "is_computed": true, "target_field": "eas税额"}, {"value": null, "rule_type": "constant", "target_field": "费用项目"}, {"value": null, "rule_type": "constant", "target_field": "报表取数"}, {"value": null, "rule_type": "constant", "target_field": "报表利润中心id"}, {"value": null, "rule_type": "constant", "target_field": "报表利润中心"}, {"value": null, "rule_type": "constant", "target_field": "报表费用类型"}, {"value": null, "rule_type": "constant", "target_field": "是否公摊"}, {"value": null, "rule_type": "constant", "target_field": "中心群"}, {"rule_type": "direct_mapping", "source_field": "摘要", "target_field": "摘要备注"}, {"rule_type": "direct_mapping", "source_field": "月份", "target_field": "月分区"}, {"value": null, "rule_type": "constant", "target_field": "备注"}, {"fallback": 0, "rule_type": "regex_extract", "value_type": "float_percent", "description": "从摘要列中提取税率：在'调整费用/调整收入/调整成本'后找'+'，截取+到%之间的数字除以100作为税率（如+6%取得0.06），摘要中无匹配则税率为0", "source_field": "摘要", "target_field": "税率", "extract_group": 1, "extract_pattern": "(?:调整费用|调整收入|调整成本)\\\\+([\\\\d.]+%)"}]}, {"merge": {"output": {"description": "合并完成后，将新生成文件路径与合并后文件路径一并返回给调用侧", "return_fields": [{"key": "generated_file_path", "description": "本次规则执行生成的新文件路径"}, {"key": "merged_file_path", "description": "新文件与目标文件合并后生成的结果文件路径"}]}, "enabled": true, "description": "将规则生成的新文件内容与已上传的目标文件进行合并，生成最终合并文件", "merge_strategy": {"type": "append_rows", "description": "将新生成文件的行追加到已有目标文件的行之后，形成合并数据集", "column_mismatch_policy": {"policy": "union_columns", "description": "当新文件与 merge 目标文件的列数量不一致时，取两者列的并集，缺失列填充空值", "fill_missing_value": null}}, "target_file_match": {"match_by": "target_table", "description": "根据上传文件列表，查找与 target_table 名称匹配的已有文件作为 merge 目标", "match_field": "BI损益毛利明细表"}}, "rule_id": "SYNC_ROL_002", "version": "1.0", "description": "手工凭证表同步到BI损益毛利明细表（手工类）的字段映射规则", "target_table": "BI损益毛利明细表（手工类）", "global_filter": {"values": ["主营业务收入", "主营业务成本_销售成本", "主营业务成本_技术服务成本"], "operator": "starts_with", "description": "从手工凭证表中过滤相关数据的总体规则", "source_column": "科目名称"}, "lookup_tables": [{"table_name": "关联公司表", "description": "用于判断客户/供应商是否为关联公司"}, {"table_name": "收入明细表", "description": "用于根据科目名称查询收入类型和收入明细"}], "source_tables": "手工凭证表", "field_mappings": [{"rule_type": "direct_mapping", "source_field": "业务时间", "target_field": "日期"}, {"value": "手工凭证", "rule_type": "constant", "target_field": "数据源"}, {"rule_type": "direct_mapping", "source_field": "凭证号", "target_field": "订单类型"}, {"rule_type": "direct_mapping", "source_field": "公司名称", "target_field": "公司"}, {"rule_type": "direct_mapping", "source_field": "平台", "target_field": "店铺名称加平台"}, {"rule_type": "conditional_extract", "conditions": [{"action": "从'调整收入'关键词后的+号开始提取客户信息", "condition": {"op": "contains", "field": "摘要", "value": "调整收入"}, "extract_group": 1, "extract_pattern": "调整收入.*?\\\\+(.+?)(?:\\\\+|$)"}], "description": "从手工凭证表中取：如果摘要列里内容是调整收入，则从'调整收入'关键词后的+号开始可以取到客户信息", "source_field": "摘要", "target_field": "客户"}, {"rule_type": "lookup", "description": "从关联公司表中取，如果是关联公司，则该值为：关联，如果不是这些公司则为非关联", "lookup_field": "客户", "lookup_table": "关联公司表", "match_result": "关联", "target_field": "是否关联客户", "no_match_result": "非关联"}, {"rule_type": "direct_mapping", "source_field": "商品大类", "target_field": "商品大类"}, {"rule_type": "conditional_extract", "conditions": [{"action": "从'调整成本'或'调整费用'后的+号开始取供应商", "condition": {"or": [{"op": "contains", "field": "摘要", "value": "调整成本"}, {"op": "contains", "field": "摘要", "value": "调整费用"}]}, "extract_group": 1, "extract_pattern": "(?:调整成本|调整费用).*?\\\\+(.+?)(?:\\\\+|$)"}], "description": "从手工凭证表中取：如果摘要列里内容是调整成本或调整费用，则从调整成本或调整费用的+号后开始取供应商", "source_field": "摘要", "target_field": "供应商"}, {"rule_type": "lookup", "description": "从关联公司表中取，如果是关联公司，则该值为：关联，如果不是这些公司则为非关联", "lookup_field": "供应商", "lookup_table": "关联公司表", "match_result": "关联", "target_field": "是否关联供应商", "no_match_result": "非关联"}, {"rule_type": "conditional_value", "conditions": [{"value": "净额", "condition": {"op": "eq", "field": "科目名称", "value": "主营业务收入_寄售收入"}}, {"value": "总额", "condition": {"default": true}}], "description": "从手工凭证表中取：从科目名称判断：当前科目名称=主营业务收入_寄售收入，则值为：净额；其他为：总额", "source_field": "科目名称", "target_field": "核算类型或返点类型"}, {"rule_type": "direct_mapping", "source_field": "科目编码", "target_field": "eas科目"}, {"rule_type": "direct_mapping", "source_field": "科目名称", "target_field": "科目名称"}, {"formula": "round(eas收入不含税 * (1 + 税率), 2)", "rule_type": "formula", "depends_on": ["eas收入不含税", "税率"], "description": "含税销售额=eas收入不含税*(1+税率)，结果保留2位小数，该列为计算列", "is_computed": true, "target_field": "含税销售额"}, {"formula": "round(eas成本不含税 * (1 + 税率), 2)", "rule_type": "formula", "depends_on": ["eas成本不含税", "税率"], "description": "含税采购成本=eas成本不含税*(1+税率)，结果保留2位小数，该列为计算列", "is_computed": true, "target_field": "含税采购成本"}, {"formula": "round(含税销售额 - 含税采购成本, 2)", "rule_type": "formula", "depends_on": ["含税销售额", "含税采购成本"], "description": "含税差额收入=含税销售额-含税采购成本，结果保留2位小数，该列为计算列", "is_computed": true, "target_field": "含税差额收入"}, {"rule_type": "conditional_formula", "conditions": [{"formula": "贷方发生额", "condition": {"and": [{"op": "contains", "field": "摘要", "value": "调整收入"}, {"op": "eq", "field": "科目名称", "value": "主营业务收入_寄售收入"}]}, "description": "eas收入不含税为'贷方发生额'，'eas成本不含税'为零", "eas成本不含税": 0}, {"formula": "贷方发生额", "condition": {"or": [{"op": "startswith", "field": "科目名称", "value": "主营业务收入_销售收入"}, {"op": "startswith", "field": "科目名称", "value": "主营业务收入_技术服务收入"}]}, "description": "eas收入不含税为'贷方发生额'，'eas成本不含税'为零", "eas成本不含税": 0}], "description": "从手工凭证表中取，根据摘要里的调整类型和科目名称条件判断取值", "source_field": "科目名称", "target_field": "eas收入不含税"}, {"rule_type": "conditional_formula", "conditions": [{"formula": "-贷方发生额", "condition": {"and": [{"op": "contains", "field": "摘要", "value": "调整成本"}, {"op": "eq", "field": "科目名称", "value": "主营业务收入_寄售收入"}]}, "description": "eas收入不含税为零，'eas成本不含税'为负数'贷方发生额'", "eas收入不含税": 0}, {"formula": "借方发生额", "condition": {"or": [{"op": "startswith", "field": "科目名称", "value": "主营业务成本_销售成本"}, {"op": "startswith", "field": "科目名称", "value": "主营业务成本_技术服务成本"}]}, "description": "eas收入不含税为零，'eas成本不含税'为'借方发生额'", "eas收入不含税": 0}], "description": "从手工凭证表中取，根据摘要里的调整类型和科目名称条件判断取值", "source_field": "科目名称", "target_field": "eas成本不含税"}, {"formula": "round(含税销售额 - eas收入不含税, 2)", "rule_type": "formula", "depends_on": ["含税销售额", "eas收入不含税"], "description": "eas税额=含税销售额-eas收入不含税，结果保留2位小数，该列为计算列", "is_computed": true, "target_field": "eas税额"}, {"formula": "round(eas收入不含税 - eas成本不含税, 2)", "rule_type": "formula", "depends_on": ["eas收入不含税", "eas成本不含税"], "description": "eas差额收入不含税=eas收入不含税-eas成本不含税，结果保留2位小数，该列为计算列", "is_computed": true, "target_field": "eas差额收入不含税"}, {"rule_type": "lookup", "lookup_key": "科目名称", "description": "从手工凭证表中取科目名称，并根据科目名称的值从收入类型与收入明细表中取对应的收入类型", "lookup_table": "收入明细表", "return_field": "收入类型", "source_field": "科目名称", "target_field": "收入类型"}, {"rule_type": "lookup", "lookup_key": "科目名称", "description": "从手工凭证表中取科目名称，并根据科目名称的值并从收入类型与收入明细表中取对应的收入明细", "lookup_table": "收入明细表", "return_field": "收入明细", "source_field": "科目名称", "target_field": "收入明细"}, {"rule_type": "conditional_value", "conditions": [{"value": 0.13, "condition": {"or": [{"op": "eq", "field": "科目名称", "value": "主营业务收入_销售收入_销售收入-13%"}, {"op": "eq", "field": "科目名称", "value": "主营业务成本_销售成本_销售成本-13%"}]}, "description": "税率为13%"}, {"value": 0.09, "condition": {"or": [{"op": "eq", "field": "科目名称", "value": "主营业务收入_销售收入_销售收入-9%"}, {"op": "eq", "field": "科目名称", "value": "主营业务成本_销售成本_销售成本-9%"}]}, "description": "税率为9%"}, {"value": 0.03, "condition": {"or": [{"op": "eq", "field": "科目名称", "value": "主营业务收入_销售收入_销售收入-3%"}, {"op": "eq", "field": "科目名称", "value": "主营业务成本_销售成本_销售成本-3%"}]}, "description": "税率为3%"}, {"value": 0.01, "condition": {"or": [{"op": "eq", "field": "科目名称", "value": "主营业务收入_销售收入_销售收入-1%"}, {"op": "eq", "field": "科目名称", "value": "主营业务成本_销售成本_销售成本-1%"}]}, "description": "税率为1%"}, {"value": 0.06, "condition": {"default": true}, "description": "其他科目税率为6%"}], "description": "根据科目名称判断税率：含-13%的为13%，含-9%的为9%，含-3%的为3%，含-1%的为1%，其他为6%", "source_field": "科目名称", "target_field": "税率"}]}], "role_desc": "核算部门数据整理规则", "file_rule_code": "recog_file_check"}	核算部门数据整理规则	proc	\N	核算部门数据整理规则	3
4	audio_recon	{"rules": [{"output": {"format": "xlsx", "sheets": {"summary": {"name": "核对汇总", "enabled": true, "description": "输出核对结果汇总信息，包括总记录数、匹配数、差异数等"}, "source_only": {"name": "合单独有", "enabled": true, "description": "仅在合单文件中存在的记录"}, "target_only": {"name": "官网独有", "enabled": true, "description": "仅在官网文件中存在的记录"}, "matched_with_diff": {"name": "差异记录", "enabled": true, "description": "关键列匹配但数值有差异的记录详情"}}, "file_name_template": "喜马26_{rule_name}_核对结果_{timestamp}"}, "enabled": true, "rule_id": "XM_26_RECONC_001", "rule_name": "喜马-26合单与官网数据核对", "description": "将合单文件与官网文件进行核对，通过sup订单号与第三方订单号关联，比对金额数据差异", "source_file": {"table_name": "喜马合单表", "description": "源文件定义（合单文件）", "identification": {"match_by": "table_name", "description": "通过文件校验阶段识别的表名匹配源文件", "match_value": "喜马合单表", "match_strategy": "exact"}}, "target_file": {"table_name": "喜马官网表", "description": "目标文件定义（官网文件）", "identification": {"match_by": "table_name", "description": "通过文件校验阶段识别的表名匹配目标文件", "match_value": "喜马官网表", "match_strategy": "exact"}}, "diff_analysis": {"description": "差异分析配置", "diff_columns": {"columns": [{"name": "diff_合作方分销收入", "formula": "source.发生减 - target.合作方分销收入", "description": "合作方分销收入差异 = 合单发生- - 官网合作方分销收入"}, {"name": "diff_应结算平台金额", "formula": "source.发生加 - target.应结算平台金额", "description": "应结算平台金额差异 = 合单发生+ - 官网应结算平台金额"}, {"name": "diff_商品金额", "formula": "source.发生加 - target.商品金额", "description": "商品金额差异"}, {"name": "diff_实付金额", "formula": "source.发生加 - target.实付金额", "description": "实付金额差异"}, {"name": "diff_percent_合作方分销收入", "formula": "(source.发生减 - target.合作方分销收入) / target.合作方分销收入 * 100", "description": "合作方分销收入差异百分比"}], "description": "差异计算列配置"}, "output_types": [{"type": "matched_with_diff", "enabled": true, "description": "关键列匹配但数值有差异的记录", "output_columns": ["source.*", "target.*", "diff.*"]}, {"type": "source_only", "enabled": true, "description": "仅在源文件(合单)中存在，目标文件中不存在的记录", "output_columns": ["source.*"]}, {"type": "target_only", "enabled": true, "description": "仅在目标文件(官网)中存在，源文件中不存在的记录", "output_columns": ["target.*"]}, {"type": "matched_exact", "enabled": false, "description": "完全匹配的记录（可选输出）", "output_columns": ["source.*"]}]}, "reconciliation_config": {"aggregation": {"enabled": false, "group_by": ["订单号", "sup订单号"], "description": "分组聚合配置，启用后先按group_by列分组聚合，再进行比对", "aggregations": [{"alias": "发生加_汇总", "column": "发生+", "function": "sum"}, {"alias": "发生减_汇总", "column": "发生-", "function": "sum"}]}, "description": "核对配置", "key_columns": {"columns": ["sup订单号", "第三方订单号"], "match_type": "exact", "description": "用于关联源文件与目标文件的关键列（相当于JOIN条件）", "case_sensitive": false, "transformations": {"source": {"description": "去除合单文件sup订单号的单引号前缀", "strip_prefix": "'"}, "target": {"description": "去除官网文件第三方订单号的_后缀", "regex_replace": {"pattern": "_\\\\d+$", "replacement": ""}}}, "cross_file_mapping": {"source_column": "sup订单号", "target_column": "第三方订单号"}}, "compare_columns": {"columns": [{"column": "发生减", "tolerance": 0.01, "description": "合单发生- 与 官网合作方分销收入 比对，允许0.01的绝对误差", "compare_type": "numeric", "source_table": "喜马合单表", "target_table": "喜马官网表", "source_column": "发生-", "target_column": "应结算平台金额", "tolerance_type": "absolute"}], "description": "需要比对的数值列"}}}], "description": "喜马-26文件对账规则定义，用于合单文件与官网文件的数据比对与差异分析", "file_rule_code": "audio_recon_file_check", "schema_version": "1.0", "global_settings": {"diff_output_types": {"source_only": "仅在源文件中存在的记录（目标文件缺失）", "target_only": "仅在目标文件中存在的记录（源文件缺失）", "matched_exact": "完全匹配的记录", "matched_with_diff": "关键列匹配但数值有差异的记录"}, "key_columns_config": {"match_type_options": {"exact": "精确匹配", "fuzzy": "模糊匹配（忽略空格、大小写等）", "prefix": "前缀匹配"}}, "file_identification": {"match_by_options": {"table_name": "通过文件校验阶段关联的表名识别", "file_name_regex": "文件名正则匹配", "column_signature": "通过列名签名识别（指定必需列）", "file_name_contains": "文件名包含指定关键词"}, "match_strategy_options": {"exact": "精确匹配", "regex": "正则匹配", "contains": "包含匹配", "startswith": "前缀匹配"}}, "aggregation_functions": {"avg": "平均值", "max": "最大值", "min": "最小值", "sum": "求和", "last": "取最后一个值", "count": "计数", "first": "取第一个值"}, "compare_columns_config": {"compare_type_options": {"date": "日期比对", "text": "文本比对", "numeric": "数值比对"}, "tolerance_type_options": {"none": "不允许任何差异", "absolute": "绝对误差（如0.01表示允许±0.01的差异）", "relative": "相对误差（如0.01表示允许±1%的差异）"}}}}	审计对账规则，用于源文件与目标文件的数据比对与差异分析	recon	\N	喜马-26合单与官网数据核对	5
3	verif_recog_merge	{"action": "", "description": "数据合并规则定义文件，支持多表数据合并操作", "merge_rules": [{"output": {"format": "xlsx", "description": "输出文件命名模板和格式", "file_name_template": "{table_name}_merged_{timestamp}"}, "enabled": true, "rule_id": "MERGE_001", "table_id": "BI_EXPENSE_DETAIL", "rule_name": "BI费用明细表合并", "merge_type": "append_rows", "table_name": "BI费用明细表", "description": "将所有BI费用明细表类型的文件合并为一个表", "merge_config": {"description": "append_rows: 将所有匹配表的行追加合并", "deduplication": {"enabled": false, "description": "是否去重，如启用需指定去重键列", "key_columns": []}, "sort_after_merge": {"enabled": false, "ascending": true, "description": "合并后是否排序", "sort_columns": []}, "column_mismatch_policy": {"policy": "union_columns", "description": "列不一致时取并集，缺失列填充空值", "fill_missing_value": null}}, "table_matching": {"match_by": "table_name", "description": "通过文件校验阶段关联的table_name进行匹配，table_name相同即视为同类表"}}, {"output": {"format": "xlsx", "description": "输出文件命名模板和格式", "file_name_template": "{table_name}_merged_{timestamp}"}, "enabled": true, "rule_id": "MERGE_002", "table_id": "BI_PROFIT_LOSS_DETAIL", "rule_name": "BI损益毛利明细表合并", "merge_type": "append_rows", "table_name": "BI损益毛利明细表", "description": "将所有BI损益毛利明细表类型的文件合并为一个表", "merge_config": {"description": "append_rows: 将所有匹配表的行追加合并", "deduplication": {"enabled": false, "description": "是否去重，如启用需指定去重键列", "key_columns": []}, "sort_after_merge": {"enabled": false, "ascending": true, "description": "合并后是否排序", "sort_columns": []}, "column_mismatch_policy": {"policy": "union_columns", "description": "列不一致时取并集，缺失列填充空值", "fill_missing_value": null}}, "table_matching": {"match_by": "table_name", "description": "通过文件校验阶段关联的table_name进行匹配，table_name相同即视为同类表"}}], "file_rule_code": "recog_merge_file_check", "schema_version": "1.0", "global_settings": {"merge_types": {"append_rows": {"use_case": "适用于相同结构的表需要纵向拼接的场景", "description": "行追加合并，将所有匹配表的数据行合并为一个表"}, "aggregate_by_key": {"use_case": "适用于需要按维度汇总数据的场景", "description": "按键聚合合并，根据指定键列相同时进行聚合操作"}}, "aggregation_methods": {"text": {"last": "取最后一个值", "first": "取第一个值", "concat": "拼接（可指定分隔符）", "longest": "取最长文本", "shortest": "取最短文本", "concat_distinct": "去重后拼接"}, "numeric": {"avg": "平均值", "max": "最大值", "min": "最小值", "sum": "求和", "last": "取最后一个值", "count": "计数", "first": "取第一个值"}, "datetime": {"max": "取最晚日期", "min": "取最早日期", "last": "取最后一个值", "first": "取第一个值"}}, "table_matching_options": {"match_modes": {"all": "所有matcher都匹配才视为适用", "any": "任一matcher匹配即视为适用"}, "matcher_types": {"column_signature": "通过列标题签名匹配同类表", "table_name_exact": "表名精确匹配", "table_name_regex": "表名正则匹配", "table_name_contains": "表名包含关键词", "table_name_startswith": "表名以指定前缀开头"}}, "column_mismatch_policies": {"strict": "列必须完全一致，否则报错", "union_columns": "取所有表列的并集，缺失列填充指定值", "intersection_columns": "取所有表列的交集，只保留共有列"}}}	文件校验与识别后的数据合并规则	proc	\N	BI费用明细表合并	3
5	recog_merge_file_check	{"file_validation_rules": {"version": "1.0", "description": "文件上传合法性校验规则，用于验证用户上传的文件是否符合系统要求", "table_schemas": [{"is_ness": false, "table_id": "BI_EXPENSE_DETAIL", "file_type": ["xls", "xlsx", "csv"], "table_name": "BI费用明细表", "table_type": "target", "all_columns": ["日期", "所属公司", "客户", "店铺_平台", "数据来源", "rp单据", "行政中心", "利润中心", "eas一级科目", "费用二级项目", "费用三级项目", "账单上提取规则", "是否归属店铺费用", "是否参与综合店铺分摊", "eas含税金额", "eas不含税金额", "eas税额", "费用项目", "报表取数", "报表利润中心id", "报表利润中心", "报表费用类型", "是否公摊", "中心群", "摘要备注", "月分区", "备注", "税率"], "description": "BI费用明细表（手工类），用于记录费用明细数据", "column_aliases": {"日期": ["date", "业务日期"], "所属公司": ["公司", "company"], "数据来源": ["来源", "source"], "eas一级科目": ["一级科目", "科目一级"], "eas不含税金额": ["不含税金额", "金额"]}, "optional_columns": ["客户", "店铺平台", "rp单据", "费用二级项目", "费用三级项目", "账单上提取规则", "是否归属店铺", "是否参与综合", "eas含税金额", "eas税额", "费用项目", "报表取数", "报表利润中心id", "报表利润中心", "报表费用类型", "是否公摊", "中心群", "摘要备注", "月分区", "备注"], "required_columns": ["日期", "所属公司", "数据来源", "行政中心", "利润中心", "eas一级科目", "eas不含税金额"]}, {"is_ness": false, "table_id": "BI_PROFIT_LOSS_DETAIL", "file_type": ["xls", "xlsx", "csv"], "table_name": "BI损益毛利明细表", "table_type": "target", "all_columns": ["日期", "数据源", "订单类型", "公司", "店铺名称加平台", "客户", "是否关联客户", "商品大类", "供应商", "是否关联供应商", "核算类型或返点类型", "eas科目", "科目名称", "含税销售额", "含税采购成本", "含税差额收入", "eas收入不含税", "eas成本不含税", "eas税额", "eas差额收入不含税", "收入类型", "收入明细", "税率"], "description": "BI损益毛利明细表（手工类），用于记录损益和毛利数据", "column_aliases": {"公司": ["所属公司", "company"], "日期": ["date", "业务日期"], "数据源": ["数据来源", "source"], "科目名称": ["科目", "account_name"], "eas成本不含税": ["成本不含税", "不含税成本"], "eas收入不含税": ["收入不含税", "不含税收入"]}, "optional_columns": ["订单类型", "店铺名称加平台", "客户", "是否关联客户", "商品大类", "供应商", "是否关联供应商", "核算类型或返点类型", "eas科目", "含税销售额", "含税采购成本", "含税差额收入", "eas税额", "eas差额收入不含税", "收入类型", "收入明细"], "required_columns": ["日期", "数据源", "公司", "科目名称", "eas收入不含税", "eas成本不含税"]}], "validation_config": {"file_count": {"max": 10, "min": 2, "allow_multiple": true, "max_description": "最大上传文件数量，0表示不限制", "min_description": "最少上传文件数量", "allow_multiple_description": "是否允许多文件上传"}, "case_sensitive": false, "match_strategy": "exact", "ignore_whitespace": true, "allow_multi_rule_match": false, "case_sensitive_description": "列名匹配是否区分大小写", "match_strategy_description": "exact表示全量列名精确匹配，文件列名必须与规则定义的列名集合完全一致", "ignore_whitespace_description": "是否忽略列名中的空格", "allow_multi_rule_match_description": "true.表示允许多个文件匹配到一条规则,false.表示不允许"}}}	整理操作-文件上传合法性校验规则	file	\N	整理操作-文件上传合法性校验规则	3
1	recog_file_check	{"file_validation_rules": {"version": "1.0", "description": "文件上传合法性校验规则，用于验证用户上传的文件是否符合系统要求", "table_schemas": [{"is_ness": true, "table_id": "MANUAL_VOUCHER", "file_type": ["xls", "xlsx", "csv"], "table_name": "手工凭证表", "table_type": "source", "all_columns": ["月份", "取值类型", "科目编码", "科目名称", "公司名称", "币种", "商品大类", "平台", "行政组织", "业务时间", "借方发生额", "贷方发生额", "摘要", "凭证号", "制单人", "来源类型"], "description": "手工凭证数据源表，包含凭证的基本信息和金额数据", "column_aliases": {"摘要": ["备注", "description", "remark"], "月份": ["月", "month", "期间"], "凭证号": ["凭证编号", "voucher_no", "单据号"], "公司名称": ["公司", "company", "company_name"], "科目名称": ["科目", "account_name"], "科目编码": ["科目代码", "account_code"], "借方发生额": ["借方金额", "debit", "借方"], "贷方发生额": ["贷方金额", "credit", "贷方"]}, "optional_columns": ["取值类型", "币种", "商品大类", "平台", "行政组织", "业务时间", "制单人", "来源类型"], "required_columns": ["月份", "科目编码", "科目名称", "公司名称", "借方发生额", "贷方发生额", "摘要", "凭证号"]}, {"is_ness": false, "table_id": "BI_EXPENSE_DETAIL", "file_type": ["xls", "xlsx", "csv"], "table_name": "BI费用明细表", "table_type": "target", "all_columns": ["日期", "所属公司", "客户", "店铺_平台", "数据来源", "rp单据", "行政中心", "利润中心", "eas一级科目", "费用二级项目", "费用三级项目", "账单上提取规则", "是否归属店铺费用", "是否参与综合店铺分摊", "eas含税金额", "eas不含税金额", "eas税额", "费用项目", "报表取数", "报表利润中心id", "报表利润中心", "报表费用类型", "是否公摊", "中心群", "摘要备注", "月分区", "备注", "税率"], "description": "BI费用明细表（手工类），用于记录费用明细数据", "column_aliases": {"日期": ["date", "业务日期"], "所属公司": ["公司", "company"], "数据来源": ["来源", "source"], "eas一级科目": ["一级科目", "科目一级"], "eas不含税金额": ["不含税金额", "金额"]}, "optional_columns": ["客户", "店铺平台", "rp单据", "费用二级项目", "费用三级项目", "账单上提取规则", "是否归属店铺", "是否参与综合", "eas含税金额", "eas税额", "费用项目", "报表取数", "报表利润中心id", "报表利润中心", "报表费用类型", "是否公摊", "中心群", "摘要备注", "月分区", "备注"], "required_columns": ["日期", "所属公司", "数据来源", "行政中心", "利润中心", "eas一级科目", "eas不含税金额"]}, {"is_ness": false, "table_id": "BI_PROFIT_LOSS_DETAIL", "file_type": ["xls", "xlsx", "csv"], "table_name": "BI损益毛利明细表", "table_type": "target", "all_columns": ["日期", "数据源", "订单类型", "公司", "店铺名称加平台", "客户", "是否关联客户", "商品大类", "供应商", "是否关联供应商", "核算类型或返点类型", "eas科目", "科目名称", "含税销售额", "含税采购成本", "含税差额收入", "eas收入不含税", "eas成本不含税", "eas税额", "eas差额收入不含税", "收入类型", "收入明细", "税率"], "description": "BI损益毛利明细表（手工类），用于记录损益和毛利数据", "column_aliases": {"公司": ["所属公司", "company"], "日期": ["date", "业务日期"], "数据源": ["数据来源", "source"], "科目名称": ["科目", "account_name"], "eas成本不含税": ["成本不含税", "不含税成本"], "eas收入不含税": ["收入不含税", "不含税收入"]}, "optional_columns": ["订单类型", "店铺名称加平台", "客户", "是否关联客户", "商品大类", "供应商", "是否关联供应商", "核算类型或返点类型", "eas科目", "含税销售额", "含税采购成本", "含税差额收入", "eas税额", "eas差额收入不含税", "收入类型", "收入明细"], "required_columns": ["日期", "数据源", "公司", "科目名称", "eas收入不含税", "eas成本不含税"]}], "validation_config": {"case_sensitive": false, "match_strategy": "exact", "ignore_whitespace": true, "case_sensitive_description": "列名匹配是否区分大小写", "match_strategy_description": "exact表示全量列名精确匹配，文件列名必须与规则定义的列名集合完全一致", "ignore_whitespace_description": "是否忽略列名中的空格"}}}	整理操作-文件上传合法性校验规则	file	\N	整理操作-文件上传合法性校验规则	3
6	audio_recon_file_check	{"file_validation_rules": {"version": "1.0", "description": "音频业务对账文件校验规则，包含喜马-26、腾讯异业、南京飞翰等目录的文件校验", "table_schemas": [{"is_ness": false, "table_id": "XIMA_HE_DAN", "file_type": ["xls", "xlsx", "csv"], "table_name": "喜马合单表", "table_type": "source", "all_columns": ["完成时间", "订单来源", "订单号", "sup订单号", "合单订单号", "订单类型", "结算类型", "渠道所属公司", "渠道供应商", "渠道名称", "渠道账号", "发生+", "发生-", "商品大类", "公司id", "渠道id", "供应商id", "退款订单号", "提交时间", "分区"], "description": "喜马合单数据表，包含订单汇总和渠道结算信息", "column_aliases": {"发生+": ["发生加", "收入", "income"], "发生-": ["发生减", "支出", "expense"], "订单号": ["订单编号", "order_no"], "完成时间": ["完成日期", "finish_time"], "渠道名称": ["channel_name"], "结算类型": ["settlement_type"], "订单来源": ["来源", "order_source"], "订单类型": ["order_type"], "渠道供应商": ["供应商", "channel_supplier"], "渠道所属公司": ["所属公司", "channel_company"]}, "optional_columns": ["sup订单号", "合单订单号", "渠道账号", "商品大类", "公司id", "渠道id", "供应商id", "退款订单号", "提交时间", "分区"], "required_columns": ["完成时间", "订单来源", "订单号", "订单类型", "结算类型", "渠道所属公司", "渠道供应商", "渠道名称", "发生+", "发生-"], "max_file_match_count": 1, "max_file_match_count_description": "0.表示不限制数量,其它配置则超时此数量则校验不通过"}, {"is_ness": false, "table_id": "XIMA_GUAN_WANG", "file_type": ["xls", "xlsx", "csv"], "table_name": "喜马官网表", "table_type": "target", "all_columns": ["喜马订单号", "支付时间", "分成比例", "合作方分销收入", "应结算平台金额", "结算状态", "应用名称", "支付渠道", "第三方订单号", "用户客户端类型", "商品名称", "商品类型", "商品图片", "专辑id", "商品金额", "实付金额", "支付渠道费", "订单状态", "CPA信息", "物流公司", "物流单号", "物流状态"], "description": "喜马官网订单明细表，包含订单详情和商品信息", "column_aliases": {"分成比例": ["分成", "share_ratio"], "商品金额": ["product_amount", "商品总价"], "实付金额": ["actual_amount", "实际支付金额"], "支付时间": ["pay_time", "付款时间"], "结算状态": ["settlement_status"], "喜马订单号": ["订单号", "xima_order_no", "order_no"], "合作方分销收入": ["分销收入", "partner_income"], "应结算平台金额": ["结算金额", "settlement_amount"]}, "optional_columns": ["应用名称", "支付渠道", "第三方订单号", "用户客户端类型", "商品名称", "商品类型", "商品图片", "专辑id", "支付渠道费", "订单状态", "CPA信息", "物流公司", "物流单号", "物流状态"], "required_columns": ["喜马订单号", "支付时间", "分成比例", "合作方分销收入", "应结算平台金额", "结算状态", "商品金额", "实付金额"]}, {"is_ness": false, "table_id": "TENCENT_RECON_STATEMENT", "file_type": ["csv"], "table_name": "腾讯异业对账流水表", "table_type": "source", "all_columns": ["statis_date", "ftran_time", "offer_name", "offer_id", "contract_no", "sub_merchant_name", "result", "roc_oid", "pay_channel", "deliver_method", "provide_no_type", "provide_uin", "product_name", "product_id", "buy_quantity", "product_price", "pay_amt", "tob_sub_channel_id", "drm_info", "activity_id", "rebate_goods", "provide_result", "product_offer_id", "roc_oid_text"], "description": "腾讯异业对账流水表，包含腾讯侧的订单交易明细数据", "column_aliases": {"result": ["结果", "交易结果"], "pay_amt": ["支付金额", "支付总额", "pay_amount"], "roc_oid": ["订单号", "订单ID"], "offer_id": ["商品ID", "offer_id_cn"], "ftran_time": ["交易时间", "transaction_time"], "offer_name": ["商品名称", "offer_name_cn"], "pay_channel": ["支付渠道", "支付方式"], "statis_date": ["统计日期", "stat_date"], "buy_quantity": ["购买数量", "quantity"]}, "optional_columns": ["contract_no", "sub_merchant_name", "deliver_method", "provide_no_type", "provide_uin", "product_id", "product_price", "tob_sub_channel_id", "drm_info", "activity_id", "rebate_goods", "provide_result", "product_offer_id", "roc_oid_text"], "required_columns": ["statis_date", "ftran_time", "offer_name", "offer_id", "result", "roc_oid", "pay_channel", "product_name", "buy_quantity", "pay_amt"]}, {"is_ness": false, "table_id": "TENCENT_CHANNEL_DETAILS", "file_type": ["xls", "xlsx", "csv"], "table_name": "腾讯异业渠道明细表", "table_type": "target", "all_columns": ["完成时间", "订单来源", "订单号", "sup订单号", "合单订单号", "订单类型", "结算类型", "渠道所属公司", "渠道供应商", "渠道名称", "渠道账号", "发生+", "发生-", "商品大类", "公司id", "渠道id", "供应商id", "退款订单号", "提交时间", "分区"], "description": "腾讯异业渠道明细表，包含订单汇总和渠道结算信息", "column_aliases": {"发生+": ["发生加", "收入", "income"], "发生-": ["发生减", "支出", "expense"], "订单号": ["订单编号", "order_no"], "完成时间": ["完成日期", "finish_time"], "渠道名称": ["channel_name"], "结算类型": ["settlement_type"], "订单来源": ["来源", "order_source"], "订单类型": ["order_type"], "渠道供应商": ["供应商", "channel_supplier"], "渠道所属公司": ["所属公司", "channel_company"]}, "optional_columns": ["sup订单号", "合单订单号", "渠道账号", "商品大类", "公司id", "渠道id", "供应商id", "退款订单号", "提交时间", "分区"], "required_columns": ["完成时间", "订单来源", "订单号", "订单类型", "结算类型", "渠道所属公司", "渠道供应商", "渠道名称", "发生+", "发生-"]}, {"is_ness": false, "table_id": "NANJING_ORDER_DETAIL", "file_type": ["xls", "xlsx", "csv"], "table_name": "南京飞翰订单明细表", "table_type": "source", "all_columns": ["订单编号", "sp订单号", "商品编号", "商品名称", "充值账号", "面值", "购买数量", "销售额", "成本", "利润", "状态", "操作人", "接收短信手机", "接收邮箱", "订单时间", "处理时间", "员工编号"], "description": "南京飞翰订单明细表，包含订单商品和充值信息", "column_aliases": {"利润": ["profit", "毛利"], "成本": ["cost"], "状态": ["订单状态", "status"], "面值": ["面额", "face_value"], "销售额": ["销售金额", "sales"], "充值账号": ["账号", "account"], "商品名称": ["product_name"], "商品编号": ["商品ID", "product_id"], "订单编号": ["订单号", "order_no", "order_id"], "购买数量": ["数量", "quantity"]}, "optional_columns": ["sp订单号", "操作人", "接收短信手机", "接收邮箱", "订单时间", "处理时间", "员工编号"], "required_columns": ["订单编号", "商品编号", "商品名称", "充值账号", "面值", "购买数量", "销售额", "成本", "利润", "状态"]}, {"is_ness": false, "table_id": "NANJING_CHANNEL_DETAILS", "file_type": ["xls", "xlsx", "csv"], "table_name": "南京飞翰渠道明细表", "table_type": "target", "all_columns": ["完成时间", "提交时间", "订单来源", "订单号", "sup订单号", "合单订单号", "订单类型", "结算类型", "渠道所属公司", "渠道供应商", "渠道名称", "渠道账号", "发生+", "发生-", "商品大类", "公司id", "渠道id", "供应商id", "退款订单号", "分区"], "description": "南京飞翰渠道明细表，包含订单汇总和渠道结算信息", "column_aliases": {"发生+": ["发生加", "收入", "income"], "发生-": ["发生减", "支出", "expense"], "订单号": ["订单编号", "order_no"], "完成时间": ["完成日期", "finish_time"], "渠道名称": ["channel_name"], "结算类型": ["settlement_type"], "订单来源": ["来源", "order_source"], "订单类型": ["order_type"], "渠道供应商": ["供应商", "channel_supplier"], "渠道所属公司": ["所属公司", "channel_company"]}, "optional_columns": ["提交时间", "sup订单号", "合单订单号", "渠道账号", "商品大类", "公司id", "渠道id", "供应商id", "退款订单号", "分区"], "required_columns": ["完成时间", "订单来源", "订单号", "订单类型", "结算类型", "渠道所属公司", "渠道供应商", "渠道名称", "发生+", "发生-"]}, {"is_ness": false, "table_id": "XIMA_HE_DAN_2", "file_type": ["xls", "xlsx", "csv"], "table_name": "喜马合单表_副本", "table_type": "source", "all_columns": ["完成时间", "订单来源", "订单号", "sup订单号", "合单订单号", "订单类型", "结算类型", "渠道所属公司", "渠道供应商", "渠道名称", "渠道账号", "发生+", "发生-", "商品大类", "公司id", "渠道id", "供应商id", "退款订单号", "提交时间", "分区"], "description": "喜马合单数据表，包含订单汇总和渠道结算信息", "column_aliases": {"发生+": ["发生加", "收入", "income"], "发生-": ["发生减", "支出", "expense"], "订单号": ["订单编号", "order_no"], "完成时间": ["完成日期", "finish_time"], "渠道名称": ["channel_name"], "结算类型": ["settlement_type"], "订单来源": ["来源", "order_source"], "订单类型": ["order_type"], "渠道供应商": ["供应商", "channel_supplier"], "渠道所属公司": ["所属公司", "channel_company"]}, "optional_columns": ["sup订单号", "合单订单号", "渠道账号", "商品大类", "公司id", "渠道id", "供应商id", "退款订单号", "提交时间", "分区"], "required_columns": ["完成时间", "订单来源", "订单号", "订单类型", "结算类型", "渠道所属公司", "渠道供应商", "渠道名称", "发生+", "发生-"], "max_file_match_count": 1, "max_file_match_count_description": "0.表示不限制数量,其它配置则超时此数量则校验不通过"}], "validation_config": {"file_count": {"max": 10, "min": 2, "allow_multiple": true, "max_description": "最大上传文件数量，0表示不限制", "min_description": "最少上传文件数量", "allow_multiple_description": "是否允许多文件上传"}, "case_sensitive": false, "match_strategy": "exact", "ignore_whitespace": true, "allow_multi_rule_match": false, "case_sensitive_description": "列名匹配是否区分大小写", "match_strategy_description": "exact表示全量列名精确匹配，文件列名必须与规则定义的列名集合完全一致", "ignore_whitespace_description": "是否忽略列名中的空格", "allow_multi_rule_match_description": "是否允许多条table_schemas规则同时命中同一个文件，true表示允许，false表示不允许（文件只能匹配一条规则）"}}}	审计对账-文件上传合法性校验规则	file	\N	审计对账-文件上传合法性校验规则	5
\.


--
-- Data for Name: rule_usage_logs; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.rule_usage_logs (id, rule_id, user_id, department_id, task_id, action, result_summary, created_at) FROM stdin;
\.


--
-- Data for Name: rule_versions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.rule_versions (id, rule_id, version, rule_template, created_by, change_summary, created_at) FROM stdin;
\.


--
-- Data for Name: user_tasks; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_tasks (id, user_id, task_code, task_name, description) FROM stdin;
3	00000000-0000-0000-0000-000000000003	verif_recog	数据整理	\N
5	00000000-0000-0000-0000-000000000003	audio_recon	数据对账	\N
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.users (id, username, password_hash, email, phone, department_id, company_id, role, created_at, updated_at, last_login, status) FROM stdin;
00000000-0000-0000-0000-000000000001	system		system@finflux.local	\N	\N	\N	admin	2026-02-12 16:20:15.777487+08	2026-02-12 16:20:15.777487+08	\N	active
3b593fbd-d0cd-48b8-99f1-fd9274f4059d	testuser	$2b$12$eMoYGYTk1cBXupBiYXk5he8PG56Fyb8t2TpFCVovKcQrnWJdg0VKG	\N	\N	00000000-0000-0000-0000-000000000002	00000000-0000-0000-0000-000000000001	member	2026-02-12 17:08:15.240684+08	2026-02-12 17:08:15.240684+08	\N	active
8416371f-95f9-4454-b516-a20d434ca79c	testuser_828796	$2b$12$aortAUQny0vsJFcFfFkJ4edAzrphidZX1pRDsb6y3D.CD1AeD9B.q	\N	\N	\N	\N	member	2026-02-13 11:20:30.039084+08	2026-02-13 11:24:06.561373+08	2026-02-13 11:24:06.561373+08	active
85a817b0-9fdb-4281-89e1-220ee539373c	testuser_1770953046_7807	$2b$12$avN29IEdT0T1c.16NOFkGOC2XJpew5ziRJQxVBja7jjMUdlVWDZda	testuser_1770953046_7807@test.com	13800000000	\N	\N	member	2026-02-13 11:24:06.954359+08	2026-02-13 11:24:06.954359+08	\N	active
dbcc40a1-1a3f-4da9-a726-76e3b1e29e0b	user_1770953127_9395	$2b$12$MF1isplyh9RcLJAt4L8tzOw/Vgjpyk1dJkZyekDhej.Ssafd9CVH.	user_1770953127_9395@example.com	13800000000	\N	\N	member	2026-02-13 11:25:28.940015+08	2026-02-13 11:25:31.71581+08	2026-02-13 11:25:31.71581+08	active
869405c8-4cdf-4137-ab53-c9fd98796293	financer	$2b$12$KaYrIUU/AA0YT6BfLEaJVOgCi0.OpG/A8f5JQyjb.YpgLfD4PPPDO	financer@lanchen.com	15020302832	4a0127f2-98ae-4769-a9c1-5de3334af801	ef39a863-6ab7-4f99-bb78-236170d38117	member	2026-02-19 16:43:43.320509+08	2026-02-19 16:43:43.320509+08	\N	active
00000000-0000-0000-0000-000000000003	admin	$2a$06$8jR7WzRe5E3upJmmCtIPyOfArPX1k8140YBJ/rZIe6nr6k4hG3Tna	admin@example.com	\N	00000000-0000-0000-0000-000000000002	00000000-0000-0000-0000-000000000001	admin	2026-02-10 16:11:16.330406+08	2026-03-19 11:03:52.231239+08	2026-03-19 11:03:52.231239+08	active
\.


--
-- Name: admins_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.admins_id_seq', 1, true);


--
-- Name: admins admins_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admins
    ADD CONSTRAINT admins_pkey PRIMARY KEY (id);


--
-- Name: admins admins_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admins
    ADD CONSTRAINT admins_username_key UNIQUE (username);


--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);


--
-- Name: rule_detail bus_file_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rule_detail
    ADD CONSTRAINT bus_file_rules_pkey PRIMARY KEY (id);


--
-- Name: company company_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company
    ADD CONSTRAINT company_code_key UNIQUE (code);


--
-- Name: company company_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company
    ADD CONSTRAINT company_pkey PRIMARY KEY (id);


--
-- Name: conversations conversations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_pkey PRIMARY KEY (id);


--
-- Name: departments departments_company_id_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT departments_company_id_code_key UNIQUE (company_id, code);


--
-- Name: departments departments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT departments_pkey PRIMARY KEY (id);


--
-- Name: guest_auth_tokens guest_auth_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.guest_auth_tokens
    ADD CONSTRAINT guest_auth_tokens_pkey PRIMARY KEY (id);


--
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);


--
-- Name: reconciliation_rules reconciliation_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reconciliation_rules
    ADD CONSTRAINT reconciliation_rules_pkey PRIMARY KEY (id);


--
-- Name: reconciliation_tasks reconciliation_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reconciliation_tasks
    ADD CONSTRAINT reconciliation_tasks_pkey PRIMARY KEY (id);


--
-- Name: rule_detail rule_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rule_detail
    ADD CONSTRAINT rule_code UNIQUE (rule_code);


--
-- Name: rule_usage_logs rule_usage_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rule_usage_logs
    ADD CONSTRAINT rule_usage_logs_pkey PRIMARY KEY (id);


--
-- Name: rule_versions rule_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rule_versions
    ADD CONSTRAINT rule_versions_pkey PRIMARY KEY (id);


--
-- Name: rule_versions rule_versions_rule_id_version_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rule_versions
    ADD CONSTRAINT rule_versions_rule_id_version_key UNIQUE (rule_id, version);


--
-- Name: user_tasks user_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_tasks
    ADD CONSTRAINT user_tasks_pkey PRIMARY KEY (id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: idx_audit_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_action ON public.audit_logs USING btree (action);


--
-- Name: idx_audit_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_created ON public.audit_logs USING btree (created_at DESC);


--
-- Name: idx_audit_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_user ON public.audit_logs USING btree (user_id);


--
-- Name: idx_company_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_company_code ON public.company USING btree (code);


--
-- Name: idx_company_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_company_status ON public.company USING btree (status);


--
-- Name: idx_conversations_updated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_updated_at ON public.conversations USING btree (updated_at DESC);


--
-- Name: idx_conversations_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_user_id ON public.conversations USING btree (user_id);


--
-- Name: idx_departments_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_departments_code ON public.departments USING btree (company_id, code);


--
-- Name: idx_departments_company; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_departments_company ON public.departments USING btree (company_id);


--
-- Name: idx_departments_parent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_departments_parent ON public.departments USING btree (parent_id);


--
-- Name: idx_guest_tokens_expires; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_guest_tokens_expires ON public.guest_auth_tokens USING btree (expires_at);


--
-- Name: idx_guest_tokens_session; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_guest_tokens_session ON public.guest_auth_tokens USING btree (session_id);


--
-- Name: idx_guest_tokens_token; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_guest_tokens_token ON public.guest_auth_tokens USING btree (token);


--
-- Name: idx_messages_attachments; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_messages_attachments ON public.messages USING gin (attachments);


--
-- Name: idx_messages_conversation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_messages_conversation_id ON public.messages USING btree (conversation_id);


--
-- Name: idx_messages_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_messages_created_at ON public.messages USING btree (created_at);


--
-- Name: idx_rule_detail_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rule_detail_name ON public.rule_detail USING btree (name);


--
-- Name: idx_rule_detail_rule_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rule_detail_rule_code ON public.rule_detail USING btree (rule_code);


--
-- Name: idx_rule_detail_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rule_detail_task_id ON public.rule_detail USING btree (task_id);


--
-- Name: idx_rule_detail_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rule_detail_user_id ON public.rule_detail USING btree (user_id);


--
-- Name: idx_rule_versions_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rule_versions_created ON public.rule_versions USING btree (created_at DESC);


--
-- Name: idx_rule_versions_rule; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rule_versions_rule ON public.rule_versions USING btree (rule_id);


--
-- Name: idx_rules_company; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rules_company ON public.reconciliation_rules USING btree (company_id);


--
-- Name: idx_rules_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rules_created_by ON public.reconciliation_rules USING btree (created_by);


--
-- Name: idx_rules_department; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rules_department ON public.reconciliation_rules USING btree (department_id);


--
-- Name: idx_rules_field_mapping_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rules_field_mapping_hash ON public.reconciliation_rules USING btree (field_mapping_hash);


--
-- Name: idx_rules_key_field; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rules_key_field ON public.reconciliation_rules USING btree (key_field_role);


--
-- Name: idx_rules_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rules_status ON public.reconciliation_rules USING btree (status);


--
-- Name: idx_rules_tags; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rules_tags ON public.reconciliation_rules USING gin (tags);


--
-- Name: idx_rules_template_gin; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rules_template_gin ON public.reconciliation_rules USING gin (rule_template);


--
-- Name: idx_rules_visibility; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rules_visibility ON public.reconciliation_rules USING btree (visibility);


--
-- Name: idx_tasks_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tasks_created ON public.reconciliation_tasks USING btree (created_at DESC);


--
-- Name: idx_tasks_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tasks_created_by ON public.reconciliation_tasks USING btree (created_by);


--
-- Name: idx_tasks_result_gin; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tasks_result_gin ON public.reconciliation_tasks USING gin (result_summary);


--
-- Name: idx_tasks_rule; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tasks_rule ON public.reconciliation_tasks USING btree (rule_id);


--
-- Name: idx_tasks_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tasks_status ON public.reconciliation_tasks USING btree (status);


--
-- Name: idx_usage_logs_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_usage_logs_created ON public.rule_usage_logs USING btree (created_at DESC);


--
-- Name: idx_usage_logs_rule; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_usage_logs_rule ON public.rule_usage_logs USING btree (rule_id);


--
-- Name: idx_usage_logs_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_usage_logs_user ON public.rule_usage_logs USING btree (user_id);


--
-- Name: idx_user_tasks_task_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_tasks_task_code ON public.user_tasks USING btree (task_code);


--
-- Name: idx_user_tasks_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_tasks_user_id ON public.user_tasks USING btree (user_id);


--
-- Name: idx_users_company; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_company ON public.users USING btree (company_id);


--
-- Name: idx_users_department; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_department ON public.users USING btree (department_id);


--
-- Name: idx_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_email ON public.users USING btree (email);


--
-- Name: idx_users_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_status ON public.users USING btree (status);


--
-- Name: idx_users_username; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_username ON public.users USING btree (username);


--
-- Name: unique_rule_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX unique_rule_code ON public.rule_detail USING btree (rule_code);


--
-- Name: company update_company_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_company_updated_at BEFORE UPDATE ON public.company FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: departments update_departments_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_departments_updated_at BEFORE UPDATE ON public.departments FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: reconciliation_rules update_rules_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_rules_updated_at BEFORE UPDATE ON public.reconciliation_rules FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: reconciliation_tasks update_tasks_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_tasks_updated_at BEFORE UPDATE ON public.reconciliation_tasks FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: users update_users_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: audit_logs audit_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: conversations conversations_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: departments departments_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT departments_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;


--
-- Name: departments departments_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT departments_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.departments(id) ON DELETE SET NULL;


--
-- Name: messages messages_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: reconciliation_rules reconciliation_rules_approved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reconciliation_rules
    ADD CONSTRAINT reconciliation_rules_approved_by_fkey FOREIGN KEY (approved_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: reconciliation_rules reconciliation_rules_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reconciliation_rules
    ADD CONSTRAINT reconciliation_rules_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE SET NULL;


--
-- Name: reconciliation_rules reconciliation_rules_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reconciliation_rules
    ADD CONSTRAINT reconciliation_rules_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: reconciliation_rules reconciliation_rules_department_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reconciliation_rules
    ADD CONSTRAINT reconciliation_rules_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.departments(id) ON DELETE SET NULL;


--
-- Name: reconciliation_tasks reconciliation_tasks_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reconciliation_tasks
    ADD CONSTRAINT reconciliation_tasks_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: reconciliation_tasks reconciliation_tasks_department_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reconciliation_tasks
    ADD CONSTRAINT reconciliation_tasks_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.departments(id) ON DELETE SET NULL;


--
-- Name: reconciliation_tasks reconciliation_tasks_rule_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reconciliation_tasks
    ADD CONSTRAINT reconciliation_tasks_rule_id_fkey FOREIGN KEY (rule_id) REFERENCES public.reconciliation_rules(id) ON DELETE RESTRICT;


--
-- Name: rule_detail rule_detail_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rule_detail
    ADD CONSTRAINT rule_detail_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.user_tasks(id) ON DELETE SET NULL;


--
-- Name: rule_usage_logs rule_usage_logs_department_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rule_usage_logs
    ADD CONSTRAINT rule_usage_logs_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.departments(id) ON DELETE SET NULL;


--
-- Name: rule_usage_logs rule_usage_logs_rule_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rule_usage_logs
    ADD CONSTRAINT rule_usage_logs_rule_id_fkey FOREIGN KEY (rule_id) REFERENCES public.reconciliation_rules(id) ON DELETE CASCADE;


--
-- Name: rule_usage_logs rule_usage_logs_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rule_usage_logs
    ADD CONSTRAINT rule_usage_logs_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.reconciliation_tasks(id) ON DELETE SET NULL;


--
-- Name: rule_usage_logs rule_usage_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rule_usage_logs
    ADD CONSTRAINT rule_usage_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: rule_versions rule_versions_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rule_versions
    ADD CONSTRAINT rule_versions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: rule_versions rule_versions_rule_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rule_versions
    ADD CONSTRAINT rule_versions_rule_id_fkey FOREIGN KEY (rule_id) REFERENCES public.reconciliation_rules(id) ON DELETE CASCADE;


--
-- Name: user_tasks user_tasks_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_tasks
    ADD CONSTRAINT user_tasks_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: users users_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE SET NULL;


--
-- Name: users users_department_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.departments(id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--

