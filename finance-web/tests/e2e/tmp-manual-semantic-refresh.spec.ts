import { expect, test, type Page } from '@playwright/test';

const ADMIN_USERNAME = 'admin';
const ADMIN_PASSWORD = 'admin123';
const SOURCE_NAME = '财务中台订单holo';
const DATASET_CODE = 'public.ods_yxst_trd_order_di_o';

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

test('手动刷新语义建议返回最新结果', async ({ page }) => {
  test.setTimeout(180_000);

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
  await page.getByText(SOURCE_NAME).click();
  await page.getByRole('button', { name: '物理目录' }).click();
  await page.getByPlaceholder('搜索表名/业务名/关键字').fill(DATASET_CODE);

  const datasetRow = page.locator('tr').filter({ hasText: DATASET_CODE }).first();
  await expect(datasetRow).toBeVisible();

  const managePublishButton = datasetRow.getByRole('button', { name: '管理发布' });
  if ((await managePublishButton.count()) > 0) {
    await managePublishButton.first().click();
  } else {
    await datasetRow.getByRole('button', { name: '发布' }).first().click();
  }

  await expect(page.getByRole('button', { name: '刷新语义建议' })).toBeVisible();
  const initialResponseCount = semanticResponses.length;

  await page.getByRole('button', { name: '刷新语义建议' }).click();

  await expect
    .poll(() => semanticResponses.length, {
      timeout: 90_000,
      intervals: [500, 1000, 2000],
    })
    .toBe(initialResponseCount + 1);

  const latestResponse = semanticResponses[semanticResponses.length - 1] ?? null;
  expect(latestResponse?.status).toBe(200);
  const latestDataset =
    (latestResponse?.body.dataset as Record<string, unknown> | undefined) ??
    (latestResponse?.body.item as Record<string, unknown> | undefined) ??
    (((latestResponse?.body.data as Record<string, unknown> | undefined)?.dataset as Record<string, unknown>) ||
      undefined);
  const metadata =
    ((latestDataset?.metadata as Record<string, unknown> | undefined) ??
      (latestDataset?.meta as Record<string, unknown> | undefined) ??
      {}) as Record<string, unknown>;
  const semanticProfile = ((metadata.semantic_profile as Record<string, unknown> | undefined) ??
    {}) as Record<string, unknown>;
  const semanticGenerator = ((semanticProfile.semantic_generator as Record<string, unknown> | undefined) ??
    {}) as Record<string, unknown>;
  const semanticFields = Array.isArray(semanticProfile.fields)
    ? (semanticProfile.fields as Array<Record<string, unknown>>)
    : [];

  console.log(
    JSON.stringify(
      {
        status: latestResponse?.status,
        body: latestResponse?.body,
        message: latestResponse?.body.message,
        semanticStatus: latestDataset?.semantic_status,
        profileStatus: semanticProfile.status,
        generatorMode: semanticGenerator.mode,
        generatorProvider: semanticGenerator.provider,
        llmEnabled: semanticGenerator.llm_enabled,
        fieldPreview: semanticFields.slice(0, 8).map((field) => ({
          raw_name: field.raw_name,
          display_name: field.display_name,
          source: field.source,
          confirmed_by_user: field.confirmed_by_user,
        })),
      },
      null,
      2,
    ),
  );
});
