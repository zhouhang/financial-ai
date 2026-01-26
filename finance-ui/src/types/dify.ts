/**
 * TypeScript type definitions for Dify integration
 */

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  command?: string;
}

export interface ChatRequest {
  query: string;
  conversation_id?: string;
  streaming?: boolean;
}

export interface ChatResponse {
  event: string;
  message_id: string;
  conversation_id: string;
  answer: string;
  metadata?: {
    command?: string;
  };
  data?: {
    outputs?: {
      answer?: string;
    };
  };
  command?: string;
}

export interface ChatState {
  messages: ChatMessage[];
  conversationId: string | null;
  loading: boolean;
  sendMessage: (query: string) => Promise<void>;
  clearMessages: () => void;
  updateMessage: (messageId: string, content: string, clearCommand?: boolean) => void;
}
