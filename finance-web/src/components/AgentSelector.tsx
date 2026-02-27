import { useState } from 'react';
import { MessageSquare, Plus, History, Sparkles } from 'lucide-react';
import type { AgentType } from '../types';
import { AVAILABLE_AGENTS } from '../types';

interface AgentSelectorProps {
  selectedAgent: AgentType;
  onSelectAgent: (agent: AgentType) => void;
}

export default function AgentSelector({
  selectedAgent,
  onSelectAgent,
}: AgentSelectorProps) {
  return (
    <div className="px-3 py-2">
      {/* 数字员工选择标签 */}
      <div className="text-xs font-medium text-gray-500 mb-2 px-2">
        选择数字员工
      </div>
      
      {/* Agent 选择按钮组 */}
      <div className="flex flex-col gap-1">
        {AVAILABLE_AGENTS.map((agent) => {
          const isSelected = selectedAgent === agent.id;
          const Icon = agent.icon === 'FileSpreadsheet' ? Sparkles : MessageSquare;
          
          return (
            <button
              key={agent.id}
              onClick={() => onSelectAgent(agent.id)}
              className={`
                flex items-center gap-2.5 px-3 py-2.5 rounded-lg
                transition-all duration-150 cursor-pointer w-full text-left
                ${isSelected
                  ? 'bg-blue-50 text-blue-600'
                  : 'text-gray-700 hover:bg-gray-100'
                }
              `}
            >
              <Icon className={`w-4 h-4 shrink-0 ${isSelected ? 'text-blue-600' : 'text-gray-500'}`} />
              <span className="text-sm font-medium truncate flex-1">{agent.name}</span>
              {isSelected && (
                <div className="w-1.5 h-1.5 rounded-full bg-blue-600 shrink-0" />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
