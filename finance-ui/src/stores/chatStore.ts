/**
 * Chat state management with Zustand - Streaming Mode
 */
import { create } from 'zustand';
import { difyApi } from '@/api/dify';
import { ChatState, ChatMessage } from '@/types/dify';

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  conversationId: null,
  loading: false,

  sendMessage: async (query: string) => {
    // Add user message
    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: query,
      timestamp: new Date(),
    };

    // Create placeholder for assistant message
    const assistantMessageId = `assistant-${Date.now()}`;
    const assistantMessage: ChatMessage = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
    };

    set((state) => ({
      messages: [...state.messages, userMessage, assistantMessage],
      loading: false, // Set to false since we're showing the placeholder
    }));

    try {
      let fullAnswer = '';
      let messageId = '';
      let conversationId = '';
      let detectedCommand: string | null = null;

      // Use streaming API
      await difyApi.chatStream(
        {
          query,
          conversation_id: get().conversationId || undefined,
        },
        (data) => {
          // Handle streaming data
          if (data.event === 'message' || data.event === 'agent_message') {
            // Accumulate answers instead of replacing
            if (data.answer) {
              fullAnswer += data.answer;
            }
            messageId = data.message_id || messageId;
            conversationId = data.conversation_id || conversationId;

            // Update message content in real-time
            set((state) => ({
              messages: state.messages.map((msg) =>
                msg.id === assistantMessageId
                  ? { ...msg, content: fullAnswer, id: messageId || msg.id }
                  : msg
              ),
            }));
          } else if (data.event === 'workflow_finished') {
            // Use complete answer from workflow_finished event
            if (data.data?.outputs?.answer) {
              fullAnswer = data.data.outputs.answer;
              set((state) => ({
                messages: state.messages.map((msg) =>
                  msg.id === assistantMessageId || msg.id === messageId
                    ? { ...msg, content: fullAnswer }
                    : msg
                ),
              }));
            }
          } else if (data.event === 'message_end') {
            // Final message with metadata
            if (data.metadata?.command) {
              detectedCommand = data.metadata.command;
            }
          } else if (data.event === 'command_detected') {
            // Command detected event from backend
            detectedCommand = data.command;
          }
        },
        (error) => {
          console.error('Streaming error:', error);
          // Update message with error
          set((state) => ({
            messages: state.messages.map((msg) =>
              msg.id === assistantMessageId
                ? { ...msg, content: '抱歉，发生了错误。请稍后重试。' }
                : msg
            ),
          }));
        }
      );

      // Update final message with command and conversation ID
      set((state) => ({
        messages: state.messages.map((msg) =>
          msg.id === assistantMessageId || msg.id === messageId
            ? { ...msg, command: detectedCommand || undefined }
            : msg
        ),
        conversationId: conversationId || state.conversationId,
      }));
    } catch (error) {
      console.error('Failed to send message:', error);
      throw error;
    }
  },

  clearMessages: () => {
    set({
      messages: [],
      conversationId: null,
      loading: false,
    });
  },

  updateMessage: (messageId: string, content: string, clearCommand?: boolean) => {
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === messageId
          ? { ...msg, content, ...(clearCommand ? { command: undefined } : {}) }
          : msg
      ),
    }));
  },
}));
