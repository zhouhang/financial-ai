---
phase: 01
slug: wizard-foundation
status: approved
shadcn_initialized: false
preset: none
created: 2026-04-22
---

# Phase 01 — UI Design Contract

> Visual and interaction contract for the new reconciliation-scheme wizard shell.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none |
| Preset | not applicable |
| Component library | none |
| Icon library | lucide-react |
| Font | system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif |

---

## Spacing Scale

Declared values (must be multiples of 4):

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Inline icon gaps, status dots |
| sm | 8px | Compact label-to-value spacing |
| md | 16px | Default control spacing, form stack gaps |
| lg | 24px | Section padding inside cards |
| xl | 32px | Gaps between wizard sections |
| 2xl | 48px | Large modal section separation |
| 3xl | 64px | Rare page-level vertical spacing |

Exceptions: modal outer shell may continue using existing `rounded-[28px]` / `px-6 py-5` geometry from `ReconWorkspace`

---

## Typography

| Role | Size | Weight | Line Height |
|------|------|--------|-------------|
| Body | 14px | 400 | 1.6 |
| Label | 12px | 500 | 1.4 |
| Heading | 16px | 600 | 1.4 |
| Display | 20px | 600 | 1.3 |

Rules:
- Step titles, section titles and summary card titles use Heading.
- Form helper text, state hints and dataset subtitles use Label or Body, never uppercase technical jargon blocks.
- JSON panel remains monospaced; business-facing forms and summaries stay in sans-serif.

---

## Color

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `#ffffff` / dark `#132033` | Primary surfaces, modal body, editable cards |
| Secondary (30%) | `#f5f7fb` / dark `#091321` | Secondary panels, step shells, summary groups |
| Accent (10%) | `#0284c7` / dark `#39b6cc` | Active step, primary CTA, focus ring, progress emphasis |
| Destructive | `#ef4444` / dark `#f87171` | Delete, destructive confirmation, hard failure only |

Accent reserved for:
- Primary action buttons such as `下一步` and `保存方案`
- Active wizard step badge
- Focus-visible ring and selected chips
- Non-destructive progress emphasis

Never use accent for:
- Large background fills
- Passive metadata chips
- Secondary/cancel buttons

---

## Layout Contract

- Wizard remains a modal inside `ReconWorkspace`, max width stays in the current large-modal range; do not move Phase 1 to a standalone page.
- The top area has three layers only: eyebrow, title, step badges. Avoid adding dense status rows above the fold.
- Step badges must communicate `current`, `completed`, `upcoming` clearly without horizontal overflow on laptop widths.
- Step 1 is a concise business intent form. It must fit comfortably in one viewport without requiring the user to scan through data-source controls.
- Step 4 is a summary and gate screen, not a second editing canvas. It should show business goal, Step 2 data-preparation snapshot, Step 3 recon-rule snapshot, and trial pass/fail status.
- When upstream edits invalidate downstream work, show clear warning banners inline in the relevant step body instead of top-of-modal hidden notices.

---

## Interaction Contract

- Step transitions preserve already-entered draft state unless an explicit invalidation rule clears derived artifacts.
- User-edited business text is always the visible source of truth. Do not show a rendered summary that diverges from the editable text.
- Derived artifacts such as generated JSON, compatibility checks and trial samples can show `待生成` / `待试跑` / `仅供参考` / `已通过`, but must never appear current when the underlying step has changed.
- If a downstream step becomes stale, keep the last output visible only as reference and mark it clearly as stale.
- Validation and error feedback must appear next to the step body or action area the user is working in, not only at modal top.
- Dark mode must preserve contrast for primary CTA and focus states; no white CTA on white/light surface.

---

## Copywriting Contract

| Element | Copy |
|---------|------|
| Primary CTA | `下一步` / `保存方案` |
| Empty state heading | `先补充方案目标，再进入数据准备` |
| Empty state body | `填写方案名称和对账目的后，系统再带你配置左右数据与后续试跑。` |
| Error state | `当前步骤还没完成，请先处理提示项后继续。` |
| Destructive confirmation | `关闭创建向导`：`当前未保存的方案草稿将丢失，确认关闭吗？` |

Copy rules:
- Prefer finance language: `方案目标`、`数据准备`、`对账规则`、`确认保存`
- Avoid default technical copy such as `proc` / `recon` / `validator` in visible section headings
- Technical terms can appear only in advanced JSON view or debug-level error detail

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none | not required |
| third-party registry | none | not required |

---

## Checker Sign-Off

- [x] Dimension 1 Copywriting: PASS
- [x] Dimension 2 Visuals: PASS
- [x] Dimension 3 Color: PASS
- [x] Dimension 4 Typography: PASS
- [x] Dimension 5 Spacing: PASS
- [x] Dimension 6 Registry Safety: PASS

**Approval:** approved 2026-04-22
