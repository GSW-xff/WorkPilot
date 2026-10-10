from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlparse

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from pydantic import BaseModel, Field

from workpilot.context import detect_prompt_injection
from workpilot.knowledge import ObjectStore


class BrowserPolicyError(ValueError):
    pass


class BrowserAction(BaseModel):
    type: Literal["click", "fill", "select", "scroll"]
    selector: str | None = None
    value: str | None = Field(default=None, max_length=2_000)
    expected_text: str | None = Field(default=None, max_length=500)


class BrowserObservation(BaseModel):
    sequence: int
    url: str
    title: str
    body_text: str
    dom_evidence_key: str
    dom_sha256: str
    screenshot_evidence_key: str
    screenshot_sha256: str
    controls: list[dict[str, str]]
    trust: Literal["untrusted"] = "untrusted"
    injection_markers: list[str] = Field(default_factory=list)


class BrowserActionEvidence(BaseModel):
    action: BrowserAction
    before: BrowserObservation
    after: BrowserObservation
    verified: bool


@dataclass(frozen=True, slots=True)
class BrowserPolicy:
    allowed_origins: frozenset[str]
    allow_downloads: bool = False
    allow_uploads: bool = False
    max_actions: int = 30
    selector_pattern: re.Pattern[str] = field(
        default=re.compile(r'^(#[A-Za-z][\w:-]*|\[data-testid="[\w:-]+"\])$'),
        repr=False,
    )

    def validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self.allowed_origins:
            raise BrowserPolicyError(f"origin is not allowlisted: {origin}")

    def validate_action(self, action: BrowserAction) -> None:
        if action.type in {"click", "fill", "select"}:
            if not action.selector or not self.selector_pattern.fullmatch(action.selector):
                raise BrowserPolicyError("selector must be a stable id or data-testid")
        if action.type in {"fill", "select"} and action.value is None:
            raise BrowserPolicyError(f"{action.type} requires a value")


class PlaywrightBrowserAdapter:
    """Evidence-first browser channel restricted to an explicit test origin."""

    def __init__(self, policy: BrowserPolicy, evidence_store: ObjectStore, run_id: str) -> None:
        self.policy = policy
        self.evidence_store = evidence_store
        self.run_id = run_id
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._sequence = 0
        self._actions = 0
        self._download_attempted = False
        self._dialog_attempted = False

    async def __aenter__(self) -> PlaywrightBrowserAdapter:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._context = await self._browser.new_context(accept_downloads=False)
        await self._context.route("**/*", self._route)
        self._page = await self._context.new_page()
        self._page.on("download", lambda _download: setattr(self, "_download_attempted", True))
        self._page.on("dialog", self._dismiss_dialog)
        return self

    async def __aexit__(self, *_args) -> None:
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()

    async def navigate(self, url: str) -> BrowserObservation:
        self.policy.validate_url(url)
        page = self._require_page()
        await page.goto(url, wait_until="domcontentloaded")
        return await self.observe()

    async def act(self, action: BrowserAction) -> BrowserActionEvidence:
        self.policy.validate_action(action)
        if self._actions >= self.policy.max_actions:
            raise BrowserPolicyError("browser action budget exceeded")
        self._actions += 1
        page = self._require_page()
        self.policy.validate_url(page.url)
        before = await self.observe()
        if action.type == "click":
            assert action.selector is not None
            await page.locator(action.selector).click()
        elif action.type == "fill":
            assert action.selector is not None and action.value is not None
            await page.locator(action.selector).fill(action.value)
        elif action.type == "select":
            assert action.selector is not None and action.value is not None
            await page.locator(action.selector).select_option(action.value)
        else:
            amount = int(action.value or "600")
            if abs(amount) > 2_000:
                raise BrowserPolicyError("scroll distance exceeds policy")
            await page.evaluate("amount => window.scrollBy(0, amount)", amount)
        await page.wait_for_timeout(50)
        if self._download_attempted and not self.policy.allow_downloads:
            raise BrowserPolicyError("downloads are blocked")
        if self._dialog_attempted:
            raise BrowserPolicyError("page dialogs are blocked")
        after = await self.observe()
        verified = action.expected_text is None or action.expected_text in after.body_text
        if not verified:
            raise BrowserPolicyError("expected UI state was not observed after action")
        return BrowserActionEvidence(action=action, before=before, after=after, verified=verified)

    async def observe(self) -> BrowserObservation:
        page = self._require_page()
        self.policy.validate_url(page.url)
        self._sequence += 1
        body_text = (await page.locator("body").inner_text())[:20_000]
        html = (await page.locator("html").evaluate("node => node.outerHTML")).encode()
        screenshot = await page.screenshot(full_page=True)
        controls = await page.locator("button,input,select,textarea,a").evaluate_all(
            "elements => elements.slice(0, 100).map(element => ({"
            "tag: element.tagName.toLowerCase(), "
            "id: element.id || element.getAttribute('data-testid') || '', "
            "label: element.innerText || element.getAttribute('aria-label') || ''}))"
        )
        prefix = f"browser/{self.run_id}/{self._sequence:04d}"
        dom_key = f"{prefix}.html"
        screenshot_key = f"{prefix}.png"
        self.evidence_store.put(dom_key, html)
        self.evidence_store.put(screenshot_key, screenshot)
        return BrowserObservation(
            sequence=self._sequence,
            url=page.url,
            title=await page.title(),
            body_text=body_text,
            dom_evidence_key=dom_key,
            dom_sha256=hashlib.sha256(html).hexdigest(),
            screenshot_evidence_key=screenshot_key,
            screenshot_sha256=hashlib.sha256(screenshot).hexdigest(),
            controls=json.loads(json.dumps(controls)),
            injection_markers=detect_prompt_injection(body_text),
        )

    async def _route(self, route) -> None:
        url = route.request.url
        if url == "about:blank":
            await route.continue_()
            return
        try:
            self.policy.validate_url(url)
        except BrowserPolicyError:
            await route.abort("blockedbyclient")
        else:
            await route.continue_()

    async def _dismiss_dialog(self, dialog) -> None:
        self._dialog_attempted = True
        await dialog.dismiss()

    def _require_page(self) -> Page:
        if self._page is None:
            raise RuntimeError("browser adapter is not started")
        return self._page
