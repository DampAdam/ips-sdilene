# Role AI v tvorbě: postupy a důkazy

Podklad: rešerše literatury (2026). Čísla jsou z citovaných studií; mapování na kroky je interpretace (předpoklad).

## Proč „nejdřív sám, pak AI“ (důkazy)

| Zjištění | Velikost | Zdroj |
|---|---|---|
| S AI je jednotlivý kreativní výstup lepší | g = 0,27 | metaanalýza, arXiv 2505.17241 (2025) |
| S AI klesá rozmanitost nápadů | g = -0,86 | tamtéž |
| Nápady od LLM: novost +8,1 %, užitečnost +9 %, ale podobnost mezi autory +10,7 % | | Doshi a Hauser, Science Advances 2024 |
| Úloha mimo hranici schopností AI: o 19 p. b. méně správných řešení | | Dell'Acqua et al. 2023 (BCG, N = 758) |
| Vyšší důvěra v AI souvisí s menším kritickým myšlením | korelace | Lee et al., CHI 2025 (N = 319) |
| Ukázky od AI zvyšují fixaci na první příklad a snižují počet a rozmanitost nápadů | | Wadinambiarachchi et al., CHI 2024 (N = 60) |
| „Vygeneruj mnoho a vyber nejodlišnější“ v jednom běhu se blíží rozmanitosti lidských skupin; generování po jednom v oddělených bězích ji snižuje | | Meincke, Mollick, Terwiesch 2024; arXiv 2607.27553 |
| Inkubace pomáhá řešení problémů | nevážený průměr 0,41 | Sio a Ormerod 2009 (117 studií) |
| LLM soudce: přes 80 % shody s lidmi, ale zkreslení podle pozice, délky a sebe-preference | | Zheng et al. 2023 (MT-Bench) |

## Role a prompt vzory po krocích

| Krok | Role AI | Vzor (uprav slovy podle situace) | Jen uživatel | Riziko |
|---|---|---|---|---|
| 1 Nápad | tazatel, přeformulovač | „Polož 5 otázek, které odhalí, jaký problém tím řeším; neřeš řešení.“ „Přeformuluj nápad 10 způsoby jako problém.“ | původní věta, zda je to jeho téma | ukotvení na formulaci AI |
| 2 Koncept | generátor konceptů, simulovaný uživatel, kritik | „Vygeneruj 30 krátkých konceptů, vyber 5 nejodlišnějších a zdůvodni odlišnost.“ „Zhodnoť z pohledu 4 odlišných uživatelů zvlášť.“ „Napiš nejsilnější argument, proč by to nikdo nepoužíval.“ | uživatel, hodnota, výběr | homogenizace; persona není skutečný uživatel |
| 3 Návrh | generátor variant, ďáblův advokát, red team, hodnotitel | Morfologie: „4-6 dimenzí, ke každé 3 možnosti, 5 nejodlišnějších kombinací.“ Pre-mortem: „Je za rok, V1 selhala; 5 nejpravděpodobnějších příčin.“ Steelman zamítnuté varianty. Pareto podle Hodnoty a Náročnosti. | kritéria (předem), volba, apetit, kill kritéria | pozice a délka zkreslují hodnocení |
| 4 Specifikace | spec-writer, tazatel | „Kde chybí informace, napiš otázku, ne předpoklad.“ EARS: „KDYŽ [událost], SYSTÉM MUSÍ [chování].“ Kontrola po 6 aspektech. | schválení, priority | vymyšlené požadavky, tichá změna směru |
| 5 Plán | plánovač, hledač rizik | „Úkoly do 1-2 h s kritériem hotovo a pořadím; nejriskantnější první.“ | apetit, co vypustit | optimistické odhady |
| 6 Výstup | implementátor, verifikátor | test nebo kontrolní seznam předem; revize v čistém kontextu: „zkontroluj proti specifikaci, vypiš rozpory“ | akceptace, validace proti Účelu | iluze rychlosti, neověřený výstup |
| 7 Provoz a učení | analytik retrospektivy | „Co ukazují poznámky z používání o předpokladech z Konceptu?“ | závěry, vyřazení | racionalizace neúspěchu |

## Podle aspektů

- **Účel:** AI jen klade otázky; odpověď píše uživatel.
- **Funkce:** ke každé funkci potřeba; bez potřeby = ke škrtnutí.
- **Data:** každý údaj má zdroj a použití.
- **Rozhraní:** simulace hlavních scénářů krok po kroku, hledání slepých uliček.
- **Kvalita:** návrh měřitelných prahů; uživatel vybere relevantní.
- **Stavba:** 2-3 architektury se zápisem ADR; rozhodnutí je jeho.

## AI jako soudce

Rubrika s kritérii předem; každé srovnání dvakrát s prohozeným pořadím; srovnatelně dlouhé popisy; neshoda = nejisté hodnocení, které se řekne; nikdy jediný podklad rozhodnutí.
