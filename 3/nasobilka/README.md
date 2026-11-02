# Násobilka

Procvičování násobilky do 10 v terminálu (Python 3, jen standardní knihovna, `curses`).

```
python3 nasobilka.py              # stav v zak_default.json
python3 nasobilka.py --zak anicka # stav v zak_anicka.json
```

## Parametry

| parametr        | výchozí   | význam                                                    |
|-----------------|-----------|-----------------------------------------------------------|
| `--zak <jméno>` | `default` | jméno žáka; stav se načítá a ukládá do `zak_<jméno>.json` |

Každý žák má vlastní stavový soubor v aktuálním adresáři, a tedy vlastní
frontu, skóre i model GMM. Jméno se vkládá do názvu souboru beze změny,
takže by nemělo obsahovat `/`.

## Ovládání

1. Úvodní obrazovka: **Enter** spustí odpočet 3… 2… 1… START!
2. Zobrazí se příklad. Čas zatím neběží.
3. Učitel příklad přečte a stiskne **Enter**: čas běží od 0.
4. Žák napíše výsledek (Backspace opravuje) a potvrdí **Enterem**.
5. **2× Esc** kdykoli ukončí aplikaci, uloží stav do `zak_<jméno>.json`
   v aktuálním adresáři a vypíše závěrečné statistiky.

Při dalším spuštění se stav načte a pokračuje se tam, kde se skončilo.

## Evidence příkladů

Eviduje se všech 100 příkladů `1×1` až `10×10` a **záleží na pořadí**:
`2×3` a `3×2` jsou dva samostatné příklady s vlastní historií.

## Měření času

Měří se doba od Enteru učitele do **první napsané číslice**, ne do potvrzení.
Doba psaní (dvouciferný výsledek se píše déle než jednociferný) tak
nezkresluje měření a čas odpovídá tomu, jak rychle si žák výsledek vybavil.

## Učební metoda: odkládání o počet příkladů

Je to varianta spaced repetition. Intervaly se ale nepočítají v minutách
ani dnech, počítají se **v počtu zodpovězených příkladů**. Pro paměť je podstatné
hlavně to, kolik jiných věcí proběhlo mezi dvěma opakováními (interference).
Aplikace navíc běží jen v sezeních, takže kalendářní čas by stejně nebyl
k ničemu. Fronta se ukládá, a tak plynule pokračuje i přes víc sezení.

Každý příklad má:

| pole       | význam                                                       |
|------------|--------------------------------------------------------------|
| `interval` | za kolik příkladů má přijít znovu                            |
| `na_rade`  | pořadové číslo odpovědi, od kdy je příklad znovu na řadě     |
| `skore`    | odhad pravděpodobnosti, že ho žák „ví“ (0–1), viz níže       |

### Aktualizace po odpovědi

Globální `pocitadlo` = počet všech odpovědí.

- **Chyba:** `interval = 3`. Příklad se vrátí brzy, ale ne hned. Okamžité
  zopakování by testovalo jen krátkodobou paměť.
- **Správně:** `interval = round(interval × (1.2 + 1.8 × skore))`,
  omezeno na 3 až 1000.
  - zapamatovaný příklad (`skore ≈ 1`): interval ×3 (3 → 9 → 27 → 81 …)
  - počítaný příklad (`skore ≈ 0`): interval ×1.2, odkládá se jen málo
- Potom `na_rade = pocitadlo + interval`.

### Výběr dalšího příkladu

1. Ze všech už zkoušených příkladů, které jsou na řadě (`na_rade ≤ pocitadlo`),
   se vybere ten, který čeká nejdéle. Shodu rozhodne náhoda.
2. Pokud žádný na řadě není, přijde náhodný **nový** (dosud nezkoušený) příklad.
3. Pokud nové došly, vybere se ten, který bude na řadě nejdřív.

Právě zodpovězený příklad nikdy nepřijde hned znovu.

## Rozlišení „pamatuje“ vs. „počítá“: GMM

Doby odpovědí mívají dva vrcholy. Kolem 1–2 s jsou příklady, které žák zná
z paměti, kolem 4–8 s ty, které dopočítává. Hranice mezi nimi je u každého
dítěte jiná a s časem se posouvá. Proto se nenastavuje natvrdo, ale **učí se
z dat**.

### Model

Na časech posledních **100 správných odpovědí** se fituje **směs dvou
normálních rozdělení** (Gaussian Mixture Model) na **logaritmu času**.
Logaritmus se používá proto, že reakční časy jsou zešikmené doprava a po
zlogaritmování vypadají oba shluky přibližně normálně.

```
p(x) = w₀·N(x; μ₀, σ₀²) + w₁·N(x; μ₁, σ₁²),   x = ln(čas)
```

Složka s menším `μ` = paměť, s větším = počítání.

Fit probíhá algoritmem **EM** (100 iterací):

- start: `μ` = 1. a 3. kvartil, `σ²` = celkový rozptyl, `w = 0.5 / 0.5`
- E-krok: pro každou odpověď `r = w₀N₀ / (w₀N₀ + w₁N₁)`
- M-krok: vážené průměry, rozptyly a váhy z `r`
- minimální rozptyl 0.01 (v log prostoru), aby se složka nezhroutila na bod

Model se **nepoužije** (a místo něj nastoupí záloha), pokud:
- je méně než 20 správných odpovědí,
- jedna složka „vyschne“ (méně než 1 bod),
- středy jsou si moc blízko (`μ₁ − μ₀ < 0.3`, tj. pomalejší shluk je méně než
  o ~35 % pomalejší). Data pak nejsou dvouvrcholová a dělení by bylo umělé.

Přefitování: na začátku sezení a pak každých 20 odpovědí. Hranice se tak
posouvá s tím, jak se dítě zrychluje.

### Pravděpodobnost „pamatuje“ pro jednu odpověď

```
P(paměť | čas) = w₀N₀(x) / (w₀N₀(x) + w₁N₁(x))
```

`x` se ořízne do intervalu `[μ₀, μ₁]`. Bez ořezu by u extrémně rychlých nebo
pomalých časů mohla „vyhrát“ širší složka a výsledek by se otočil.

**Záloha bez modelu:** logistická křivka kolem 3 s,
`P = 1 / (1 + e^((čas − 3) / 0.7))`.

### Skóre příkladu

Klouzavý (exponenciální) průměr přes odpovědi s váhou nové odpovědi `α = 0.4`:

```
skore = 0.6 × skore + 0.4 × p
```

kde `p = P(paměť | čas)` u správné odpovědi a `p = 0` u chyby.
Na první odpověď se `skore = p`.

Kategorie (u příkladů s aspoň 2 správnými odpověďmi):

| skóre      | kategorie     |
|------------|---------------|
| ≥ 70 %     | zapamatováno  |
| 40–70 %    | mezi          |
| < 40 %     | počítá        |
| málo dat   | neznámé       |

## Závěrečné statistiky

Po ukončení se vypíše:

- **Toto sezení:** počet odpovědí, úspěšnost, medián a nejrychlejší čas, seznam chyb.
- **Celkem:** úspěšnost, medián času, počty v kategoriích, parametry obou
  shluků GMM a hranice (čas, kde `P(paměť) = 0.5`, hledá se půlením intervalu).
- **Žebříček řad násobilky:** řada *n* = všech 19 příkladů, kde je *n*
  jedním z činitelů.
- **Žebříček typů příkladů:** ×1 a ×10, ×2 a ×5, čtverce, malá (obě ≤ 5),
  velká (obě ≥ 6), smíšená, menší × větší, větší × menší.
- **Nejtěžší příklady:** 10 příkladů s nejnižším skóre.
- **Asymetrie:** dvojice, kde se skóre `a×b` a `b×a` liší aspoň o 20 bodů.
- **Tabulka 10×10** se skóre, barevně (zelená = paměť, žlutá = mezi, červená = počítá).

Žebříčky jsou seřazené podle průměrného skóre a obsahují počet příkladů,
počet pokusů, úspěšnost, medián času správných odpovědí, průměrné skóre
a počet zapamatovaných.

Medián se používá místo průměru, aby jedna rozptýlená odpověď (třeba 30 s)
nezkreslila výsledek.

## Soubor stavu

`zak_<jméno>.json`:

```json
{
  "pocitadlo": 674,
  "historie": [1.2, 4.8, ...],
  "priklady": {
    "7x8": {
      "interval": 4, "na_rade": 678, "skore": 0.12,
      "pokusy": 20, "spravne": 16, "chyby": 4,
      "casy": [5.1, 4.7, ...]
    }
  }
}
```

- `historie`: časy posledních 100 správných odpovědí (vstup pro GMM)
- `casy`: posledních 10 správných časů daného příkladu

Starší formát (`nasobilka_stav.json` s polem `priorita`) se nepodporuje
a nepřevádí. Nový žák začíná od nuly.

## Konstanty

Jsou na začátku `nasobilka.py`:

| konstanta        | hodnota | význam                                    |
|------------------|---------|-------------------------------------------|
| `INTERVAL_CHYBA` | 3       | interval po chybě, zároveň minimum        |
| `INTERVAL_MAX`   | 1000    | strop intervalu                           |
| `ALFA`           | 0.4     | váha nové odpovědi ve skóre               |
| `HISTORIE_MAX`   | 100     | kolik časů se drží pro GMM                |
| `MIN_FIT`        | 20      | minimum správných odpovědí pro GMM        |
| `REFIT_KAZDYCH`  | 20      | jak často se GMM přefituje                |
| `MIN_ROZPTYL`    | 0.01    | spodní mez rozptylu složky (log prostor)  |
| `MIN_ODSTUP`     | 0.3     | minimální odstup středů shluků            |
