"""Capture recruiter-facing screenshots from a hosted ModelForge deployment."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default=os.getenv("MODELFORGE_PUBLIC_URL", ""),
    )
    parser.add_argument(
        "--api-key-env",
        default="MODELFORGE_API_KEY",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evidence"),
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    if not base_url.startswith("https://"):
        parser.error("--base-url must be the HTTPS hosted ModelForge URL.")

    api_key = os.getenv(args.api_key_env, "").strip()
    if not api_key:
        parser.error(
            f"{args.api_key_env} must contain a ModelForge workspace API key."
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1600, "height": 1000},
            device_scale_factor=1,
            extra_http_headers={
                "Authorization": f"Bearer {api_key}",
            },
        )
        page = context.new_page()

        page.goto(base_url + "/", wait_until="networkidle")
        page.screenshot(
            path=args.output_dir / "landing-page.png",
            full_page=True,
        )

        page.goto(base_url + "/dashboard", wait_until="networkidle")
        page.wait_for_function(
            """
            () => {
              const count = document.getElementById("models-count");
              return count && count.textContent !== "—";
            }
            """,
            timeout=20000,
        )
        page.screenshot(
            path=args.output_dir / "saas-console.png",
            full_page=True,
        )

        manifest = {
            "landing_page": "landing-page.png",
            "saas_console": "saas-console.png",
            "dashboard_url": base_url + "/dashboard",
            "workspace": page.locator("#workspace-subtitle").inner_text(),
            "models": page.locator("#models-count").inner_text(),
            "deployments": page.locator("#deployments-count").inner_text(),
            "canaries": page.locator("#canaries-count").inner_text(),
            "runtimes": page.locator("#runtimes-count").inner_text(),
        }
        (args.output_dir / "screenshots.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
