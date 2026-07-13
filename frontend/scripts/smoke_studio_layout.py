#!/usr/bin/env python3
"""Smoke: fullscreen prompt studio + exit to cabinet."""
from __future__ import annotations

import json
import sys
import time

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8080"


def main() -> int:
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(f"{BASE}/app", wait_until="domcontentloaded")
        time.sleep(1)
        if page.locator("#email").count():
            page.fill("#email", "demo@onestack.dev")
            page.fill("#password", "demo1234")
            page.click("#btn-login")
            time.sleep(2)

        after_login = page.evaluate(
            """() => ({
              dash: !document.querySelector('#tab-dash')?.classList.contains('hidden'),
              focus: document.body.classList.contains('studio-focus'),
            })"""
        )
        if not after_login.get("dash") or after_login.get("focus"):
            errors.append(f"login should open dash, got {after_login}")

        page.click('[data-tab="projects"]')
        time.sleep(1.2)
        info = page.evaluate(
            """() => {
              const shell = document.querySelector('#zc-work-shell');
              const cols = shell ? getComputedStyle(shell).gridTemplateColumns.split(' ').filter(Boolean).length : 0;
              return {
                panes: document.querySelectorAll('.agent-pane').length,
                hero: !!document.querySelector('.ap-hero'),
                rail_hidden: document.querySelector('#zc-rail')?.classList.contains('hidden'),
                preview_hidden: document.querySelector('#zc-preview-dock')?.classList.contains('hidden'),
                exit: !!document.querySelector('#btn-studio-exit'),
                top_hidden: getComputedStyle(document.querySelector('.top')).display === 'none',
                cols,
                agents_ui: document.querySelectorAll('[data-ap-agents],[data-agents-n]').length,
              };
            }"""
        )
        print(json.dumps(info, ensure_ascii=False, indent=2))
        for k, v in {
            "panes": 1,
            "hero": True,
            "rail_hidden": True,
            "preview_hidden": True,
            "exit": True,
            "top_hidden": True,
            "cols": 1,
            "agents_ui": 0,
        }.items():
            if info.get(k) != v:
                errors.append(f"{k}: expected {v}, got {info.get(k)}")

        page.click("#btn-studio-exit")
        time.sleep(0.6)
        back = page.evaluate(
            """() => ({
              dash: !document.querySelector('#tab-dash')?.classList.contains('hidden'),
              focus: document.body.classList.contains('studio-focus'),
              side: getComputedStyle(document.querySelector('.side')).display !== 'none',
            })"""
        )
        if not (back.get("dash") and not back.get("focus") and back.get("side")):
            errors.append(f"exit broken: {back}")

        browser.close()

    if errors:
        print("FAIL:")
        for e in errors:
            print("-", e)
        return 1
    print("OK clean studio smoke")
    return 0


if __name__ == "__main__":
    sys.exit(main())
