import type { CollaborationProvider } from './types';

export interface CollaborationChannelCard {
  provider: CollaborationProvider;
  title: string;
  description: string;
  accent: string;
  clientIdLabel: string;
  clientSecretLabel: string;
  robotCodeLabel: string;
  defaultName: string;
}

export const COLLABORATION_CHANNEL_CARDS: CollaborationChannelCard[] = [
  {
    provider: 'dingtalk_dws',
    title: '钉钉',
    description: '公司级钉钉协作通道，用于消息催办、待办和状态轮询。',
    accent: 'text-sky-700 bg-sky-50',
    clientIdLabel: 'Client ID',
    clientSecretLabel: 'Client Secret',
    robotCodeLabel: 'Robot Code',
    defaultName: '钉钉默认通道',
  },
  {
    provider: 'feishu',
    title: '飞书',
    description: '公司级飞书协作通道，预留消息、卡片与待办能力接入。',
    accent: 'text-emerald-700 bg-emerald-50',
    clientIdLabel: 'App ID',
    clientSecretLabel: 'App Secret',
    robotCodeLabel: 'Bot / App Code',
    defaultName: '飞书默认通道',
  },
  {
    provider: 'wechat_work',
    title: '企微',
    description: '公司级企业微信协作通道，预留消息推送与任务分发能力。',
    accent: 'text-amber-700 bg-amber-50',
    clientIdLabel: 'Corp ID / Agent ID',
    clientSecretLabel: 'Secret',
    robotCodeLabel: 'Agent / Robot Code',
    defaultName: '企微默认通道',
  },
];

export function collaborationProviderLabel(provider: CollaborationProvider): string {
  return COLLABORATION_CHANNEL_CARDS.find((item) => item.provider === provider)?.title ?? provider;
}
