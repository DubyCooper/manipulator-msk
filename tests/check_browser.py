"""Offline Chromium smoke tests for the current static demo, not a production audit."""
from datetime import date, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]

def scenario(page):
    page.locator("#truck").select_option("3")
    page.locator("#hours").fill("1")
    page.locator("#inside").fill("10")
    page.locator("#outside").fill("5")
    page.locator("#tolls").fill("0")
    def total():
        return int("".join(c for c in page.locator("#total").inner_text() if c.isdigit()))
    assert total() == 10950
    page.locator("#night").check()
    assert total() == 12550
    page.locator("#addstop").click()
    page.locator(".stopaddress").fill("Test stop")
    assert total() == 13550
    page.get_by_role("button", name="Удалить остановку").click()
    assert total() == 12550
    page.locator("#weight").fill("4000")
    expect(page.locator("#warning")).to_contain_text("Вес превышает")
    page.locator("#route").click()
    expect(page.locator("#status")).to_contain_text("Укажите адреса")

def main():
    # Bind to loopback only. Test the checked-out files, never a live site.
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(ROOT)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for label, viewport in (("desktop", {"width": 1440, "height": 900}),
                                    ("mobile viewport", {"width": 390, "height": 844})):
                context = browser.new_context(viewport=viewport, service_workers="block")
                page = context.new_page()
                errors = []
                failed_local = []
                unexpected = []
                def route_request(route):
                    url = urlsplit(route.request.url)
                    if f"{url.scheme}://{url.netloc}" == origin and route.request.method in ("GET", "HEAD"):
                        route.continue_()
                    else:
                        if route.request.method not in ("GET", "HEAD"):
                            unexpected.append(route.request.method)
                        route.abort()
                context.route("**/*", route_request)
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("response", lambda response: failed_local.append(response.status)
                        if response.url.startswith(origin + "/") and response.status >= 400
                        and not response.url.endswith("/favicon.ico") else None)
                try:
                    response = page.goto(origin + "/index.html", wait_until="load")
                    assert response and response.ok
                    expect(page.locator("h1").first).to_be_visible()
                    scenario(page)
                    assert not errors, errors
                    assert not failed_local, failed_local
                    assert not unexpected, unexpected
                    print(f"PASS: {label}")
                finally:
                    context.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

if __name__ == "__main__":
    main()
