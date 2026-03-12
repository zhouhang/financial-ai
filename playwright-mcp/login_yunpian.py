import json
import re
from typing import Dict, List

from playwright.sync_api import sync_playwright


URL = "https://www.yunpian.com/entry"
EMAIL = "2006zhouhang@163.com"
PASSWORD = "19861201zh"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # 1. 打开登录页
        page.goto(URL, wait_until="domcontentloaded", timeout=60_000)

        # 2. 切换到"邮箱登录"Tab
        try:
            page.get_by_text("邮箱登录", exact=True).click(timeout=10_000)
            except Exception:
            # 如果未找到精确文本，尝试模糊匹配
            page.get_by_text("邮箱", exact=False).click(timeout=10_000)

        # 3. 填写邮箱与密码（根据实际占位符）
        email_input = page.get_by_placeholder("输入注册邮箱地址")
        email_input.fill(EMAIL)

        password_input = page.get_by_placeholder("8-24位，至少包含数字、英文、符号中的两种")
        password_input.fill(PASSWORD)

        # 4. 点击登录按钮
        page.get_by_text("登 录").click()

        # 5. 等待跳转到欢迎页（根据实际情况可改成等待特定元素）
        page.wait_for_url("**/console/**", timeout=60_000)
        page.wait_for_load_state("domcontentloaded", timeout=60_000)

        # 6. 抓取欢迎页的主要信息
        # 页面主内容
        main_text = page.inner_text("body")

        # 等待几秒让控制台 iframe 加载
        page.wait_for_timeout(5_000)

        # 遍历所有 frame，收集正文
        iframe_texts = []
        for frame in page.frames:
            try:
                body_text = frame.locator("body").inner_text(timeout=5_000)
                iframe_texts.append(body_text)
            except Exception:
                continue

        combined = (main_text + "\n\n" + "\n\n".join(iframe_texts)).strip()

        print("\n====== 欢迎页主要信息（截取前 2000 字符） ======\n")
        print(combined[:2000])

        # 7. 将关键字段结构化为 JSON
        def extract_company(text: str) -> str:
            m = re.search(r"\n([^\n]{2,30}?有限公司)\s*\n", text)
            return m.group(1).strip() if m else ""

        def extract_balance(text: str) -> str:
            m = re.search(r"账户余额\s*¥\s*([0-9.,]+)", text)
            return m.group(1) if m else ""

        def extract_user_level(text: str) -> str:
            m = re.search(r"\n(普通用户|高级用户|管理员)\s*\n", text)
            return m.group(1) if m else ""

        def extract_verified(text: str) -> bool:
            return "已认证" in text

        def extract_sub_accounts(text: str) -> int:
            m = re.search(r"共\s*(\d+)\s*个子账号", text)
            return int(m.group(1)) if m else 0

        def extract_notices(text: str, limit: int = 8) -> List[str]:
            # 抓取“公告”段落之后的若干行
            notices: List[str] = []
            if "公告" not in text:
                return notices
            segment = text.split("公告", 1)[1]
            # 按行拆分，过滤空行，截断
            for line in segment.splitlines():
                line = line.strip()
                if not line or len(line) < 2:
                    continue
                # 忽略明显的按钮/符号
                if line in {"更多", "置顶"}:
                    continue
                # 截取到日期或过长则收集
                notices.append(line)
                if len(notices) >= limit:
                    break
            return notices

        summary: Dict[str, object] = {
            "company": extract_company(combined),
            "verified": extract_verified(combined),
            "user_level": extract_user_level(combined),
            "balance": extract_balance(combined),
            "sub_accounts": extract_sub_accounts(combined),
            "notices": extract_notices(combined),
        }

        print("\n====== 欢迎页结构化信息 (JSON) ======\n")
        print(json.dumps(summary, ensure_ascii=False, indent=2))

        # 7. 关闭浏览器
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
