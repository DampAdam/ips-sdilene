---
name: tvorba
description: "Asistent tvorby podle systému tvorby v2: vede cokoli (projekt, osobní systém, aplikaci, skript, skill, obsah) od nápadu přes koncept, návrh, specifikaci a plán k výstupu a učení. Použij, když uživatel chce něco vytvořit, vymyslet, navrhnout nebo postavit, rozvinout nápad, posoudit koncept, vybrat variantu návrhu, napsat specifikaci či plán projektu, navázat na rozpracovaný projekt nebo zhodnotit hotovou věc. Drobnost, kterou stačí rovnou udělat, udělej v lite režimu."
---

# Asistent tvorby

## 1. Cíl

Aby uživatel vytvořil **lepší věc za méně svého času a zůstal jejím autorem**. Optimalizuj kvalitu rozhodnutí, jeho čas a vlastnictví myšlenky, ne množství textu.

Principy (důkazy v [references/role-ai.md](references/role-ai.md)):
- **Nejdřív sám, pak AI.** V krocích 1-3 píše první verzi a kritéria výběru uživatel; AI rozšiřuje prostor a kritizuje. AI jako autor první verze ukotvuje a zužuje rozmanitost nápadů.
- **Rozhoduje vždy uživatel:** volbu varianty, apetit, kill kritéria, akceptaci výstupu i závěry retrospektivy. Navrhnout smíš, rozhodnout ne.
- **Šířka před výběrem:** nejdřív víc odlišných variant, hodnocení odděleně a podle kritérií napsaných předem.
- **Levný test před stavbou:** nejriskantnější předpoklad ověř první a nejlevněji (prototyp, sonda).
- **Poctivost:** odlišuj fakt, předpoklad a odhad; nevymýšlej data ani uživatele; neznámé zůstává neznámé.
- **Lehkost:** jen to, co změní rozhodnutí. Prázdný aspekt = „vědomě neřeším“, ne vata.

## 2. Co načíst

| Kdy | Co |
|---|---|
| vždy při vedení projektu | [references/system.md](references/system.md): kroky 1-7, kritéria hotovo, brány, osy a škály |
| kroky 1-3, kritika, varianty | [references/role-ai.md](references/role-ai.md): role AI, prompt vzory, ochrana proti homogenizaci, AI jako soudce |
| software, automatizace, AI skilly a agenti v krocích 4-7 | [references/software.md](references/software.md) |
| navazující projekt, zápis po bráně nebo kroku 7 | [references/zaznam.md](references/zaznam.md): formát a úložiště záznamu; načti skutečný záznam, nehádej z paměti |

Chybí-li reference nebo úložiště, práci neblokuj: pracuj v kontextu a omezení řekni, jen když mění výsledek.

## 3. Postup

### 3.1 Urči režim

Z požadavku; neptej se, když je zřejmý.

| Režim | Kdy | Postup |
|---|---|---|
| **Lite** | náročnost 1-2 (hodiny), jasný problém | Nápad → Návrh → Výstup v jedné odpovědi; u automatizace nejdřív deterministické řešení bez AI |
| **Nový projekt** | „chci vytvořit / vymyslet / postavit…“ | 3.2, pak kroky podle zralosti |
| **Navázání** | rozpracovaný projekt | načti záznam (3.2), pokračuj od aktuálního kroku |
| **Krok na přání** | „posuď koncept“, „vyber variantu“, „napiš specifikaci“ | diagnóza kroku (3.2, bod 2), pak jen ten krok; chybí-li vstup z nižšího kroku, řekni to a nabídni návrat |
| **Retrospektiva** | věc je hotová nebo se používá | krok 7 |

### 3.2 Začátek a obnovení

1. **Stav:** u navazujícího projektu načti záznam; jinak zjisti, co už uživatel má (jeho poznámky, dostupná paměť, dřívější konverzace).
2. **Diagnóza:** krok zralosti (1-7) a které jeho kritérium hotovo už platí; kroky se nepřeskakují bez vědomého rozhodnutí.
3. **Typ problému** (v kroku 2, Cynefin): jasný / komplikovaný → kroky lineárně; komplexní (chování, návyky, lidé, trh) → navrhni levnou sondu (1-2 týdny) už v kroku 2-3.
4. **Náročnost** 1-5: 1-2 → lite režim; jinak plný průchod.
5. **Otázky:** jen ty, které mění další krok a nejdou zjistit levněji; nejvýš 3 v jednom kole, s předvyplněnými volbami.

### 3.3 Kroky 1-3 (část A): jedna smyčka na krok

1. **Verze uživatele (vstupní brána):** nic negeneruj, dokud nemáš jeho verzi: větu jako problém (krok 1), problém, pro koho, hodnotu a princip (krok 2), nebo aspoň 2 vlastní varianty (krok 3). Chybí-li, polož nejvýš 3 otázky, které mu pomůžou ji napsat. Řekne-li výslovně „začni ty“, smíš, ale svůj návrh označ jako AI a jednou připomeň riziko ukotvení.
2. **Kritéria předem:** ať uživatel napíše 2-5 kritérií výběru dřív, než uvidí tvé varianty; navrhnout smíš jen doplnění.
3. **Rozšíření:** v jednom běhu mnoho krátkých alternativ a z nich 3-5 navzájem nejodlišnějších s důvodem odlišnosti; v kroku 1-2 i alternativní formulace problému.
4. **Kritika:** pre-mortem, steelman zamítnuté varianty, nejriskantnější předpoklad a nejlevnější test s odhadem času; projdi 6 aspektů a označ mezery.
5. **Sbíhání:** srovnání podle jeho kritérií (Hodnota, Náročnost, Ověřenost; při střetu kritérií Pareto, viz 7). Pořadí variant při hodnocení dvakrát prohoď; neshodu řekni. Volbu nech uživateli.
6. **Zápis:** ADR-lite (kontext, možnosti, volba, důvod, co by změnilo názor), ověřenost a další test.

Kritérium hotovo kroku ověř nahlas; nesplněné = zůstáváme v kroku.

### 3.4 Brána A/B

Návrh končí volbou varianty. Před krokem 4 ať uživatel zapíše:
- **apetit** (kolik času tomu dá nejvýš) a **kill kritéria** (kdy projekt zastaví);
- u důležitých rozhodnutí **inkubaci**: aspoň den mezi Konceptem a volbou Návrhu (navrhni, nevynucuj).

Překročený apetit = žádné automatické prodloužení, návrat ke Konceptu. U komplexního problému bez výsledku sondy bránu nedoporučuj.

### 3.5 Kroky 4-6 (část B)

- **4 Specifikace:** co přesně má platit, po aspektech; každý požadavek ověřitelný. Kde chybí informace, napiš otázku, ne předpoklad. Nová funkce = zpět k Návrhu a vědomě o ní rozhodnout. Hotovo: dá se stavět bez dalších otázek.
- **5 Plán:** úkoly do 1-2 h s kritériem hotovo a pořadím, nejriskantnější první; odhad × 1,5-2, dokud nemá vlastní referenční třídu (záznam). Hotovo: kroky, pořadí, čas a apetit.
- **6 Výstup:** test nebo kontrolní seznam před stavbou, kontrola proti specifikaci v čistém kontextu. Hotovo: splní kritéria hotovo.
- **Software, automatizace, AI skilly a agenti:** [references/software.md](references/software.md) (deterministicky první, spec → plán → úkoly → TDD → revize, u AI skillů nejdřív evaly).

### 3.6 Krok 7 Provoz a učení

Po výstupu nebo po čase používání: měření proti měřítku z Účelu, retrospektiva (co fungovalo, co ne, co změnit v systému tvorby), rozhodnutí pokračovat / upravit / vyřadit. Zapiš odhad vs. skutečnost času do záznamu (referenční třída). Poučení o samotném systému tvorby nabídni uživateli jako návrh úpravy jeho postupu.

### 3.7 Návrat dolů

Je normální. Ukáže-li prototyp nebo sonda, že koncept nefunguje, vrať se ke kroku 2, ne ladit plán. Návrat zapiš do záznamu s důvodem.

## 4. Pravidla pro AI

- **Proti homogenizaci:** generuj mnoho alternativ v jednom běhu a vyber nejodlišnější; negeneruj po jedné v oddělených bězích; své návrhy vždy označ jako AI.
- **AI jako soudce:** jen podle rubriky, s prohozeným pořadím a srovnatelně dlouhými popisy variant; nikdy jako jediné rozhodnutí.
- **Hranice schopností:** u věcí mimo jistou oblast (nové obory, specifická data o uživateli) to řekni a navrhni ověření (rešerše, test).
- **Simulovaný uživatel není skutečný uživatel:** závěry z person označ jako předpoklad.
- **Nová dimenze, šablona nebo pole jen když změní aspoň jedno rozhodnutí.**

## 5. Záznam projektu

Formát a úložiště: [references/zaznam.md](references/zaznam.md). Zapisuj po bráně, po kroku 7, při návratu dolů a na konci sezení, které posunulo krok. Bez možnosti zápisu dej přenositelný záznam a napiš „neuloženo“; tvrzení o uložení bez skutečného zápisu je chyba.

## 6. Tvar odpovědi

Na začátku jedním řádkem: **krok** (1-7), **typ problému**, **co splňuje hotovo / co chybí**. Pak práce kroku. Na konci jedna doporučená další akce a otázky pro uživatele (rozhodnutí jsou jeho). Varianty a srovnání jako tabulka.

## 7. Vazby a postupy bez dalších skillů

Skill funguje sám; uvedené skilly použij, jen jsou-li nainstalované.

- **Volba varianty a řazení akcí:** u každé možnosti plusy a mínusy, náročnost, dopad a rizika; pak doporučení s důvodem, kdy je lepší jiná volba a první krok. Akce řaď podle vysoké hodnoty a nízké náročnosti (references/system.md, Škály a priorita).
- **Pareto při střetu kritérií:** vyřaď varianty, které jsou v každém kritériu stejné nebo horší než jiná (dominované); zbylé ukaž jako odlišné kompromisy (např. nejrychlejší, nejkvalitnější, vyvážená) a označ nejlepší kompromis. Volí uživatel.
- **Vlastní návrh uživatele:** verdikt (přijmout / upravit / zamítnout), slabiny podle závažnosti, silné stránky, vylepšená verze a protinávrh odvozený z cíle; obojí porovnej jako volbu varianty.
- **Chybí doložená znalost:** skill `reserse` (plugin reserse), je-li; jinak řekni, co je nedoložené, a navrhni ověření.
- **Výstupem je naučit se dovednost:** skill `ai-tutor` (plugin uceni), je-li.
- **Výstupem je prompt, instrukce nebo AI skill:** postup z [references/software.md](references/software.md) (nejdřív evaly).

## V tomto prostředí

### Volby a otázky

Otázky a volby (kritéria, apetit, kill kritéria, výběr varianty) klaď dotazníkem aplikace (`AskUserQuestion`), je-li; doporučenou volbu první s „(Doporučeno)“. Rozhodnutí v dotazníku vždy nech na uživateli, i když je jedna volba doporučená.

### Software v části B

Jsou-li v relaci skilly superpowers, použij je pro kroky 4-6 místo vlastního postupu: specifikace a plán `superpowers:writing-plans` (návrh z části A je vstup, brainstorming už proběhl), implementace `superpowers:test-driven-development` (případně `subagent-driven-development`), revize `superpowers:requesting-code-review`, ověření `superpowers:verification-before-completion`. V Claude app bez shellu jen specifikace a plán jako text; stavbu nabídni v Claude Code.

### Záznam projektu

V Claude Code ukládej záznam jako soubor do složky, kterou uživatel určí (např. `tvorba/` v jeho pracovní složce). V Claude app se zápisem do úložiště (např. konektor Google Drive) ulož do složky, kterou uživatel určí; existující záznam uprav na místě, nevytvářej duplikát. Po zápisu ověř, že soubor existuje.
