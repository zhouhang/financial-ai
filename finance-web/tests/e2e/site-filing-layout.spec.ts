import { expect, test, type Page } from '@playwright/test';

interface LayoutBox {
  x: number;
  y: number;
  width: number;
  height: number;
  right: number;
  bottom: number;
}

interface SiteFilingLayout {
  filing: LayoutBox | null;
  main: LayoutBox | null;
  aside: LayoutBox | null;
  shell: LayoutBox | null;
  content: LayoutBox | null;
  text: string;
  href: string;
  overlapsAside: boolean;
  insideMain: boolean;
  spansViewport: boolean;
  viewport: {
    width: number;
    height: number;
  };
}

function assertBox(value: LayoutBox | null, label: string): LayoutBox {
  if (!value) {
    throw new Error(`Missing layout box: ${label}`);
  }
  return value;
}

async function collectSiteFilingLayout(page: Page): Promise<SiteFilingLayout> {
  return page.evaluate(() => {
    const rect = (element: Element | null) => {
      if (!element) return null;
      const box = element.getBoundingClientRect();
      return {
        x: Math.round(box.x),
        y: Math.round(box.y),
        width: Math.round(box.width),
        height: Math.round(box.height),
        right: Math.round(box.right),
        bottom: Math.round(box.bottom),
      };
    };

    const filing = document.querySelector('.site-filing');
    const main = document.querySelector('main.site-main-column');
    const aside = document.querySelector('aside');
    const shell = document.querySelector('.site-shell');
    const content = document.querySelector('.site-shell-content');
    const link = document.querySelector('.site-filing a');
    const filingBox = rect(filing);
    const mainBox = rect(main);
    const asideBox = rect(aside);
    const overlapsAside = Boolean(
      filingBox &&
        asideBox &&
        filingBox.x < asideBox.right &&
        filingBox.right > asideBox.x &&
        filingBox.y < asideBox.bottom &&
        filingBox.bottom > asideBox.y,
    );
    const insideMain = Boolean(
      filingBox &&
        mainBox &&
        filingBox.x >= mainBox.x &&
        filingBox.right <= mainBox.right &&
        filingBox.bottom <= mainBox.bottom,
    );
    const spansViewport = Boolean(filingBox && filingBox.x === 0 && filingBox.right === window.innerWidth);

    return {
      filing: filingBox,
      main: mainBox,
      aside: asideBox,
      shell: rect(shell),
      content: rect(content),
      text: link?.textContent?.trim() ?? '',
      href: link instanceof HTMLAnchorElement ? link.href : '',
      overlapsAside,
      insideMain,
      spansViewport,
      viewport: {
        width: window.innerWidth,
        height: window.innerHeight,
      },
    };
  });
}

test('主应用备案号固定在右侧内容列底部且不遮挡侧栏', async ({ page }) => {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await expect(page.getByLabel('ICP备案号')).toBeVisible();

  const expanded = await collectSiteFilingLayout(page);
  const expandedFiling = assertBox(expanded.filing, 'expanded filing');
  const expandedMain = assertBox(expanded.main, 'expanded main');
  const expandedAside = assertBox(expanded.aside, 'expanded aside');

  expect(expanded.text).toBe('鄂ICP备2026028755号-1');
  expect(expanded.href).toBe('https://beian.miit.gov.cn/');
  expect(expanded.insideMain).toBe(true);
  expect(expanded.overlapsAside).toBe(false);
  expect(expanded.spansViewport).toBe(false);
  expect(expandedFiling.x).toBe(expandedMain.x);
  expect(expandedFiling.right).toBe(expandedMain.right);
  expect(expandedFiling.x).toBe(expandedAside.right);

  await page.getByTitle('收起侧边栏').click();
  await expect(page.getByTitle('展开侧边栏')).toBeVisible();

  const collapsed = await collectSiteFilingLayout(page);
  const collapsedFiling = assertBox(collapsed.filing, 'collapsed filing');
  const collapsedMain = assertBox(collapsed.main, 'collapsed main');
  const collapsedAside = assertBox(collapsed.aside, 'collapsed aside');

  expect(collapsed.insideMain).toBe(true);
  expect(collapsed.overlapsAside).toBe(false);
  expect(collapsed.spansViewport).toBe(false);
  expect(collapsedFiling.x).toBe(collapsedMain.x);
  expect(collapsedFiling.right).toBe(collapsedMain.right);
  expect(collapsedFiling.x).toBe(collapsedAside.right);
});

test('公共页面备案号保留全宽底部栏且内容区避开备案栏', async ({ page }) => {
  for (const route of ['/handoff', '/recon/runs/run-001/exceptions?owner=ding-user-001']) {
    await page.goto(route, { waitUntil: 'domcontentloaded' });
    await expect(page.getByLabel('ICP备案号')).toBeVisible();

    const layout = await collectSiteFilingLayout(page);
    const filing = assertBox(layout.filing, `${route} filing`);
    const shell = assertBox(layout.shell, `${route} shell`);
    const content = assertBox(layout.content, `${route} content`);

    expect(layout.text).toBe('鄂ICP备2026028755号-1');
    expect(layout.spansViewport).toBe(true);
    expect(filing.bottom).toBe(layout.viewport.height);
    expect(shell.height).toBe(layout.viewport.height);
    expect(content.bottom).toBe(filing.y);
  }
});
