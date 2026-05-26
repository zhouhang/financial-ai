# Playbook JSON Editor Tolerance Design

Date: 2026-05-22

## Context

Operators paste browser playbook JSON into the registration dialog. JSON copied from chat often contains real newlines or tabs inside quoted selector strings, for example a selector split across two lines. Native `JSON.parse` rejects this with `Bad control character in string literal`, and the existing textarea has no line numbers, so the user cannot quickly locate the problem.

## Design

Add a small parser helper for browser playbook JSON input:

- First try strict `JSON.parse`.
- If it fails, scan the text character by character and normalize only control characters found inside quoted JSON strings.
- Inside strings:
  - `\n` and `\r` are removed when adjacent to CJK characters, so split words like `历史下载记\n录` become `历史下载记录`.
  - `\n` and `\r` otherwise become one space, so split CSS selector lists remain readable.
  - `\t` becomes one space.
  - Other unescaped control characters become a safe space.
- Parse the normalized text. If it succeeds, submit the normalized object and show a non-blocking warning with the number of fixes.
- If it still fails, show the parse message with `第 X 行，第 Y 列` when the browser error includes line/column data.

Add a lightweight line-number gutter next to the playbook textarea:

- Keep the existing textarea to avoid introducing a heavy editor dependency.
- Render line numbers in a left gutter and sync gutter scroll with the textarea.
- Use stable monospace sizing so line numbers and JSON text align.

## Non-Goals

- Do not rewrite arbitrary malformed JSON.
- Do not auto-correct invalid action names or selector semantics.
- Do not add Monaco or CodeMirror.
- Do not change backend registration contracts.

## Validation

- Unit-test parser strict success, control-character repair, CJK newline joining, tab normalization, and line/column formatting.
- Run the finance-web build.
