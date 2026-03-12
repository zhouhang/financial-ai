"""HTML 表单生成模块

包含登录、注册、管理员相关表单的 HTML 生成函数。
"""

from __future__ import annotations


def generate_login_form(error: str = "") -> str:
    """生成登录表单 HTML"""
    error_html = f'<div class="auth-error">❌ {error}</div>' if error else ""
    return f"""
<div class="auth-form-container">
  <h3>用户登录</h3>
  {error_html}
  <form id="login-form" class="auth-form">
    <div class="form-group">
      <label for="username">用户名</label>
      <input type="text" id="username" name="username" required placeholder="请输入用户名" />
    </div>
    <div class="form-group">
      <label for="password">密码</label>
      <input type="password" id="password" name="password" required placeholder="请输入密码" />
    </div>
    <button type="submit" class="btn-primary">登录</button>
  </form>
  <p class="auth-hint">没有账号？请输入"我要注册"</p>
</div>
"""


def generate_register_form(error: str = "", companies: list = None, departments: list = None, selected_company_id: str = "") -> str:
    """生成注册表单 HTML
    
    Args:
        error: 错误信息
        companies: 公司列表
        departments: 部门列表（当选择了公司后传入）
        selected_company_id: 已选择的公司 ID
    """
    error_html = f'<div class="auth-error">❌ {error}</div>' if error else ""
    
    # 公司下拉选项
    companies_html = ""
    if companies:
        for c in companies:
            selected = 'selected' if str(c["id"]) == str(selected_company_id) else ''
            companies_html += f'<option value="{c["id"]}" {selected}>{c["name"]}</option>'
    else:
        companies_html = '<option value="">暂无公司，请联系管理员创建</option>'
    
    # 部门下拉选项
    departments_html = ""
    if departments:
        departments_html = "".join([f'<option value="{d["id"]}">{d["name"]}</option>' for d in departments])
    else:
        departments_html = '<option value="">请先选择公司</option>'
    
    # 如果还没选择公司，显示选择公司的表单
    if not selected_company_id:
        return f"""
<div class="auth-form-container">
  <h3>用户注册 - 第1步：选择公司</h3>
  {error_html}
  <form id="select_company-form" class="auth-form">
    <div class="form-group">
      <label for="company_id">请选择公司 *</label>
      <select id="company_id" name="company_id" required>
        <option value="">请选择公司</option>
        {companies_html}
      </select>
    </div>
    <button type="submit" class="btn-primary">下一步</button>
  </form>
  <p class="auth-hint">已有账号？请输入"我要登录"</p>
</div>
"""
    
    # 已选择公司，显示完整注册表单
    return f"""
<div class="auth-form-container">
  <h3>用户注册 - 第2步：填写信息</h3>
  {error_html}
  <form id="register-form" class="auth-form">
    <input type="hidden" name="company_id" value="{selected_company_id}" />
    <div class="form-group">
      <label for="username">用户名 *</label>
      <input type="text" id="username" name="username" required placeholder="请输入用户名" />
    </div>
    <div class="form-group">
      <label for="password">密码 *</label>
      <input type="password" id="password" name="password" required placeholder="至少6位字符" />
    </div>
    <div class="form-group">
      <label for="email">邮箱</label>
      <input type="email" id="email" name="email" placeholder="选填" />
    </div>
    <div class="form-group">
      <label for="phone">手机号</label>
      <input type="tel" id="phone" name="phone" placeholder="选填" />
    </div>
    <div class="form-group">
      <label for="department_id">部门 *</label>
      <select id="department_id" name="department_id" required>
        <option value="">请选择部门</option>
        {departments_html}
      </select>
    </div>
    <button type="submit" class="btn-primary">注册</button>
  </form>
  <p class="auth-hint">已有账号？请输入"我要登录"</p>
</div>
"""


def generate_admin_login_form(error: str = "") -> str:
    """生成管理员登录表单 HTML"""
    error_html = f'<div class="auth-error">❌ {error}</div>' if error else ""
    return f"""
<div class="auth-form-container">
  <h3>管理员登录</h3>
  {error_html}
  <form id="admin_login-form" class="auth-form">
    <div class="form-group">
      <label for="username">管理员用户名</label>
      <input type="text" id="username" name="username" required placeholder="请输入管理员用户名" />
    </div>
    <div class="form-group">
      <label for="password">密码</label>
      <input type="password" id="password" name="password" required placeholder="请输入密码" />
    </div>
    <button type="submit" class="btn-primary">管理员登录</button>
  </form>
  <p class="auth-hint">普通用户请输入"我要登录"</p>
</div>
"""


def generate_create_company_form(error: str = "") -> str:
    """生成创建公司表单 HTML"""
    error_html = f'<div class="auth-error">❌ {error}</div>' if error else ""
    return f"""
<div class="auth-form-container">
  <h3>创建公司</h3>
  {error_html}
  <form id="create_company-form" class="auth-form">
    <div class="form-group">
      <label for="name">公司名称 *</label>
      <input type="text" id="name" name="name" required placeholder="请输入公司名称" />
    </div>
    <button type="submit" class="btn-primary">创建公司</button>
  </form>
  <p class="auth-hint">输入"返回"回到管理员视图</p>
</div>
"""


def generate_create_department_form(companies: list = None, error: str = "") -> str:
    """生成创建部门表单 HTML"""
    error_html = f'<div class="auth-error">❌ {error}</div>' if error else ""
    
    companies_html = ""
    if companies:
        companies_html = "".join([f'<option value="{c["id"]}">{c["name"]}</option>' for c in companies])
    else:
        companies_html = '<option value="">暂无公司</option>'
    
    return f"""
<div class="auth-form-container">
  <h3>创建部门</h3>
  {error_html}
  <form id="create_department-form" class="auth-form">
    <div class="form-group">
      <label for="company_id">所属公司 *</label>
      <select id="company_id" name="company_id" required>
        <option value="">请选择公司</option>
        {companies_html}
      </select>
    </div>
    <div class="form-group">
      <label for="name">部门名称 *</label>
      <input type="text" id="name" name="name" required placeholder="请输入部门名称" />
    </div>
    <button type="submit" class="btn-primary">创建部门</button>
  </form>
  <p class="auth-hint">输入"返回"回到管理员视图</p>
</div>
"""


def generate_admin_view(data: dict = None, admin_token: str = "") -> str:
    """生成管理员视图 HTML"""
    if not data:
        data = {"companies": []}
    
    companies_html = ""
    for company in data.get("companies", []):
        depts_html = ""
        for dept in company.get("departments", []):
            employees = ", ".join([e["username"] for e in dept.get("employees", [])]) or "无"
            rules = ", ".join([r["name"] for r in dept.get("rules", [])]) or "无"
            depts_html += f"""
            <li>
              <strong>{dept["name"]}</strong>
              <ul>
                <li>员工: {employees}</li>
                <li>规则: {rules}</li>
              </ul>
            </li>"""
        
        companies_html += f"""
        <li>
          <strong>{company["name"]}</strong>
          <ul>{depts_html}</ul>
        </li>"""
    
    if not companies_html:
        companies_html = "<li>暂无公司数据</li>"
    
    return f"""
<div class="admin-view-container">
  <h3>管理员视图</h3>
  <ul class="admin-tree">
    {companies_html}
  </ul>
  <p class="admin-hint">
    输入"创建公司"添加公司 | 输入"创建部门"添加部门 | 输入"退出"退出管理员
  </p>
</div>
"""
