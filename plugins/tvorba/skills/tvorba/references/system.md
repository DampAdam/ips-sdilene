# Systém tvorby v2 (provozní rozpis)

Tento soubor je provozní rozpis pro vedení projektu. Čísla jsou pracovní, doladí se po pilotu.

## Kroky zralosti

| Krok | Otázka | Výstup | Hotovo, když |
|---|---|---|---|
| **A 1 Nápad** | Co mě napadlo a jaký problém či příležitost za tím je? | jedna věta jako problém | je napsaný jednou větou jako problém, ne jen řešení |
| **A 2 Koncept** | Co a proč? | problém, pro koho, hodnota, hlavní princip, typ problému, měřítko úspěchu | jde posoudit a porovnat s jiným konceptem; umí odpovědět „proč by to někdo chtěl?“ |
| **A 3 Návrh** | Jakým řešením? | konkrétní podoba, varianty, zdůvodnění, ADR-lite | jde rozhodnout (ano / ne / jiná varianta) |
| *brána A/B* | | volba varianty, apetit, kill kritéria | rozhodnutí zapsané |
| **B 4 Specifikace** | Co přesně má platit? | ověřitelné požadavky po aspektech, otevřené otázky = 0 | dá se stavět bez dalších otázek |
| **B 5 Plán** | Jak a kdy? | úkoly s hotovo, pořadí, čas, apetit, rizika | má kroky, pořadí, čas a apetit |
| **B 6 Výstup** | Je to hotové? | hotová věc + test nebo kontrolní seznam | splní kritéria hotovo |
| **C 7 Provoz a učení** | Splnilo to Účel? | měření, retrospektiva, odhad vs. skutečnost | zapsané poučení a rozhodnutí pokračovat / upravit / vyřadit |

- **Funkce:** koncept = potřeby a schopnosti; návrh = výběr funkcí; specifikace = přesné chování. Nová funkce ve specifikaci → zpět k návrhu.
- **Lite režim:** náročnost 1-2 → Nápad → Návrh → Výstup.
- **Typ problému (Cynefin):** jasný / komplikovaný = lineárně; komplexní = sonda už v kroku 2-3 a výsledek zpět do Návrhu.

## Pravidla průchodu kroky 1-3

1. Rozbíhání a sbíhání: aspoň 3 vlastní varianty nebo formulace, hodnocení odděleně, kritéria předem.
2. Nejdřív sám, pak AI; AI rozšiřuje a kritizuje; rozhoduje uživatel.
3. Inkubace: u důležitých rozhodnutí aspoň den mezi Konceptem a volbou Návrhu.
4. ADR-lite u každé volby: kontext, možnosti, volba, důvod, co by změnilo názor.

## Brány

Na hranici A/B (u důležitých věcí už po Konceptu): apetit a kill kritéria. Překročený apetit = návrat ke Konceptu, ne prodloužení. Specifikace už nemění směr.

## Osa Aspekt (Účel vždy první)

| Aspekt | Otázka | Hotovo |
|---|---|---|
| Účel | Proč a pro koho? | problém, uživatel, měřítko úspěchu |
| Funkce | Co umí? | každá funkce má potřebu |
| Data | Co si pamatuje? | každý údaj má zdroj a použití |
| Rozhraní | Jak s tím pracuju? | hlavní scénáře prošlé krok po kroku |
| Kvalita | Jak dobře? | měřitelné prahy (kontrolní seznam ISO/IEC 25010 u softwaru) |
| Stavba | Z čeho a na čem? | každá funkce má kde běžet; řešit až od návrhu |

Prázdný aspekt = „vědomě neřeším“.

## Osa Detail

Celek → Oblast → Prvek → Pravidlo; úplné a bez překryvů, nejvýš ~7 částí na úroveň. Koncept → oblasti, návrh → prvky, specifikace → pravidla. U osobních projektů obvykle stačí Prvek.

## Škály a priorita

- **Hodnota 1-5** (žádná, bonus, zlepšení, klíčová, nezbytná); test „co se stane, když to nebude?“; ≈ dopad × četnost.
- **Náročnost 1-5** (< 1 h, hodiny, dny, týdny, měsíce; čas, peníze, energie, údržba); odhad × 1,5-2, dokud není vlastní referenční třída (po ~10 projektech medián poměru skutečnost / odhad).
- **Ověřenost:** domněnka → podložená → otestovaná → potvrzená; nejlevnější posun je prototyp nebo sonda.
- **Priorita částí:** vysoká hodnota a nízká náročnost první; hodnota ≥ 4 a ověřenost „domněnka“ → nejdřív levný test. Dopad / Risk / Náročnost (/10) jen pro řazení projektů a akcí.
- Doplňky jen při potřebě (verze a životní cyklus, riziko a vratnost, produkt vs. proces); novou dimenzi jen když změní rozhodnutí.
