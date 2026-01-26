/**
 * Dify API
 */
import apiClient from './client';
import { ChatRequest, ChatResponse } from '@/types/dify';

export const difyApi = {
  /**
   * Send chat message to Dify
   */
  chat: async (request: ChatRequest): Promise<ChatResponse> => {
    const response = await apiClient.post<ChatResponse>('/dify/chat', request);
    return response.data;
  },

  /**
   * Send chat message with streaming response
   */
  chatStream: async (
    request: ChatRequest,
    onMessage: (data: ChatResponse) => void,
    onError: (error: Error) => void
  ): Promise<void> => {
    try {
      const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/dify/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ ...request, streaming: true }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('No response body');
      }

      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        // Decode chunk and add to buffer
        buffer += decoder.decode(value, { stream: true });

        // Split by double newline (SSE event separator)
        const events = buffer.split('\n\n');

        // Keep the last incomplete event in buffer
        buffer = events.pop() || '';

        // Process complete events
        for (const event of events) {
          if (!event.trim()) continue;

          // Split event into lines
          const lines = event.split('\n');
          let eventData = '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              eventData = line.slice(6).trim();
              break;
            }
          }

          if (eventData) {
            try {
              const data = JSON.parse(eventData);
              console.log('Received SSE event:', data.event, data);
              onMessage(data);
            } catch (e) {
              console.error('Failed to parse SSE data:', eventData, e);
            }
          }
        }
      }

      // Process any remaining data in buffer
      if (buffer.trim()) {
        const lines = buffer.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6).trim());
              console.log('Received final SSE event:', data.event, data);
              onMessage(data);
            } catch (e) {
              console.error('Failed to parse final SSE data:', line, e);
            }
          }
        }
      }
    } catch (error) {
      console.error('Streaming error:', error);
      onError(error as Error);
    }
  },
};
