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

INSERT INTO public.admins VALUES (1, 'admin', '92925488b28ab12584ac8fcaa8a27a0f497b2c62940c8f4fbc8ef19ebc87c43e', '2026-02-19 10:27:27.267257');


--
-- Data for Name: company; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.company VALUES ('00000000-0000-0000-0000-000000000001', '示例公司', 'DEMO_COMPANY', 1000, 100, '["reconciliation", "data_prep"]', '2026-02-10 16:11:16.32517+08', '2026-02-10 16:11:16.32517+08', 'active');
INSERT INTO public.company VALUES ('ef39a863-6ab7-4f99-bb78-236170d38117', '武汉岚晨网络科技有限公司', 'COMP_83035BAF', 100, 10, '["reconciliation", "data_prep"]', '2026-02-19 16:30:56.871353+08', '2026-02-25 10:18:15.898601+08', 'active');


--
-- Data for Name: departments; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.departments VALUES ('00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', NULL, '财务部', 'FINANCE', '财务对账部门', '{}', '2026-02-10 16:11:16.327623+08', '2026-02-10 16:11:16.327623+08');
INSERT INTO public.departments VALUES ('063eae86-62ee-43f9-ac81-7776c25ecb7c', 'ef39a863-6ab7-4f99-bb78-236170d38117', NULL, '资产部', 'DEPT_3EF4E97B', NULL, '{}', '2026-02-19 16:31:29.88011+08', '2026-02-25 10:18:30.09625+08');
INSERT INTO public.departments VALUES ('4a0127f2-98ae-4769-a9c1-5de3334af801', 'ef39a863-6ab7-4f99-bb78-236170d38117', NULL, '核算部', 'DEPT_7CD78C2B', NULL, '{}', '2026-02-19 16:40:06.467791+08', '2026-02-25 10:18:30.09625+08');


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.users VALUES ('00000000-0000-0000-0000-000000000001', 'system', '', 'system@tally.local', NULL, NULL, NULL, 'admin', '2026-02-12 16:20:15.777487+08', '2026-02-12 16:20:15.777487+08', NULL, 'active');
INSERT INTO public.users VALUES ('3b593fbd-d0cd-48b8-99f1-fd9274f4059d', 'testuser', '$2b$12$eMoYGYTk1cBXupBiYXk5he8PG56Fyb8t2TpFCVovKcQrnWJdg0VKG', NULL, NULL, '00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', 'member', '2026-02-12 17:08:15.240684+08', '2026-02-12 17:08:15.240684+08', NULL, 'active');
INSERT INTO public.users VALUES ('8416371f-95f9-4454-b516-a20d434ca79c', 'testuser_828796', '$2b$12$aortAUQny0vsJFcFfFkJ4edAzrphidZX1pRDsb6y3D.CD1AeD9B.q', NULL, NULL, NULL, NULL, 'member', '2026-02-13 11:20:30.039084+08', '2026-02-13 11:24:06.561373+08', '2026-02-13 11:24:06.561373+08', 'active');
INSERT INTO public.users VALUES ('85a817b0-9fdb-4281-89e1-220ee539373c', 'testuser_1770953046_7807', '$2b$12$avN29IEdT0T1c.16NOFkGOC2XJpew5ziRJQxVBja7jjMUdlVWDZda', 'testuser_1770953046_7807@test.com', '13800000000', NULL, NULL, 'member', '2026-02-13 11:24:06.954359+08', '2026-02-13 11:24:06.954359+08', NULL, 'active');
INSERT INTO public.users VALUES ('dbcc40a1-1a3f-4da9-a726-76e3b1e29e0b', 'user_1770953127_9395', '$2b$12$MF1isplyh9RcLJAt4L8tzOw/Vgjpyk1dJkZyekDhej.Ssafd9CVH.', 'user_1770953127_9395@example.com', '13800000000', NULL, NULL, 'member', '2026-02-13 11:25:28.940015+08', '2026-02-13 11:25:31.71581+08', '2026-02-13 11:25:31.71581+08', 'active');
INSERT INTO public.users VALUES ('00000000-0000-0000-0000-000000000003', 'admin', '$2a$06$8jR7WzRe5E3upJmmCtIPyOfArPX1k8140YBJ/rZIe6nr6k4hG3Tna', 'admin@example.com', NULL, '00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', 'admin', '2026-02-10 16:11:16.330406+08', '2026-02-25 09:27:37.873784+08', '2026-02-25 09:27:37.873784+08', 'active');
INSERT INTO public.users VALUES ('869405c8-4cdf-4137-ab53-c9fd98796293', 'financer', '$2b$12$KaYrIUU/AA0YT6BfLEaJVOgCi0.OpG/A8f5JQyjb.YpgLfD4PPPDO', 'financer@lanchen.com', '15020302832', '4a0127f2-98ae-4769-a9c1-5de3334af801', 'ef39a863-6ab7-4f99-bb78-236170d38117', 'member', '2026-02-19 16:43:43.320509+08', '2026-02-19 16:43:43.320509+08', NULL, 'active');


--
-- Data for Name: audit_logs; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: conversations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.conversations VALUES ('9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', '00000000-0000-0000-0000-000000000003', '你好', '2026-02-25 09:38:49.018524', '2026-02-25 10:28:12.798989', 'active');


--
-- Data for Name: messages; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.messages VALUES ('740b3a46-15e9-4131-b867-6e6a7f016404', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'user', '你好', '{}', '[]', '2026-02-25 09:38:49.045634');
INSERT INTO public.messages VALUES ('2242a22c-fc90-4e56-a8ef-7925df4431de', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '你好，admin！

我是专业的财务对账助手，可以帮助你完成以下工作：
1. **执行对账**：使用已有的对账规则快速对账
2. **创建规则**：引导你创建新的对账规则
3. **编辑规则**：调整已有规则的字段映射、配置等
4. **删除规则**：删除不需要的对账规则
5. **查看规则列表**：列出所有已创建的对账规则
6. **理解对账结果**：帮助你分析和解释对账结果

当前已有的对账规则包括：
- 喜马（喜马）
- 腾讯异业（腾讯异业）
- 西福（西福）

请问你需要什么帮助？', '{}', '[]', '2026-02-25 09:38:49.070981');
INSERT INTO public.messages VALUES ('2187f401-6918-456f-9b2c-4961e0b060af', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'user', '你好', '{}', '[]', '2026-02-25 09:39:13.424614');
INSERT INTO public.messages VALUES ('616f2c98-1589-42b5-a9a6-ada87a31c269', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '你好，admin！

我是专业的财务对账助手，可以帮助你完成以下工作：
1. **执行对账**：使用已有的对账规则快速对账
2. **创建规则**：引导你创建新的对账规则
3. **编辑规则**：调整已有规则的字段映射、配置等
4. **删除规则**：删除不需要的对账规则
5. **查看规则列表**：列出所有已创建的对账规则
6. **理解对账结果**：帮助你分析和解释对账结果

当前已有的对账规则包括：
- 喜马（喜马）
- 腾讯异业（腾讯异业）
- 西福（西福）

请问你需要什么帮助？', '{}', '[]', '2026-02-25 09:39:13.448352');
INSERT INTO public.messages VALUES ('372fc992-cfd5-44ed-a5a9-e8bf9d835af0', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'user', '创建规则', '{}', '[]', '2026-02-25 09:39:29.01492');
INSERT INTO public.messages VALUES ('805bc68f-e902-49c6-a3cf-f1d0eddb8441', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '🎯 开始创建新的对账规则

我会引导你完成以下4个步骤：

1️⃣ 上传并分析文件 - 分析文件结构和列名
2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）
3️⃣ 配置规则参数 - 设置容差、订单号特征等
4️⃣ 预览并保存 - 查看规则效果并保存

请先上传需要对账的文件（业务数据和财务数据各一个 Excel/CSV 文件）。', '{}', '[]', '2026-02-25 09:39:29.03876');
INSERT INTO public.messages VALUES ('4aebf402-00a8-48b8-84b4-6691a1508e4f', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'user', '已上传 2 个文件，请处理。', '{}', '[{"name": null, "path": "/uploads/2026/2/25/1767597466118_093934.csv", "size": 0}, {"name": null, "path": "/uploads/2026/2/25/ads_finance_d_inc_channel_details_20260105152012277_0_093935.csv", "size": 0}]', '2026-02-25 09:39:42.584161');
INSERT INTO public.messages VALUES ('db8887fe-364d-4438-a836-7ceb37baf18e', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '🎯 开始创建新的对账规则

我会引导你完成以下4个步骤：

1️⃣ 上传并分析文件 - 分析文件结构和列名
2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）
3️⃣ 配置规则参数 - 设置容差、订单号特征等
4️⃣ 预览并保存 - 查看规则效果并保存

请先上传需要对账的文件（业务数据和财务数据各一个 Excel/CSV 文件）。', '{}', '[]', '2026-02-25 09:39:42.608422');
INSERT INTO public.messages VALUES ('5756a0a1-533a-4ebd-a854-0b8b47cd8765', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '📊 **第1步：文件分析完成**

📄 **1767597466118_093934.csv**
   • 列数: 17  行数: 985
   • 列名: 订单编号, sp订单号, 商品编号, 商品名称, 充值账号, 面值, 购买数量, 销售额, 成本, 利润...

📄 **ads_finance_d_inc_channel_details_20260105152012277_0_093935.csv**
   • 列数: 20  行数: 976
   • 列名: 完成时间, 提交时间, 订单来源, 订单号, sup订单号, 合单订单号, 订单类型, 结算类型, 渠道所属公司, 渠道供应商...

正在为你生成字段映射建议...', '{}', '[]', '2026-02-25 09:39:42.630879');
INSERT INTO public.messages VALUES ('1164eec8-c429-46db-815c-d489599e5b80', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '你好，admin！

我是专业的财务对账助手，可以帮助你完成以下工作：
1. **执行对账**：使用已有的对账规则快速对账
2. **创建规则**：引导你创建新的对账规则
3. **编辑规则**：调整已有规则的字段映射、配置等
4. **删除规则**：删除不需要的对账规则
5. **查看规则列表**：列出所有已创建的对账规则
6. **理解对账结果**：帮助你分析和解释对账结果

当前已有的对账规则包括：
- 喜马（喜马）
- 腾讯异业（腾讯异业）
- 西福（西福）

请问你需要什么帮助？', '{}', '[]', '2026-02-25 09:39:42.656367');
INSERT INTO public.messages VALUES ('8c5fe3cc-1ab9-401e-b213-0b4ddb4271b9', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'user', '1', '{}', '[{"name": null, "path": "/uploads/2026/2/25/1767597466118_093934.csv", "size": 0}, {"name": null, "path": "/uploads/2026/2/25/ads_finance_d_inc_channel_details_20260105152012277_0_093935.csv", "size": 0}]', '2026-02-25 09:39:59.682195');
INSERT INTO public.messages VALUES ('708ee1cd-20ae-4650-9a10-c9d2fad0d79a', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '📊 **第1步：文件分析完成**

📄 **1767597466118_093934.csv**
   • 列数: 17  行数: 985
   • 列名: 订单编号, sp订单号, 商品编号, 商品名称, 充值账号, 面值, 购买数量, 销售额, 成本, 利润...

📄 **ads_finance_d_inc_channel_details_20260105152012277_0_093935.csv**
   • 列数: 20  行数: 976
   • 列名: 完成时间, 提交时间, 订单来源, 订单号, sup订单号, 合单订单号, 订单类型, 结算类型, 渠道所属公司, 渠道供应商...

正在为你生成字段映射建议...', '{}', '[]', '2026-02-25 09:39:59.709019');
INSERT INTO public.messages VALUES ('be54c8ad-1a39-467c-9aae-e8251c94444e', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '✅ 已选择规则「西福」

📋 **字段映射**
业务: date→订单时间, amount→销售额, status→状态, order_id→[''sp订单号'']
财务: date→完成时间, amount→发生-, status→None, order_id→[''sup订单号'']

⚙️ **规则配置**
默认规则

此规则进行对请确认是否采用账？
（回复"确认"采用，或回复"不要"返回）', '{}', '[]', '2026-02-25 09:39:59.730505');
INSERT INTO public.messages VALUES ('79f33d67-68e5-436f-8295-c61328ba896f', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '🚀 对账任务已启动

规则：西福
文件：2 个
任务ID：task_5a3fe27f69b1

⏳ 正在执行对账，预计需要 10-60 秒

进度：开始加载数据', '{}', '[]', '2026-02-25 09:39:59.749947');
INSERT INTO public.messages VALUES ('df52d241-acd1-4618-8f80-7226c761a52f', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '🎯 开始创建新的对账规则

我会引导你完成以下4个步骤：

1️⃣ 上传并分析文件 - 分析文件结构和列名
2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）
3️⃣ 配置规则参数 - 设置容差、订单号特征等
4️⃣ 预览并保存 - 查看规则效果并保存

请先上传需要对账的文件（业务数据和财务数据各一个 Excel/CSV 文件）。', '{}', '[]', '2026-02-25 09:39:59.772061');
INSERT INTO public.messages VALUES ('0919eab9-b169-4a0f-b5c1-eda872242654', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '你好，admin！

我是专业的财务对账助手，可以帮助你完成以下工作：
1. **执行对账**：使用已有的对账规则快速对账
2. **创建规则**：引导你创建新的对账规则
3. **编辑规则**：调整已有规则的字段映射、配置等
4. **删除规则**：删除不需要的对账规则
5. **查看规则列表**：列出所有已创建的对账规则
6. **理解对账结果**：帮助你分析和解释对账结果

当前已有的对账规则包括：
- 喜马（喜马）
- 腾讯异业（腾讯异业）
- 西福（西福）

请问你需要什么帮助？', '{}', '[]', '2026-02-25 09:39:59.791218');
INSERT INTO public.messages VALUES ('213f5179-ac6f-45a8-9d31-8a37a28d3a0b', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'user', '创建规则', '{}', '[]', '2026-02-25 09:46:03.142381');
INSERT INTO public.messages VALUES ('124e97d3-101d-4ee7-80da-c67cfbb15ffb', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '🎯 开始创建新的对账规则

我会引导你完成以下4个步骤：

1️⃣ 上传并分析文件 - 分析文件结构和列名
2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）
3️⃣ 配置规则参数 - 设置容差、订单号特征等
4️⃣ 预览并保存 - 查看规则效果并保存

请先上传需要对账的文件（业务数据和财务数据各一个 Excel/CSV 文件）。', '{}', '[]', '2026-02-25 09:46:03.172784');
INSERT INTO public.messages VALUES ('def29d24-999a-4640-81f2-e91bcfcd5fbe', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'user', '已上传 2 个文件，请处理。', '{}', '[{"name": null, "path": "/uploads/2026/2/25/1767597466118_094607.csv", "size": 0}, {"name": null, "path": "/uploads/2026/2/25/ads_finance_d_inc_channel_details_20260105152012277_0_094607.csv", "size": 0}]', '2026-02-25 09:46:15.174064');
INSERT INTO public.messages VALUES ('933c1500-467f-4aaa-b9f5-0a5fa2f37f46', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '📊 **第1步：文件分析完成**

📄 **1767597466118_094607.csv**
   • 列数: 17  行数: 985
   • 列名: 订单编号, sp订单号, 商品编号, 商品名称, 充值账号, 面值, 购买数量, 销售额, 成本, 利润...

📄 **ads_finance_d_inc_channel_details_20260105152012277_0_094607.csv**
   • 列数: 20  行数: 976
   • 列名: 完成时间, 提交时间, 订单来源, 订单号, sup订单号, 合单订单号, 订单类型, 结算类型, 渠道所属公司, 渠道供应商...

正在为你生成字段映射建议...', '{}', '[]', '2026-02-25 09:46:15.197293');
INSERT INTO public.messages VALUES ('b9b0487a-fdbd-42b6-8335-d6cb9bf4e558', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '🎯 开始创建新的对账规则

我会引导你完成以下4个步骤：

1️⃣ 上传并分析文件 - 分析文件结构和列名
2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）
3️⃣ 配置规则参数 - 设置容差、订单号特征等
4️⃣ 预览并保存 - 查看规则效果并保存

请先上传需要对账的文件（业务数据和财务数据各一个 Excel/CSV 文件）。', '{}', '[]', '2026-02-25 09:46:15.216379');
INSERT INTO public.messages VALUES ('ea8f53fa-5c38-4771-bd19-542b7667fa8e', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'user', '创建规则', '{}', '[]', '2026-02-25 10:03:43.339952');
INSERT INTO public.messages VALUES ('806f66d6-8d70-456c-b5c6-d6af7e557156', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '🎯 开始创建新的对账规则

我会引导你完成以下4个步骤：

1️⃣ 上传并分析文件 - 分析文件结构和列名
2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）
3️⃣ 配置规则参数 - 设置容差、订单号特征等
4️⃣ 预览并保存 - 查看规则效果并保存

请先上传需要对账的文件（业务数据和财务数据各一个 Excel/CSV 文件）。', '{}', '[]', '2026-02-25 10:03:43.365895');
INSERT INTO public.messages VALUES ('c786b566-5394-43b4-959c-52c24d845809', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'user', '已上传 2 个文件，请处理。', '{}', '[{"name": null, "path": "/uploads/2026/2/25/1767597466118_100518.csv", "size": 0}, {"name": null, "path": "/uploads/2026/2/25/ads_finance_d_inc_channel_details_20260105152012277_0_100519.csv", "size": 0}]', '2026-02-25 10:05:26.938382');
INSERT INTO public.messages VALUES ('49b248fd-ab63-4a70-a305-135fbb9551a8', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '🎯 开始创建新的对账规则

我会引导你完成以下4个步骤：

1️⃣ 上传并分析文件 - 分析文件结构和列名
2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）
3️⃣ 配置规则参数 - 设置容差、订单号特征等
4️⃣ 预览并保存 - 查看规则效果并保存

请先上传需要对账的文件（业务数据和财务数据各一个 Excel/CSV 文件）。', '{}', '[]', '2026-02-25 10:05:26.963558');
INSERT INTO public.messages VALUES ('3344361a-a7b9-4e7b-8370-3aafb3d66cbd', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '📊 **第1步：文件分析完成**

📄 **1767597466118_100518.csv**
   • 列数: 17  行数: 985
   • 列名: 订单编号, sp订单号, 商品编号, 商品名称, 充值账号, 面值, 购买数量, 销售额, 成本, 利润...

📄 **ads_finance_d_inc_channel_details_20260105152012277_0_100519.csv**
   • 列数: 20  行数: 976
   • 列名: 完成时间, 提交时间, 订单来源, 订单号, sup订单号, 合单订单号, 订单类型, 结算类型, 渠道所属公司, 渠道供应商...

正在为你生成字段映射建议...', '{}', '[]', '2026-02-25 10:05:26.987999');
INSERT INTO public.messages VALUES ('2086c3e6-0acc-4619-b9cb-3e72e9eb0a86', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'user', '1', '{}', '[{"name": null, "path": "/uploads/2026/2/25/1767597466118_100518.csv", "size": 0}, {"name": null, "path": "/uploads/2026/2/25/ads_finance_d_inc_channel_details_20260105152012277_0_100519.csv", "size": 0}]', '2026-02-25 10:05:32.607948');
INSERT INTO public.messages VALUES ('b03d30e1-386d-4c48-8971-36a7eb80408c', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '🎯 开始创建新的对账规则

我会引导你完成以下4个步骤：

1️⃣ 上传并分析文件 - 分析文件结构和列名
2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）
3️⃣ 配置规则参数 - 设置容差、订单号特征等
4️⃣ 预览并保存 - 查看规则效果并保存

请先上传需要对账的文件（业务数据和财务数据各一个 Excel/CSV 文件）。', '{}', '[]', '2026-02-25 10:05:32.629365');
INSERT INTO public.messages VALUES ('ecf78d23-96a3-478e-99d0-3cb9a0ff085d', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '📊 **第1步：文件分析完成**

📄 **1767597466118_100518.csv**
   • 列数: 17  行数: 985
   • 列名: 订单编号, sp订单号, 商品编号, 商品名称, 充值账号, 面值, 购买数量, 销售额, 成本, 利润...

📄 **ads_finance_d_inc_channel_details_20260105152012277_0_100519.csv**
   • 列数: 20  行数: 976
   • 列名: 完成时间, 提交时间, 订单来源, 订单号, sup订单号, 合单订单号, 订单类型, 结算类型, 渠道所属公司, 渠道供应商...

正在为你生成字段映射建议...', '{}', '[]', '2026-02-25 10:05:32.652233');
INSERT INTO public.messages VALUES ('cc151164-0de0-461a-8028-7d5215b2cf53', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'user', '1', '{}', '[{"name": null, "path": "/uploads/2026/2/25/1767597466118_100518.csv", "size": 0}, {"name": null, "path": "/uploads/2026/2/25/ads_finance_d_inc_channel_details_20260105152012277_0_100519.csv", "size": 0}]', '2026-02-25 10:05:56.172812');
INSERT INTO public.messages VALUES ('906c7e83-3b83-4caf-821b-fa7a9977f9a7', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '🎯 开始创建新的对账规则

我会引导你完成以下4个步骤：

1️⃣ 上传并分析文件 - 分析文件结构和列名
2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）
3️⃣ 配置规则参数 - 设置容差、订单号特征等
4️⃣ 预览并保存 - 查看规则效果并保存

请先上传需要对账的文件（业务数据和财务数据各一个 Excel/CSV 文件）。', '{}', '[]', '2026-02-25 10:05:56.19646');
INSERT INTO public.messages VALUES ('164e232c-c7e3-43c5-9a20-7fb4723a26f9', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '📊 **第1步：文件分析完成**

📄 **1767597466118_100518.csv**
   • 列数: 17  行数: 985
   • 列名: 订单编号, sp订单号, 商品编号, 商品名称, 充值账号, 面值, 购买数量, 销售额, 成本, 利润...

📄 **ads_finance_d_inc_channel_details_20260105152012277_0_100519.csv**
   • 列数: 20  行数: 976
   • 列名: 完成时间, 提交时间, 订单来源, 订单号, sup订单号, 合单订单号, 订单类型, 结算类型, 渠道所属公司, 渠道供应商...

正在为你生成字段映射建议...', '{}', '[]', '2026-02-25 10:05:56.219302');
INSERT INTO public.messages VALUES ('3ad59929-4b6b-42ab-8023-0a0376ac0524', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'user', '创建规则', '{}', '[]', '2026-02-25 10:12:34.838035');
INSERT INTO public.messages VALUES ('a5b04af3-57d4-4afb-9334-803c024ef1c2', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '🎯 开始创建新的对账规则

我会引导你完成以下4个步骤：

1️⃣ 上传并分析文件 - 分析文件结构和列名
2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）
3️⃣ 配置规则参数 - 设置容差、订单号特征等
4️⃣ 预览并保存 - 查看规则效果并保存

请先上传需要对账的文件（业务数据和财务数据各一个 Excel/CSV 文件）。', '{}', '[]', '2026-02-25 10:12:34.871313');
INSERT INTO public.messages VALUES ('410e2f98-f531-4816-9f69-8d9bb319226b', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'user', '已上传 2 个文件，请处理。', '{}', '[{"name": null, "path": "/uploads/2026/2/25/1767597466118_101241.csv", "size": 0}, {"name": null, "path": "/uploads/2026/2/25/ads_finance_d_inc_channel_details_20260105152012277_0_101241.csv", "size": 0}]', '2026-02-25 10:12:50.833265');
INSERT INTO public.messages VALUES ('516db3bf-a92c-4d25-805f-5bfe0f1a23fe', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '📊 **第1步：文件分析完成**

📄 **1767597466118_101241.csv**
   • 列数: 17  行数: 985
   • 列名: 订单编号, sp订单号, 商品编号, 商品名称, 充值账号, 面值, 购买数量, 销售额, 成本, 利润...

📄 **ads_finance_d_inc_channel_details_20260105152012277_0_101241.csv**
   • 列数: 20  行数: 976
   • 列名: 完成时间, 提交时间, 订单来源, 订单号, sup订单号, 合单订单号, 订单类型, 结算类型, 渠道所属公司, 渠道供应商...

正在为你生成字段映射建议...', '{}', '[]', '2026-02-25 10:12:50.858379');
INSERT INTO public.messages VALUES ('8afc8ba4-8768-4692-b58e-ab16c92ddea0', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '🎯 开始创建新的对账规则

我会引导你完成以下4个步骤：

1️⃣ 上传并分析文件 - 分析文件结构和列名
2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）
3️⃣ 配置规则参数 - 设置容差、订单号特征等
4️⃣ 预览并保存 - 查看规则效果并保存

请先上传需要对账的文件（业务数据和财务数据各一个 Excel/CSV 文件）。', '{}', '[]', '2026-02-25 10:12:50.878791');
INSERT INTO public.messages VALUES ('180922de-6f17-4c1e-9b38-84a2c1693559', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'user', '1', '{}', '[{"name": null, "path": "/uploads/2026/2/25/1767597466118_101241.csv", "size": 0}, {"name": null, "path": "/uploads/2026/2/25/ads_finance_d_inc_channel_details_20260105152012277_0_101241.csv", "size": 0}]', '2026-02-25 10:12:54.969791');
INSERT INTO public.messages VALUES ('e411f8d5-8dfc-4964-9218-b9a41e60bb3f', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '📊 **第1步：文件分析完成**

📄 **1767597466118_101241.csv**
   • 列数: 17  行数: 985
   • 列名: 订单编号, sp订单号, 商品编号, 商品名称, 充值账号, 面值, 购买数量, 销售额, 成本, 利润...

📄 **ads_finance_d_inc_channel_details_20260105152012277_0_101241.csv**
   • 列数: 20  行数: 976
   • 列名: 完成时间, 提交时间, 订单来源, 订单号, sup订单号, 合单订单号, 订单类型, 结算类型, 渠道所属公司, 渠道供应商...

正在为你生成字段映射建议...', '{}', '[]', '2026-02-25 10:12:54.990765');
INSERT INTO public.messages VALUES ('4d841c9e-7ad1-4346-9dd8-6dc27814180d', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '🎯 开始创建新的对账规则

我会引导你完成以下4个步骤：

1️⃣ 上传并分析文件 - 分析文件结构和列名
2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）
3️⃣ 配置规则参数 - 设置容差、订单号特征等
4️⃣ 预览并保存 - 查看规则效果并保存

请先上传需要对账的文件（业务数据和财务数据各一个 Excel/CSV 文件）。', '{}', '[]', '2026-02-25 10:12:55.010652');
INSERT INTO public.messages VALUES ('a2c794cf-d652-4c13-80b3-20cb9451555d', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'user', '创建规则', '{}', '[]', '2026-02-25 10:20:58.868289');
INSERT INTO public.messages VALUES ('3a199181-fa38-4b64-88a5-adc2c4fb44f7', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '🎯 开始创建新的对账规则

我会引导你完成以下4个步骤：

1️⃣ 上传并分析文件 - 分析文件结构和列名
2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）
3️⃣ 配置规则参数 - 设置容差、订单号特征等
4️⃣ 预览并保存 - 查看规则效果并保存

请先上传需要对账的文件（业务数据和财务数据各一个 Excel/CSV 文件）。', '{}', '[]', '2026-02-25 10:20:58.900773');
INSERT INTO public.messages VALUES ('351b4610-7184-40b4-b494-f749eb65b00a', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'user', '已上传 2 个文件，请处理。', '{}', '[{"name": null, "path": "/uploads/2026/2/25/1767597466118_102102.csv", "size": 0}, {"name": null, "path": "/uploads/2026/2/25/ads_finance_d_inc_channel_details_20260105152012277_0_102103.csv", "size": 0}]', '2026-02-25 10:21:10.325565');
INSERT INTO public.messages VALUES ('d78dd8d6-91b6-443d-bd1b-b9f4a56909ff', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '🎯 开始创建新的对账规则

我会引导你完成以下4个步骤：

1️⃣ 上传并分析文件 - 分析文件结构和列名
2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）
3️⃣ 配置规则参数 - 设置容差、订单号特征等
4️⃣ 预览并保存 - 查看规则效果并保存

请先上传需要对账的文件（业务数据和财务数据各一个 Excel/CSV 文件）。', '{}', '[]', '2026-02-25 10:21:10.351694');
INSERT INTO public.messages VALUES ('470407eb-64c6-47c9-be76-74e346fa1279', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '📊 **第1步：文件分析完成**

📄 **1767597466118_102102.csv**
   • 列数: 17  行数: 985
   • 列名: 订单编号, sp订单号, 商品编号, 商品名称, 充值账号, 面值, 购买数量, 销售额, 成本, 利润...

📄 **ads_finance_d_inc_channel_details_20260105152012277_0_102103.csv**
   • 列数: 20  行数: 976
   • 列名: 完成时间, 提交时间, 订单来源, 订单号, sup订单号, 合单订单号, 订单类型, 结算类型, 渠道所属公司, 渠道供应商...

正在为你生成字段映射建议...', '{}', '[]', '2026-02-25 10:21:10.379293');
INSERT INTO public.messages VALUES ('cc83d43b-f444-476a-871b-d9538c41808a', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'user', '1', '{}', '[{"name": null, "path": "/uploads/2026/2/25/1767597466118_102102.csv", "size": 0}, {"name": null, "path": "/uploads/2026/2/25/ads_finance_d_inc_channel_details_20260105152012277_0_102103.csv", "size": 0}]', '2026-02-25 10:21:14.350199');
INSERT INTO public.messages VALUES ('682e0ada-713f-405b-a71e-340b11244d1b', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '🎯 开始创建新的对账规则

我会引导你完成以下4个步骤：

1️⃣ 上传并分析文件 - 分析文件结构和列名
2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）
3️⃣ 配置规则参数 - 设置容差、订单号特征等
4️⃣ 预览并保存 - 查看规则效果并保存

请先上传需要对账的文件（业务数据和财务数据各一个 Excel/CSV 文件）。', '{}', '[]', '2026-02-25 10:21:14.431133');
INSERT INTO public.messages VALUES ('e88b689c-2d2c-498f-8a21-26f07b799d45', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '📊 **第1步：文件分析完成**

📄 **1767597466118_102102.csv**
   • 列数: 17  行数: 985
   • 列名: 订单编号, sp订单号, 商品编号, 商品名称, 充值账号, 面值, 购买数量, 销售额, 成本, 利润...

📄 **ads_finance_d_inc_channel_details_20260105152012277_0_102103.csv**
   • 列数: 20  行数: 976
   • 列名: 完成时间, 提交时间, 订单来源, 订单号, sup订单号, 合单订单号, 订单类型, 结算类型, 渠道所属公司, 渠道供应商...

正在为你生成字段映射建议...', '{}', '[]', '2026-02-25 10:21:14.459578');
INSERT INTO public.messages VALUES ('e98ba5d9-b0b3-4a45-9daf-e77a2063e1eb', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'user', '创建规则', '{}', '[]', '2026-02-25 10:27:53.723051');
INSERT INTO public.messages VALUES ('7279e88a-f4c2-4da5-a9fb-8f717cb5ece6', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '🎯 开始创建新的对账规则

我会引导你完成以下4个步骤：

1️⃣ 上传并分析文件 - 分析文件结构和列名
2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）
3️⃣ 配置规则参数 - 设置容差、订单号特征等
4️⃣ 预览并保存 - 查看规则效果并保存

请先上传需要对账的文件（业务数据和财务数据各一个 Excel/CSV 文件）。', '{}', '[]', '2026-02-25 10:27:53.748835');
INSERT INTO public.messages VALUES ('289e3eb9-e8c0-4a96-9f2b-89922d66aebd', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'user', '已上传 2 个文件，请处理。', '{}', '[{"name": null, "path": "/uploads/2026/2/25/1767597466118_102759.csv", "size": 0}, {"name": null, "path": "/uploads/2026/2/25/ads_finance_d_inc_channel_details_20260105152012277_0_102800.csv", "size": 0}]', '2026-02-25 10:28:07.267918');
INSERT INTO public.messages VALUES ('ef08bfc7-c2e7-486d-885e-333ac90ab335', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '📊 **第1步：文件分析完成**

📄 **1767597466118_102759.csv**
   • 列数: 17  行数: 985
   • 列名: 订单编号, sp订单号, 商品编号, 商品名称, 充值账号, 面值, 购买数量, 销售额, 成本, 利润...

📄 **ads_finance_d_inc_channel_details_20260105152012277_0_102800.csv**
   • 列数: 20  行数: 976
   • 列名: 完成时间, 提交时间, 订单来源, 订单号, sup订单号, 合单订单号, 订单类型, 结算类型, 渠道所属公司, 渠道供应商...

正在为你生成字段映射建议...', '{}', '[]', '2026-02-25 10:28:07.294902');
INSERT INTO public.messages VALUES ('a35d1020-5e15-45b5-94e6-6b2077cbf413', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '🎯 开始创建新的对账规则

我会引导你完成以下4个步骤：

1️⃣ 上传并分析文件 - 分析文件结构和列名
2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）
3️⃣ 配置规则参数 - 设置容差、订单号特征等
4️⃣ 预览并保存 - 查看规则效果并保存

请先上传需要对账的文件（业务数据和财务数据各一个 Excel/CSV 文件）。', '{}', '[]', '2026-02-25 10:28:07.320369');
INSERT INTO public.messages VALUES ('f13a12e6-6a63-4b28-b8c7-7b5763f80e68', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'user', '1', '{}', '[{"name": null, "path": "/uploads/2026/2/25/1767597466118_102759.csv", "size": 0}, {"name": null, "path": "/uploads/2026/2/25/ads_finance_d_inc_channel_details_20260105152012277_0_102800.csv", "size": 0}]', '2026-02-25 10:28:12.707681');
INSERT INTO public.messages VALUES ('a19d266b-61ea-43b8-92fc-7b7913803b9b', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '📊 **第1步：文件分析完成**

📄 **1767597466118_102759.csv**
   • 列数: 17  行数: 985
   • 列名: 订单编号, sp订单号, 商品编号, 商品名称, 充值账号, 面值, 购买数量, 销售额, 成本, 利润...

📄 **ads_finance_d_inc_channel_details_20260105152012277_0_102800.csv**
   • 列数: 20  行数: 976
   • 列名: 完成时间, 提交时间, 订单来源, 订单号, sup订单号, 合单订单号, 订单类型, 结算类型, 渠道所属公司, 渠道供应商...

正在为你生成字段映射建议...', '{}', '[]', '2026-02-25 10:28:12.731498');
INSERT INTO public.messages VALUES ('9c56f690-7065-4008-a76e-2c3c9a0e3ba0', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '🎯 开始创建新的对账规则

我会引导你完成以下4个步骤：

1️⃣ 上传并分析文件 - 分析文件结构和列名
2️⃣ 确认字段映射 - 将列名映射到标准字段（订单号、金额等）
3️⃣ 配置规则参数 - 设置容差、订单号特征等
4️⃣ 预览并保存 - 查看规则效果并保存

请先上传需要对账的文件（业务数据和财务数据各一个 Excel/CSV 文件）。', '{}', '[]', '2026-02-25 10:28:12.755623');
INSERT INTO public.messages VALUES ('9ae55841-1d53-42ae-a6fe-146164d6bc7a', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '✅ 已选择规则「西福」

📋 **字段映射**
业务: date→订单时间, amount→销售额, status→状态, order_id→[''sp订单号'']
财务: date→完成时间, amount→发生-, status→None, order_id→[''sup订单号'']

⚙️ **规则配置**
默认规则

请确认是否采用此规则进行对账？
（回复"确认"采用，或回复"不要"返回）', '{}', '[]', '2026-02-25 10:28:12.777322');
INSERT INTO public.messages VALUES ('6e392e26-4b09-4fdf-b074-91b1562f640e', '9fdd4ab4-e561-43b8-99b1-e8fcc97172a9', 'assistant', '🚀 对账任务已启动

规则：西福
文件：2 个
任务ID：task_a910e4a60ded

⏳ 正在执行对账，预计需要 10-60 秒

进度：开始加载数据', '{}', '[]', '2026-02-25 10:28:12.798989');


--
-- Data for Name: reconciliation_rules; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.reconciliation_rules VALUES ('3a6650f8-3c0c-49b5-a124-1ff6c87c8b46', '测试认证规则', '更新后的描述', '3b593fbd-d0cd-48b8-99f1-fd9274f4059d', '00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', 'company', '{}', '{"version": "1.0", "description": "测试认证规则", "data_sources": {"finance": {}, "business": {}}}', '1.0', 0, NULL, '{测试,认证}', 'archived', NULL, NULL, '2026-02-12 17:08:15.339339+08', '2026-02-12 17:08:15.526847+08', DEFAULT, NULL);
INSERT INTO public.reconciliation_rules VALUES ('15221300-8179-493b-ac9d-80a94a9d3624', '西福', '西福', '00000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', 'private', '{}', '{"version": "1.0", "tolerance": {"date_format": "%Y-%m-%d", "amount_diff_max": 0.1}, "description": "西福", "data_sources": {"finance": {"field_roles": {"date": "完成时间", "amount": "发生-", "status": null, "order_id": ["sup订单号"]}, "file_pattern": ["ads_finance_d_inc_channel_details_20260105152012277_0_*.xlsx", "ads_finance_d_inc_channel_details_20260105152012277_0_*.csv", "ads_finance_d_inc_channel_details_20260105152012277_0_*.xlsb", "ads_finance_d_inc_channel_details_20260105152012277_0_*.xls", "ads_finance_d_inc_channel_details_20260105152012277_0_*.xlsm"]}, "business": {"field_roles": {"date": "订单时间", "amount": "销售额", "status": "状态", "order_id": ["sp订单号"]}, "file_pattern": ["1767597466118_*.csv", "1767597466118_*.xlsb", "1767597466118_*.xls", "1767597466118_*.xlsx", "1767597466118_*.xlsm"]}}, "key_field_role": "order_id", "custom_validations": [{"name": "missing_in_business", "issue_type": "missing_in_business", "condition_expr": "fin_exists and not biz_exists", "detail_template": "{fin_file}存在，{biz_file}无此订单记录"}, {"name": "missing_in_finance", "issue_type": "missing_in_finance", "condition_expr": "biz_exists and not fin_exists", "detail_template": "{biz_file}存在，{fin_file}无此订单记录"}, {"name": "amount_mismatch", "issue_type": "amount_mismatch", "condition_expr": "biz_exists and fin_exists and biz.get(''amount'') is not None and fin.get(''amount'') is not None and abs(float(biz.get(''amount'', 0)) - float(fin.get(''amount'', 0))) > amount_diff_max", "detail_template": "{biz_file}金额 {biz[amount]} vs {fin_file}金额 {fin[amount]}，差额 {amount_diff_formatted} 超出容差 {amount_diff_max}"}, {"name": "order_status_mismatch", "issue_type": "order_status_mismatch", "condition_expr": "biz_exists and str(biz.get(''status'', '''')).lower() != ''success'' and str(biz.get(''status'', '''')).lower() != ''成功'' and str(biz.get(''status'', '''')).lower() != ''交易成功''", "detail_template": "订单状态不一致：状态为 {biz[status]}，不是允许的成功状态"}], "data_cleaning_rules": {"global": {"global_transforms": [{"keep": "first", "subset": ["order_id"], "operation": "drop_duplicates", "description": "全局去重"}]}, "finance": {"row_filters": [{"condition": "str(row.get(''order_id'', '''')).startswith(''104'')", "description": "只保留104开头的订单号"}], "aggregations": [{"group_by": "order_id", "agg_fields": {"date": "first", "amount": "sum"}, "description": "按订单号合并"}, {"group_by": "order_id", "agg_fields": {"amount": "sum"}, "description": "按订单号合并，金额累加"}], "field_transforms": [{"field": "amount", "operation": "abs", "description": "金额取绝对值"}, {"field": "amount", "decimals": 2, "operation": "round", "description": "金额保留2位小数"}, {"field": "order_id", "operation": "strip", "description": "订单号去除首尾空格"}, {"field": "order_id", "transform": "str(row.get(''order_id'', '''')).strip(\"''\")[:21]", "description": "订单号去掉开头单引号，并截取前21位"}], "global_transforms": [{"subset": ["order_id", "amount"], "operation": "drop_na", "description": "删除关键字段为空的记录"}]}, "business": {"row_filters": [{"condition": "str(row.get(''order_id'', '''')).startswith(''104'')", "description": "只保留104开头的订单号"}], "aggregations": [{"group_by": "order_id", "agg_fields": {"date": "first", "amount": "sum"}, "description": "按订单号合并"}, {"group_by": "order_id", "agg_fields": {"amount": "sum"}, "description": "按订单号合并，金额累加"}], "field_transforms": [{"field": "amount", "decimals": 2, "operation": "round", "description": "金额保留2位小数"}, {"field": "order_id", "operation": "strip", "description": "订单号去除首尾空格"}, {"field": "order_id", "transform": "str(row.get(''order_id'', '''')).strip(\"''\")[:21]", "description": "订单号去掉开头单引号，并截取前21位"}], "global_transforms": [{"subset": ["order_id"], "operation": "drop_na", "description": "删除订单号为空的记录"}]}}}', '1.0', 0, NULL, '{}', 'active', NULL, NULL, '2026-02-14 15:32:11.585011+08', '2026-02-14 15:32:11.585011+08', DEFAULT, NULL);
INSERT INTO public.reconciliation_rules VALUES ('1fdf802d-6a6a-445c-a1c4-7e939983fe26', '腾讯异业', '腾讯异业', '00000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', 'private', '{}', '{"version": "1.0", "tolerance": {"date_format": "%Y-%m-%d", "amount_diff_max": 0.1}, "description": "腾讯异业", "data_sources": {"finance": {"field_roles": {"date": ["完成时间"], "amount": ["发生-"], "order_id": ["sup订单号"]}, "file_pattern": ["ads_finance_d_inc_channel_details_20260105133821735_0_*.xlsb", "ads_finance_d_inc_channel_details_20260105133821735_0_*.csv", "ads_finance_d_inc_channel_details_20260105133821735_0_*.xls", "ads_finance_d_inc_channel_details_20260105133821735_0_*.xlsx", "ads_finance_d_inc_channel_details_20260105133821735_0_*.xlsm"]}, "business": {"field_roles": {"date": ["ftran_time"], "amount": "product_price", "status": ["result", "provide_result"], "order_id": ["roc_oid"]}, "file_pattern": ["2025-12-01~2025-12-01对账流水_*.xlsb", "2025-12-01~2025-12-01对账流水_*.xlsm", "2025-12-01~2025-12-01对账流水_*.xlsx", "2025-12-01~2025-12-01对账流水_*.csv", "2025-12-01~2025-12-01对账流水_*.xls"]}}, "key_field_role": "order_id", "custom_validations": [{"name": "missing_in_business", "issue_type": "missing_in_business", "condition_expr": "fin_exists and not biz_exists", "detail_template": "{fin_file}存在，{biz_file}无此订单记录"}, {"name": "missing_in_finance", "issue_type": "missing_in_finance", "condition_expr": "biz_exists and not fin_exists", "detail_template": "{biz_file}存在，{fin_file}无此订单记录"}, {"name": "amount_mismatch", "issue_type": "amount_mismatch", "condition_expr": "biz_exists and fin_exists and biz.get(''amount'') is not None and fin.get(''amount'') is not None and abs(float(biz.get(''amount'', 0)) - float(fin.get(''amount'', 0))) > amount_diff_max", "detail_template": "{biz_file}金额 {biz[amount]} vs {fin_file}金额 {fin[amount]}，差额 {amount_diff_formatted} 超出容差 {amount_diff_max}"}, {"name": "order_status_mismatch", "issue_type": "order_status_mismatch", "condition_expr": "biz_exists and str(biz.get(''status'', '''')).lower() != ''success'' and str(biz.get(''status'', '''')).lower() != ''成功'' and str(biz.get(''status'', '''')).lower() != ''交易成功''", "detail_template": "订单状态不一致：状态为 {biz[status]}，不是允许的成功状态"}], "data_cleaning_rules": {"global": {"global_transforms": [{"keep": "first", "subset": ["order_id"], "operation": "drop_duplicates", "description": "全局去重"}]}, "finance": {"group_by": [{"field": "order_id", "aggregations": [{"field": "amount", "operation": "sum", "output_field": "amount"}]}], "row_filters": [], "aggregations": [{"group_by": "order_id", "agg_fields": {"date": "first", "amount": "sum"}, "description": "按订单号合并"}], "field_transforms": [{"field": "amount", "operation": "abs", "description": "金额取绝对值"}, {"field": "amount", "decimals": 2, "operation": "round", "description": "金额保留2位小数"}, {"field": "order_id", "operation": "strip", "description": "订单号去除首尾空格"}, {"field": "order_id", "transform": "str(row.get(''order_id'', '''')).lstrip(\"''\")[:21]", "description": "订单号去掉开头单引号，并截取前21位"}, {"field": "order_id", "transform": "str(row.get(''order_id'', ''''))", "description": "订单号转换为字符串"}], "global_transforms": [{"subset": ["order_id", "amount"], "operation": "drop_na", "description": "删除关键字段为空的记录"}]}, "business": {"group_by": [{"field": "order_id", "aggregations": [{"field": "amount", "operation": "sum", "output_field": "amount"}]}], "row_filters": [], "aggregations": [{"group_by": "order_id", "agg_fields": {"date": "first", "amount": "sum"}, "description": "按订单号合并"}], "field_transforms": [{"field": "amount", "decimals": 2, "operation": "round", "description": "金额保留2位小数"}, {"field": "order_id", "operation": "strip", "description": "订单号去除首尾空格"}, {"field": "order_id", "transform": "str(row.get(''order_id'', '''')).lstrip(\"''\")[:21]", "description": "订单号去掉开头单引号，并截取前21位"}, {"field": "order_id", "transform": "str(row.get(''order_id'', ''''))", "description": "订单号转换为字符串"}, {"field": "amount", "transform": "float(row.get(''amount'', 0)) / 100", "description": "product_price 除以100转换为元"}], "global_transforms": [{"subset": ["order_id"], "operation": "drop_na", "description": "删除订单号为空的记录"}]}}}', '1.0', 0, NULL, '{}', 'active', NULL, NULL, '2026-02-14 22:37:54.072215+08', '2026-02-14 22:37:54.072215+08', DEFAULT, NULL);
INSERT INTO public.reconciliation_rules VALUES ('1eb20a3b-44c7-49fb-9239-62082b3f3d9a', '喜马', '喜马', '00000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', 'private', '{}', '{"version": "1.0", "tolerance": {"date_format": "%Y-%m-%d", "amount_diff_max": 0.1}, "description": "喜马", "data_sources": {"finance": {"field_roles": {"date": "完成时间", "amount": ["发生-"], "order_id": "sup订单号"}, "file_pattern": ["合单_*.xlsx", "合单_*.csv", "合单_*.xls", "合单_*.xlsb", "合单_*.xlsm"]}, "business": {"field_roles": {"date": "支付时间", "amount": ["应结算平台金额"], "order_id": ["第三方订单号"]}, "file_pattern": ["官网_*.xlsb", "官网_*.xlsm", "官网_*.xlsx", "官网_*.csv", "官网_*.xls"]}}, "key_field_role": "order_id", "rule_config_text": "金额容差 0.1 元\n业务文件：金额保留2位小数\n业务文件：订单号去除首尾空格\n业务文件：订单号去掉开头单引号，并截取前21位\n业务文件：相同的订单号按金额累加合并\n财务文件：金额取绝对值\n财务文件：金额保留2位小数\n财务文件：订单号去除首尾空格\n财务文件：订单号去掉开头单引号，并截取前21位\n财务文件：相同的订单号按金额累加合并", "custom_validations": [{"name": "missing_in_business", "issue_type": "missing_in_business", "condition_expr": "fin_exists and not biz_exists", "detail_template": "{fin_file}存在，{biz_file}无此订单记录"}, {"name": "missing_in_finance", "issue_type": "missing_in_finance", "condition_expr": "biz_exists and not fin_exists", "detail_template": "{biz_file}存在，{fin_file}无此订单记录"}, {"name": "amount_mismatch", "issue_type": "amount_mismatch", "condition_expr": "biz_exists and fin_exists and biz.get(''amount'') is not None and fin.get(''amount'') is not None and abs(float(biz.get(''amount'', 0)) - float(fin.get(''amount'', 0))) > amount_diff_max", "detail_template": "{biz_file}金额 {biz[amount]} vs {fin_file}金额 {fin[amount]}，差额 {amount_diff_formatted} 超出容差 {amount_diff_max}"}], "field_mapping_text": "业务: 日期->支付时间, 金额->应结算平台金额, 订单号->第三方订单号\n财务: 日期->完成时间, 金额->发生-, 订单号->sup订单号", "data_cleaning_rules": {"global": {"global_transforms": [{"keep": "first", "subset": ["order_id"], "operation": "drop_duplicates", "description": "全局去重"}]}, "finance": {"aggregations": [{"group_by": "order_id", "agg_fields": {"date": "first", "amount": "sum"}, "description": "相同的订单号按金额累加合并"}], "field_transforms": [{"field": "amount", "operation": "abs", "description": "金额取绝对值"}, {"field": "amount", "decimals": 2, "operation": "round", "description": "金额保留2位小数"}, {"field": "order_id", "operation": "strip", "description": "订单号去除首尾空格"}, {"field": "order_id", "operation": "expr", "expression": "str(row.get(''order_id'', '''')).lstrip(\"''\")[:21] if pd.notna(row.get(''order_id'', '''')) else row.get(''order_id'', '''')", "description": "订单号去掉开头单引号，并截取前21位"}]}, "business": {"aggregations": [{"group_by": "order_id", "agg_fields": {"date": "first", "amount": "sum"}, "description": "相同的订单号按金额累加合并"}], "field_transforms": [{"field": "amount", "decimals": 2, "operation": "round", "description": "金额保留2位小数"}, {"field": "order_id", "operation": "strip", "description": "订单号去除首尾空格"}, {"field": "order_id", "operation": "expr", "expression": "str(row.get(''order_id'', '''')).lstrip(\"''\")[:21] if pd.notna(row.get(''order_id'', '''')) else row.get(''order_id'', '''')", "description": "订单号去掉开头单引号，并截取前21位"}]}}}', '1.0', 0, NULL, '{}', 'active', NULL, NULL, '2026-02-15 20:57:47.56214+08', '2026-02-15 20:57:47.56214+08', DEFAULT, NULL);
INSERT INTO public.reconciliation_rules VALUES ('715b4720-f674-42bd-9347-4513b81b02ff', '对账吧', '对账吧', '00000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', 'private', '{}', '{"version": "1.0", "tolerance": {"date_format": "%Y-%m-%d", "amount_diff_max": 0.1}, "description": "对账吧", "data_sources": {"finance": {"field_roles": {"date": "完成时间", "amount": ["发生-"], "order_id": "sup订单号"}, "file_pattern": ["合单_*.xlsm", "合单_*.csv", "合单_*.xls", "合单_*.xlsx", "合单_*.xlsb"]}, "business": {"field_roles": {"date": "支付时间", "amount": ["应结算平台金额"], "order_id": ["第三方订单号"]}, "file_pattern": ["官网_*.xlsb", "官网_*.xlsm", "官网_*.csv", "官网_*.xlsx", "官网_*.xls"]}}, "key_field_role": "order_id", "rule_config_text": "", "custom_validations": [{"name": "missing_in_business", "issue_type": "missing_in_business", "condition_expr": "fin_exists and not biz_exists", "detail_template": "{fin_file}存在，{biz_file}无此订单记录"}, {"name": "missing_in_finance", "issue_type": "missing_in_finance", "condition_expr": "biz_exists and not fin_exists", "detail_template": "{biz_file}存在，{fin_file}无此订单记录"}, {"name": "amount_mismatch", "issue_type": "amount_mismatch", "condition_expr": "biz_exists and fin_exists and biz.get(''amount'') is not None and fin.get(''amount'') is not None and abs(float(biz.get(''amount'', 0)) - float(fin.get(''amount'', 0))) > amount_diff_max", "detail_template": "{biz_file}金额 {biz[amount]} vs {fin_file}金额 {fin[amount]}，差额 {amount_diff_formatted} 超出容差 {amount_diff_max}"}], "field_mapping_text": "业务: 日期->支付时间, 金额->应结算平台金额, 订单号->第三方订单号\n财务: 日期->完成时间, 金额->发生-, 订单号->sup订单号", "data_cleaning_rules": {"global": {"global_transforms": [{"keep": "first", "subset": ["order_id"], "operation": "drop_duplicates", "description": "全局去重"}]}, "finance": {"aggregations": [{"group_by": "order_id", "agg_fields": {"date": "first", "amount": "sum"}, "description": "相同的订单号按金额累加合并"}], "field_transforms": [{"field": "amount", "operation": "abs", "description": "金额取绝对值"}, {"field": "amount", "decimals": 2, "operation": "round", "description": "金额保留2位小数"}, {"field": "order_id", "operation": "strip", "description": "订单号去除首尾空格"}, {"field": "order_id", "operation": "expr", "expression": "str(row.get(''order_id'', '''')).lstrip(\"''\")[:21] if pd.notna(row.get(''order_id'', '''')) else row.get(''order_id'', '''')", "description": "订单号去掉开头单引号，并截取前21位"}]}, "business": {"aggregations": [{"group_by": "order_id", "agg_fields": {"date": "first", "amount": "sum"}, "description": "相同的订单号按金额累加合并"}], "field_transforms": [{"field": "amount", "decimals": 2, "operation": "round", "description": "金额保留2位小数"}, {"field": "order_id", "operation": "strip", "description": "订单号去除首尾空格"}, {"field": "order_id", "operation": "expr", "expression": "str(row.get(''order_id'', '''')).lstrip(\"''\")[:21] if pd.notna(row.get(''order_id'', '''')) else row.get(''order_id'', '''')", "description": "订单号去掉开头单引号，并截取前21位"}]}}}', '1.0', 0, NULL, '{}', 'active', NULL, NULL, '2026-02-24 16:35:56.862839+08', '2026-02-24 16:35:56.862839+08', DEFAULT, '98f51d95bba9c295c0a459ad548ab61b');
INSERT INTO public.reconciliation_rules VALUES ('6c5c6b4c-6993-4c09-a979-7e19f402e609', '确认', '确认', '00000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', 'private', '{}', '{"version": "1.0", "tolerance": {"date_format": "%Y-%m-%d", "amount_diff_max": 0.1}, "description": "确认", "data_sources": {"finance": {"field_roles": {"date": "完成时间", "amount": ["发生-"], "order_id": "sup订单号"}, "file_pattern": ["合单_*.xlsm", "合单_*.xlsx", "合单_*.xls", "合单_*.xlsb", "合单_*.csv"]}, "business": {"field_roles": {"date": "支付时间", "amount": ["应结算平台金额"], "order_id": ["第三方订单号"]}, "file_pattern": ["官网_*.xlsm", "官网_*.xlsx", "官网_*.xls", "官网_*.csv", "官网_*.xlsb"]}}, "key_field_role": "order_id", "rule_config_text": "", "custom_validations": [{"name": "missing_in_business", "issue_type": "missing_in_business", "condition_expr": "fin_exists and not biz_exists", "detail_template": "{fin_file}存在，{biz_file}无此订单记录"}, {"name": "missing_in_finance", "issue_type": "missing_in_finance", "condition_expr": "biz_exists and not fin_exists", "detail_template": "{biz_file}存在，{fin_file}无此订单记录"}, {"name": "amount_mismatch", "issue_type": "amount_mismatch", "condition_expr": "biz_exists and fin_exists and biz.get(''amount'') is not None and fin.get(''amount'') is not None and abs(float(biz.get(''amount'', 0)) - float(fin.get(''amount'', 0))) > amount_diff_max", "detail_template": "{biz_file}金额 {biz[amount]} vs {fin_file}金额 {fin[amount]}，差额 {amount_diff_formatted} 超出容差 {amount_diff_max}"}], "field_mapping_text": "业务: 日期->支付时间, 金额->应结算平台金额, 订单号->第三方订单号\n财务: 日期->完成时间, 金额->发生-, 订单号->sup订单号", "data_cleaning_rules": {"global": {"global_transforms": [{"keep": "first", "subset": ["order_id"], "operation": "drop_duplicates", "description": "全局去重"}]}, "finance": {"aggregations": [{"group_by": "order_id", "agg_fields": {"date": "first", "amount": "sum"}, "description": "相同的订单号按金额累加合并"}], "field_transforms": [{"field": "amount", "operation": "abs", "description": "金额取绝对值"}, {"field": "amount", "decimals": 2, "operation": "round", "description": "金额保留2位小数"}, {"field": "order_id", "operation": "strip", "description": "订单号去除首尾空格"}, {"field": "order_id", "operation": "expr", "expression": "str(row.get(''order_id'', '''')).lstrip(\"''\")[:21] if pd.notna(row.get(''order_id'', '''')) else row.get(''order_id'', '''')", "description": "订单号去掉开头单引号，并截取前21位"}]}, "business": {"aggregations": [{"group_by": "order_id", "agg_fields": {"date": "first", "amount": "sum"}, "description": "相同的订单号按金额累加合并"}], "field_transforms": [{"field": "amount", "decimals": 2, "operation": "round", "description": "金额保留2位小数"}, {"field": "order_id", "operation": "strip", "description": "订单号去除首尾空格"}, {"field": "order_id", "operation": "expr", "expression": "str(row.get(''order_id'', '''')).lstrip(\"''\")[:21] if pd.notna(row.get(''order_id'', '''')) else row.get(''order_id'', '''')", "description": "订单号去掉开头单引号，并截取前21位"}]}}}', '1.0', 0, NULL, '{}', 'active', NULL, NULL, '2026-02-24 16:59:55.579337+08', '2026-02-24 16:59:55.579337+08', DEFAULT, '98f51d95bba9c295c0a459ad548ab61b');
INSERT INTO public.reconciliation_rules VALUES ('05e8f9ce-06f6-41dd-92b1-81b9f379c301', '西福商管', '西福商管', '00000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', 'private', '{}', '{"version": "1.0", "tolerance": {"date_format": "%Y-%m-%d", "amount_diff_max": 0.1}, "description": "西福商管", "data_sources": {"finance": {"field_roles": {"date": "完成时间", "amount": "发生-", "order_id": ["sup订单号"]}, "file_pattern": ["ads_finance_d_inc_channel_details_20260105152012277_0_*.csv", "ads_finance_d_inc_channel_details_20260105152012277_0_*.xls", "ads_finance_d_inc_channel_details_20260105152012277_0_*.xlsm", "ads_finance_d_inc_channel_details_20260105152012277_0_*.xlsx", "ads_finance_d_inc_channel_details_20260105152012277_0_*.xlsb"]}, "business": {"field_roles": {"date": "订单时间", "amount": "销售额", "order_id": ["sp订单号"]}, "file_pattern": ["1767597466118_*.xls", "1767597466118_*.xlsb", "1767597466118_*.xlsx", "1767597466118_*.csv", "1767597466118_*.xlsm"]}}, "key_field_role": "order_id", "rule_config_text": "去掉sup订单号单引号，并截取前21位\n相同的订单号按金额累加合并", "custom_validations": [{"name": "missing_in_business", "issue_type": "missing_in_business", "condition_expr": "fin_exists and not biz_exists", "detail_template": "{fin_file}存在，{biz_file}无此订单记录"}, {"name": "missing_in_finance", "issue_type": "missing_in_finance", "condition_expr": "biz_exists and not fin_exists", "detail_template": "{biz_file}存在，{fin_file}无此订单记录"}, {"name": "amount_mismatch", "issue_type": "amount_mismatch", "condition_expr": "biz_exists and fin_exists and biz.get(''amount'') is not None and fin.get(''amount'') is not None and abs(float(biz.get(''amount'', 0)) - float(fin.get(''amount'', 0))) > amount_diff_max", "detail_template": "{biz_file}金额 {biz[amount]} vs {fin_file}金额 {fin[amount]}，差额 {amount_diff_formatted} 超出容差 {amount_diff_max}"}], "field_mapping_text": "业务: 订单号->sp订单号, 金额->销售额, 日期->订单时间\n财务: 订单号->sup订单号, 金额->发生-, 日期->完成时间", "data_cleaning_rules": {"global": {"global_transforms": [{"keep": "first", "subset": ["order_id"], "operation": "drop_duplicates", "description": "全局去重"}]}, "finance": {"row_filters": [], "aggregations": [{"group_by": "order_id", "agg_fields": {"date": "first", "amount": "sum"}, "description": "相同的订单号按金额累加合并"}], "field_transforms": [{"field": "amount", "operation": "abs", "description": "金额取绝对值"}, {"field": "amount", "decimals": 2, "operation": "round", "description": "金额保留2位小数"}, {"field": "order_id", "operation": "strip", "description": "订单号去除首尾空格"}, {"field": "order_id", "operation": "expr", "expression": "str(row.get(''order_id'', '''')).lstrip(\"''\")[:21] if pd.notna(row.get(''order_id'', '''')) else row.get(''order_id'', '''')", "description": "sup订单号去掉前面的单引号，并截取前21位"}], "global_transforms": [{"subset": ["order_id", "amount"], "operation": "drop_na", "description": "删除关键字段为空的记录"}]}, "business": {"row_filters": [], "aggregations": [{"group_by": "order_id", "agg_fields": {"date": "first", "amount": "sum"}, "description": "相同的订单号按金额累加合并"}], "field_transforms": [{"field": "amount", "decimals": 2, "operation": "round", "description": "金额保留2位小数"}, {"field": "order_id", "operation": "strip", "description": "订单号去除首尾空格"}], "global_transforms": [{"subset": ["order_id"], "operation": "drop_na", "description": "删除订单号为空的记录"}]}}}', '1.0', 0, NULL, '{}', 'active', NULL, NULL, '2026-02-24 10:43:25.954193+08', '2026-02-24 14:02:48.375566+08', DEFAULT, '7fe0d171d468f2fd9c8c04eb3e84a033');


--
-- Data for Name: reconciliation_tasks; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: rule_usage_logs; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: rule_versions; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Name: admins_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.admins_id_seq', 1, true);


--
-- PostgreSQL database dump complete
--

