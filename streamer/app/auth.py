"""Programmatic ui.com login.

Used only when the persistent profile has no valid session — once the
streamer has logged in once, cookies persist across container restarts
because the profile lives on a docker volume.

If the user's account requires MFA, the script will not be able to
complete login automatically. In that case the operator runs the
streamer one-time with `STREAMER_BOOTSTRAP_ONLY=true` and
`STREAMER_HEADLESS=false`, attaches via VNC or SSH-X to complete the
MFA prompt, then re-deploys with bootstrap_only=false.
"""
from __future__ import annotations

import asyncio
import logging

from playwright.async_api import Page

log = logging.getLogger("streamer.auth")

LOGIN_PROBE_URL = "https://unifi.ui.com/"
LOGIN_FORM_URL  = "https://account.ui.com/login"


async def is_logged_in(page: Page) -> bool:
    """We're logged in iff visiting unifi.ui.com lands us on the Site
    Manager page (URL stays under unifi.ui.com) rather than redirecting
    to account.ui.com/login."""
    try:
        await page.goto(LOGIN_PROBE_URL, wait_until="domcontentloaded", timeout=20_000)
    except Exception as e:
        log.warning("probe nav failed: %s", e)
        return False
    await asyncio.sleep(2)
    url = page.url
    return url.startswith("https://unifi.ui.com/") and "login" not in url


async def login(page: Page, email: str, password: str) -> bool:
    """Attempt programmatic login. Returns True on success."""
    log.info("attempting programmatic login as %s", email)
    try:
        await page.goto(LOGIN_FORM_URL, wait_until="domcontentloaded", timeout=20_000)
    except Exception as e:
        log.error("could not load login page: %s", e)
        return False

    # Account UI can vary. Try several selectors in turn.
    email_selectors = [
        'input[type="email"]',
        'input[name="username"]',
        'input[name="email"]',
        'input[autocomplete="username"]',
    ]
    password_selectors = [
        'input[type="password"]',
        'input[name="password"]',
        'input[autocomplete="current-password"]',
    ]

    async def fill_first(selectors: list[str], value: str) -> bool:
        for sel in selectors:
            el = await page.query_selector(sel)
            if el:
                await el.fill(value)
                return True
        return False

    if not await fill_first(email_selectors, email):
        log.error("email input not found on login page")
        return False
    if not await fill_first(password_selectors, password):
        log.error("password input not found on login page")
        return False

    submit = await page.query_selector('button[type="submit"]')
    if submit:
        await submit.click()
    else:
        await page.keyboard.press("Enter")

    # Wait up to 20s for either redirect to unifi.ui.com or an MFA prompt.
    for _ in range(20):
        await asyncio.sleep(1)
        url = page.url
        if url.startswith("https://unifi.ui.com/") and "login" not in url:
            log.info("login OK")
            return True
        if "mfa" in url.lower() or "two-factor" in url.lower():
            log.error("MFA challenge — automated login can't complete; "
                      "run with STREAMER_BOOTSTRAP_ONLY=true + STREAMER_HEADLESS=false "
                      "and complete MFA interactively, then re-deploy")
            return False
    log.error("login did not complete; final url=%s", page.url)
    return False
