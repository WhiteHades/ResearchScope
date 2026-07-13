#!/usr/bin/env python3
"""Verify the three-theme interface: switching + persistence across navigation.

Drives a headless Chrome over the DevTools Protocol against the static `site/`
build. Clicking the real switcher menu items exercises the switch handlers;
navigating between pages (no ?theme= param) verifies the choice persists via
localStorage and that theme-bootstrap.js commits it before first paint.

Requires: Google Chrome and the `websocket-client` package (pip install
websocket-client). No external browser download needed.

Usage:  python3 scripts/theme-persistence-test.py
Exits 0 if all checks pass, 1 otherwise.
"""
import base64
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request

try:
    import websocket  # websocket-client
except ImportError:
    sys.exit("websocket-client is required: pip install websocket-client")

PORT = int(os.environ.get("RS_TEST_PORT", "8795"))
DEVTOOLS_PORT = int(os.environ.get("RS_DEVTOOLS_PORT", "9333"))
BASE = f"http://127.0.0.1:{PORT}"
STORAGE_KEY = "researchscope-theme"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(REPO, "site")

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    shutil.which("google-chrome"),
    shutil.which("google-chrome-stable"),
    shutil.which("chromium"),
    shutil.which("chromium-browser"),
]


def find_chrome():
    for c in CHROME_CANDIDATES:
        if c and os.path.exists(c):
            return c
    sys.exit("Could not find a Chrome/Chromium binary")


def wait_port(check, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            check()
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("timed out waiting for service")


class Chrome:
    def __init__(self, binary, profile):
        self.proc = subprocess.Popen(
            [binary, "--headless=new", "--disable-gpu",
             f"--remote-debugging-port={DEVTOOLS_PORT}",
             f"--user-data-dir={profile}", "--no-first-run",
             "--no-default-browser-check", "--remote-allow-origins=*",
             "--window-size=1440,1000"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_port(lambda: urllib.request.urlopen(
            f"http://127.0.0.1:{DEVTOOLS_PORT}/json/version", timeout=1))
        targets = json.load(urllib.request.urlopen(
            f"http://127.0.0.1:{DEVTOOLS_PORT}/json/list"))
        page = next(t for t in targets
                    if t.get("type") == "page" and t.get("webSocketDebuggerUrl"))
        self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], max_size=None)
        self._id = 0
        self.cmd("Page.enable")
        self.cmd("Runtime.enable")

    def cmd(self, method, params=None):
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def ev(self, expr):
        r = self.cmd("Runtime.evaluate", {
            "expression": "(function(){%s})()" % expr,
            "returnByValue": True, "awaitPromise": True})
        return r.get("result", {}).get("value")

    def goto(self, url):
        self.cmd("Page.navigate", {"url": url})
        for _ in range(150):
            try:
                if self.ev("return document.readyState==='complete' "
                           "&& !!document.getElementById('rs-theme-switcher')"):
                    self.ev("return new Promise(r=>setTimeout(r,150))")
                    return
            except Exception:
                pass
            time.sleep(0.1)
        raise RuntimeError(f"page never became ready: {url}")

    def reload(self):
        self.cmd("Page.reload")
        for _ in range(150):
            if self.ev("return document.readyState==='complete' "
                       "&& !!document.getElementById('rs-theme-switcher')"):
                self.ev("return new Promise(r=>setTimeout(r,150))")
                return
            time.sleep(0.1)

    def pick_theme(self, pattern):
        """Open the switcher menu and click the item matching `pattern`."""
        self.ev("return document.querySelector('.rs-theme-button').click()")
        self.ev("return new Promise(r=>setTimeout(r,200))")
        sel = ("#rs-theme-menu button, #rs-theme-menu [role=menuitemradio], "
               "#rs-theme-menu [role=menuitem], #rs-theme-menu [data-theme]")
        res = self.ev(
            "var items=[].slice.call(document.querySelectorAll(%r));"
            "var el=items.find(function(e){return %s.test(e.textContent||'')});"
            "if(!el)return 'NOTFOUND';el.click();return 'clicked'" % (sel, pattern))
        self.ev("return new Promise(r=>setTimeout(r,400))")
        return res

    def theme(self):  return self.ev("return document.documentElement.dataset.rsTheme")
    def stored(self): return self.ev(f"return localStorage.getItem('{STORAGE_KEY}')")

    def close(self):
        try:
            self.ws.close()
        finally:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()


def main():
    binary = find_chrome()
    profile = tempfile.mkdtemp(prefix="rs-theme-prof-")
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1",
         "--directory", SITE],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    failures = []

    def check(label, actual, expected):
        ok = actual == expected
        print(f"  {'PASS' if ok else 'FAIL'}  {label}: {actual!r}"
              + ("" if ok else f" (expected {expected!r})"))
        if not ok:
            failures.append(label)

    try:
        wait_port(lambda: urllib.request.urlopen(BASE + "/index.html", timeout=1))
        chrome = Chrome(binary, profile)
        try:
            print("1) Fresh load defaults to Atelier Zero")
            chrome.goto(BASE + "/index.html")
            check("home theme", chrome.theme(), "atelier")

            print("2) Switcher menu -> Field Notes")
            check("menu click", chrome.pick_theme("/field/i"), "clicked")
            check("theme applied", chrome.theme(), "field-notes")
            check("theme persisted", chrome.stored(), "field-notes")

            print("3) Navigate home -> papers (no ?theme=) keeps Field Notes")
            href = chrome.ev("var a=[].slice.call(document.querySelectorAll('a'))"
                             ".find(function(a){return /papers/.test(a.getAttribute('href')||'')});"
                             "return a?a.href:null")
            chrome.goto(href)
            check("papers theme", chrome.theme(), "field-notes")
            check("bootstrap set before paint",
                  chrome.ev("return window.ResearchScopeInitialTheme"), "field-notes")

            print("4) Full reload keeps Field Notes")
            chrome.reload()
            check("reload theme", chrome.theme(), "field-notes")

            print("5) Switch to Industrial Brutalist, navigate to topics")
            check("menu click", chrome.pick_theme("/industrial|brutal/i"), "clicked")
            check("theme applied", chrome.theme(), "brutalist")
            chrome.goto(BASE + "/topics/")
            check("topics theme", chrome.theme(), "brutalist")
        finally:
            chrome.close()
    finally:
        server.send_signal(signal.SIGTERM)
        shutil.rmtree(profile, ignore_errors=True)

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s): {', '.join(failures)}")
        return 1
    print("OK: all theme switch + persistence checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
