#!/usr/bin/env python3
"""
检查 data-agent 中调用了哪些 MCP 工具，以及哪些 MCP 工具没有被使用
"""

# ════════════════════════════════════════════════════════════════════════════
# finance-mcp 中定义的所有 MCP 工具
# ════════════════════════════════════════════════════════════════════════════

ALL_MCP_TOOLS = {
    # ── 认证与规则管理 (auth/tools.py) ────────────────────────────────────────
    "auth_register": "注册新用户账号",
    "auth_login": "用户登录，返回 JWT token",
    "auth_me": "获取当前登录用户信息",
    "list_reconciliation_rules": "查询用户可见的对账规则列表",
    "get_reconciliation_rule": "获取单条对账规则详情",
    "save_reconciliation_rule": "保存新的对账规则",
    "update_reconciliation_rule": "更新已有对账规则",
    "delete_reconciliation_rule": "删除对账规则（软删除）",
    "search_rules_by_mapping": "根据字段映射哈希搜索匹配规则",
    "copy_reconciliation_rule": "复制对账规则为个人规则",
    "batch_get_reconciliation_rules": "批量获取多个规则详情",
    "admin_login": "管理员登录",
    "create_company": "管理员创建公司",
    "create_department": "管理员创建部门",
    "list_companies": "获取公司列表（管理员）",
    "list_departments": "获取部门列表（管理员）",
    "get_admin_view": "获取管理员视图（层级结构）",
    "list_companies_public": "获取公司列表（公开）",
    "list_departments_public": "获取部门列表（公开）",
    "create_conversation": "创建新会话",
    "list_conversations": "获取会话列表",
    "get_conversation": "获取单个会话详情",
    "update_conversation": "更新会话",
    "delete_conversation": "删除会话",
    "save_message": "保存消息到会话",
    
    # ── 游客认证 (auth/tools.py) ─────────────────────────────────────────────
    "create_guest_token": "创建游客临时 token",
    "verify_guest_token": "验证游客 token",
    "list_recommended_rules": "获取推荐规则列表",
    
    # ── 对账模块 (reconciliation/mcp_server/tools.py) ─────────────────────────
    "reconciliation_start": "开始对账任务",
    "reconciliation_status": "查询对账任务状态",
    "reconciliation_result": "获取对账结果",
    "reconciliation_list_tasks": "列出用户的对账任务",
    "file_upload": "上传文件（base64 编码）",
    "file_delete": "删除已上传文件",
    "get_reconciliation": "获取对账配置",
    "analyze_files": "分析文件列信息",
    "read_excel_sheets": "读取 Excel 所有 sheet",
    "detect_file_complexity": "检测文件复杂度",
    
    # ── 数据整理模块 (data_preparation/mcp_server/tools.py) ──────────────────
    "data_preparation_start": "开始数据整理任务",
    "data_preparation_result": "获取数据整理结果",
    "data_preparation_status": "查询数据整理状态",
    "data_preparation_list_tasks": "列出数据整理任务",
    
    # ── 文件校验 (tools/file_validate_tool.py) ───────────────────────────────
    "validate_uploaded_files": "校验上传文件是否符合规则",
    
    # ── 数据同步规则 (proc/mcp_server/proc_rule.py) ──────────────────────────
    "proc_rule_execute": "执行数据整理规则",
    
    # ── 规则查询 (tools/rules.py) ────────────────────────────────────────────
    "get_rule_from_bus": "从 bus_rules 表获取规则",
    "list_digital_employees": "获取数字员工列表",
    "list_rules_by_employee": "根据员工 code 获取规则列表",
    
    # ── 核对模块 (recon/mcp_server/recon_tool.py) ────────────────────────────
    "recon_execute": "执行对账（源文件与目标文件比对）",
    "recon_list_rules": "列出可用的核对规则",
    
    # ── 新增：recon_task_execution (recon/mcp_server/recon_tool.py) ─────────
    "recon_task_execution": "执行对账任务，生成差异报告",
}

# ════════════════════════════════════════════════════════════════════════════
# data-agent 中调用的 MCP 工具（从 mcp_client.py 和其他文件中提取）
# ════════════════════════════════════════════════════════════════════════════

USED_MCP_TOOLS = {
    # ── 认证相关 ─────────────────────────────────────────────────────────────
    "auth_login": "server.py:832, tools/mcp_client.py:369",
    "auth_register": "server.py:886, tools/mcp_client.py:377",
    "auth_me": "server.py:351, tools/mcp_client.py:384",
    
    # ── 规则管理 ─────────────────────────────────────────────────────────────
    "list_reconciliation_rules": "tools/mcp_client.py:423",
    "get_reconciliation_rule": "tools/mcp_client.py:440",
    "save_reconciliation_rule": "tools/mcp_client.py:450",
    "update_reconciliation_rule": "tools/mcp_client.py:464",
    "delete_reconciliation_rule": "tools/mcp_client.py:472",
    "copy_reconciliation_rule": "server.py:913",
    
    # ── 管理员功能 ───────────────────────────────────────────────────────────
    "admin_login": "tools/mcp_client.py:481",
    "create_company": "tools/mcp_client.py:489",
    "create_department": "tools/mcp_client.py:497",
    "list_companies": "tools/mcp_client.py:506",
    "list_departments": "tools/mcp_client.py:516",
    "get_admin_view": "tools/mcp_client.py:521",
    "list_companies_public": "server.py:847, tools/mcp_client.py:528",
    "list_departments_public": "server.py:860, tools/mcp_client.py:533",
    
    # ── 会话管理 ─────────────────────────────────────────────────────────────
    "create_conversation": "server.py:688, tools/mcp_client.py:547",
    "list_conversations": "server.py:943, tools/mcp_client.py:552",
    "get_conversation": "server.py:964, tools/mcp_client.py:561",
    "update_conversation": "tools/mcp_client.py:577",
    "delete_conversation": "server.py:985, tools/mcp_client.py:582",
    "save_message": "server.py:711/720, tools/mcp_client.py:600",
    
    # ── 游客认证 ─────────────────────────────────────────────────────────────
    "create_guest_token": "tools/mcp_client.py:400",
    "verify_guest_token": "tools/mcp_client.py:405",
    "list_recommended_rules": "tools/mcp_client.py:410",
    
    # ── 对账模块 ─────────────────────────────────────────────────────────────
    "reconciliation_start": "tools/mcp_client.py:321",
    "reconciliation_status": "tools/mcp_client.py:337",
    "reconciliation_result": "tools/mcp_client.py:353",
    "reconciliation_list_tasks": "tools/mcp_client.py:362",
    "file_upload": "server.py:260",
    "file_delete": "helpers_original.py:64",
    "analyze_files": "helpers_original.py:1572/1645/1730",
    "read_excel_sheets": "helpers_original.py:1371",
    "detect_file_complexity": "helpers_original.py:1315",
    
    # ── 数据整理模块 ─────────────────────────────────────────────────────────
    # 注意：data_preparation_* 工具未被直接调用，而是通过 proc 模块间接使用
    
    # ── 文件校验 ─────────────────────────────────────────────────────────────
    "validate_uploaded_files": "graphs/main_graph/public_nodes.py:277, tools/mcp_client.py:689",
    
    # ── 数据同步规则 ─────────────────────────────────────────────────────────
    "proc_rule_execute": "tools/mcp_client.py:715",
    
    # ── 规则查询 ─────────────────────────────────────────────────────────────
    "get_rule_from_bus": "graphs/proc/api.py:205, tools/mcp_client.py:665",
    "list_digital_employees": "graphs/proc/api.py:102, tools/mcp_client.py:623",
    "list_rules_by_employee": "graphs/proc/api.py:153, tools/mcp_client.py:644",
    
    # ── 核对模块 ─────────────────────────────────────────────────────────────
    "recon_execute": "tools/mcp_client.py:796",
    "recon_task_execution": "graphs/recon/nodes.py:208, tools/mcp_client.py:751",
}


def print_analysis():
    """打印分析报告"""
    print("="*100)
    print("📊 MCP 工具使用情况分析")
    print("="*100)
    
    all_tools = set(ALL_MCP_TOOLS.keys())
    used_tools = set(USED_MCP_TOOLS.keys())
    unused_tools = all_tools - used_tools
    
    print(f"\n📈 统计信息:")
    print(f"   - finance-mcp 总工具数：{len(all_tools)}")
    print(f"   - data-agent 已使用：{len(used_tools)}")
    print(f"   - data-agent 未使用：{len(unused_tools)}")
    print(f"   - 使用率：{len(used_tools)/len(all_tools)*100:.1f}%")
    
    print("\n" + "="*100)
    print("✅ 已使用的 MCP 工具")
    print("="*100)
    
    # 按模块分类显示已使用的工具
    modules = {
        "认证": ["auth_login", "auth_register", "auth_me"],
        "规则管理": ["list_reconciliation_rules", "get_reconciliation_rule", "save_reconciliation_rule", 
                   "update_reconciliation_rule", "delete_reconciliation_rule", "copy_reconciliation_rule"],
        "管理员": ["admin_login", "create_company", "create_department", "list_companies", 
                 "list_departments", "get_admin_view", "list_companies_public", "list_departments_public"],
        "会话管理": ["create_conversation", "list_conversations", "get_conversation", 
                   "update_conversation", "delete_conversation", "save_message"],
        "游客认证": ["create_guest_token", "verify_guest_token", "list_recommended_rules"],
        "对账模块": ["reconciliation_start", "reconciliation_status", "reconciliation_result", 
                   "reconciliation_list_tasks", "file_upload", "file_delete", "analyze_files", 
                   "read_excel_sheets", "detect_file_complexity"],
        "文件校验": ["validate_uploaded_files"],
        "数据同步": ["proc_rule_execute"],
        "规则查询": ["get_rule_from_bus", "list_digital_employees", "list_rules_by_employee"],
        "核对模块": ["recon_execute", "recon_task_execution"],
    }
    
    for module, tools in modules.items():
        used_in_module = [t for t in tools if t in used_tools]
        if used_in_module:
            print(f"\n  {module}:")
            for tool in used_in_module:
                print(f"    ✅ {tool:<40} - {ALL_MCP_TOOLS.get(tool, '')}")
                print(f"         📍 {USED_MCP_TOOLS.get(tool, 'unknown')}")
    
    print("\n" + "="*100)
    print("❌ 未使用的 MCP 工具")
    print("="*100)
    
    if unused_tools:
        # 按模块分类显示未使用的工具
        unused_by_module = {
            "对账配置": ["get_reconciliation"],
            "数据整理": ["data_preparation_start", "data_preparation_result", 
                       "data_preparation_status", "data_preparation_list_tasks"],
            "规则搜索": ["search_rules_by_mapping", "batch_get_reconciliation_rules"],
            "核对规则列表": ["recon_list_rules"],
        }
        
        for module, tools in unused_by_module.items():
            unused_in_module = [t for t in tools if t in unused_tools]
            if unused_in_module:
                print(f"\n  {module}:")
                for tool in unused_in_module:
                    print(f"    ❌ {tool:<40} - {ALL_MCP_TOOLS.get(tool, '')}")
    else:
        print("\n🎉 所有工具都被使用了！")
    
    print("\n" + "="*100)
    print("📝 分析总结")
    print("="*100)
    print("""
1. 核心功能覆盖:
   - ✅ 认证系统：完整使用（登录/注册/用户信息）
   - ✅ 规则管理：基本使用（增删改查/复制）
   - ✅ 会话管理：完整使用（创建/列表/获取/更新/删除/保存消息）
   - ✅ 对账执行：完整使用（开始/状态/结果/列表）
   - ✅ 文件处理：完整使用（上传/删除/分析/读取）
   - ✅ 文件校验：已使用
   - ✅ 数据同步：已使用
   - ✅ 规则查询：已使用（数字员工/规则列表）
   - ✅ 核对模块：已使用

2. 未使用的工具:
   - ❌ get_reconciliation: 获取对账配置（可能被 reconciliation_start 替代）
   - ❌ data_preparation_*: 数据整理模块工具（可能通过 proc_rule_execute 间接使用）
   - ❌ search_rules_by_mapping: 根据字段映射搜索规则（规则推荐功能）
   - ❌ batch_get_reconciliation_rules: 批量获取规则（规则推荐功能）
   - ❌ recon_list_rules: 列出核对规则（可能被其他工具替代）

3. 建议:
   - 考虑移除或重构未使用的工具，减少代码复杂度
   - 或者在 data-agent 中添加对应的使用场景
""")
    print("="*100)


if __name__ == "__main__":
    print_analysis()
