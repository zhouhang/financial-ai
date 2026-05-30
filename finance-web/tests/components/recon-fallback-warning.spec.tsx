import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import SchemeWizardReconStep from '../../src/components/recon/SchemeWizardReconStep';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('对账方案 warning 展示', () => {
  it('第3步数据对账在 warning 时展示提示文案', () => {
    render(
      <SchemeWizardReconStep
        reconRuleName="资金对账逻辑"
        matchFieldPairs={[{ id: 'match-1', leftField: '业务单号', rightField: '业务单号' }]}
        compareFieldPairs={[{ id: 'compare-1', leftField: '金额', rightField: '金额' }]}
        leftMatchFieldOptions={[{ value: '业务单号', label: '业务单号' }]}
        rightMatchFieldOptions={[{ value: '业务单号', label: '业务单号' }]}
        leftCompareFieldOptions={[{ value: '金额', label: '金额' }]}
        rightCompareFieldOptions={[{ value: '金额', label: '金额' }]}
        reconCompatibility={{
          status: 'warning',
          message: '对账规则生成失败，已回退为兜底规则，请重点检查字段配置。',
          details: ['mock recon fallback'],
        }}
        onStructuredConfigChange={vi.fn()}
        onViewReconJson={vi.fn()}
      />,
    );

    expect(screen.getAllByText('对账规则生成失败，已回退为兜底规则，请重点检查字段配置。').length).toBeGreaterThan(0);
    expect(screen.getByText('mock recon fallback')).toBeInTheDocument();
  });

  it('第3步对账字段优先展示中文名称，底层字段仍保留英文 value', () => {
    render(
      <SchemeWizardReconStep
        reconRuleName="订单对账逻辑"
        matchFieldPairs={[{ id: 'match-1', leftField: 'biz_key', rightField: 'biz_key' }]}
        compareFieldPairs={[{ id: 'compare-1', leftField: 'amount', rightField: 'amount' }]}
        leftFieldLabelMap={{ biz_key: '客户订单号', amount: '含税销售金额', biz_date: '订单完成时间' }}
        rightFieldLabelMap={{ biz_key: '商户订单号', amount: '订单金额', biz_date: '入账时间' }}
        leftMatchFieldOptions={[{ value: 'biz_key', label: '客户订单号' }]}
        rightMatchFieldOptions={[{ value: 'biz_key', label: '商户订单号' }]}
        leftCompareFieldOptions={[{ value: 'amount', label: '含税销售金额' }]}
        rightCompareFieldOptions={[{ value: 'amount', label: '订单金额' }]}
        onStructuredConfigChange={vi.fn()}
        onViewReconJson={vi.fn()}
      />,
    );

    expect(screen.getByText('字段对 1：客户订单号 ↔ 商户订单号')).toBeInTheDocument();
    expect(screen.getByText('字段对 1：含税销售金额 ↔ 订单金额')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '客户订单号' })).toHaveValue('biz_key');
  });

  it('第3步支持用户调整匹配字段和对比字段字段对', () => {
    const onStructuredConfigChange = vi.fn();
    render(
      <SchemeWizardReconStep
        reconRuleName="订单对账逻辑"
        matchFieldPairs={[{ id: 'match-1', leftField: 'biz_key', rightField: 'biz_key' }]}
        compareFieldPairs={[{ id: 'compare-1', leftField: 'amount', rightField: 'amount' }]}
        leftMatchFieldOptions={[
          { value: 'biz_key', label: '客户订单号' },
          { value: 'member_code', label: '客户会员编码' },
        ]}
        rightMatchFieldOptions={[
          { value: 'biz_key', label: '商户订单号' },
          { value: 'buyer_code', label: '买家编码' },
        ]}
        leftCompareFieldOptions={[{ value: 'amount', label: '含税销售金额' }]}
        rightCompareFieldOptions={[{ value: 'amount', label: '订单金额' }]}
        leftFieldLabelMap={{ biz_key: '客户订单号', member_code: '客户会员编码', amount: '含税销售金额' }}
        rightFieldLabelMap={{ biz_key: '商户订单号', buyer_code: '买家编码', amount: '订单金额' }}
        onStructuredConfigChange={onStructuredConfigChange}
        onViewReconJson={vi.fn()}
      />,
    );

    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[0], { target: { value: 'member_code' } });
    fireEvent.change(selects[1], { target: { value: 'buyer_code' } });

    expect(onStructuredConfigChange).toHaveBeenNthCalledWith(1, {
      matchFieldPairs: [{ id: 'match-1', leftField: 'member_code', rightField: 'biz_key' }],
    });
    expect(onStructuredConfigChange).toHaveBeenNthCalledWith(2, {
      matchFieldPairs: [{ id: 'match-1', leftField: 'biz_key', rightField: 'buyer_code' }],
    });
  });

  it('第3步不再展示手动试跑入口和样例结果区', () => {
    render(
      <SchemeWizardReconStep
        reconRuleName="订单对账逻辑"
        matchFieldPairs={[{ id: 'match-1', leftField: 'biz_key', rightField: 'biz_key' }]}
        compareFieldPairs={[{ id: 'compare-1', leftField: 'amount', rightField: 'amount' }]}
        leftMatchFieldOptions={[{ value: 'biz_key', label: '客户订单号' }]}
        rightMatchFieldOptions={[{ value: 'biz_key', label: '商户订单号' }]}
        leftCompareFieldOptions={[{ value: 'amount', label: '含税销售金额' }]}
        rightCompareFieldOptions={[{ value: 'amount', label: '订单金额' }]}
        leftFieldLabelMap={{ biz_key: '客户订单号', amount: '含税销售金额' }}
        rightFieldLabelMap={{ biz_key: '商户订单号', amount: '订单金额' }}
        reconJsonPreview='{"name":"订单对账逻辑"}'
        onStructuredConfigChange={vi.fn()}
        onViewReconJson={vi.fn()}
      />,
    );

    expect(screen.queryByText('试跑验证')).not.toBeInTheDocument();
    expect(screen.queryByText('正在试跑对账规则，请稍候…')).not.toBeInTheDocument();
    expect(screen.queryByText('对账结果摘要')).not.toBeInTheDocument();
    expect(screen.queryByText('对账差异')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '查看 JSON' })).toBeEnabled();
  });
});
