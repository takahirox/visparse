"""Explicit-URL Playwright collector with bounded artifacts and total timeout."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from visparse.collector_contract import validate_capture_payload
from visparse.contracts import bounded, check, number
from visparse.inspection import validate_inspection
from visparse.model import ValidationError

STYLES = ["font-family", "font-size", "font-weight", "line-height", "letter-spacing", "color", "background-color",
          "border-top-left-radius", "border-top-width", "border-right-width", "border-bottom-width", "border-left-width",
          "border-color", "box-shadow", "opacity", "display", "position", "padding", "margin", "gap", "row-gap", "column-gap",
          "width", "height", "max-width", "min-width"]


@dataclass(frozen=True)
class CaptureOptions:
    viewports: tuple[tuple[int, int], ...] = ((1440, 900), (390, 844))
    timeout_seconds: float = 30
    max_nodes: int = 40
    max_scan: int = 5000
    max_requests: int = 200
    max_artifact_bytes: int = 5_000_000
    wait_until: str = "load"
    full_page: bool = False

    def validate(self):
        check(0 < len(self.viewports) <= 5, "expected 1–5 viewports")
        check(len(set(self.viewports)) == len(self.viewports), "duplicate viewport")
        for width, height in self.viewports:
            for value in (width, height):
                check(type(value) is int and 1 <= value <= 4096, "viewport dimensions must be integers in 1..4096")
        number(self.timeout_seconds, 1, 300)
        for value, maximum in ((self.max_nodes, 200), (self.max_scan, 50_000), (self.max_requests, 2000), (self.max_artifact_bytes, 20_000_000)):
            check(type(value) is int and 1 <= value <= maximum, "invalid collector limit")
        check(self.wait_until in {"load", "domcontentloaded", "networkidle"}, "invalid wait strategy")


def validate_url(url: str) -> str:
    parsed = urlsplit(url)
    check(parsed.scheme in {"http", "https"} and bool(parsed.hostname), "capture requires an explicit HTTP(S) URL")
    check(parsed.username is None and parsed.password is None, "credential-bearing URLs are not accepted")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, parsed.fragment))


async def _capture(url: str, directory: Path, options: CaptureOptions) -> dict:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise ValidationError('install visparse[collector] and run playwright install chromium') from None
    inventory = Path(__file__).with_name("inventory.js").read_text(encoding="utf-8")
    session_id = uuid.uuid4().hex
    captures = []
    pending_artifacts = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            for index, (width, height) in enumerate(options.viewports, 1):
                context = await browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1,
                                                    accept_downloads=False, service_workers="block")
                try:
                    page = await context.new_page()
                    requests = 0
                    blocked = 0

                    async def route_request(route):
                        nonlocal requests, blocked
                        requests += 1
                        request = route.request
                        permitted = urlsplit(request.url).scheme in {"http", "https"} and requests <= options.max_requests
                        if request.is_navigation_request():
                            permitted = permitted and request.frame == page.main_frame and request.url.split("#")[0] == url.split("#")[0]
                        if permitted:
                            await route.continue_()
                        else:
                            blocked += 1
                            await route.abort()

                    await context.route("**/*", route_request)
                    await page.add_init_script("window.__visparseMutationCount = 0; new MutationObserver(() => window.__visparseMutationCount++).observe(document, {subtree:true, childList:true, attributes:true, characterData:true});")
                    page.set_default_timeout(options.timeout_seconds * 1000)
                    await page.goto(url, wait_until=options.wait_until)
                    data = await page.evaluate(inventory, {"maxNodes": options.max_nodes, "maxScan": options.max_scan, "styles": STYLES})
                    # Mask form/editable values in screenshots as well as omitting them from JSON.
                    screenshot = await page.screenshot(type="png", full_page=options.full_page,
                        mask=[page.locator("input,textarea,select,[contenteditable]")])
                    check(len(screenshot) <= options.max_artifact_bytes, "screenshot exceeds artifact byte limit")
                    after = await page.evaluate("window.__visparseMutationCount || 0")
                    digest = hashlib.sha256(screenshot).hexdigest()
                    pending_artifacts.append((digest, screenshot))
                    viewport = f"{width}x{height}"
                    shot_id, dom_id = f"screenshot-{index}", f"dom-{index}"
                    payload = {"collector_schema_version": "0.1", "context": {"session_id": session_id, "viewport": viewport,
                        "state": "default", "scroll_x": data["scroll_x"], "scroll_y": data["scroll_y"], "device_pixel_ratio": 1,
                        "screenshot_id": shot_id}, "nodes": data["nodes"], "coverage": data["coverage"], "css_variables": data["css_variables"],
                        "metadata": {"url": url, "title": (await page.title())[:240], "captured_at": datetime.now(timezone.utc).isoformat(),
                        "browser_version": browser.version, "collector_version": "0.1", "playwright_version": importlib.metadata.version("playwright"),
                        "wait_until": options.wait_until, "coordinate_space": "viewport CSS pixels", "blocked_requests": blocked,
                        "mutations_between_inventory_and_screenshot": after - data["mutation_count"], "atomic_snapshot": False}}
                    if options.full_page:
                        payload["coverage"]["omissions"].append("Full-page screenshot covers more than the viewport-scoped DOM sample.")
                    validate_capture_payload(payload)
                    captures.extend([
                        {"id": shot_id, "kind": "screenshot", "locator": f"artifact:sha256:{digest}", "payload": {
                            "sha256": digest, "artifact_file": f"{digest}.png", "viewport": viewport, "session_id": session_id,
                            "viewport_width": width, "viewport_height": height, "device_pixel_ratio": 1, "full_page": options.full_page}},
                        {"id": dom_id, "kind": "dom", "locator": f"collector:{session_id}:{viewport}", "payload": payload},
                    ])
                    # CDP supplies actual computed AX properties. Limit the retained
                    # inventory and omit value fields, including password values.
                    client = await context.new_cdp_session(page)
                    ax = await client.send("Accessibility.getFullAXTree", {"depth": 3})
                    ax_nodes = []
                    for node in ax["nodes"][:options.max_nodes]:
                        role = node.get("role", {}).get("value", "")
                        ax_nodes.append({"id": node["nodeId"], "role": str(role)[:160], "name": str(node.get("name", {}).get("value", ""))[:160],
                            "ignored": node.get("ignored", False), "properties": [
                                {"name": p["name"], "value": p.get("value", {}).get("value")}
                                for p in node.get("properties", []) if p["name"] in {"focusable", "disabled", "expanded", "selected", "checked"}]})
                    captures.append({"id": f"accessibility-{index}", "kind": "accessibility", "locator": f"collector:{session_id}:{viewport}:ax",
                        "payload": {"session_id": session_id, "viewport": viewport, "nodes": ax_nodes, "depth_limit": 3,
                        "truncated": len(ax["nodes"]) > len(ax_nodes), "node_identity": "CDP AX IDs; no DOM cross-link asserted"}})
                finally:
                    await context.close()
        finally:
            await browser.close()
    bundle = {"schema_version": "0.1", "captures": captures, "measurements": [], "runtime_observations": [],
        "visual_observations": [], "interpretations": [], "confidence": [],
        "provenance": {"created_by": "visparse-collector/0.1", "inputs": [c["id"] for c in captures]}}
    bounded(validate_inspection(bundle))
    directory.mkdir(parents=True, exist_ok=True)
    for digest, content in pending_artifacts:
        path = directory / f"{digest}.png"
        try:
            with path.open("xb") as stream:
                stream.write(content)
        except FileExistsError:
            check(not path.is_symlink() and path.is_file() and path.stat().st_size == len(content)
                  and hashlib.sha256(path.read_bytes()).hexdigest() == digest, "artifact path collision")
    return bundle


def capture(url: str, directory: str | Path, options: CaptureOptions | None = None) -> dict:
    """Capture only the supplied URL. Redirect navigation requires a new explicit URL."""
    url = validate_url(url)
    options = options or CaptureOptions()
    options.validate()

    async def run():
        try:
            return await asyncio.wait_for(_capture(url, Path(directory), options), timeout=options.timeout_seconds)
        except asyncio.TimeoutError:
            raise ValidationError("collector total timeout exceeded") from None
    return asyncio.run(run())
