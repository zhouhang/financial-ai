/**
 * Dify API - Direct integration with Dify service
 */
import { ChatRequest, ChatResponse } from '@/types/dify';

// Dify API configuration from environment variables
const DIFY_API_URL = import.meta.env.VITE_DIFY_API_URL || 'http://localhost/v1';
const DIFY_API_KEY = import.meta.env.VITE_DIFY_API_KEY || 'app-pffBjBphPBhbrSwz8mxku2R3';

/**
 * Detect special commands in Dify response
 */
function detectCommand(text: string): string | null {
  const commands = {
    '\\[create_schema\\]': 'create_schema',
    '\\[update_schema\\]': 'update_schema',
    '\\[schema_list\\]': 'schema_list',
    '\\[login_form\\]': 'login_form',
  };

  for (const [pattern, command] of Object.entries(commands)) {
    if (new RegExp(pattern, 'i').test(text)) {
      return command;
    }
  }

  return null;
}

export const difyApi = {
  /**
   * Send chat message to Dify (blocking mode)
   */
  chat: async (request: ChatRequest): Promise<ChatResponse> => {
    const response = await fetch(`${DIFY_API_URL}/chat-messages`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${DIFY_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        inputs: {},
        query: request.query,
        response_mode: 'blocking',
        user: 'anonymous_user',
        conversation_id: request.conversation_id,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }

    const data = await response.json();

    // Detect command in response
    const answer = data.answer || '';
    const command = detectCommand(answer);

    return {
      event: 'message',
      message_id: data.message_id,
      conversation_id: data.conversation_id,
      answer: answer,
      metadata: {
        ...data.metadata,
        command: command || undefined,
      },
    };
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
      const response = await fetch(`${DIFY_API_URL}/chat-messages`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${DIFY_API_KEY}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          inputs: {},
          query: request.query,
          response_mode: 'streaming',
          user: 'anonymous_user',
          conversation_id: request.conversation_id,
        }),
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
      let fullAnswer = '';

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

              // Accumulate answer for command detection
              if (data.event === 'message' || data.event === 'agent_message') {
                if (data.answer) {
                  fullAnswer += data.answer;
                }
              } else if (data.event === 'workflow_finished') {
                if (data.data?.outputs?.answer) {
                  fullAnswer = data.data.outputs.answer;
                }
              } else if (data.event === 'message_end') {
                if (data.answer) {
                  fullAnswer = data.answer;
                }
              }

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

      // Send command detection event
      const command = detectCommand(fullAnswer);
      if (command) {
        console.log('Command detected:', command);
        onMessage({
          event: 'command_detected',
          command: command,
        } as ChatResponse);
      }
    } catch (error) {
      console.error('Streaming error:', error);
      onError(error as Error);
    }
  },
};
