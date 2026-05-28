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
});
