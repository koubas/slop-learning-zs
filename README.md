# slop-learning-zs

Malé vibecodované aplikace na procvičování učiva základní školy.

Číselné adresáře v kořeni odpovídají třídě ZŠ. V každém jsou jednotlivé
aplikace, každá ve vlastním podadresáři s vlastním README.

```
<třída>/<aplikace>/
```

## Aplikace

| třída | aplikace                         | popis                                 |
|-------|----------------------------------|---------------------------------------|
| 3     | [nasobilka](3/nasobilka/)        | TUI trenažér malé násobilky do 10     |

## Webová verze

Terminálové aplikace se dají spustit i v prohlížeči. Python běží
v [Pyodide](https://pyodide.org) (CPython zkompilovaný do WebAssembly),
terminál kreslí [xterm.js](https://xtermjs.org). Obojí se načítá z CDN
jsdelivr, takže je potřeba internet.

```
python3 web/build.py
python3 -m http.server -d dist
```

### Lokální vývoj bez internetu

```
python3 web/dev.py               # stáhne knihovny, sestaví, http://localhost:8000/
python3 web/dev.py --port 8080
python3 web/dev.py --jen-stahnout
```

`dev.py` stáhne Pyodide a xterm.js (~14 MB) do `web/vendor/` (v gitignore).
Stahuje jen to, co tam ještě chybí, takže internet je potřeba jen poprvé
a po změně verze. Pak sestaví `dist/` s lokálními knihovnami
(`build.py --lokalni`) a spustí server. Produkční build (`build.py` bez
přepínače) dál načítá knihovny z CDN.

### Společné pro obě varianty

Pak otevři <http://localhost:8000/>. Rozcestník odkazuje na jednotlivé
aplikace (`dist/<třída>/<aplikace>/`). Stránku je potřeba otevřít přes
`localhost` nebo https. Na adrese typu `http://192.168.…` nebo přes
`file://` prohlížeč nepovolí potřebné API.

Do webu se dostane každá aplikace, která má ve svém adresáři `web.json`:

```json
{
  "nazev": "Násobilka",
  "popis": "Trenažér malé násobilky do 10",
  "spoustec": "nasobilka.py",
  "dotaz": {
    "text": "Jméno žáka",
    "seznam": "Uložení žáci",
    "prazdny": "zatím žádní",
    "argument": "--zak",
    "vychozi": "default",
    "data": "zak_{}.json"
  }
}
```

- `spoustec`: skript, který se spustí jako `__main__`. Do prohlížeče se
  zkopírují všechny `.py` soubory z adresáře aplikace.
- `dotaz` (nepovinné): před spuštěním se terminál zeptá na hodnotu
  a předá ji jako `argument`. `data` je vzor datových souborů, podle kterého
  se před dotazem vypíšou už uložené hodnoty (např. jména žáků) pod nadpisem
  `seznam`, případně text `prazdny`, když zatím nic uloženo není.

### Jak to funguje

| soubor                     | úloha                                                                 |
|----------------------------|-----------------------------------------------------------------------|
| `web/build.py`             | najde aplikace s `web.json`, vygeneruje `dist/` (stránky, rozcestník) |
| `web/dev.py`               | stáhne knihovny do `web/vendor/`, sestaví lokální `dist/` a spustí server |
| `web/runtime/main.js`      | hlavní vlákno: xterm.js, klávesnice, localStorage                     |
| `web/runtime/worker.js`    | Web Worker: načte Pyodide, připraví virtuální FS a spustí aplikaci    |
| `web/runtime/bootstrap.py` | v Pythonu: dotaz na argument, spuštění aplikace, uložení dat          |
| `web/runtime/curses_shim.py` | náhrada `curses` (v Pyodide není) kreslící ANSI sekvencemi          |
| `web/runtime/sw.js`        | service worker přidávající hlavičky COOP/COEP                         |

- **Blokující vstup:** aplikace čtou klávesy synchronně (`getch()`).
  Python proto běží ve Web Workeru a klávesy dostává přes kruhový buffer
  ve `SharedArrayBuffer` a `Atomics.wait()`. Kód aplikací se nemusí
  měnit a stejný skript běží v terminálu i v prohlížeči.
- **Cross-origin izolace:** `SharedArrayBuffer` vyžaduje hlavičky COOP/COEP.
  Obyčejný `http.server` ani GitHub Pages je neposílají, proto je přidává
  service worker `sw.js`. Při první návštěvě se stránka jednou sama znovu načte.
- **curses:** náhrada implementuje jen to, co aplikace v repu používají.
  Pro ne-ASCII znaky vrací `getch()` bajty UTF-8 stejně jako skutečný curses.
- **Data:** soubory, které aplikace zapíše do pracovního adresáře, se po
  jejím skončení uloží do `localStorage` pod klíčem
  `slop-learning-zs:<třída>/<aplikace>:<soubor>` a při dalším načtení se vrátí
  zpět do virtuálního FS. Data tedy zůstávají jen v daném prohlížeči.
- **Verze** Pyodide a xterm.js i seznam souborů pro lokální kopii jsou
  v `KNIHOVNY` na začátku `web/build.py`.
