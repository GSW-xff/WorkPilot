# Policy-bound Browser Adapter

`PlaywrightBrowserAdapter` is an optional last-mile channel for a self-hosted sandbox site.
It is not a general web-browsing agent. Every navigation and subresource must match an
explicit origin allowlist; only stable `#id` and `data-testid` selectors are accepted.
Actions are limited to click, fill, select and bounded scroll. Downloads, uploads, dialogs,
unknown origins and action-budget overflow fail closed.

Before and after every action the adapter stores full-page PNG and HTML evidence with
SHA-256 digests, plus URL, title, visible text and a compact control inventory. Success is
based on an expected UI-state observation, not merely a successful Playwright command.
All page text is labelled untrusted and prompt-injection markers remain evidence only.

Run the real browser test with:

```bash
uv run playwright install chromium
WORKPILOT_RUN_BROWSER_INTEGRATION=1 uv run pytest tests/test_browser_adapter.py
```
