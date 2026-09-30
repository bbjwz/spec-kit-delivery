from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .models import Assertion, Scenario
from .storage import inside


def assert_values(observed: dict, assertions: list[Assertion]) -> list[dict]:
    results = []
    for assertion in assertions:
        value = observed
        exists = True
        for component in assertion.field.split("."):
            if isinstance(value, dict) and component in value:
                value = value[component]
            elif isinstance(value, list) and component.isdigit() and int(component) < len(value):
                value = value[int(component)]
            else:
                exists = False
                value = None
                break
        if assertion.operator == "exists":
            passed = exists and assertion.value is True
        elif assertion.operator == "equals":
            passed = exists and type(value) is type(assertion.value) and value == assertion.value
        else:
            passed = exists and isinstance(value, (str, list, dict)) and assertion.value in value
        results.append({"assertion": assertion.model_dump(), "observed": value, "passed": passed})
    return results


def clean_environment() -> dict[str, str]:
    # Commands never inherit GitHub/provider credentials. Project fixtures needing
    # authentication must use synthetic local identities in v1.
    return {
        k: v
        for k, v in os.environ.items()
        if k
        in {
            "PATH",
            "HOME",
            "LANG",
            "LC_ALL",
            "TMPDIR",
            "SYSTEMROOT",
            "VIRTUAL_ENV",
            "PLAYWRIGHT_BROWSERS_PATH",
            "PYTHONPATH",
        }
    }


def command(argv: list[str], root: Path, timeout: int) -> dict:
    with subprocess.Popen(
        argv,
        cwd=root,
        env=clean_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    ) as proc:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate()
            return {"exit_code": -1, "stdout": stdout, "stderr": stderr, "timeout": True}
    return {"exit_code": proc.returncode, "stdout": stdout, "stderr": stderr, "timeout": False}


def checked_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username:
        raise ValueError("scenario URL must be HTTP(S) without embedded credentials")
    return url


def execute(scenario: Scenario, root: Path, output: Path) -> tuple[dict, list[dict]]:
    if scenario.kind == "cli":
        observed = command(scenario.command, root, scenario.timeout_seconds)
    elif scenario.kind == "api":
        response = httpx.request(
            scenario.method,
            checked_url(scenario.url),
            json=scenario.body,
            timeout=scenario.timeout_seconds,
            follow_redirects=False,
        )
        observed = {"status": response.status_code, "text": response.text}
        try:
            observed["json"] = response.json()
        except ValueError:
            observed["json"] = None
    elif scenario.kind == "inspection":
        path = inside(root, scenario.file)
        observed = {"exists": path.is_file(), "text": path.read_text() if path.is_file() else ""}
    else:
        return browser(scenario, output)
    return observed, assert_values(observed, scenario.assertions)


def browser(scenario: Scenario, output: Path) -> tuple[dict, list[dict]]:
    from playwright.sync_api import expect, sync_playwright

    results = []
    observed = {"steps": []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        context.set_default_timeout(scenario.timeout_seconds * 1000)
        context.tracing.start(screenshots=True, snapshots=True, sources=False)
        page = context.new_page()
        try:
            for step in scenario.steps:
                if step.action == "goto":
                    page.goto(checked_url(step.target), wait_until="domcontentloaded")
                elif step.action == "click":
                    page.locator(step.target).click()
                elif step.action == "fill":
                    page.locator(step.target).fill(step.value)
                elif step.action == "assert_text":
                    expect(page.locator(step.target)).to_have_text(step.value)
                    results.append({"assertion": step.model_dump(), "passed": True})
                elif step.action == "assert_visible":
                    expect(page.locator(step.target)).to_be_visible()
                    results.append({"assertion": step.model_dump(), "passed": True})
                observed["steps"].append(step.model_dump())
        except Exception as exc:
            # Exception text may contain application content; evidence stays private.
            results.append({"passed": False, "error": str(exc)})
        finally:
            try:
                page.screenshot(path=str(output / "screenshot.png"), full_page=True)
            finally:
                context.tracing.stop(path=str(output / "trace.zip"))
                browser.close()
    return observed, results
