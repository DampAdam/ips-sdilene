#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""veda.py – sjednocený dotaz do odborných katalogů (linka V rešerší; jen standardní knihovna, Python >= 3.9).

Příkazy (výstup vždy JSON na stdout):
  dotaz TEMA [--filtr F] [--od ROK]           – jen sestaví dotazy (offline; pro protokol a znovuspuštění)
  hledej TEMA [--filtr F] [--max 20] [--od ROK] [--zdroje pubmed,europepmc,crossref] [--vystup X.json]
                                              – PubMed (E-utilities esearch + esummary), Europe PMC (REST
                                                search) a Crossref (works); sloučené záznamy
                                                {zdroj, id, doi, pmid, nazev, rok, typ_publikace, retrahovano}
  zname VYSLEDKY.json POLOZKA [POLOZKA ...]   – obsahují výsledky známé položky (DOI, PMID nebo název)?

Filtr = sjednocení typu publikace a výrazů v názvu (i pravopisné varianty): prehledy (výchozí; systematické
přehledy, metaanalýzy, přehledy přehledů), replikace, rct, zadny. TEMA piš anglicky a s variantami
(„"growth mindset" OR "growth mind-set"“), bez polí katalogů. Europe PMC hledá TEMA jen v názvu a abstraktu
(TITLE_ABS; v plných textech vracel mimotematické přehledy); Crossref booleovské operátory nezná, dostane
jen slova tématu a jeden výraz filtru (víc výrazů filtru přebilo téma) a název musí obsahovat filtr
i aspoň jedno slovo tématu.

Síť: přes citace.stahni (jen http/https, timeout, rozestup hostů, opakování při 429 a 5xx, limit velikosti).
Volitelně ${NCBI_API_KEY} (vyšší limit PubMedu); bez klíče to funguje pomaleji. Klíč nikdy není ve výstupu.
retrahovano: true = zdroj článek označuje jako retrahovaný; false = v tomto zdroji bez označení (≠ jistota);
null = nezjišťováno.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.parse
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import citace  # noqa: E402  (sdílená síťová vrstva a normalizace DOI)

VERZE = "0.2"
MAX_ZAZNAMU = 100              # strop --max na jeden zdroj
VYCHOZI_MAX = 20
MAX_CROSSREF_RADKU = 100       # Crossref vrací víc kandidátů, filtr podle názvu je zúží
PRAH_NAZEV = citace.PRAH_NAZEV  # shoda názvu u známých položek (předpoklad k měření, jako v citace.py)
ZDROJE = ("pubmed", "europepmc", "crossref")
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
CROSSREF = "https://api.crossref.org/works"

# Filtry: typ publikace ∪ výrazy v názvu. Výrazy jsou i v regulárním výrazu pro Crossref (filtr po stažení).
FILTRY: Dict[str, dict] = {
    "prehledy": {
        "pubmed_typy": ["systematic review[pt]", "meta-analysis[pt]"],
        "epmc_typy": ["systematic-review", "systematic review", "meta-analysis"],
        "nazev": ["meta-analysis", "meta-analyses", "meta analysis", "metaanalysis", "meta-analytic",
                  "systematic review", "systematic literature review", "umbrella review", "overview of reviews",
                  "review of reviews", "review of systematic reviews"],
        "regex": r"meta[\s-]?analy|systematic (?:literature )?review|umbrella review|"
                 r"(?:overview|review) of (?:systematic )?reviews",
    },
    "replikace": {
        "pubmed_typy": [],
        "epmc_typy": [],
        "nazev": ["replication", "replications", "replicate", "registered report", "many labs", "multi-site",
                  "multisite", "multi-lab", "multilab", "multi-laboratory"],
        "regex": r"replicat|registered report|many labs|multi[\s-]?(?:site|lab)",
    },
    "rct": {
        "pubmed_typy": ["randomized controlled trial[pt]"],
        "epmc_typy": ["randomized controlled trial"],
        "nazev": ["randomized", "randomised", "randomized controlled trial", "randomised controlled trial"],
        "regex": r"randomi[sz]ed",
    },
    "zadny": {"pubmed_typy": [], "epmc_typy": [], "nazev": [], "regex": ""},
}


# ---------------------------------------------------------------------------
# Sestavení dotazů
# ---------------------------------------------------------------------------
def _uvozovky(vyraz: str) -> str:
    return '"' + vyraz.replace('"', "") + '"'


def dotaz_pubmed(tema: str, filtr: str) -> str:
    f = FILTRY[filtr]
    casti = list(f["pubmed_typy"]) + [_uvozovky(v) + "[ti]" for v in f["nazev"]]
    return f"({tema})" + (" AND (" + " OR ".join(casti) + ")" if casti else "")


def dotaz_europepmc(tema: str, filtr: str, od: Optional[int] = None) -> str:
    f = FILTRY[filtr]
    casti = [f"PUB_TYPE:{_uvozovky(t)}" for t in f["epmc_typy"]] + [f"TITLE:{_uvozovky(v)}" for v in f["nazev"]]
    q = f"TITLE_ABS:({tema})" + (" AND (" + " OR ".join(casti) + ")" if casti else "")
    if od:
        q += f" AND PUB_YEAR:[{int(od)} TO 3000]"
    return q


def slova_pro_crossref(tema: str) -> str:
    """Crossref booleovské dotazy nezná: jen slova tématu bez operátorů, uvozovek a polí."""
    t = re.sub(r"\[[a-z]{1,10}\]", " ", tema, flags=re.I)
    t = re.sub(r"\b(?:AND|OR|NOT)\b", " ", t)
    t = re.sub(r"[\"()\[\]{}*:]", " ", t)
    slova: List[str] = []
    for s in t.split():
        if s.lower() not in (x.lower() for x in slova):
            slova.append(s)
    return " ".join(slova)


def dotaz_crossref(tema: str, filtr: str, n: int, od: Optional[int] = None) -> Dict[str, str]:
    f = FILTRY[filtr]
    navic = f["nazev"][0] if f["nazev"] else ""  # jeden výraz: dva (2026-10-31) přebily téma
    parametry = {"query.bibliographic": (slova_pro_crossref(tema) + " " + navic).strip(),
                 "rows": str(max(1, min(n, MAX_CROSSREF_RADKU))),
                 "select": "DOI,title,issued,type,updated-by,update-to,relation"}
    if od:
        parametry["filter"] = f"from-pub-date:{int(od)}"
    return parametry


def dotazy(tema: str, filtr: str = "prehledy", od: Optional[int] = None, n: int = VYCHOZI_MAX) -> dict:
    return {"pubmed": dotaz_pubmed(tema, filtr) + (f" AND {int(od)}:3000[dp]" if od else ""),
            "europepmc": dotaz_europepmc(tema, filtr, od),
            "crossref": dotaz_crossref(tema, filtr, n * 3 if FILTRY[filtr]["regex"] else n, od)}


# ---------------------------------------------------------------------------
# Síť
# ---------------------------------------------------------------------------
def _url(zaklad: str, parametry: Dict[str, str]) -> str:
    return zaklad + "?" + urllib.parse.urlencode(parametry, quote_via=urllib.parse.quote)


def _ncbi(cesta: str, parametry: Dict[str, str]) -> citace.Odpoved:
    parametry = dict(parametry, tool="reserse")
    klic = citace.klic_api("NCBI_API_KEY")
    if klic:
        parametry["api_key"] = klic
    return citace.stahni(_url(EUTILS + cesta, parametry), prijmout="application/json")


def _rok(x) -> Optional[int]:
    m = re.search(r"\b(1[89]\d\d|20\d\d)\b", str(x or ""))
    return int(m.group(1)) if m else None


def _zaznam(zdroj: str, id_: str, doi=None, pmid=None, nazev=None, rok=None, typy=None, retrahovano=None) -> dict:
    return {"zdroj": zdroj, "id": id_, "doi": citace.normalizuj_doi(doi) if doi else None,
            "pmid": str(pmid) if pmid and str(pmid).isdigit() else None,
            "nazev": citace._zkrat(html.unescape(citace._bez_tagu(str(nazev or ""))).strip(), 400) or None,
            "rok": rok, "typ_publikace": [str(t) for t in (typy or []) if t][:10], "retrahovano": retrahovano}


def hledej_pubmed(dotaz: str, n: int) -> Tuple[List[dict], dict]:
    odp = _ncbi("esearch.fcgi", {"db": "pubmed", "term": dotaz, "retmode": "json", "retmax": str(n),
                                  "sort": "relevance"})
    data = citace._json(odp) if odp.ok else None
    hledani = citace._slovnik(citace._slovnik(data).get("esearchresult"))
    if not odp.ok or not hledani:
        return [], {"stav": "chyba", "duvod": f"esearch: {odp.popis()}" if not odp.ok else "esearch: neplatná odpověď"}
    idy = [i for i in citace._seznam(hledani.get("idlist")) if str(i).isdigit()][:n]
    celkem = int(hledani["count"]) if str(hledani.get("count", "")).isdigit() else None
    if not idy:
        return [], {"stav": "ok", "celkem": celkem, "vraceno": 0, "duvod": ""}
    odp = _ncbi("esummary.fcgi", {"db": "pubmed", "id": ",".join(idy), "retmode": "json"})
    souhrn = citace._slovnik(citace._slovnik(citace._json(odp) if odp.ok else None).get("result"))
    if not odp.ok or not souhrn:
        return [], {"stav": "chyba", "celkem": celkem,
                    "duvod": f"esummary: {odp.popis()}" if not odp.ok else "esummary: neplatná odpověď"}
    zaznamy = []
    for pmid in idy:
        z = citace._slovnik(souhrn.get(pmid))
        if not z:
            continue
        doi = next((a.get("value") for a in citace._seznam(z.get("articleids"))
                    if isinstance(a, dict) and a.get("idtype") == "doi"), None)
        typy = [str(t) for t in citace._seznam(z.get("pubtype"))]
        zaznamy.append(_zaznam("pubmed", f"PMID:{pmid}", doi, pmid, z.get("title"),
                               _rok(z.get("sortpubdate") or z.get("pubdate")), typy,
                               any(t.lower() == "retracted publication" for t in typy)))
    return zaznamy, {"stav": "ok", "celkem": celkem, "vraceno": len(zaznamy), "duvod": ""}


def hledej_europepmc(dotaz: str, n: int) -> Tuple[List[dict], dict]:
    odp = citace.stahni(_url(EPMC, {"query": dotaz, "format": "json", "pageSize": str(n), "resultType": "lite"}),
                        prijmout="application/json")
    data = citace._slovnik(citace._json(odp) if odp.ok else None)
    if not odp.ok or "resultList" not in data:
        return [], {"stav": "chyba", "duvod": odp.popis() if not odp.ok else "neplatná odpověď"}
    zaznamy = []
    for r in citace._seznam(citace._slovnik(data.get("resultList")).get("result"))[:n]:
        if not isinstance(r, dict):
            continue
        typy = [t.strip() for t in str(r.get("pubType") or "").split(";") if t.strip()]
        zaznamy.append(_zaznam("europepmc", f"{r.get('source', '')}:{r.get('id', '')}", r.get("doi"), r.get("pmid"),
                               r.get("title"), _rok(r.get("pubYear")), typy,
                               any(t.lower() == "retracted publication" for t in typy)))
    celkem = data.get("hitCount") if isinstance(data.get("hitCount"), int) else None
    return zaznamy, {"stav": "ok", "celkem": celkem, "vraceno": len(zaznamy), "duvod": ""}


def kmeny_tematu(tema: str) -> set:
    """Kmeny slov tématu (bez operátorů a stop-slov) pro kontrolu, že název Crossrefu je k tématu."""
    return set(citace.tokeny(slova_pro_crossref(tema)))


def hledej_crossref(parametry: Dict[str, str], n: int, regex: str,
                    kmeny: Optional[set] = None) -> Tuple[List[dict], dict]:
    odp = citace.stahni(_url(CROSSREF, parametry), prijmout="application/json")
    zprava = citace._slovnik(citace._slovnik(citace._json(odp) if odp.ok else None).get("message"))
    if not odp.ok or "items" not in zprava:
        return [], {"stav": "chyba", "duvod": odp.popis() if not odp.ok else "neplatná odpověď"}
    vzor = re.compile(regex, re.I) if regex else None
    zaznamy, odfiltrovano, mimo_tema = [], 0, 0
    for m in citace._seznam(zprava.get("items")):
        if not isinstance(m, dict):
            continue
        doi = citace.normalizuj_doi(str(m.get("DOI") or ""))
        nazev = (citace._seznam(m.get("title")) or [""])[0]
        if vzor and not vzor.search(str(nazev)):
            odfiltrovano += 1
            continue
        if kmeny and not kmeny & set(citace.tokeny(str(nazev))):
            mimo_tema += 1  # např. „Fixed Effect vs Random Effects Meta-Analyses“ k jakémukoli tématu
            continue
        retrakce, _ = citace.zaznamy_retrakci_crossref(m, doi or "")
        dp = citace._seznam(citace._slovnik(m.get("issued")).get("date-parts"))
        rok = dp[0][0] if dp and isinstance(dp[0], list) and dp[0] and isinstance(dp[0][0], int) else None
        zaznamy.append(_zaznam("crossref", f"DOI:{doi}", doi, None, nazev, rok, [m.get("type")],
                               any(z["stav"] == "retrahovano" for z in retrakce)))
        if len(zaznamy) >= n:
            break
    celkem = zprava.get("total-results") if isinstance(zprava.get("total-results"), int) else None
    return zaznamy, {"stav": "ok", "celkem": celkem, "vraceno": len(zaznamy), "odfiltrovano_podle_nazvu": odfiltrovano,
                     "odfiltrovano_mimo_tema": mimo_tema, "duvod": ""}


# ---------------------------------------------------------------------------
# Sloučení a známé položky
# ---------------------------------------------------------------------------
def _klice(z: dict) -> List[str]:
    k = []
    if z.get("doi"):
        k.append("doi:" + z["doi"].lower())
    if z.get("pmid"):
        k.append("pmid:" + z["pmid"])
    if z.get("nazev"):
        k.append("nazev:" + citace._norm_nazev(z["nazev"]))
    return k


def sluc(zaznamy: List[dict]) -> List[dict]:
    """Sloučí záznamy téhož článku z různých zdrojů (DOI, PMID, normalizovaný název); pořadí = první výskyt."""
    vysledek: List[dict] = []
    index: Dict[str, int] = {}
    for z in zaznamy:
        cil = next((index[k] for k in _klice(z) if k in index), None)
        if cil is None:
            vysledek.append(dict(z, nalezeno_v=[z["zdroj"]]))
            cil = len(vysledek) - 1
        else:
            s = vysledek[cil]
            for pole in ("doi", "pmid", "nazev", "rok"):
                if s.get(pole) is None and z.get(pole) is not None:
                    s[pole] = z[pole]
            if z["zdroj"] not in s["nalezeno_v"]:
                s["nalezeno_v"].append(z["zdroj"])
            s["typ_publikace"] = list(dict.fromkeys(s["typ_publikace"] + z["typ_publikace"]))[:10]
            hodnoty = (s.get("retrahovano"), z.get("retrahovano"))
            s["retrahovano"] = True if True in hodnoty else (False if False in hodnoty else None)
        for k in _klice(vysledek[cil]):
            index.setdefault(k, cil)
    return vysledek


def hledej(tema: str, filtr: str = "prehledy", n: int = VYCHOZI_MAX, od: Optional[int] = None,
           zdroje: Tuple[str, ...] = ZDROJE) -> dict:
    tema = (tema or "").strip()
    if not tema:
        return {"stav": "chyba", "duvod": "prázdné téma"}
    if filtr not in FILTRY:
        return {"stav": "chyba", "duvod": f"neznámý filtr (povolené: {', '.join(FILTRY)})"}
    n = max(1, min(int(n or VYCHOZI_MAX), MAX_ZAZNAMU))
    q = dotazy(tema, filtr, od, n)
    vsechny: List[dict] = []
    stavy: Dict[str, dict] = {}
    for zdroj in zdroje:
        try:
            if zdroj == "pubmed":
                zz, st = hledej_pubmed(q["pubmed"], n)
            elif zdroj == "europepmc":
                zz, st = hledej_europepmc(q["europepmc"], n)
            elif zdroj == "crossref":
                zz, st = hledej_crossref(q["crossref"], n, FILTRY[filtr]["regex"], kmeny_tematu(tema))
            else:
                zz, st = [], {"stav": "chyba", "duvod": "neznámý zdroj"}
        except Exception as e:  # jeden zdroj nesmí shodit ostatní
            zz, st = [], {"stav": "chyba", "duvod": f"{type(e).__name__}: {e}"[:200]}
        vsechny += zz
        stavy[zdroj] = st
    ok = [z for z, st in stavy.items() if st.get("stav") == "ok"]
    stav = "ok" if len(ok) == len(stavy) else ("castecne" if ok else "chyba")
    zaznamy = sluc(vsechny)
    return {"stav": stav, "verze": VERZE, "datum": time.strftime("%Y-%m-%d"), "tema": tema, "filtr": filtr,
            "od": od, "dotazy": {z: q[z] for z in zdroje if z in q}, "zdroje": stavy, "pocet": len(zaznamy),
            "zaznamy": zaznamy}


def _druh_polozky(polozka: str) -> Tuple[str, str]:
    p = (polozka or "").strip()
    doi = citace.normalizuj_doi(p)
    if doi:
        return "doi", doi.lower()
    m = re.fullmatch(r"(?:pmid\s*:?\s*)?(\d{1,9})", p, re.I)
    if m:
        return "pmid", str(int(m.group(1)))
    return "nazev", p


def zname(vysledky: dict, polozky: List[str]) -> dict:
    """Kontrola úplnosti: které známé položky výsledky obsahují (DOI a PMID přesně, název přibližně)."""
    zaznamy = [z for z in citace._seznam(citace._slovnik(vysledky).get("zaznamy")) if isinstance(z, dict)]
    nalezeno, chybi = [], []
    for p in polozky:
        druh, hodnota = _druh_polozky(p)
        shoda = None
        for z in zaznamy:
            if druh == "doi" and str(z.get("doi") or "").lower() == hodnota:
                shoda = z
            elif druh == "pmid" and str(z.get("pmid") or "") == hodnota:
                shoda = z
            elif druh == "nazev" and z.get("nazev") and citace.podobnost_nazvu(hodnota, z["nazev"]) >= PRAH_NAZEV:
                shoda = z
            if shoda:
                break
        if shoda:
            nalezeno.append({"polozka": p, "druh": druh, "id": shoda.get("id"), "nalezeno_v": shoda.get("nalezeno_v")})
        else:
            chybi.append({"polozka": p, "druh": druh})
    n = len(polozky)
    return {"stav": "ok", "celkem": n, "nalezeno": nalezeno, "chybi": chybi,
            "uplnost": round(len(nalezeno) / n, 3) if n else None,
            "poznamka": "chybí-li známá položka, oprav dotaz (termíny, varianty, index), ne závěr"}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
class _ChybaArgumentu(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _ChybaArgumentu(message)


def main(argv: Optional[List[str]] = None) -> int:
    p = _Parser(prog="veda.py", description="Sjednocený dotaz do odborných katalogů (výstup JSON).")
    sub = p.add_subparsers(dest="prikaz")
    for nazev in ("dotaz", "hledej"):
        s = sub.add_parser(nazev)
        s.add_argument("tema")
        s.add_argument("--filtr", default="prehledy", choices=list(FILTRY))
        s.add_argument("--od", type=int, help="nejstarší rok vydání")
        s.add_argument("--max", type=int, default=VYCHOZI_MAX, help=f"záznamů na zdroj (≤ {MAX_ZAZNAMU})")
        if nazev == "hledej":
            s.add_argument("--zdroje", default=",".join(ZDROJE))
            s.add_argument("--vystup", help="kam uložit celý výsledek (JSON)")
    s = sub.add_parser("zname")
    s.add_argument("vysledky")
    s.add_argument("polozky", nargs="+")
    try:
        a = p.parse_args(argv)
        if not a.prikaz:
            raise _ChybaArgumentu("chybí příkaz (dotaz, hledej, zname)")
        if a.prikaz == "dotaz":
            citace._vypis({"stav": "ok", "tema": a.tema, "filtr": a.filtr,
                           "dotazy": dotazy(a.tema, a.filtr, a.od, max(1, min(a.max, MAX_ZAZNAMU)))})
        elif a.prikaz == "hledej":
            zdroje = tuple(z.strip() for z in a.zdroje.split(",") if z.strip())
            nezname = [z for z in zdroje if z not in ZDROJE]
            if nezname or not zdroje:
                raise _ChybaArgumentu(f"neznámé zdroje {nezname} (povolené: {', '.join(ZDROJE)})")
            vysl = hledej(a.tema, a.filtr, a.max, a.od, zdroje)
            if a.vystup:  # i neúspěšný běh: dotazy a stavy zdrojů patří do protokolu
                with open(a.vystup, "w", encoding="utf-8") as f:
                    json.dump(vysl, f, ensure_ascii=False, indent=1)
            citace._vypis(vysl)
            return 0 if vysl.get("stav") in ("ok", "castecne") else 1
        elif a.prikaz == "zname":
            with open(a.vysledky, encoding="utf-8") as f:
                vysl = json.load(f)
            citace._vypis(zname(vysl, a.polozky))
        return 0
    except _ChybaArgumentu as e:
        citace._vypis({"stav": "chyba", "duvod": f"argumenty: {e}"[:300]})
        return 2
    except OSError as e:
        citace._vypis({"stav": "chyba", "duvod": f"soubor: {e}"[:300]})
        return 1
    except ValueError as e:
        citace._vypis({"stav": "chyba", "duvod": f"vstup: {e}"[:300]})
        return 2
    except Exception as e:  # pojistka: výstup vždy JSON
        citace._vypis({"stav": "chyba", "duvod": f"{type(e).__name__}: {e}"[:300]})
        return 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
