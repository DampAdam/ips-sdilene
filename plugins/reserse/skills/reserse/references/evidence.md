# Hodnocení důkazů a štítky

Štítky dává sběrač podle pravidel M0 a definic v `references/role.md`; skript `scripts/citace.py stitky` je jen zeslabí (oddíl 4). Žebříčky níže slouží k zadání typů zdrojů, ke kontrole výstupu a jako **úroveň důkazu** (vysoká / střední / nízká / velmi nízká) v režimu s G2.

## 1. Tři žebříčky

Pořadí shora = silnější důkaz. Žebříček vyber podle typu tvrzení, ne podle tématu.

**Věda (linka V) - „funguje X, jak velký je efekt“**

| Stupeň | Typ | Úroveň |
|---|---|---|
| 1 | preregistrovaná replikace, vícelaboratorní studie (Many Labs, registrovaná zpráva) | vysoká |
| 2 | systematický přehled či metaanalýza kvalitních studií; přehled přehledů | vysoká |
| 3 | randomizovaná kontrolovaná studie (preregistrovaná > ostatní) | vysoká až střední |
| 4 | kvaziexperiment, kohortová studie | nízká |
| 5 | průřezová či korelační studie, série případů, modelace | nízká |
| 6 | odborný názor, mechanistická úvaha, kazuistika | velmi nízká |
| 7 | anekdota, marketing | velmi nízká |

Replikace stojí nad metaanalýzami: metaanalýzy mají efekty v průměru asi 3× větší než preregistrované replikace téhož jevu (Kvarven et al. 2020, 15 párů, https://pubmed.ncbi.nlm.nih.gov/31873200/).

**Technika (linka T)**

| Stupeň | „Co nástroj umí, kolik stojí, co se změnilo“ | „Jak dobře funguje“ |
|---|---|---|
| 1 | primární dokumentace, ceník, changelog (s datem) | nezávislé reprodukovatelné měření, RCT s lidmi |
| 2 | oficiální oznámení výrobce | recenzovaný článek s otevřeným kódem či daty |
| 3 | issue či odpověď správce v repozitáři | preprint s kódem |
| 4 | nezávislý technický článek | benchmark výrobce (**střet zájmů**, nejvýš „nízká“) |
| 5 | fórum, sociální sítě, blog | blog, fórum, sociální sítě |

Úroveň: stupeň 1-2 = vysoká, 3 = střední, 4 = nízká, 5 = velmi nízká.

**Produkty, ceny, právo (linka P)**

| Stupeň | Typ | Úroveň |
|---|---|---|
| 1 | platný předpis, oficiální rozhodnutí, oficiální ceník či podmínky k datu | vysoká |
| 2 | úřad, regulátor, oficiální statistika | vysoká |
| 3 | nezávislý test s metodikou (spotřebitelská organizace) | střední |
| 4 | odborný komentář s datem (advokát, specializovaný web) | nízká |
| 5 | média s odkazem na primární zdroj | nízká |
| 6 | recenze uživatelů, srovnávače, fóra | velmi nízká |

## 2. Modifikátory

- **Dolů (o stupeň):** malý vzorek, krátké sledování, chybí kontrolní skupina, výsledek z podskupiny, jiná populace než ta, na kterou se otázka ptá, preprint bez recenze, bez preregistrace, publikační zkreslení, střet zájmů, starý zdroj v rychle se měnící oblasti.
- **Nahoru (o stupeň):** velký a konzistentní efekt, závislost na dávce, nezávislá replikace, preregistrace s otevřenými daty.
- **Vyřadit z opory:** retrakce; vyjádření obav = nejvýš „podložené“ (řeší skript).

## 3. Úroveň důkazu k tvrzení (režim s G2)

- **GRADE-lite:** start vysoká (RCT či přehled RCT), nebo nízká (observační studie); o stupeň dolů za každou vážnou výhradu (riziko zkreslení, nekonzistence, nepřímost, nepřesnost, publikační zkreslení); nahoru za velký efekt či závislost na dávce. Uvádí-li jistotu GRADE kvalitní přehled, převezmi ji se zdrojem.
- **AMSTAR 2 nalehko** (kvalita přehledu, 7 kritických domén): registrovaný protokol, dostatečné hledání, vyloučené studie s důvody, riziko zkreslení studií, vhodná metaanalýza, zkreslení v interpretaci, publikační zkreslení. 0 vad = hlavní opora; 1 = nízká důvěra; ≥ 2 = jen mapa studií; neověřitelná doména se počítá jako nejistá.
- **SIFT** (mimo vědu): Stop (kdo je vydavatel a jaký má zájem) → Investigate (co o něm říkají jiní) → Find better coverage (nezávislé pokrytí) → Trace (původní kontext a datum).

Výsledek (vysoká / střední / nízká / velmi nízká) je vstup `uroven_dukazu` pro `citace.py stitky`.

## 4. Pravidlo štítků (PŘEDPOKLAD ke kalibraci)

Štítky odvozuje proces, ne dojem hlavního agenta. Pravidlo je ve skriptu (`PRAVIDLO_STITKU`, `SILA_STITKU`) a zreviduje se po dalším měření nebo namátkových kontrolách.

**Tvrdá vada G1:** mrtvý odkaz bez platného DOI, neexistující či nesedící DOI, retrakce. Oznámení o retrakci (Retraction Note) **není** retrahovaný článek: skript ho hlásí v `oznameni_k` a je to platný doklad o retrakci, ne o nálezech původního článku. **Výhrada G1:** vyjádření obav; čísla tvrzení ve zdroji chybí nebo citát nenalezen, obojí jen v plně načteném textu. Zástěna (souhlas s cookies, přihlášení), krátký či žádný text = „nenačteno“: není výhrada ani vada a do podílu vad pro G2 se nepočítá.

**Nezávislost:** stejné DOI (i v URL), stejná `skupina` nebo stejná doména = jeden zdroj; u katalogů a platforem vydavatelů (PubMed, arXiv, doi.org, velcí vydavatelé…) rozhoduje dílo (cesta URL), ne doména.

**Výchozí režim - bez G2** (tvrzení má `stitek_sberace`): štítek sběrače se nikdy nezesílí.

| Situace po G1 | Štítek | Akce |
|---|---|---|
| všechny zdroje mají tvrdou vadu | neznámé (neověřeno) | vyřadit |
| tvrzení nemá zdroj | neznámé (`odhad` zůstává) | ponechat s výhradou |
| „fakt“ a po vyřazení vadných < 2 nezávislé zdroje | podložené | ponechat |
| „fakt“ a výhrada G1 (i zdroj bez řádku G1) | podložené | ponechat |
| jinak | štítek sběrače | ponechat |

**Režim s G2** (cizí výstup, „ověř to“, vady G1 u > 20 % citací): štítek spočítá skript z verdiktů G2, počtu nezávislých zdrojů a úrovně důkazu; má-li tvrzení štítek sběrače, výsledek nebude silnější.

| Situace (po vyřazení vadných zdrojů) | Štítek | Akce |
|---|---|---|
| žádný použitelný zdroj | neznámé | vyřadit |
| G2 vyvrátil a nic nepotvrzuje | - | vyřadit |
| G2 vyvrátil, ale ≥ 1 zdroj potvrzuje aspoň částečně | sporné | ponechat |
| ≥ 2 nezávislé potvrzující zdroje, úroveň vysoká či střední, bez výhrady | fakt | ponechat |
| ≥ 1 potvrzující zdroj vysoké či střední úrovně; nebo ≥ 2 nezávislé při nízké | podložené | ponechat |
| 1 potvrzující zdroj nízké úrovně, nebo úroveň velmi nízká | neznámé („důkazy nestačí“) | ponechat |
| G2 jen „částečně“ | neznámé | přeformulovat a ověřit znovu |
| G2 neověřil | neznámé | ponechat s výhradou |

„Důkazy nestačí“ je platný výsledek, ne selhání rešerše.

## 5. Jistota závěru (L0)

Jistotu uvádí sběrač (pravidlo 5). Hlavní agent ji nezvyšuje; vyřadil-li nebo zeslabil-li skript tvrzení, na kterém závěr stojí, sníží ji: jistota je nejvýš nejslabší štítek nosných tvrzení [předpoklad]: fakt → vysoká (~80-90 %), podložené → střední (~60-75 %), sporné či neznámé → nízká (≤ 50 %). Vždy řekni, co by jistotu nejvíc změnilo.
