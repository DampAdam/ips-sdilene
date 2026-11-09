# Model studenta

Nejmenší záznam, ze kterého jde vybrat další krok a navázat bez nového onboardingu. Patří jednomu učebnímu cíli (předmět, téma, dovednost), ne osobě; fakta o studentovi do něj nepatří.

## Úložiště

- Jeden záznam `<id-cile>.md` na cíl (`id-cile` v kebab-case, např. `linearni-algebra`, `kytara-akordy`).
- Kam ho uložit, určuje uživatel: složka, kterou si zvolí (např. na Google Disku), soubory nebo znalosti projektu, nebo nikam, a záznam pak na začátku dalšího sezení vloží zpět do chatu. Nevíš-li, kam ukládat, u prvního delšího cíle se jednou zeptej.
- Zapisuj jen u delšího cíle (víc sezení) a jen tam, kam máš opravdu schopnost zápisu. Bez ní pracuj v kontextu a na konci dej přenositelný záznam ve stejném formátu.
- Načti skutečný záznam daného cíle (soubor, nebo text vložený uživatelem); existuje-li víc podobných, zeptej se, který.

## Pravidla obsahu

- Zapisuj jen to, co sezení doložilo. Odděl přímé pozorování, hlášení studenta a hodnocení jinou osobou.
- Žádná procenta zvládnutí ani pravděpodobnosti; stav položky je kategorie s datem a podkladem.
- Navržený cíl odliš od potvrzeného. Neznámé hodnoty piš „neznámé“.
- Stav plánovače kartiček (FSRS) je v aplikaci s kartičkami, ne tady.
- Nezapisuj prázdné řádky tabulek ani vymyšlenou historii.

## Stav položky

`neviděno` → `rozpracováno` → `s pomocí` (zvládne s nápovědou) → `bez pomoci (datum)` → `odloženě bez pomoci (datum)` (aspoň den po výuce, bez nápověd). Selhání po odstupu vrací položku na `rozpracováno`.

## Šablona

```markdown
# Model studenta: <název cíle>

Verze formátu: 1
ID cíle: <id-cile>
Poslední aktualizace: <RRRR-MM-DD>

## 1. Cíl a profil
- Cílový výkon: Bez pomoci <sloveso + obsah + kritérium>, i za 4 týdny. (potvrzený / návrh)
- Profil: <A-F nebo vlastní: základ + změněná pole>
- Termín: <datum / bez termínu>
- Rozpočet: <h týdně / neznámé>
- Horizont uchování: <do termínu / měsíce / trvale>
- Povolené pomůcky a pravidla: <např. ručně psané poznámky; zákaz AI u úkolů>
- Zdroje: <skripta, slajdy, staré zkoušky>

## 2. Mapa učiva
| ID | Koncept nebo dovednost | Prerekvizity | Stav | Poslední podklad | Další návrat |
|---|---|---|---|---|---|

## 3. Mylné představy
| ID | Popis | Kde se projevila | Stav (aktivní / vyvrácená, datum ověření) |
|---|---|---|---|

## 4. Kalibrace a pomoc
- Jistota vs. výsledek: <kde přeceňuje / podceňuje>
- Typická úroveň nápověd: <H1-H4 podle typu úloh>

## 5. Sezení
| Datum | Co | Exit ticket (bez pomoci) | Čas (změřený / odhad) |
|---|---|---|---|

## 6. Návaznost
- Další krok: <...>
- Ověřit: <položky k odloženému testu>
- Návrat: <datum nebo podmínka>
```
