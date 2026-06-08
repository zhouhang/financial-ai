# Site Filing Layout Design

## Goal

Move the ICP filing number so it remains visible without covering the left sidebar user/status
area in the main Tally application.

The filing number is:

```text
鄂ICP备2026028755号-1
```

It should keep linking to:

```text
https://beian.miit.gov.cn/
```

## Problem

The current implementation places `SiteFiling` as an absolutely positioned full-width bottom bar
inside the app shell. The main content gets bottom padding, but `Sidebar` remains `h-screen`.
As a result, the filing bar overlays the sidebar's bottom user/status controls.

## Confirmed Direction

Use layout option A from the visual review:

- Main app: show the filing number at the bottom of the right-side content area only.
- Public recon exception pages: keep the current full-page bottom filing placement.
- `/handoff`: keep the current full-page bottom filing placement.

## Non-Goals

- Do not change the filing number text or MIIT link.
- Do not redesign the sidebar footer or user menu.
- Do not change public recon or handoff page visual structure except preserving their existing
  filing placement.
- Do not add a floating filing badge.

## Main App Layout

Change the main app shell from "one full-width shell with a bottom filing bar" to a two-column
layout:

```text
+----------------------+--------------------------------------+
| Sidebar              | Right content column                 |
| h-screen             | +----------------------------------+ |
| no filing overlap    | | Chat / Recon / Data Connections  | |
|                      | | min-h-0 flex-1 overflow-hidden   | |
| user/status intact   | +----------------------------------+ |
|                      | | SiteFiling, 28px, shrink-0       | |
+----------------------+--------------------------------------+
```

Implementation shape:

- Keep `Sidebar` as a direct sibling of the right content column.
- Add a right-side app column such as `site-main-column`.
- Put the active panel (`ChatArea`, `ReconWorkspace`, or `DataConnectionsPanel`) inside a
  `min-h-0 flex-1 overflow-hidden` container.
- Put `<SiteFiling />` at the bottom of that right column with `shrink-0`.
- Remove the main app's full-width absolute filing bar.

This keeps the sidebar independent and preserves its full viewport height.

## Public And Handoff Pages

For routes without the main sidebar:

- `PublicReconRunExceptionsPage` keeps the existing full-page bottom filing bar.
- `/handoff` keeps the existing full-page bottom filing bar.

These pages do not have the left sidebar collision, so the current placement is acceptable.

## Styling

Use restrained legal/footer styling:

- Height around `28px`.
- Small text, muted color.
- Link inherits color, underlines on hover.
- No decorative pill or floating card treatment.

The main app filing should look like a footer for the right content column, not a global overlay.

## Testing

Automated:

- Keep the `SiteFiling` component test verifying the text and MIIT link attributes.
- Add or update a focused layout test if practical to assert that main app rendering places
  `SiteFiling` inside the right content area, not after the full app shell.

Build:

- Run `npm run build` in `finance-web`.

Manual:

- Open the main app and confirm the sidebar bottom user/status area is not covered.
- Collapse the sidebar and confirm the filing remains aligned to the right content area.
- Open a public recon exception URL and confirm the filing remains full-page bottom centered.
- Open `/handoff` and confirm the filing remains full-page bottom centered.
