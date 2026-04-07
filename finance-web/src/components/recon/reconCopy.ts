export const RECON_COPY = {
  tabs: {
    schemes: '对账方案',
    tasks: '对账任务',
    runs: '运行记录',
  },
  center: {
    sectionTitle: '对账中心',
    sectionSubtitle: '管理对账方案、对账任务与运行记录',
    actions: {
      createTask: '新建对账任务',
      rerun: '重新验证',
      followup: '异常处理',
    },
  },
} as const;

export type ReconCopy = typeof RECON_COPY;
