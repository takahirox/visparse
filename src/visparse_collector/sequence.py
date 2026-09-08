"""Bounded explicit interaction plans; no discovery or recovery policy."""
from __future__ import annotations
import asyncio
import hashlib
import time
from pathlib import Path
from urllib.parse import urldefrag
from visparse.contracts import bounded, check, items, number, shape, text
from visparse.interaction import ACTIONS, validate_sequence
from visparse.model import ValidationError
from .browser import validate_url


def validate_plan(plan):
    bounded(plan)
    shape(plan, {"schema_version", "url", "allowed_navigation", "viewport", "steps", "parameters", "timeout_ms", "action_timeout_ms", "max_artifact_bytes"})
    check(plan["schema_version"] == "interaction-plan/0.1", "unsupported plan version")
    validate_url(plan["url"])
    check(len(items(plan["allowed_navigation"])) <= 10, "too many navigation URLs")
    for url in plan["allowed_navigation"]:
        validate_url(url)
    check(len(items(plan["viewport"])) == 2, "viewport requires two dimensions")
    for dimension in plan["viewport"]:
        check(type(dimension) is int and 1 <= dimension <= 4096, "invalid viewport")
    number(plan["timeout_ms"], 100, 120000)
    number(plan["action_timeout_ms"], 50, min(10000, plan["timeout_ms"]))
    check(type(plan["max_artifact_bytes"]) is int and 1 <= plan["max_artifact_bytes"] <= 20000000, "invalid artifact budget")
    check(isinstance(plan["parameters"], dict) and len(plan["parameters"]) <= 20, "invalid parameters")
    for key, value in plan["parameters"].items():
        check(key.startswith(("fixture:", "redacted:")), "parameter requires fixture/redacted reference")
        text(value); check(len(value) <= 1000, "parameter too long")
    check(1 <= len(items(plan["steps"])) <= 20, "expected 1..20 steps")
    for step in plan["steps"]:
        shape(step, {"kind", "selector", "input_ref", "key", "delta", "wait_ms", "sample_ms"})
        check(step["kind"] in ACTIONS, "unsupported action")
        targeted = step["kind"] in {"click", "fill", "press", "hover", "focus"}
        if targeted:
            text(step["selector"]); check(len(step["selector"]) <= 500, "selector too long")
        else:
            check(step["selector"] is None, "non-targeted action cannot have selector")
        if step["kind"] == "fill":
            check(step["input_ref"] in plan["parameters"], "unknown fill parameter")
        else:
            check(step["input_ref"] is None, "only fill accepts parameter")
        if step["kind"] == "press":
            check(step["key"] in {"Tab", "Shift+Tab", "Enter", "Escape", "Space", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"}, "unsupported key")
        else:
            check(step["key"] is None, "key only applies to press")
        check(len(items(step["delta"])) == 2, "scroll delta requires two values")
        for delta in step["delta"]:
            number(delta, -4096, 4096)
        check(step["kind"] == "scroll" or step["delta"] == [0, 0], "scroll delta on non-scroll action")
        number(step["wait_ms"], 0, 5000)
        check(step["kind"] == "wait" or step["wait_ms"] == 0, "wait_ms only applies to wait")
        check(len(items(step["sample_ms"])) <= 3, "at most three feedback samples")
        for delay in step["sample_ms"]:
            number(delay, 0, 2000)
    return plan


DOM = """() => ({nodes: Array.from(document.querySelectorAll('body *')).slice(0,200).map(e => ({
 tag:e.tagName, id:e.id, role:e.getAttribute('role'), text: ['INPUT','TEXTAREA','SELECT'].includes(e.tagName)||e.isContentEditable ? '[redacted]' : Array.from(e.childNodes).filter(n=>n.nodeType===3).map(n=>n.textContent).join('').slice(0,160),
 hidden: !e.getClientRects().length, expanded:e.getAttribute('aria-expanded'), selected:e.getAttribute('aria-selected'), checked:e.getAttribute('aria-checked'), pressed:e.getAttribute('aria-pressed'),
 valid:e.matches('input,textarea,select') ? e.validity.valid : null,
 css:{display:getComputedStyle(e).display, visibility:getComputedStyle(e).visibility},
 box:{x:e.getBoundingClientRect().x,y:e.getBoundingClientRect().y,width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height}
 })), focus:document.activeElement?.id || document.activeElement?.tagName, scroll:[scrollX,scrollY], total_nodes:document.querySelectorAll('body *').length})"""


def _redact(value, parameters):
    if isinstance(value, str):
        for private in parameters.values():
            value = value.replace(private, "[redacted]")
        return value
    if isinstance(value, list):
        return [_redact(v, parameters) for v in value]
    if isinstance(value, dict):
        return {k: _redact(v, parameters) for k, v in value.items()}
    return value


async def _record(plan, directory):
    try:
        from playwright.async_api import async_playwright, TimeoutError as BrowserTimeout, Error as BrowserError
    except ImportError:
        raise ValidationError("install visparse[collector] and Playwright Chromium") from None
    start = time.monotonic()
    now = lambda: (time.monotonic() - start) * 1000
    base = {"session_id": "session", "clock_id": "clock"}
    bundle = {"schema_version": "interaction-sequence/0.2", "sessions": [{"id": "session", "reset": "fresh browser context; empty cookies and storage; reload retains same context", "viewport": plan["viewport"], "input_modality": "pointer-keyboard", "origin": plan["url"]}],
              "clocks": [{"id": "clock", "session_id": "session", "unit": "ms", "basis": "collector monotonic", "method": "time.monotonic around non-atomic reads"}],
              "captures": [], "targets": [], "actions": [], "expectations": [],
              "coverage": {"scope": "explicit supplied plan only", "omissions": ["Frames, shadow DOM, Canvas/WebGL semantics and unsampled transients unavailable", "DOM limited to 200 nodes; AX depth 3; input values redacted", "Screenshots, DOM and AX are sequential non-atomic observations"]}}
    artifacts = {}
    allowed = {urldefrag(validate_url(u))[0] for u in [plan["url"]] + plan["allowed_navigation"]}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(timeout=plan["timeout_ms"])
        try:
            context = await browser.new_context(viewport=dict(zip(("width", "height"), plan["viewport"])), accept_downloads=False, service_workers="block")
            try:
                page = await context.new_page()
                page.set_default_timeout(plan["action_timeout_ms"])
                blocked = []
                request_count = 0

                async def route_handler(route):
                    nonlocal request_count
                    request_count += 1
                    request = route.request
                    if request_count > 200 or (request.is_navigation_request() and (request.frame != page.main_frame or urldefrag(request.url)[0] not in allowed)):
                        blocked.append("navigation/request outside declared scope or request budget")
                        await route.abort()
                    else:
                        await route.continue_()
                await context.route("**/*", route_handler)
                async def popup(p):
                    blocked.append("popup outside single-page scope")
                    await p.close()
                page.on("popup", popup)
                async def download(d):
                    blocked.append("download outside capture scope")
                    await d.cancel()
                page.on("download", download)
                client = await context.new_cdp_session(page)

                async def snapshot():
                    ids = []
                    for kind in ("dom", "screenshot", "accessibility"):
                        t0 = now(); artifact = None
                        if kind == "dom":
                            data = await page.evaluate(DOM)
                            data.update(browser_version=browser.version, wait_until="domcontentloaded", atomic_snapshot=False)
                        elif kind == "screenshot":
                            masks = [page.locator("input,textarea,select,[contenteditable]")]
                            masks += [page.get_by_text(v, exact=False) for v in plan["parameters"].values()]
                            raw = await page.screenshot(type="png", mask=masks)
                            digest = hashlib.sha256(raw).hexdigest()
                            check(sum(len(v) for v in artifacts.values()) + (0 if digest in artifacts else len(raw)) <= plan["max_artifact_bytes"], "artifact budget exhausted")
                            artifacts[digest] = raw
                            artifact = {"sha256": digest, "media_type": "image/png"}
                            data = {"viewport": plan["viewport"]}
                        else:
                            tree = await client.send("Accessibility.getFullAXTree", {"depth": 3})
                            data = {"nodes": [{"id": n["nodeId"], "role": n.get("role", {}).get("value"), "name": n.get("name", {}).get("value"), "properties": [p for p in n.get("properties", []) if p["name"] in {"focused", "focusable", "disabled", "expanded", "selected", "checked"}]} for n in tree["nodes"][:200]], "truncated": len(tree["nodes"]) > 200}
                        cid = f"capture-{len(bundle['captures'])}"
                        bundle["captures"].append(dict(base, id=cid, start_ms=t0, end_ms=now(), kind=kind, artifact=artifact, data=_redact(data, plan["parameters"]), omissions=["non-atomic sampled evidence"]))
                        ids.append(cid)
                    return ids

                async def run():
                    await page.goto(plan["url"], wait_until="domcontentloaded")
                    if blocked:
                        return
                    for i, step in enumerate(plan["steps"]):
                        before = await snapshot()
                        target_id = None
                        if step["selector"] is not None:
                            target_id = f"target-{i}"
                            bundle["targets"].append({"id": target_id, "session_id": "session", "capture_ids": before, "locator": step["selector"]})
                        t0 = now()
                        action = dict(base, id=f"action-{i}", start_ms=t0, end_ms=t0, order=i, kind=step["kind"], target_id=target_id, input_ref=step["input_ref"], before=before, feedback=[], after=[], outcome="unobserved", reason="post-state not collected")
                        action["input_parameters"] = {"key": step["key"]} if step["kind"] == "press" else {"delta": step["delta"]} if step["kind"] == "scroll" else {"wait_ms": step["wait_ms"]} if step["kind"] == "wait" else {}
                        bundle["actions"].append(action)
                        try:
                            locator = page.locator(step["selector"]) if target_id else None
                            if locator is not None and await locator.count() != 1:
                                action.update(outcome="failed-action", reason="selector did not resolve to exactly one target")
                                break
                            kind = step["kind"]
                            if kind in {"click", "hover", "focus"}: await getattr(locator, kind)()
                            elif kind == "fill": await locator.fill(plan["parameters"][step["input_ref"]])
                            elif kind == "press": await locator.press(step["key"])
                            elif kind == "scroll": await page.evaluate("d => scrollBy(d[0],d[1])", step["delta"])
                            elif kind == "wait": await asyncio.sleep(step["wait_ms"] / 1000)
                            elif kind == "reload": await page.reload(wait_until="domcontentloaded")
                            action["end_ms"] = now()
                            if urldefrag(page.url)[0] not in allowed: blocked.append("same-document navigation outside declared scope")
                            if blocked:
                                action.update(outcome="failed-action", reason=blocked[0]); break
                            for delay in step["sample_ms"]:
                                await asyncio.sleep(delay / 1000)
                                action["feedback"].extend(await snapshot())
                            action["after"] = await snapshot()
                            a = next(c for c in bundle["captures"] if c["id"] == before[0])["data"]
                            b = next(c for c in bundle["captures"] if c["id"] == action["after"][0])["data"]
                            action.update(outcome="observed-no-change" if a == b else "observed-effect", reason="comparison of sampled redacted DOM/focus/scroll; hidden state and backend result unknown")
                        except BrowserTimeout:
                            action.update(outcome="collection-timeout", reason="action or observation deadline; application outcome unknown")
                            break
                        except (BrowserError, ValidationError):
                            action.update(outcome="failed-action" if blocked else "unobserved", reason=blocked[0] if blocked else "capture/execution unavailable; inspect coverage")
                            break
                        finally:
                            # Completion time excludes post-action observation intervals.
                            if action["end_ms"] == t0: action["end_ms"] = now()
                try:
                    await asyncio.wait_for(run(), timeout=max(.001, (plan["timeout_ms"] - now()) / 1000))
                except (asyncio.TimeoutError, BrowserTimeout):
                    bundle["coverage"]["omissions"].append("total collection deadline reached; remaining plan not executed")
                    if bundle["actions"]:
                        action = bundle["actions"][-1]
                        if action["outcome"] == "unobserved": action.update(outcome="collection-timeout", reason="total collection deadline")
                except BrowserError:
                    bundle["coverage"]["omissions"].append("browser evidence unavailable")
                bundle["coverage"]["omissions"].extend(blocked)
                if len(bundle["actions"]) < len(plan["steps"]): bundle["coverage"]["omissions"].append("remaining plan not executed")
            finally:
                await context.close()
        finally:
            await browser.close()
    validate_sequence(bundle)
    directory.mkdir(parents=True, exist_ok=True)
    for digest, raw in artifacts.items():
        path = directory / f"{digest}.png"
        try:
            with path.open("xb") as stream: stream.write(raw)
        except FileExistsError:
            check(not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == digest, "artifact collision")
    return bundle


def capture_sequence(plan, artifact_directory):
    validate_plan(plan)  # no imports, browser or filesystem effects before preflight
    return asyncio.run(_record(plan, Path(artifact_directory)))
