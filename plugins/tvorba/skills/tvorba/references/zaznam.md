# Záznam projektu

**Úložiště (volitelné):** složka, kterou uživatel určí (lokální složka, Disk Google či jiné úložiště dostupné v prostředí), soubor `<id-projektu>.md` (id malými písmeny s pomlčkami, např. `moje-aplikace`). Nový záznam = nový soubor; změna existujícího = úprava téhož souboru, ne nový. Ukládej jen u projektu, který má víc než jedno sezení nebo prošel bránou. Bez možnosti zápisu dej záznam do odpovědi jako blok kódu a napiš „neuloženo“.

**Kdy zapsat:** po bráně A/B, po kroku 7, při návratu dolů a na konci sezení, které posunulo krok.

## Formát

```markdown
# <Název projektu>

- Krok: <1-7> (<název kroku>) | Typ problému: <jasný / komplikovaný / komplexní> | Náročnost: <1-5>
- Apetit: <hodiny nebo Neznámé> | Kill kritéria: <seznam nebo Neznámé>
- Měřítko úspěchu (Účel): <...>
- Aktualizováno: <RRRR-MM-DD>

## Nápad a koncept
<věta jako problém; pro koho, hodnota, princip; porovnané koncepty>

## Varianty
| Varianta | Popis | Hodnota | Náročnost | Ověřenost | Původ (uživatel / AI) |

## Rozhodnutí (ADR-lite)
- <datum> · <rozhodnutí>: kontext, možnosti, volba, důvod, co by změnilo názor

## Ověřenost a testy
- Nejriskantnější předpoklad: <...> | test: <...> | výsledek: <...>

## Aspekty
<jen vyplněné; ostatní „vědomě neřeším“>

## Měření (krok 7)
| Datum | Co | Odhad | Skutečnost | Poznámka |

## Historie kroků
- <datum> · <krok> → <krok> (<důvod, i návrat dolů>)
```
