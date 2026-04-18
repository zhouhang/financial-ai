import { expect, test, type Page } from '@playwright/test';

const ADMIN_USERNAME = 'admin';
const ADMIN_PASSWORD = 'admin123';

async function loginAsAdmin(page: Page, theme: 'light' | 'dark' = 'light') {
  await page.goto('/');
  const loginResult = await page.evaluate(
    async ({ username, password, nextTheme }) => {
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
        window.localStorage.setItem('tally_theme_mode', nextTheme);
      }
      return { ok: response.ok, data };
    },
    {
      username: ADMIN_USERNAME,
      password: ADMIN_PASSWORD,
      nextTheme: theme,
    },
  );

  expect(loginResult.ok).toBeTruthy();
  expect((loginResult.data as Record<string, unknown>).success).toBeTruthy();
  await page.reload();
  await expect(page.getByRole('button', { name: '登录' })).toHaveCount(0);
}

async function openReconCenter(page: Page) {
  const reconGroupEntry = page.getByRole('button', { name: '数据对账' });
  await expect(reconGroupEntry).toBeVisible();
  await reconGroupEntry.click();
  await page.getByRole('button', { name: '对账中心' }).click();
  await expect(page.getByText('统一查看对账方案、对账任务与运行记录')).toBeVisible();
}

test('数据库连接页显示统一治理入口且操作列默认可见', async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto('/?section=data-connections');

  await page.getByRole('button', { name: '数据库连接' }).click();
  await expect(page.getByText('数据库连接列表')).toBeVisible();
  await page.getByText('财务中台订单holo').click();

  await expect(page.getByRole('button', { name: '物理目录' })).toBeVisible();
  await page.getByRole('button', { name: '物理目录' }).click();

  const keywordInput = page.getByPlaceholder('搜索表名/业务名/关键字');
  await keywordInput.fill('支付宝订单数据');

  const datasetRow = page.locator('tr').filter({ hasText: '支付宝订单数据' }).first();
  await expect(datasetRow).toBeVisible();
  await expect(datasetRow.getByRole('button', { name: '管理发布' })).toBeVisible();
  await expect(page.getByRole('button', { name: '编辑元数据' })).toHaveCount(0);

  await datasetRow.getByRole('button', { name: '管理发布' }).click();
  await expect(page.getByText('业务类型', { exact: true })).toHaveCount(0);
  await expect(page.getByText('粒度', { exact: true })).toHaveCount(0);
  await expect(page.getByText('关键字段', { exact: true })).toHaveCount(0);
  await expect(page.getByText('唯一标识字段', { exact: true })).toBeVisible();
  await expect(page.getByText(/保存时使用技术字段名/)).toBeVisible();
  await expect(page.getByPlaceholder('多个字段用逗号分隔，例如：订单号, 商户单号')).toHaveCount(0);
  await expect(page.getByText('字段语义确认', { exact: true })).toBeVisible();
  await expect(page.getByText('展开全部字段', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '刷新语义建议' })).toBeVisible();
  await expect(page.getByRole('button', { name: '全部接受建议' })).toBeVisible();
  await expect(page.getByRole('button', { name: '保存发布信息' })).toBeVisible();
});

test('新增对账方案可看到已发布数据集候选且 dark mode 确定按钮非白色', async ({ page }) => {
  await loginAsAdmin(page, 'dark');
  await openReconCenter(page);

  await page.getByRole('button', { name: '新增对账方案' }).click();
  await expect(page.getByText('按四步完成方案设计与试跑确认')).toBeVisible();

  await page.getByLabel('方案名称').fill(`PW 发布候选校验 ${Date.now()}`);
  await page.getByLabel('对账目标').fill('确认已发布数据集能够出现在左右侧原始数据候选中。');

  const leftCard = page.getByText('左侧原始数据').locator('xpath=ancestor::div[contains(@class,"rounded-3xl")][1]');
  const dropdownButton = leftCard.getByRole('button').first();
  await dropdownButton.click();

  const dropdownPanel = page
    .locator('div.absolute')
    .filter({ has: page.getByRole('button', { name: '确定' }) })
    .last();
  await expect(dropdownPanel).toBeVisible();

  const searchInput = dropdownPanel.getByPlaceholder('搜索业务名称/技术名/数据源，不输入则展示已发布候选');
  await searchInput.fill('支付宝');

  await expect(dropdownPanel.getByText('支付宝订单数据')).toBeVisible();

  const confirmButton = dropdownPanel.getByRole('button', { name: '确定' });
  const backgroundColor = await confirmButton.evaluate((element) => window.getComputedStyle(element).backgroundColor);
  expect(backgroundColor).not.toBe('rgb(255, 255, 255)');
});
