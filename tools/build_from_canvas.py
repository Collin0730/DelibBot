"""Convert a Design canvas artboard (.dc.html) into this static site.

Usage:
    python tools/build_from_canvas.py path/to/FullUX.dc.html

Writes public/index.html and public/app.js. Rerun it whenever the canvas
version of the mock changes.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"

INDEX = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 28 28%27 fill=%27none%27 stroke=%27%231F5A8C%27 stroke-width=%272.4%27%3E%3Ccircle cx=%2710%27 cy=%2712%27 r=%277%27/%3E%3Ccircle cx=%2718%27 cy=%2716%27 r=%277%27/%3E%3C/svg%3E">
<meta name="description" content="Interactive demo of the Deliberation Partner: an AI coach for participants in citizens' assemblies.">
__HEAD__
<style>
html,body{margin:0}
#app-error{display:none;max-width:640px;margin:40px auto;padding:16px 20px;border:1px solid #E3B4AE;border-radius:10px;background:#FBEBE9;color:#6B1F17;font-family:system-ui,sans-serif}
</style>
</head>
<body>
<div id="app"></div>
<div id="app-error" role="alert"></div>
<noscript><p style="font-family:system-ui,sans-serif;max-width:640px;margin:40px auto">This demo needs JavaScript enabled.</p></noscript>
<template id="dc-template">
__TEMPLATE__
</template>
<script type="module">
import { mount } from './dc-runtime.js';
mount({ templateId: 'dc-template', appSrc: './app.js', target: document.getElementById('app'), props: __PROPS__ })
  .catch((err) => {
    const box = document.getElementById('app-error');
    box.textContent = 'The demo failed to start: ' + err.message;
    box.style.display = 'block';
    console.error(err);
  });
</script>
</body>
</html>
"""


def main(src: str) -> None:
    html = Path(src).read_text(encoding="utf-8")
    title = re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip()
    xdc = re.search(r"<x-dc>(.*)</x-dc>", html, re.S).group(1)
    helmet_match = re.search(r"<helmet>(.*?)</helmet>", xdc, re.S)
    head = helmet_match.group(1).strip() if helmet_match else ""
    template = re.sub(r"<helmet>.*?</helmet>", "", xdc, count=1, flags=re.S).strip()

    script_match = re.search(r"<script type=\"text/x-dc\" data-dc-script data-props='(.*?)'>(.*?)</script>", html, re.S)
    props_spec = json.loads(script_match.group(1).replace("&#39;", "'").replace("&amp;", "&"))
    logic = script_match.group(2).strip()
    props = {k: v["default"] for k, v in props_spec.items() if not k.startswith("$") and isinstance(v, dict) and "default" in v}

    if "</template>" in template:
        raise SystemExit("The markup contains </template>, which would break the page.")

    index = (
        INDEX.replace("__TITLE__", title)
        .replace("__HEAD__", head)
        .replace("__TEMPLATE__", template)
        .replace("__PROPS__", json.dumps(props))
    )
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (PUBLIC / "index.html").write_text(index, encoding="utf-8")
    (PUBLIC / "app.js").write_text(
        "// Generated from the Design canvas by tools/build_from_canvas.py. Edit the canvas, then rebuild.\n"
        + logic
        + "\n\nwindow.__DCComponent = Component;\n",
        encoding="utf-8",
    )
    print(f"Wrote {PUBLIC / 'index.html'} and {PUBLIC / 'app.js'} (props: {props})")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
