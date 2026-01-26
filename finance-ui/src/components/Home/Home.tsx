/**
 * Home page with chat interface - DeepSeek Style
 */
import React, { useState, useRef, useEffect } from 'react';
import { Layout, Input, Button, Typography, Space } from 'antd';
import { SendOutlined, RobotOutlined, UserOutlined, ClearOutlined } from '@ant-design/icons';
import { useChatStore } from '@/stores/chatStore';
import CreateSchemaModal from '@/components/Canvas/CreateSchemaModal';
import { Schema } from '@/types/canvas';
import './Home.css';

const { Content } = Layout;
const { TextArea } = Input;

const Home: React.FC = () => {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { messages, loading, sendMessage, clearMessages, updateMessage } = useChatStore();
  const [createSchemaModalVisible, setCreateSchemaModalVisible] = useState(false);
  const [createSchemaMessageId, setCreateSchemaMessageId] = useState<string | null>(null);

  // Auto scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    try {
      await sendMessage(input);
      setInput('');
    } catch (error) {
      console.error('Failed to send message:', error);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Render login form without error container (error will be added dynamically on failure)
  const renderLoginForm = (content: string) => {
    // Remove [login_form] directive from content
    const cleanContent = content.replace(/\[login_form\]/gi, '').trim();

    // Generate login form HTML
    const loginFormHTML = `
      <form data-format="json">
        <label for="username">用户名:</label>
        <input type="text" name="username" placeholder="请输入用户名" />
        <label for="password">密码:</label>
        <input type="password" name="password" placeholder="请输入密码" />
        <button data-size="small" data-variant="primary" type="button">登录</button>
      </form>
    `;

    // Wrap the content with login form container (no error div initially)
    return `
      <div class="login-form-container">
        ${cleanContent}
        ${loginFormHTML}
      </div>
    `;
  };

  // Render create schema button
  const renderCreateSchemaButton = (content: string, messageId: string) => {
    const cleanContent = content.replace(/\[create_schema\]/gi, '').trim();
    return `
      <div class="create-schema-container">
        ${cleanContent}
        <button
          class="create-schema-btn"
          data-message-id="${messageId}"
          type="button">
          开始创建规则
        </button>
      </div>
    `;
  };

  // Handle login form submission
  const handleLoginSubmit = async (messageId: string, username: string, password: string) => {
    const loginFormDiv = document.querySelector(`[data-message-id="${messageId}"] .login-form-container`);
    const submitButton = loginFormDiv?.querySelector('button[type="button"]') as HTMLButtonElement;

    // Remove any existing error div
    const existingError = loginFormDiv?.querySelector('.login-error');
    if (existingError) {
      existingError.remove();
    }

    // Disable button with loading state
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.innerHTML = '<span class="loading-spinner"></span> 登录中...';
    }

    try {
      const response = await fetch('/api/dify/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: JSON.stringify({ username, password }),
          conversation_id: useChatStore.getState().conversationId || undefined,
          streaming: false,
        }),
      });

      const data = await response.json();

      if (response.ok && data.answer) {
        // Login successful - completely replace the message content with API response
        // Clear the command to prevent re-rendering the login form
        updateMessage(messageId, data.answer, true);
      } else {
        // Login failed - show error message from API below the button
        const errorMessage = data.answer || data.detail || '登录失败，请重试';

        // Create and insert error div after the form
        const errorDiv = document.createElement('div');
        errorDiv.className = 'login-error';
        errorDiv.textContent = errorMessage;
        loginFormDiv?.appendChild(errorDiv);

        // Re-enable button
        if (submitButton) {
          submitButton.disabled = false;
          submitButton.innerHTML = '登录';
        }
      }
    } catch (error) {
      console.error('Login error:', error);
      const errorMessage = error instanceof Error ? error.message : '网络错误，请重试';

      // Create and insert error div after the form
      const errorDiv = document.createElement('div');
      errorDiv.className = 'login-error';
      errorDiv.textContent = errorMessage;
      loginFormDiv?.appendChild(errorDiv);

      // Re-enable button
      if (submitButton) {
        submitButton.disabled = false;
        submitButton.innerHTML = '登录';
      }
    }
  };

  // Setup login form event listeners
  useEffect(() => {
    const setupLoginForms = () => {
      document.querySelectorAll('.login-form-container form').forEach((form) => {
        const messageId = form.closest('[data-message-id]')?.getAttribute('data-message-id');
        if (!messageId) return;

        const button = form.querySelector('button[type="button"]');
        const usernameInput = form.querySelector('input[name="username"]') as HTMLInputElement;
        const passwordInput = form.querySelector('input[name="password"]') as HTMLInputElement;

        if (button && usernameInput && passwordInput) {
          // Remove existing listener to avoid duplicates
          const newButton = button.cloneNode(true) as HTMLButtonElement;
          button.parentNode?.replaceChild(newButton, button);

          newButton.addEventListener('click', (e) => {
            e.preventDefault();
            const username = usernameInput.value.trim();
            const password = passwordInput.value.trim();

            if (username && password) {
              handleLoginSubmit(messageId, username, password);
            }
          });
        }
      });
    };

    // Setup create schema buttons
    const setupCreateSchemaButtons = () => {
      document.querySelectorAll('.create-schema-btn').forEach((button) => {
        const messageId = button.getAttribute('data-message-id');
        if (!messageId) return;

        // Remove existing listener to avoid duplicates
        const newButton = button.cloneNode(true) as HTMLButtonElement;
        button.parentNode?.replaceChild(newButton, button);

        newButton.addEventListener('click', () => {
          setCreateSchemaMessageId(messageId);
          setCreateSchemaModalVisible(true);
        });
      });
    };

    setupLoginForms();
    setupCreateSchemaButtons();
  }, [messages]);

  return (
    <Layout style={{
      minHeight: '100vh',
      background: '#0f0f0f',
      display: 'flex',
      flexDirection: 'column'
    }}>
      {/* Header */}
      <div style={{
        background: '#1a1a1a',
        borderBottom: '1px solid #2a2a2a',
        padding: '12px 24px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <RobotOutlined style={{ fontSize: 24, color: '#4a9eff' }} />
          <Typography.Title level={4} style={{ margin: 0, color: '#fff' }}>
            Finance AI 助手
          </Typography.Title>
        </div>
        <Button
          icon={<ClearOutlined />}
          onClick={clearMessages}
          style={{
            background: 'transparent',
            border: '1px solid #2a2a2a',
            color: '#999'
          }}
        >
          清空对话
        </Button>
      </div>

      {/* Chat Messages Area */}
      <Content style={{
        flex: 1,
        overflowY: 'auto',
        padding: '24px',
        maxWidth: 900,
        width: '100%',
        margin: '0 auto'
      }}>
        {messages.length === 0 ? (
          <div style={{
            textAlign: 'center',
            padding: '80px 20px',
            color: '#666'
          }}>
            <RobotOutlined style={{ fontSize: 64, marginBottom: 24, color: '#4a9eff' }} />
            <Typography.Title level={3} style={{ color: '#fff', marginBottom: 16 }}>
              欢迎使用 Finance AI 助手
            </Typography.Title>
            <Typography.Paragraph style={{ color: '#999', fontSize: 16 }}>
              我可以帮您创建和管理财务数据处理规则
            </Typography.Paragraph>
            <div style={{ marginTop: 32 }}>
              <Space direction="vertical" size="middle">
                <Button
                  type="text"
                  onClick={() => setInput('帮我创建一个货币资金数据整理的规则')}
                  style={{
                    color: '#4a9eff',
                    border: '1px solid #2a2a2a',
                    background: '#1a1a1a',
                    height: 'auto',
                    padding: '12px 24px'
                  }}
                >
                  💰 创建货币资金数据整理规则
                </Button>
                <Button
                  type="text"
                  onClick={() => setInput('显示我的所有规则')}
                  style={{
                    color: '#4a9eff',
                    border: '1px solid #2a2a2a',
                    background: '#1a1a1a',
                    height: 'auto',
                    padding: '12px 24px'
                  }}
                >
                  📋 查看我的所有规则
                </Button>
              </Space>
            </div>
          </div>
        ) : (
          <div>
            {messages.map((message, index) => (
              <div
                key={message.id || index}
                data-message-id={message.id}
                style={{
                  marginBottom: 32,
                  display: 'flex',
                  gap: 16,
                  alignItems: 'flex-start'
                }}
              >
                {/* Avatar */}
                <div style={{
                  width: 36,
                  height: 36,
                  borderRadius: '50%',
                  background: message.role === 'user' ? '#4a9eff' : '#2a2a2a',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0
                }}>
                  {message.role === 'user' ? (
                    <UserOutlined style={{ fontSize: 18, color: '#fff' }} />
                  ) : (
                    <RobotOutlined style={{ fontSize: 18, color: '#4a9eff' }} />
                  )}
                </div>

                {/* Message Content */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    color: '#999',
                    fontSize: 12,
                    marginBottom: 8
                  }}>
                    {message.role === 'user' ? '你' : 'Finance AI'}
                    <span style={{ marginLeft: 12 }}>
                      {new Date(message.timestamp).toLocaleTimeString('zh-CN', {
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                    </span>
                  </div>
                  {message.content ? (
                    <div
                      className="message-content"
                      style={{
                        color: '#e0e0e0',
                        fontSize: 15,
                        lineHeight: 1.7,
                        wordBreak: 'break-word'
                      }}
                      dangerouslySetInnerHTML={{
                        __html: message.command === 'login_form'
                          ? renderLoginForm(message.content)
                          : message.command === 'create_schema'
                          ? renderCreateSchemaButton(message.content, message.id)
                          : message.content
                      }}
                    />
                  ) : (
                    <div style={{ color: '#666', fontSize: 15 }}>
                      <span className="typing-indicator">正在思考</span>
                    </div>
                  )}
                  <style>{`
                    .message-content form {
                      background: #1a1a1a !important;
                      border: 1px solid #2a2a2a !important;
                      border-radius: 8px !important;
                      padding: 16px !important;
                      margin: 12px 0 !important;
                      display: block !important;
                    }
                    .message-content label {
                      display: block !important;
                      color: #e0e0e0 !important;
                      margin: 8px 0 4px 0 !important;
                      font-size: 14px !important;
                    }
                    .message-content input {
                      width: 100% !important;
                      background: #0f0f0f !important;
                      border: 1px solid #2a2a2a !important;
                      border-radius: 6px !important;
                      padding: 8px 12px !important;
                      color: #e0e0e0 !important;
                      font-size: 14px !important;
                      margin-bottom: 12px !important;
                      box-sizing: border-box !important;
                      display: block !important;
                    }
                    .message-content button {
                      background: #4a9eff !important;
                      color: #fff !important;
                      border: none !important;
                      border-radius: 6px !important;
                      padding: 8px 16px !important;
                      font-size: 14px !important;
                      cursor: pointer !important;
                      margin-top: 8px !important;
                      display: inline-block !important;
                    }
                    .message-content button:hover {
                      background: #3a8eef !important;
                    }
                    .message-content button:disabled {
                      background: #2a5a8f !important;
                      cursor: not-allowed !important;
                      opacity: 0.7 !important;
                    }
                    .message-content * {
                      color: #e0e0e0 !important;
                    }
                    .login-error {
                      color: #f87171 !important;
                      background: #3a1a1a !important;
                      border: 1px solid #5a2a2a !important;
                      border-radius: 6px !important;
                      padding: 8px 12px !important;
                      margin-top: 12px !important;
                      font-size: 14px !important;
                    }
                    .loading-spinner {
                      display: inline-block !important;
                      width: 12px !important;
                      height: 12px !important;
                      border: 2px solid #ffffff !important;
                      border-top-color: transparent !important;
                      border-radius: 50% !important;
                      animation: spin 0.6s linear infinite !important;
                      margin-right: 6px !important;
                      vertical-align: middle !important;
                    }
                    @keyframes spin {
                      to { transform: rotate(360deg); }
                    }
                  `}</style>
                  {message.command && (
                    <div style={{
                      marginTop: 12,
                      padding: '8px 12px',
                      background: '#1a1a1a',
                      border: '1px solid #2a2a2a',
                      borderRadius: 6,
                      fontSize: 13,
                      color: '#4a9eff'
                    }}>
                      🔍 检测到命令: <strong>{message.command}</strong>
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </Content>

      {/* Input Area */}
      <div style={{
        background: '#1a1a1a',
        borderTop: '1px solid #2a2a2a',
        padding: '16px 24px',
        position: 'sticky',
        bottom: 0
      }}>
        <div style={{
          maxWidth: 900,
          margin: '0 auto',
          display: 'flex',
          gap: 12,
          alignItems: 'flex-end'
        }}>
          <TextArea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
            autoSize={{ minRows: 1, maxRows: 6 }}
            disabled={loading}
            style={{
              flex: 1,
              background: '#0f0f0f',
              border: '1px solid #2a2a2a',
              color: '#e0e0e0',
              fontSize: 15,
              borderRadius: 8,
              resize: 'none'
            }}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            loading={loading}
            disabled={!input.trim()}
            style={{
              height: 40,
              background: '#4a9eff',
              border: 'none',
              borderRadius: 8
            }}
          >
            发送
          </Button>
        </div>
      </div>

      {/* Create Schema Modal */}
      <CreateSchemaModal
        visible={createSchemaModalVisible}
        messageId={createSchemaMessageId}
        onClose={() => {
          setCreateSchemaModalVisible(false);
          setCreateSchemaMessageId(null);
        }}
        onSuccess={(schema: Schema) => {
          // Update message with success info
          if (createSchemaMessageId) {
            updateMessage(
              createSchemaMessageId,
              `规则创建成功！\n\n规则名称：${schema.name_cn}\n规则类型：${schema.work_type === 'DATA_PREPARATION' ? '数据整理' : '数据对账'}\n规则ID：${schema.type_key}\n\n您现在可以使用此规则进行数据处理。`,
              true
            );
          }
          setCreateSchemaModalVisible(false);
          setCreateSchemaMessageId(null);
        }}
      />
    </Layout>
  );
};

export default Home;
