import { useCallback, useEffect, useState } from 'react';
import type { Conversation } from '../types';

/** 后端返回的会话格式 */
interface ApiConversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  status: string;
  messages?: ApiMessage[];
}

/** 后端返回的消息格式 */
interface ApiMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
  metadata?: Record<string, unknown>;
}

/** 转换后端会话到前端格式 */
function convertConversation(api: ApiConversation): Conversation {
  return {
    id: api.id,
    title: api.title || '新对话',
    createdAt: new Date(api.created_at),
    updatedAt: new Date(api.updated_at),
    messages: (api.messages || []).map((m) => ({
      id: m.id,
      role: m.role,
      content: m.content,
      timestamp: new Date(m.created_at),
    })),
  };
}

interface UseConversationsOptions {
  authToken: string | null;
  onError?: (error: string) => void;
}

interface UseConversationsResult {
  /** 从服务器加载的会话列表 */
  serverConversations: Conversation[];
  /** 是否正在加载 */
  isLoading: boolean;
  /** 加载会话列表 */
  loadConversations: () => Promise<void>;
  /** 加载单个会话（包含消息） */
  loadConversation: (id: string) => Promise<Conversation | null>;
  /** 删除会话 */
  deleteConversation: (id: string) => Promise<boolean>;
  /** 清空本地缓存 */
  clearCache: () => void;
}

export function useConversations({
  authToken,
  onError,
}: UseConversationsOptions): UseConversationsResult {
  const [serverConversations, setServerConversations] = useState<Conversation[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(() => Boolean(authToken));

  /** 加载会话列表 */
  const loadConversations = useCallback(async () => {
    if (!authToken) {
      setServerConversations([]);
      return;
    }

    setIsLoading(true);
    try {
      const response = await fetch('/api/conversations', {
        headers: {
          Authorization: `Bearer ${authToken}`,
        },
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || '加载会话列表失败');
      }

      const data = await response.json();
      if (data.success && Array.isArray(data.conversations)) {
        const converted = data.conversations.map(convertConversation);
        setServerConversations(converted);
      }
    } catch (err) {
      console.error('加载会话列表失败:', err);
      onError?.(err instanceof Error ? err.message : '加载会话列表失败');
    } finally {
      setIsLoading(false);
    }
  }, [authToken, onError]);

  /** 加载单个会话（包含消息） */
  const loadConversation = useCallback(
    async (id: string): Promise<Conversation | null> => {
      if (!authToken) return null;

      console.log('[loadConversation] 开始加载会话:', id);
      try {
        const response = await fetch(`/api/conversations/${id}`, {
          headers: {
            Authorization: `Bearer ${authToken}`,
          },
        });

        if (!response.ok) {
          const error = await response.json().catch(() => ({}));
          console.error('[loadConversation] 请求失败:', error);
          throw new Error(error.detail || '加载会话失败');
        }

        const data = await response.json();
        console.log('[loadConversation] API返回数据:', {
          success: data.success,
          hasConversation: !!data.conversation,
          messagesCount: data.conversation?.messages?.length || 0,
        });
        if (data.success && data.conversation) {
          const converted = convertConversation(data.conversation);
          console.log('[loadConversation] 转换后消息数:', converted.messages.length);
          return converted;
        }
        return null;
      } catch (err) {
        console.error('加载会话失败:', err);
        onError?.(err instanceof Error ? err.message : '加载会话失败');
        return null;
      }
    },
    [authToken, onError]
  );

  /** 删除会话 */
  const deleteConversation = useCallback(
    async (id: string): Promise<boolean> => {
      if (!authToken) return false;

      try {
        const response = await fetch(`/api/conversations/${id}`, {
          method: 'DELETE',
          headers: {
            Authorization: `Bearer ${authToken}`,
          },
        });

        if (!response.ok) {
          const error = await response.json().catch(() => ({}));
          throw new Error(error.detail || '删除会话失败');
        }

        // 从本地列表中移除
        setServerConversations((prev) => prev.filter((c) => c.id !== id));
        return true;
      } catch (err) {
        console.error('删除会话失败:', err);
        onError?.(err instanceof Error ? err.message : '删除会话失败');
        return false;
      }
    },
    [authToken, onError]
  );

  /** 清空本地缓存 */
  const clearCache = useCallback(() => {
    setServerConversations([]);
  }, []);

  // 当 authToken 变化时自动加载会话列表
  // 注意：直接在 effect 内部实现加载逻辑，避免依赖 useCallback 导致的潜在问题
  useEffect(() => {
    if (!authToken) {
      setServerConversations([]);
      return;
    }

    let cancelled = false;

    const doLoad = async () => {
      setIsLoading(true);
      try {
        const response = await fetch('/api/conversations', {
          headers: {
            Authorization: `Bearer ${authToken}`,
          },
        });

        if (cancelled) return;

        if (!response.ok) {
          const error = await response.json().catch(() => ({}));
          throw new Error(error.detail || '加载会话列表失败');
        }

        const data = await response.json();
        if (!cancelled && data.success && Array.isArray(data.conversations)) {
          const converted = data.conversations.map(convertConversation);
          setServerConversations(converted);
        }
      } catch (err) {
        if (!cancelled) {
          console.error('加载会话列表失败:', err);
          onError?.(err instanceof Error ? err.message : '加载会话列表失败');
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    doLoad();

    return () => {
      cancelled = true;
    };
  }, [authToken, onError]);

  return {
    serverConversations,
    isLoading,
    loadConversations,
    loadConversation,
    deleteConversation,
    clearCache,
  };
}
