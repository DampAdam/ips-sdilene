# ips-sdilene

Veřejné pluginy pro Claude (Claude Code a aplikace Claude): skilly a podagenti, které autor sám používá a sdílí s ostatními.

## Pluginy

### reserse (verze 1.3.0)

Rešerše s ověřenými citacemi: izolovaný sběrač hledá podle pěti pravidel a skript kontroluje odkazy, DOI, retrakce a čísla u všech citací.

- Skilly: `reserse`
- Podagenti: `reserse-overovac`, `reserse-sberac`

### tvorba (verze 1.0.0)

Asistent tvorby čehokoli od nápadu přes koncept, návrh, specifikaci a plán k výstupu a učení; AI rozšiřuje a kritizuje, rozhoduje uživatel.

- Skilly: `tvorba`

### uceni (verze 1.0.0)

AI tutor podle výzkumu efektivní výuky: učí cokoli (předmět, téma, dovednost), vede nápovědami místo hotových řešení, zkouší, připravuje ke zkoušce a plánuje opakování.

- Skilly: `ai-tutor`

## Instalace

### Claude Code

```
/plugin marketplace add DampAdam/ips-sdilene
/plugin install reserse@ips-sdilene
/plugin install tvorba@ips-sdilene
/plugin install uceni@ips-sdilene
```

### Aplikace Claude

1. Otevři Settings a v části s pluginy (marketplace) přidej GitHub repozitář `DampAdam/ips-sdilene`.
2. Nainstaluj plugin, který chceš používat.

## Původ

Obsah se generuje automaticky; ručně se tu neupravuje a při dalším exportu se přepíše. Chyby a nápady pište do issues, jsou vítané.
