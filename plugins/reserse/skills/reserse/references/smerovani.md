# Směrování: linky a zdroje

Linka = doména z triáže (SKILL.md, oddíl 1) → jaké typy zdrojů a v jakém pořadí dá hlavní agent do zadání sběrače (`references/role.md`). Výběr, ne úplný seznam: sběrač hledá i další. Konkrétní nástroje (vyhledávání, čtení stránek, konektory, kvóty) jsou v adaptéru prostředí.

## Linka V - psychologie, zdraví, učení

1. **Volitelně od R2 (hlavní agent):** sjednocený dotaz do katalogů `scripts/veda.py hledej` (typ publikace ∪ výrazy v názvu, anglické termíny i pravopisné varianty, např. `"growth mindset" OR "growth mind-set"`) a kontrola známých položek `veda.py zname VYSLEDKY.json <DOI|PMID|název>…`. Hlavní agent čte jen metadata; nalezené přehledy předá sběrači jako kandidáty. Není to povinný krok: naivní dotaz v jednom indexu přehlédl klíčové práce (F1), ale sběrač bez limitu volání hledá šířeji (A/B 2026-10-31).
2. **Známé položky** chybí ve výstupu → oprav zadání (termíny, varianty, index), ne závěr.
3. **Přehled přehledů nejdřív** (umbrella review), pak systematické přehledy a metaanalýzy. Kvalitu přehledu odhadni nalehko podle AMSTAR 2 (7 kritických domén, `references/evidence.md`); jistotu GRADE převezmi z přehledu, je-li uvedená.
4. **Replikace:** stav replikace hledej ve FReD a v projektech typu Many Labs nebo registrovaných zprávách. Nenalezeno = „neznámé“, ne „replikováno“. Replikace stojí v žebříčku nad metaanalýzami (metaanalýzy mají efekty v průměru asi 3× větší než preregistrované replikace).
5. **Eskalace na primární studie**, když:
   - přehled chybí;
   - přehledy si odporují;
   - téma je mladší než poslední přehled (nové RCT po jeho uzávěrce);
   - otázka míří na praktickou vrstvu (dávka, přesný postup, konkrétní populace tazatele), na kterou přehled neodpovídá.
6. Populárně-naučné texty jen k objevení primárního zdroje, nikdy jako opora.

## Linka T - AI, software, nástroje

1. Nejdřív to, co už je zjištěné: archiv dřívějších rešerší.
2. **Primární dokumentace** výrobce, ceníky, changelogy, poznámky k verzi, stavové stránky; vždy s datem.
3. Články: preprint (arXiv) je slabší důkaz než recenzovaný; u benchmarku metodika a reprodukovatelnost.
4. **Benchmarky a studie výrobce = střet zájmů:** štítek „střet zájmů“ a hledej nezávislé měření (nezávislé hodnoticí organizace, RCT, replikace).
5. Issues v repozitářích, fóra, sociální sítě jen k objevení kandidátů a známých chyb; tvrzení z nich potřebuje primární potvrzení.

## Linka P - produkty, ceny, právo, úřady, ČR

1. **Oficiální zdroj s datem:** výrobce, prodejce, úřad, sbírka předpisů; uveď „platné k“.
2. **Laterální ověření (SIFT):** kdo je vydavatel podle jiných zdrojů, zda tvrzení potvrzuje nezávislý zdroj, původ tvrzení (`references/evidence.md`).
3. **Česká větev jen při místní dimenzi** (české právo, ceny v ČR, úřady, studium v ČR): jinak stačí mezinárodní zdroje.
4. Srovnávače a recenze uživatelů jen jako vzorek k objevení, ne jako důkaz; nezávislé testy (spotřebitelské organizace) jako doplněk.

## Nezávislé cesty

Pro triangulaci kombinuj aspoň dvě různé cesty: (1) obecný web, (2) odborný index nebo katalog domény, (3) oficiální či primární zdroj, (4) archiv a dřívější rešerše. Dva texty, které opisují tentýž zdroj, jsou jeden zdroj. Sběrač na opačnou hypotézu (R2) dostane v zadání jinou cestu, než odkud přišla hlavní tvrzení.

## Katalog zdrojů

„Ověřeno k“ = adresa odpověděla z prostředí relace (HTTP 200/202), nebo je uvedeno jinak. 401/403/419/429 a timeout znamenají blokování skriptů, ne mrtvý zdroj: čti přes sběrače.

| Linka | Zdroj | K čemu | Ověřeno k |
|---|---|---|---|
| V | PubMed (+ API E-utilities) | biomedicína, psychologie; typ publikace | 2026-10-31 (web i API) |
| V | Europe PMC (REST API) | PubMed + PMC + preprinty; plné texty OA | 2026-10-31 (API; web 403) |
| V | Crossref (API) | metadata DOI, retrakce (vč. Retraction Watch) | 2026-10-31 |
| V | OpenAlex (API) | metadata, citační síť, `is_retracted` | 2026-10-31 (429 bez klíče, záloha) |
| V | Cochrane Library | systematické přehledy ve zdravotnictví | 2026-10-31 (403/419 pro skripty) |
| V | FReD (FORRT Replication Database) | stav replikací v psychologii | 2026-10-31 |
| V | Retraction Watch | retrakce a vyjádření obav | 2026-10-31 |
| V | WHO, NICE, EFSA | doporučené postupy | 2026-10-31 |
| V | SÚKL, NZIP | léky a zdraví v ČR | 2026-10-31 |
| V/T | Semantic Scholar | vyhledávání článků, citace | 2026-10-31 |
| V/T | OSF | preregistrace, data, preprinty | 2026-10-31 |
| T | arXiv | preprinty informatiky, AI, matematiky | 2026-10-31 |
| T | METR, Epoch AI, Artificial Analysis | nezávislá měření AI | 2026-10-31 |
| T | denní přehled článků (Hugging Face Papers) | nové články AI | 2026-10-31 |
| P | e-Sbírka, EUR-Lex | právo ČR a EU | 2026-10-31 |
| P | NS, NSS, ÚS, SDEU | judikatura | 2026-10-31 |
| P | ČSÚ, Eurostat, ČNB | statistiky, kurzy | 2026-10-31 (OECD 403) |
| P | obchodní rejstřík (justice.cz), ARES | firmy | 2026-10-31 |
| P | dTest, ČOI, RTINGS | nezávislé testy, dozor nad trhem | 2026-10-31 |
| P | ČTK, Reuters | aktuální události | 2026-10-31 (Reuters 401 pro skripty) |

## Mimo automatické cesty

- **Placené vyhledávací a stahovací služby** (kredity): jen když stránku jinak načíst nejde nebo jsou potřeba strukturovaná data.
- **Služby hlubokého výzkumu jiných firem:** jen předávka R3 (`references/predani.md`) a příjem jejich výstupu jako data (s G2).
- **Vlastní režim hlubokého výzkumu prostředí:** jen interaktivně po potvrzení uživatele, nikdy v naplánované úloze.
- **Konektory, které na plánu uživatele nefungují**, a kvóty bezplatných služeb: adaptér.
