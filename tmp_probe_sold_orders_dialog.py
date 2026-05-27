import asyncio
import json

from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:55711")
        page = next(
            (pg for c in browser.contexts for pg in c.pages if "trade-platform/tp/sold" in pg.url),
            None,
        )
        if page is None:
            raise SystemExit("sold page not found")
        data = await page.evaluate(
            """
            () => {
              const visible = (el) => {
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
              };
              const labelText = (el) => {
                const label = el.closest('label');
                if (label) return label.innerText || label.textContent || '';
                const parent = el.parentElement;
                return parent ? (parent.innerText || parent.textContent || '') : '';
              };
              const inputs = [...document.querySelectorAll('input')].map((el, i) => ({
                i,
                type: el.type,
                value: el.value,
                placeholder: el.getAttribute('placeholder'),
                checked: el.checked,
                disabled: el.disabled,
                visible: visible(el),
                aria: el.getAttribute('aria-label'),
                cls: el.className,
                text: labelText(el).trim().slice(0, 120),
              }));
              const buttons = [...document.querySelectorAll('button')].map((el, i) => ({
                i,
                text: (el.innerText || el.textContent || '').trim(),
                disabled: el.disabled,
                visible: visible(el),
                cls: el.className,
              }));
              const checkboxes = inputs.filter((el) => el.type === 'checkbox' || String(el.cls).includes('checkbox'));
              const dialogs = [...document.querySelectorAll('[role=dialog], .next-dialog, .next-overlay-wrapper, .next-balloon')].map((el, i) => ({
                i,
                visible: visible(el),
                cls: el.className,
                text: (el.innerText || el.textContent || '').trim().slice(0, 1600),
              }));
              return { inputs, buttons, checkboxes, dialogs };
            }
            """
        )
        print(json.dumps(data, ensure_ascii=False, indent=2))
        await browser.close()


asyncio.run(main())
