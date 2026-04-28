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

--
-- Data for Name: admins; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.admins (id, username, password, created_at) VALUES (1, 'admin', '92925488b28ab12584ac8fcaa8a27a0f497b2c62940c8f4fbc8ef19ebc87c43e', '2026-02-19 10:27:27.267257');


--
-- Data for Name: company; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.company (id, name, code, max_users, max_departments, enabled_features, created_at, updated_at, status) VALUES ('00000000-0000-0000-0000-000000000001', '示例公司', 'DEMO_COMPANY', 1000, 100, '["reconciliation", "data_prep"]', '2026-02-10 16:11:16.32517+08', '2026-02-10 16:11:16.32517+08', 'active');
INSERT INTO public.company (id, name, code, max_users, max_departments, enabled_features, created_at, updated_at, status) VALUES ('ef39a863-6ab7-4f99-bb78-236170d38117', '武汉岚晨网络科技有限公司', 'COMP_83035BAF', 100, 10, '["reconciliation", "data_prep"]', '2026-02-19 16:30:56.871353+08', '2026-02-25 10:18:15.898601+08', 'active');
INSERT INTO public.company (id, name, code, max_users, max_departments, enabled_features, created_at, updated_at, status) VALUES ('c2a4b2b8-2afd-41ae-91ab-23df1ac97fc1', '测试部', 'COMP_3BE8A888', 100, 10, '["reconciliation", "data_prep"]', '2026-03-04 15:32:19.755906+08', '2026-03-04 15:32:19.755906+08', 'active');


--
-- Data for Name: departments; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.departments (id, company_id, parent_id, name, code, description, settings, created_at, updated_at) VALUES ('00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', NULL, '财务部', 'FINANCE', '财务对账部门', '{}', '2026-02-10 16:11:16.327623+08', '2026-02-10 16:11:16.327623+08');
INSERT INTO public.departments (id, company_id, parent_id, name, code, description, settings, created_at, updated_at) VALUES ('063eae86-62ee-43f9-ac81-7776c25ecb7c', 'ef39a863-6ab7-4f99-bb78-236170d38117', NULL, '资产部', 'DEPT_3EF4E97B', NULL, '{}', '2026-02-19 16:31:29.88011+08', '2026-02-25 10:18:30.09625+08');
INSERT INTO public.departments (id, company_id, parent_id, name, code, description, settings, created_at, updated_at) VALUES ('4a0127f2-98ae-4769-a9c1-5de3334af801', 'ef39a863-6ab7-4f99-bb78-236170d38117', NULL, '核算部', 'DEPT_7CD78C2B', NULL, '{}', '2026-02-19 16:40:06.467791+08', '2026-02-25 10:18:30.09625+08');
INSERT INTO public.departments (id, company_id, parent_id, name, code, description, settings, created_at, updated_at) VALUES ('3f3cd4fd-eca3-4783-8273-cd94c284d4c7', 'c2a4b2b8-2afd-41ae-91ab-23df1ac97fc1', NULL, '测试一组', 'DEPT_E48C5851', NULL, '{}', '2026-03-04 15:32:38.377629+08', '2026-03-04 15:32:38.377629+08');


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.users (id, username, password_hash, email, phone, department_id, company_id, role, created_at, updated_at, last_login, status) VALUES ('00000000-0000-0000-0000-000000000001', 'system', '', 'system@finflux.local', NULL, NULL, NULL, 'admin', '2026-02-12 16:20:15.777487+08', '2026-02-12 16:20:15.777487+08', NULL, 'active');
INSERT INTO public.users (id, username, password_hash, email, phone, department_id, company_id, role, created_at, updated_at, last_login, status) VALUES ('3b593fbd-d0cd-48b8-99f1-fd9274f4059d', 'testuser', '$2b$12$eMoYGYTk1cBXupBiYXk5he8PG56Fyb8t2TpFCVovKcQrnWJdg0VKG', NULL, NULL, '00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', 'member', '2026-02-12 17:08:15.240684+08', '2026-02-12 17:08:15.240684+08', NULL, 'active');
INSERT INTO public.users (id, username, password_hash, email, phone, department_id, company_id, role, created_at, updated_at, last_login, status) VALUES ('8416371f-95f9-4454-b516-a20d434ca79c', 'testuser_828796', '$2b$12$aortAUQny0vsJFcFfFkJ4edAzrphidZX1pRDsb6y3D.CD1AeD9B.q', NULL, NULL, NULL, NULL, 'member', '2026-02-13 11:20:30.039084+08', '2026-02-13 11:24:06.561373+08', '2026-02-13 11:24:06.561373+08', 'active');
INSERT INTO public.users (id, username, password_hash, email, phone, department_id, company_id, role, created_at, updated_at, last_login, status) VALUES ('85a817b0-9fdb-4281-89e1-220ee539373c', 'testuser_1770953046_7807', '$2b$12$avN29IEdT0T1c.16NOFkGOC2XJpew5ziRJQxVBja7jjMUdlVWDZda', 'testuser_1770953046_7807@test.com', '13800000000', NULL, NULL, 'member', '2026-02-13 11:24:06.954359+08', '2026-02-13 11:24:06.954359+08', NULL, 'active');
INSERT INTO public.users (id, username, password_hash, email, phone, department_id, company_id, role, created_at, updated_at, last_login, status) VALUES ('dbcc40a1-1a3f-4da9-a726-76e3b1e29e0b', 'user_1770953127_9395', '$2b$12$MF1isplyh9RcLJAt4L8tzOw/Vgjpyk1dJkZyekDhej.Ssafd9CVH.', 'user_1770953127_9395@example.com', '13800000000', NULL, NULL, 'member', '2026-02-13 11:25:28.940015+08', '2026-02-13 11:25:31.71581+08', '2026-02-13 11:25:31.71581+08', 'active');
INSERT INTO public.users (id, username, password_hash, email, phone, department_id, company_id, role, created_at, updated_at, last_login, status) VALUES ('869405c8-4cdf-4137-ab53-c9fd98796293', 'financer', '$2b$12$KaYrIUU/AA0YT6BfLEaJVOgCi0.OpG/A8f5JQyjb.YpgLfD4PPPDO', 'financer@lanchen.com', '15020302832', '4a0127f2-98ae-4769-a9c1-5de3334af801', 'ef39a863-6ab7-4f99-bb78-236170d38117', 'member', '2026-02-19 16:43:43.320509+08', '2026-02-19 16:43:43.320509+08', NULL, 'active');
INSERT INTO public.users (id, username, password_hash, email, phone, department_id, company_id, role, created_at, updated_at, last_login, status) VALUES ('00000000-0000-0000-0000-000000000003', 'admin', '$2a$06$8jR7WzRe5E3upJmmCtIPyOfArPX1k8140YBJ/rZIe6nr6k4hG3Tna', 'admin@example.com', NULL, '00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', 'admin', '2026-02-10 16:11:16.330406+08', '2026-03-27 17:54:56.561397+08', '2026-03-27 17:54:56.561397+08', 'active');


--
-- Data for Name: conversations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.conversations (id, user_id, title, created_at, updated_at, status) VALUES ('d9d4079d-ce32-43d6-b3ee-41e6e3a8a548', '00000000-0000-0000-0000-000000000003', '我的规则列表', '2026-03-22 15:37:09.271053', '2026-03-27 18:39:41.260096', 'active');


--
-- Data for Name: messages; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('3da80c1b-0f97-458f-a4e3-fc2a7e9aae5c', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '📋 **我的对账规则列表**

• **南京飞翰123**
• **腾讯异业123**
• **西福123**
• **喜马**
• **西福商管欧飞**
• **腾讯异业**', '{}', '[]', '2026-03-22 15:37:09.327404');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('fed408c3-2693-4306-941c-830c40629335', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '🚀 对账任务已启动

- 规则：腾讯异业
- 2025-12-01~2025-12-01对账流水.csv
- ads_finance_d_inc_channel_details_20260105133821735_0.csv

⏳ 正在执行对账，预计需要 10-60 秒

进度：开始加载数据', '{}', '[]', '2026-03-22 15:38:31.552448');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('72c473fb-a853-44a4-bdca-ed76eeaae340', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '📊 **开始数据整理任务**

已选择规则：**逾期统计数据整理**

请先上传需要整理的数据文件（Excel 或 CSV 格式）。', '{}', '[]', '2026-03-24 11:24:31.331693');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('eca4d4ae-cad2-4a20-a23a-3e8c08b5a247', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '📊 **开始数据整理任务**

已选择规则：**逾期统计数据整理**

📋 **处理流程**（共4个步骤）：

1. **读取规则** — 从数据库加载数据整理规则定义
2. **文件校验** — 校验上传文件格式、列名是否符合规则要求
3. **执行整理** — 按照规则执行数据转换和整理
4. **结果展示** — 展示处理结果和生成的执行计划

请上传需要整理的数据文件，系统将自动按上述流程处理。', '{}', '[]', '2026-03-24 11:32:14.795231');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('6d63ac9a-01e8-4e5e-94a9-c99929ab6873', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '你好，admin！我是 Tally，专业的智能财务助手。

我可以帮助您完成财务数据整理和对账工作。选择任务类型（数据整理/数据对账）和数据规则即可开始处理。', '{}', '[]', '2026-03-24 12:23:52.801214');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('685a6831-3e09-48e3-bb5e-bc0ea41b456e', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '已读取规则「逾期统计数据整理」，开始准备文件校验。', '{}', '[]', '2026-03-24 12:24:05.093753');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('1e9ca583-d54b-4afd-b650-9c45f3ff8e03', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '数据整理任务已完成，结果文件如下。

规则：逾期统计数据整理

**结果文件：**
- **[金蝶期末余额-检核](http://localhost:3335/output/proc/overdue_statistics/金蝶期末余额-检核_20260324_140424_082.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzMzIyNDgsImV4cCI6MTc3NDQxODY0OCwianRpIjoiZGVjMWE5MDQtY2E4Zi00ZjUwLTgxOTAtZDEzYzEyZDBjZjM1In0.sdzDXPJcbgbbmTLL4QFfCRbQ8NVvpsXqR9LScfrIm4Q)** — 2行
- **[统计使用-7月余额](http://localhost:3335/output/proc/overdue_statistics/统计使用-7月余额_20260324_140424_082.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzMzIyNDgsImV4cCI6MTc3NDQxODY0OCwianRpIjoiZGVjMWE5MDQtY2E4Zi00ZjUwLTgxOTAtZDEzYzEyZDBjZjM1In0.sdzDXPJcbgbbmTLL4QFfCRbQ8NVvpsXqR9LScfrIm4Q)** — 2行
- **[统计使用-借方](http://localhost:3335/output/proc/overdue_statistics/统计使用-借方_20260324_140424_082.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzMzIyNDgsImV4cCI6MTc3NDQxODY0OCwianRpIjoiZGVjMWE5MDQtY2E4Zi00ZjUwLTgxOTAtZDEzYzEyZDBjZjM1In0.sdzDXPJcbgbbmTLL4QFfCRbQ8NVvpsXqR9LScfrIm4Q)** — 4行
- **[统计使用-贷方](http://localhost:3335/output/proc/overdue_statistics/统计使用-贷方_20260324_140424_082.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzMzIyNDgsImV4cCI6MTc3NDQxODY0OCwianRpIjoiZGVjMWE5MDQtY2E4Zi00ZjUwLTgxOTAtZDEzYzEyZDBjZjM1In0.sdzDXPJcbgbbmTLL4QFfCRbQ8NVvpsXqR9LScfrIm4Q)** — 4行
- **[统计合并](http://localhost:3335/output/proc/overdue_statistics/统计合并_20260324_140424_082.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzMzIyNDgsImV4cCI6MTc3NDQxODY0OCwianRpIjoiZGVjMWE5MDQtY2E4Zi00ZjUwLTgxOTAtZDEzYzEyZDBjZjM1In0.sdzDXPJcbgbbmTLL4QFfCRbQ8NVvpsXqR9LScfrIm4Q)** — 2行
- **[逾期统计](http://localhost:3335/output/proc/overdue_statistics/逾期统计_20260324_140424_082.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzMzIyNDgsImV4cCI6MTc3NDQxODY0OCwianRpIjoiZGVjMWE5MDQtY2E4Zi00ZjUwLTgxOTAtZDEzYzEyZDBjZjM1In0.sdzDXPJcbgbbmTLL4QFfCRbQ8NVvpsXqR9LScfrIm4Q)** — 2行

如需重新处理或使用其他规则，请告知。', '{}', '[]', '2026-03-24 14:04:24.645933');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('5d00c843-3c9c-4ac5-ab75-50a6ac47c66b', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '📊 **开始对账执行任务**

已选择规则：**喜马-26合单与官网数据核对**
已上传文件：2 个

正在校验文件并加载规则...', '{}', '[]', '2026-03-24 14:05:09.502719');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('b8ec8a3a-5e69-454a-9599-65c5c8d73e31', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '以下是详细对账结果。

**规则：** 喜马-26合单与官网数据核对

---

📁 **文件**: `合单.xlsx` ↔ `官网.xlsx`



📊 **结果统计**:

| 类型 | 数量 | 说明 |
|------|------|------|
| ✅ 完全匹配 | 6484 | 数据完全一致 |
| ⚠️ 匹配有差异 | 0 | sup订单号/第三方订单号匹配但发生减不同 |
| 📤 合单.xlsx独有 | 0 | 仅在合单.xlsx中存在 |
| 📥 官网.xlsx独有 | 10 | 仅在官网.xlsx中存在 |
| **合计** | **6494** | 总记录数 |

📄 **[查看详细差异报告](http://localhost:3335/output/recon/喜马-26合单与官网数据核对_核对结果_20260324_140525.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzMzIyNDgsImV4cCI6MTc3NDQxODY0OCwianRpIjoiZGVjMWE5MDQtY2E4Zi00ZjUwLTgxOTAtZDEzYzEyZDBjZjM1In0.sdzDXPJcbgbbmTLL4QFfCRbQ8NVvpsXqR9LScfrIm4Q)**

---


如需进一步分析或有疑问，请告知。', '{}', '[]', '2026-03-24 14:05:26.599544');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('99bf74f2-d121-4c19-9e3b-61d8a12243bd', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '已读取规则「喜马-26合单与官网数据核对」，开始准备文件校验。', '{}', '[]', '2026-03-24 17:47:09.294256');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('e7627516-cebc-470d-8d9a-7b6b65340739', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '已读取规则「逾期统计数据整理」，开始准备文件校验。', '{}', '[]', '2026-03-24 17:47:33.596899');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('293f51b3-8af2-4104-9fe4-40f73485ae60', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'user', '已上传 2 个文件，请处理。', '{}', '[]', '2026-03-25 12:33:50.16365');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('35f86089-8a92-4532-8f7a-e39486734f69', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '已读取规则「喜马-26合单与官网数据核对」，开始准备文件校验。', '{}', '[]', '2026-03-25 12:33:50.669632');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('a8458541-8dca-49ce-8ddc-98f335a6f6a1', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '数据整理任务已完成，结果文件如下。

规则：逾期统计数据整理

**结果文件：**
- **[金蝶期末余额-检核](http://localhost:3335/output/proc/overdue_statistics/金蝶期末余额-检核_20260325_123419_722.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ0MTMyMDUsImV4cCI6MTc3NDQ5OTYwNSwianRpIjoiOWZjYTI5NjctNDE0Zi00NTUxLWFhNjUtOWM0ZDNkOTMyZDI0In0.MmpM8gFVq4sMc7of_qtUB5iAnPAB4FLTUB9nbK9HCwM)** — 2行
- **[统计使用-7月余额](http://localhost:3335/output/proc/overdue_statistics/统计使用-7月余额_20260325_123419_722.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ0MTMyMDUsImV4cCI6MTc3NDQ5OTYwNSwianRpIjoiOWZjYTI5NjctNDE0Zi00NTUxLWFhNjUtOWM0ZDNkOTMyZDI0In0.MmpM8gFVq4sMc7of_qtUB5iAnPAB4FLTUB9nbK9HCwM)** — 2行
- **[统计使用-借方](http://localhost:3335/output/proc/overdue_statistics/统计使用-借方_20260325_123419_722.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ0MTMyMDUsImV4cCI6MTc3NDQ5OTYwNSwianRpIjoiOWZjYTI5NjctNDE0Zi00NTUxLWFhNjUtOWM0ZDNkOTMyZDI0In0.MmpM8gFVq4sMc7of_qtUB5iAnPAB4FLTUB9nbK9HCwM)** — 4行
- **[统计使用-贷方](http://localhost:3335/output/proc/overdue_statistics/统计使用-贷方_20260325_123419_722.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ0MTMyMDUsImV4cCI6MTc3NDQ5OTYwNSwianRpIjoiOWZjYTI5NjctNDE0Zi00NTUxLWFhNjUtOWM0ZDNkOTMyZDI0In0.MmpM8gFVq4sMc7of_qtUB5iAnPAB4FLTUB9nbK9HCwM)** — 4行
- **[统计合并](http://localhost:3335/output/proc/overdue_statistics/统计合并_20260325_123419_722.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ0MTMyMDUsImV4cCI6MTc3NDQ5OTYwNSwianRpIjoiOWZjYTI5NjctNDE0Zi00NTUxLWFhNjUtOWM0ZDNkOTMyZDI0In0.MmpM8gFVq4sMc7of_qtUB5iAnPAB4FLTUB9nbK9HCwM)** — 2行
- **[逾期统计](http://localhost:3335/output/proc/overdue_statistics/逾期统计_20260325_123419_722.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ0MTMyMDUsImV4cCI6MTc3NDQ5OTYwNSwianRpIjoiOWZjYTI5NjctNDE0Zi00NTUxLWFhNjUtOWM0ZDNkOTMyZDI0In0.MmpM8gFVq4sMc7of_qtUB5iAnPAB4FLTUB9nbK9HCwM)** — 2行

如需重新处理或使用其他规则，请告知。', '{}', '[]', '2026-03-25 12:34:20.429962');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('c2594807-2d54-4b69-baec-2839d137ce7d', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '📊 **开始数据整理任务**

已选择规则：**逾期统计数据整理**
已上传文件：6 个

📋 **处理流程**（共4个步骤）：

1. **读取规则** — 从数据库加载数据整理规则定义
2. **文件校验** — 校验上传文件格式、列名是否符合规则要求
3. **执行整理** — 按照规则执行数据转换和整理
4. **结果展示** — 展示处理结果和生成的执行计划

正在校验文件并加载规则...', '{}', '[]', '2026-03-25 19:01:58.661627');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('c788e057-0430-4ff7-a694-b8cc7f7461d0', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '执行整理已完成。

- 规则：逾期统计数据整理
- 生成目标文件：6 个
- 合并文件：0 个

正在整理最终结果，请稍候。', '{}', '[]', '2026-03-25 19:12:39.660096');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('22e549a8-f312-4cf4-8a49-8de0296b62ff', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '执行整理已完成。

- 规则：逾期统计数据整理
- 生成目标文件：6 个
- 合并文件：0 个

正在整理最终结果，请稍候。', '{}', '[]', '2026-03-26 10:27:10.447798');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('e8ec67c4-7f31-40e5-ba5c-6bb1d07784f3', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '文件校验通过。

**文件识别结果：**
✅ **已匹配：**
- **3、金蝶期末余额-检核.xlsx** → 金蝶期末余额-检核
- **3.1、科目期初.xlsx** → 科目期初
- **3.2、借方-计提单明细.xlsx** → 借方-计提单明细
- **3.3、贷方-收款单明细.xlsx** → 贷方-收款单明细
- **3.4、调整明细.xlsx** → 调整明细
- **中心匹配.xlsx** → 中心匹配', '{}', '[]', '2026-03-26 10:27:10.535405');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('aa737d69-a554-47fb-9497-8a2d250832a1', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'user', '已上传 6 个文件，请处理。', '{}', '[{"name": null, "path": "/uploads/2026/3/27/贷方-收款单明细_180411.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/27/调整明细_180411.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/27/借方-计提单明细_180411.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/27/金蝶期末余额-检核_180411.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/27/科目期初_180411.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/27/中心匹配_180411.xlsx", "size": 0}]', '2026-03-27 18:04:13.123547');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('9d89cbdd-7ccc-454f-9ed9-7e030eee3ff9', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'user', '使用腾讯异业', '{}', '[]', '2026-03-22 15:37:21.797786');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('2f9c25df-52dd-42e2-8926-0dc21dd8c636', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '好的，将使用规则「腾讯异业」进行对账。

✨ 请上传对账文件（文件1和文件2各一个）', '{}', '[]', '2026-03-22 15:38:31.583213');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('423f05e1-871d-4ff7-84a2-87042f568a45', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'user', '已上传 5 个文件，请处理。', '{}', '[{"name": null, "path": "/uploads/2026/3/24/贷方-收款单明细_112559.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/24/调整明细_112559.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/24/借方-计提单明细_112559.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/24/金蝶期末余额-检核_112559.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/24/科目期初_112559.xlsx", "size": 0}]', '2026-03-24 11:25:59.851142');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('8b666647-47be-402c-b09e-95aa2f9a517f', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '✅ 读取规则

✅ 文件校验

✅ 执行整理

✅ 结果展示

数据整理任务已完成。

规则：逾期统计数据整理

已生成 6 个文件：
- **[金蝶期末余额-检核](http://localhost:3335/output/proc/overdue_statistics/金蝶期末余额-检核_20260324_113214_519.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzMjMxMjMsImV4cCI6MTc3NDQwOTUyMywianRpIjoiOGJmZDhkMzMtYWU4NS00NTgwLTg4ODItNmQzMTNhZDIyMzc3In0.5PC2tCKSIO0nC4Hw9z6KTAFZZCtgDhCc7yypJlm9Xfs)** — 2行
- **[统计使用-7月余额](http://localhost:3335/output/proc/overdue_statistics/统计使用-7月余额_20260324_113214_519.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzMjMxMjMsImV4cCI6MTc3NDQwOTUyMywianRpIjoiOGJmZDhkMzMtYWU4NS00NTgwLTg4ODItNmQzMTNhZDIyMzc3In0.5PC2tCKSIO0nC4Hw9z6KTAFZZCtgDhCc7yypJlm9Xfs)** — 2行
- **[统计使用-借方](http://localhost:3335/output/proc/overdue_statistics/统计使用-借方_20260324_113214_519.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzMjMxMjMsImV4cCI6MTc3NDQwOTUyMywianRpIjoiOGJmZDhkMzMtYWU4NS00NTgwLTg4ODItNmQzMTNhZDIyMzc3In0.5PC2tCKSIO0nC4Hw9z6KTAFZZCtgDhCc7yypJlm9Xfs)** — 4行
- **[统计使用-贷方](http://localhost:3335/output/proc/overdue_statistics/统计使用-贷方_20260324_113214_519.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzMjMxMjMsImV4cCI6MTc3NDQwOTUyMywianRpIjoiOGJmZDhkMzMtYWU4NS00NTgwLTg4ODItNmQzMTNhZDIyMzc3In0.5PC2tCKSIO0nC4Hw9z6KTAFZZCtgDhCc7yypJlm9Xfs)** — 4行
- **[统计合并](http://localhost:3335/output/proc/overdue_statistics/统计合并_20260324_113214_519.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzMjMxMjMsImV4cCI6MTc3NDQwOTUyMywianRpIjoiOGJmZDhkMzMtYWU4NS00NTgwLTg4ODItNmQzMTNhZDIyMzc3In0.5PC2tCKSIO0nC4Hw9z6KTAFZZCtgDhCc7yypJlm9Xfs)** — 2行
- **[逾期统计](http://localhost:3335/output/proc/overdue_statistics/逾期统计_20260324_113214_519.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzMjMxMjMsImV4cCI6MTc3NDQwOTUyMywianRpIjoiOGJmZDhkMzMtYWU4NS00NTgwLTg4ODItNmQzMTNhZDIyMzc3In0.5PC2tCKSIO0nC4Hw9z6KTAFZZCtgDhCc7yypJlm9Xfs)** — 2行

如需重新处理或使用其他规则，请告知。', '{}', '[]', '2026-03-24 11:32:14.87669');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('324a90dc-b179-41a5-b2ba-ab03851723a3', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'user', '已上传 5 个文件，请处理。', '{}', '[{"name": null, "path": "/uploads/2026/3/24/贷方-收款单明细_122402.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/24/调整明细_122402.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/24/借方-计提单明细_122402.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/24/金蝶期末余额-检核_122403.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/24/科目期初_122403.xlsx", "size": 0}]', '2026-03-24 12:24:04.592368');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('b34a8fad-3e1d-4d9b-8ba9-5299cec08af7', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '文件校验通过。

**文件识别结果：**
✅ **已匹配：**
- **贷方-收款单明细.xlsx** → 贷方-收款单明细
- **调整明细.xlsx** → 调整明细
- **借方-计提单明细.xlsx** → 借方-计提单明细
- **金蝶期末余额-检核.xlsx** → 金蝶期末余额-检核
- **科目期初.xlsx** → 科目期初', '{}', '[]', '2026-03-24 12:24:05.165614');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('f97470fc-9ba7-46b2-afcd-51c4262e025b', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '文件校验通过。

**文件识别结果：**
✅ **已匹配：**
- **贷方-收款单明细.xlsx** → 贷方-收款单明细
- **调整明细.xlsx** → 调整明细
- **借方-计提单明细.xlsx** → 借方-计提单明细
- **金蝶期末余额-检核.xlsx** → 金蝶期末余额-检核
- **科目期初.xlsx** → 科目期初', '{}', '[]', '2026-03-24 14:04:24.740443');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('b527cb94-1bb4-45d3-a133-8a61d2875807', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '已读取规则「喜马-26合单与官网数据核对」，开始准备文件校验。', '{}', '[]', '2026-03-24 14:05:09.593807');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('15d1e4b9-abc7-4f93-90ed-6e5d3cfab36b', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '已读取规则「喜马-26合单与官网数据核对」，开始准备文件校验。', '{}', '[]', '2026-03-24 14:05:26.687287');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('5a9bc174-7d00-4f10-afb9-1afaf46f0c11', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '文件校验通过。

**文件识别结果：**
✅ **已匹配：**
- **官网.xlsx** → 喜马官网表
- **合单.xlsx** → 喜马合单表', '{}', '[]', '2026-03-24 17:47:09.384292');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('fd9e79cb-56ef-4141-9352-8b4b28e84338', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '📊 **开始数据整理任务**

已选择规则：**逾期统计数据整理**
已上传文件：5 个

📋 **处理流程**（共4个步骤）：

1. **读取规则** — 从数据库加载数据整理规则定义
2. **文件校验** — 校验上传文件格式、列名是否符合规则要求
3. **执行整理** — 按照规则执行数据转换和整理
4. **结果展示** — 展示处理结果和生成的执行计划

正在校验文件并加载规则...', '{}', '[]', '2026-03-24 17:47:33.707345');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('a45ec2ea-4821-490b-92cf-5faabfe0eecc', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '以下是详细对账结果。

**规则：** 喜马-26合单与官网数据核对

---

📁 **文件**: `合单.xlsx` ↔ `官网.xlsx`



📊 **结果统计**:

| 类型 | 数量 | 说明 |
|------|------|------|
| ✅ 完全匹配 | 6484 | 数据完全一致 |
| ⚠️ 匹配有差异 | 0 | sup订单号/第三方订单号匹配但发生减不同 |
| 📤 合单.xlsx独有 | 0 | 仅在合单.xlsx中存在 |
| 📥 官网.xlsx独有 | 10 | 仅在官网.xlsx中存在 |
| **合计** | **6494** | 总记录数 |

📄 **[查看详细差异报告](http://localhost:3335/output/recon/喜马-26合单与官网数据核对_核对结果_20260325_123349.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ0MTMyMDUsImV4cCI6MTc3NDQ5OTYwNSwianRpIjoiOWZjYTI5NjctNDE0Zi00NTUxLWFhNjUtOWM0ZDNkOTMyZDI0In0.MmpM8gFVq4sMc7of_qtUB5iAnPAB4FLTUB9nbK9HCwM)**

---


如需进一步分析或有疑问，请告知。', '{}', '[]', '2026-03-25 12:33:50.264232');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('3ba25520-aaf5-45b7-b7c0-a50ccb5c5bf6', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'user', '已上传 5 个文件，请处理。', '{}', '[{"name": null, "path": "/uploads/2026/3/25/贷方-收款单明细_123418.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/25/调整明细_123418.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/25/借方-计提单明细_123418.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/25/金蝶期末余额-检核_123418.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/25/科目期初_123418.xlsx", "size": 0}]', '2026-03-25 12:34:19.909039');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('bde72100-9640-471a-ab25-4a41a1c2835f', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '已读取规则「逾期统计数据整理」，开始准备文件校验。', '{}', '[]', '2026-03-25 12:34:20.525772');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('35a668ce-715a-4773-bfe1-3e62806e10b2', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '数据整理任务执行失败。

**规则：** 逾期统计数据整理
**错误信息：** 等待 MCP 响应超时

请检查上传文件是否符合规则要求，或联系管理员排查问题。', '{}', '[]', '2026-03-25 19:01:58.750534');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('4c9968ad-e4ae-43c1-ac23-1f7480e1e879', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '数据整理任务已完成，结果文件如下。

规则：逾期统计数据整理

**结果文件：**
- **[金蝶期末余额-检核](http://localhost:3335/output/proc/overdue_statistics/金蝶期末余额-检核_20260325_191238_158.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ0MTMyMDUsImV4cCI6MTc3NDQ5OTYwNSwianRpIjoiOWZjYTI5NjctNDE0Zi00NTUxLWFhNjUtOWM0ZDNkOTMyZDI0In0.MmpM8gFVq4sMc7of_qtUB5iAnPAB4FLTUB9nbK9HCwM)** — 169行
- **[统计使用-7月余额](http://localhost:3335/output/proc/overdue_statistics/统计使用-7月余额_20260325_191238_158.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ0MTMyMDUsImV4cCI6MTc3NDQ5OTYwNSwianRpIjoiOWZjYTI5NjctNDE0Zi00NTUxLWFhNjUtOWM0ZDNkOTMyZDI0In0.MmpM8gFVq4sMc7of_qtUB5iAnPAB4FLTUB9nbK9HCwM)** — 99行
- **[统计使用-借方](http://localhost:3335/output/proc/overdue_statistics/统计使用-借方_20260325_191238_158.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ0MTMyMDUsImV4cCI6MTc3NDQ5OTYwNSwianRpIjoiOWZjYTI5NjctNDE0Zi00NTUxLWFhNjUtOWM0ZDNkOTMyZDI0In0.MmpM8gFVq4sMc7of_qtUB5iAnPAB4FLTUB9nbK9HCwM)** — 996行
- **[统计使用-贷方](http://localhost:3335/output/proc/overdue_statistics/统计使用-贷方_20260325_191238_158.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ0MTMyMDUsImV4cCI6MTc3NDQ5OTYwNSwianRpIjoiOWZjYTI5NjctNDE0Zi00NTUxLWFhNjUtOWM0ZDNkOTMyZDI0In0.MmpM8gFVq4sMc7of_qtUB5iAnPAB4FLTUB9nbK9HCwM)** — 296行
- **[统计合并](http://localhost:3335/output/proc/overdue_statistics/统计合并_20260325_191238_158.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ0MTMyMDUsImV4cCI6MTc3NDQ5OTYwNSwianRpIjoiOWZjYTI5NjctNDE0Zi00NTUxLWFhNjUtOWM0ZDNkOTMyZDI0In0.MmpM8gFVq4sMc7of_qtUB5iAnPAB4FLTUB9nbK9HCwM)** — 274行
- **[逾期统计](http://localhost:3335/output/proc/overdue_statistics/逾期统计_20260325_191238_158.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ0MTMyMDUsImV4cCI6MTc3NDQ5OTYwNSwianRpIjoiOWZjYTI5NjctNDE0Zi00NTUxLWFhNjUtOWM0ZDNkOTMyZDI0In0.MmpM8gFVq4sMc7of_qtUB5iAnPAB4FLTUB9nbK9HCwM)** — 116行

如需重新处理或使用其他规则，请告知。', '{}', '[]', '2026-03-25 19:12:39.796544');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('9e6d3bcf-5e13-4030-a0d0-e2948626f1a9', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '已读取规则「逾期统计数据整理」，开始准备文件校验。', '{}', '[]', '2026-03-27 18:04:13.500743');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('c7d17fae-4083-4610-af10-2622d151ab08', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '已读取规则「逾期统计数据整理」，开始准备文件校验。', '{}', '[]', '2026-03-27 18:17:30.020007');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('bd7e51c4-5098-46e5-992f-c3b5dc157e1c', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '好的，将使用规则「腾讯异业」进行对账。

✨ 请上传对账文件（文件1和文件2各一个）', '{}', '[]', '2026-03-22 15:37:21.828628');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('a8109057-0a37-478d-b1f8-4407003eb849', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'user', '你好', '{}', '[]', '2026-03-23 17:51:52.058052');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('a6ca2aa2-00f8-4983-ac6a-27612e8aca57', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '未找到规则编码为「verif_recog」的规则。
请确认规则编码是否正确，或联系管理员获取可用的规则列表。', '{}', '[]', '2026-03-24 11:25:59.951748');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('c2c19a98-51b9-4fd3-ae6a-a4cfd0fd009c', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '✅ 读取规则

✅ 文件校验

✅ 执行整理

⏳ 正在进行 **结果展示** 的工作...', '{}', '[]', '2026-03-24 11:32:15.000615');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('f9d9c8e0-85f7-463d-af63-e12d7d064e74', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '📊 **开始数据整理任务**

已选择规则：**逾期统计数据整理**
已上传文件：5 个

📋 **处理流程**（共4个步骤）：

1. **读取规则** — 从数据库加载数据整理规则定义
2. **文件校验** — 校验上传文件格式、列名是否符合规则要求
3. **执行整理** — 按照规则执行数据转换和整理
4. **结果展示** — 展示处理结果和生成的执行计划

正在校验文件并加载规则...', '{}', '[]', '2026-03-24 12:24:04.712174');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('0948ee2f-776f-4c45-8509-1c9771508ec7', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'user', '已上传 5 个文件，请处理。', '{}', '[{"name": null, "path": "/uploads/2026/3/24/贷方-收款单明细_140422.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/24/调整明细_140422.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/24/借方-计提单明细_140422.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/24/金蝶期末余额-检核_140422.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/24/科目期初_140422.xlsx", "size": 0}]', '2026-03-24 14:04:24.250779');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('c79d4698-e496-45e2-a553-db13b23f0ee5', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '📊 **开始数据整理任务**

已选择规则：**逾期统计数据整理**
已上传文件：5 个

📋 **处理流程**（共4个步骤）：

1. **读取规则** — 从数据库加载数据整理规则定义
2. **文件校验** — 校验上传文件格式、列名是否符合规则要求
3. **执行整理** — 按照规则执行数据转换和整理
4. **结果展示** — 展示处理结果和生成的执行计划

正在校验文件并加载规则...', '{}', '[]', '2026-03-24 14:04:24.812789');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('b871d469-2abf-4f6e-87b0-fc5fd29ac6a1', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'user', '已上传 2 个文件，请处理。', '{}', '[]', '2026-03-24 14:05:26.30917');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('70ac83e2-3bb4-45e9-8b8f-3fd99a597069', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '文件校验通过。

**文件识别结果：**
✅ **已匹配：**
- **官网.xlsx** → 喜马官网表
- **合单.xlsx** → 喜马合单表', '{}', '[]', '2026-03-24 14:05:26.769606');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('992327f0-26cf-4e5d-96bb-d7b8c8474f0c', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '对账执行已完成：共处理 6494 条，匹配 6484 条，异常 10 条。

异常分布：
- 目标文件独有: 10 条

正在生成详细结果，请稍候。', '{}', '[]', '2026-03-24 17:47:09.478111');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('2ddfa7e1-29f5-48aa-9cb9-085e762bb091', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '数据整理任务已完成，结果文件如下。

规则：逾期统计数据整理

**结果文件：**
- **[金蝶期末余额-检核](http://localhost:3335/output/proc/overdue_statistics/金蝶期末余额-检核_20260324_174733_351.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzNDU2MDYsImV4cCI6MTc3NDQzMjAwNiwianRpIjoiZWMwY2IwYjktYTYyMC00ZDYwLWJkNjktZWZmZjkzYTE3OTM5In0.xvk5LZ8OHUdCSXdToeOao-jpBnc6SKgC6-sbeuRK6GA)** — 2行
- **[统计使用-7月余额](http://localhost:3335/output/proc/overdue_statistics/统计使用-7月余额_20260324_174733_351.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzNDU2MDYsImV4cCI6MTc3NDQzMjAwNiwianRpIjoiZWMwY2IwYjktYTYyMC00ZDYwLWJkNjktZWZmZjkzYTE3OTM5In0.xvk5LZ8OHUdCSXdToeOao-jpBnc6SKgC6-sbeuRK6GA)** — 2行
- **[统计使用-借方](http://localhost:3335/output/proc/overdue_statistics/统计使用-借方_20260324_174733_351.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzNDU2MDYsImV4cCI6MTc3NDQzMjAwNiwianRpIjoiZWMwY2IwYjktYTYyMC00ZDYwLWJkNjktZWZmZjkzYTE3OTM5In0.xvk5LZ8OHUdCSXdToeOao-jpBnc6SKgC6-sbeuRK6GA)** — 4行
- **[统计使用-贷方](http://localhost:3335/output/proc/overdue_statistics/统计使用-贷方_20260324_174733_351.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzNDU2MDYsImV4cCI6MTc3NDQzMjAwNiwianRpIjoiZWMwY2IwYjktYTYyMC00ZDYwLWJkNjktZWZmZjkzYTE3OTM5In0.xvk5LZ8OHUdCSXdToeOao-jpBnc6SKgC6-sbeuRK6GA)** — 4行
- **[统计合并](http://localhost:3335/output/proc/overdue_statistics/统计合并_20260324_174733_351.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzNDU2MDYsImV4cCI6MTc3NDQzMjAwNiwianRpIjoiZWMwY2IwYjktYTYyMC00ZDYwLWJkNjktZWZmZjkzYTE3OTM5In0.xvk5LZ8OHUdCSXdToeOao-jpBnc6SKgC6-sbeuRK6GA)** — 2行
- **[逾期统计](http://localhost:3335/output/proc/overdue_statistics/逾期统计_20260324_174733_351.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzNDU2MDYsImV4cCI6MTc3NDQzMjAwNiwianRpIjoiZWMwY2IwYjktYTYyMC00ZDYwLWJkNjktZWZmZjkzYTE3OTM5In0.xvk5LZ8OHUdCSXdToeOao-jpBnc6SKgC6-sbeuRK6GA)** — 2行

如需重新处理或使用其他规则，请告知。', '{}', '[]', '2026-03-24 17:47:33.944135');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('f33e2f74-d50e-4572-a292-aa9991a5d375', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '对账执行已完成：共处理 6494 条，匹配 6484 条，异常 10 条。

异常分布：
- 目标文件独有: 10 条

正在生成详细结果，请稍候。', '{}', '[]', '2026-03-25 12:33:50.357254');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('6599e52e-2760-416d-971f-60d3f6d6d6bd', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '📊 **开始数据整理任务**

已选择规则：**逾期统计数据整理**
已上传文件：5 个

📋 **处理流程**（共4个步骤）：

1. **读取规则** — 从数据库加载数据整理规则定义
2. **文件校验** — 校验上传文件格式、列名是否符合规则要求
3. **执行整理** — 按照规则执行数据转换和整理
4. **结果展示** — 展示处理结果和生成的执行计划

正在校验文件并加载规则...', '{}', '[]', '2026-03-25 12:34:20.015491');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('cc0b3562-9f68-4524-9012-f0a78a2f8009', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'user', '已上传 6 个文件，请处理。', '{}', '[{"name": null, "path": "/uploads/2026/3/25/3、金蝶期末余额-检核_190053.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/25/3.1、科目期初_190054.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/25/3.2、借方-计提单明细_190054.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/25/3.3、贷方-收款单明细_190054.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/25/3.4、调整明细_190054.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/25/中心匹配_190054.xlsx", "size": 0}]', '2026-03-25 19:01:58.35414');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('69d9e2e7-350d-489f-8223-82c111bde417', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '已读取规则「逾期统计数据整理」，开始准备文件校验。', '{}', '[]', '2026-03-25 19:01:58.836545');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('d0eb072b-7e44-467c-81f9-ad0bffdebbb6', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '文件校验通过。

**文件识别结果：**
✅ **已匹配：**
- **3、金蝶期末余额-检核.xlsx** → 金蝶期末余额-检核
- **3.1、科目期初.xlsx** → 科目期初
- **3.2、借方-计提单明细.xlsx** → 借方-计提单明细
- **3.3、贷方-收款单明细.xlsx** → 贷方-收款单明细
- **3.4、调整明细.xlsx** → 调整明细
- **中心匹配.xlsx** → 中心匹配', '{}', '[]', '2026-03-25 19:12:39.921809');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('60405329-c4aa-4771-9f5a-09001ca9275c', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '数据整理任务已完成，结果文件如下。

规则：逾期统计数据整理

**结果文件：**
- **[金蝶期末余额-检核](http://localhost:3335/output/proc/overdue_statistics/金蝶期末余额-检核_20260326_102708_777.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ0MTMyMDUsImV4cCI6MTc3NDQ5OTYwNSwianRpIjoiOWZjYTI5NjctNDE0Zi00NTUxLWFhNjUtOWM0ZDNkOTMyZDI0In0.MmpM8gFVq4sMc7of_qtUB5iAnPAB4FLTUB9nbK9HCwM)** — 169行
- **[统计使用-7月余额](http://localhost:3335/output/proc/overdue_statistics/统计使用-7月余额_20260326_102708_777.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ0MTMyMDUsImV4cCI6MTc3NDQ5OTYwNSwianRpIjoiOWZjYTI5NjctNDE0Zi00NTUxLWFhNjUtOWM0ZDNkOTMyZDI0In0.MmpM8gFVq4sMc7of_qtUB5iAnPAB4FLTUB9nbK9HCwM)** — 99行
- **[统计使用-借方](http://localhost:3335/output/proc/overdue_statistics/统计使用-借方_20260326_102708_777.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ0MTMyMDUsImV4cCI6MTc3NDQ5OTYwNSwianRpIjoiOWZjYTI5NjctNDE0Zi00NTUxLWFhNjUtOWM0ZDNkOTMyZDI0In0.MmpM8gFVq4sMc7of_qtUB5iAnPAB4FLTUB9nbK9HCwM)** — 996行
- **[统计使用-贷方](http://localhost:3335/output/proc/overdue_statistics/统计使用-贷方_20260326_102708_777.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ0MTMyMDUsImV4cCI6MTc3NDQ5OTYwNSwianRpIjoiOWZjYTI5NjctNDE0Zi00NTUxLWFhNjUtOWM0ZDNkOTMyZDI0In0.MmpM8gFVq4sMc7of_qtUB5iAnPAB4FLTUB9nbK9HCwM)** — 296行
- **[统计合并](http://localhost:3335/output/proc/overdue_statistics/统计合并_20260326_102708_777.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ0MTMyMDUsImV4cCI6MTc3NDQ5OTYwNSwianRpIjoiOWZjYTI5NjctNDE0Zi00NTUxLWFhNjUtOWM0ZDNkOTMyZDI0In0.MmpM8gFVq4sMc7of_qtUB5iAnPAB4FLTUB9nbK9HCwM)** — 259行
- **[逾期统计](http://localhost:3335/output/proc/overdue_statistics/逾期统计_20260326_102708_777.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ0MTMyMDUsImV4cCI6MTc3NDQ5OTYwNSwianRpIjoiOWZjYTI5NjctNDE0Zi00NTUxLWFhNjUtOWM0ZDNkOTMyZDI0In0.MmpM8gFVq4sMc7of_qtUB5iAnPAB4FLTUB9nbK9HCwM)** — 115行

如需重新处理或使用其他规则，请告知。', '{}', '[]', '2026-03-26 10:27:10.132641');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('abb39c22-1c48-41ca-8274-575f28523495', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '已读取规则「逾期统计数据整理」，开始准备文件校验。', '{}', '[]', '2026-03-27 18:39:40.691002');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('857c2eaa-1ed0-4e3c-b100-4ff33ad9f290', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'user', '已上传 2 个文件，请处理。', '{}', '[{"name": null, "path": "/uploads/2026/3/22/2025-12-01~2025-12-01对账流水_153733.csv", "size": 0}, {"name": null, "path": "/uploads/2026/3/22/ads_finance_d_inc_channel_details_20260105133821735_0_153733.csv", "size": 0}]', '2026-03-22 15:38:31.486792');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('06b6e353-5048-4fab-9a60-a3b12e83f941', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '你好！我是 Tally，专业的智能财务助手。我可以帮助您完成财务数据整理和对账工作。选择任务类型（数据整理/数据对账）和数据规则即可开始处理。', '{}', '[]', '2026-03-23 17:51:52.155075');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('fe64ff8c-f980-4e00-b895-a9cc184aeb83', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '📊 **开始数据整理任务**

已选择规则：**逾期统计数据整理**

📋 **处理流程**（共4个步骤）：

1. **读取规则** — 从数据库加载数据整理规则定义
2. **文件校验** — 校验上传文件格式、列名是否符合规则要求
3. **执行整理** — 按照规则执行数据转换和整理
4. **结果展示** — 展示处理结果和生成的执行计划

请上传需要整理的数据文件，系统将自动按上述流程处理。', '{}', '[]', '2026-03-24 11:26:00.029893');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('53b3d30e-ed36-4bd1-bd88-ec7d1a85984d', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '文件校验通过。

**文件识别结果：**
✅ **已匹配：**
- **贷方-收款单明细.xlsx** → 贷方-收款单明细
- **调整明细.xlsx** → 调整明细
- **借方-计提单明细.xlsx** → 借方-计提单明细
- **金蝶期末余额-检核.xlsx** → 金蝶期末余额-检核
- **科目期初.xlsx** → 科目期初', '{}', '[]', '2026-03-24 11:32:15.255494');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('ae74c2cc-7f2d-4377-bf39-1a4f56467bfe', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '数据整理任务已完成，结果文件如下。

规则：逾期统计数据整理

**结果文件：**
- **[金蝶期末余额-检核](http://localhost:3335/output/proc/overdue_statistics/金蝶期末余额-检核_20260324_122404_420.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzMjMxMjMsImV4cCI6MTc3NDQwOTUyMywianRpIjoiOGJmZDhkMzMtYWU4NS00NTgwLTg4ODItNmQzMTNhZDIyMzc3In0.5PC2tCKSIO0nC4Hw9z6KTAFZZCtgDhCc7yypJlm9Xfs)** — 2行
- **[统计使用-7月余额](http://localhost:3335/output/proc/overdue_statistics/统计使用-7月余额_20260324_122404_420.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzMjMxMjMsImV4cCI6MTc3NDQwOTUyMywianRpIjoiOGJmZDhkMzMtYWU4NS00NTgwLTg4ODItNmQzMTNhZDIyMzc3In0.5PC2tCKSIO0nC4Hw9z6KTAFZZCtgDhCc7yypJlm9Xfs)** — 2行
- **[统计使用-借方](http://localhost:3335/output/proc/overdue_statistics/统计使用-借方_20260324_122404_420.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzMjMxMjMsImV4cCI6MTc3NDQwOTUyMywianRpIjoiOGJmZDhkMzMtYWU4NS00NTgwLTg4ODItNmQzMTNhZDIyMzc3In0.5PC2tCKSIO0nC4Hw9z6KTAFZZCtgDhCc7yypJlm9Xfs)** — 4行
- **[统计使用-贷方](http://localhost:3335/output/proc/overdue_statistics/统计使用-贷方_20260324_122404_420.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzMjMxMjMsImV4cCI6MTc3NDQwOTUyMywianRpIjoiOGJmZDhkMzMtYWU4NS00NTgwLTg4ODItNmQzMTNhZDIyMzc3In0.5PC2tCKSIO0nC4Hw9z6KTAFZZCtgDhCc7yypJlm9Xfs)** — 4行
- **[统计合并](http://localhost:3335/output/proc/overdue_statistics/统计合并_20260324_122404_420.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzMjMxMjMsImV4cCI6MTc3NDQwOTUyMywianRpIjoiOGJmZDhkMzMtYWU4NS00NTgwLTg4ODItNmQzMTNhZDIyMzc3In0.5PC2tCKSIO0nC4Hw9z6KTAFZZCtgDhCc7yypJlm9Xfs)** — 2行
- **[逾期统计](http://localhost:3335/output/proc/overdue_statistics/逾期统计_20260324_122404_420.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzMjMxMjMsImV4cCI6MTc3NDQwOTUyMywianRpIjoiOGJmZDhkMzMtYWU4NS00NTgwLTg4ODItNmQzMTNhZDIyMzc3In0.5PC2tCKSIO0nC4Hw9z6KTAFZZCtgDhCc7yypJlm9Xfs)** — 2行

如需重新处理或使用其他规则，请告知。', '{}', '[]', '2026-03-24 12:24:04.828848');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('5132fbf0-d556-4866-9330-86e17657bb47', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '已读取规则「逾期统计数据整理」，开始准备文件校验。', '{}', '[]', '2026-03-24 14:04:24.354863');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('b56dc64d-9fcc-471c-a62e-b65d9dc4702e', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'user', '已上传 2 个文件，请处理。', '{}', '[{"name": null, "path": "/uploads/2026/3/24/1767597466118_140508.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/24/ads_finance_d_inc_channel_details_20260105152012277_0_140508.xlsx", "size": 0}]', '2026-03-24 14:05:09.292621');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('4d70c3ca-e31f-4917-98dc-467879006b1c', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '📊 **开始对账执行任务**

已选择规则：**喜马-26合单与官网数据核对**
已上传文件：2 个

正在校验文件并加载规则...', '{}', '[]', '2026-03-24 14:05:26.402025');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('e37f25ae-38d7-4d9a-be0b-45caee963b6f', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'user', '已上传 2 个文件，请处理。', '{}', '[]', '2026-03-24 17:47:09.124461');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('33c51826-3688-4bdc-a17c-c8aac6107829', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '以下是详细对账结果。

**规则：** 喜马-26合单与官网数据核对

---

📁 **文件**: `合单.xlsx` ↔ `官网.xlsx`



📊 **结果统计**:

| 类型 | 数量 | 说明 |
|------|------|------|
| ✅ 完全匹配 | 6484 | 数据完全一致 |
| ⚠️ 匹配有差异 | 0 | sup订单号/第三方订单号匹配但发生减不同 |
| 📤 合单.xlsx独有 | 0 | 仅在合单.xlsx中存在 |
| 📥 官网.xlsx独有 | 10 | 仅在官网.xlsx中存在 |
| **合计** | **6494** | 总记录数 |

📄 **[查看详细差异报告](http://localhost:3335/output/recon/喜马-26合单与官网数据核对_核对结果_20260324_174708.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQzNDU2MDYsImV4cCI6MTc3NDQzMjAwNiwianRpIjoiZWMwY2IwYjktYTYyMC00ZDYwLWJkNjktZWZmZjkzYTE3OTM5In0.xvk5LZ8OHUdCSXdToeOao-jpBnc6SKgC6-sbeuRK6GA)**

---


如需进一步分析或有疑问，请告知。', '{}', '[]', '2026-03-24 17:47:09.577704');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('2739e998-7b50-4035-a7cc-48882fc9fb62', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '文件校验通过。

**文件识别结果：**
✅ **已匹配：**
- **贷方-收款单明细.xlsx** → 贷方-收款单明细
- **调整明细.xlsx** → 调整明细
- **借方-计提单明细.xlsx** → 借方-计提单明细
- **金蝶期末余额-检核.xlsx** → 金蝶期末余额-检核
- **科目期初.xlsx** → 科目期初', '{}', '[]', '2026-03-24 17:47:34.064997');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('58802dd9-6dbc-4092-9b1c-2dbd504d7b88', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '📊 **开始对账执行任务**

已选择规则：**喜马-26合单与官网数据核对**
已上传文件：2 个

正在校验文件并加载规则...', '{}', '[]', '2026-03-25 12:33:50.462693');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('afc2017b-28d6-4653-bfa5-66a3c548c8ba', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '执行整理已完成。

- 规则：逾期统计数据整理
- 生成目标文件：6 个
- 合并文件：0 个

正在整理最终结果，请稍候。', '{}', '[]', '2026-03-25 12:34:20.109897');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('56c594a0-3302-4259-a2e9-6240682c73bf', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '文件校验通过。

**文件识别结果：**
✅ **已匹配：**
- **3、金蝶期末余额-检核.xlsx** → 金蝶期末余额-检核
- **3.1、科目期初.xlsx** → 科目期初
- **3.2、借方-计提单明细.xlsx** → 借方-计提单明细
- **3.3、贷方-收款单明细.xlsx** → 贷方-收款单明细
- **3.4、调整明细.xlsx** → 调整明细
- **中心匹配.xlsx** → 中心匹配', '{}', '[]', '2026-03-25 19:01:58.474776');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('2d58c828-b848-4a7e-b56c-ca956b591f6e', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'user', '已上传 6 个文件，请处理。', '{}', '[{"name": null, "path": "/uploads/2026/3/25/3、金蝶期末余额-检核_191135.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/25/3.1、科目期初_191135.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/25/3.2、借方-计提单明细_191135.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/25/3.3、贷方-收款单明细_191135.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/25/3.4、调整明细_191135.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/25/中心匹配_191135.xlsx", "size": 0}]', '2026-03-25 19:12:39.397319');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('dff92a4b-667c-46e7-b2a2-674aa30020c0', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '📊 **开始数据整理任务**

已选择规则：**逾期统计数据整理**
已上传文件：6 个

📋 **处理流程**（共4个步骤）：

1. **读取规则** — 从数据库加载数据整理规则定义
2. **文件校验** — 校验上传文件格式、列名是否符合规则要求
3. **执行整理** — 按照规则执行数据转换和整理
4. **结果展示** — 展示处理结果和生成的执行计划

正在校验文件并加载规则...', '{}', '[]', '2026-03-25 19:12:40.019928');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('1d12ae40-4043-4a51-bff6-79f384455e1d', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '已读取规则「逾期统计数据整理」，开始准备文件校验。', '{}', '[]', '2026-03-26 10:27:10.251728');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('8aafa1ad-4b87-4a10-85a3-4a98fafa1203', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '执行整理已完成。

- 规则：逾期统计数据整理
- 生成目标文件：6 个
- 合并文件：0 个

正在整理最终结果，请稍候。', '{}', '[]', '2026-03-27 18:17:30.126626');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('9deff274-d81d-4936-8ef2-cdf8a0b35e35', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'user', '我的规则列表', '{}', '[]', '2026-03-22 15:37:09.303455');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('2121f012-d4af-45da-847e-d5f58dccbdf9', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '✅ 对账完成

**对账概览**
- **2025-12-01~2025-12-01对账流水_153733.csv:** 2316条
- **ads_finance_d_inc_channel_details_20260105133821735_0_153733.csv:** 2289条
- **匹配成功:** 2289条
- **异常记录:** 27条
- **匹配率:** 98.8%

**异常明细 (27条)**

| 异常订单号 | 异常原因 |
|-----------|----------|
| L25120110170809713900 | 2025-12-01~2025-12-01对账流水_153733.csv存在，ads_finance_d_inc_channel_details_20260105133821735_0_153733.csv无此订单记录 |
| L25120111175452914200 | 2025-12-01~2025-12-01对账流水_153733.csv存在，ads_finance_d_inc_channel_details_20260105133821735_0_153733.csv无此订单记录 |
| L25120110321469314100 | 2025-12-01~2025-12-01对账流水_153733.csv存在，ads_finance_d_inc_channel_details_20260105133821735_0_153733.csv无此订单记录 |
| L25120103334534714200 | 2025-12-01~2025-12-01对账流水_153733.csv存在，ads_finance_d_inc_channel_details_20260105133821735_0_153733.csv无此订单记录 |
| L25120110161182614100 | 2025-12-01~2025-12-01对账流水_153733.csv存在，ads_finance_d_inc_channel_details_20260105133821735_0_153733.csv无此订单记录 |
| L25120111443209714200 | 2025-12-01~2025-12-01对账流水_153733.csv存在，ads_finance_d_inc_channel_details_20260105133821735_0_153733.csv无此订单记录 |
| L25120113570522214200 | 2025-12-01~2025-12-01对账流水_153733.csv存在，ads_finance_d_inc_channel_details_20260105133821735_0_153733.csv无此订单记录 |
| L25120113314579414000 | 2025-12-01~2025-12-01对账流水_153733.csv存在，ads_finance_d_inc_channel_details_20260105133821735_0_153733.csv无此订单记录 |
| L25120100244338814200 | 2025-12-01~2025-12-01对账流水_153733.csv存在，ads_finance_d_inc_channel_details_20260105133821735_0_153733.csv无此订单记录 |
| L25120111412116113900 | 2025-12-01~2025-12-01对账流水_153733.csv存在，ads_finance_d_inc_channel_details_20260105133821735_0_153733.csv无此订单记录 |
| L25120114565738713900 | 2025-12-01~2025-12-01对账流水_153733.csv存在，ads_finance_d_inc_channel_details_20260105133821735_0_153733.csv无此订单记录 |
| L25120115025545713900 | 2025-12-01~2025-12-01对账流水_153733.csv存在，ads_finance_d_inc_channel_details_20260105133821735_0_153733.csv无此订单记录 |
| L25120111455281814000 | 2025-12-01~2025-12-01对账流水_153733.csv存在，ads_finance_d_inc_channel_details_20260105133821735_0_153733.csv无此订单记录 |
| L25120112364330914000 | 2025-12-01~2025-12-01对账流水_153733.csv存在，ads_finance_d_inc_channel_details_20260105133821735_0_153733.csv无此订单记录 |
| L25120100512124614000 | 2025-12-01~2025-12-01对账流水_153733.csv存在，ads_finance_d_inc_channel_details_20260105133821735_0_153733.csv无此订单记录 |
| L25120112094453614000 | 2025-12-01~2025-12-01对账流水_153733.csv存在，ads_finance_d_inc_channel_details_20260105133821735_0_153733.csv无此订单记录 |
| L25120110060875614200 | 2025-12-01~2025-12-01对账流水_153733.csv存在，ads_finance_d_inc_channel_details_20260105133821735_0_153733.csv无此订单记录 |
| L25120108194593814000 | 2025-12-01~2025-12-01对账流水_153733.csv存在，ads_finance_d_inc_channel_details_20260105133821735_0_153733.csv无此订单记录 |
| L25120112572006214100 | 2025-12-01~2025-12-01对账流水_153733.csv存在，ads_finance_d_inc_channel_details_20260105133821735_0_153733.csv无此订单记录 |
| L25120109310768114100 | 2025-12-01~2025-12-01对账流水_153733.csv存在，ads_finance_d_inc_channel_details_20260105133821735_0_153733.csv无此订单记录 |
（共27条，仅列前20条）', '{}', '[]', '2026-03-22 15:38:31.518143');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('12119ebf-40b4-4289-9cc2-5d97f143a2a3', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'user', '你好', '{}', '[]', '2026-03-24 11:24:31.251016');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('428ef151-63f1-4f47-bea8-ac361c82a503', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'user', '已上传 5 个文件，请处理。', '{}', '[{"name": null, "path": "/uploads/2026/3/24/贷方-收款单明细_113212.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/24/调整明细_113212.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/24/借方-计提单明细_113212.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/24/金蝶期末余额-检核_113213.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/24/科目期初_113213.xlsx", "size": 0}]', '2026-03-24 11:32:14.687188');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('4448b755-1cdb-45de-8f4a-8d55a41c682a', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'user', '你好', '{}', '[]', '2026-03-24 12:23:52.689767');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('13102ccf-4947-45b5-82f7-87e1c2635243', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '执行整理已完成。

- 规则：逾期统计数据整理
- 生成目标文件：6 个
- 合并文件：0 个

正在整理最终结果，请稍候。', '{}', '[]', '2026-03-24 12:24:05.00133');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('174dd5ff-2fa0-40e9-b71c-422188d58cc2', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '执行整理已完成。

- 规则：逾期统计数据整理
- 生成目标文件：6 个
- 合并文件：0 个

正在整理最终结果，请稍候。', '{}', '[]', '2026-03-24 14:04:24.458857');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('f99ccb94-420c-4ffa-886f-1c419d0d2fb6', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '文件校验失败：

本次共上传 2 个文件；当前规则需要 2 类文件。

上传的文件不符合「喜马-26合单与官网数据核对」规则。
规则要求上传以下文件，并且文件表头需包含对应列名：

- 喜马合单表：完成时间、订单来源、订单号、订单类型、结算类型、渠道所属公司、渠道供应商、渠道名称、发生+、发生-
- 喜马官网表：喜马订单号、支付时间、分成比例、合作方分销收入、应结算平台金额、结算状态、商品金额、实付金额

已识别的文件：
- ads_finance_d_inc_channel_details_20260105152012277_0.xlsx -> 喜马合单表

未识别的文件：
- 1767597466118.xlsx

发现以下问题：
- 存在未能识别的文件，请检查文件格式和表头是否符合规则要求。

请检查文件格式后重新上传文件。', '{}', '[]', '2026-03-24 14:05:09.397343');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('3ae40b9c-73e1-4a31-b451-d5e0ba343c5d', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '对账执行已完成：共处理 6494 条，匹配 6484 条，异常 10 条。

异常分布：
- 目标文件独有: 10 条

正在生成详细结果，请稍候。', '{}', '[]', '2026-03-24 14:05:26.483221');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('f45077d2-20d6-42d0-b52b-fc205a2e25f1', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '📊 **开始对账执行任务**

已选择规则：**喜马-26合单与官网数据核对**
已上传文件：2 个

正在校验文件并加载规则...', '{}', '[]', '2026-03-24 17:47:09.216131');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('57890a0b-556e-47df-96aa-b4c43cb55bff', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'user', '已上传 5 个文件，请处理。', '{}', '[{"name": null, "path": "/uploads/2026/3/24/贷方-收款单明细_174732.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/24/调整明细_174732.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/24/借方-计提单明细_174732.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/24/金蝶期末余额-检核_174732.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/24/科目期初_174732.xlsx", "size": 0}]', '2026-03-24 17:47:33.517039');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('31c2da68-1841-4dfa-b038-19a6423d3826', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '执行整理已完成。

- 规则：逾期统计数据整理
- 生成目标文件：6 个
- 合并文件：0 个

正在整理最终结果，请稍候。', '{}', '[]', '2026-03-24 17:47:34.176437');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('05af01e0-9d52-4cfd-bf4f-5031e99aeb4c', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '文件校验通过。

**文件识别结果：**
✅ **已匹配：**
- **官网.xlsx** → 喜马官网表
- **合单.xlsx** → 喜马合单表', '{}', '[]', '2026-03-25 12:33:50.562928');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('7ead1505-7b0e-4833-a524-eb9028f1ba31', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '文件校验通过。

**文件识别结果：**
✅ **已匹配：**
- **贷方-收款单明细.xlsx** → 贷方-收款单明细
- **调整明细.xlsx** → 调整明细
- **借方-计提单明细.xlsx** → 借方-计提单明细
- **金蝶期末余额-检核.xlsx** → 金蝶期末余额-检核
- **科目期初.xlsx** → 科目期初', '{}', '[]', '2026-03-25 12:34:20.315036');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('0e280323-0bea-475e-959f-a5bdc9d1e2c5', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '执行整理失败，正在整理错误详情。

- 规则：逾期统计数据整理
- 错误摘要：等待 MCP 响应超时', '{}', '[]', '2026-03-25 19:01:58.575248');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('6d382f79-84b0-489d-a3e3-39e11472aace', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '已读取规则「逾期统计数据整理」，开始准备文件校验。', '{}', '[]', '2026-03-25 19:12:39.506945');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('4bdacf53-cdc0-4296-b685-b5e4b86f2858', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'user', '已上传 6 个文件，请处理。', '{}', '[{"name": null, "path": "/uploads/2026/3/26/3、金蝶期末余额-检核_102638.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/26/3.1、科目期初_102638.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/26/3.2、借方-计提单明细_102638.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/26/3.3、贷方-收款单明细_102638.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/26/3.4、调整明细_102638.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/26/中心匹配_102638.xlsx", "size": 0}]', '2026-03-26 10:27:10.017426');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('fa26fa82-5186-44cf-a094-09b7512bbf14', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '📊 **开始数据整理任务**

已选择规则：**逾期统计数据整理**
已上传文件：6 个

📋 **处理流程**（共4个步骤）：

1. **读取规则** — 从数据库加载数据整理规则定义
2. **文件校验** — 校验上传文件格式、列名是否符合规则要求
3. **执行整理** — 按照规则执行数据转换和整理
4. **结果展示** — 展示处理结果和生成的执行计划

正在校验文件并加载规则...', '{}', '[]', '2026-03-26 10:27:10.343184');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('80871105-dc36-420c-817d-2a4034a9560c', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '📊 **开始数据整理任务**

已选择规则：**逾期统计数据整理**
已上传文件：6 个

📋 **处理流程**（共4个步骤）：

1. **读取规则** — 从数据库加载数据整理规则定义
2. **文件校验** — 校验上传文件格式、列名是否符合规则要求
3. **执行整理** — 按照规则执行数据转换和整理
4. **结果展示** — 展示处理结果和生成的执行计划

正在校验文件并加载规则...', '{}', '[]', '2026-03-27 18:04:13.360495');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('92d7edcd-056c-4134-b973-82b32895109d', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '📊 **开始数据整理任务**

已选择规则：**逾期统计数据整理**
已上传文件：6 个

📋 **处理流程**（共4个步骤）：

1. **读取规则** — 从数据库加载数据整理规则定义
2. **文件校验** — 校验上传文件格式、列名是否符合规则要求
3. **执行整理** — 按照规则执行数据转换和整理
4. **结果展示** — 展示处理结果和生成的执行计划

正在校验文件并加载规则...', '{}', '[]', '2026-03-27 18:17:30.246073');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('7315b668-2bf8-4662-b59c-ee95d855579f', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '文件校验失败：

本次共上传 6 个文件；当前规则需要 6 类文件。

上传的文件不符合「逾期统计数据整理」规则。
规则要求上传以下文件，并且文件表头需包含对应列名：

- 中心匹配：中心1
- 科目期初：日期、科目代码、科目名称、公司、客商名称、周期、归属中心、期末余额、预计回款时间、逾期时间
- 借方-计提单明细：对应科目编码、对应科目、日期、公司名称、中心、计提项目、周期、客商名称、含税金额、不含税金额、税额、单号整理、期数、逾期时间
- 贷方-收款单明细：对应科目编码、对应科目、日期、公司名称、客商名称、金额、单号、费用项目、商户、填单人
- 金蝶期末余额-检核：科目代码、科目名称、公司、客商名称、期初、借方合计、贷方合计、借方调整、贷方调整、计算余额
- 调整明细：科目编码、科目名称、公司、对方核算项目、业务日期、借方、贷方、中心、周期

已识别的文件：
- 贷方-收款单明细.xlsx -> 贷方-收款单明细
- 调整明细.xlsx -> 调整明细
- 借方-计提单明细.xlsx -> 借方-计提单明细
- 中心匹配.xlsx -> 中心匹配

未识别的文件：
- 金蝶期末余额-检核.xlsx
- 科目期初.xlsx

发现以下问题：
- 存在未能识别的文件，请检查文件格式和表头是否符合规则要求。

请检查文件格式后重新上传文件。', '{}', '[]', '2026-03-27 18:04:13.25438');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('d1b63404-b228-443b-964d-a14ffed9bbb0', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'user', '已上传 6 个文件，请处理。', '{}', '[{"name": null, "path": "/uploads/2026/3/27/贷方-收款单明细_181659.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/27/调整明细_181700.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/27/借方-计提单明细_181700.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/27/金蝶期末余额-检核_181700.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/27/科目期初_181700.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/27/中心匹配_181700.xlsx", "size": 0}]', '2026-03-27 18:17:29.790831');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('f9330d29-f90b-413d-97cf-6f511b8f46b2', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '数据整理任务已完成，结果文件如下。

规则：逾期统计数据整理

**结果文件：**
- **[金蝶期末余额-检核](http://localhost:3335/output/proc/overdue_statistics/金蝶期末余额-检核_20260327_181728_673.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ2MDUyOTYsImV4cCI6MTc3NDY5MTY5NiwianRpIjoiZjgyNTg0NmYtYzUzNy00NDRkLWJhMmUtOTNkMTY3N2NiNTEyIn0.ajcpE4TZvzO8o6J6t3hAQq9XUUu-x8-Ik7b2bn6OuTo)** — 124行
- **[统计使用-7月余额](http://localhost:3335/output/proc/overdue_statistics/统计使用-7月余额_20260327_181728_673.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ2MDUyOTYsImV4cCI6MTc3NDY5MTY5NiwianRpIjoiZjgyNTg0NmYtYzUzNy00NDRkLWJhMmUtOTNkMTY3N2NiNTEyIn0.ajcpE4TZvzO8o6J6t3hAQq9XUUu-x8-Ik7b2bn6OuTo)** — 91行
- **[统计使用-借方](http://localhost:3335/output/proc/overdue_statistics/统计使用-借方_20260327_181728_673.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ2MDUyOTYsImV4cCI6MTc3NDY5MTY5NiwianRpIjoiZjgyNTg0NmYtYzUzNy00NDRkLWJhMmUtOTNkMTY3N2NiNTEyIn0.ajcpE4TZvzO8o6J6t3hAQq9XUUu-x8-Ik7b2bn6OuTo)** — 944行
- **[统计使用-贷方](http://localhost:3335/output/proc/overdue_statistics/统计使用-贷方_20260327_181728_673.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ2MDUyOTYsImV4cCI6MTc3NDY5MTY5NiwianRpIjoiZjgyNTg0NmYtYzUzNy00NDRkLWJhMmUtOTNkMTY3N2NiNTEyIn0.ajcpE4TZvzO8o6J6t3hAQq9XUUu-x8-Ik7b2bn6OuTo)** — 270行
- **[统计合并](http://localhost:3335/output/proc/overdue_statistics/统计合并_20260327_181728_673.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ2MDUyOTYsImV4cCI6MTc3NDY5MTY5NiwianRpIjoiZjgyNTg0NmYtYzUzNy00NDRkLWJhMmUtOTNkMTY3N2NiNTEyIn0.ajcpE4TZvzO8o6J6t3hAQq9XUUu-x8-Ik7b2bn6OuTo)** — 193行
- **[逾期统计](http://localhost:3335/output/proc/overdue_statistics/逾期统计_20260327_181728_673.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ2MDUyOTYsImV4cCI6MTc3NDY5MTY5NiwianRpIjoiZjgyNTg0NmYtYzUzNy00NDRkLWJhMmUtOTNkMTY3N2NiNTEyIn0.ajcpE4TZvzO8o6J6t3hAQq9XUUu-x8-Ik7b2bn6OuTo)** — 40行

如需重新处理或使用其他规则，请告知。', '{}', '[]', '2026-03-27 18:17:29.92541');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('2c602fd0-952a-491c-bf60-038f7c0b51d4', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '文件校验通过。

**文件识别结果：**
✅ **已匹配：**
- **贷方-收款单明细.xlsx** → 贷方-收款单明细
- **调整明细.xlsx** → 调整明细
- **借方-计提单明细.xlsx** → 借方-计提单明细
- **金蝶期末余额-检核.xlsx** → 金蝶期末余额-检核
- **科目期初.xlsx** → 科目期初
- **中心匹配.xlsx** → 中心匹配', '{}', '[]', '2026-03-27 18:17:30.390883');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('2ade07af-0bac-47d6-b8ee-21f42f3bac59', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'user', '已上传 6 个文件，请处理。', '{}', '[{"name": null, "path": "/uploads/2026/3/27/贷方-收款单明细_183910.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/27/调整明细_183910.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/27/借方-计提单明细_183910.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/27/金蝶期末余额-检核_183910.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/27/科目期初_183910.xlsx", "size": 0}, {"name": null, "path": "/uploads/2026/3/27/中心匹配_183910.xlsx", "size": 0}]', '2026-03-27 18:39:40.584238');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('6943312e-03ad-450c-9d60-d57721031c40', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '文件校验通过。

**文件识别结果：**
✅ **已匹配：**
- **贷方-收款单明细.xlsx** → 贷方-收款单明细
- **调整明细.xlsx** → 调整明细
- **借方-计提单明细.xlsx** → 借方-计提单明细
- **金蝶期末余额-检核.xlsx** → 金蝶期末余额-检核
- **科目期初.xlsx** → 科目期初
- **中心匹配.xlsx** → 中心匹配', '{}', '[]', '2026-03-27 18:39:40.933959');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('9bf919dd-0292-46c3-a865-b3f65511cd53', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '📊 **开始数据整理任务**

已选择规则：**逾期统计数据整理**
已上传文件：6 个

📋 **处理流程**（共4个步骤）：

1. **读取规则** — 从数据库加载数据整理规则定义
2. **文件校验** — 校验上传文件格式、列名是否符合规则要求
3. **执行整理** — 按照规则执行数据转换和整理
4. **结果展示** — 展示处理结果和生成的执行计划

正在校验文件并加载规则...', '{}', '[]', '2026-03-27 18:39:41.029816');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('1e3d6f8e-a61f-4523-90de-fdf52fc29d19', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '执行整理已完成。

- 规则：逾期统计数据整理
- 生成目标文件：6 个
- 合并文件：0 个

正在整理最终结果，请稍候。', '{}', '[]', '2026-03-27 18:39:41.140513');
INSERT INTO public.messages (id, conversation_id, role, content, metadata, attachments, created_at) VALUES ('0a2f3004-6ee9-4114-b952-df21cca3c231', 'd9d4079d-ce32-43d6-b3ee-41e6e3a8a548', 'assistant', '数据整理任务已完成，结果文件如下。

规则：逾期统计数据整理

**结果文件：**
- **[金蝶期末余额-检核](http://localhost:3335/output/proc/overdue_statistics/金蝶期末余额-检核_20260327_183939_291.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ2MDUyOTYsImV4cCI6MTc3NDY5MTY5NiwianRpIjoiZjgyNTg0NmYtYzUzNy00NDRkLWJhMmUtOTNkMTY3N2NiNTEyIn0.ajcpE4TZvzO8o6J6t3hAQq9XUUu-x8-Ik7b2bn6OuTo)** — 124行
- **[统计使用-7月余额](http://localhost:3335/output/proc/overdue_statistics/统计使用-7月余额_20260327_183939_291.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ2MDUyOTYsImV4cCI6MTc3NDY5MTY5NiwianRpIjoiZjgyNTg0NmYtYzUzNy00NDRkLWJhMmUtOTNkMTY3N2NiNTEyIn0.ajcpE4TZvzO8o6J6t3hAQq9XUUu-x8-Ik7b2bn6OuTo)** — 91行
- **[统计使用-借方](http://localhost:3335/output/proc/overdue_statistics/统计使用-借方_20260327_183939_291.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ2MDUyOTYsImV4cCI6MTc3NDY5MTY5NiwianRpIjoiZjgyNTg0NmYtYzUzNy00NDRkLWJhMmUtOTNkMTY3N2NiNTEyIn0.ajcpE4TZvzO8o6J6t3hAQq9XUUu-x8-Ik7b2bn6OuTo)** — 944行
- **[统计使用-贷方](http://localhost:3335/output/proc/overdue_statistics/统计使用-贷方_20260327_183939_291.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ2MDUyOTYsImV4cCI6MTc3NDY5MTY5NiwianRpIjoiZjgyNTg0NmYtYzUzNy00NDRkLWJhMmUtOTNkMTY3N2NiNTEyIn0.ajcpE4TZvzO8o6J6t3hAQq9XUUu-x8-Ik7b2bn6OuTo)** — 270行
- **[统计合并](http://localhost:3335/output/proc/overdue_statistics/统计合并_20260327_183939_291.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ2MDUyOTYsImV4cCI6MTc3NDY5MTY5NiwianRpIjoiZjgyNTg0NmYtYzUzNy00NDRkLWJhMmUtOTNkMTY3N2NiNTEyIn0.ajcpE4TZvzO8o6J6t3hAQq9XUUu-x8-Ik7b2bn6OuTo)** — 193行
- **[逾期统计](http://localhost:3335/output/proc/overdue_statistics/逾期统计_20260327_183939_291.xlsx?auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDMiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiY29tcGFueV9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsImRlcGFydG1lbnRfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJpYXQiOjE3NzQ2MDUyOTYsImV4cCI6MTc3NDY5MTY5NiwianRpIjoiZjgyNTg0NmYtYzUzNy00NDRkLWJhMmUtOTNkMTY3N2NiNTEyIn0.ajcpE4TZvzO8o6J6t3hAQq9XUUu-x8-Ik7b2bn6OuTo)** — 40行

如需重新处理或使用其他规则，请告知。', '{}', '[]', '2026-03-27 18:39:41.260096');


--
-- Data for Name: user_tasks; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.user_tasks (id, user_id, task_code, task_name, description) VALUES (3, '00000000-0000-0000-0000-000000000003', 'verif_recog', '数据整理', NULL);
INSERT INTO public.user_tasks (id, user_id, task_code, task_name, description) VALUES (5, '00000000-0000-0000-0000-000000000003', 'audio_recon', '数据对账', NULL);


--
-- Data for Name: rule_detail; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.rule_detail (id, rule_code, rule, remark, rule_type, user_id, name, task_id) VALUES (6, 'audio_recon_file_check', '{"file_validation_rules": {"version": "1.0", "description": "音频业务对账文件校验规则，包含喜马-26、腾讯异业、南京飞翰等目录的文件校验", "table_schemas": [{"table_id": "XIMA_HE_DAN", "file_type": ["xls", "xlsx", "csv"], "table_name": "喜马合单表", "table_type": "source", "description": "喜马合单数据表，包含订单汇总和渠道结算信息", "is_required": true, "column_aliases": {"发生+": ["发生加", "收入", "income"], "发生-": ["发生减", "支出", "expense"], "订单号": ["订单编号", "order_no"], "完成时间": ["完成日期", "finish_time"], "渠道名称": ["channel_name"], "结算类型": ["settlement_type"], "订单来源": ["来源", "order_source"], "订单类型": ["order_type"], "渠道供应商": ["供应商", "channel_supplier"], "渠道所属公司": ["所属公司", "channel_company"]}, "max_match_count": 1, "required_columns": ["完成时间", "订单来源", "订单号", "订单类型", "结算类型", "渠道所属公司", "渠道供应商", "渠道名称", "发生+", "发生-"]}, {"table_id": "XIMA_GUAN_WANG", "file_type": ["xls", "xlsx", "csv"], "table_name": "喜马官网表", "table_type": "target", "description": "喜马官网订单明细表，包含订单详情和商品信息", "is_required": true, "column_aliases": {"分成比例": ["分成", "share_ratio"], "商品金额": ["product_amount", "商品总价"], "实付金额": ["actual_amount", "实际支付金额"], "支付时间": ["pay_time", "付款时间"], "结算状态": ["settlement_status"], "喜马订单号": ["订单号", "xima_order_no", "order_no"], "合作方分销收入": ["分销收入", "partner_income"], "应结算平台金额": ["结算金额", "settlement_amount"]}, "max_match_count": 1, "required_columns": ["喜马订单号", "支付时间", "分成比例", "合作方分销收入", "应结算平台金额", "结算状态", "商品金额", "实付金额"]}], "validation_config": {"case_sensitive": false, "ignore_whitespace": true}}}', '审计对账-文件上传合法性校验规则', 'file', NULL, '审计对账-文件上传合法性校验规则', 5);
INSERT INTO public.rule_detail (id, rule_code, rule, remark, rule_type, user_id, name, task_id) VALUES (4, 'audio_recon', '{"rules": [{"recon": {"aggregation": {"enabled": true, "group_by": [{"source_field": "sup订单号", "target_field": "第三方订单号"}], "description": "分组聚合配置，启用后先按 source/target 对应字段分组聚合，再进行比对", "aggregations": [{"alias": "应结算平台金额汇总", "function": "sum", "source_field": "发生-", "target_field": "应结算平台金额"}]}, "description": "核对配置", "key_columns": {"mappings": [{"source_field": "sup订单号", "target_field": "第三方订单号"}], "match_type": "exact", "description": "用于关联源文件与目标文件的关键列映射（相当于 JOIN 条件），支持多字段映射", "transformations": {"source": {"sup订单号": [{"type": "strip_prefix", "value": "''"}, {"type": "regex_replace", "pattern": "^(.{1,21}).*$", "replacement": "\\1"}]}, "target": {"第三方订单号": [{"type": "regex_replace", "pattern": "_\\\\d+$", "replacement": ""}, {"type": "regex_replace", "pattern": "^(.{1,21}).*$", "replacement": "\\1"}]}}}, "compare_columns": {"columns": [{"name": "发生减", "tolerance": 0.01, "description": "合单发生- 与 官网应结算平台金额比对，允许 0.01 的绝对误差", "compare_type": "numeric", "source_column": "发生-", "target_column": "应结算平台金额"}], "description": "需要比对的数值列"}}, "output": {"format": "xlsx", "sheets": {"summary": {"name": "核对汇总", "enabled": true, "description": "输出核对结果汇总信息，包括总记录数、匹配数、差异数等"}, "source_only": {"name": "合单独有", "enabled": true, "description": "仅在合单文件中存在的记录"}, "target_only": {"name": "官网独有", "enabled": true, "description": "仅在官网文件中存在的记录"}, "matched_with_diff": {"name": "差异记录", "enabled": true, "description": "关键列匹配但数值有差异的记录详情"}}, "file_name_template": "喜马26_{rule_name}_核对结果_{timestamp}"}, "enabled": true, "source_file": {"table_name": "喜马合单表", "description": "源文件定义（合单文件）", "identification": {"match_by": "table_name", "description": "通过文件校验阶段识别的表名匹配源文件", "match_value": "喜马合单表", "match_strategy": "exact"}}, "target_file": {"table_name": "喜马官网表", "description": "目标文件定义（官网文件）", "identification": {"match_by": "table_name", "description": "通过文件校验阶段识别的表名匹配目标文件", "match_value": "喜马官网表", "match_strategy": "exact"}}}], "rule_id": "XM_26_RECONC_001", "rule_name": "喜马-26合单与官网数据核对", "description": "将合单文件与官网文件进行核对，通过 sup 订单号与第三方订单号关联，比对应结算金额差异", "file_rule_code": "audio_recon_file_check", "schema_version": "1.6"}', '审计对账规则，用于源文件与目标文件的数据比对与差异分析', 'recon', NULL, '喜马-26合单与官网数据核对', 5);
INSERT INTO public.rule_detail (id, rule_code, rule, remark, rule_type, user_id, name, task_id) VALUES (7, 'overdue_file_check', '{"file_validation_rules": {"table_schemas": [{"table_id": "OVERDUE_CENTER_MAPPING", "file_type": ["xls", "xlsx", "xlsm", "xlsb", "csv"], "table_name": "中心匹配", "column_aliases": {"中心1": ["安全法务中心"]}, "required_columns": ["中心1", "中心2"]}, {"table_id": "OVERDUE_OPENING_BALANCE", "file_type": ["xls", "xlsx", "xlsm", "xlsb", "csv"], "table_name": "科目期初", "column_aliases": {"公司": ["公司名称"], "归属中心": ["中心"], "核算项目": ["客商名称", "客商"], "科目代码": ["科目编码"], "预计回款时间": ["预计回款日期", "预计回款"]}, "required_columns": ["日期", "科目代码", "科目名称", "公司", "核算项目", "周期", "归属中心", "期末余额", "预计回款时间"]}, {"table_id": "OVERDUE_DEBIT_DETAIL", "file_type": ["xls", "xlsx", "xlsm", "xlsb", "csv"], "table_name": "借方-计提单明细", "column_aliases": {"公司名称": ["公司"], "单号整理": ["单号"], "客商名称": ["核算项目", "客商"], "对应科目": ["科目名称"], "计提项目": ["计提项"], "对应科目编码": ["科目编码", "科目代码"]}, "required_columns": ["对应科目编码", "对应科目", "日期", "公司名称", "中心", "计提项目", "周期", "客商名称", "含税金额", "不含税金额", "税额", "单号整理", "期数", "逾期时间"]}, {"table_id": "OVERDUE_CREDIT_DETAIL", "file_type": ["xls", "xlsx", "xlsm", "xlsb", "csv"], "table_name": "贷方-收款单明细", "column_aliases": {"公司名称": ["公司"], "客商名称": ["核算项目", "客商"], "对应科目": ["科目名称"], "对应科目编码": ["科目编码", "科目代码"]}, "required_columns": ["对应科目编码", "对应科目", "日期", "公司名称", "客商名称", "中心", "周期", "金额", "单号", "费用项目", "商户", "填单人"]}, {"table_id": "OVERDUE_KINGDEE_CHECK", "file_type": ["xls", "xlsx", "xlsm", "xlsb", "csv"], "table_name": "金蝶期末余额-检核", "column_aliases": {"公司": ["公司名称"], "科目代码": ["科目编码"], "核算项目1": ["客商名称", "核算项目"]}, "required_columns": ["科目代码", "科目名称", "公司", "核算项目1", "计算余额", "期初", "借方合计", "贷方合计", "借方调整", "贷方调整"]}, {"table_id": "OVERDUE_ADJUSTMENT_DETAIL", "file_type": ["xls", "xlsx", "xlsm", "xlsb", "csv"], "table_name": "调整明细", "column_aliases": {"借方": ["借方金额"], "贷方": ["贷方金额"], "业务日期": ["日期"], "对方核算项目": ["客商名称", "核算项目", "客商"]}, "required_columns": ["科目编码", "科目名称", "公司", "对方核算项目", "业务日期", "借方", "贷方", "中心", "周期"]}], "validation_config": {"case_sensitive": false, "ignore_whitespace": true}}}', '逾期统计文件校验规则', 'file', NULL, '逾期统计-文件上传合法性校验规则', 3);
INSERT INTO public.rule_detail (id, rule_code, rule, remark, rule_type, user_id, name, task_id) VALUES (8, 'overdue_statistics', '{"steps": [{"match": {"sources": [{"keys": [{"field": "科目名称", "target_field": "科目名称"}, {"field": "公司", "target_field": "公司"}, {"field": "核算项目", "target_field": "核算项目1"}], "alias": "opening_balance_agg"}, {"keys": [{"field": "对应科目", "target_field": "科目名称"}, {"field": "公司名称", "target_field": "公司"}, {"field": "客商名称", "target_field": "核算项目1"}], "alias": "debit_detail_agg"}, {"keys": [{"field": "对应科目", "target_field": "科目名称"}, {"field": "公司名称", "target_field": "公司"}, {"field": "客商名称", "target_field": "核算项目1"}], "alias": "credit_detail_agg"}, {"keys": [{"field": "科目名称", "target_field": "科目名称"}, {"field": "公司", "target_field": "公司"}, {"field": "对方核算项目", "target_field": "核算项目1"}], "alias": "adjustment_agg"}]}, "action": "write_dataset", "sources": [{"alias": "opening_balance_source", "table": "科目期初"}, {"alias": "debit_detail_source", "table": "借方-计提单明细"}, {"alias": "credit_detail_source", "table": "贷方-收款单明细"}, {"alias": "adjustment_source", "table": "调整明细"}], "step_id": "step1_update_check_table_amounts", "mappings": [{"value": {"type": "source", "source": {"alias": "opening_balance_agg", "field": "agg_期初"}}, "target_field": "期初", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "debit_detail_agg", "field": "agg_借方合计"}}, "target_field": "借方合计", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "credit_detail_agg", "field": "agg_贷方合计"}}, "target_field": "贷方合计", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "adjustment_agg", "field": "agg_借方调整"}}, "target_field": "借方调整", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "adjustment_agg", "field": "agg_贷方调整"}}, "target_field": "贷方调整", "field_write_mode": "overwrite"}], "aggregate": [{"aggregations": [{"alias": "agg_期初", "field": "期末余额", "operator": "sum"}], "group_fields": ["科目名称", "公司", "核算项目"], "output_alias": "opening_balance_agg", "source_alias": "opening_balance_source"}, {"aggregations": [{"alias": "agg_借方合计", "field": "含税金额", "operator": "sum"}], "group_fields": ["对应科目", "公司名称", "客商名称"], "output_alias": "debit_detail_agg", "source_alias": "debit_detail_source"}, {"aggregations": [{"alias": "agg_贷方合计", "field": "金额", "operator": "sum"}], "group_fields": ["对应科目", "公司名称", "客商名称"], "output_alias": "credit_detail_agg", "source_alias": "credit_detail_source"}, {"aggregations": [{"alias": "agg_借方调整", "field": "借方", "operator": "sum"}, {"alias": "agg_贷方调整", "field": "贷方", "operator": "sum"}], "group_fields": ["科目名称", "公司", "对方核算项目"], "output_alias": "adjustment_agg", "source_alias": "adjustment_source"}], "description": "根据四张源表汇总更新金蝶期末余额-检核的期初与借贷调整字段", "target_table": "金蝶期末余额-检核", "row_write_mode": "update_only"}, {"match": {"sources": [{"keys": [{"field": "科目代码", "target_field": "科目代码"}, {"field": "科目名称", "target_field": "科目名称"}, {"field": "公司", "target_field": "公司"}, {"field": "核算项目1", "target_field": "核算项目1"}], "alias": "check_table_source"}]}, "action": "write_dataset", "sources": [{"alias": "check_table_source", "table": "金蝶期末余额-检核"}], "step_id": "step1_finalize_check_table_balance", "mappings": [{"value": {"expr": "coalesce({opening}, 0) + coalesce({debit_total}, 0) - coalesce({credit_total}, 0) + coalesce({adjust_debit}, 0) - coalesce({adjust_credit}, 0)", "type": "formula"}, "bindings": {"opening": {"type": "source", "source": {"alias": "check_table_source", "field": "期初"}}, "debit_total": {"type": "source", "source": {"alias": "check_table_source", "field": "借方合计"}}, "adjust_debit": {"type": "source", "source": {"alias": "check_table_source", "field": "借方调整"}}, "credit_total": {"type": "source", "source": {"alias": "check_table_source", "field": "贷方合计"}}, "adjust_credit": {"type": "source", "source": {"alias": "check_table_source", "field": "贷方调整"}}}, "target_field": "计算余额", "field_write_mode": "overwrite"}], "depends_on": ["step1_update_check_table_amounts"], "description": "根据更新后的期初与借贷调整重新计算金蝶期末余额-检核的计算余额", "target_table": "金蝶期末余额-检核", "row_write_mode": "update_only"}, {"action": "create_schema", "schema": {"columns": [{"name": "日期", "nullable": false, "data_type": "date"}, {"name": "对应科目编码", "nullable": false, "data_type": "string"}, {"name": "对应科目", "nullable": false, "data_type": "string"}, {"name": "公司名称", "nullable": false, "data_type": "string"}, {"name": "客商名称", "nullable": false, "data_type": "string"}, {"name": "周期", "nullable": false, "data_type": "string"}, {"name": "中心", "nullable": false, "data_type": "string"}, {"name": "期末余额", "scale": 2, "default": 0, "data_type": "decimal", "precision": 18}, {"name": "预计回款时间", "nullable": true, "data_type": "date"}, {"name": "逾期时间", "nullable": true, "data_type": "date"}], "primary_key": []}, "step_id": "step2_create_july_balance_usage", "description": "创建统计使用-7月余额表", "target_table": "统计使用-7月余额"}, {"action": "write_dataset", "sources": [{"alias": "opening_balance_source", "table": "科目期初"}], "step_id": "step2_write_july_balance_usage", "mappings": [{"value": {"type": "source", "source": {"alias": "opening_balance_source", "field": "日期"}}, "target_field": "日期", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "opening_balance_source", "field": "科目代码"}}, "target_field": "对应科目编码", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "opening_balance_source", "field": "科目名称"}}, "target_field": "对应科目", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "opening_balance_source", "field": "公司"}}, "target_field": "公司名称", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "opening_balance_source", "field": "核算项目"}}, "target_field": "客商名称", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "opening_balance_source", "field": "周期"}}, "target_field": "周期", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "opening_balance_source", "field": "归属中心"}}, "target_field": "中心", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "opening_balance_source", "field": "期末余额"}}, "target_field": "期末余额", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "opening_balance_source", "field": "预计回款时间"}}, "target_field": "预计回款时间", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "opening_balance_source", "field": "逾期时间"}}, "target_field": "逾期时间", "field_write_mode": "overwrite"}], "depends_on": ["step1_finalize_check_table_balance", "step2_create_july_balance_usage"], "description": "按金蝶期末余额-检核匹配科目期初，生成统计使用-7月余额", "target_table": "统计使用-7月余额", "row_write_mode": "upsert", "reference_filter": {"keys": [{"source_field": "科目名称", "reference_field": "科目名称"}, {"source_field": "公司", "reference_field": "公司"}, {"source_field": "核算项目", "reference_field": "核算项目1"}], "source_alias": "opening_balance_source", "reference_table": "金蝶期末余额-检核"}}, {"match": {"sources": [{"keys": [{"field": "单号", "target_field": "单号"}, {"field": "对应科目编码", "target_field": "对应科目编码"}, {"field": "公司名称", "target_field": "公司名称"}, {"field": "客商名称", "target_field": "客商名称"}, {"field": "周期", "target_field": "周期"}, {"field": "中心", "target_field": "中心"}], "alias": "credit_usage"}]}, "action": "write_dataset", "sources": [{"alias": "credit_usage", "table": "统计使用-贷方"}, {"alias": "center_mapping", "table": "中心匹配"}], "step_id": "step2_map_credit_center", "mappings": [{"value": {"expr": "coalesce({mapped_center}, {original_center})", "type": "formula"}, "bindings": {"mapped_center": {"keys": [{"input": {"type": "source", "source": {"alias": "credit_usage", "field": "中心"}}, "lookup_field": "中心1"}], "type": "lookup", "value_field": "中心2", "source_alias": "center_mapping"}, "original_center": {"type": "source", "source": {"alias": "credit_usage", "field": "中心"}}}, "target_field": "中心", "field_write_mode": "overwrite"}], "depends_on": ["step2_write_credit_usage"], "description": "根据中心匹配表将统计使用-贷方的中心替换为中心2", "target_table": "统计使用-贷方", "row_write_mode": "update_only"}, {"match": {"sources": [{"keys": [{"field": "单号", "target_field": "单号"}, {"field": "对应科目编码", "target_field": "对应科目编码"}, {"field": "公司名称", "target_field": "公司名称"}, {"field": "客商名称", "target_field": "客商名称"}, {"field": "周期", "target_field": "周期"}, {"field": "中心", "target_field": "中心"}], "alias": "debit_usage"}]}, "action": "write_dataset", "sources": [{"alias": "debit_usage", "table": "统计使用-借方"}, {"alias": "center_mapping", "table": "中心匹配"}], "step_id": "step2_map_debit_center", "mappings": [{"value": {"expr": "coalesce({mapped_center}, {original_center})", "type": "formula"}, "bindings": {"mapped_center": {"keys": [{"input": {"type": "source", "source": {"alias": "debit_usage", "field": "中心"}}, "lookup_field": "中心1"}], "type": "lookup", "value_field": "中心2", "source_alias": "center_mapping"}, "original_center": {"type": "source", "source": {"alias": "debit_usage", "field": "中心"}}}, "target_field": "中心", "field_write_mode": "overwrite"}], "depends_on": ["step2_write_debit_usage"], "description": "根据中心匹配表将统计使用-借方的中心替换为中心2", "target_table": "统计使用-借方", "row_write_mode": "update_only"}, {"action": "create_schema", "schema": {"columns": [{"name": "对应科目编码", "nullable": false, "data_type": "string"}, {"name": "对应科目", "nullable": false, "data_type": "string"}, {"name": "日期", "nullable": false, "data_type": "date"}, {"name": "公司名称", "nullable": false, "data_type": "string"}, {"name": "中心", "nullable": false, "data_type": "string"}, {"name": "计提项目", "nullable": true, "data_type": "string"}, {"name": "周期", "nullable": false, "data_type": "string"}, {"name": "客商名称", "nullable": false, "data_type": "string"}, {"name": "大类", "nullable": true, "data_type": "string"}, {"name": "含税金额", "scale": 2, "default": 0, "data_type": "decimal", "precision": 18}, {"name": "不含税金额", "scale": 2, "default": 0, "data_type": "decimal", "precision": 18}, {"name": "税额", "scale": 2, "default": 0, "data_type": "decimal", "precision": 18}, {"name": "单号", "nullable": false, "data_type": "string"}, {"name": "期数", "nullable": true, "data_type": "string"}, {"name": "逾期时间", "nullable": true, "data_type": "date"}], "primary_key": []}, "step_id": "step2_create_debit_usage", "description": "创建统计使用-借方表", "target_table": "统计使用-借方"}, {"action": "write_dataset", "sources": [{"alias": "debit_detail_source", "table": "借方-计提单明细"}], "step_id": "step2_write_debit_usage", "mappings": [{"value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "对应科目编码"}}, "target_field": "对应科目编码", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "对应科目"}}, "target_field": "对应科目", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "日期"}}, "target_field": "日期", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "公司名称"}}, "target_field": "公司名称", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "中心"}}, "target_field": "中心", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "计提项目"}}, "target_field": "计提项目", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "周期"}}, "target_field": "周期", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "客商名称"}}, "target_field": "客商名称", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "大类"}}, "target_field": "大类", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "含税金额"}}, "target_field": "含税金额", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "不含税金额"}}, "target_field": "不含税金额", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "税额"}}, "target_field": "税额", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "单号整理"}}, "target_field": "单号", "field_write_mode": "overwrite"}, {"value": {"expr": "{period_text} == ''月返'' ? ''1/1'' : {source_installment}", "type": "formula"}, "bindings": {"period_text": {"type": "source", "source": {"alias": "debit_detail_source", "field": "周期"}}, "source_installment": {"type": "source", "source": {"alias": "debit_detail_source", "field": "期数"}}}, "target_field": "期数", "field_write_mode": "overwrite"}, {"value": {"args": {"date": {"type": "source", "source": {"alias": "debit_detail_source", "field": "日期"}}, "months": {"expr": "{period_text} == ''月返'' ? 4 : ({period_text} == ''季返'' ? 6 - {period_numerator} : ({period_text} == ''年返'' ? 15 - {period_numerator} : 0))", "type": "formula", "bindings": {"period_text": {"type": "source", "source": {"alias": "debit_detail_source", "field": "周期"}}, "period_numerator": {"args": {"value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "期数"}}}, "type": "function", "function": "fraction_numerator"}}}}, "type": "function", "function": "add_months"}, "target_field": "逾期时间", "field_write_mode": "overwrite"}], "depends_on": ["step1_finalize_check_table_balance", "step2_create_debit_usage"], "description": "按金蝶期末余额-检核匹配借方明细，生成统计使用-借方，并按周期与期数分子计算逾期时间", "target_table": "统计使用-借方", "row_write_mode": "upsert", "reference_filter": {"keys": [{"source_field": "对应科目", "reference_field": "科目名称"}, {"source_field": "公司名称", "reference_field": "公司"}, {"source_field": "客商名称", "reference_field": "核算项目1"}], "source_alias": "debit_detail_source", "reference_table": "金蝶期末余额-检核"}}, {"action": "create_schema", "schema": {"columns": [{"name": "对应科目编码", "nullable": false, "data_type": "string"}, {"name": "对应科目", "nullable": false, "data_type": "string"}, {"name": "日期", "nullable": false, "data_type": "date"}, {"name": "公司名称", "nullable": false, "data_type": "string"}, {"name": "客商名称", "nullable": false, "data_type": "string"}, {"name": "中心", "nullable": false, "data_type": "string"}, {"name": "周期", "nullable": false, "data_type": "string"}, {"name": "金额", "scale": 2, "default": 0, "data_type": "decimal", "precision": 18}, {"name": "单号", "nullable": false, "data_type": "string"}, {"name": "费用项目", "nullable": true, "data_type": "string"}, {"name": "商户", "nullable": true, "data_type": "string"}, {"name": "填单人", "nullable": true, "data_type": "string"}], "primary_key": []}, "step_id": "step2_create_credit_usage", "description": "创建统计使用-贷方表", "target_table": "统计使用-贷方"}, {"action": "write_dataset", "sources": [{"alias": "credit_detail_source", "table": "贷方-收款单明细"}], "step_id": "step2_write_credit_usage", "mappings": [{"value": {"type": "source", "source": {"alias": "credit_detail_source", "field": "对应科目编码"}}, "target_field": "对应科目编码", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "credit_detail_source", "field": "对应科目"}}, "target_field": "对应科目", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "credit_detail_source", "field": "日期"}}, "target_field": "日期", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "credit_detail_source", "field": "公司名称"}}, "target_field": "公司名称", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "credit_detail_source", "field": "客商名称"}}, "target_field": "客商名称", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "credit_detail_source", "field": "中心"}}, "target_field": "中心", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "credit_detail_source", "field": "周期"}}, "target_field": "周期", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "credit_detail_source", "field": "金额"}}, "target_field": "金额", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "credit_detail_source", "field": "单号"}}, "target_field": "单号", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "credit_detail_source", "field": "费用项目"}}, "target_field": "费用项目", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "credit_detail_source", "field": "商户"}}, "target_field": "商户", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "credit_detail_source", "field": "填单人"}}, "target_field": "填单人", "field_write_mode": "overwrite"}], "depends_on": ["step1_finalize_check_table_balance", "step2_create_credit_usage"], "description": "按金蝶期末余额-检核匹配贷方明细，直接使用源文件中的中心和周期，生成统计使用-贷方", "target_table": "统计使用-贷方", "row_write_mode": "upsert", "reference_filter": {"keys": [{"source_field": "对应科目", "reference_field": "科目名称"}, {"source_field": "公司名称", "reference_field": "公司"}, {"source_field": "客商名称", "reference_field": "核算项目1"}], "source_alias": "credit_detail_source", "reference_table": "金蝶期末余额-检核"}}, {"action": "create_schema", "schema": {"columns": [{"name": "对应科目编码", "nullable": false, "data_type": "string"}, {"name": "对应科目", "nullable": false, "data_type": "string"}, {"name": "公司名称", "nullable": false, "data_type": "string"}, {"name": "客商名称", "nullable": false, "data_type": "string"}, {"name": "周期", "nullable": false, "data_type": "string"}, {"name": "中心", "nullable": false, "data_type": "string"}, {"name": "累计借方", "scale": 2, "default": 0, "data_type": "decimal", "precision": 18}, {"name": "累计贷方", "scale": 2, "default": 0, "data_type": "decimal", "precision": 18}, {"name": "累计调整-借", "scale": 2, "default": 0, "data_type": "decimal", "precision": 18}, {"name": "累计调整-贷", "scale": 2, "default": 0, "data_type": "decimal", "precision": 18}, {"name": "7月余额", "scale": 2, "default": 0, "data_type": "decimal", "precision": 18}, {"name": "逾期时间", "nullable": true, "data_type": "date"}, {"name": "计算余额", "scale": 2, "default": 0, "data_type": "decimal", "precision": 18}], "primary_key": ["对应科目编码", "对应科目", "公司名称", "客商名称", "周期", "中心"], "export_layout": {"fixed_columns": ["对应科目编码", "对应科目", "公司名称", "客商名称", "周期", "中心", "累计贷方", "累计借方", "累计调整-借", "累计调整-贷", "7月余额", "逾期时间", "计算余额"], "dynamic_groups": [{"end": {"args": {}, "type": "function", "function": "current_date"}, "start": {"args": {"offset": 1, "source": "统计使用-7月余额", "date_field": "日期"}, "type": "function", "function": "earliest_date"}, "columns": [{"header_template": "{month_end_date}", "source_template": "{month}月借"}, {"header": "调整-借", "source_template": "{month}月调整-借"}, {"header": "调整-贷", "source_template": "{month}月调整-贷"}, {"header": "逾期时间", "source_template": "{month}月逾期时间"}, {"header": "计算余额", "source_template": "{month}月计算余额"}], "dimension": "month"}]}, "dynamic_columns": {"end": {"args": {"date": {"args": {}, "type": "function", "function": "current_date"}}, "type": "function", "function": "month_of"}, "start": {"args": {"offset": 1, "source": "统计使用-7月余额", "date_field": "日期", "output_format": "month"}, "type": "function", "function": "earliest_date"}, "dimension": "month", "columns_pattern": [{"name": "{month}月借", "scale": 2, "default": 0, "data_type": "decimal", "precision": 18, "variables": {"month": {"name": "month", "type": "context"}}}, {"name": "{month}月贷", "scale": 2, "default": 0, "data_type": "decimal", "precision": 18, "variables": {"month": {"name": "month", "type": "context"}}}, {"name": "{month}月调整-借", "scale": 2, "default": 0, "data_type": "decimal", "precision": 18, "variables": {"month": {"name": "month", "type": "context"}}}, {"name": "{month}月调整-贷", "scale": 2, "default": 0, "data_type": "decimal", "precision": 18, "variables": {"month": {"name": "month", "type": "context"}}}, {"name": "{month}月逾期时间", "nullable": true, "data_type": "date", "variables": {"month": {"name": "month", "type": "context"}}}, {"name": "{month}月计算余额", "scale": 2, "default": 0, "data_type": "decimal", "precision": 18, "variables": {"month": {"name": "month", "type": "context"}}}]}}, "step_id": "step3_create_merged_statistics", "depends_on": ["step2_write_credit_usage"], "description": "创建统计合并表结构，并按月份生成动态列", "target_table": "统计合并"}, {"match": {"sources": [{"keys": [{"field": "对应科目编码", "target_field": "对应科目编码"}, {"field": "对应科目", "target_field": "对应科目"}, {"field": "公司名称", "target_field": "公司名称"}, {"field": "客商名称", "target_field": "客商名称"}, {"field": "周期", "target_field": "周期"}, {"field": "中心", "target_field": "中心"}], "alias": "july_balance_usage"}]}, "action": "write_dataset", "sources": [{"alias": "july_balance_usage", "table": "统计使用-7月余额"}], "step_id": "step3_seed_merged_keys_from_july_balance", "mappings": [{"value": {"type": "source", "source": {"alias": "july_balance_usage", "field": "对应科目编码"}}, "target_field": "对应科目编码", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "july_balance_usage", "field": "对应科目"}}, "target_field": "对应科目", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "july_balance_usage", "field": "公司名称"}}, "target_field": "公司名称", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "july_balance_usage", "field": "客商名称"}}, "target_field": "客商名称", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "july_balance_usage", "field": "周期"}}, "target_field": "周期", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "july_balance_usage", "field": "中心"}}, "target_field": "中心", "field_write_mode": "overwrite"}], "depends_on": ["step3_create_merged_statistics"], "description": "用统计使用-7月余额初始化统计合并业务键", "target_table": "统计合并", "row_write_mode": "upsert"}, {"match": {"sources": [{"keys": [{"field": "对应科目编码", "target_field": "对应科目编码"}, {"field": "对应科目", "target_field": "对应科目"}, {"field": "公司名称", "target_field": "公司名称"}, {"field": "客商名称", "target_field": "客商名称"}, {"field": "周期", "target_field": "周期"}, {"field": "中心", "target_field": "中心"}], "alias": "debit_usage"}]}, "action": "write_dataset", "sources": [{"alias": "debit_usage", "table": "统计使用-借方"}], "step_id": "step3_seed_merged_keys_from_debit_usage", "mappings": [{"value": {"type": "source", "source": {"alias": "debit_usage", "field": "对应科目编码"}}, "target_field": "对应科目编码", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "debit_usage", "field": "对应科目"}}, "target_field": "对应科目", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "debit_usage", "field": "公司名称"}}, "target_field": "公司名称", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "debit_usage", "field": "客商名称"}}, "target_field": "客商名称", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "debit_usage", "field": "周期"}}, "target_field": "周期", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "debit_usage", "field": "中心"}}, "target_field": "中心", "field_write_mode": "overwrite"}], "depends_on": ["step3_seed_merged_keys_from_july_balance", "step2_map_debit_center"], "description": "用统计使用-借方补充统计合并业务键", "target_table": "统计合并", "row_write_mode": "upsert"}, {"match": {"sources": [{"keys": [{"field": "对应科目编码", "target_field": "对应科目编码"}, {"field": "对应科目", "target_field": "对应科目"}, {"field": "公司名称", "target_field": "公司名称"}, {"field": "客商名称", "target_field": "客商名称"}, {"field": "周期", "target_field": "周期"}, {"field": "中心", "target_field": "中心"}], "alias": "credit_usage"}]}, "action": "write_dataset", "sources": [{"alias": "credit_usage", "table": "统计使用-贷方"}], "step_id": "step3_seed_merged_keys_from_credit_usage", "mappings": [{"value": {"type": "source", "source": {"alias": "credit_usage", "field": "对应科目编码"}}, "target_field": "对应科目编码", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "credit_usage", "field": "对应科目"}}, "target_field": "对应科目", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "credit_usage", "field": "公司名称"}}, "target_field": "公司名称", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "credit_usage", "field": "客商名称"}}, "target_field": "客商名称", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "credit_usage", "field": "周期"}}, "target_field": "周期", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "credit_usage", "field": "中心"}}, "target_field": "中心", "field_write_mode": "overwrite"}], "depends_on": ["step3_seed_merged_keys_from_debit_usage", "step2_map_credit_center"], "description": "用统计使用-贷方补充统计合并业务键", "target_table": "统计合并", "row_write_mode": "upsert"}, {"match": {"sources": [{"keys": [{"field": "科目编码", "target_field": "对应科目编码"}, {"field": "科目名称", "target_field": "对应科目"}, {"field": "公司", "target_field": "公司名称"}, {"field": "对方核算项目", "target_field": "客商名称"}, {"field": "周期", "target_field": "周期"}, {"field": "中心", "target_field": "中心"}], "alias": "adjustment_source"}]}, "action": "write_dataset", "sources": [{"alias": "adjustment_source", "table": "调整明细"}], "step_id": "step3_seed_merged_keys_from_adjustment", "mappings": [{"value": {"type": "source", "source": {"alias": "adjustment_source", "field": "科目编码"}}, "target_field": "对应科目编码", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "adjustment_source", "field": "科目名称"}}, "target_field": "对应科目", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "adjustment_source", "field": "公司"}}, "target_field": "公司名称", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "adjustment_source", "field": "对方核算项目"}}, "target_field": "客商名称", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "adjustment_source", "field": "周期"}}, "target_field": "周期", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "adjustment_source", "field": "中心"}}, "target_field": "中心", "field_write_mode": "overwrite"}], "depends_on": ["step3_seed_merged_keys_from_credit_usage"], "description": "用调整明细补充统计合并业务键", "target_table": "统计合并", "row_write_mode": "upsert", "reference_filter": {"keys": [{"source_field": "科目名称", "reference_field": "科目名称"}, {"source_field": "公司", "reference_field": "公司"}, {"source_field": "对方核算项目", "reference_field": "核算项目1"}], "source_alias": "adjustment_source", "reference_table": "金蝶期末余额-检核"}}, {"match": {"sources": [{"keys": [{"field": "对应科目编码", "target_field": "对应科目编码"}, {"field": "对应科目", "target_field": "对应科目"}, {"field": "公司名称", "target_field": "公司名称"}, {"field": "客商名称", "target_field": "客商名称"}, {"field": "周期", "target_field": "周期"}, {"field": "中心", "target_field": "中心"}], "alias": "debit_usage_agg"}]}, "action": "write_dataset", "sources": [{"alias": "debit_usage", "table": "统计使用-借方"}], "step_id": "step3_fill_cumulative_debit", "mappings": [{"value": {"type": "source", "source": {"alias": "debit_usage_agg", "field": "agg_累计借方"}}, "target_field": "累计借方", "field_write_mode": "overwrite"}], "aggregate": [{"aggregations": [{"alias": "agg_累计借方", "field": "含税金额", "operator": "sum"}], "group_fields": ["对应科目编码", "对应科目", "公司名称", "客商名称", "周期", "中心"], "output_alias": "debit_usage_agg", "source_alias": "debit_usage"}], "depends_on": ["step3_seed_merged_keys_from_adjustment"], "description": "聚合统计使用-借方，回填累计借方", "target_table": "统计合并", "row_write_mode": "update_only"}, {"match": {"sources": [{"keys": [{"field": "对应科目编码", "target_field": "对应科目编码"}, {"field": "对应科目", "target_field": "对应科目"}, {"field": "公司名称", "target_field": "公司名称"}, {"field": "客商名称", "target_field": "客商名称"}, {"field": "周期", "target_field": "周期"}, {"field": "中心", "target_field": "中心"}], "alias": "credit_usage_agg"}]}, "action": "write_dataset", "sources": [{"alias": "credit_usage", "table": "统计使用-贷方"}], "step_id": "step3_fill_cumulative_credit", "mappings": [{"value": {"type": "source", "source": {"alias": "credit_usage_agg", "field": "agg_累计贷方"}}, "target_field": "累计贷方", "field_write_mode": "overwrite"}], "aggregate": [{"aggregations": [{"alias": "agg_累计贷方", "field": "金额", "operator": "sum"}], "group_fields": ["对应科目编码", "对应科目", "公司名称", "客商名称", "周期", "中心"], "output_alias": "credit_usage_agg", "source_alias": "credit_usage"}], "depends_on": ["step3_fill_cumulative_debit"], "description": "聚合统计使用-贷方，回填累计贷方", "target_table": "统计合并", "row_write_mode": "update_only"}, {"match": {"sources": [{"keys": [{"field": "科目编码", "target_field": "对应科目编码"}, {"field": "科目名称", "target_field": "对应科目"}, {"field": "公司", "target_field": "公司名称"}, {"field": "对方核算项目", "target_field": "客商名称"}, {"field": "周期", "target_field": "周期"}, {"field": "中心", "target_field": "中心"}], "alias": "adjustment_agg"}]}, "action": "write_dataset", "sources": [{"alias": "adjustment_source", "table": "调整明细"}], "step_id": "step3_fill_cumulative_adjustment", "mappings": [{"value": {"type": "source", "source": {"alias": "adjustment_agg", "field": "agg_累计调整借"}}, "target_field": "累计调整-借", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "adjustment_agg", "field": "agg_累计调整贷"}}, "target_field": "累计调整-贷", "field_write_mode": "overwrite"}], "aggregate": [{"aggregations": [{"alias": "agg_累计调整借", "field": "借方", "operator": "sum"}, {"alias": "agg_累计调整贷", "field": "贷方", "operator": "sum"}], "group_fields": ["科目编码", "科目名称", "公司", "对方核算项目", "周期", "中心"], "output_alias": "adjustment_agg", "source_alias": "adjustment_source"}], "depends_on": ["step3_fill_cumulative_credit"], "description": "聚合调整明细，回填累计调整借贷", "target_table": "统计合并", "row_write_mode": "update_only", "reference_filter": {"keys": [{"source_field": "科目名称", "reference_field": "科目名称"}, {"source_field": "公司", "reference_field": "公司"}, {"source_field": "对方核算项目", "reference_field": "核算项目1"}], "source_alias": "adjustment_source", "reference_table": "金蝶期末余额-检核"}}, {"match": {"sources": [{"keys": [{"field": "对应科目编码", "target_field": "对应科目编码"}, {"field": "对应科目", "target_field": "对应科目"}, {"field": "公司名称", "target_field": "公司名称"}, {"field": "客商名称", "target_field": "客商名称"}, {"field": "周期", "target_field": "周期"}, {"field": "中心", "target_field": "中心"}], "alias": "july_balance_agg"}]}, "action": "write_dataset", "sources": [{"alias": "july_balance_usage", "table": "统计使用-7月余额"}], "step_id": "step3_fill_july_balance", "mappings": [{"value": {"type": "source", "source": {"alias": "july_balance_agg", "field": "agg_7月余额"}}, "target_field": "7月余额", "field_write_mode": "overwrite"}], "aggregate": [{"aggregations": [{"alias": "agg_7月余额", "field": "期末余额", "operator": "sum"}], "group_fields": ["对应科目编码", "对应科目", "公司名称", "客商名称", "周期", "中心"], "output_alias": "july_balance_agg", "source_alias": "july_balance_usage"}], "depends_on": ["step3_fill_cumulative_adjustment"], "description": "聚合统计使用-7月余额，回填7月余额", "target_table": "统计合并", "row_write_mode": "update_only"}, {"match": {"sources": [{"keys": [{"field": "对应科目编码", "target_field": "对应科目编码"}, {"field": "对应科目", "target_field": "对应科目"}, {"field": "公司名称", "target_field": "公司名称"}, {"field": "客商名称", "target_field": "客商名称"}, {"field": "周期", "target_field": "周期"}, {"field": "中心", "target_field": "中心"}], "alias": "july_overdue_agg"}]}, "action": "write_dataset", "sources": [{"alias": "july_balance_usage", "table": "统计使用-7月余额"}], "step_id": "step3_fill_overdue_time", "mappings": [{"value": {"type": "source", "source": {"alias": "july_overdue_agg", "field": "agg_7月逾期时间"}}, "target_field": "逾期时间", "field_write_mode": "overwrite"}], "aggregate": [{"aggregations": [{"alias": "agg_7月逾期时间", "field": "预计回款时间", "operator": "min"}], "group_fields": ["对应科目编码", "对应科目", "公司名称", "客商名称", "周期", "中心"], "output_alias": "july_overdue_agg", "source_alias": "july_balance_usage"}], "depends_on": ["step3_fill_july_balance"], "description": "聚合统计使用-7月余额，回填7月逾期时间", "target_table": "统计合并", "row_write_mode": "update_only"}, {"match": {"sources": [{"keys": [{"field": "对应科目编码", "target_field": "对应科目编码"}, {"field": "对应科目", "target_field": "对应科目"}, {"field": "公司名称", "target_field": "公司名称"}, {"field": "客商名称", "target_field": "客商名称"}, {"field": "周期", "target_field": "周期"}, {"field": "中心", "target_field": "中心"}], "alias": "debit_monthly_agg"}]}, "action": "write_dataset", "sources": [{"alias": "debit_usage", "table": "统计使用-借方"}], "step_id": "step3_fill_dynamic_debit_columns", "mappings": [{"value": {"type": "source", "source": {"alias": "debit_monthly_agg", "field": "agg_月借"}}, "field_write_mode": "overwrite", "target_field_template": {"template": "{month}月借", "variables": {"month": {"args": {"date": {"type": "source", "source": {"alias": "debit_monthly_agg", "field": "日期"}}}, "type": "function", "function": "month_of"}}}}, {"value": {"type": "source", "source": {"alias": "debit_monthly_agg", "field": "agg_月逾期时间"}}, "field_write_mode": "overwrite", "target_field_template": {"template": "{month}月逾期时间", "variables": {"month": {"args": {"date": {"type": "source", "source": {"alias": "debit_monthly_agg", "field": "日期"}}}, "type": "function", "function": "month_of"}}}}], "aggregate": [{"aggregations": [{"alias": "agg_月借", "field": "含税金额", "operator": "sum"}, {"alias": "agg_月逾期时间", "field": "逾期时间", "operator": "min"}], "group_fields": ["对应科目编码", "对应科目", "公司名称", "客商名称", "周期", "中心", "日期"], "output_alias": "debit_monthly_agg", "source_alias": "debit_usage"}], "depends_on": ["step3_fill_overdue_time"], "description": "按月聚合统计使用-借方，回填月借和月逾期时间", "target_table": "统计合并", "row_write_mode": "update_only"}, {"match": {"sources": [{"keys": [{"field": "对应科目编码", "target_field": "对应科目编码"}, {"field": "对应科目", "target_field": "对应科目"}, {"field": "公司名称", "target_field": "公司名称"}, {"field": "客商名称", "target_field": "客商名称"}, {"field": "周期", "target_field": "周期"}, {"field": "中心", "target_field": "中心"}], "alias": "credit_monthly_agg"}]}, "action": "write_dataset", "sources": [{"alias": "credit_usage", "table": "统计使用-贷方"}], "step_id": "step3_fill_dynamic_credit_columns", "mappings": [{"value": {"type": "source", "source": {"alias": "credit_monthly_agg", "field": "agg_月贷"}}, "field_write_mode": "overwrite", "target_field_template": {"template": "{month}月贷", "variables": {"month": {"args": {"date": {"type": "source", "source": {"alias": "credit_monthly_agg", "field": "日期"}}}, "type": "function", "function": "month_of"}}}}], "aggregate": [{"aggregations": [{"alias": "agg_月贷", "field": "金额", "operator": "sum"}], "group_fields": ["对应科目编码", "对应科目", "公司名称", "客商名称", "周期", "中心", "日期"], "output_alias": "credit_monthly_agg", "source_alias": "credit_usage"}], "depends_on": ["step3_fill_dynamic_debit_columns"], "description": "按月聚合统计使用-贷方，回填月贷", "target_table": "统计合并", "row_write_mode": "update_only"}, {"match": {"sources": [{"keys": [{"field": "科目编码", "target_field": "对应科目编码"}, {"field": "科目名称", "target_field": "对应科目"}, {"field": "公司", "target_field": "公司名称"}, {"field": "对方核算项目", "target_field": "客商名称"}, {"field": "周期", "target_field": "周期"}, {"field": "中心", "target_field": "中心"}], "alias": "adjustment_monthly_agg"}]}, "action": "write_dataset", "sources": [{"alias": "adjustment_source", "table": "调整明细"}], "step_id": "step3_fill_dynamic_adjustment_columns", "mappings": [{"value": {"type": "source", "source": {"alias": "adjustment_monthly_agg", "field": "agg_月调整借"}}, "field_write_mode": "overwrite", "target_field_template": {"template": "{month}月调整-借", "variables": {"month": {"args": {"date": {"type": "source", "source": {"alias": "adjustment_monthly_agg", "field": "业务日期"}}}, "type": "function", "function": "month_of"}}}}, {"value": {"type": "source", "source": {"alias": "adjustment_monthly_agg", "field": "agg_月调整贷"}}, "field_write_mode": "overwrite", "target_field_template": {"template": "{month}月调整-贷", "variables": {"month": {"args": {"date": {"type": "source", "source": {"alias": "adjustment_monthly_agg", "field": "业务日期"}}}, "type": "function", "function": "month_of"}}}}], "aggregate": [{"aggregations": [{"alias": "agg_月调整借", "field": "借方", "operator": "sum"}, {"alias": "agg_月调整贷", "field": "贷方", "operator": "sum"}], "group_fields": ["科目编码", "科目名称", "公司", "对方核算项目", "周期", "中心", "业务日期"], "output_alias": "adjustment_monthly_agg", "source_alias": "adjustment_source"}], "depends_on": ["step3_fill_dynamic_credit_columns"], "description": "按月聚合调整明细，回填月调整借贷", "target_table": "统计合并", "row_write_mode": "update_only", "reference_filter": {"keys": [{"source_field": "科目名称", "reference_field": "科目名称"}, {"source_field": "公司", "reference_field": "公司"}, {"source_field": "对方核算项目", "reference_field": "核算项目1"}], "source_alias": "adjustment_source", "reference_table": "金蝶期末余额-检核"}}, {"match": {"sources": [{"keys": [{"field": "对应科目编码", "target_field": "对应科目编码"}, {"field": "对应科目", "target_field": "对应科目"}, {"field": "公司名称", "target_field": "公司名称"}, {"field": "客商名称", "target_field": "客商名称"}, {"field": "周期", "target_field": "周期"}, {"field": "中心", "target_field": "中心"}], "alias": "merged_statistics"}]}, "action": "write_dataset", "sources": [{"alias": "merged_statistics", "table": "统计合并"}], "step_id": "step3_calculate_dynamic_balance", "depends_on": ["step3_fill_dynamic_adjustment_columns"], "description": "按月计算统计合并的月度计算余额", "target_table": "统计合并", "row_write_mode": "update_only", "dynamic_mappings": {"end": {"args": {"date": {"args": {}, "type": "function", "function": "current_date"}}, "type": "function", "function": "month_of"}, "start": {"args": {"offset": 1, "source": "统计使用-7月余额", "date_field": "日期", "output_format": "month"}, "type": "function", "function": "earliest_date"}, "mappings": [{"value": {"expr": "{is_first_month} ? ({july_balance} - {cumulative_credit}) : ({previous_month_balance} + {current_month_debit} + {current_month_adjust_debit} - {current_month_adjust_credit})", "type": "formula"}, "bindings": {"july_balance": {"type": "source", "source": {"alias": "merged_statistics", "field": "7月余额"}}, "is_first_month": {"name": "is_first_month", "type": "context"}, "cumulative_credit": {"type": "source", "source": {"alias": "merged_statistics", "field": "累计贷方"}}, "current_month_debit": {"type": "template_source", "source": {"alias": "merged_statistics"}, "default": 0, "template": "{month}月借", "variables": {"month": {"name": "month", "type": "context"}}}, "previous_month_balance": {"type": "template_source", "source": {"alias": "merged_statistics"}, "default": 0, "template": "{prev_month}月计算余额", "variables": {"prev_month": {"name": "prev_month", "type": "context"}}}, "current_month_adjust_debit": {"type": "template_source", "source": {"alias": "merged_statistics"}, "default": 0, "template": "{month}月调整-借", "variables": {"month": {"name": "month", "type": "context"}}}, "current_month_adjust_credit": {"type": "template_source", "source": {"alias": "merged_statistics"}, "default": 0, "template": "{month}月调整-贷", "variables": {"month": {"name": "month", "type": "context"}}}}, "field_write_mode": "overwrite", "target_field_template": {"template": "{month}月计算余额", "variables": {"month": {"name": "month", "type": "context"}}}}], "dimension": "month"}}, {"match": {"sources": [{"keys": [{"field": "对应科目编码", "target_field": "对应科目编码"}, {"field": "对应科目", "target_field": "对应科目"}, {"field": "公司名称", "target_field": "公司名称"}, {"field": "客商名称", "target_field": "客商名称"}, {"field": "周期", "target_field": "周期"}, {"field": "中心", "target_field": "中心"}], "alias": "merged_statistics"}]}, "action": "write_dataset", "sources": [{"alias": "merged_statistics", "table": "统计合并"}], "step_id": "step3_finalize_current_balance", "mappings": [{"value": {"expr": "{july_balance} - {cumulative_credit}", "type": "formula"}, "bindings": {"july_balance": {"type": "source", "source": {"alias": "merged_statistics", "field": "7月余额"}}, "cumulative_credit": {"type": "source", "source": {"alias": "merged_statistics", "field": "累计贷方"}}}, "target_field": "计算余额", "field_write_mode": "overwrite"}], "depends_on": ["step3_calculate_dynamic_balance"], "description": "回填7月计算余额", "target_table": "统计合并", "row_write_mode": "update_only"}, {"action": "create_schema", "schema": {"columns": [{"name": "对应科目编码", "nullable": false, "data_type": "string"}, {"name": "对应科目", "nullable": false, "data_type": "string"}, {"name": "公司名称", "nullable": false, "data_type": "string"}, {"name": "客商名称", "nullable": false, "data_type": "string"}, {"name": "周期", "nullable": false, "data_type": "string"}, {"name": "中心", "nullable": false, "data_type": "string"}, {"name": "计算余额", "scale": 2, "default": 0, "data_type": "decimal", "precision": 18}, {"name": "逾期合计", "scale": 2, "default": 0, "data_type": "decimal", "precision": 18}, {"name": "逾期金额", "scale": 2, "default": 0, "data_type": "decimal", "precision": 18}, {"name": "7月逾期", "scale": 2, "default": 0, "data_type": "decimal", "precision": 18}], "primary_key": ["对应科目编码", "对应科目", "公司名称", "客商名称", "周期", "中心"], "dynamic_columns": {"end": {"args": {"date": {"args": {}, "type": "function", "function": "current_date"}}, "type": "function", "function": "month_of"}, "start": {"args": {"offset": 1, "source": "统计使用-7月余额", "date_field": "日期", "output_format": "month"}, "type": "function", "function": "earliest_date"}, "dimension": "month", "columns_pattern": [{"name": "{month}月逾期", "scale": 2, "default": 0, "data_type": "decimal", "precision": 18, "variables": {"month": {"name": "month", "type": "context"}}}]}}, "step_id": "step4_create_overdue_statistics", "depends_on": ["step3_finalize_current_balance"], "description": "创建逾期统计表结构", "target_table": "逾期统计"}, {"match": {"sources": [{"keys": [{"field": "对应科目编码", "target_field": "对应科目编码"}, {"field": "对应科目", "target_field": "对应科目"}, {"field": "公司名称", "target_field": "公司名称"}, {"field": "客商名称", "target_field": "客商名称"}, {"field": "周期", "target_field": "周期"}, {"field": "中心", "target_field": "中心"}], "alias": "merged_statistics"}]}, "action": "write_dataset", "filter": {"expr": "{current_balance} > 0 and {overdue_time} < {today}", "type": "formula", "bindings": {"today": {"args": {}, "type": "function", "function": "current_date"}, "overdue_time": {"type": "source", "source": {"alias": "merged_statistics", "field": "逾期时间"}}, "current_balance": {"type": "source", "source": {"alias": "merged_statistics", "field": "计算余额"}}}}, "sources": [{"alias": "merged_statistics", "table": "统计合并"}], "step_id": "step4_sync_overdue_base", "mappings": [{"value": {"type": "source", "source": {"alias": "merged_statistics", "field": "对应科目编码"}}, "target_field": "对应科目编码", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "merged_statistics", "field": "对应科目"}}, "target_field": "对应科目", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "merged_statistics", "field": "公司名称"}}, "target_field": "公司名称", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "merged_statistics", "field": "客商名称"}}, "target_field": "客商名称", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "merged_statistics", "field": "周期"}}, "target_field": "周期", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "merged_statistics", "field": "中心"}}, "target_field": "中心", "field_write_mode": "overwrite"}, {"value": {"type": "source", "source": {"alias": "merged_statistics", "field": "计算余额"}}, "target_field": "计算余额", "field_write_mode": "overwrite"}, {"value": {"expr": "{july_balance} <= 0 or is_null({overdue_time}) or {overdue_time} >= {today} ? 0 : {july_balance}", "type": "formula"}, "bindings": {"today": {"args": {}, "type": "function", "function": "current_date"}, "july_balance": {"type": "source", "source": {"alias": "merged_statistics", "field": "7月余额"}}, "overdue_time": {"type": "source", "source": {"alias": "merged_statistics", "field": "逾期时间"}}}, "target_field": "7月逾期", "field_write_mode": "overwrite"}, {"value": {"expr": "{july_balance} <= 0 or is_null({overdue_time}) or {overdue_time} >= {today} ? 0 : {july_balance}", "type": "formula"}, "bindings": {"today": {"args": {}, "type": "function", "function": "current_date"}, "july_balance": {"type": "source", "source": {"alias": "merged_statistics", "field": "7月余额"}}, "overdue_time": {"type": "source", "source": {"alias": "merged_statistics", "field": "逾期时间"}}}, "target_field": "逾期合计", "field_write_mode": "overwrite"}], "depends_on": ["step4_create_overdue_statistics"], "description": "筛选统计合并中已逾期且计算余额大于0的数据，写入逾期统计基础字段", "target_table": "逾期统计", "row_write_mode": "upsert"}, {"match": {"sources": [{"keys": [{"field": "对应科目编码", "target_field": "对应科目编码"}, {"field": "对应科目", "target_field": "对应科目"}, {"field": "公司名称", "target_field": "公司名称"}, {"field": "客商名称", "target_field": "客商名称"}, {"field": "周期", "target_field": "周期"}, {"field": "中心", "target_field": "中心"}], "alias": "merged_statistics"}]}, "action": "write_dataset", "sources": [{"alias": "merged_statistics", "table": "统计合并"}], "step_id": "step4_fill_dynamic_monthly_overdue", "depends_on": ["step4_sync_overdue_base"], "description": "逐月判断逾期金额，回填月逾期并累加逾期合计", "target_table": "逾期统计", "row_write_mode": "update_only", "dynamic_mappings": {"end": {"args": {"date": {"args": {}, "type": "function", "function": "current_date"}}, "type": "function", "function": "month_of"}, "start": {"args": {"offset": 1, "source": "统计使用-7月余额", "date_field": "日期", "output_format": "month"}, "type": "function", "function": "earliest_date"}, "mappings": [{"value": {"expr": "{month_balance} <= 0 or is_null({month_overdue_time}) or {month_overdue_time} >= {today} ? 0 : {month_balance}", "type": "formula"}, "bindings": {"today": {"args": {}, "type": "function", "function": "current_date"}, "month_balance": {"type": "template_source", "source": {"alias": "merged_statistics"}, "default": 0, "template": "{month}月计算余额", "variables": {"month": {"name": "month", "type": "context"}}}, "month_overdue_time": {"type": "template_source", "source": {"alias": "merged_statistics"}, "template": "{month}月逾期时间", "variables": {"month": {"name": "month", "type": "context"}}}}, "field_write_mode": "overwrite", "target_field_template": {"template": "{month}月逾期", "variables": {"month": {"name": "month", "type": "context"}}}}, {"value": {"expr": "{month_balance} <= 0 or is_null({month_overdue_time}) or {month_overdue_time} >= {today} ? 0 : {month_balance}", "type": "formula"}, "bindings": {"today": {"args": {}, "type": "function", "function": "current_date"}, "month_balance": {"type": "template_source", "source": {"alias": "merged_statistics"}, "default": 0, "template": "{month}月计算余额", "variables": {"month": {"name": "month", "type": "context"}}}, "month_overdue_time": {"type": "template_source", "source": {"alias": "merged_statistics"}, "template": "{month}月逾期时间", "variables": {"month": {"name": "month", "type": "context"}}}}, "target_field": "逾期合计", "field_write_mode": "increment"}], "dimension": "month"}}, {"match": {"sources": [{"keys": [{"field": "对应科目编码", "target_field": "对应科目编码"}, {"field": "对应科目", "target_field": "对应科目"}, {"field": "公司名称", "target_field": "公司名称"}, {"field": "客商名称", "target_field": "客商名称"}, {"field": "周期", "target_field": "周期"}, {"field": "中心", "target_field": "中心"}], "alias": "overdue_statistics"}]}, "action": "write_dataset", "sources": [{"alias": "overdue_statistics", "table": "逾期统计"}], "step_id": "step4_finalize_overdue_amount", "mappings": [{"value": {"expr": "{balance} - {overdue_total} <= 0 ? {balance} : {overdue_total}", "type": "formula"}, "bindings": {"balance": {"type": "source", "source": {"alias": "overdue_statistics", "field": "计算余额"}}, "overdue_total": {"type": "source", "source": {"alias": "overdue_statistics", "field": "逾期合计"}}}, "target_field": "逾期金额", "field_write_mode": "overwrite"}], "depends_on": ["step4_fill_dynamic_monthly_overdue"], "description": "根据计算余额与逾期合计关系回填最终逾期金额", "target_table": "逾期统计", "row_write_mode": "update_only"}], "version": "5.0", "metadata": {"tags": ["财务核算", "数据整理", "逾期统计", "聚合分析"], "author": "codex", "created_at": "2026-03-25T19:10:00+08:00"}, "role_desc": "逾期统计数据整理规则", "global_config": {"date_format": "YYYY-MM-DD", "error_handling": "stop", "null_value_handling": "keep", "default_round_precision": 2}, "file_rule_code": "overdue_file_check", "dsl_constraints": {"actions": ["create_schema", "write_dataset"], "row_write_modes": ["insert_if_missing", "update_only", "upsert"], "merge_strategies": ["union_distinct"], "value_node_types": ["source", "formula", "template_source", "function", "context", "lookup"], "builtin_functions": ["earliest_date", "current_date", "month_of", "add_months", "fraction_numerator"], "column_data_types": ["string", "date", "decimal"], "field_write_modes": ["overwrite", "increment"], "loop_context_vars": ["month", "prev_month", "is_first_month"], "aggregate_operators": ["sum", "min"]}}', '逾期统计数据整理规则', 'proc', NULL, '逾期统计数据整理', 3);


--
-- Name: admins_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.admins_id_seq', 1, true);


--
-- PostgreSQL database dump complete
--

