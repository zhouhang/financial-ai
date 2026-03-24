import { useState, useEffect, useRef } from 'react';
import { X, AlertCircle, ChevronDown } from 'lucide-react';

interface LoginModalProps {
  isOpen: boolean;
  onClose: () => void;
  onLoginSuccess: (user: { username: string; userId: string }) => void | Promise<void>;
  /** 标题提示，如「登录后使用完整功能」；有值时显示为标题，否则显示默认「登录」/「注册」 */
  titleHint?: string | null;
}

type ModalMode = 'login' | 'register';

interface Company {
  id: string;
  name: string;
  code?: string;
}

interface Department {
  id: string;
  name: string;
  code?: string;
}

export default function LoginModal({ isOpen, onClose, onLoginSuccess, titleHint }: LoginModalProps) {
  const [mode, setMode] = useState<ModalMode>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [companyId, setCompanyId] = useState('');
  const [departmentId, setDepartmentId] = useState('');
  const [companies, setCompanies] = useState<Company[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const modalRef = useRef<HTMLDivElement>(null);
  const usernameInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      document.body.style.overflow = 'hidden';
      const timer = setTimeout(() => usernameInputRef.current?.focus(), 50);
      return () => {
        clearTimeout(timer);
        document.removeEventListener('keydown', handleEscape);
        document.body.style.overflow = 'unset';
      };
    }
    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, onClose]);

  useEffect(() => {
    if (isOpen) {
      setError('');
      setFieldErrors({});
      setMode('login');
      setCompanyId('');
      setDepartmentId('');
      setDepartments([]);
    }
  }, [isOpen]);

  useEffect(() => {
    if (isOpen && mode === 'register') {
      fetch('/api/companies')
        .then((r) => r.json())
        .then((data) => setCompanies(Array.isArray(data) ? data : []))
        .catch(() => setCompanies([]));
    }
  }, [isOpen, mode]);

  useEffect(() => {
    if (companyId) {
      fetch(`/api/departments?company_id=${encodeURIComponent(companyId)}`)
        .then((r) => r.json())
        .then((data) => setDepartments(Array.isArray(data) ? data : []))
        .catch(() => setDepartments([]));
      setDepartmentId('');
    } else {
      setDepartments([]);
      setDepartmentId('');
    }
  }, [companyId]);

  const clearFieldErrors = (field?: string) => {
    if (field) {
      setFieldErrors((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    } else {
      setFieldErrors({});
    }
  };

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    clearFieldErrors();

    const errs: Record<string, string> = {};
    if (!username.trim()) errs.username = '请输入用户名';
    if (!password) errs.password = '请输入密码';
    if (Object.keys(errs).length) {
      setFieldErrors(errs);
      return;
    }

    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('username', username);
      formData.append('password', password);

      const resp = await fetch('/api/auth/login', {
        method: 'POST',
        body: formData,
      });

      const data = await resp.json().catch(() => ({}));

      if (resp.ok && data.success && data.token) {
        const userInfo = {
          username: data.user?.username || username,
          userId: data.user?.id || data.user_id
        };
        localStorage.setItem('tally_auth_token', data.token);
        localStorage.setItem('tally_current_user', JSON.stringify({
          username: userInfo.username,
          userId: userInfo.userId,
        }));
        setUsername('');
        setPassword('');
        document.body.style.overflow = 'unset';
        onClose();
        void onLoginSuccess(userInfo);
      } else {
        const errMsg = typeof data.detail === 'string' ? data.detail : data.error || data.detail || '用户名或密码错误';
        setError(errMsg);
      }
    } catch (err) {
      setError('登录失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    clearFieldErrors();

    const errs: Record<string, string> = {};
    if (!companyId) errs.company = '请选择公司';
    if (!departmentId) errs.department = '请选择部门';
    if (!username.trim()) errs.username = '请输入用户名';
    if (!password) errs.password = '请输入密码';
    else if (password.length < 6) errs.password = '密码长度至少 6 位';
    if (Object.keys(errs).length) {
      setFieldErrors(errs);
      return;
    }

    setLoading(true);

    try {
      const formData = new FormData();
      formData.append('username', username);
      formData.append('password', password);
      formData.append('company_id', companyId);
      formData.append('department_id', departmentId);
      if (email.trim()) formData.append('email', email.trim());
      if (phone.trim()) formData.append('phone', phone.trim());

      const resp = await fetch('/api/auth/register', {
        method: 'POST',
        body: formData,
      });

      const data = await resp.json().catch(() => ({}));

      if (resp.ok && data.success && data.token) {
        const userInfo = {
          username: data.user?.username || username,
          userId: data.user?.id || data.user_id
        };
        localStorage.setItem('tally_auth_token', data.token);
        localStorage.setItem('tally_current_user', JSON.stringify({
          username: userInfo.username,
          userId: userInfo.userId,
        }));
        setUsername('');
        setPassword('');
        setEmail('');
        setPhone('');
        document.body.style.overflow = 'unset';
        onClose();
        void onLoginSuccess(userInfo);
      } else {
        const errMsg = typeof data.detail === 'string' ? data.detail : data.error || data.detail || '注册失败';
        setError(errMsg);
      }
    } catch (err) {
      setError('注册失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  const switchToRegister = (e: React.MouseEvent) => {
    e.preventDefault();
    setError('');
    clearFieldErrors();
    setCompanyId('');
    setDepartmentId('');
    setMode('register');
    setTimeout(() => usernameInputRef.current?.focus(), 50);
  };

  const switchToLogin = (e: React.MouseEvent) => {
    e.preventDefault();
    setError('');
    clearFieldErrors();
    setMode('login');
    setTimeout(() => usernameInputRef.current?.focus(), 50);
  };

  if (!isOpen) return null;

  return (
    <div
      data-login-modal-backdrop="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={handleBackdropClick}
    >
      <div
        ref={modalRef}
        className="bg-white rounded-xl shadow-2xl w-full max-w-md mx-4 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="text-lg font-semibold text-gray-900">
            {titleHint || (mode === 'login' ? '登录' : '注册')}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {mode === 'login' ? (
          <form onSubmit={handleLoginSubmit} noValidate className="p-6">
            {error && (
              <div className="mb-4 px-4 py-3 bg-red-50 border border-red-100 rounded-lg text-sm text-red-600 flex items-start gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-red-500" />
                <span>{error}</span>
              </div>
            )}

            <div className="space-y-4">
              <div>
                <label htmlFor="login-username" className="block text-sm font-medium text-gray-700 mb-1">
                  用户名
                </label>
                <input
                  ref={usernameInputRef}
                  id="login-username"
                  type="text"
                  value={username}
                  onChange={(e) => { setUsername(e.target.value); clearFieldErrors('username'); }}
                  className={`w-full px-4 py-2.5 border rounded-lg focus:outline-none focus:ring-2 focus:border-transparent transition-colors ${
                    fieldErrors.username ? 'border-red-300 focus:ring-red-500' : 'border-gray-200 focus:ring-blue-500'
                  }`}
                  placeholder="请输入用户名"
                />
                {fieldErrors.username && (
                  <p className="mt-1 text-xs text-red-500">{fieldErrors.username}</p>
                )}
              </div>

              <div>
                <label htmlFor="login-password" className="block text-sm font-medium text-gray-700 mb-1">
                  密码
                </label>
                <input
                  id="login-password"
                  type="password"
                  value={password}
                  onChange={(e) => { setPassword(e.target.value); clearFieldErrors('password'); }}
                  className={`w-full px-4 py-2.5 border rounded-lg focus:outline-none focus:ring-2 focus:border-transparent transition-colors ${
                    fieldErrors.password ? 'border-red-300 focus:ring-red-500' : 'border-gray-200 focus:ring-blue-500'
                  }`}
                  placeholder="请输入密码"
                />
                {fieldErrors.password && (
                  <p className="mt-1 text-xs text-red-500">{fieldErrors.password}</p>
                )}
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-6 px-4 py-2.5 bg-blue-500 hover:bg-blue-600 text-white font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? '登录中...' : '登录'}
            </button>

            <p className="mt-4 text-center text-sm text-gray-500">
              没有账号？{' '}
              <button type="button" onClick={switchToRegister} className="text-blue-500 hover:text-blue-600 font-medium">
                立即注册
              </button>
            </p>
          </form>
        ) : (
          <form onSubmit={handleRegisterSubmit} noValidate className="p-6">
            {error && (
              <div className="mb-4 px-4 py-3 bg-red-50 border border-red-100 rounded-lg text-sm text-red-600 flex items-start gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-red-500" />
                <span>{error}</span>
              </div>
            )}

            <div className="space-y-4">
              <div>
                <label htmlFor="reg-company" className="block text-sm font-medium text-gray-700 mb-1">
                  公司 *
                </label>
                <div className="relative">
                  <select
                    id="reg-company"
                    value={companyId}
                    onChange={(e) => { setCompanyId(e.target.value); clearFieldErrors('company'); }}
                    className={`w-full pl-4 pr-10 py-2.5 border rounded-lg focus:outline-none focus:ring-2 focus:border-transparent bg-white transition-colors appearance-none ${
                      fieldErrors.company ? 'border-red-300 focus:ring-red-500' : 'border-gray-200 focus:ring-blue-500'
                    }`}
                  >
                    <option value="">请选择公司</option>
                    {companies.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400 pointer-events-none" />
                </div>
                {fieldErrors.company && (
                  <p className="mt-1 text-xs text-red-500">{fieldErrors.company}</p>
                )}
                {companies.length === 0 && !fieldErrors.company && (
                  <p className="mt-1 text-xs text-amber-600">暂无公司，请联系管理员创建</p>
                )}
              </div>

              <div>
                <label htmlFor="reg-department" className="block text-sm font-medium text-gray-700 mb-1">
                  部门 *
                </label>
                <div className="relative">
                  <select
                    id="reg-department"
                    value={departmentId}
                    onChange={(e) => { setDepartmentId(e.target.value); clearFieldErrors('department'); }}
                    className={`w-full pl-4 pr-10 py-2.5 border rounded-lg focus:outline-none focus:ring-2 focus:border-transparent bg-white transition-colors appearance-none ${
                      fieldErrors.department ? 'border-red-300 focus:ring-red-500' : 'border-gray-200 focus:ring-blue-500'
                    }`}
                    disabled={!companyId}
                  >
                    <option value="">{companyId ? '请选择部门' : '请先选择公司'}</option>
                    {departments.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400 pointer-events-none" />
                </div>
                {fieldErrors.department && (
                  <p className="mt-1 text-xs text-red-500">{fieldErrors.department}</p>
                )}
              </div>

              <div>
                <label htmlFor="reg-username" className="block text-sm font-medium text-gray-700 mb-1">
                  用户名 *
                </label>
                <input
                  ref={usernameInputRef}
                  id="reg-username"
                  type="text"
                  value={username}
                  onChange={(e) => { setUsername(e.target.value); clearFieldErrors('username'); }}
                  className={`w-full px-4 py-2.5 border rounded-lg focus:outline-none focus:ring-2 focus:border-transparent transition-colors ${
                    fieldErrors.username ? 'border-red-300 focus:ring-red-500' : 'border-gray-200 focus:ring-blue-500'
                  }`}
                  placeholder="请输入用户名"
                />
                {fieldErrors.username && (
                  <p className="mt-1 text-xs text-red-500">{fieldErrors.username}</p>
                )}
              </div>

              <div>
                <label htmlFor="reg-password" className="block text-sm font-medium text-gray-700 mb-1">
                  密码 *
                </label>
                <input
                  id="reg-password"
                  type="password"
                  value={password}
                  onChange={(e) => { setPassword(e.target.value); clearFieldErrors('password'); }}
                  className={`w-full px-4 py-2.5 border rounded-lg focus:outline-none focus:ring-2 focus:border-transparent transition-colors ${
                    fieldErrors.password ? 'border-red-300 focus:ring-red-500' : 'border-gray-200 focus:ring-blue-500'
                  }`}
                  placeholder="请输入密码（至少 6 位）"
                />
                {fieldErrors.password && (
                  <p className="mt-1 text-xs text-red-500">{fieldErrors.password}</p>
                )}
              </div>

              <div>
                <label htmlFor="reg-email" className="block text-sm font-medium text-gray-700 mb-1">
                  邮箱（可选）
                </label>
                <input
                  id="reg-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-4 py-2.5 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="请输入邮箱"
                />
              </div>

              <div>
                <label htmlFor="reg-phone" className="block text-sm font-medium text-gray-700 mb-1">
                  手机号（可选）
                </label>
                <input
                  id="reg-phone"
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="w-full px-4 py-2.5 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="请输入手机号"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-6 px-4 py-2.5 bg-blue-500 hover:bg-blue-600 text-white font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? '注册中...' : '注册'}
            </button>

            <p className="mt-4 text-center text-sm text-gray-500">
              已有账号？{' '}
              <button type="button" onClick={switchToLogin} className="text-blue-500 hover:text-blue-600 font-medium">
                返回登录
              </button>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
