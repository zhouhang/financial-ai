import { expect, test, type Page } from '@playwright/test';

interface AuthSession {
  token: string;
  userId: string;
  username: string;
}

const DEFAULT_COMPANY_ID = '00000000-0000-0000-0000-000000000001';
const DEFAULT_DEPARTMENT_ID = '00000000-0000-0000-0000-000000000002';

async function registerAuthSession(page: Page): Promise<AuthSession> {
  await page.goto('/');
  const username = `pw_keyflow_${Date.now()}`;
  const password = 'Pw123456!';

  const registerResult = await page.evaluate(
    async ({ name, pwd, companyId, departmentId }) => {
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
      return { ok: response.ok, data };
    },
    {
      name: username,
      pwd: password,
      companyId: DEFAULT_COMPANY_ID,
      departmentId: DEFAULT_DEPARTMENT_ID,
    },
  );

  expect(registerResult.ok).toBeTruthy();
  const resultData = registerResult.data as Record<string, unknown>;
  expect(resultData.success).toBeTruthy();
  expect(resultData.token).toBeTruthy();

  return {
    token: String(resultData.token),
    userId: String((resultData.user as { id?: string } | undefined)?.id || ''),
    username: String((resultData.user as { username?: string } | undefined)?.username || username),
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
  await reconCenterEntry.click();
  await expect(page.getByText('统一查看对账方案、对账任务与运行记录')).toBeVisible();
}

async function hasAnyDataset(page: Page, authToken: string): Promise<boolean> {
  return page.evaluate(async ({ token }) => {
    const headers = { Authorization: `Bearer ${token}` };
    const sourceResponse = await fetch('/api/data-sources', { headers });
    if (!sourceResponse.ok) return false;
    const sourceData = await sourceResponse.json().catch(() => ({}));
    const sources = Array.isArray(sourceData.sources) ? sourceData.sources : [];
    for (const source of sources) {
      const sourceId = String((source as { id?: string }).id || '');
      if (!sourceId) continue;
      const datasetResponse = await fetch(`/api/data-sources/${sourceId}/datasets`, { headers });
      if (!datasetResponse.ok) continue;
      const datasetData = await datasetResponse.json().catch(() => ({}));
      const datasets = Array.isArray(datasetData.datasets) ? datasetData.datasets : [];
      if (datasets.length > 0) return true;
    }
    return false;
  }, { token: authToken });
}

async function selectDatasetInDropdown(page: Page, sectionTitle: '左侧原始数据' | '右侧原始数据') {
  const card = page
    .getByText(sectionTitle)
    .locator('xpath=ancestor::div[contains(@class,"rounded-3xl")][1]');
  const dropdownButton = card.getByRole('button').first();
  await dropdownButton.click();

  const dropdownPanel = page
    .locator('div.absolute')
    .filter({ has: page.getByRole('button', { name: '确定' }) })
    .last();
  await expect(dropdownPanel).toBeVisible();
  await dropdownPanel.locator('input[type="checkbox"]').first().check();
  await dropdownPanel.getByRole('button', { name: '确定' }).click();
  await expect(dropdownPanel).toHaveCount(0);
}

test('对账中心顶部三个视图可切换', async ({ page }) => {
  const authSession = await registerAuthSession(page);
  await seedAuthSession(page, authSession);
  await openReconCenter(page);

  await page.getByRole('button', { name: '对账方案', exact: true }).click();
  await expect(page.getByRole('button', { name: '新增对账方案' })).toBeVisible();

  await page.getByRole('button', { name: '对账任务', exact: true }).click();
  await expect(page.getByRole('button', { name: '新增运行计划' })).toBeVisible();
  await expect(page.getByText('任务名称')).toBeVisible();

  await page.getByRole('button', { name: '运行记录', exact: true }).click();
  await expect(page.getByText('运行任务')).toBeVisible();
});

test('对账中心可打开新增运行计划浮层（无方案时回退验证新增对账方案浮层）', async ({ page }) => {
  const authSession = await registerAuthSession(page);
  await seedAuthSession(page, authSession);
  await openReconCenter(page);
  await page.getByRole('button', { name: '对账任务', exact: true }).click();

  const openPlanButton = page.getByRole('button', { name: '新增运行计划' });
  if (await openPlanButton.isEnabled()) {
    await openPlanButton.click();
    await expect(page.getByText('为方案补充调度、时间口径、协作通道与责任人')).toBeVisible();
    await expect(page.getByRole('button', { name: '保存任务' })).toBeVisible();
    return;
  }

  await page.getByRole('button', { name: '对账方案', exact: true }).click();
  await page.getByRole('button', { name: '新增对账方案' }).click();
  await expect(page.getByText('按四步完成方案设计与试跑确认')).toBeVisible();
});

test('新增对账方案可完成第一步并进入第二步', async ({ page }) => {
  const authSession = await registerAuthSession(page);
  await seedAuthSession(page, authSession);

  const datasetReady = await hasAnyDataset(page, authSession.token);
  test.skip(!datasetReady, '当前环境无可用数据集，跳过方案向导步骤验证。');

  await openReconCenter(page);
  await page.getByRole('button', { name: '新增对账方案' }).click();
  await expect(page.getByText('按四步完成方案设计与试跑确认')).toBeVisible();

  await page.getByLabel('方案名称').fill(`PW 关键路径方案 ${Date.now()}`);
  await page.getByLabel('对账目标').fill('核对左右两侧订单金额与业务主键是否一致。');

  await selectDatasetInDropdown(page, '左侧原始数据');
  await selectDatasetInDropdown(page, '右侧原始数据');

  const nextStepButton = page.getByRole('button', { name: '下一步' });
  await expect(nextStepButton).toBeEnabled();
  await nextStepButton.click();

  await expect(page.getByText('配置方式')).toBeVisible();
  await expect(page.getByRole('button', { name: 'AI生成整理配置' })).toBeVisible();
});
