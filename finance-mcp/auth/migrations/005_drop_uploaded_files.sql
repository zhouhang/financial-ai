-- 删除未使用的 uploaded_files 表
-- 该表自创建以来从未被代码写入，上传文件由 file_uploads 表（004_file_ownership）和内存状态管理

DROP TABLE IF EXISTS public.uploaded_files CASCADE;
