#!/usr/bin/env python3
"""Lokální vývoj webové verze bez internetu.

Stáhne Pyodide a xterm.js do web/vendor/ (jen to, co ještě chybí),
sestaví dist/ s lokálními knihovnami a spustí server na localhostu.
Stahuje se jen poprvé (a po změně verze v build.py), pak to jde offline.

    python3 web/dev.py              # http://localhost:8000/
    python3 web/dev.py --port 8080
    python3 web/dev.py --jen-stahnout
"""

import argparse
import functools
import http.server
import sys
import urllib.request

import build


def stahni():
    for balicek, verze, soubory in build.KNIHOVNY.values():
        for f in soubory:
            cil = build.VENDOR / build.adresar(balicek, verze) / f
            if cil.exists():
                continue
            url = f"{build.CDN}/{balicek}@{verze}/{f}"
            print(f"  stahuji {url}")
            cil.parent.mkdir(parents=True, exist_ok=True)
            docasny = cil.with_name(cil.name + ".part")
            with urllib.request.urlopen(url) as odpoved, open(docasny, "wb") as soubor:
                while blok := odpoved.read(1 << 16):
                    soubor.write(blok)
            docasny.rename(cil)


def main():
    parser = argparse.ArgumentParser(description="Lokální vývoj webové verze (bez CDN).")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--jen-stahnout", action="store_true", help="jen stáhnout knihovny do web/vendor/")
    args = parser.parse_args()

    try:
        stahni()
    except OSError as e:
        sys.exit(f"Stažení selhalo ({e}). Napoprvé je potřeba internet.")
    if args.jen_stahnout:
        return
    build.sestav(lokalni=True)

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=build.DIST)
    with http.server.ThreadingHTTPServer(("localhost", args.port), handler) as server:
        print(f"Běží na http://localhost:{args.port}/ (Ctrl+C = konec)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
