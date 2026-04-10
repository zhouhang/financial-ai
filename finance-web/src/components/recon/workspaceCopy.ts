import type { ReconCenterTab } from './types';
import { RECON_COPY } from './reconCopy';

export const CENTER_TABS: Array<{ key: ReconCenterTab; label: string }> = [
  { key: 'schemes', label: RECON_COPY.tabs.schemes },
  { key: 'tasks', label: RECON_COPY.tabs.tasks },
  { key: 'runs', label: RECON_COPY.tabs.runs },
];
