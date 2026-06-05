# Windows 浏览器采集机搭建（常开 browser-agent）

把一台常开的 Windows 机器装成 Tally 采集机，跑 `browser-agent`，连云端 `wss://www.tallyai.cn/api/browser-agent`。

> 重点：**原生跑，不要用 Docker**。browser-agent 要在「已登录的交互式桌面」里驱动真实 Chrome（OS 级远控接管要看窗口、注入点击/键盘），Windows 容器没有交互式 GUI，做不了。它只主动出站连云端、不开任何入站端口，所以放公司内网即可。

## 一、前置安装（一次）
1. **Windows 10 22H2+ 或 Windows 11**（带桌面；不要用 Server Core）。
2. 装 **Git**、**Python 3.12**（安装时勾 Add to PATH）、**Google Chrome**。
3. 拉代码（GitHub 慢的话用公司网/代理，或镜像到 gitee 再拉）：
   ```powershell
   git clone <仓库地址> C:\tally\financial-ai
   cd C:\tally\financial-ai
   ```

## 二、配置 .env（一次）
```powershell
copy finance-agents\browser-agent\.env.example finance-agents\browser-agent\.env
notepad finance-agents\browser-agent\.env
```
必填/改:
- `DATA_AGENT_WS_URL=wss://www.tallyai.cn/api/browser-agent`
- `JWT_SECRET=` **填 ECS `/opt/tally/.env.prod` 里同一个 JWT_SECRET**（必须一致，否则云端拒绝）
- `BROWSER_AGENT_COMPANY_ID=` 你的 company_id
- `BROWSER_AGENT_ID=collector-win-1`（给这台机器一个稳定唯一 id）
- 可选 `BROWSER_AGENT_PROFILE_ROOT` / `DOWNLOAD_ROOT` 用 Windows 路径，如 `C:\tally\profiles`

## 三、一键安装（管理员 PowerShell，用采集账号登录后运行）
```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\install-collector.ps1
```
它会:建 `.venv` + 装依赖 + `playwright install chrome`；关睡眠/息屏/休眠（交流电）；注册计划任务 **TallyBrowserAgent**（登录启动、交互式会话、崩溃自动重启）。

## 四、还需手动设置（让"交互式会话"常在）
1. **开启自动登录**：`netplwiz` → 取消"要使用本计算机，用户必须输入用户名和密码" → 填采集账号密码。（这样开机即进桌面，agent 才能在交互式会话里跑。）
2. **关闭锁屏/屏保/睡眠**：设置 → 电源，"屏幕和睡眠"全设"从不"；关屏保。
3. **网络**：确保能访问 `www.tallyai.cn`。若走代理：代理要**开机自启且先于 agent 就绪**（否则 agent 起来时解析不了域名会一直 `Errno 8`，需重启 agent 才恢复）。

## 五、启动与验证
```powershell
# 自检环境
powershell -ExecutionPolicy Bypass -File scripts\windows\start-browser-agent.ps1 -Check
# 立即启动(或重启电脑自动起)
Start-ScheduledTask -TaskName TallyBrowserAgent
# 看状态 / 日志
powershell -ExecutionPolicy Bypass -File scripts\windows\start-browser-agent.ps1 -Status
Get-Content finance-agents\browser-agent\logs\browser-agent.log -Tail 30 -Wait
```
日志出现 `data-agent WS 已连接: wss://www.tallyai.cn/...` 即成功。云端 `agents` 表会出现 `collector-win-1` 的实时心跳（离线告警里也不再缺它）。

## 六、日常运维
- 看状态：`start-browser-agent.ps1 -Status`
- 停止：`Stop-ScheduledTask -TaskName TallyBrowserAgent`（再 `start-browser-agent.ps1 -Stop` 兜底杀进程）
- 更新代码：`git pull` 后 `Stop-ScheduledTask` → `Start-ScheduledTask`（CI/CD 见下）
- 远程管理（从 Mac）：用 **ToDesk**（开无人值守 + 开机自启）最省事；要更安全用 **Tailscale + 远程桌面(RDP)**。

## 七、CI/CD（可选，后续）
采集机不打镜像、不用 registry。两种自动更新方式:
- **self-hosted GitHub Actions runner**（推荐）：在本机装 runner（主动出站连 GitHub，无需开入站），workflow `runs-on: [self-hosted, windows]`，push main 时 `git pull` + `pip install` + 重启计划任务。
- **拉取式**：再加一个计划任务，定时 `git pull`，有变更就重启 TallyBrowserAgent。

> 注意:OS 级远控（看窗口/注入）依赖 `pywin32 / mss / Pillow`，install 脚本已装；该能力的代码在合并到 main 后随 `git pull` 生效。当前未合并时，采集与 Playwright 版接管仍可正常工作。
