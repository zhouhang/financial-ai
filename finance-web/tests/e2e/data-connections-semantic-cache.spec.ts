import { execFileSync } from 'node:child_process';
import { expect, test, type Page } from '@playwright/test';

const ADMIN_USERNAME = 'admin';
const ADMIN_PASSWORD = 'admin123';
const DATASET_SOURCE_NAME = '财务中台订单holo';
const DATASET_CODE = 'public_ads_d_cardstock_zm_order_info_20200117';

function resetDatasetSemanticCache() {
  const sql = `
    UPDATE data_source_datasets AS d
    SET meta = COALESCE(d.meta, '{}'::jsonb) - 'semantic_profile',
        updated_at = CURRENT_TIMESTAMP
    FROM data_sources AS s
    WHERE s.id = d.data_source_id
      AND s.name = '${DATASET_SOURCE_NAME}'
      AND d.dataset_code = '${DATASET_CODE}';
  `;

  execFileSync(
    'psql',
    ['-h', 'localhost', '-U', 'tally_user', '-d', 'tally', '-v', 'ON_ERROR_STOP=1', '-c', sql],
    {
      env: {
        ...process.env,
        PGPASSWORD: process.env.DB_PASSWORD || '123456',
      },
      stdio: 'pipe',
    },
  );
}

async function loginAsAdmin(page: Page) {
  await page.goto('/');
  const loginResult = await page.evaluate(
    async ({ username, password }) => {
      const form = new FormData();
      form.append('username', username);
      form.append('password', password);

      const response = await fetch('/api/auth/login', {
        method: 'POST',
        body: form,
      });
      const data = await response.json().catch(() => ({}));
      if (response.ok && data.success && data.token) {
        window.localStorage.setItem('tally_auth_token', String(data.token));
        window.localStorage.setItem(
          'tally_current_user',
          JSON.stringify({
            id: String(data.user?.id || ''),
            userId: String(data.user?.id || ''),
            username: String(data.user?.username || username),
          }),
        );
      }
      return { ok: response.ok, data };
    },
    {
      username: ADMIN_USERNAME,
      password: ADMIN_PASSWORD,
    },
  );

  expect(loginResult.ok).toBeTruthy();
  expect((loginResult.data as Record<string, unknown>).success).toBeTruthy();
  await page.reload();
}

test('首开发布自动触发语义刷新，二次打开复用缓存', async ({ page }) => {
  test.setTimeout(180_000);
  resetDatasetSemanticCache();

  const semanticResponses: Array<{
    status: number;
    body: Record<string, unknown>;
  }> = [];

  page.on('response', async (response) => {
    if (!response.url().includes('/semantic-profile')) return;
    const body = (await response.json().catch(() => ({}))) as Record<string, unknown>;
    semanticResponses.push({
      status: response.status(),
      body,
    });
  });

  await loginAsAdmin(page);
  await page.goto('/?section=data-connections');

  await page.getByRole('button', { name: '数据库连接' }).click();
  await page.getByText(DATASET_SOURCE_NAME).click();
  await page.getByRole('button', { name: '物理目录' }).click();
  await page.getByPlaceholder('搜索表名/业务名/关键字').fill(DATASET_CODE);

  const datasetRow = page.locator('tr').filter({ hasText: DATASET_CODE }).first();
  await expect(datasetRow).toBeVisible();

  await datasetRow.getByRole('button', { name: '发布' }).click();
  await expect(page.getByRole('button', { name: '关闭' })).toBeVisible();

  await expect
    .poll(() => semanticResponses.length, {
      timeout: 75_000,
      intervals: [500, 1000, 2000],
    })
    .toBe(1);

  const firstResponse = semanticResponses[0] ?? null;
  const firstDataset =
    (firstResponse?.body.dataset as Record<string, unknown> | undefined) ??
    (firstResponse?.body.item as Record<string, unknown> | undefined) ??
    (((firstResponse?.body.data as Record<string, unknown> | undefined)?.dataset as Record<string, unknown>) ||
      undefined);
  const metadata =
    ((firstDataset?.metadata as Record<string, unknown> | undefined) ??
      (firstDataset?.meta as Record<string, unknown> | undefined) ??
      {}) as Record<string, unknown>;
  const semanticProfile = ((metadata.semantic_profile as Record<string, unknown> | undefined) ??
    {}) as Record<string, unknown>;
  const semanticGenerator = ((semanticProfile.semantic_generator as Record<string, unknown> | undefined) ??
    {}) as Record<string, unknown>;

  console.log(
    JSON.stringify(
      {
        firstCallStatus: firstResponse?.status,
        message: firstResponse?.body.message,
        semanticStatus: firstDataset?.semantic_status,
        profileStatus: semanticProfile.status,
        generatorMode: semanticGenerator.mode,
        generatorProvider: semanticGenerator.provider,
        llmEnabled: semanticGenerator.llm_enabled,
      },
      null,
      2,
    ),
  );

  await page.getByRole('button', { name: '关闭' }).click();
  await expect(page.getByRole('button', { name: '关闭' })).toHaveCount(0);

  await datasetRow.getByRole('button', { name: '发布' }).click();
  await expect(page.getByRole('button', { name: '关闭' })).toBeVisible();

  await page.waitForTimeout(5000);
  expect(semanticResponses.length).toBe(1);
});
