import type { ReconAutoSubTab, ReconWorkspaceTab } from './types';
import { RECON_COPY } from './reconCopy';

export const WORKSPACE_TABS: Array<{ key: ReconWorkspaceTab; label: string }> = [
  { key: 'instant', label: RECON_COPY.tabs.instant },
  { key: 'auto', label: RECON_COPY.tabs.auto },
  { key: 'rules', label: RECON_COPY.tabs.rules },
];

export const AUTO_SUB_TABS: Array<{ key: ReconAutoSubTab; label: string }> = [
  { key: 'configs', label: RECON_COPY.auto.subTabs.configs },
  { key: 'runs', label: RECON_COPY.auto.subTabs.runs },
];
