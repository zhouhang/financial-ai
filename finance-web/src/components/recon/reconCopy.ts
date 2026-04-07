export const RECON_COPY = {
  tabs: {
    instant: '立即对账',
    auto: '自动对账',
    rules: '规则配置',
  },
  auto: {
    sectionTitle: '自动对账',
    sectionSubtitle: '任务配置、运行记录、异常跟进与重新验证',
    subTabs: {
      configs: '任务配置',
      runs: '任务运行',
    },
    metrics: {
      enabledTasks: '启用中的自动对账任务',
      pendingRuns: '待跟进对账批次',
      totalExceptions: '累计异常条数',
    },
    actions: {
      createTask: '新建自动对账任务',
      refreshRuns: '刷新自动对账运行',
      rerun: '重新验证',
      followup: '异常跟进',
    },
  },
} as const;

export type ReconCopy = typeof RECON_COPY;
