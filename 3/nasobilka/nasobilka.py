#!/usr/bin/env python3
"""Procvičování násobilky do 10 v terminálu.

Ovládání (celé obsluhuje učitel, žák jen odpovídá nahlas): učitel přečte
příklad a stiskne Enter (spustí čas), jakmile žák řekne výsledek, učitel ho
napíše a potvrdí Enterem. Dvakrát Esc = konec a uložení stavu.

Plánování: každý příklad má interval v počtu příkladů, po kterém přijde znovu.
Chyba interval vrátí na INTERVAL_CHYBA, správná odpověď ho vynásobí podle
toho, jak moc příklad vypadá „zapamatovaný“. To se odhaduje směsí dvou
normálních rozdělení (GMM) na logaritmu času do první napsané číslice
(≈ okamžik, kdy žák odpověď vyslovil):
rychlá složka = vybavuje si z paměti, pomalá = počítá.
"""

import argparse
import curses
import json
import locale
import math
import os
import random
import statistics
import time

INTERVAL_CHYBA = 3
INTERVAL_MAX = 1000
ALFA = 0.4  # váha nové odpovědi v klouzavém průměru skóre
HISTORIE_MAX = 100  # z kolika posledních správných časů se fituje GMM
MIN_FIT = 20
REFIT_KAZDYCH = 20
MIN_ROZPTYL = 0.01  # v log prostoru
MIN_ODSTUP = 0.3  # minimální rozdíl středů v log prostoru (~35 %), jinak jen jeden shluk


def vychozi_priklad():
    return {
        "interval": INTERVAL_CHYBA,
        "na_rade": 0,
        "skore": None,
        "pokusy": 0,
        "spravne": 0,
        "chyby": 0,
        "casy": [],
    }


def nacti_stav(soubor):
    stav = {
        "pocitadlo": 0,
        "historie": [],
        "priklady": {f"{a}x{b}": vychozi_priklad() for a in range(1, 11) for b in range(1, 11)},
    }
    if os.path.exists(soubor):
        with open(soubor, encoding="utf-8") as f:
            ulozeny = json.load(f)
        stav["pocitadlo"] = ulozeny.get("pocitadlo", 0)
        stav["historie"] = ulozeny.get("historie", [])
        for klic, data in ulozeny.get("priklady", {}).items():
            if klic in stav["priklady"]:
                zaznam = stav["priklady"][klic]
                zaznam.update({k: v for k, v in data.items() if k in zaznam})
    return stav


def uloz_stav(stav, soubor):
    with open(soubor, "w", encoding="utf-8") as f:
        json.dump(stav, f, ensure_ascii=False, indent=2)


def _hustota(x, mu, var):
    return math.exp(-((x - mu) ** 2) / (2 * var)) / math.sqrt(2 * math.pi * var)


def fituj_gmm(casy):
    """EM pro směs dvou normálních rozdělení na log(čas).

    Vrací (vahy, stredy, rozptyly) s rychlou složkou na indexu 0, nebo None,
    pokud je dat málo nebo se nedají rozdělit na dva odlišné shluky.
    """
    if len(casy) < MIN_FIT:
        return None
    x = [math.log(max(t, 0.05)) for t in casy]
    s = sorted(x)
    mu = [s[len(s) // 4], s[3 * len(s) // 4]]
    var = [max(statistics.pvariance(x), MIN_ROZPTYL)] * 2
    w = [0.5, 0.5]
    for _ in range(100):
        r = []
        for xi in x:
            p0 = w[0] * _hustota(xi, mu[0], var[0])
            p1 = w[1] * _hustota(xi, mu[1], var[1])
            r.append(p0 / (p0 + p1) if p0 + p1 > 0 else 0.5)
        n0 = sum(r)
        n1 = len(x) - n0
        if n0 < 1 or n1 < 1:
            return None
        mu = [
            sum(ri * xi for ri, xi in zip(r, x)) / n0,
            sum((1 - ri) * xi for ri, xi in zip(r, x)) / n1,
        ]
        var = [
            max(sum(ri * (xi - mu[0]) ** 2 for ri, xi in zip(r, x)) / n0, MIN_ROZPTYL),
            max(sum((1 - ri) * (xi - mu[1]) ** 2 for ri, xi in zip(r, x)) / n1, MIN_ROZPTYL),
        ]
        w = [n0 / len(x), n1 / len(x)]
    if mu[0] > mu[1]:
        w, mu, var = w[::-1], mu[::-1], var[::-1]
    if mu[1] - mu[0] < MIN_ODSTUP:
        return None
    return w, mu, var


def p_pameti(model, cas):
    """Pravděpodobnost, že odpověď byla vybavená z paměti (rychlý shluk)."""
    if model is None:
        # bez modelu: logistická křivka kolem 3 s
        return 1 / (1 + math.exp((cas - 3.0) / 0.7))
    w, mu, var = model
    # ořez na rozsah středů, aby širší složka nepřebrala extrémní hodnoty
    x = min(max(math.log(max(cas, 0.05)), mu[0]), mu[1])
    p0 = w[0] * _hustota(x, mu[0], var[0])
    p1 = w[1] * _hustota(x, mu[1], var[1])
    return p0 / (p0 + p1)


def vyber_priklad(stav, posledni):
    """Nejdéle čekající příklad, který je na řadě; jinak nový; jinak nejbližší."""
    n = stav["pocitadlo"]
    priklady = {k: v for k, v in stav["priklady"].items() if k != posledni}
    na_rade = [k for k, v in priklady.items() if v["pokusy"] and v["na_rade"] <= n]
    if na_rade:
        nejdriv = min(priklady[k]["na_rade"] for k in na_rade)
        return random.choice([k for k in na_rade if priklady[k]["na_rade"] == nejdriv])
    nove = [k for k, v in priklady.items() if not v["pokusy"]]
    if nove:
        return random.choice(nove)
    return min(priklady, key=lambda k: (priklady[k]["na_rade"], random.random()))


def aktualizuj(stav, klic, spravne, cas, model):
    zaznam = stav["priklady"][klic]
    stav["pocitadlo"] += 1
    zaznam["pokusy"] += 1
    p = 0.0
    if spravne:
        zaznam["spravne"] += 1
        zaznam["casy"] = (zaznam["casy"] + [round(cas, 2)])[-10:]
        stav["historie"] = (stav["historie"] + [round(cas, 2)])[-HISTORIE_MAX:]
        p = p_pameti(model, cas)
    else:
        zaznam["chyby"] += 1
    zaznam["skore"] = round(p if zaznam["skore"] is None else (1 - ALFA) * zaznam["skore"] + ALFA * p, 3)
    if spravne:
        novy = round(zaznam["interval"] * (1.2 + 1.8 * zaznam["skore"]))
        zaznam["interval"] = min(INTERVAL_MAX, max(INTERVAL_CHYBA, novy))
    else:
        zaznam["interval"] = INTERVAL_CHYBA
    zaznam["na_rade"] = stav["pocitadlo"] + zaznam["interval"]


def tabulka(stav):
    """Textová tabulka 10×10 se skóre zapamatování (ANSI barvy)."""
    radky = ["   × " + "".join(f"{b:>5}" for b in range(1, 11))]
    for a in range(1, 11):
        bunky = []
        for b in range(1, 11):
            z = stav["priklady"][f"{a}x{b}"]
            if z["spravne"] < 2 or z["skore"] is None:
                bunky.append("\033[2m   --\033[0m")
                continue
            barva = 32 if z["skore"] >= 0.7 else 33 if z["skore"] >= 0.4 else 31
            bunky.append(f"\033[{barva}m{round(z['skore'] * 100):>4}%\033[0m")
        radky.append(f"{a:>4} " + "".join(bunky))
    return "\n".join(radky)


def _median(hodnoty):
    return statistics.median(hodnoty) if hodnoty else None


def _fmt(hodnota, vzor, prazdne="--"):
    return prazdne if hodnota is None else vzor.format(hodnota)


def _souhrn(zaznamy):
    pokusy = sum(z["pokusy"] for z in zaznamy)
    spravne = sum(z["spravne"] for z in zaznamy)
    skore = [z["skore"] for z in zaznamy if z["skore"] is not None]
    return {
        "pocet": len(zaznamy),
        "pokusy": pokusy,
        "uspesnost": spravne / pokusy if pokusy else None,
        "median": _median([t for z in zaznamy for t in z["casy"]]),
        "skore": sum(skore) / len(skore) if skore else None,
        "zvladnuto": sum(1 for z in zaznamy if z["spravne"] >= 2 and (z["skore"] or 0) >= 0.7),
    }


def _radek_souhrnu(nazev, s, sirka=22):
    return (
        f"{nazev:<{sirka}}{s['pocet']:>5}{s['pokusy']:>8}"
        f"{_fmt(s['uspesnost'], '{:.0%}'):>10}{_fmt(s['median'], '{:.1f} s'):>9}"
        f"{_fmt(s['skore'], '{:.0%}'):>8}{s['zvladnuto']:>6}/{s['pocet']:<3}"
    )


def hranice_gmm(model):
    """Čas, kde je P(paměť) = 0.5 (půlením intervalu mezi středy)."""
    if model is None:
        return 3.0
    lo, hi = math.exp(model[1][0]), math.exp(model[1][1])
    for _ in range(50):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if p_pameti(model, m) > 0.5 else (lo, m)
    return (lo + hi) / 2


def statistiky(stav, sezeni, model):
    """Závěrečný textový přehled: sezení, celkem, žebříčky skupin a příkladů."""
    pr = stav["priklady"]
    vse = list(pr.values())
    out = []

    out.append("=== TOTO SEZENÍ ===")
    if sezeni:
        ok = [c for _, s, c in sezeni if s]
        out.append(
            f"odpovědí {len(sezeni)}, správně {len(ok)} ({len(ok) / len(sezeni):.0%}), "
            f"medián času {_fmt(_median(ok), '{:.1f} s')}, nejrychlejší {_fmt(min(ok, default=None), '{:.1f} s')}"
        )
        chybne = sorted({k.replace("x", "×") for k, s, _ in sezeni if not s})
        out.append("chyby: " + (", ".join(chybne) if chybne else "žádné"))
    else:
        out.append("žádné odpovědi")

    c = _souhrn(vse)
    nezname = sum(1 for z in vse if z["spravne"] < 2 or z["skore"] is None)
    pocita = sum(1 for z in vse if z["spravne"] >= 2 and z["skore"] is not None and z["skore"] < 0.4)
    out.append("")
    out.append("=== CELKEM ===")
    out.append(
        f"odpovědí {c['pokusy']}, úspěšnost {_fmt(c['uspesnost'], '{:.0%}')}, "
        f"medián času {_fmt(c['median'], '{:.1f} s')}"
    )
    out.append(
        f"zapamatováno {c['zvladnuto']}, počítá {pocita}, "
        f"mezi {100 - c['zvladnuto'] - pocita - nezname}, zatím neznámé {nezname} (ze 100)"
    )
    if model:
        w, mu, _ = model
        out.append(
            f"shluky: paměť ~{math.exp(mu[0]):.1f} s ({w[0]:.0%}), počítání ~{math.exp(mu[1]):.1f} s ({w[1]:.0%}), "
            f"hranice {hranice_gmm(model):.1f} s"
        )
    else:
        out.append(f"shluky: zatím málo dat (min. {MIN_FIT} správných), hranice odhadem 3.0 s")

    hlavicka = f"{'':<22}{'příkl':>5}{'pokusů':>8}{'úspěšn.':>10}{'medián':>9}{'skóre':>8}  zvládnuto"

    def zebricek(titulek, skupiny):
        radky = [(n, _souhrn(z)) for n, z in skupiny if z]
        radky.sort(key=lambda r: (r[1]["skore"] is None, -(r[1]["skore"] or 0)))
        out.append("")
        out.append(f"=== {titulek} (od nejlepší) ===")
        out.append(hlavicka)
        out.extend(f"{i:>2}. " + _radek_souhrnu(n, s, 18) for i, (n, s) in enumerate(radky, 1))

    def klice(podminka):
        return [pr[f"{a}x{b}"] for a in range(1, 11) for b in range(1, 11) if podminka(a, b)]

    zebricek("ŘADY NÁSOBILKY", [(f"řada {n}", klice(lambda a, b, n=n: n in (a, b))) for n in range(1, 11)])
    zebricek("TYPY PŘÍKLADŮ", [
        ("×1 a ×10", klice(lambda a, b: {1, 10} & {a, b})),
        ("×2 a ×5", klice(lambda a, b: {2, 5} & {a, b} and not {1, 10} & {a, b})),
        ("čtverce (a×a)", klice(lambda a, b: a == b)),
        ("malá (obě ≤5)", klice(lambda a, b: a <= 5 and b <= 5)),
        ("velká (obě ≥6)", klice(lambda a, b: a >= 6 and b >= 6)),
        ("smíšená", klice(lambda a, b: min(a, b) <= 5 < max(a, b))),
        ("menší × větší", klice(lambda a, b: a < b)),
        ("větší × menší", klice(lambda a, b: a > b)),
    ])

    def klic_hor(z):
        return (z["skore"] if z["skore"] is not None else 2, -z["chyby"])

    zkousene = [(k, z) for k, z in pr.items() if z["pokusy"]]
    out.append("")
    out.append("=== NEJTĚŽŠÍ PŘÍKLADY ===")
    out.append(f"{'':<8}{'pokusů':>8}{'chyb':>6}{'medián':>9}{'skóre':>8}{'interval':>10}")
    for k, z in sorted(zkousene, key=lambda kz: klic_hor(kz[1]))[:10]:
        out.append(
            f"{k.replace('x', ' × '):<8}{z['pokusy']:>8}{z['chyby']:>6}"
            f"{_fmt(_median(z['casy']), '{:.1f} s'):>9}{_fmt(z['skore'], '{:.0%}'):>8}{z['interval']:>10}"
        )

    rozdily = []
    for a in range(1, 11):
        for b in range(a + 1, 11):
            s1, s2 = pr[f"{a}x{b}"]["skore"], pr[f"{b}x{a}"]["skore"]
            if s1 is not None and s2 is not None:
                rozdily.append((abs(s1 - s2), a, b, s1, s2))
    rozdily = [r for r in sorted(rozdily, reverse=True) if r[0] >= 0.2][:5]
    out.append("")
    out.append("=== ASYMETRIE (a×b vs b×a) ===")
    if rozdily:
        for _, a, b, s1, s2 in rozdily:
            out.append(f"{a} × {b}: {s1:.0%}   vs   {b} × {a}: {s2:.0%}")
    else:
        out.append("žádné výrazné rozdíly")

    out.append("")
    out.append("=== SKÓRE ZAPAMATOVÁNÍ ===")
    out.append(tabulka(stav))
    return "\n".join(out)


def stred(okno, y, text, attr=0):
    _, sirka = okno.getmaxyx()
    x = max(0, (sirka - len(text)) // 2)
    try:
        okno.addstr(y, x, text[: sirka - 1], attr)
    except curses.error:
        pass


def uvod(okno):
    """Čeká na Enter a odpočítá start. Vrací False, pokud uživatel skončil 2× Esc."""
    esc_ceka = False
    while True:
        okno.erase()
        vyska, _ = okno.getmaxyx()
        y = max(0, vyska // 2 - 2)
        stred(okno, y, "NÁSOBILKA", curses.A_BOLD)
        stred(okno, y + 2, "Stiskni Enter pro start")
        napoveda = "Stiskni Esc ještě jednou pro ukončení" if esc_ceka else "2× Esc = konec"
        stred(okno, vyska - 2, napoveda, curses.color_pair(3) if esc_ceka else curses.A_DIM)
        okno.refresh()

        k = okno.getch()
        if k == -1:
            continue
        if k == 27:
            if esc_ceka:
                return False
            esc_ceka = True
            continue
        esc_ceka = False
        if k in (curses.KEY_ENTER, 10, 13):
            break

    for text in ("3...", "2...", "1...", "START!"):
        okno.erase()
        vyska, _ = okno.getmaxyx()
        stred(okno, vyska // 2, text, curses.color_pair(3) | curses.A_BOLD)
        okno.refresh()
        time.sleep(1 if text != "START!" else 0.6)
    curses.flushinp()
    return True


def hlavni(okno, stav, sezeni):
    curses.curs_set(0)
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, -1)
    curses.init_pair(2, curses.COLOR_RED, -1)
    curses.init_pair(3, curses.COLOR_YELLOW, -1)
    okno.timeout(100)

    if not uvod(okno):
        return

    model = fituj_gmm(stav["historie"])
    klic = vyber_priklad(stav, None)
    vstup = ""
    zacatek = None  # None = čeká se na Enter učitele
    prvni_cislice = None
    zprava, zprava_attr = "", 0
    esc_ceka = False
    spravne_celkem = odpovedi_celkem = 0

    while True:
        a, b = map(int, klic.split("x"))
        if zacatek is None:
            cas = 0.0
        elif prvni_cislice is not None:
            cas = prvni_cislice
        else:
            cas = time.monotonic() - zacatek

        okno.erase()
        vyska, _ = okno.getmaxyx()
        y = max(0, vyska // 2 - 4)

        stred(okno, y, "NÁSOBILKA", curses.A_BOLD)
        stred(okno, y + 2, f"{a} × {b} = {vstup}_", curses.A_BOLD)
        stred(okno, y + 4, f"čas: {cas:5.1f} s", curses.A_DIM if zacatek is None else 0)
        stred(okno, y + 6, zprava, zprava_attr)
        stred(okno, y + 8, f"správně {spravne_celkem} z {odpovedi_celkem}")
        if esc_ceka:
            napoveda = "Stiskni Esc ještě jednou pro ukončení"
        elif zacatek is None:
            napoveda = "přečti příklad, Enter = spustit čas, 2× Esc = konec"
        else:
            napoveda = "napiš, co žák řekl, Enter = potvrdit, 2× Esc = konec"
        stred(okno, vyska - 2, napoveda, curses.color_pair(3) if esc_ceka or zacatek is None else curses.A_DIM)
        okno.refresh()

        k = okno.getch()
        if k == -1:
            continue
        if k == 27:
            if esc_ceka:
                return
            esc_ceka = True
            continue
        esc_ceka = False

        if zacatek is None:
            if k in (curses.KEY_ENTER, 10, 13):
                zacatek = time.monotonic()
                curses.flushinp()
            continue

        if ord("0") <= k <= ord("9") and len(vstup) < 3:
            if prvni_cislice is None:
                prvni_cislice = time.monotonic() - zacatek
            vstup += chr(k)
        elif k in (curses.KEY_BACKSPACE, 127, 8):
            vstup = vstup[:-1]
        elif k in (curses.KEY_ENTER, 10, 13) and vstup:
            spravne = int(vstup) == a * b
            aktualizuj(stav, klic, spravne, prvni_cislice, model)
            sezeni.append((klic, spravne, prvni_cislice))
            odpovedi_celkem += 1
            if stav["pocitadlo"] % REFIT_KAZDYCH == 0:
                model = fituj_gmm(stav["historie"])
            if spravne:
                spravne_celkem += 1
                zprava = f"Správně! ({prvni_cislice:.1f} s)"
                zprava_attr = curses.color_pair(1) | curses.A_BOLD
            else:
                zprava = f"Špatně: {a} × {b} = {a * b}, ne {vstup}"
                zprava_attr = curses.color_pair(2) | curses.A_BOLD
            klic = vyber_priklad(stav, klic)
            vstup = ""
            zacatek = prvni_cislice = None


def main():
    os.environ.setdefault("ESCDELAY", "25")
    locale.setlocale(locale.LC_ALL, "")
    parser = argparse.ArgumentParser(description="Procvičování násobilky do 10.")
    parser.add_argument("--zak", default="default", help="jméno žáka; stav se ukládá do zak_<jméno>.json")
    soubor = os.path.join(os.getcwd(), f"zak_{parser.parse_args().zak}.json")
    stav = nacti_stav(soubor)
    sezeni = []
    try:
        curses.wrapper(hlavni, stav, sezeni)
    except KeyboardInterrupt:
        pass
    finally:
        uloz_stav(stav, soubor)
        print(statistiky(stav, sezeni, fituj_gmm(stav["historie"])))
        print(f"Stav uložen do {soubor}")


if __name__ == "__main__":
    main()
