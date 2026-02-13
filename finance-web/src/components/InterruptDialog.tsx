import { useState } from 'react';
import { Send, AlertCircle } from 'lucide-react';

interface InterruptDialogProps {
  payload: Record<string, unknown>;
  onSubmit: (response: string) => void;
}

export default function InterruptDialog({
  payload,
  onSubmit,
}: InterruptDialogProps) {
  const [response, setResponse] = useState('');

  const question =
    (payload?.question as string) || '请回复以继续';
  const hint = (payload?.hint as string) || '';

  const handleSubmit = () => {
    if (!response.trim()) return;
    onSubmit(response.trim());
    setResponse('');
  };

  return (
    <div className="flex justify-center animate-fade-in-up">
      <div className="bg-primary-50 border-2 border-primary/30 rounded-2xl px-5 py-4 max-w-lg w-full">
        <div className="flex items-start gap-2.5 mb-3">
          <AlertCircle className="w-5 h-5 text-primary shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-text-primary">{question}</p>
            {hint && (
              <p className="text-xs text-text-secondary mt-1">{hint}</p>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={response}
            onChange={(e) => setResponse(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
            placeholder="输入您的回复..."
            className="flex-1 px-3 py-2 text-sm rounded-lg border border-border bg-white
              focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
          />
          <button
            onClick={handleSubmit}
            disabled={!response.trim()}
            className="px-3 py-2 rounded-lg bg-primary text-white text-sm font-medium
              hover:bg-primary-dark disabled:opacity-40 disabled:cursor-not-allowed
              transition-colors cursor-pointer"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
