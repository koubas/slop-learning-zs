"""Spouštěč aplikace v prohlížeči (běží v Pyodide ve Web Workeru).

Zeptá se na hodnotu argumentu podle web.json (např. jméno žáka), spustí
aplikaci jako __main__ a po jejím skončení pošle datové soubory
z pracovního adresáře do localStorage. Pak nabídne nové spuštění.
"""

import codecs
import json
import os
import runpy
import sys
import time
import traceback

import js

APP = json.loads(js.appConfig)
ENTER = (10, 13)
BACKSPACE = (8, 127, 263)

# time.sleep ve workeru přes Atomics.wait, aby opravdu blokoval a nevytěžoval CPU
time.sleep = lambda s: js.sleepMs(max(0, int(s * 1000)))


def napis(text):
    sys.stdout.flush()
    js.writeOut(text)


def cekej_enter():
    js.flushInput()
    while js.readKey(-1) not in ENTER:
        pass


def nacti_radek(vychozi):
    dekoder = codecs.getincrementaldecoder("utf-8")("ignore")
    text = ""
    while True:
        k = js.readKey(-1)
        if k in ENTER:
            napis("\r\n")
            return text.strip() or vychozi
        if k in BACKSPACE:
            if text:
                text = text[:-1]
                napis("\b \b")
        elif 32 <= k < 256 and k != 127:
            znak = dekoder.decode(bytes([k]))
            if znak and znak not in "/\\":
                text += znak
                napis(znak)


def existujici(vzor):
    predpona, pripona = vzor.split("{}")
    return sorted(
        f[len(predpona) : len(f) - len(pripona)]
        for f in os.listdir(".")
        if f.startswith(predpona) and f.endswith(pripona) and len(f) > len(predpona) + len(pripona)
    )


def argumenty():
    dotaz = APP.get("dotaz")
    if not dotaz:
        return []
    if "data" in dotaz:
        znami = existujici(dotaz["data"])
        napis(f"{dotaz.get('seznam', 'Uložené')}:\r\n")
        for jmeno in znami:
            napis(f"  \x1b[36m{jmeno}\x1b[0m\r\n")
        if not znami:
            napis(f"  \x1b[2m({dotaz.get('prazdny', 'zatím žádné')})\x1b[0m\r\n")
        napis("\r\n")
    napis(f"{dotaz['text']} [{dotaz['vychozi']}]: ")
    return [dotaz["argument"], nacti_radek(dotaz["vychozi"])]


def uloz_data():
    zdrojove = set(APP["soubory"])
    data = {}
    for f in os.listdir("."):
        if f in zdrojove or not os.path.isfile(f):
            continue
        try:
            with open(f, encoding="utf-8") as soubor:
                data[f] = soubor.read()
        except UnicodeDecodeError:
            pass
    js.saveFiles(json.dumps(data))


def spust():
    os.environ.setdefault("LANG", "C.UTF-8")
    while True:
        napis(f"\x1b[1m{APP['nazev']}\x1b[0m\r\n\r\n")
        sys.argv = [APP["spoustec"], *argumenty()]
        try:
            runpy.run_path(APP["spoustec"], run_name="__main__")
        except SystemExit:
            pass
        except BaseException:
            traceback.print_exc()
        uloz_data()
        napis("\r\n\x1b[2mKonec. Stiskni Enter pro nové spuštění.\x1b[0m\r\n")
        cekej_enter()
        napis("\x1b[2J\x1b[H")
