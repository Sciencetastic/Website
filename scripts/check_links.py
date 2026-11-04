"""Fail if any local href/src in the static sites points to a missing file."""
import re, sys, pathlib
from urllib.parse import urlparse

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "sites").resolve()
bad = []
for page in root.rglob("*.html"):
    text = page.read_text(encoding="utf-8")
    for ref in re.findall(r'(?:href|src)="([^"]+)"', text) + re.findall(r'url\("([^"]+)"\)', text):
        u = urlparse(ref)
        if u.scheme or ref.startswith(("#", "mailto:", "data:")):
            continue
        path = u.path
        target = (root / path.lstrip("/")) if path.startswith("/") else (page.parent / path)
        if target.is_dir() or path.endswith("/"):
            target = target / "index.html"
        if not target.resolve().exists():
            bad.append(f"{page.relative_to(root)}: {ref}")
for css in root.rglob("*.css"):
    for ref in re.findall(r'url\("([^"]+)"\)', css.read_text()):
        if not ref.startswith("data:") and not (css.parent / ref).resolve().exists():
            bad.append(f"{css.relative_to(root)}: {ref}")
print("\n".join(bad) or f"OK: all local links resolve under {root}")
sys.exit(1 if bad else 0)
