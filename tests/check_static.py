"""Basic static smoke checks for the demo HTML page (not a security audit)."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote
import json
import subprocess
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.refs = []
        self.scripts = []
        self.current = None
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for attr in ("src", "href", "poster"):
            if attrs.get(attr):
                self.refs.append(attrs[attr])
        if tag == "script" and not attrs.get("src"):
            self.current = (attrs.get("type", "").lower().strip(), [])
    def handle_data(self, data):
        if self.current is not None:
            self.current[1].append(data)
    def handle_endtag(self, tag):
        if tag == "script" and self.current is not None:
            self.scripts.append((self.current[0], "".join(self.current[1])))
            self.current = None

def main():
    errors = []
    for name in ("index.html",):
        path = ROOT / name
        parser = Page()
        parser.feed(path.read_text(encoding="utf-8"))
        parser.close()
        for ref in set(parser.refs):
            url = urlsplit(ref)
            if url.scheme or url.netloc or not url.path or url.path.startswith("/"):
                continue
            target = (path.parent / unquote(url.path)).resolve()
            if not target.is_relative_to(ROOT) or not target.exists():
                errors.append(f"{name}: missing or out-of-tree local reference: {ref}")
        for number, (kind, source) in enumerate(parser.scripts, 1):
            if kind == "application/ld+json":
                try:
                    json.loads(source)
                except ValueError as exc:
                    errors.append(f"{name}: invalid JSON-LD script {number}: {exc}")
            elif kind in ("", "text/javascript", "application/javascript", "module"):
                with tempfile.TemporaryDirectory() as tmp:
                    js = Path(tmp) / ("check.mjs" if kind == "module" else "check.js")
                    js.write_text(source, encoding="utf-8")
                    result = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
                    if result.returncode:
                        errors.append(f"{name}: JS script {number}: {result.stderr}")
        print(f"Inspected {name}: {len(set(parser.refs))} references, {len(parser.scripts)} inline scripts")
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print("Static smoke checks passed; runtime behavior and security not verified.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
