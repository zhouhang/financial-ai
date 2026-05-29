import { describe, expect, it } from 'vitest';

import {
  buildExceptionBusinessDisplay,
  type ExceptionBusinessDisplayContext,
  type ExceptionBusinessItem,
} from '../../src/components/recon/exceptionBusinessSummary';

const context: ExceptionBusinessDisplayContext = {
  datasetLabels: {
    left: 'tb0131100248-店铺订单',
    right: '交易订单明细表',
  },
  fieldLabelForSide: (_side, field) => {
    const labels: Record<string, string> = {
      biz_key: '订单编号',
      merchant_order_no: '商户订单号',
      amount: '含税销售金额',
      paid_amount: '买家实付金额',
      order_status: '订单状态',
      pay_status: '支付状态',
    };
    return labels[field] || field;
  },
};

function buildItem(patch: Partial<ExceptionBusinessItem>): ExceptionBusinessItem {
  return {
    anomalyType: 'source_only',
    summary: '仅 tb0131100248-店铺订单 存在（交易订单明细表 缺失）：订单编号=5118002676174023242',
    raw: {},
    ...patch,
  };
}

describe('exception business summary display', () => {
  it('builds source_only summaries from the non-empty left join value', () => {
    const item = buildItem({
      anomalyType: 'source_only',
      raw: {
        detail_json: {
          source_ref: 'left_recon_ready',
          target_ref: 'right_recon_ready',
          join_key: [
            {
              source_field: 'biz_key',
              target_field: 'biz_key',
              source_value: '5118002676174023242',
              target_value: null,
            },
          ],
          compare_values: [
            {
              source_field: 'amount',
              target_field: 'paid_amount',
              source_value: '0.00',
              target_value: null,
            },
          ],
          left_record: {
            biz_key: '5118002676174023242',
            amount: '0.00',
          },
        },
      },
    });

    const display = buildExceptionBusinessDisplay(item, context);

    expect(display.shortSummary).toBe('交易订单明细表缺失订单编号 5118002676174023242');
    expect(display.conclusion).toBe('交易订单明细表缺失订单编号 5118002676174023242');
    expect(display.keyLines).toEqual([
      {
        side: 'left',
        datasetLabel: 'tb0131100248-店铺订单',
        fieldLabel: '订单编号',
        value: '5118002676174023242',
      },
      {
        side: 'right',
        datasetLabel: '交易订单明细表',
        fieldLabel: '订单编号',
        value: '--',
      },
    ]);
    expect(display.compareLines).toEqual([
      {
        fieldLabel: '含税销售金额 / 买家实付金额',
        sourceDatasetLabel: 'tb0131100248-店铺订单',
        targetDatasetLabel: '交易订单明细表',
        sourceValue: '0.00',
        targetValue: '--',
        diffValue: '--',
      },
    ]);
    expect(display.recordSections).toHaveLength(2);
    expect(display.recordSections[0]).toMatchObject({
      side: 'left',
      title: 'tb0131100248-店铺订单',
    });
    expect(display.recordSections[0].emptyMessage).toBeUndefined();
    expect(display.recordSections[0].entries.map((entry) => entry.label)).toEqual(['订单编号', '含税销售金额']);
    expect(display.recordSections[1]).toMatchObject({
      side: 'right',
      title: '交易订单明细表',
      entries: [],
      emptyMessage: '未匹配到原始记录',
    });
  });

  it('builds target_only summaries from the non-empty right join value', () => {
    const item = buildItem({
      anomalyType: 'target_only',
      raw: {
        detail_json: {
          source_ref: 'left_recon_ready',
          target_ref: 'right_recon_ready',
          join_key: [
            {
              source_field: 'merchant_order_no',
              target_field: 'merchant_order_no',
              source_value: null,
              target_value: '202605280001',
            },
          ],
          right_record: {
            merchant_order_no: '202605280001',
            paid_amount: '88.00',
          },
        },
      },
    });

    const display = buildExceptionBusinessDisplay(item, context);

    expect(display.shortSummary).toBe('tb0131100248-店铺订单缺失商户订单号 202605280001');
    expect(display.conclusion).toBe('tb0131100248-店铺订单缺失商户订单号 202605280001');
  });

  it('builds matched_with_diff summaries from the match field and difference type', () => {
    const item = buildItem({
      anomalyType: 'matched_with_diff',
      raw: {
        detail_json: {
          join_key: [
            {
              field: 'biz_key',
              value: '5118002676174023242',
            },
          ],
          compare_values: [
            {
              source_field: 'amount',
              target_field: 'paid_amount',
              source_value: '10.00',
              target_value: '9.00',
              diff_value: '1.00',
            },
          ],
        },
      },
    });

    const display = buildExceptionBusinessDisplay(item, context);

    expect(display.shortSummary).toBe('订单编号 5118002676174023242 金额不一致');
    expect(display.conclusion).toBe('订单编号 5118002676174023242 金额不一致');
  });

  it('falls back to formatted original summary chunks when join_key is missing', () => {
    const item = buildItem({
      anomalyType: 'matched_with_diff',
      summary: '差异类型：金额差异 匹配字段：订单号=TB001 对比字段：实收金额 100 / 98',
      raw: { detail_json: {} },
    });

    const display = buildExceptionBusinessDisplay(item, context);

    expect(display.shortSummary).toBe('差异类型：金额差异\n匹配字段：订单号=TB001\n对比字段：实收金额 100 / 98');
    expect(display.conclusion).toBe('差异类型：金额差异\n匹配字段：订单号=TB001\n对比字段：实收金额 100 / 98');
  });

  it('uses detail fallback when detail_json is present but empty', () => {
    const item = buildItem({
      anomalyType: 'matched_with_diff',
      raw: {
        detail_json: {},
        detail: {
          join_key: [
            {
              field: 'biz_key',
              value: '5118002676174023242',
            },
          ],
          compare_values: [
            {
              source_field: 'order_status',
              target_field: 'pay_status',
              source_value: '已发货',
              target_value: '未支付',
            },
          ],
        },
      },
    });

    const display = buildExceptionBusinessDisplay(item, context);

    expect(display.shortSummary).toBe('订单编号 5118002676174023242 状态不一致');
  });

  it('splits prefixed raw_record entries into left and right record sections', () => {
    const item = buildItem({
      anomalyType: 'matched_with_diff',
      raw: {
        detail_json: {
          join_key: [
            {
              source_field: 'biz_key',
              target_field: 'biz_key',
            },
          ],
          compare_values: [
            {
              source_field: 'amount',
              target_field: 'paid_amount',
            },
          ],
          raw_record: {
            'source.biz_key': '5118002676174023242',
            'source.amount': '10.00',
            'target.biz_key': '5118002676174023242',
            'target.paid_amount': '9.00',
          },
        },
      },
    });

    const display = buildExceptionBusinessDisplay(item, context);

    expect(display.shortSummary).toBe('订单编号 5118002676174023242 金额不一致');
    expect(display.keyLines.map((line) => line.value)).toEqual([
      '5118002676174023242',
      '5118002676174023242',
    ]);
    expect(display.compareLines.map((line) => [line.sourceValue, line.targetValue])).toEqual([
      ['10.00', '9.00'],
    ]);
    expect(display.recordSections).toEqual([
      {
        side: 'left',
        title: 'tb0131100248-店铺订单',
        entries: [
          { field: 'biz_key', label: '订单编号', value: '5118002676174023242' },
          { field: 'amount', label: '含税销售金额', value: '10.00' },
        ],
      },
      {
        side: 'right',
        title: '交易订单明细表',
        entries: [
          { field: 'biz_key', label: '订单编号', value: '5118002676174023242' },
          { field: 'paid_amount', label: '买家实付金额', value: '9.00' },
        ],
      },
    ]);
  });

  it('recovers key and compare values from record payloads when detail values are omitted', () => {
    const item = buildItem({
      anomalyType: 'matched_with_diff',
      raw: {
        detail_json: {
          join_key: [
            {
              source_field: 'biz_key',
              target_field: 'biz_key',
            },
          ],
          compare_values: [
            {
              source_field: 'amount',
              target_field: 'paid_amount',
            },
          ],
          left_record: {
            biz_key: '5118002676174023242',
            amount: '10.00',
          },
          right_record: {
            biz_key: '5118002676174023242',
            paid_amount: '9.00',
          },
        },
      },
    });

    const display = buildExceptionBusinessDisplay(item, context);

    expect(display.shortSummary).toBe('订单编号 5118002676174023242 金额不一致');
    expect(display.keyLines.map((line) => line.value)).toEqual([
      '5118002676174023242',
      '5118002676174023242',
    ]);
    expect(display.compareLines).toEqual([
      {
        fieldLabel: '含税销售金额 / 买家实付金额',
        sourceDatasetLabel: 'tb0131100248-店铺订单',
        targetDatasetLabel: '交易订单明细表',
        sourceValue: '10.00',
        targetValue: '9.00',
        diffValue: '--',
      },
    ]);
  });

  it('shows unprefixed raw_record fields on the side that has a recovered match value', () => {
    const item = buildItem({
      anomalyType: 'source_only',
      raw: {
        detail_json: {
          source_ref: 'left_recon_ready',
          target_ref: 'right_recon_ready',
          join_key: [
            {
              source_field: 'biz_key',
              target_field: 'biz_key',
            },
          ],
          raw_record: {
            biz_key: '5118002676174023242',
            amount: '10.00',
          },
        },
      },
    });

    const display = buildExceptionBusinessDisplay(item, context);

    expect(display.shortSummary).toBe('交易订单明细表缺失订单编号 5118002676174023242');
    expect(display.recordSections).toEqual([
      {
        side: 'left',
        title: 'tb0131100248-店铺订单',
        entries: [
          { field: 'biz_key', label: '订单编号', value: '5118002676174023242' },
          { field: 'amount', label: '含税销售金额', value: '10.00' },
        ],
      },
      {
        side: 'right',
        title: '交易订单明细表',
        entries: [],
        emptyMessage: '未匹配到原始记录',
      },
    ]);
  });
});
