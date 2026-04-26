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

  await openReconCenter(page);
  await page.getByRole('button', { name: '新增对账方案' }).click();
  await expect(page.getByText('按四步完成方案设计与试跑确认')).toBeVisible();

  await page.getByLabel('方案名称').fill(`PW 关键路径方案 ${Date.now()}`);
  await page.getByLabel('对账目的').fill('核对左右两侧订单金额与业务主键是否一致。');

  const nextStepButton = page.getByRole('button', { name: '下一步' });
  await expect(nextStepButton).toBeEnabled();
  await nextStepButton.click();

  await expect(page.getByText('第二步：选择数据集并配置输出字段')).toBeVisible();
  await expect(page.getByText('1. 选择左右原始数据集')).toBeVisible();
  await expect(page.getByText('2. 调整左右输出字段')).toBeVisible();
  await expect(page.getByText('选完数据集后会自动推荐字段')).toBeVisible();
  await expect(page.getByText('左侧输出字段')).toBeVisible();
  await expect(page.getByText('右侧输出字段')).toBeVisible();
  await expect(page.getByRole('button', { name: '试跑验证' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'AI生成整理配置' })).toHaveCount(0);
});
