export const EXCEPTION_SUMMARY_SECTION_LABELS = ['差异类型', '匹配字段', '对比字段'] as const;

function sectionLabelPattern(): RegExp {
  return new RegExp(`(^|[\\s\\n；;，,])((?:${EXCEPTION_SUMMARY_SECTION_LABELS.join('|')})[:：])`, 'g');
}

export function formatExceptionSummaryLines(text: string, fallback = '异常详情待补充。'): string {
  const source = (text || fallback).trim() || fallback;
  return source
    .replace(/\r\n?/g, '\n')
    .replace(/[；;]\s*/g, '\n')
    .replace(sectionLabelPattern(), (_match, prefix: string, label: string) => {
      const isLineStart = prefix === '' || prefix === '\n';
      return `${isLineStart ? '' : '\n'}${label}`;
    })
    .replace(/\s{2,}/g, '\n')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .join('\n');
}
