import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import SchemeWizardReconStep from '../../src/components/recon/SchemeWizardReconStep';
import SchemeWizardTargetProcStep from '../../src/components/recon/SchemeWizardTargetProcStep';

describe('对账方案 fallback warning 展示', () => {
  it('第2步数据整理在 fallback 时展示 warning 文案', () => {
    render(
      <SchemeWizardTargetProcStep
        step={2}
        schemeDraft={{
          name: '资金对账方案',
          businessGoal: '核对订单与流水金额差异',
          leftDescription: '左侧订单数据',
          rightDescription: '右侧流水数据',
          procConfigMode: 'ai',
          selectedProcConfigId: '',
          procDraft: '步骤1：定义左侧整理结果表。\n步骤2：定义右侧整理结果表。',
          procTrialStatus: 'idle',
          procTrialSummary: '',
        }}
        availableSources={[]}
        loadingSources={false}
        selectedLeftSources={[]}
        selectedRightSources={[]}
        existingProcOptions={[]}
        procCompatibility={{
          status: 'warning',
          message: 'AI 生成失败，已回退为兜底规则，请重点检查后再试跑。',
          details: ['mock proc fallback'],
        }}
        onNameChange={vi.fn()}
        onBusinessGoalChange={vi.fn()}
        onDescriptionChange={vi.fn()}
        onChangeSourceSelection={vi.fn()}
        onProcConfigModeChange={vi.fn()}
        onSelectExistingProcConfig={vi.fn()}
        onGenerateProc={vi.fn()}
        onTrialProc={vi.fn()}
        onProcDraftChange={vi.fn()}
        onViewProcJson={vi.fn()}
      />,
    );

    expect(screen.getAllByText('AI 生成失败，已回退为兜底规则，请重点检查后再试跑。').length).toBeGreaterThan(0);
    expect(screen.getByText('mock proc fallback')).toBeInTheDocument();
  });

  it('第3步数据对账在 fallback 时展示 warning 文案', () => {
    render(
      <SchemeWizardReconStep
        schemeDraft={{
          reconDraft: '1. 按业务主键匹配。\n2. 按金额字段比对。',
          reconTrialStatus: 'idle',
          reconTrialSummary: '',
        }}
        reconConfigMode="ai"
        reconCompatibility={{
          status: 'warning',
          message: 'AI 生成失败，已回退为兜底规则，请重点检查后再试跑。',
          details: ['mock recon fallback'],
        }}
        onReconConfigModeChange={vi.fn()}
        onSelectExistingReconConfig={vi.fn()}
        onGenerateRecon={vi.fn()}
        onTrialRecon={vi.fn()}
        onReconDraftChange={vi.fn()}
        onViewReconJson={vi.fn()}
      />,
    );

    expect(screen.getAllByText('AI 生成失败，已回退为兜底规则，请重点检查后再试跑。').length).toBeGreaterThan(0);
    expect(screen.getByText('mock recon fallback')).toBeInTheDocument();
  });
});
