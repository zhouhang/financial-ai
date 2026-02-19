"""HTML 表单生成模块

包含登录和注册表单的 HTML 生成函数。
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


def generate_register_form(error: str = "") -> str:
    """生成注册表单 HTML"""
    error_html = f'<div class="auth-error">❌ {error}</div>' if error else ""
    return f"""
<div class="auth-form-container">
  <h3>用户注册</h3>
  {error_html}
  <form id="register-form" class="auth-form">
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
      <label for="company_code">公司编码</label>
      <input type="text" id="company_code" name="company_code" placeholder="加入已有公司（选填）" />
    </div>
    <div class="form-group">
      <label for="department_code">部门编码</label>
      <input type="text" id="department_code" name="department_code" placeholder="选填" />
    </div>
    <button type="submit" class="btn-primary">注册</button>
  </form>
  <p class="auth-hint">已有账号？请输入"我要登录"</p>
</div>
"""
