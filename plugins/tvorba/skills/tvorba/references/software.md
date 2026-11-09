# Software, automatizace, AI skilly a agenti

## Pravidla

1. **Deterministicky první.** Jde-li úlohu popsat pevnými kroky, skript nebo workflow; LLM jen tam, kde je potřeba úsudek nad nestrukturovaným vstupem. Agenta až když workflow nestačí (Anthropic, Building effective agents: nejjednodušší řešení, složitost jen když je potřeba).
2. **Spec-driven pro věci, které se budou udržovat:** spec → plán → úkoly → implementace s TDD → revize. Vibe coding jen na prototyp k zahození (ověření předpokladu v kroku 2-3).
3. **AI skilly a agenti: nejdřív evaly.** Před napsáním 5-10 testovacích vstupů s očekávaným chováním; po každé změně znovu (analogie TDD pro prompty).
4. **Měř, neodhaduj zrychlení.** U zkušených vývojářů ve vlastním kódu bylo s AI zpomalení o 19 % při pocitu zrychlení (METR 2025); zapisuj čas do záznamu projektu.
5. **Malé kroky a revize:** časté commity, možnost vrátit změnu; AI zesiluje silné i slabé stránky postupu (DORA 2025).
6. **Kontext:** co nejmenší sada užitečných informací; pro dlouhé úlohy poznámky a podagenti (Anthropic, context engineering).

## Mapování na kroky

| Krok | Artefakt | Praxe | Brána |
|---|---|---|---|
| 1-3 | poznámka projektu (záznam) | tento skill, část A | volba varianty + kill kritéria |
| 0 (jednou za projekt) | AGENTS.md / CLAUDE.md, principy | příkazy pro testy, konvence | |
| 4 Specifikace | spec.md (požadavky v EARS, akceptační kritéria) | otázky místo předpokladů; každý požadavek testovatelný | žádné otevřené otázky |
| 5 Plán | plan.md + tasks.md, ADR | úkoly 2-5 min až 1-2 h s cestami k souborům a testy; kontrola konzistence spec-plán-úkoly | každý úkol má test a hotovo |
| 6 Výstup | kód + testy | TDD (red-green-refactor), implementace po úkolech, revize v čistém kontextu | testy zelené, revize bez blokujících nálezů |
| 7 Provoz a učení | metriky, poznámky, úprava AGENTS.md | retrospektiva, poučení do pravidel projektu | metrika z Účelu |

## Výstupem je AI skill, prompt nebo agent

Kroky 4-6 jako u softwaru; evaly (pravidlo 3) do `evals/` skillu.
