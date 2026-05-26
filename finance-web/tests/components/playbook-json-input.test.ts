import { describe, expect, it } from 'vitest';

import { parsePlaybookJsonInput } from '../../src/utils/playbookJsonInput';

describe('parsePlaybookJsonInput', () => {
  it('parses strict JSON without repairs', () => {
    const result = parsePlaybookJsonInput('{"schema_version":"1.0","steps":[]}');

    expect(result.value).toEqual({ schema_version: '1.0', steps: [] });
    expect(result.repairCount).toBe(0);
    expect(result.error).toBeUndefined();
  });

  it('repairs newlines and tabs inside JSON strings before parsing', () => {
    const result = parsePlaybookJsonInput(`{
      "selector": "input[name='TPL_password'],
        input[type='password']",
      "label": "历史下载记
录",
      "tabbed": "a	b"
    }`);

    expect(result.value).toEqual({
      selector: "input[name='TPL_password'], input[type='password']",
      label: '历史下载记录',
      tabbed: 'a b',
    });
    expect(result.repairCount).toBe(3);
    expect(result.error).toBeUndefined();
  });

  it('formats native parse errors with Chinese line and column hints', () => {
    const result = parsePlaybookJsonInput('{\n  "schema_version": "1.0",\n  "steps": [\n}');

    expect(result.value).toBeUndefined();
    expect(result.error).toContain('第 4 行');
  });
});
