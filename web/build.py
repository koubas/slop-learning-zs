#!/usr/bin/env python3
"""Sestaví webové verze aplikací do dist/.

Aplikace je každý adresář <třída>/<název>/ se souborem web.json. Do
dist/<třída>/<název>/ se zkopírují její .py soubory a vygeneruje se
index.html s terminálem xterm.js. Python běží v prohlížeči přes Pyodide.

    python3 web/build.py             # produkce: knihovny z CDN
    python3 web/build.py --lokalni   # knihovny z web/vendor/ (stáhne web/dev.py)
    python3 -m http.server -d dist
"""

import argparse
import html
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "web" / "runtime"
DIST = ROOT / "dist"
VENDOR = ROOT / "web" / "vendor"

CDN = "https://cdn.jsdelivr.net/npm"
# zástupný symbol -> (npm balíček, verze, soubory potřebné pro lokální běh)
KNIHOVNY = {
    "__PYODIDE__": (
        "pyodide",
        "314.0.7",
        ["pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"],
    ),
    "__XTERM__": ("@xterm/xterm", "6.0.0", ["lib/xterm.js", "css/xterm.css"]),
    "__XTERM_FIT__": ("@xterm/addon-fit", "0.11.0", ["lib/addon-fit.js"]),
}


def adresar(balicek, verze):
    """Relativní cesta knihovny ve vendor/ (stejná ve web/vendor i dist/vendor)."""
    return f"{balicek}@{verze}"

STRANKA_APLIKACE = """<!doctype html>
<html lang="cs">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{nazev}</title>
<link rel="icon" href="data:,">
<link rel="stylesheet" href="__XTERM__css/xterm.css" crossorigin>
<style>
  html, body {{ margin: 0; height: 100%; background: #111111; }}
  #term {{ position: absolute; inset: 0; padding: 8px; box-sizing: border-box; }}
</style>
</head>
<body>
<div id="term"></div>
<script type="application/json" id="app">{konfigurace}</script>
<script src="__XTERM__lib/xterm.js" crossorigin></script>
<script src="__XTERM_FIT__lib/addon-fit.js" crossorigin></script>
<script type="module" src="{root}runtime/main.js"></script>
</body>
</html>
"""

ROZCESTNIK = """<!doctype html>
<html lang="cs">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Procvičování pro ZŠ</title>
<link rel="icon" href="data:,">
<style>
  :root {{ color-scheme: light dark; --bg: #ffffff; --fg: #1a1a1a; --muted: #666666; --link: #0b5fff; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #111111; --fg: #eeeeee; --muted: #999999; --link: #7aa7ff; }}
  }}
  body {{ margin: 0 auto; max-width: 40rem; padding: 2rem 1rem; background: var(--bg); color: var(--fg);
         font: 1.1rem/1.5 system-ui, sans-serif; }}
  h2 {{ margin-top: 2rem; }}
  a {{ color: var(--link); }}
  .popis {{ color: var(--muted); }}
</style>
</head>
<body>
<h1>Procvičování pro ZŠ</h1>
<p class="popis">Aplikace na procvičování učiva ZŠ.</p>
{obsah}
</body>
</html>
"""


def dosad(text, lokalni, root):
    """Nahradí zástupné symboly knihoven adresou na CDN, nebo ve vendor/ (relativně k root)."""
    for symbol, (balicek, verze, _) in KNIHOVNY.items():
        zaklad = f"{root}vendor/{adresar(balicek, verze)}/" if lokalni else f"{CDN}/{balicek}@{verze}/"
        text = text.replace(symbol, zaklad)
    return text


def najdi_aplikace():
    for web_json in sorted(ROOT.glob("*/*/web.json")):
        trida = web_json.parent.parent.name
        if trida.isdigit():
            yield trida, web_json.parent, json.loads(web_json.read_text(encoding="utf-8"))


def sestav_aplikaci(trida, zdroj, konfigurace, lokalni):
    cil = DIST / trida / zdroj.name
    cil.mkdir(parents=True)
    soubory = sorted(p.name for p in zdroj.glob("*.py"))
    for f in soubory:
        shutil.copy2(zdroj / f, cil / f)
    data = {**konfigurace, "id": f"{trida}/{zdroj.name}", "root": "../../", "soubory": soubory}
    # </ v JSON uvnitř <script> by ukončilo tag
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    stranka = STRANKA_APLIKACE.format(
        nazev=html.escape(konfigurace["nazev"]), root="../../", konfigurace=data_json
    )
    (cil / "index.html").write_text(dosad(stranka, lokalni, "../../"), encoding="utf-8")


def zkopiruj_knihovny():
    for balicek, verze, soubory in KNIHOVNY.values():
        for f in soubory:
            zdroj = VENDOR / adresar(balicek, verze) / f
            if not zdroj.exists():
                raise SystemExit(f"Chybí {zdroj.relative_to(ROOT)}, spusť python3 web/dev.py")
            cil = DIST / "vendor" / adresar(balicek, verze) / f
            cil.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(zdroj, cil)


def sestav(lokalni=False):
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "runtime").mkdir(parents=True)
    if lokalni:
        zkopiruj_knihovny()
    for f in sorted(p for p in RUNTIME.iterdir() if p.is_file()):
        # sw.js musí být v kořeni, aby jeho scope pokryl všechny aplikace
        cil, root = (DIST / "sw.js", "") if f.name == "sw.js" else (DIST / "runtime" / f.name, "../")
        cil.write_text(dosad(f.read_text(encoding="utf-8"), lokalni, root), encoding="utf-8")

    podle_tridy = {}
    for trida, zdroj, konfigurace in najdi_aplikace():
        sestav_aplikaci(trida, zdroj, konfigurace, lokalni)
        podle_tridy.setdefault(trida, []).append((zdroj.name, konfigurace))
        print(f"  {trida}/{zdroj.name}")

    obsah = []
    for trida in sorted(podle_tridy, key=int):
        obsah.append(f"<h2>{trida}. třída</h2>\n<ul>")
        for nazev, k in podle_tridy[trida]:
            obsah.append(
                f'<li><a href="{trida}/{nazev}/">{html.escape(k["nazev"])}</a>'
                f' <span class="popis">{html.escape(k.get("popis", ""))}</span></li>'
            )
        obsah.append("</ul>")
    (DIST / "index.html").write_text(ROZCESTNIK.format(obsah="\n".join(obsah)), encoding="utf-8")
    print(f"Hotovo ({'lokální knihovny' if lokalni else 'CDN'}): {DIST}")


def main():
    parser = argparse.ArgumentParser(description="Sestaví webové verze aplikací do dist/.")
    parser.add_argument("--lokalni", action="store_true", help="knihovny z web/vendor/ místo CDN")
    sestav(parser.parse_args().lokalni)


if __name__ == "__main__":
    main()
