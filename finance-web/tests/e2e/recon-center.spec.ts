import { expect, test, type Page } from '@playwright/test';

interface AuthSession {
  token: string;
  userId: string;
  username: string;
}

interface ApiResult<T = Record<string, unknown>> {
  ok: boolean;
  status: number;
  data: T;
}

interface SourceDatasetCandidate {
  sourceId: string;
  sourceName: string;
  datasetId: string;
  datasetName: string;
  datasetCode: string;
  resourceKey: string;
  schemaSummary: Record<string, unknown>;
  columns: string[];
  score: number;
}

const DEFAULT_COMPANY_ID = '00000000-0000-0000-0000-000000000001';
const DEFAULT_DEPARTMENT_ID = '00000000-0000-0000-0000-000000000002';

async function registerAuthSession(page: Page): Promise<AuthSession> {
  await page.goto('/');

  const username = `pw_e2e_${Date.now()}`;
  const password = 'Pw123456!';
  const registerResult = await page.evaluate(async ({ name, pwd, companyId, departmentId }) => {
    const form = new URLSearchParams();
    form.set('username', name);
    form.set('password', pwd);
    form.set('company_id', companyId);
    form.set('department_id', departmentId);

    const response = await fetch('/api/auth/register', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
      },
      body: form.toString(),
    });
    const data = await response.json().catch(() => ({}));
    return {
      ok: response.ok,
      status: response.status,
      data,
    };
  }, {
    name: username,
    pwd: password,
    companyId: DEFAULT_COMPANY_ID,
    departmentId: DEFAULT_DEPARTMENT_ID,
  });
  expect(registerResult.ok).toBeTruthy();
  const registerData = registerResult.data as Record<string, unknown>;
  expect(registerData.success).toBeTruthy();
  expect(registerData.token).toBeTruthy();

  return {
    token: String(registerData.token),
    userId: String(registerData.user?.id || registerData.user_id || ''),
    username: String(registerData.user?.username || username),
  };
}

async function seedAuthSession(page: Page, authSession: AuthSession) {
  await page.goto('/');
  await page.evaluate(({ authToken, userId, username }) => {
    window.localStorage.setItem('tally_auth_token', authToken);
    window.localStorage.setItem(
      'tally_current_user',
      JSON.stringify({
          id: userId,
        userId,
        username,
      }),
    );
  }, {
    authToken: authSession.token,
    userId: authSession.userId,
    username: authSession.username,
  });
  await page.reload();
  await expect(page.getByRole('button', { name: '登录' })).toHaveCount(0);
}

async function openReconCenter(page: Page) {
  const reconCenterEntry = page.getByRole('button', { name: '对账中心' });
  if (!(await reconCenterEntry.isVisible())) {
    const reconGroupEntry = page.getByRole('button', { name: '数据对账' });
    await expect(reconGroupEntry).toBeVisible();
    await reconGroupEntry.click();
  }
  await expect(reconCenterEntry).toBeVisible();
  await reconCenterEntry.click();
  await expect(page.getByText('统一查看对账方案、对账任务与运行记录')).toBeVisible();
}

async function fetchAuthedJson<T = Record<string, unknown>>(
  page: Page,
  authToken: string,
  path: string,
  init?: { method?: string; headers?: Record<string, string>; body?: string },
): Promise<ApiResult<T>> {
  return page.evaluate(
    async ({ auth, reqPath, requestInit }) => {
      const headers = new Headers(requestInit?.headers || {});
      headers.set('Authorization', `Bearer ${auth}`);
      const response = await fetch(reqPath, {
        method: requestInit?.method || 'GET',
        headers,
        body: requestInit?.body,
      });
      const data = await response.json().catch(() => ({}));
      return {
        ok: response.ok,
        status: response.status,
        data,
      };
    },
    { auth: authToken, reqPath: path, requestInit: init || null },
  );
}

function extractColumnsFromSchemaSummary(schemaSummary: Record<string, unknown>): string[] {
  const columns = schemaSummary?.columns;
  if (Array.isArray(columns)) {
    return columns
      .map((item) => {
        if (!item || typeof item !== 'object') return '';
        const row = item as Record<string, unknown>;
        return String(row.name || row.column_name || '').trim();
      })
      .filter(Boolean);
  }
  return Object.keys(schemaSummary || {}).filter((key) => key !== 'columns');
}

function scoreDatasetColumns(columns: string[]): number {
  const normalized = columns.map((item) => item.toLowerCase());
  const amountScore = normalized.some((item) =>
    /(amount|amt|price|money|payment|paid|settle|fee|total|balance|金额|实收|实付|应收|应付)/.test(item),
  )
    ? 4
    : 0;
  const dateScore = normalized.some((item) =>
    /(date|time|day|dt|created|updated|biz_date|trade_date|交易时间|业务日期|日期|账期)/.test(item),
  )
    ? 3
    : 0;
  const keyScore = normalized.some((item) =>
    /(order|id|no|code|sn|流水|单号|订单号|编码)/.test(item),
  )
    ? 2
    : 0;
  return amountScore + dateScore + keyScore + Math.min(normalized.length, 6) * 0.01;
}

async function discoverDatasetCandidates(page: Page, authToken: string): Promise<SourceDatasetCandidate[]> {
  const sourcesResult = await fetchAuthedJson<Record<string, unknown>>(page, authToken, '/api/data-sources');
  expect(sourcesResult.ok).toBeTruthy();
  const sourcesRaw = Array.isArray((sourcesResult.data as Record<string, unknown>).sources)
    ? ((sourcesResult.data as Record<string, unknown>).sources as Array<Record<string, unknown>>)
    : [];

  const candidates: SourceDatasetCandidate[] = [];

  for (const source of sourcesRaw) {
    const sourceId = String(source.id || '');
    const sourceName = String(source.name || source.source_name || sourceId);
    if (!sourceId) continue;
    const datasetResult = await fetchAuthedJson<Record<string, unknown>>(
      page,
      authToken,
      `/api/data-sources/${sourceId}/datasets`,
    );
    if (!datasetResult.ok) continue;
    const datasetRows = Array.isArray((datasetResult.data as Record<string, unknown>).datasets)
      ? ((datasetResult.data as Record<string, unknown>).datasets as Array<Record<string, unknown>>)
      : [];
    for (const dataset of datasetRows) {
      const schemaSummary = (dataset.schema_summary ||
        dataset.schemaSummary ||
        {}) as Record<string, unknown>;
      const columns = extractColumnsFromSchemaSummary(schemaSummary);
      candidates.push({
        sourceId,
        sourceName,
        datasetId: String(dataset.id || dataset.dataset_id || ''),
        datasetName: String(dataset.name || dataset.dataset_name || dataset.dataset_code || dataset.resource_key || ''),
        datasetCode: String(dataset.dataset_code || ''),
        resourceKey: String(dataset.resource_key || ''),
        schemaSummary,
        columns,
        score: scoreDatasetColumns(columns),
      });
    }
  }

  return candidates.sort((left, right) => right.score - left.score);
}

async function selectDatasetInDropdown(
  page: Page,
  sectionTitle: '左侧原始数据' | '右侧原始数据',
  datasetName?: string,
) {
  const title = page.locator('p').filter({ hasText: new RegExp(`^${sectionTitle}$`) }).first();
  const card = title.locator('xpath=ancestor::div[contains(@class,"rounded-3xl")][1]');
  const dropdownButton = card.getByRole('button').first();
  await dropdownButton.click();
  const dropdownPanel = card
    .locator('div.absolute')
    .filter({ has: page.getByRole('button', { name: '确定' }) })
    .last();
  await expect(dropdownPanel).toBeVisible();

  let checkbox = dropdownPanel.locator('input[type="checkbox"]').first();
  if (datasetName?.trim()) {
    const matchedCheckbox = dropdownPanel
      .locator('div')
      .filter({ hasText: datasetName.trim() })
      .locator('input[type="checkbox"]')
      .first();
    if (await matchedCheckbox.count()) {
      checkbox = matchedCheckbox;
    }
  }

  await expect(checkbox).toBeVisible({ timeout: 15_000 });
  await checkbox.check();
  await dropdownPanel.getByRole('button', { name: '确定' }).click();
  await expect(dropdownPanel).toHaveCount(0);
}

async function closeJsonPreview(page: Page) {
  const closeButton = page.getByRole('button', { name: '取消' }).last();
  await expect(closeButton).toBeVisible();
  await closeButton.click();
}

async function waitForOptionalStatus(page: Page, text: string, timeoutMs = 180_000) {
  const status = page.getByText(text);
  await status.waitFor({ state: 'visible', timeout: 5_000 }).catch(() => null);
  await status.waitFor({ state: 'hidden', timeout: timeoutMs }).catch(() => null);
}

async function ensureTimeSemanticSelected(page: Page, label: string) {
  const select = page.getByLabel(label);
  await expect(select).toBeVisible();
  const current = await select.inputValue();
  if (current) return;
  const options = await select.locator('option').evaluateAll((rows) =>
    rows.map((row) => ({ value: (row as HTMLOptionElement).value, label: row.textContent || '' })),
  );
  const candidate = options.find((item) => item.value);
  expect(candidate, `${label} 没有可选项`).toBeTruthy();
  await select.selectOption(candidate!.value);
}

function extractOutputFieldNames(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (!item || typeof item !== 'object') return '';
      const row = item as Record<string, unknown>;
      return String(row.output_name || row.outputName || '').trim();
    })
    .filter(Boolean);
}

function extractSchemeMetaRow(value: Record<string, unknown> | undefined): Record<string, unknown> {
  if (!value) return {};
  const meta = value.scheme_meta_json || value.scheme_meta || value.schemeMeta || value.meta;
  return meta && typeof meta === 'object' ? (meta as Record<string, unknown>) : {};
}

function getSchemeRow(page: Page, schemeName: string) {
  return page
    .locator('div')
    .filter({ has: page.getByRole('button', { name: '查看详情' }) })
    .filter({ hasText: schemeName })
    .first();
}

async function waitForRunRecord(
  page: Page,
  authToken: string,
  planCode: string,
  timeoutMs = 90_000,
): Promise<Record<string, unknown>> {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const result = await fetchAuthedJson<Record<string, unknown>>(
      page,
      authToken,
      `/api/recon/runs?plan_code=${encodeURIComponent(planCode)}`,
    );
    if (result.ok) {
      const rows = Array.isArray((result.data as Record<string, unknown>).runs)
        ? ((result.data as Record<string, unknown>).runs as Array<Record<string, unknown>>)
        : [];
      if (rows.length > 0) {
        return rows[0];
      }
    }
    await page.waitForTimeout(2_000);
  }
  throw new Error(`等待运行记录超时: ${planCode}`);
}


async function createReconScheme(
  page: Page,
  authSession: AuthSession,
  suffix = '',
): Promise<{ schemeName: string; schemeCode: string }> {
  const schemeName = `Playwright 方案 ${Date.now()}${suffix ? ` ${suffix}` : ''}`;

  const datasetCandidates = await discoverDatasetCandidates(page, authSession.token);
  expect(datasetCandidates.length).toBeGreaterThan(0);
  const selectedDataset = datasetCandidates[0];

  await openReconCenter(page);
  await page.getByRole('button', { name: '新增对账方案' }).click();
  await expect(page.getByText('按四步完成方案设计与试跑确认')).toBeVisible();
  await page.getByLabel('方案名称').fill(schemeName);
  await page.getByLabel('对账目的').fill('核对左右数据金额以及业务主键一致性。');
  await expect(page.getByRole('button', { name: '下一步' })).toBeEnabled();
  await page.getByRole('button', { name: '下一步' }).click();
  await expect(
    page.getByText('第二步只负责数据整理。先选中左右侧原始数据，再生成和试跑当前的数据整理配置。'),
  ).toBeVisible();
  await selectDatasetInDropdown(page, '左侧原始数据', selectedDataset.datasetName);
  await selectDatasetInDropdown(page, '右侧原始数据', selectedDataset.datasetName);

  await page.getByRole('button', { name: 'AI生成整理配置' }).click();
  await waitForOptionalStatus(page, 'AI 正在生成整理配置，请稍候…');
  await expect(page.getByLabel('数据整理配置')).toHaveValue(/\S/, { timeout: 180_000 });
  await page.getByRole('button', { name: 'JSON' }).click();
  await expect(page.getByText('数据整理配置 JSON')).toBeVisible();
  await expect(page.locator('pre')).toContainText('"steps"');
  await expect(page.locator('pre')).toContainText('"action"');
  await closeJsonPreview(page);

  await page.getByRole('button', { name: '试跑验证' }).click();
  await waitForOptionalStatus(page, 'AI 正在试跑数据整理，请稍候…', 120_000);
  await expect(page.getByText('左侧原始数据抽样')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText('整理后左侧输出')).toBeVisible({ timeout: 30_000 });
  await page.getByRole('button', { name: '下一步' }).click();

  await page.getByRole('button', { name: 'AI生成对账逻辑' }).click();
  await waitForOptionalStatus(page, 'AI 正在生成对账逻辑，请稍候…', 120_000);
  await expect(page.getByLabel('数据对账逻辑')).toHaveValue(/\S/, { timeout: 120_000 });
  await page.getByRole('button', { name: 'JSON' }).click();
  await expect(page.getByText('对账逻辑 JSON')).toBeVisible();
  await expect(page.locator('pre')).toContainText('"rules"');
  await expect(page.locator('pre')).toContainText('"source_file"');
  await closeJsonPreview(page);

  await page.getByRole('button', { name: '试跑验证' }).click();
  await waitForOptionalStatus(page, 'AI 正在试跑数据对账，请稍候…', 120_000);
  await expect(page.getByText('对账结果摘要')).toBeVisible({ timeout: 30_000 });
  await page.getByRole('button', { name: '下一步' }).click();

  await expect(page.getByText('确认保存前，再看一遍当前方案')).toBeVisible();
  await expect(page.getByText('当前整理配置和对账规则都已试跑通过，可以保存方案。')).toBeVisible();
  await page.getByRole('button', { name: '保存方案' }).click();
  await expect(page.getByText('按四步完成方案设计与试跑确认')).toHaveCount(0, { timeout: 30_000 });

  const schemesResult = await fetchAuthedJson<Record<string, unknown>>(page, authSession.token, '/api/recon/schemes');
  expect(schemesResult.ok).toBeTruthy();
  const schemes = Array.isArray((schemesResult.data as Record<string, unknown>).schemes)
    ? ((schemesResult.data as Record<string, unknown>).schemes as Array<Record<string, unknown>>)
    : [];
  const savedScheme = schemes.find((scheme) => String(scheme.scheme_name || scheme.name || '') === schemeName);
  expect(savedScheme).toBeTruthy();
  const schemeCode = String(savedScheme?.scheme_code || savedScheme?.schemeCode || '');
  expect(schemeCode).toBeTruthy();

  return { schemeName, schemeCode };
}

async function createRunPlanForScheme(
  page: Page,
  authSession: AuthSession,
  schemeName: string,
  schemeCode: string,
): Promise<{ planCode: string; planName: string; ownerSummary: string; channelConfigId: string }> {
  const ownerSummary = `Playwright 责任人 ${Date.now()}`;
  await openReconCenter(page);
  await page.getByRole('button', { name: '对账方案', exact: true }).click();
  const schemeRow = getSchemeRow(page, schemeName);
  await expect(schemeRow).toBeVisible();
  await schemeRow.getByRole('button', { name: '查看详情' }).click();
  await expect(page.getByText('方案详情')).toBeVisible();
  await page.getByRole('button', { name: '新增运行计划' }).click();
  await expect(page.getByText('为方案补充调度、时间口径、协作通道与责任人')).toBeVisible();
  await expect(page.getByLabel('对账方案')).toHaveValue(schemeCode);
  await ensureTimeSemanticSelected(page, '左侧时间口径');
  await ensureTimeSemanticSelected(page, '右侧时间口径');
  await page.getByLabel('责任人').fill(ownerSummary);
  await page.getByRole('button', { name: '保存任务' }).click();
  await expect(page.getByText('为方案补充调度、时间口径、协作通道与责任人')).toHaveCount(0, { timeout: 30_000 });

  const tasksResult = await fetchAuthedJson<Record<string, unknown>>(page, authSession.token, '/api/recon/tasks');
  expect(tasksResult.ok).toBeTruthy();
  const tasks = Array.isArray((tasksResult.data as Record<string, unknown>).tasks)
    ? ((tasksResult.data as Record<string, unknown>).tasks as Array<Record<string, unknown>>)
    : [];
  const savedTask = tasks.find((task) => String(task.scheme_code || task.schemeCode || '') === schemeCode);
  expect(savedTask).toBeTruthy();
  const planCode = String(savedTask?.plan_code || savedTask?.planCode || '');
  const planName = String(savedTask?.plan_name || savedTask?.planName || '');
  const channelConfigId = String(savedTask?.channel_config_id || savedTask?.channelConfigId || '');
  expect(planCode).toBeTruthy();
  return { planCode, planName, ownerSummary, channelConfigId };
}

test.describe.serial('对账任务关键路径', () => {
  test.describe.configure({ timeout: 240_000 });
  let authSession: AuthSession;
  let sharedScheme: { schemeName: string; schemeCode: string };

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(240_000);
    const context = await browser.newContext();
    const page = await context.newPage();
    authSession = await registerAuthSession(page);
    await seedAuthSession(page, authSession);
    sharedScheme = await createReconScheme(page, authSession, '共享');
    await context.close();
  });

  test.beforeEach(async ({ page }) => {
    await seedAuthSession(page, authSession);
  });

  test('新增运行计划后任务列表展示关键信息', async ({ page }) => {
    const { planName, ownerSummary } = await createRunPlanForScheme(
      page,
      authSession,
      sharedScheme.schemeName,
      sharedScheme.schemeCode,
    );
    await openReconCenter(page);
    await page.getByRole('button', { name: '对账任务' }).click();

    const taskRow = page.locator('div').filter({ hasText: planName }).first();
    await expect(taskRow).toBeVisible();
    await expect(taskRow).toContainText(sharedScheme.schemeName);
    await expect(taskRow).toContainText(ownerSummary);
    await expect(taskRow).toContainText('·');
  });

  test('运行记录中展示异常看板入口', async ({ page }) => {
    test.setTimeout(420_000);
    const { planCode } = await createRunPlanForScheme(
      page,
      authSession,
      sharedScheme.schemeName,
      sharedScheme.schemeCode,
    );
    const triggerResult = await page.evaluate(
      async ({ authToken, plan, bizDate }) => {
        const response = await fetch(`/api/recon/run-plans/${plan}/run`, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${authToken}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            biz_date: bizDate,
            trigger_mode: 'manual',
            run_context: { initiated_by: 'playwright_e2e' },
          }),
        });
        const data = await response.json().catch(() => ({}));
        return { status: response.status, data };
      },
      { authToken: authSession.token, plan: planCode, bizDate: new Date().toISOString().slice(0, 10) },
    );
    expect([200, 400]).toContain(triggerResult.status);

    const runRecord = await waitForRunRecord(page, authSession.token, planCode);
    expect(String(runRecord.id || '')).toBeTruthy();
    await openReconCenter(page);
    await page.getByRole('button', { name: '运行记录' }).click();
    const exceptionButton = page.getByRole('button', { name: '异常看板' }).first();
    await expect(exceptionButton).toBeVisible({ timeout: 30_000 });
    await exceptionButton.click();
    await expect(page.getByText('失败原因', { exact: true })).toBeVisible();
  });
});

test('对账中心可打开并进入新增对账方案第二步', async ({ page }) => {
  const authSession = await registerAuthSession(page);
  await seedAuthSession(page, authSession);

  await openReconCenter(page);
  await page.getByRole('button', { name: '新增对账方案' }).click();

  await expect(page.getByText('按四步完成方案设计与试跑确认')).toBeVisible();
  await page.getByLabel('方案名称').fill('Playwright 冒烟方案');
  await page.getByLabel('对账目的').fill('核对左右数据集中的订单金额是否一致。');
  await expect(page.getByRole('button', { name: '下一步' })).toBeEnabled();
  await page.getByRole('button', { name: '下一步' }).click();

  await expect(
    page.getByText('第二步只负责数据整理。先选中左右侧原始数据，再生成和试跑当前的数据整理配置。'),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'AI生成整理配置' })).toBeVisible();
});

test('对账方案可完成真实生成并保存运行计划后查看运行记录', async ({ page }) => {
  test.setTimeout(420_000);

  const authSession = await registerAuthSession(page);
  await seedAuthSession(page, authSession);

  const datasetCandidates = await discoverDatasetCandidates(page, authSession.token);
  expect(datasetCandidates.length).toBeGreaterThan(0);
  const selectedDataset = datasetCandidates[0];
  console.log(
    `Using dataset for P0 acceptance: ${selectedDataset.sourceName} / ${selectedDataset.datasetName} / ${selectedDataset.columns.join(', ')}`,
  );

  const schemeName = `PW 实模验收 ${Date.now()}`;
  const today = new Date().toISOString().slice(0, 10);

  await openReconCenter(page);
  await page.getByRole('button', { name: '新增对账方案' }).click();

  await page.getByLabel('方案名称').fill(schemeName);
  await page.getByLabel('对账目的').fill('将左右两侧数据整理成同一口径的订单金额明细，按业务主键匹配并校验金额是否一致。');
  await expect(page.getByRole('button', { name: '下一步' })).toBeEnabled();
  await page.getByRole('button', { name: '下一步' }).click();
  await expect(
    page.getByText('第二步只负责数据整理。先选中左右侧原始数据，再生成和试跑当前的数据整理配置。'),
  ).toBeVisible();
  await selectDatasetInDropdown(page, '左侧原始数据', selectedDataset.datasetName);
  await selectDatasetInDropdown(page, '右侧原始数据', selectedDataset.datasetName);

  console.log('Step 1 complete');
  await expect(page.getByRole('button', { name: 'AI生成整理配置' })).toBeVisible();
  console.log('Step 2 generate proc start');
  await page.getByRole('button', { name: 'AI生成整理配置' }).click();
  await waitForOptionalStatus(page, 'AI 正在生成整理配置，请稍候…', 120_000);
  await expect(page.getByLabel('数据整理配置')).toHaveValue(/\S[\s\S]*/, { timeout: 120_000 });
  await page.getByRole('button', { name: 'JSON' }).click();
  await expect(page.getByText('数据整理配置 JSON')).toBeVisible();
  await expect(page.locator('pre')).toContainText('"steps"');
  await expect(page.locator('pre')).toContainText('"action"');
  await closeJsonPreview(page);
  console.log('Step 2 generate proc done');

  console.log('Step 2 trial proc start');
  await page.getByRole('button', { name: '试跑验证' }).click();
  await waitForOptionalStatus(page, 'AI 正在试跑数据整理，请稍候…', 120_000);
  await expect(page.getByText('左侧原始数据抽样')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText('整理后左侧输出')).toBeVisible();
  await expect(page.getByRole('button', { name: '下一步' })).toBeEnabled();
  console.log('Step 2 trial proc done');

  await page.getByRole('button', { name: '下一步' }).click();
  await expect(page.getByRole('button', { name: 'AI生成对账逻辑' })).toBeVisible();

  console.log('Step 3 generate recon start');
  await page.getByRole('button', { name: 'AI生成对账逻辑' }).click();
  await waitForOptionalStatus(page, 'AI 正在生成对账逻辑，请稍候…', 120_000);
  await expect(page.getByLabel('数据对账逻辑')).toHaveValue(/\S[\s\S]*/, { timeout: 120_000 });
  await page.getByRole('button', { name: 'JSON' }).click();
  await expect(page.getByText('对账逻辑 JSON')).toBeVisible();
  await expect(page.locator('pre')).toContainText('"rules"');
  await expect(page.locator('pre')).toContainText('"source_file"');
  await closeJsonPreview(page);
  console.log('Step 3 generate recon done');

  console.log('Step 3 trial recon start');
  await page.getByRole('button', { name: '试跑验证' }).click();
  await waitForOptionalStatus(page, 'AI 正在试跑数据对账，请稍候…', 120_000);
  await expect(page.getByText('对账结果摘要')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('button', { name: '下一步' })).toBeEnabled();
  console.log('Step 3 trial recon done');

  await page.getByRole('button', { name: '下一步' }).click();
  await expect(page.getByText('确认保存前，再看一遍当前方案')).toBeVisible();
  await expect(page.getByText('当前整理配置和对账规则都已试跑通过，可以保存方案。')).toBeVisible();
  await page.getByRole('button', { name: '保存方案' }).click();
  await expect(page.getByText('按四步完成方案设计与试跑确认')).toHaveCount(0, { timeout: 30_000 });
  console.log('Step 4 save scheme done');

  const schemesResult = await fetchAuthedJson<Record<string, unknown>>(page, authSession.token, '/api/recon/schemes');
  expect(schemesResult.ok).toBeTruthy();
  const schemes = Array.isArray((schemesResult.data as Record<string, unknown>).schemes)
    ? ((schemesResult.data as Record<string, unknown>).schemes as Array<Record<string, unknown>>)
    : [];
  const savedScheme = schemes.find((item) => String(item.scheme_name || item.name || '') === schemeName);
  expect(savedScheme).toBeTruthy();
  const schemeCode = String(savedScheme?.scheme_code || savedScheme?.schemeCode || '');
  expect(schemeCode).toBeTruthy();
  const savedSchemeMeta = extractSchemeMetaRow(savedScheme);
  const leftOutputFields = extractOutputFieldNames(savedSchemeMeta.left_output_fields);
  const rightOutputFields = extractOutputFieldNames(savedSchemeMeta.right_output_fields);
  const leftTimeSemantic = String(savedSchemeMeta.left_time_semantic || '');
  const rightTimeSemantic = String(savedSchemeMeta.right_time_semantic || '');
  expect(leftOutputFields.length).toBeGreaterThan(0);
  expect(rightOutputFields.length).toBeGreaterThan(0);
  expect(String(savedSchemeMeta.match_key || '')).toBeTruthy();
  expect(String(savedSchemeMeta.left_amount_field || '')).toBeTruthy();
  expect(String(savedSchemeMeta.right_amount_field || '')).toBeTruthy();
  expect(leftTimeSemantic).toBeTruthy();
  expect(rightTimeSemantic).toBeTruthy();

  await openReconCenter(page);
  await page.getByRole('button', { name: '对账方案', exact: true }).click();
  const savedSchemeRow = getSchemeRow(page, schemeName);
  await expect(savedSchemeRow).toBeVisible();
  await savedSchemeRow.getByRole('button', { name: '查看详情' }).click();
  await expect(page.getByText('方案详情')).toBeVisible();
  const detailModal = page.locator('div').filter({ has: page.getByText('方案详情') }).last();
  await expect(detailModal).toContainText(leftOutputFields[0]);
  await expect(detailModal).toContainText(rightOutputFields[0]);
  await page.getByRole('button', { name: '新增运行计划' }).click();
  await expect(page.getByText('为方案补充调度、时间口径、协作通道与责任人')).toBeVisible();
  await expect(page.getByLabel('对账方案')).toHaveValue(schemeCode);
  await expect(page.getByLabel('左侧时间口径')).toHaveValue(leftTimeSemantic);
  await expect(page.getByLabel('右侧时间口径')).toHaveValue(rightTimeSemantic);
  await page.getByLabel('责任人').fill('Playwright 责任人');
  await page.getByRole('button', { name: '保存任务' }).click();
  await expect(page.getByText('为方案补充调度、时间口径、协作通道与责任人')).toHaveCount(0, { timeout: 30_000 });
  console.log('Run plan saved');

  const tasksResult = await fetchAuthedJson<Record<string, unknown>>(page, authSession.token, '/api/recon/tasks');
  expect(tasksResult.ok).toBeTruthy();
  const tasks = Array.isArray((tasksResult.data as Record<string, unknown>).tasks)
    ? ((tasksResult.data as Record<string, unknown>).tasks as Array<Record<string, unknown>>)
    : [];
  const savedTask = tasks.find((item) => String(item.scheme_code || item.schemeCode || '') === schemeCode);
  expect(savedTask).toBeTruthy();
  const planCode = String(savedTask?.plan_code || savedTask?.planCode || '');
  const planName = String(savedTask?.plan_name || savedTask?.planName || '');
  expect(planCode).toBeTruthy();
  expect(planName).toBeTruthy();

  const runTriggerResult = await fetchAuthedJson<Record<string, unknown>>(
    page,
    authSession.token,
    `/api/recon/run-plans/${planCode}/run`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        biz_date: today,
        trigger_mode: 'manual',
        run_context: { initiated_by: 'playwright_e2e' },
      }),
    },
  );
  expect(runTriggerResult.status).toBe(200);
  console.log(`Run trigger status: ${runTriggerResult.status}`);

  const runRecord = await waitForRunRecord(page, authSession.token, planCode);
  const runId = String(runRecord.id || '');
  const executionStatus = String(runRecord.execution_status || runRecord.executionStatus || '');
  console.log(`Run created: ${planCode} / ${runId} / ${executionStatus}`);
  expect(runId).toBeTruthy();

  await page.reload();
  await openReconCenter(page);
  await page.getByRole('button', { name: '运行记录' }).click();
  await expect(page.getByText(planName)).toBeVisible({ timeout: 30_000 });

  const runRow = page.getByTestId(`execution-run-row-${runId}`);
  await expect(runRow).toBeVisible();

  if (['failed', 'error'].includes(executionStatus.toLowerCase())) {
    const retryButton = runRow.getByRole('button', { name: /重试/ });
    if (await retryButton.count()) {
      await retryButton.click();
      await expect(page.getByText('已重新触发该运行任务，请稍后刷新查看最新状态。')).toBeVisible({ timeout: 30_000 });
    }
  }

  await page.getByTestId(`execution-run-exceptions-${runId}`).click();
  await expect(page.getByText('失败原因', { exact: true })).toBeVisible();

  const exceptionsResult = await fetchAuthedJson<Record<string, unknown>>(
    page,
    authSession.token,
    `/api/recon/runs/${runId}/exceptions`,
  );
  expect(exceptionsResult.ok).toBeTruthy();
  const exceptionRows = Array.isArray((exceptionsResult.data as Record<string, unknown>).exceptions)
    ? ((exceptionsResult.data as Record<string, unknown>).exceptions as Array<Record<string, unknown>>)
    : [];

  if (exceptionRows.length > 0) {
    await expect(page.getByText('异常内容')).toBeVisible();
  } else {
    await expect(page.getByText('当前运行暂无异常处理记录。')).toBeVisible();
  }
});
