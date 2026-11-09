#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""citace.py – brána G1 rešerší: ověřování citací (jen standardní knihovna, Python >= 3.9).

Příkazy (výstup vždy JSON na stdout):
  url URL                                   – stav odkazu (+ Wayback u mrtvých)
  doi DOI [--nazev T] [--autor A] [--rok R] – metadata z Crossrefu / OpenAlexu a porovnání
  retrakce DOI                              – retrakce, vyjádření obav, opravy
  pasaze --tvrzeni T [--tvrzeni-en T_EN] [--citat C] --url U [--doi D] [--k 3]
                                            – nejlepší pasáže zdroje k tvrzení (bez modelu); skóruje se
                                              podle --tvrzeni-en, je-li zadané; --citat = doslovný citát
                                              ze zdroje (pole "citat": doslovne|temer|nenalezen|nelze)
  davka VSTUP.jsonl VYSTUP.jsonl            – dávkové zpracování (řádek může mít i tvrzeni_en, citat)
  stitky VSTUP.json [--g1 DAVKA.jsonl]      – štítek každého tvrzení: se „stitek_sberace“ a bez G2 = štítek
                                              sběrače zeslabený vadou G1 (nikdy zesílený); s verdikty G2 =
                                              pravidlo PRAVIDLO_STITKU (předpoklad), nejvýš štítek sběrače;
                                              pole "g1" = podíl vad (tvrdé vady + nesedící čísla v plně
                                              načteném textu) a zvlášť podíl nenačtených citací (zástěna,
                                              částečný text); g2_doporucen jen podle vad (> 20 %);
                                              "zdroje_bez_g1" = zdroje bez řádku G1 (doplnit do dávky)
  vytahni ZPRAVA.md [--vystup X.jsonl]      – tvrzení s citacemi z Markdown zprávy do JSONL pro davka
  zadani-g2 DAVKA.jsonl --tvrzeni VSTUP.jsonl [--id ID …] [--po 8]
                                            – zadání ověřovače G2 po dávkách (pasáže doslova ze skriptu,
                                              zdroje s tvrdou vadou G1 vynechá)
  verdikty DAVKA.jsonl [--g2 G] [--tvrzeni T] [--stitky S] [--g3 G3] [--vystup X.md]
                                            – tabulka verdiktů bran v Markdownu (pole "markdown")

Pasáže jsou jen nápověda (Z2b: podvržené tvrzení nerozliší). M0-lite (sada reserse 1.2.0): štítek dává
sběrač a „stitky“ ho jen zeslabí; verdikt o tvrzení dává ověřovač G2, jen když proběhl.
Oznámení o retrakci či opravě není retrahovaný článek (retrakce: "oznameni_k").

Stavy pasáží: nalezeno | nenalezeno (= neprokázáno, ne „zdroj to neříká“; jen u textu >= 5 000 znaků) |
castecne_nacteno (krátký text < 5 000 znaků bez nalezené pasáže; u článku ani po zálohách) | nenacteno (i zástěna:
souhlas s cookies, přihlášení, kontrola robota… – pole "zastena", důvod „zástěna“). Nesedící čísla a nenalezený
citát se posuzují jen v plně načteném textu; nenačtená citace není vada (pilot 2026-11-04).
Zálohy: 5xx = jedno opakování po 2–5 s, pak abstrakt z Europe PMC; 401/403 a nenačtené PDF = nejnovější
snímek Waybacku (datum ve "zdroj_textu"); tenký text článku a zástěna = Europe PMC, OpenAlex, Wayback.
403/407 od proxy relace se neopakuje ani neobchází (ani Waybackem). PDF jen s volitelným pypdf / pdftotext.

Bezpečnost: obsah stránek se nikdy nespouští ani nevyhodnocuje; jen schémata http/https
(ani přesměrování jinam nevede); nejvýš 5 přesměrování; nejvýš 3 MB na stránku;
výstup neobsahuje text stránky mimo pasáže <= 400 znaků (metadata API jsou zkrácená).
"""
from __future__ import annotations

import argparse
import bisect
import concurrent.futures
import dataclasses
import heapq
import html as html_mod
import http.client
import importlib.util
import io
import json
import logging
import math
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zlib
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Konstanty
# ---------------------------------------------------------------------------
VERZE = "0.5.3"
# Poctivá identifikace bez e-mailu (žádný mailto v User-Agent).
USER_AGENT = "citace-prototyp/0.2 (overovani citaci; Python-urllib)"
TIMEOUT = 20.0                 # s na jeden požadavek (připojení i čtení těla)
MAX_BAJTU = 3 * 1024 * 1024    # max 3 MB na stránku
MAX_PRESMEROVANI = 5
MEZERA_HOST = 1.0              # s mezi požadavky na stejný host
MAX_OPAKOVANI_429 = 2
ZAKLAD_CEKANI_429 = 2.0        # s; exponenciálně 2, 4, …
MAX_CEKANI_429 = 30.0
MAX_SOUBEZNE = 4               # max souběžných požadavků (globálně)
MAX_PASAZ = 400                # max znaků jedné pasáže ve výstupu
MIN_TEXT = 200                 # méně znaků textu = stránka „bez textu“
MAX_CACHE = 16                 # počet odpovědí v paměťové cache (jen v rámci běhu)
# 5xx: jedno opakování po CEKANI_5XX s (Retry-After se respektuje v mezích 2–5 s); 501 není přechodná chyba.
MAX_OPAKOVANI_5XX = 1
CEKANI_5XX = 3.0
CEKANI_5XX_MIN = 2.0
CEKANI_5XX_MAX = 5.0
BEZ_OPAKOVANI_5XX = frozenset({501, 505})
# Krátký text (jakákoli stránka) bez nalezené pasáže = „castecne_nacteno“, ne vada; u článkové stránky (DOI,
# časopis, arXiv abs, abstrakt) se navíc zkoušejí zálohy. Předpoklad k měření (Z2: tenké stránky
# 1 861–3 095 znaků, plné texty > 8 000; pilot 2026-11-04: stránka se souhlasem s cookies 438 znaků).
MIN_CLANEK_TEXT = 5000
# Zástěna (souhlas s cookies, přihlášení, kontrola robota, předplatné, „zapněte JavaScript“): krátký text
# s aspoň MIN_FRAZI_ZASTENY různými frázemi (pod MAX_TEXT_JEDNA_FRAZE znaky stačí jedna) a bez nalezené
# pasáže či citátu = „nenacteno“ s důvodem „zástěna“, ne vada. Prahy jsou předpoklad k měření.
MIN_FRAZI_ZASTENY = 2
MAX_TEXT_JEDNA_FRAZE = 1500
# PDF (volitelně pypdf, jinak pdftotext): strop stran a času, ať jedno PDF nezdrží dávku.
MAX_STRAN_PDF = 300
MAX_CAS_PDF = 30.0

# PRAH: předpoklad k měření, ne kalibrovaná hodnota. Skóre pasáže je 0–1
# (vážená kombinace normalizovaného BM25, pokrytí pořadí přes difflib a shody čísel).
# Hodnota 0.40 je odhad z ručních příkladů; je potřeba ji změřit na sadě
# tvrzení se známou odpovědí (přesnost/úplnost) a případně upravit.
PRAH = 0.40
# Práh podobnosti názvu u porovnání metadat DOI – také předpoklad k měření.
PRAH_NAZEV = 0.85

BM25_K1 = 1.2
BM25_B = 0.75
DELKA_KMENE = 5                # hrubé „stemování“ ořezem (předpoklad, funguje pro EN i CZ)
VAHY_S_CISLY = {"bm25": 0.45, "difflib": 0.20, "cisla": 0.35}
VAHY_BEZ_CISEL = {"bm25": 0.70, "difflib": 0.30, "cisla": 0.0}
MAX_KANDIDATU_DIFFLIB = 300

# Citát (doslovný úryvek ze zdroje, jak ho uvedl sběrač): podobnost 0–1 nejlepšího úseku textu
# po normalizaci mezer, uvozovek, pomlček a velikosti písmen.
# PRAH_CITAT_DOSLOVNE: předpoklad k měření (přesná shoda = 1,0; 0,98 snese drobný šum, např. dělení
#   slov v PDF nebo jeden překlep na ~50 znacích).
# PRAH_CITAT_TEMER: předpoklad k měření (0,85 ≈ jedno až dvě změněná slova v citátu o ~15 slovech).
PRAH_CITAT_DOSLOVNE = 0.98
PRAH_CITAT_TEMER = 0.85
MAX_CITAT = 1000               # znaků normalizovaného citátu pro přibližné hledání (delší se zkrátí)
MAX_KANDIDATU_CITAT = 5        # počet oken z hrubého průchodu, která se zpřesní přes difflib
MAX_MEZERA_VYPUSTKY = 2000     # max znaků mezi úseky citátu s výpustkou („…“, „[...]“)

# ---------------------------------------------------------------------------
# Pomocné textové funkce
# ---------------------------------------------------------------------------
_NEVIDITELNE = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad]")
_RIDICI = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _bez_diakritiky(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _normalizuj(s: str) -> str:
    """Normalizace pro porovnávání: bez neviditelných znaků, bez diakritiky, malá písmena."""
    return _bez_diakritiky(_NEVIDITELNE.sub("", s)).lower()


def _zkrat(s: Optional[str], n: int = 300) -> Optional[str]:
    if s is None:
        return None
    s = _RIDICI.sub("", s)
    return s if len(s) <= n else s[: n - 1] + "…"


def _bezpecny_kus(s: Optional[str], n: int) -> str:
    """Krátký kus textu od serveru (hlavička, typ obsahu) pro pole duvod: zkrácený a bez pokynů pro AI."""
    kus = _zkrat(s or "", n) or ""
    return "[vynecháno]" if obsahuje_pokyn(kus) else kus


# ---------------------------------------------------------------------------
# Síť
# ---------------------------------------------------------------------------
class SitovaChyba(Exception):
    """Chyba na úrovni sítě. druh: dns | timeout | tls | spojeni | schema | presmerovani | zakazano."""

    def __init__(self, druh: str, zprava: str):
        super().__init__(zprava)
        self.druh = druh
        self.zprava = zprava


@dataclass
class Odpoved:
    status: Optional[int]
    url: str
    hlavicky: Dict[str, str] = field(default_factory=dict)
    telo: bytes = b""
    oriznuto: bool = False
    chyba: Optional[str] = None      # druh síťové chyby (viz SitovaChyba), None = HTTP odpověď
    zprava: str = ""
    presmerovani: int = 0
    opakovani: int = 0               # počet opakování po 5xx

    @property
    def ok(self) -> bool:
        return self.chyba is None and self.status is not None and 200 <= self.status < 300

    @property
    def typ(self) -> str:
        return self.hlavicky.get("content-type", "").split(";")[0].strip().lower()

    def popis(self) -> str:
        if self.chyba:
            return f"síť: {self.chyba} ({self.zprava})" if self.zprava else f"síť: {self.chyba}"
        return f"HTTP {self.status}"


def povolena_url(url: str) -> bool:
    try:
        cast = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    return cast.scheme.lower() in ("http", "https") and bool(cast.hostname)


def _bezpecna_url(url: str) -> str:
    """Zakóduje mezery a ne-ASCII znaky (IDNA host, procentové kódování cesty)."""
    c = urllib.parse.urlsplit(url.strip())
    host = c.hostname or ""
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        pass
    netloc = f"[{host}]" if ":" in host else host  # IPv6; přihlašovací údaje z URL se zahazují
    if c.port:
        netloc += f":{c.port}"
    cesta = urllib.parse.quote(c.path, safe="/%:@!$&'()*+,;=-._~")
    dotaz = urllib.parse.quote(c.query, safe="=&%/:?+,;@!$'()*-._~")
    return urllib.parse.urlunsplit((c.scheme.lower(), netloc, cesta or "/", dotaz, ""))


_OPENER = None
_OPENER_ZAMEK = threading.Lock()


def _opener():
    """OpenerDirector jen s HTTP/HTTPS (žádný file:, ftp:, data:) a bez automatických přesměrování."""
    global _OPENER
    with _OPENER_ZAMEK:
        if _OPENER is None:
            ctx = ssl.create_default_context()  # ověřování TLS zůstává zapnuté (SSL_CERT_FILE)
            o = urllib.request.OpenerDirector()
            for h in (
                urllib.request.ProxyHandler(),
                urllib.request.UnknownHandler(),
                urllib.request.HTTPHandler(),
                urllib.request.HTTPSHandler(context=ctx),
                urllib.request.HTTPDefaultErrorHandler(),
                urllib.request.HTTPErrorProcessor(),
            ):
                o.add_handler(h)
            _OPENER = o
        return _OPENER


def _dns_existuje(host: Optional[str]) -> Optional[bool]:
    """True = název se přeloží, False = neexistuje (NXDOMAIN), None = nelze rozhodnout."""
    if not host:
        return None
    try:
        socket.getaddrinfo(host, None)
        return True
    except socket.gaierror as e:
        nenalezeno = {getattr(socket, n) for n in ("EAI_NONAME", "EAI_NODATA") if hasattr(socket, n)}
        return False if e.errno in nenalezeno else None
    except OSError:
        return None


_INTERNI_CACHE: Dict[str, bool] = {}


def _interni_host(host: Optional[str]) -> bool:
    """True pro loopback/privátní/link-local adresy (ochrana proti SSRF, např. 169.254.169.254).
    Nepřeložitelný název není interní (rozhodne až požadavek). Pozor: DNS rebinding neřeší."""
    import ipaddress
    if not host:
        return True
    h = host.strip("[]").lower().rstrip(".")
    if h == "localhost" or h.endswith((".localhost", ".local", ".internal", ".localdomain")):
        return True
    if h in _INTERNI_CACHE:
        return _INTERNI_CACHE[h]
    adresy = []
    try:
        adresy = [ipaddress.ip_address(h)]
    except ValueError:
        try:
            adresy = [ipaddress.ip_address(i[4][0].split("%")[0]) for i in socket.getaddrinfo(h, None)]
        except (OSError, UnicodeError, ValueError):
            adresy = []
    vysl = any(a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_multicast
               or a.is_unspecified for a in adresy)
    _INTERNI_CACHE[h] = vysl
    return vysl


def _preloz_chybu(duvod, url: str) -> SitovaChyba:
    if isinstance(duvod, socket.gaierror):
        nenalezeno = {getattr(socket, n) for n in ("EAI_NONAME", "EAI_NODATA") if hasattr(socket, n)}
        if duvod.errno in nenalezeno:
            return SitovaChyba("dns", "název serveru nelze přeložit")
        return SitovaChyba("spojeni", f"DNS dočasně selhalo: {duvod}")
    if isinstance(duvod, (socket.timeout, TimeoutError)):
        return SitovaChyba("timeout", "vypršel časový limit")
    if isinstance(duvod, ssl.SSLCertVerificationError):
        return SitovaChyba("tls", "certifikát nelze ověřit")
    if isinstance(duvod, ssl.SSLError):
        return SitovaChyba("tls", f"TLS: {duvod}"[:200])
    text = str(duvod)
    if "Tunnel connection failed" in text:
        # Přes proxy se DNS chyba projeví jako selhání tunelu (502); rozhodneme místním DNS.
        if _dns_existuje(urllib.parse.urlsplit(url).hostname) is False:
            return SitovaChyba("dns", "název serveru nelze přeložit (proxy: tunel selhal)")
        return SitovaChyba("spojeni", f"proxy: {text}"[:200])
    if "timed out" in text.lower():
        return SitovaChyba("timeout", "vypršel časový limit")
    return SitovaChyba("spojeni", text[:200])


def _precti(resp, max_bajtu: int, deadline: float) -> Tuple[bytes, bool]:
    # read1 = nejvýš jedno volání recv: kontrola deadline proběhne aspoň jednou za timeout soketu.
    # resp.read(n) by čekalo, dokud nepřijde celých n bajtů, takže server posílající 1 bajt
    # za pár sekund by celkový limit obešel (každé recv se vejde do timeoutu soketu).
    cti = getattr(resp, "read1", None)
    if not callable(cti):
        cti = resp.read
    casti: List[bytes] = []
    celkem = 0
    while True:
        if time.monotonic() > deadline:
            raise SitovaChyba("timeout", "čtení těla překročilo časový limit")
        kus = cti(65536)
        if not kus:
            return b"".join(casti), False
        casti.append(kus)
        celkem += len(kus)
        if celkem > max_bajtu:
            return b"".join(casti)[:max_bajtu], True


def _jeden_pozadavek(url: str, hlavicky: Dict[str, str], timeout: float, max_bajtu: int) -> Odpoved:
    """Jeden GET bez sledování přesměrování. HTTP chyby vrací jako Odpoved, síťové vyhazuje."""
    req = urllib.request.Request(url, headers=hlavicky, method="GET")
    zacatek = time.monotonic()
    try:
        resp = _opener().open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        resp = e
    except urllib.error.URLError as e:
        raise _preloz_chybu(e.reason, url)
    except http.client.HTTPException as e:
        # Jen název výjimky: např. BadStatusLine nese text stavového řádku od serveru.
        raise SitovaChyba("spojeni", f"neplatná odpověď serveru ({type(e).__name__})")
    except ValueError as e:
        raise SitovaChyba("spojeni", f"{type(e).__name__}: {e}"[:200])
    except OSError as e:
        raise _preloz_chybu(e, url)
    try:
        status = getattr(resp, "status", None) or resp.getcode()
        hl = {k.lower(): v for k, v in (resp.headers.items() if resp.headers else [])}
        try:
            telo, oriznuto = _precti(resp, max_bajtu, zacatek + timeout)
        except SitovaChyba:
            raise
        except (http.client.HTTPException, OSError) as e:
            raise _preloz_chybu(e, url) if isinstance(e, OSError) else \
                SitovaChyba("spojeni", f"přerušené tělo odpovědi ({type(e).__name__})")
    finally:
        try:
            resp.close()
        except Exception:
            pass
    return Odpoved(status=status, url=url, hlavicky=hl, telo=telo, oriznuto=oriznuto)


class _OmezovacHostu:
    """Rozestup >= MEZERA_HOST mezi začátky požadavků na stejný host (i mezi vlákny)."""

    def __init__(self):
        self._zamek = threading.Lock()
        self._dalsi: Dict[str, float] = {}

    def cekej(self, host: str) -> None:
        with self._zamek:
            ted = time.monotonic()
            slot = max(ted, self._dalsi.get(host, 0.0))
            self._dalsi[host] = slot + MEZERA_HOST
        pauza = slot - ted
        if pauza > 0:
            time.sleep(pauza)

    def vycisti(self) -> None:
        with self._zamek:
            self._dalsi.clear()


_OMEZOVAC = _OmezovacHostu()
_SEMAFOR = threading.BoundedSemaphore(MAX_SOUBEZNE)
_CACHE: "OrderedDict[tuple, Odpoved]" = OrderedDict()
_CACHE_ZAMEK = threading.Lock()


def vycisti_cache() -> None:
    with _CACHE_ZAMEK:
        _CACHE.clear()
    _OMEZOVAC.vycisti()


def _cekani_429(retry_after: Optional[str], pokus: int) -> float:
    if retry_after and retry_after.strip().isdigit():
        return min(float(retry_after.strip()), MAX_CEKANI_429)
    return min(ZAKLAD_CEKANI_429 * (2 ** pokus), MAX_CEKANI_429)


def _cekani_5xx(retry_after: Optional[str]) -> float:
    if retry_after and retry_after.strip().isdigit():
        return min(max(float(retry_after.strip()), CEKANI_5XX_MIN), CEKANI_5XX_MAX)
    return CEKANI_5XX


def _dekomprimuj(odp: Odpoved, max_bajtu: int) -> None:
    kod = odp.hlavicky.get("content-encoding", "").strip().lower()
    if kod in ("", "identity") or not odp.telo:
        return
    if kod in ("gzip", "x-gzip", "deflate"):
        for wbits in ((16 + zlib.MAX_WBITS,) if "gzip" in kod else (zlib.MAX_WBITS, -zlib.MAX_WBITS)):
            try:
                d = zlib.decompressobj(wbits)
                data = d.decompress(odp.telo, max_bajtu + 1)
                if len(data) > max_bajtu:
                    data, odp.oriznuto = data[:max_bajtu], True
                odp.telo = data
                return
            except zlib.error:
                continue
        odp.zprava = f"poškozená komprese obsahu ({_bezpecny_kus(kod, 20)})"
    else:
        # Hodnota hlavičky je text od serveru: do výstupu jen krátký a očištěný kus.
        odp.zprava = f"nepodporované kódování obsahu: {_bezpecny_kus(kod, 40)}"
    odp.telo = b""


def stahni(url: str, prijmout: Optional[str] = None, max_bajtu: int = MAX_BAJTU,
           pouzij_cache: bool = True) -> Odpoved:
    """GET s ručním sledováním přesměrování (max 5, jen http/https), rozestupem hostů,
    opakováním při 429 a limitem velikosti. Nikdy nevyhazuje; chybu vrací v Odpoved."""
    if not povolena_url(url):
        return Odpoved(None, url, chyba="schema", zprava="nepodporované schéma nebo URL (jen http/https)")
    try:
        aktualni = _bezpecna_url(url)
    except ValueError as e:
        return Odpoved(None, url, chyba="schema", zprava=f"neplatná URL: {e}"[:200])
    klic = (aktualni, prijmout, max_bajtu)
    if pouzij_cache:
        with _CACHE_ZAMEK:
            if klic in _CACHE:
                _CACHE.move_to_end(klic)
                return _CACHE[klic]
    hlavicky = {
        "User-Agent": USER_AGENT,
        "Accept": prijmout or "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
        "Accept-Encoding": "identity",
        "Accept-Language": "en,cs;q=0.8,*;q=0.5",
    }
    pocet = 0
    pokus_429 = 0
    pokus_5xx = 0
    while True:
        host = urllib.parse.urlsplit(aktualni).hostname or ""
        if _interni_host(host):
            vysl = Odpoved(None, aktualni, chyba="zakazano",
                           zprava="interní nebo lokální adresa se nenačítá", presmerovani=pocet)
            break
        _OMEZOVAC.cekej(host)
        try:
            with _SEMAFOR:
                odp = _jeden_pozadavek(aktualni, hlavicky, TIMEOUT, max_bajtu)
        except SitovaChyba as e:
            vysl = Odpoved(None, aktualni, chyba=e.druh, zprava=e.zprava, presmerovani=pocet)
            break
        if odp.status in (301, 302, 303, 307, 308):
            cil = (odp.hlavicky.get("location") or "").strip()
            if not cil:
                odp.presmerovani = pocet
                vysl = odp
                break
            dalsi = urllib.parse.urljoin(aktualni, cil)
            if not povolena_url(dalsi):
                vysl = Odpoved(None, aktualni, chyba="schema",
                               zprava="přesměrování na nepovolené schéma (jen http/https)", presmerovani=pocet)
                break
            pocet += 1
            if pocet > MAX_PRESMEROVANI:
                vysl = Odpoved(None, aktualni, chyba="presmerovani",
                               zprava=f"víc než {MAX_PRESMEROVANI} přesměrování", presmerovani=pocet)
                break
            try:
                aktualni = _bezpecna_url(dalsi)
            except ValueError:
                vysl = Odpoved(None, aktualni, chyba="schema", zprava="neplatná cílová URL přesměrování")
                break
            pokus_429 = 0
            continue
        if odp.status == 429 and pokus_429 < MAX_OPAKOVANI_429:
            cekani = _cekani_429(odp.hlavicky.get("retry-after"), pokus_429)
            pokus_429 += 1
            time.sleep(cekani)
            continue
        if (odp.status is not None and odp.status >= 500 and odp.status not in BEZ_OPAKOVANI_5XX
                and pokus_5xx < MAX_OPAKOVANI_5XX):
            # Přechodná chyba serveru (Z2: v20, Europe PMC 500): jedno opakování po 2–5 s.
            pokus_5xx += 1
            time.sleep(_cekani_5xx(odp.hlavicky.get("retry-after")))
            continue
        odp.presmerovani = pocet
        odp.opakovani = pokus_5xx
        odp.url = aktualni
        vysl = odp
        break
    _dekomprimuj(vysl, max_bajtu)
    if pouzij_cache:
        with _CACHE_ZAMEK:
            _CACHE[klic] = vysl
            while len(_CACHE) > MAX_CACHE:
                _CACHE.popitem(last=False)
    return vysl


_LATIN1_ZNACKY = {"iso-8859-1", "iso8859-1", "latin1", "latin-1", "l1", "iso-ir-100", "cp819", "ibm819",
                  "us-ascii", "ascii", "iso-8859-1:1987", "csisolatin1", "windows-1252", "x-cp1252"}


def dekoduj(telo: bytes, content_type: str = "") -> str:
    charset = None
    m = re.search(r"charset=[\"']?([\w.:-]+)", content_type or "", re.I)
    if m:
        charset = m.group(1)
    elif telo.startswith(b"\xef\xbb\xbf"):
        charset = "utf-8-sig"
    elif telo.startswith((b"\xff\xfe", b"\xfe\xff")):
        charset = "utf-16"
    else:
        hlava = telo[:4096].decode("ascii", "ignore")
        m = re.search(r"<meta[^>]+charset=[\"']?([\w.:-]+)", hlava, re.I) or \
            re.search(r"<\?xml[^>]+encoding=[\"']([\w.:-]+)", hlava, re.I)
        if m:
            charset = m.group(1)
    if charset and charset.strip().lower().replace("_", "-") in _LATIN1_ZNACKY:
        # Podle standardu WHATWG se tyto značky dekódují jako windows-1252; čisté latin-1 by
        # z bajtů 0x80–0x9F (uvozovky, pomlčky) udělalo neviditelné řídicí znaky C1.
        charset = "cp1252"
    try:
        return telo.decode(charset or "utf-8", errors="replace")
    except LookupError:
        return telo.decode("utf-8", errors="replace")


def _json(odp: Odpoved):
    try:
        return json.loads(dekoduj(odp.telo, odp.hlavicky.get("content-type", "")))
    except ValueError:
        return None


# Odpověď proxy relace (ne cílového serveru). Zjištěno v Z2b: github.com vracel 403 s JSON tělem
# „GitHub access to this repository is not enabled for this session. Use add_repo…“, bez hlaviček GitHubu;
# CONNECT prošel (200), takže se odmítnutí neobjevilo v recentRelayFailures.
_PROXY_TEXT = re.compile(rb"not enabled for this session|use add_repo|__agentproxy|(?:egress|proxy) policy", re.I)
_GITHUB_HOSTY = frozenset({"github.com", "www.github.com", "api.github.com", "raw.githubusercontent.com",
                           "codeload.github.com", "gist.github.com", "gist.githubusercontent.com"})


def odmitnuto_proxy(odp: Odpoved) -> bool:
    """True = 403/407 vrátila proxy relace (politika přístupu), ne cílový server. Takový požadavek se
    neopakuje ani neobchází (ani přes Wayback). Rozpoznání: text odpovědi proxy; u hostů GitHubu i chybějící
    X-GitHub-Request-Id (skutečné odpovědi GitHubu ji nesou vždy)."""
    if odp.chyba or odp.status not in (403, 407):
        return False
    if odp.status == 407 or _PROXY_TEXT.search(odp.telo[:4096]):
        return True
    host = (urllib.parse.urlsplit(odp.url or "").hostname or "").lower()
    return host in _GITHUB_HOSTY and "x-github-request-id" not in odp.hlavicky


# ---------------------------------------------------------------------------
# Příkaz: url
# ---------------------------------------------------------------------------
def wayback(url: str) -> Tuple[Optional[bool], str]:
    """Wayback availability API. (True/False/None, popis)."""
    api = "https://archive.org/wayback/available?url=" + urllib.parse.quote(url, safe="")
    odp = stahni(api, prijmout="application/json")
    if not odp.ok:
        return None, f"Wayback nedostupný ({odp.popis()})"
    data = _json(odp)
    if not isinstance(data, dict):
        return None, "Wayback vrátil neplatnou odpověď"
    nejblizsi = _slovnik(_slovnik(data.get("archived_snapshots")).get("closest"))
    if nejblizsi.get("available") and isinstance(nejblizsi.get("url"), str) and nejblizsi.get("url"):
        snap = str(nejblizsi.get("url"))
        if not povolena_url(snap):
            return True, "archivní kopie existuje"
        return True, f"archivní kopie: {_zkrat(snap, 300)}"
    return False, "bez archivní kopie ve Waybacku"


_SNIMEK_URL = re.compile(r"^https?://web\.archive\.org/web/(\d{14})(?:[a-z]{2}_)?/", re.I)


def _datum_z_casu(cas: str) -> str:
    return f"{cas[0:4]}-{cas[4:6]}-{cas[6:8]}"


def wayback_snimek(url: str) -> Tuple[Optional[dict], str]:
    """Nejnovější snímek stránky ve Waybacku: ({"url": přímý obsah snímku (id_), "cas", "datum"}, popis).
    Availability API vrací snímek nejbližší k parametru timestamp; dnešní datum = nejnovější snímek.
    URL obsahu se skládá z časového razítka a naší URL (ne z URL od API)."""
    dnes = time.strftime("%Y%m%d", time.gmtime())
    api = ("https://archive.org/wayback/available?url=" + urllib.parse.quote(url, safe="")
           + "&timestamp=" + dnes)
    odp = stahni(api, prijmout="application/json")
    if not odp.ok:
        return None, f"Wayback nedostupný ({odp.popis()})"
    data = _json(odp)
    if not isinstance(data, dict):
        return None, "Wayback vrátil neplatnou odpověď"
    nejblizsi = _slovnik(_slovnik(data.get("archived_snapshots")).get("closest"))
    cas = str(nejblizsi.get("timestamp") or "")
    if not nejblizsi.get("available") or not re.fullmatch(r"\d{14}", cas):
        return None, "bez archivní kopie ve Waybacku"
    stav = str(nejblizsi.get("status") or "200")
    if stav != "200":
        return None, f"snímek ve Waybacku má stav {_bezpecny_kus(stav, 5)}"
    return {"url": f"https://web.archive.org/web/{cas}id_/{url}", "cas": cas, "datum": _datum_z_casu(cas)}, ""


def zkontroluj_url(url: str) -> dict:
    if not povolena_url(url):
        return {"stav": "nenacteno", "http": None, "wayback": None,
                "duvod": "nepodporované schéma nebo URL (jen http/https); lokální soubory se nečtou"}
    odp = stahni(url)
    presm = f" po {odp.presmerovani} přesměrováních" if odp.presmerovani else ""
    if odp.chyba == "dns":
        wb, wb_popis = wayback(url)
        return {"stav": "mrtvy", "http": None, "wayback": wb, "duvod": f"DNS: doména neexistuje; {wb_popis}"}
    if odp.chyba:
        return {"stav": "nenacteno", "http": None, "wayback": None, "duvod": odp.popis() + presm}
    s = odp.status
    if 200 <= s < 300:
        return {"stav": "ok", "http": s, "wayback": None, "duvod": f"HTTP {s}{presm}"}
    if s in (404, 410):
        wb, wb_popis = wayback(url)
        return {"stav": "mrtvy", "http": s, "wayback": wb, "duvod": f"HTTP {s}{presm}; {wb_popis}"}
    if odmitnuto_proxy(odp):
        duvod = f"HTTP {s} od proxy relace (politika přístupu), ne od cílového serveru; neopakuje se"
    elif s in (401, 403):
        duvod = f"HTTP {s}: přístup odepřen (blokování robotů nebo přihlášení), ne mrtvý odkaz"
    elif s == 429:
        duvod = f"HTTP 429: příliš mnoho požadavků i po {MAX_OPAKOVANI_429} opakováních"
    elif s >= 500:
        duvod = f"HTTP {s}: chyba serveru (dočasná?)"
    else:
        duvod = f"HTTP {s}"
    return {"stav": "nenacteno", "http": s, "wayback": None, "duvod": duvod + presm}


# ---------------------------------------------------------------------------
# DOI: metadata a porovnání
# ---------------------------------------------------------------------------
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")


def normalizuj_doi(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = urllib.parse.unquote(s.strip())
    s = re.sub(r"^(?:https?://)?(?:dx\.|www\.)?doi\.org/", "", s, flags=re.I)
    s = re.sub(r"^doi\s*:?\s*", "", s, flags=re.I).strip().rstrip(".,;")  # „doi:10…“ i „DOI 10…“
    return s if _DOI_RE.match(s) else None


def _doi_v_url(doi: str) -> str:
    return urllib.parse.quote(doi, safe="/()")


def _bez_tagu(s: str) -> str:
    return html_mod.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def _slovnik(x) -> dict:
    return x if isinstance(x, dict) else {}


def _seznam(x) -> list:
    return x if isinstance(x, list) else []


def _meta_crossref(m: dict) -> dict:
    t = m.get("title")
    nazev = _bez_tagu(str(((t or [""])[0] if isinstance(t, list) else t) or ""))
    autori = [a for a in _seznam(m.get("author")) if isinstance(a, dict)]
    prvni = next((a for a in autori if a.get("sequence") == "first"), autori[0] if autori else {})
    prijmeni = prvni.get("family") or prvni.get("name") or None
    rok = None
    for k in ("issued", "published-print", "published-online", "published", "created"):
        dp = _seznam(_slovnik(m.get(k)).get("date-parts"))
        if dp and isinstance(dp[0], list) and dp[0] and dp[0][0]:
            try:
                rok = int(dp[0][0])
                break
            except (TypeError, ValueError):
                continue
    return {"nazev": _zkrat(nazev or None), "prvni_autor": _zkrat(str(prijmeni) if prijmeni else None, 100),
            "rok": rok}


def _meta_openalex(m: dict) -> dict:
    nazev = _bez_tagu(str(m.get("title") or m.get("display_name") or ""))
    prijmeni = None
    auth = [a for a in _seznam(m.get("authorships")) if isinstance(a, dict)]
    if auth:
        jmeno = str(_slovnik(auth[0].get("author")).get("display_name") or auth[0].get("raw_author_name") or "").strip()
        if jmeno:
            prijmeni = jmeno.split(",")[0].strip() if "," in jmeno else jmeno.split()[-1]
    rok = m.get("publication_year")
    return {"nazev": _zkrat(nazev or None), "prvni_autor": _zkrat(prijmeni, 100),
            "rok": int(rok) if isinstance(rok, int) else None}


def _norm_nazev(s: str) -> str:
    s = _normalizuj(_bez_tagu(s))
    s = re.sub(r"[\W_]+", " ", s)  # Unicode: cyrilice, řečtina, CJK zůstanou (dřív [^a-z0-9] = prázdný řetězec)
    return " ".join(s.split())


_PREDPONA_RETRAKCE = re.compile(r"^(?:retracted|withdrawn)(?: article)? ")


def podobnost_nazvu(a: str, b: str) -> float:
    # Crossref u retrahovaných prací mění název na „RETRACTED: …“; citace má původní název.
    na = _PREDPONA_RETRAKCE.sub("", _norm_nazev(a or ""))
    nb = _PREDPONA_RETRAKCE.sub("", _norm_nazev(b or ""))
    if not na or not nb:
        return 0.0
    r = SequenceMatcher(None, na, nb, autojunk=False).ratio()
    kratsi, delsi = sorted((na, nb), key=len)
    if len(kratsi) >= 20 and delsi.startswith(kratsi):  # chybějící podtitul
        r = max(r, 0.95)
    return r


# Šlechtické a jiné částice příjmení: samy o sobě shodu nedokládají („de Souza“ ≠ „de Oliveira“).
_CASTICE = {"de", "da", "di", "do", "dos", "das", "del", "della", "dei", "van", "von", "der", "den", "ter", "te",
            "la", "le", "du", "des", "zu", "y", "e", "bin", "ibn", "al", "el", "ben", "ap"}


def shoda_autora(zadany: str, nalezene_prijmeni: Optional[str]) -> bool:
    if not zadany or not nalezene_prijmeni:
        return False

    def tok(s):
        # Unicode písmena (cyrilice, CJK…); jednopísmenné latinské iniciály se zahodí.
        return [t for t in re.sub(r"[\W\d_]+", " ", _normalizuj(s)).split() if len(t) > 1 or not t.isascii()]
    if "," in zadany:  # „Příjmení, J.“
        zadany = zadany.split(",")[0]
    sz, sn = tok(zadany), tok(nalezene_prijmeni)
    if not sz or not sn:
        return False
    tz = (set(sz) - _CASTICE) or set(sz)
    tn = (set(sn) - _CASTICE) or set(sn)
    return bool(tz & tn) or "".join(sz) == "".join(sn)  # „VanderBerg“ = „van der Berg“


_POLE_POROVNANI = ("nazev", "prvni_autor", "rok")


def _pozadovana_pole(nazev, autor, rok) -> List[str]:
    return [p for p, v in zip(_POLE_POROVNANI, (nazev, autor, rok)) if (v is not None if p == "rok" else v)]


def _porovnej(nalezeno: dict, nazev: Optional[str], autor: Optional[str], rok: Optional[int]) -> List[dict]:
    """Neshody jen u polí, která metadata obsahují; chybějící pole vrací _neoverena (není to neshoda)."""
    neshody = []
    if nazev and nalezeno.get("nazev"):
        p = podobnost_nazvu(nazev, nalezeno.get("nazev") or "")
        if p < PRAH_NAZEV:
            neshody.append({"pole": "nazev", "ocekavano": _zkrat(nazev), "nalezeno": nalezeno.get("nazev"),
                            "podobnost": round(p, 3)})
    if autor and nalezeno.get("prvni_autor"):
        if not shoda_autora(autor, nalezeno.get("prvni_autor")):
            neshody.append({"pole": "prvni_autor", "ocekavano": _zkrat(autor, 100),
                            "nalezeno": nalezeno.get("prvni_autor")})
    if rok is not None and nalezeno.get("rok") is not None:
        r = nalezeno.get("rok")
        if abs(int(r) - int(rok)) > 1:
            neshody.append({"pole": "rok", "ocekavano": int(rok), "nalezeno": r})
    return neshody


def _neoverena(nalezeno: dict, nazev, autor, rok) -> List[str]:
    return [p for p in _pozadovana_pole(nazev, autor, rok) if nalezeno.get(p) is None]


def _crossref_work(doi: str) -> Odpoved:
    return stahni("https://api.crossref.org/works/" + _doi_v_url(doi), prijmout="application/json")


def klic_api(nazev: str) -> Optional[str]:
    """Volitelný klíč API z proměnné prostředí (NCBI_API_KEY, OPENALEX_API_KEY); do výstupu se nikdy nedostane
    (chybové popisy odpovědí URL neobsahují)."""
    hodnota = os.environ.get(nazev, "").strip()
    return hodnota if re.fullmatch(r"[A-Za-z0-9._\-]{8,200}", hodnota) else None


def _openalex_work(doi: str) -> Odpoved:
    url = "https://api.openalex.org/works/https://doi.org/" + _doi_v_url(doi)
    klic = klic_api("OPENALEX_API_KEY")
    if klic:
        url += "?api_key=" + urllib.parse.quote(klic, safe="")
    return stahni(url, prijmout="application/json")


def _doi_handle(doi: str) -> Optional[bool]:
    odp = stahni("https://doi.org/api/handles/" + _doi_v_url(doi), prijmout="application/json")
    data = _json(odp) if odp.telo else None
    if isinstance(data, dict) and data.get("responseCode") == 1:
        return True
    if odp.status == 404 or (isinstance(data, dict) and data.get("responseCode") == 100):
        return False
    return None


def over_doi(doi: str, nazev: Optional[str] = None, autor: Optional[str] = None, rok: Optional[int] = None) -> dict:
    prazdne = {"nazev": None, "prvni_autor": None, "rok": None}
    d = normalizuj_doi(doi)
    if not d:
        return {"stav": "neexistuje", "nalezeno": prazdne, "neshody": [], "neovereno": [], "zdroj": None,
                "duvod": "neplatný formát DOI (očekává se 10.XXXX/…)"}
    duvody = []
    cr = _crossref_work(d)
    meta, zdroj = None, None
    if cr.ok:
        data = _json(cr)
        if isinstance(data, dict) and isinstance(data.get("message"), dict):
            meta, zdroj = _meta_crossref(data["message"]), "crossref"
        else:
            duvody.append("Crossref: neplatná odpověď")
    else:
        duvody.append(f"Crossref: {cr.popis()}")
    if meta is None:
        oa = _openalex_work(d)
        oa_data = _json(oa) if oa.ok else None
        if isinstance(oa_data, dict):
            meta, zdroj = _meta_openalex(oa_data), "openalex"
        else:
            duvody.append(f"OpenAlex: {oa.popis() if not oa.ok else 'neplatná odpověď'}")
        if meta is None:
            existuje = _doi_handle(d)
            if existuje is False:
                return {"stav": "neexistuje", "nalezeno": prazdne, "neshody": [], "neovereno": [], "zdroj": "doi.org",
                        "duvod": "DOI není registrované (doi.org, Crossref ani OpenAlex ho neznají)"}
            if existuje is True:
                stav = "nenacteno" if (nazev or autor or rok is not None) else "ok"
                return {"stav": stav, "nalezeno": prazdne, "neshody": [],
                        "neovereno": _pozadovana_pole(nazev, autor, rok), "zdroj": "doi.org",
                        "duvod": "DOI existuje (doi.org), ale metadata nejsou v Crossrefu ani OpenAlexu; "
                                 + "; ".join(duvody)}
            return {"stav": "nenacteno", "nalezeno": prazdne, "neshody": [], "neovereno": [], "zdroj": None,
                    "duvod": "; ".join(duvody) or "metadata nelze načíst"}
    if zdroj == "crossref" and _neoverena(meta, nazev, autor, rok):
        # Crossref požadované pole nemá (chybí autor/rok/název): doplň ho z OpenAlexu, je-li tam.
        oa = _openalex_work(d)
        oa_data = _json(oa) if oa.ok else None
        if isinstance(oa_data, dict):
            oa_meta = _meta_openalex(oa_data)
            doplneno = [p for p in _neoverena(meta, nazev, autor, rok) if oa_meta.get(p) is not None]
            if doplneno:
                meta = dict(meta, **{p: oa_meta[p] for p in doplneno})
                zdroj = "crossref+openalex"
    neshody = _porovnej(meta, nazev, autor, rok)
    neovereno = _neoverena(meta, nazev, autor, rok)
    if neshody:
        stav, duvod = "nesedi", "metadata nesedí: " + ", ".join(n["pole"] for n in neshody)
    elif neovereno:
        # Chybějící pole není neshoda, ale ani potvrzení.
        stav, duvod = "nenacteno", "v metadatech chybí: " + ", ".join(neovereno) + " (nelze ověřit)"
    else:
        stav, duvod = "ok", "metadata sedí" if (nazev or autor or rok is not None) else "DOI existuje"
    if neshody and neovereno:
        duvod += "; v metadatech chybí: " + ", ".join(neovereno)
    return {"stav": stav, "nalezeno": meta, "neshody": neshody, "neovereno": neovereno, "zdroj": zdroj,
            "duvod": duvod}


# ---------------------------------------------------------------------------
# Retrakce
# ---------------------------------------------------------------------------
_TYPY_AKTUALIZACI = {
    "retraction": "retrahovano", "partial_retraction": "retrahovano", "withdrawal": "retrahovano",
    "removal": "retrahovano", "retracted": "retrahovano",
    "expression_of_concern": "vyjadreni_obav", "concern": "vyjadreni_obav",
    "correction": "oprava", "erratum": "oprava", "corrigendum": "oprava",
}
_PORADI_STAVU = {"retrahovano": 3, "vyjadreni_obav": 2, "oprava": 1}


def _typ_aktualizace(t: str) -> Optional[str]:
    t = re.sub(r"[\s\-]+", "_", (t or "").strip().lower())
    if t in _TYPY_AKTUALIZACI:
        return _TYPY_AKTUALIZACI[t]
    for klic, stav in _TYPY_AKTUALIZACI.items():
        if klic in t:
            return stav
    return None


def _datum(polozka: dict) -> Optional[str]:
    dp = _seznam(_slovnik(polozka.get("updated")).get("date-parts")) or [[None]]
    casti = []
    for i, x in enumerate(dp[0] if isinstance(dp[0], list) else []):
        try:
            x = int(x)
        except (TypeError, ValueError):
            break
        casti.append(f"{x:02d}" if i else str(x))
    return "-".join(casti) or None


def _retezec(x) -> str:
    return x if isinstance(x, str) else ""


def zaznamy_retrakci_crossref(m: dict, doi: str) -> Tuple[List[dict], List[str]]:
    """Vrátí (záznamy [{stav, typ, doi, zdroj, datum}], poznámky). Toleruje chybějící/vadná pole."""
    zaznamy: List[dict] = []
    poznamky: List[str] = []
    for p in _seznam(m.get("updated-by")):
        if not isinstance(p, dict):
            continue
        stav = _typ_aktualizace(_retezec(p.get("type")) or _retezec(p.get("label")))
        if stav:
            zaznamy.append({"stav": stav, "typ": p.get("type"), "doi": p.get("DOI"),
                            "zdroj": f"crossref:updated-by ({_zkrat(_retezec(p.get('source')), 60) or 'neznámý'})",
                            "datum": _datum(p)})
    for p in _seznam(m.get("update-to")):
        if not isinstance(p, dict):
            continue
        stav = _typ_aktualizace(_retezec(p.get("type")) or _retezec(p.get("label")))
        if not stav:
            continue
        if _retezec(p.get("DOI")).lower() == doi.lower():
            zaznamy.append({"stav": stav, "typ": p.get("type"), "doi": doi,
                            "zdroj": "crossref:update-to", "datum": _datum(p)})
        else:
            poznamky.append(f"záznam je sám oznámením ({_zkrat(_retezec(p.get('type')), 40)}) "
                            f"k DOI {_zkrat(_retezec(p.get('DOI')), 120)}")
    for typ_vztahu, cile in _slovnik(m.get("relation")).items():
        stav = _typ_aktualizace(typ_vztahu)
        if stav and typ_vztahu.lower().endswith("-by"):  # např. is-retracted-by (ne is-correction-of)
            for c in cile if isinstance(cile, list) else [cile]:
                zaznamy.append({"stav": stav, "typ": typ_vztahu, "doi": _slovnik(c).get("id"),
                                "zdroj": "crossref:relation", "datum": None})
    t = m.get("title")
    nazev = _norm_nazev(str(((t or [""])[0] if isinstance(t, list) else t) or ""))
    if not zaznamy and re.match(r"^(retracted|withdrawn)\b", nazev):
        zaznamy.append({"stav": "retrahovano", "typ": "nazev", "doi": None,
                        "zdroj": "crossref:nazev (předpona RETRACTED/WITHDRAWN)", "datum": None})
    return zaznamy, poznamky


def oznameni_k_crossref(m: dict, doi: str) -> List[dict]:
    """Je-li záznam sám oznámením (retrakce, vyjádření obav, oprava) k jinému DOI: [{typ, doi}], jinak []."""
    vysl: List[dict] = []
    for p in _seznam(m.get("update-to")):
        if not isinstance(p, dict):
            continue
        cil = _retezec(p.get("DOI"))
        typ = _retezec(p.get("type")) or _retezec(p.get("label"))
        polozka = {"typ": _zkrat(typ, 40), "doi": _zkrat(cil, 120)}
        if _typ_aktualizace(typ) and cil.lower() != doi.lower() and polozka not in vysl:
            vysl.append(polozka)
    return vysl


# OpenAlex dává is_retracted: true i samotnému oznámení o retrakci (typ díla „retraction“; A/B 2026-10-31).
_TYPY_OZNAMENI_OPENALEX = ("retraction", "erratum", "correction", "expression-of-concern", "concern")


def over_retrakci(doi: str) -> dict:
    d = normalizuj_doi(doi)
    if not d:
        return {"stav": "nenacteno", "zdroj": "", "duvod": "neplatný formát DOI", "oznameni": []}
    zaznamy: List[dict] = []
    poznamky: List[str] = []
    zkontrolovano: List[str] = []
    chyby: List[str] = []
    oznameni_k: List[dict] = []
    cr = _crossref_work(d)
    cr_data = _json(cr) if cr.ok else None
    if isinstance(cr_data, dict) and isinstance(cr_data.get("message"), dict):
        z, p = zaznamy_retrakci_crossref(cr_data["message"], d)
        zaznamy += z
        poznamky += p
        oznameni_k = oznameni_k_crossref(cr_data["message"], d)
        zkontrolovano.append("crossref (vč. Retraction Watch)")
    else:
        chyby.append(f"Crossref: {cr.popis()}")
    if not zaznamy and not oznameni_k:  # u oznámení by OpenAlex is_retracted hlásil původní článek
        oa = _openalex_work(d)
        data = _json(oa) if oa.ok else None
        if isinstance(data, dict):
            zkontrolovano.append("openalex")
            typ_oa = _retezec(data.get("type")).strip().lower()
            if typ_oa in _TYPY_OZNAMENI_OPENALEX:
                oznameni_k.append({"typ": typ_oa, "doi": None})
                poznamky.append(f"OpenAlex: záznam je sám oznámením (typ {typ_oa}); "
                                "is_retracted se týká původního článku")
            elif data.get("is_retracted") is True:
                zaznamy.append({"stav": "retrahovano", "typ": "is_retracted", "doi": None,
                                "zdroj": "openalex:is_retracted", "datum": None})
        else:
            chyby.append(f"OpenAlex: {oa.popis()}")
    if zaznamy:
        nejhorsi = max(zaznamy, key=lambda z: _PORADI_STAVU[z["stav"]])
        oznameni = [{k: z[k] for k in ("typ", "doi", "zdroj", "datum")} for z in zaznamy]
        vysl = {"stav": nejhorsi["stav"], "zdroj": nejhorsi["zdroj"],
                "duvod": "; ".join([f"nalezeno {len(zaznamy)} oznámení"] + poznamky), "oznameni": oznameni}
        return vysl | ({"oznameni_k": oznameni_k} if oznameni_k else {})
    if oznameni_k:
        cile = ", ".join(sorted({o["doi"] for o in oznameni_k if o["doi"]})) or "neuvedeno"
        return {"stav": "bez_zaznamu", "zdroj": " + ".join(zkontrolovano), "oznameni": [], "oznameni_k": oznameni_k,
                "duvod": "; ".join([f"záznam je sám oznámením ({oznameni_k[0]['typ']}) k DOI {cile}: doklad o "
                                    "retrakci či opravě, ne retrahovaný článek; nálezy původního článku nepodpírá"]
                                   + [p for p in poznamky if not p.startswith("záznam je sám")] + chyby)}
    if zkontrolovano:
        return {"stav": "bez_zaznamu", "zdroj": " + ".join(zkontrolovano),
                "duvod": "; ".join(["žádný záznam o retrakci, vyjádření obav ani opravě; "
                                    "to NEZNAMENÁ jistotu, že článek retrahován není"] + poznamky + chyby),
                "oznameni": []}
    return {"stav": "nenacteno", "zdroj": "", "duvod": "; ".join(chyby), "oznameni": []}


# ---------------------------------------------------------------------------
# Převod HTML / JATS na text
# ---------------------------------------------------------------------------
class _HtmlNaText(HTMLParser):
    PRESKOCIT = {"script", "style", "nav", "noscript", "template", "svg", "iframe", "object", "embed",
                 "footer", "aside", "form", "button", "select", "textarea", "head", "canvas", "map",
                 "annotation", "annotation-xml", "dialog"}
    BLOKY = {"p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table", "section",
             "article", "blockquote", "pre", "dd", "dt", "dl", "figcaption", "caption", "header", "main",
             "td", "th", "figure", "body", "html", "address", "details", "summary", "center"}
    PRAZDNE = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
               "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.casti: List[str] = []
        self._skip_tag: Optional[str] = None
        self._skip_hloubka = 0
        self._pre = 0

    def handle_starttag(self, tag, attrs):
        if self._skip_tag:
            if tag == self._skip_tag:
                self._skip_hloubka += 1
                return
            if not (self._skip_tag == "head" and tag == "body"):  # </head> lze vynechat
                return
            self._skip_tag, self._skip_hloubka = None, 0
        if tag in self.PRAZDNE:
            if tag in ("br", "hr"):
                self.casti.append("\n")
            return
        a = dict(attrs)
        if tag in self.PRESKOCIT or _skryty(a):
            self._skip_tag, self._skip_hloubka = tag, 1
            return
        if tag == "math":
            alt = a.get("alttext")
            if alt:
                self.casti.append(f" {alt} ")
                self._skip_tag, self._skip_hloubka = "math", 1
            return
        if tag == "pre":
            self._pre += 1
        if tag in self.BLOKY:
            self.casti.append("\n")

    def handle_endtag(self, tag):
        if self._skip_tag:
            if tag == self._skip_tag:
                self._skip_hloubka -= 1
                if self._skip_hloubka <= 0:
                    self._skip_tag = None
            return
        if tag == "pre" and self._pre:
            self._pre -= 1
        if tag in self.BLOKY:
            self.casti.append("\n")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.PRAZDNE:
            self.handle_endtag(tag)

    def handle_data(self, data):
        if self._skip_tag:
            return
        self.casti.append(data if self._pre else data.replace("\n", " ").replace("\r", " "))


def _skryty(a: dict) -> bool:
    if "hidden" in a:
        return True
    if (a.get("aria-hidden") or "").strip().lower() == "true":
        return True
    styl = (a.get("style") or "").lower().replace(" ", "")
    return "display:none" in styl or "visibility:hidden" in styl


def _uklid_text(surovy: str) -> str:
    radky = []
    for r in surovy.split("\n"):
        r = _RIDICI.sub("", _NEVIDITELNE.sub("", r))
        r = re.sub(r"[ \t\r\f\v]+", " ", r).strip()
        if r:
            radky.append(r)
    return "\n".join(radky)


def html_na_text(html: str) -> str:
    """HTML -> čistý text (odstavce oddělené \\n). Vynechá script/style/nav/… a skryté prvky."""
    p = _HtmlNaText()
    try:
        p.feed(html)
        p.close()
    except Exception:  # HTMLParser je tolerantní; pojistka proti exotickým vstupům
        pass
    return _uklid_text("".join(p.casti))


def _bez_doctype(xml: bytes) -> Optional[bytes]:
    """Odstraní jedinou deklaraci DOCTYPE bez interní podmnožiny (běžný JATS). Lineárně, bez regexu
    s backtrackingem. None = dokument má interní DTD, další DOCTYPE (např. za komentářem) nebo
    <!ENTITY – takový dokument se XML parserem nečte (ochrana před expanzí entit, „billion laughs“)."""
    i = xml.find(b"<!DOCTYPE")
    if i >= 0:
        j = xml.find(b">", i)
        if j < 0 or b"[" in xml[i:j]:
            return None
        xml = xml[:i] + xml[j + 1:]
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        return None
    return xml


def jats_na_text(xml: bytes) -> str:
    """JATS XML (Europe PMC fullTextXML) -> text: název, abstrakt, tělo (bez seznamu literatury)."""
    data = _bez_doctype(xml)
    if data is None:  # interní DTD / deklarace entit: XML parserem nečíst (expanze entit), jen jako HTML
        return html_na_text(dekoduj(xml))
    try:
        koren = ET.fromstring(data)
    except ET.ParseError:
        return html_na_text(dekoduj(xml))

    def jmeno(el):
        return el.tag.rsplit("}", 1)[-1] if isinstance(el.tag, str) else ""

    def text_el(el):
        return " ".join("".join(el.itertext()).split())

    casti: List[str] = []
    for el in koren.iter():
        if jmeno(el) == "article-title":
            casti.append(text_el(el))
            break
    for sekce in ("abstract", "body"):
        for blok in koren.iter():
            if jmeno(blok) != sekce:
                continue
            for el in blok.iter():
                if jmeno(el) in ("p", "title"):
                    t = text_el(el)
                    if t:
                        casti.append(t)
            if sekce == "body":
                break
    return _uklid_text("\n".join(casti))


# ---------------------------------------------------------------------------
# Rozpoznání zdroje
# ---------------------------------------------------------------------------
_ARXIV_ID = re.compile(r"^(?:\d{4}\.\d{4,5}|[a-z][a-z\-]*(?:\.[a-z]{2})?/\d{7})(?:v\d+)?$", re.I)
_ARXIV_HOSTY = {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}


def rozpoznej_zdroj(url: Optional[str] = None, doi: Optional[str] = None) -> dict:
    """{typ: arxiv|pmc|pubmed|doi|pdf|html|neplatna, id, url}."""
    if url:
        if not povolena_url(url):
            return {"typ": "neplatna", "id": None, "url": url}
        c = urllib.parse.urlsplit(url.strip())
        host = (c.hostname or "").lower()
        cesta = urllib.parse.unquote(c.path)
        if host in _ARXIV_HOSTY:
            m = re.match(r"^/(?:abs|pdf|html|format|ps)/(.+?)(?:\.pdf)?/?$", cesta)
            if m:
                ident = m.group(1).split("/index")[0]
                if _ARXIV_ID.match(ident):
                    return {"typ": "arxiv", "id": ident, "url": url}
        if host.endswith("ncbi.nlm.nih.gov") or host == "europepmc.org" or host.endswith(".europepmc.org"):
            m = re.search(r"(PMC\d+)", cesta, re.I)
            if m:
                return {"typ": "pmc", "id": m.group(1).upper(), "url": url}
            m = re.match(r"^/(?:pubmed/)?(\d{1,9})/?$", cesta) if host.startswith("pubmed.") else None
            m = m or re.search(r"/(?:pubmed|(?:article|abstract)/MED)/(\d{1,9})", cesta, re.I)
            if m:
                return {"typ": "pubmed", "id": m.group(1), "url": url}
        if host in ("doi.org", "dx.doi.org", "www.doi.org"):
            d = normalizuj_doi(cesta.lstrip("/"))
            if d:
                return rozpoznej_zdroj(doi=d) | {"url": url}
        gh = _github_cil(host, c.path)
        if gh:
            return {"typ": "github", "id": gh["id"], "url": url, "github": gh}
        if cesta.lower().endswith(".pdf"):
            return {"typ": "pdf", "id": None, "url": url}
        return {"typ": "html", "id": None, "url": url}
    if doi:
        d = normalizuj_doi(doi)
        if not d:
            return {"typ": "neplatna", "id": None, "url": None}
        m = re.match(r"^10\.48550/arxiv\.(.+)$", d, re.I)
        if m and _ARXIV_ID.match(m.group(1)):
            return {"typ": "arxiv", "id": m.group(1), "url": None}
        return {"typ": "doi", "id": d, "url": None}
    return {"typ": "neplatna", "id": None, "url": None}


# GitHub: github.com se nečte jako stránka (Z2: 5/5 HTTP 403 – podle Z2b od proxy relace), ale přes API
# (README, issue/PR) a raw.githubusercontent.com (soubory). Bez tokenu: limit API 60 požadavků/h.
_GH_REZERVOVANE = {"about", "apps", "collections", "codespaces", "contact", "customer-stories", "enterprise",
                   "events", "explore", "features", "issues", "login", "marketplace", "new", "notifications",
                   "orgs", "organizations", "pricing", "pulls", "readme", "search", "security", "settings",
                   "site", "sponsors", "team", "topics", "trending", "users", "join", "signup"}
_GH_JMENO = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_PRIPONY_MD = {"md", "markdown", "mdown", "mkd", "mkdn", "rst", "txt"}


def _github_cil(host: str, cesta: str) -> Optional[dict]:
    """github.com / raw.githubusercontent.com URL -> {druh: readme|issue|soubor, id, api|raw, …}; jinak None
    (wiki, discussions, releases… se čtou jako obyčejná stránka)."""
    casti = [urllib.parse.unquote(p) for p in cesta.split("/") if p]
    q = lambda s: urllib.parse.quote(s, safe="")  # noqa: E731
    if host == "raw.githubusercontent.com":
        if len(casti) >= 4 and _GH_JMENO.match(casti[0]) and _GH_JMENO.match(casti[1]):
            soubor = "/".join(casti[3:])
            return {"druh": "soubor", "id": f"{casti[0]}/{casti[1]}/{soubor}", "cesta": soubor,
                    "raw": "https://raw.githubusercontent.com/" + "/".join(q(c) for c in casti)}
        return None
    if host not in ("github.com", "www.github.com") or len(casti) < 2:
        return None
    vlastnik, repo = casti[0], casti[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    if vlastnik.lower() in _GH_REZERVOVANE or not _GH_JMENO.match(vlastnik) or not _GH_JMENO.match(repo) \
            or repo in (".", ".."):
        return None
    zaklad = f"https://api.github.com/repos/{q(vlastnik)}/{q(repo)}"
    zbytek = casti[2:]
    if not zbytek:
        return {"druh": "readme", "id": f"{vlastnik}/{repo}", "api": zaklad + "/readme"}
    if zbytek[0] in ("issues", "pull") and len(zbytek) >= 2 and zbytek[1].isdigit():
        n = zbytek[1]
        return {"druh": "issue", "id": f"{vlastnik}/{repo}#{n}", "api": f"{zaklad}/issues/{n}",
                "komentare": f"{zaklad}/issues/{n}/comments?per_page=100"}
    if zbytek[0] in ("blob", "raw") and len(zbytek) >= 3:
        ref, soubor = zbytek[1], "/".join(zbytek[2:])
        return {"druh": "soubor", "id": f"{vlastnik}/{repo}/{soubor}", "cesta": soubor,
                "raw": f"https://raw.githubusercontent.com/{q(vlastnik)}/{q(repo)}/{q(ref)}/"
                       + "/".join(q(c) for c in zbytek[2:])}
    if zbytek[0] == "tree" and len(zbytek) >= 2:
        ref, adresar = zbytek[1], "/".join(q(c) for c in zbytek[2:])
        return {"druh": "readme", "id": f"{vlastnik}/{repo}/{'/'.join(zbytek[2:])}".rstrip("/"),
                "api": zaklad + "/readme" + (f"/{adresar}" if adresar else "") + "?ref=" + q(ref)}
    return None


_DOI_V_TEXTU = re.compile(r"(10\.\d{4,9}/[^\s?#&\"'<>]+)")
_DOI_PRIPONY = re.compile(r"(?:/(?:full|abstract|pdf|epdf|pdfdirect|fulltext|summary|html|meta|references|figures|"
                          r"suppl(?:ementary)?(?:-material)?)|\.pdf|\.html?)+/?$", re.I)


def _doi_z_url(url: Optional[str]) -> Optional[str]:
    """DOI v cestě nebo dotazu URL (…/doi/full/10.1002/x, ?id=10.1371/…), bez přípon /full, .pdf…"""
    if not url:
        return None
    try:
        c = urllib.parse.urlsplit(url)
    except ValueError:
        return None
    if (c.hostname or "").lower() in ("doi.org", "dx.doi.org", "www.doi.org"):
        return normalizuj_doi(urllib.parse.unquote(c.path).lstrip("/"))
    for cast in (urllib.parse.unquote(c.path), urllib.parse.unquote(c.query)):
        m = _DOI_V_TEXTU.search(cast)
        if m:
            d = normalizuj_doi(_DOI_PRIPONY.sub("", m.group(1)))
            if d:
                return d
    return None


def je_pdf(odp: Odpoved) -> bool:
    return odp.typ == "application/pdf" or odp.telo[:5] == b"%PDF-"


# ---------------------------------------------------------------------------
# Získání textu
# ---------------------------------------------------------------------------
@dataclass
class Text:
    text: Optional[str]
    zdroj: str
    duvod: str
    url: Optional[str] = None
    oriznuto: bool = False
    http: Optional[int] = None       # stav HTTP odpovědi, ze které text je (nebo která selhala)
    chyba_site: bool = False         # selhání sítě (timeout, DNS, spojení…)
    proxy: bool = False              # 403/407 od proxy relace: neopakovat a neobcházet
    pdf: bool = False                # zdroj je PDF
    clanek: bool = False             # článek (DOI, časopis, arXiv abs, abstrakt): tenký text = castecne_nacteno
    doi: Optional[str] = None        # DOI zjištěné ze stránky (meta citation_doi…) nebo z URL


def _prosty_text(surovy: str) -> str:
    odstavce = re.split(r"\n\s*\n", surovy.replace("\r\n", "\n"))
    return _uklid_text("\n".join(" ".join(o.split()) for o in odstavce))


# Meta značky článků (Highwire/Google Scholar citation_*, bepress, PRISM, EPrints): stránka časopisu nebo
# repozitáře. dc.identifier se bere jen jako zdroj DOI (Dublin Core používají i jiné weby).
_META_TAG = re.compile(r"<meta\b[^<>]{0,3000}>", re.I)
_ATRIBUT = re.compile(r"([\w:.-]+)\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s\"'>]+)")
_META_CLANKU = ("citation_", "bepress_citation_", "prism.", "eprints.")
_META_DOI = ("citation_doi", "bepress_citation_doi", "prism.doi", "dc.identifier", "eprints.id_number")


def _clankova_meta(html: str) -> Tuple[bool, Optional[str]]:
    clanek, doi = False, None
    for m in _META_TAG.finditer(html[:300000]):
        a = {k.lower(): v[1:-1] if v[:1] in "\"'" else v for k, v in _ATRIBUT.findall(m.group())}
        jmeno = (a.get("name") or a.get("property") or "").strip().lower()
        if jmeno.startswith(_META_CLANKU):
            clanek = True
        if doi is None and jmeno in _META_DOI:
            obsah = re.sub(r"^info:doi/", "", html_mod.unescape(a.get("content") or "").strip(), flags=re.I)
            doi = normalizuj_doi(obsah)
            clanek = clanek or bool(doi)
        if clanek and doi:
            break
    return clanek, doi


def _text_z_odpovedi(odp: Odpoved, zdroj: str) -> Text:
    if odp.chyba:
        return Text(None, zdroj, odp.popis(), odp.url, chyba_site=True)
    if not odp.ok:
        if odmitnuto_proxy(odp):
            return Text(None, zdroj, f"HTTP {odp.status} od proxy relace (politika přístupu; neopakuje se, "
                                     f"zálohy se nezkoušejí)", odp.url, http=odp.status, proxy=True)
        duvod = f"HTTP {odp.status}" + (" (i po opakování)" if odp.opakovani else "")
        return Text(None, zdroj, duvod, odp.url, http=odp.status)
    if je_pdf(odp):
        return _text_z_pdf(odp, zdroj)
    if odp.zprava and not odp.telo:
        return Text(None, zdroj, odp.zprava, odp.url, http=odp.status)
    if zdroj == "pdf":  # přípona .pdf, ale server poslal jiný obsah (např. stránku článku)
        zdroj = "html"
    typ = odp.typ
    surovy = dekoduj(odp.telo, odp.hlavicky.get("content-type", ""))
    zacatek = surovy[:2000].lower()
    clanek, doi = False, None
    if typ in ("text/html", "application/xhtml+xml", "") or "<html" in zacatek or "<!doctype html" in zacatek:
        text = html_na_text(surovy)
        clanek, doi = _clankova_meta(surovy)
        if len(text) < MIN_TEXT:
            if "<script" in surovy.lower() or "javascript" in surovy.lower():
                return Text(None, zdroj, "stránka bez textu (pravděpodobně vyžaduje JavaScript)", odp.url,
                            http=odp.status, clanek=clanek, doi=doi)
            return Text(None, zdroj, "stránka neobsahuje dost textu", odp.url, http=odp.status, clanek=clanek,
                        doi=doi)
    elif typ in ("application/xml", "text/xml") or typ.endswith("+xml"):
        text = jats_na_text(odp.telo) if "<article" in zacatek else html_na_text(surovy)
    elif typ.startswith("text/"):
        text = _prosty_text(surovy)
    else:
        return Text(None, zdroj, f"nepodporovaný typ obsahu: {_bezpecny_kus(typ, 60)}", odp.url, http=odp.status)
    if not text:
        return Text(None, zdroj, "prázdný text", odp.url, http=odp.status)
    doi_url = _doi_z_url(odp.url)
    return Text(text, zdroj, "", odp.url, odp.oriznuto, http=odp.status, clanek=clanek or bool(doi_url),
                doi=doi or doi_url)


# ---------------------------------------------------------------------------
# PDF (volitelně: pypdf, nebo pdftotext v PATH; žádná povinná závislost)
# ---------------------------------------------------------------------------
def _pdf_ctecky() -> List[str]:
    """Dostupné čtečky PDF v pořadí použití."""
    ctecky = []
    try:
        if importlib.util.find_spec("pypdf") is not None:
            ctecky.append("pypdf")
    except (ImportError, ValueError):
        pass
    if shutil.which("pdftotext"):
        ctecky.append("pdftotext")
    return ctecky


def _pdf_pypdf(data: bytes) -> str:
    import pypdf  # volitelná závislost
    logging.getLogger("pypdf").setLevel(logging.ERROR)  # varování o vadných PDF nepatří do výstupu
    ctecka = pypdf.PdfReader(io.BytesIO(data), strict=False)
    if ctecka.is_encrypted:
        ctecka.decrypt("")  # PDF jen s prázdným uživatelským heslem; jinak výjimka
    zacatek = time.monotonic()
    casti = []
    for i, strana in enumerate(ctecka.pages):
        if i >= MAX_STRAN_PDF or time.monotonic() - zacatek > MAX_CAS_PDF:
            break
        casti.append(strana.extract_text() or "")
    return "\n\n".join(casti)


def _pdf_pdftotext(data: bytes) -> str:
    program = shutil.which("pdftotext")
    if not program:
        raise FileNotFoundError("pdftotext")
    with tempfile.TemporaryDirectory(prefix="citace-pdf-") as adresar:
        cesta = os.path.join(adresar, "vstup.pdf")
        with open(cesta, "wb") as f:
            f.write(data)
        # Seznam argumentů, žádný shell; výstup na stdout („-“).
        r = subprocess.run([program, "-q", "-enc", "UTF-8", "-nopgbrk", "-l", str(MAX_STRAN_PDF), cesta, "-"],
                           capture_output=True, timeout=MAX_CAS_PDF, check=False)
    if r.returncode != 0:
        raise ValueError(f"pdftotext skončil kódem {r.returncode}")
    return r.stdout[: 4 * MAX_BAJTU].decode("utf-8", errors="replace")


def _uprav_pdf_text(s: str) -> str:
    """Text z PDF: ligatury (NFKC), dělení slov na konci řádku, řádky odstavce spojit, odstavce = prázdný řádek."""
    s = unicodedata.normalize("NFKC", s).replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n\n")
    s = re.sub(r"(\w)-\n(?=[a-z])", r"\1", s)
    return _prosty_text(s)


def pdf_na_text(data: bytes, ctecky: Optional[List[str]] = None) -> Tuple[Optional[str], str]:
    """(text, popis). Zkouší čtečky v pořadí; text výjimky se nevypisuje (může nést obsah souboru)."""
    ctecky = _pdf_ctecky() if ctecky is None else ctecky
    if not ctecky:
        return None, "chybí pypdf i pdftotext"
    chyby = []
    for c in ctecky:
        try:
            surovy = _pdf_pypdf(data) if c == "pypdf" else _pdf_pdftotext(data)
        except Exception as e:  # čtečky PDF vyhazují různé výjimky (vadné, šifrované, timeout)
            chyby.append(f"{c}: {type(e).__name__}")
            continue
        text = _uprav_pdf_text(surovy)
        if len(text) >= MIN_TEXT:
            return text, c
        chyby.append(f"{c}: bez textové vrstvy (sken?)")
    return None, "; ".join(chyby)


def _pdf_zdroj(zdroj: str) -> str:
    if zdroj.startswith("wayback:") or zdroj.endswith("pdf"):
        return zdroj
    if zdroj == "html":
        return "pdf"
    return zdroj.replace("-html", "") + "-pdf"


def _text_z_pdf(odp: Odpoved, zdroj: str) -> Text:
    zdroj = _pdf_zdroj(zdroj)
    if not _pdf_ctecky():
        return Text(None, zdroj, "PDF – nelze přečíst: chybí pypdf i pdftotext", odp.url, http=odp.status, pdf=True)
    text, popis = pdf_na_text(odp.telo)
    if not text:
        pozn = "; PDF oříznuto na 3 MB" if odp.oriznuto else ""
        return Text(None, zdroj, f"PDF – text nelze přečíst ({popis}){pozn}", odp.url, http=odp.status, pdf=True)
    return Text(text, zdroj, f"text z PDF ({popis})", odp.url, odp.oriznuto, http=odp.status, pdf=True,
                doi=_doi_z_url(odp.url))


# ---------------------------------------------------------------------------
# Markdown -> text (README, issue, soubory z GitHubu)
# ---------------------------------------------------------------------------
_MD_KOMENTAR = re.compile(r"<!--.*?-->", re.S)
_MD_AUTOLINK = re.compile(r"<((?:https?|mailto):[^<>\s]{1,2000})>")
_MD_BLOKOVY_TAG = re.compile(r"</?(?:p|div|br|h[1-6]|li|ul|ol|tr|table|thead|tbody|details|summary|section|"
                             r"blockquote|pre|hr|dl|dt|dd)\b[^<>]{0,2000}>", re.I)
_MD_TAG = re.compile(r"</?[A-Za-z][\w:-]*(?:\s[^<>]{0,2000})?/?>")
_MD_OBRAZEK = re.compile(r"!\[([^\]\n]{0,500})\](?:\((?:[^()\n]|\([^()\n]*\)){0,2000}\)|\[[^\]\n]{0,200}\])")
_MD_ODKAZ = re.compile(r"\[([^\]\n]{1,500})\](?:\((?:[^()\n]|\([^()\n]*\)){0,2000}\)|\[[^\]\n]{0,200}\])")
_MD_DEFINICE = re.compile(r"^\s{0,3}\[[^\]\n]{1,500}\]:\s*\S")
_MD_NADPIS = re.compile(r"^\s{0,3}#{1,6}(?:\s+|$)")
_MD_SEZNAM = re.compile(r"^\s*(?:[-*+]|\d{1,9}[.)])\s+(?:\[[ xX]\]\s+)?")
_MD_CITACE = re.compile(r"^\s{0,3}(?:>\s?)+")
_MD_ODDELOVAC_TABULKY = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$")
_MD_LINKA = re.compile(r"^\s{0,3}(?:(?:-\s*){3,}|(?:\*\s*){3,}|(?:_\s*){3,}|(?:=\s*){3,})$")
_MD_PLOT = re.compile(r"^\s{0,3}(?:```|~~~)")
_MD_ZVYRAZNENI = re.compile(r"\*\*|__|~~|(?<![\w*])[*_](?=\S)|(?<=\S)[*_](?![\w*])")


def _md_radek(r: str) -> str:
    r = _MD_OBRAZEK.sub(lambda m: m.group(1), r)
    r = _MD_ODKAZ.sub(lambda m: m.group(1), r)
    r = _MD_ZVYRAZNENI.sub("", r).replace("`", "")
    return " ".join(r.split())


def markdown_na_text(md: str) -> str:
    """Markdown (s vloženým HTML) -> text: odstavce, položky seznamů, nadpisy a řádky tabulek na řádky;
    odkazy a obrázky -> jejich text; HTML značky a komentáře pryč."""
    md = md.replace("\r\n", "\n").replace("\r", "\n")
    md = _MD_KOMENTAR.sub("", md)
    md = _MD_AUTOLINK.sub(r"\1", md)
    md = _MD_BLOKOVY_TAG.sub("\n\n", md)
    md = _MD_TAG.sub("", md)
    odstavce: List[str] = []
    aktualni: List[str] = []

    def uzavri():
        if aktualni:
            odstavce.append(" ".join(aktualni))
            aktualni.clear()

    v_kodu = False
    for radek in md.split("\n"):
        if _MD_PLOT.match(radek):
            uzavri()
            v_kodu = not v_kodu
            continue
        if v_kodu:
            if radek.strip():
                odstavce.append(" ".join(radek.split()))
            continue
        if not radek.strip() or _MD_LINKA.match(radek) or _MD_DEFINICE.match(radek) \
                or _MD_ODDELOVAC_TABULKY.match(radek):
            uzavri()
            continue
        samostatny = False
        if _MD_NADPIS.match(radek):
            radek = _MD_NADPIS.sub("", radek).rstrip("# ")
            samostatny = True
        else:
            radek = _MD_CITACE.sub("", radek)
            if _MD_SEZNAM.match(radek):
                uzavri()
                radek = _MD_SEZNAM.sub("", radek)
            elif radek.lstrip().startswith("|") or radek.count("|") >= 2:  # řádek tabulky
                radek = " | ".join(b.strip() for b in radek.strip().strip("|").split("|") if b.strip())
                samostatny = True
        radek = _md_radek(radek)
        if samostatny:
            uzavri()
            if radek:
                odstavce.append(radek)
        elif radek:
            aktualni.append(radek)
    uzavri()
    return _uklid_text(html_mod.unescape("\n".join(odstavce)))


def _chyba_githubu(odp: Odpoved, zdroj: str) -> Text:
    t = _text_z_odpovedi(odp, zdroj)
    if not t.proxy and odp.status in (403, 429) and odp.hlavicky.get("x-ratelimit-remaining", "").strip() == "0":
        t = dataclasses.replace(t, duvod=f"HTTP {odp.status}: GitHub API – vyčerpán limit požadavků "
                                         f"(bez přihlášení 60/h)")
    return t


def _text_github(zdroj: dict) -> Text:
    gh = zdroj["github"]
    if gh["druh"] == "readme":
        odp = stahni(gh["api"], prijmout="application/vnd.github.raw")
        if not odp.ok:
            return _chyba_githubu(odp, "github-readme")
        text = markdown_na_text(dekoduj(odp.telo, odp.hlavicky.get("content-type", "")))
        if not text:
            return Text(None, "github-readme", "prázdné README", odp.url, http=odp.status)
        return Text(text, "github-readme", "", odp.url, odp.oriznuto, http=odp.status)
    if gh["druh"] == "issue":
        odp = stahni(gh["api"], prijmout="application/vnd.github+json")
        if not odp.ok:
            return _chyba_githubu(odp, "github-issue")
        data = _json(odp)
        if not isinstance(data, dict):
            return Text(None, "github-issue", "GitHub API: neplatná odpověď", odp.url, http=odp.status)
        casti = [" ".join(_retezec(data.get("title")).split()), markdown_na_text(_retezec(data.get("body")))]
        pozn = ""
        k = stahni(gh["komentare"], prijmout="application/vnd.github+json")
        komentare = _json(k) if k.ok else None
        if isinstance(komentare, list):
            casti += [markdown_na_text(_retezec(c.get("body"))) for c in komentare if isinstance(c, dict)]
            if len(komentare) >= 100:
                pozn = "načteno jen prvních 100 komentářů"
        else:
            pozn = f"komentáře nenačteny ({k.popis() if not k.ok else 'neplatná odpověď'})"
        text = _uklid_text("\n".join(c for c in casti if c))
        if not text:
            return Text(None, "github-issue", "prázdné issue", odp.url, http=odp.status)
        return Text(text, "github-issue", pozn, odp.url, http=odp.status)
    odp = stahni(gh["raw"])
    if not odp.ok:
        return _chyba_githubu(odp, "github-soubor")
    if je_pdf(odp):
        return _text_z_pdf(odp, "github-soubor")
    if b"\x00" in odp.telo[:8000]:
        return Text(None, "github-soubor", "binární soubor", odp.url, http=odp.status)
    surovy = dekoduj(odp.telo, odp.hlavicky.get("content-type", ""))
    pripona = gh.get("cesta", "").rsplit(".", 1)[-1].lower() if "." in gh.get("cesta", "") else ""
    if pripona in _PRIPONY_MD:
        text = markdown_na_text(surovy)
    elif pripona in ("html", "htm", "xhtml"):
        text = html_na_text(surovy)
    elif odp.typ.startswith("text/") or odp.typ in ("", "application/octet-stream", "application/json"):
        text = _prosty_text(surovy)
    else:
        return Text(None, "github-soubor", f"nepodporovaný typ obsahu: {_bezpecny_kus(odp.typ, 60)}", odp.url,
                    http=odp.status)
    if not text:
        return Text(None, "github-soubor", "prázdný soubor", odp.url, http=odp.status)
    return Text(text, "github-soubor", "", odp.url, odp.oriznuto, http=odp.status)


def _text_wayback(url: str, clanek: bool = False) -> Text:
    """Text z nejnovějšího snímku Waybacku; zdroj = „wayback:RRRR-MM-DD“ (datum skutečného snímku)."""
    snimek, popis = wayback_snimek(url)
    if not snimek:
        return Text(None, "wayback", popis)
    odp = stahni(snimek["url"])
    m = _SNIMEK_URL.match(odp.url or "")  # Wayback může přesměrovat na sousední snímek
    datum = _datum_z_casu(m.group(1)) if m else snimek["datum"]
    t = _text_z_odpovedi(odp, f"wayback:{datum}")
    if not t.text:
        return dataclasses.replace(t, duvod=f"snímek {datum}: {t.duvod}")
    return dataclasses.replace(t, clanek=clanek or t.clanek,
                               duvod="; ".join(p for p in (t.duvod, f"archivní snímek z {datum}") if p))


def _text_arxiv(ident: str) -> Text:
    odp = stahni(f"https://arxiv.org/html/{ident}")
    t = _text_z_odpovedi(odp, "arxiv-html")
    if t.text and len(t.text) >= 1000 and "html is not available" not in t.text[:3000].lower():
        return dataclasses.replace(t, clanek=True)
    duvod_html = t.duvod or "HTML verze chybí nebo je krátká"
    abs_odp = stahni(f"https://arxiv.org/abs/{ident}")
    if not abs_odp.ok:
        return Text(None, "arxiv", f"HTML: {duvod_html}; abs: {abs_odp.popis()}", abs_odp.url, http=abs_odp.status,
                    chyba_site=bool(abs_odp.chyba), proxy=odmitnuto_proxy(abs_odp), clanek=True)
    surovy = dekoduj(abs_odp.telo, abs_odp.hlavicky.get("content-type", ""))
    nazev = re.search(r"<h1[^>]*class=\"[^\"]*title[^\"]*\"[^>]*>(.*?)</h1>", surovy, re.S | re.I)
    abstrakt = re.search(r"<blockquote[^>]*class=\"[^\"]*abstract[^\"]*\"[^>]*>(.*?)</blockquote>", surovy, re.S | re.I)
    if not abstrakt:
        return Text(None, "arxiv", f"HTML: {duvod_html}; abstrakt na abs stránce nenalezen", abs_odp.url,
                    http=abs_odp.status, clanek=True)
    popisky = re.compile(r"<span[^>]*class=\"descriptor\"[^>]*>.*?</span>", re.S | re.I)  # „Title:“, „Abstract:“
    casti = ([popisky.sub("", nazev.group(1))] if nazev else []) + [popisky.sub("", abstrakt.group(1))]
    text = html_na_text("".join(f"<p>{c}</p>" for c in casti))
    return Text(text, "arxiv-abstrakt", f"jen abstrakt (HTML: {duvod_html})", abs_odp.url, http=abs_odp.status,
                clanek=True)


def _text_arxiv_pdf(ident: str) -> Text:
    """Záloha pro arXiv bez HTML verze: plný text z PDF (jen s pypdf / pdftotext)."""
    t = _text_z_odpovedi(stahni(f"https://arxiv.org/pdf/{ident}"), "arxiv-pdf")
    return dataclasses.replace(t, clanek=True)


def _epmc_hledej(dotaz: str) -> Tuple[Optional[dict], str]:
    url = ("https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=" + urllib.parse.quote(dotaz)
           + "&format=json&resultType=core&pageSize=1")
    odp = stahni(url, prijmout="application/json")
    if not odp.ok:
        return None, f"Europe PMC: {odp.popis()}"
    data = _json(odp)
    if not isinstance(data, dict):
        return None, "Europe PMC: neplatná odpověď"
    vysl = [r for r in _seznam(_slovnik(data.get("resultList")).get("result")) if isinstance(r, dict)]
    return (vysl[0] if vysl else None), ("" if vysl else "Europe PMC: záznam nenalezen")


def _text_pmc(pmcid: str) -> Text:
    odp = stahni(f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML",
                 prijmout="application/xml")
    if odp.ok and odp.telo:
        text = jats_na_text(odp.telo)
        if len(text) >= MIN_TEXT:
            return Text(text, "europepmc-fulltext", "", odp.url, odp.oriznuto, http=odp.status, clanek=True)
    zaznam, chyba = _epmc_hledej(f"PMCID:{pmcid}")
    plny = "plný text: " + (odp.popis() + (" (i po opakování)" if odp.opakovani else "") if not odp.ok
                            else "bez textu")
    return _text_epmc_abstrakt(zaznam, f"{plny}; {chyba}".strip("; "))


def _text_epmc_abstrakt(zaznam: Optional[dict], duvod: str) -> Text:
    if zaznam and isinstance(zaznam.get("abstractText"), str) and zaznam.get("abstractText"):
        text = html_na_text("<p>" + _retezec(zaznam.get("title")) + "</p><p>" + zaznam["abstractText"] + "</p>")
        return Text(text, "europepmc-abstrakt", f"jen abstrakt ({duvod})" if duvod else "jen abstrakt",
                    clanek=True, doi=normalizuj_doi(_retezec(zaznam.get("doi"))))
    if zaznam:  # Z2 v20: záznam existoval, ale bez abstraktu – dřív to z důvodu nebylo poznat
        duvod = "; ".join(p for p in (duvod, "Europe PMC: záznam bez abstraktu") if p)
    return Text(None, "europepmc", duvod or "abstrakt nenalezen", clanek=True)


def _text_epmc(ids: dict) -> Text:
    """Europe PMC podle PMCID / PMID / DOI: plný text (otevřený přístup), jinak abstrakt."""
    if ids.get("pmcid"):
        dotaz = f"PMCID:{ids['pmcid']}"
    elif ids.get("pmid"):
        dotaz = f"EXT_ID:{ids['pmid']} AND SRC:MED"
    elif ids.get("doi"):
        dotaz = f'DOI:"{ids["doi"]}"'
    else:
        return Text(None, "europepmc", "chybí DOI, PMID i PMCID")
    zaznam, chyba = _epmc_hledej(dotaz)
    if zaznam and zaznam.get("pmcid") and zaznam.get("isOpenAccess") == "Y":
        t = _text_pmc(zaznam["pmcid"])
        if t.text:
            return t
    return _text_epmc_abstrakt(zaznam, chyba)


def _text_pubmed(pmid: str) -> Text:
    zaznam, chyba = _epmc_hledej(f"EXT_ID:{pmid} AND SRC:MED")
    if zaznam and zaznam.get("pmcid"):
        t = _text_pmc(zaznam["pmcid"])
        if t.text:
            return t
    return _text_epmc_abstrakt(zaznam, chyba)


def _abstrakt_openalex(data: dict) -> Optional[str]:
    """OpenAlex ukládá abstrakt jako invertovaný index {slovo: [pozice]}."""
    inv = data.get("abstract_inverted_index")
    if not isinstance(inv, dict):
        return None
    pozice: Dict[int, str] = {}
    for slovo, seznam in inv.items():
        for p in _seznam(seznam):
            if isinstance(p, int) and 0 <= p < 20000:
                pozice[p] = str(slovo)
    text = " ".join(pozice[i] for i in sorted(pozice))
    return html_na_text("<p>" + text + "</p>") or None  # abstrakty OpenAlexu občas nesou HTML značky


def _oa_url_openalex(data: dict) -> Optional[str]:
    """URL otevřené kopie z OpenAlexu: PDF (jen když umíme PDF číst), jinak stránka."""
    mista = [_slovnik(data.get("best_oa_location"))] + [_slovnik(m) for m in _seznam(data.get("locations"))]
    klice = ("pdf_url", "landing_page_url") if _pdf_ctecky() else ("landing_page_url",)
    for klic in klice:
        for m in mista:
            if m.get("is_oa") is False:
                continue
            u = m.get(klic)
            if isinstance(u, str) and povolena_url(u):
                return u
    u = _slovnik(data.get("open_access")).get("oa_url")
    return u if isinstance(u, str) and povolena_url(u) else None


def _klic_zdroje(zdroj: dict) -> str:
    if zdroj.get("id"):
        return f"{zdroj.get('typ')}:{str(zdroj.get('id')).lower()}"
    return re.sub(r"^https?://(?:www\.)?", "", (zdroj.get("url") or "").lower()).rstrip("/")


def _text_openalex(doi: str, vyzkousene: set) -> Text:
    """Záloha přes OpenAlex: otevřená kopie (OA URL, jen dosud nezkoušená), jinak abstrakt."""
    oa = _openalex_work(doi)
    data = _json(oa) if oa.ok else None
    if not isinstance(data, dict):
        return Text(None, "openalex", f"OpenAlex: {oa.popis() if not oa.ok else 'neplatná odpověď'}")
    duvody = []
    oa_url = _oa_url_openalex(data)
    if oa_url:
        cil = rozpoznej_zdroj(url=oa_url)
        klic = _klic_zdroje(cil)
        if cil["typ"] != "neplatna" and klic not in vyzkousene:
            vyzkousene.add(klic)
            t = ziskej_text(cil, hloubka=1)
            if t.text:
                return dataclasses.replace(t, zdroj=f"openalex-oa:{t.zdroj}", clanek=True)
            duvody.append(f"OA kopie: {t.duvod}")
        else:
            duvody.append("OA kopie už zkoušena")
    else:
        duvody.append("bez OA kopie")
    abstrakt = _abstrakt_openalex(data)
    if abstrakt:
        return Text(abstrakt, "openalex-abstrakt", f"jen abstrakt ({'; '.join(duvody)})", clanek=True, doi=doi)
    return Text(None, "openalex", "; ".join(duvody + ["bez abstraktu"]))


def ziskej_text(zdroj: dict, hloubka: int = 0) -> Text:
    typ = zdroj.get("typ")
    if typ == "neplatna":
        return Text(None, "", "neplatná URL/DOI nebo nepodporované schéma (jen http/https)")
    if typ == "arxiv":
        return _text_arxiv(zdroj["id"])
    if typ == "pmc":
        return _text_pmc(zdroj["id"])
    if typ == "pubmed":
        return _text_pubmed(zdroj["id"])
    if typ == "github":
        return _text_github(zdroj)
    if typ == "pdf":
        if not _pdf_ctecky():  # bez čtečky nemá smysl PDF stahovat
            return Text(None, "pdf", "PDF – nelze přečíst: chybí pypdf i pdftotext (nestahuje se)",
                        zdroj.get("url"), pdf=True)
        t = _po_stazeni(stahni(zdroj["url"]), "pdf", hloubka)
        return t if t.text else dataclasses.replace(t, pdf=True)
    if typ == "doi":
        doi = zdroj["id"]
        zaznam, _ = _epmc_hledej(f'DOI:"{doi}"')
        if zaznam and zaznam.get("pmcid") and zaznam.get("isOpenAccess") == "Y":
            t = _text_pmc(zaznam["pmcid"])
            if t.text:
                return t
        odp = stahni("https://doi.org/" + _doi_v_url(doi))
        t = _po_stazeni(odp, "doi", hloubka)
        if not t.text and zaznam and zaznam.get("abstractText"):
            # Vydavatel často blokuje roboty (403) nebo vyžaduje JavaScript; Europe PMC má aspoň abstrakt.
            a = _text_epmc_abstrakt(zaznam, f"vydavatel: {t.duvod}")
            if a.text:
                return a
        return dataclasses.replace(t, clanek=True, doi=t.doi or doi)
    if typ == "html":
        odp = stahni(zdroj["url"])
        return _po_stazeni(odp, "html", hloubka)
    return Text(None, "", f"neznámý typ zdroje {typ}")


def _po_stazeni(odp: Odpoved, zdroj: str, hloubka: int) -> Text:
    """Po přesměrování (např. doi.org -> arXiv/PMC/GitHub) použij specializovanou cestu."""
    if hloubka == 0 and odp.url and povolena_url(odp.url):
        cil = rozpoznej_zdroj(url=odp.url)
        if cil["typ"] in ("arxiv", "pmc", "pubmed", "github"):
            return ziskej_text(cil, hloubka + 1)
    t = _text_z_odpovedi(odp, zdroj if zdroj != "doi" else "doi-html")
    return t


# ---------------------------------------------------------------------------
# Věty, okna, pokyny pro AI
# ---------------------------------------------------------------------------
_ZKRATKY = {"e.g", "i.e", "al", "fig", "figs", "eq", "eqs", "ref", "refs", "no", "nos", "vol", "pp", "p",
            "vs", "cf", "dr", "mr", "mrs", "ms", "prof", "inc", "ltd", "co", "approx", "ca", "sec", "tab",
            "tj", "napr", "atd", "resp", "tzv", "obr", "c", "str", "viz", "srov", "mj", "aj", "apod", "st",
            "jr", "sr", "u.s", "e.g.", "i.e.", "ph.d", "suppl", "ed", "eds", "et", "nr", "cca", "tzn"}
_HRANICE = re.compile(r"[.!?…]+[\"'”’»)\]]*(?=\s)")


_DALSI_ZNAK = re.compile(r"\s*(\S)")
_POSLEDNI_SLOVO = re.compile(r"(\S+?)[.!?…]+[\"'”’»)\]]*$")


def rozdel_na_vety(odstavec: str) -> List[str]:
    # Lineárně: žádné kopírování zbytku odstavce u každé hranice (dřív odstavec[konec:].lstrip()
    # => O(n²), 1,7 MB odstavec ~ 9 s, 3 MB desítky sekund) a zkratka se hledá jen v konci kandidáta.
    vety: List[str] = []
    start = _DALSI_ZNAK.match(odstavec).start(1) if odstavec.strip() else len(odstavec)
    for m in _HRANICE.finditer(odstavec):
        konec = m.end()
        dalsi = _DALSI_ZNAK.match(odstavec, konec)
        if not dalsi:
            break
        if dalsi.group(1).islower() or konec - start < 4:
            continue
        if m.group().startswith("."):
            posl = _POSLEDNI_SLOVO.search(odstavec[max(start, konec - 80):konec])
            slovo = _normalizuj(posl.group(1)).lstrip("([{\"'„“") if posl else ""
            if slovo in _ZKRATKY or re.fullmatch(r"[a-z]", slovo):
                continue
        vety.append(odstavec[start:konec].strip())
        start = dalsi.start(1)
    zbytek = odstavec[start:].strip()
    if zbytek:
        vety.append(zbytek)
    return vety


def _rozsekej(veta: str, max_znaku: int = MAX_PASAZ, krok: int = 260) -> List[str]:
    if len(veta) <= max_znaku:
        return [veta]
    slova = veta.split()
    kusy: List[str] = []
    i = 0
    while i < len(slova):
        kus: List[str] = []
        delka = 0
        j = i
        while j < len(slova) and delka + len(slova[j]) + (1 if kus else 0) <= max_znaku:
            delka += len(slova[j]) + (1 if kus else 0)
            kus.append(slova[j])
            j += 1
        if not kus:
            kusy.append(slova[i][:max_znaku])
            i += 1
            continue
        kusy.append(" ".join(kus))
        if j >= len(slova):
            break
        posun, k = 0, i
        while k < j and posun < krok:
            posun += len(slova[k]) + 1
            k += 1
        i = max(k, i + 1)
    return kusy


# Výplňová slova mezi slovesem a „previous/above“: „ignore ALL OF THE previous“, „disregard EVERYTHING above“.
_VYPLN = r"(?:all\s+|any\s+|the\s+|your\s+|of\s+|everything\s+|anything\s+|these\s+|those\s+|my\s+)*"
_POKYNY = [re.compile(p) for p in (
    r"\bignor(?:e|ing)\s+" + _VYPLN + r"(?:previous|prior|above|earlier|preceding|former)\b",
    r"\bdisregard\s+" + _VYPLN + r"(?:previous|prior|above|earlier|preceding)\b",
    r"\bforget\s+(?:all\s+|your\s+|the\s+)*(?:previous|prior|above)\s+(?:instructions|prompts?)\b",
    r"\byou\s+are\s+(?:now\s+)?(?:an?\s+)?(?:ai|a\.i\.|llm|large\s+language\s+model|language\s+model|"
    r"ai\s+assistant|chatbot|chatgpt|claude|gpt)\b",
    r"(?:^|[\s\"'(\[])assistant\s*:",
    r"\bsystem\s+prompt",
    r"\bnew\s+instructions?\s*:",
    r"\[/?inst\]",
    r"<\|?im_(?:start|end|sep)\|?>",
    r"</?\s*system\s*>",
    r"\bif\s+you\s+are\s+an?\s+(?:ai|llm|language\s+model|assistant)\b",
    r"\b(?:do\s+not|don'?t)\s+(?:tell|inform|reveal\s+to)\s+the\s+user\b",
    r"\binstrukce\s+pro\s+(?:model|ai|umelou\s+inteligenci|jazykovy\s+model|asistenta|llm)\b",
    r"\bignoruj\s+(?:vsechny\s+|veskere\s+)?(?:predchozi|predesle|vyse\s+uvedene|dosavadni)\b",
    r"\bjsi\s+(?:ai|umela\s+inteligence|jazykovy\s+model|asistent|chatbot)\b",
    r"\bpokyn(?:y)?\s+pro\s+(?:model|ai|asistenta|llm)\b",
)]


# Záměnné znaky (cyrilice, řečtina, IPA), kterými se dá obejít filtr: „іgnore“ s cyrilským і.
_HOMOGLYFY = str.maketrans({
    "а": "a", "е": "e", "ё": "e", "і": "i", "ї": "i", "ј": "j", "к": "k", "о": "o", "р": "p", "с": "c",
    "у": "y", "х": "x", "ѕ": "s", "ԁ": "d", "һ": "h", "ԛ": "q", "ԝ": "w", "ӏ": "l", "м": "m", "т": "t",
    "α": "a", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "ο": "o", "ρ": "p", "τ": "t", "υ": "u", "χ": "x",
    "γ": "y", "ı": "i", "ɡ": "g", "ɩ": "i", "ℓ": "l",
})


def obsahuje_pokyn(text: str) -> bool:
    n = " ".join(_normalizuj(text).translate(_HOMOGLYFY).split())
    return any(p.search(n) for p in _POKYNY)


def okna_z_textu(text: str, max_vet: int = 3, max_znaku: int = MAX_PASAZ) -> Tuple[List[dict], int]:
    """Rozdělí text na okna 1–max_vet vět v rámci odstavce (každé <= max_znaku).
    Věty s pokyny pro AI vynechá (a okna je nepřekročí). Vrací (okna, počet vynechaných)."""
    okna: List[dict] = []
    vynechano = 0
    idx = 0

    def vyprazdni(segment):
        nonlocal vynechano
        for i in range(len(segment)):
            for n in range(1, max_vet + 1):
                if i + n > len(segment):
                    break
                t = " ".join(u for _, u in segment[i:i + n])
                if len(t) > max_znaku:
                    break
                if n > 1 and obsahuje_pokyn(t):  # pokyn rozdělený přes hranici vět
                    vynechano += 1
                    continue
                okna.append({"text": t, "od": segment[i][0], "do": segment[i + n - 1][0]})

    for odstavec in text.split("\n"):
        odstavec = odstavec.strip()
        if not odstavec:
            continue
        segment: List[Tuple[int, str]] = []
        for veta in rozdel_na_vety(odstavec):
            if obsahuje_pokyn(veta):
                vynechano += 1
                vyprazdni(segment)
                segment = []
                continue
            for kus in _rozsekej(veta, max_znaku):
                segment.append((idx, kus))
                idx += 1
        vyprazdni(segment)
    return okna, vynechano


# ---------------------------------------------------------------------------
# Skórování
# ---------------------------------------------------------------------------
_STOP = set("""
a an the of in on at to for from by with and or but is are was were be been being this that these those it its
as into than then there their they them we our you your he she his her not no nor so such can could may might
will would shall should do does did has have had also which who whom whose what when where why how all any each
both more most other some only own same very just over under about between after before during through above
below up down out off again further once here few i me my us if while because until against per via among
je jsou byl byla bylo byli byt se si to ten ta ty ti tak take jako ale nebo ze by aby do od po pro pri za ve ke
ku jeho jeji jejich ktery ktera ktere kteri jak jiz uz nez podle mezi na v z s k o u i
""".split())
_SLOVO_RE = re.compile(r"[^\W\d_]\w*")  # Unicode písmena (dřív jen [a-z]: ruský/řecký text = žádné tokeny)
# Číslo, nebo desetinné číslo bez úvodní nuly ve stylu APA („d = .17“, „p < .001“, „[.05,.29]“, „.17/.21“);
# tečka za slovem („analysed.17“ = horní index odkazu, „Fig.5“) desetinné číslo nezačíná.
_CISLO = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)*(?!\w)|(?<![^\s=<>≤≥(\[±≈~:−–—\-+,;/|])\.\d+(?!\w|[.,]\d)")
# Skupina tisíců oddělená mezerou („1 234“, „12 345,5“; česky běžné, model píše i obyčejnou mezeru místo
# nezlomitelné). Ne za časem, rozsahem či slovem („14:30 100“, „18–65 120“).
_SKUPINY_TISICU = (r"(?<![\w.,:–—-])\d{1,3}(?:[ \u00a0\u202f\u2009]\d{3})+(?:[.,]\d+)?(?!\w|[.,]\d)")
_CISLO_NEBO_TISICE = re.compile(f"(?P<tis>{_SKUPINY_TISICU})|{_CISLO.pattern}")
_TECKA_STRED = re.compile("(?<=\\d)\u00b7(?=\\d)")  # Lancet: „0·17“


class _CisloZMezery(frozenset):
    """Číslo tvrzení zapsané s obyčejnou mezerou mezi tisíci („2 141“). Zápis je dvojznačný, proto ve zdroji
    smí sedět i se stejně dvojznačným slepeným tvarem („Study 2 141“); jiné číslo jen s přímým tvarem."""
    __slots__ = ()


def _priprav_cisla(text: str) -> str:
    return _TECKA_STRED.sub(".", _NEVIDITELNE.sub("", text))


def _kmen(t: str) -> str:
    if len(t) > 4 and t.endswith("ies"):
        t = t[:-3] + "y"
    elif len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        t = t[:-1]
    return t[:DELKA_KMENE]


def tokeny(text: str) -> List[str]:
    return [_kmen(t) for t in _SLOVO_RE.findall(_normalizuj(text)) if len(t) > 1 and t not in _STOP]


def _norm_des(s: str) -> str:
    if "." in s:
        cela, des = s.split(".", 1)
        des = des.rstrip("0")
        cela = cela.lstrip("0") or "0"
        return cela + ("." + des if des else "")
    return s.lstrip("0") or "0"


def kanon_cisla(s: str) -> frozenset:
    """Kanonické podoby čísla: '1,000' -> {'1000'}, '2,500' -> {'2500','2.5'}, '0,500' -> {'0.5'},
    '3,50' -> {'3.5'}, '1.234,5' -> {'1234.5'}."""
    s = re.sub("[\u00a0\u202f\u2009 ]", "", s)
    formy = set()
    if re.fullmatch(r"\d{1,3}(?:([.,])\d{3})(?:\1\d{3})*", s):
        jedna_tecka = s.count(",") + s.count(".") == 1
        if not (jedna_tecka and s[0] == "0"):  # „0,500“ je desetinné číslo, ne 500
            formy.add(str(int(re.sub(r"[.,]", "", s))))
        # Desetinný výklad jen když desetinná část není „000“: „1,000“ jako 1 by se shodovalo
        # s „Figure 1“, „10,000“ s „10“ (falešná shoda čísel s vysokou vahou).
        if jedna_tecka and not s.endswith("000"):
            formy.add(_norm_des(s.replace(",", ".")))
    elif re.fullmatch(r"\d+(?:[.,]\d+)?", s):
        formy.add(_norm_des(s.replace(",", ".")))
    elif re.fullmatch(r"\.\d+", s):  # „.17“ = 0.17
        formy.add(_norm_des("0" + s))
    elif re.fullmatch(r"\d{1,3}(?:,\d{3})+\.\d+", s):
        formy.add(_norm_des(s.replace(",", "")))
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+,\d+", s):
        formy.add(_norm_des(s.replace(".", "").replace(",", ".")))
    else:
        formy.add(s.replace(",", "."))
    return frozenset(formy)


def _rozbor_zdroje(text: str) -> Tuple[List[frozenset], set, set]:
    """Čísla textu zdroje: (přímé tvary v pořadí, jejich sjednocení, slepené tvary). Skupina s obyčejnou
    mezerou („12 345“) dá části mezi přímé tvary (v anglickém zdroji to bývají dvě čísla vedle sebe, např.
    sloupce tabulky nebo „Study 2 141“) a slepený tvar zvlášť; nezlomitelná mezera je vždy oddělovač tisíců."""
    seznam: List[frozenset] = []
    prime: set = set()
    slepene: set = set()
    videne: set = set()

    def pridej(k: frozenset) -> None:
        prime.update(k)
        if k not in videne:
            videne.add(k)
            seznam.append(k)

    for m in _CISLO_NEBO_TISICE.finditer(_priprav_cisla(text)):
        if m.group("tis") and " " in m.group():
            slepene.update(kanon_cisla(m.group()))
            for c in _CISLO.finditer(m.group()):
                pridej(kanon_cisla(c.group()))
        else:
            pridej(kanon_cisla(m.group()))
    return seznam, prime, slepene


def cisla(text: str) -> List[frozenset]:
    """Čísla textu zdroje (přímé tvary, viz _rozbor_zdroje)."""
    return _rozbor_zdroje(text)[0]


def _je_ve_zdroji(c: frozenset, prime: set, slepene: set) -> bool:
    return bool(c & prime) or (isinstance(c, _CisloZMezery) and bool(c & slepene))


# Jednotka hned za číslem (nebo měna před ním): „5 %“, „3×“, „2024 ms“, „$2020“ jsou údaje, ne šum.
_JEDNOTKA_ZA = re.compile(r"\s?(?:%|‰|°|×|[$€£¥]|(?:x|ms|min|kg|mg|µg|ug|ml|km|cm|mm|nm|kb|mb|gb|tb|kib|mib|gib|"
                          r"hz|khz|mhz|ghz|kw|mw|kwh|mwh|mmhg|usd|eur|czk|kč|kc|pp|p\.b\.)(?![^\W\d_]))", re.I)
_MENA_PRED = re.compile(r"[$€£¥]\s?$")
_LETOPOCET = re.compile(r"(?:1[89]|20)\d\d")


def cisla_tvrzeni(text: str) -> List[frozenset]:
    """Čísla tvrzení, která se porovnávají se zdrojem. Bez jednociferných čísel a samotných letopočtů
    (1800–2099) bez jednotky: v Z2 dávala falešné shody (URL s „2026“ a „7“, „Sonnet 4“, „6 agentů“).
    Tisíce oddělené mezerou („1 234“, „2 000“) jsou v tvrzení jedno číslo (český zápis), nikdy letopočet."""
    t = _priprav_cisla(text)
    vysl: List[frozenset] = []
    for m in _CISLO_NEBO_TISICE.finditer(t):
        s = m.group()
        if m.group("tis"):
            k = kanon_cisla(s)
            k = _CisloZMezery(k) if " " in s else k
            if k not in vysl:
                vysl.append(k)
            continue
        if len(s) == 1 or _LETOPOCET.fullmatch(s):
            ma_jednotku = _JEDNOTKA_ZA.match(t, m.end()) or _MENA_PRED.search(t[max(0, m.start() - 2):m.start()])
            if not ma_jednotku:
                continue
        k = kanon_cisla(s)
        if k not in vysl:
            vysl.append(k)
    return vysl


def _cisla_vystup(c: List[frozenset]) -> List[str]:
    return [sorted(k)[0] for k in c]


def ohodnot_okna(tvrzeni: str, okna: List[dict], k: int = 3) -> List[dict]:
    """Vrátí top-k oken (bez překryvu) s klíči text, skore, cisla_shoda, slozky."""
    if not okna:
        return []
    q = list(dict.fromkeys(tokeny(tvrzeni)))
    q_tok_seq = tokeny(tvrzeni)
    q_cisla = cisla_tvrzeni(tvrzeni)
    vahy = VAHY_S_CISLY if q_cisla else VAHY_BEZ_CISEL
    if not q:  # tvrzení jen z čísel
        vahy = {"bm25": 0.0, "difflib": 0.0, "cisla": 1.0}
    docs = [tokeny(o["text"]) for o in okna]
    n = len(docs)
    avgdl = (sum(len(d) for d in docs) / n) or 1.0
    df: Counter = Counter()
    for d in docs:
        df.update(set(d))
    idf = {t: math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5)) for t in q}
    idealni = sum(idf.values()) or 1.0
    predbezne = []
    for i, (o, d) in enumerate(zip(okna, docs)):
        # Binární tf (výskyt ano/ne): okno 2–3 vět jinak sbíralo body za to, že sousední věty
        # opakují stejná slova, a přebíjelo přesnou jednu větu (delší pasáže vyhrávaly).
        # Pokrytí dalších slov tvrzení se odměňuje dál, délku penalizuje normalizace BM25.
        pritomne = set(d)
        dl = len(d)
        s = 0.0
        for t in q:
            if t in pritomne:
                s += idf[t] * (BM25_K1 + 1) / (1 + BM25_K1 * (1 - BM25_B + BM25_B * dl / avgdl))
        bm = min(1.0, s / idealni) if q else 0.0
        if q_cisla:
            _, wc_prime, wc_slepene = _rozbor_zdroje(o["text"])
            zasahy = sum(1 for c in q_cisla if _je_ve_zdroji(c, wc_prime, wc_slepene))
            frac_vse = zasahy / len(q_cisla)
        else:
            frac_vse = 0.0
        # Číselná složka jen při textové shodě (Z2: skóre přesně 0,35 u oken bez jediného slova tvrzení,
        # např. URL s čísly). Tvrzení bez slov (jen čísla) se dál porovnává jen podle čísel.
        frac = frac_vse if (bm > 0 or not q) else 0.0
        predbezne.append((bm * vahy["bm25"] + frac * vahy["cisla"], i, bm, frac, frac_vse))
    predbezne.sort(key=lambda x: -x[0])
    vysledky = []
    for _, i, bm, frac, frac_vse in predbezne[:MAX_KANDIDATU_DIFFLIB]:
        if q_tok_seq:
            sm = SequenceMatcher(None, q_tok_seq, docs[i], autojunk=False)
            dif = sum(b.size for b in sm.get_matching_blocks()) / len(q_tok_seq)
        else:
            dif = 0.0
        skore = vahy["bm25"] * bm + vahy["difflib"] * dif + vahy["cisla"] * frac
        vysledky.append({"i": i, "skore": skore, "bm25": bm, "difflib": dif, "cisla": frac, "cisla_vse": frac_vse})
    vysledky.sort(key=lambda v: (-v["skore"], len(okna[v["i"]]["text"])))
    vybrane: List[dict] = []
    for v in vysledky:
        o = okna[v["i"]]
        if any(not (o["do"] < w["od"] or o["od"] > w["do"]) for w in vybrane):
            continue
        # cisla_shoda = všechna (filtrovaná) čísla tvrzení jsou v pasáži, bez ohledu na textovou shodu.
        vybrane.append({"text": o["text"][:MAX_PASAZ], "skore": round(v["skore"], 4),
                        "cisla_shoda": bool(q_cisla) and v["cisla_vse"] == 1.0,
                        "od": o["od"], "do": o["do"],
                        "slozky": {"bm25": round(v["bm25"], 3), "difflib": round(v["difflib"], 3),
                                   "cisla": round(v["cisla"], 3)}})
        if len(vybrane) >= k:
            break
    return vybrane


def cisla_chybi_v_textu(q_cisla: List[frozenset], text: str) -> List[frozenset]:
    """Čísla tvrzení, která v celém textu zdroje nejsou v žádné kanonické podobě (tvrdá kontrola G1).
    Výskyt čísla tvrzení nedokazuje; chybějící číslo je výhrada pro ověřovač a štítek."""
    if not q_cisla:
        return []
    _, prime, slepene = _rozbor_zdroje(text)
    return [c for c in q_cisla if not _je_ve_zdroji(c, prime, slepene)]


def pasaze_z_textu(tvrzeni: str, text: str, k: int = 3) -> dict:
    okna, vynechano = okna_z_textu(text)
    q_cisla = cisla_tvrzeni(tvrzeni)
    vybrane = ohodnot_okna(tvrzeni, okna, k)
    skore_max = vybrane[0]["skore"] if vybrane else 0.0
    pasaze = [{"text": _RIDICI.sub("", v["text"]), "skore": v["skore"], "cisla_shoda": v["cisla_shoda"]}
              for v in vybrane]
    if not okna:
        stav, duvod = "nenalezeno", "text neobsahuje použitelné věty"
    elif skore_max >= PRAH:
        stav, duvod = "nalezeno", f"nejlepší pasáž má skóre {skore_max:.3f} >= PRAH {PRAH}"
    else:
        stav, duvod = "nenalezeno", f"žádná pasáž nad PRAH {PRAH} (max {skore_max:.3f}); vráceni nejbližší kandidáti"
    return {"stav": stav, "duvod": duvod, "skore_max": skore_max, "pasaze": pasaze,
            "vynechano_pokynu": vynechano, "cisla_v_tvrzeni": _cisla_vystup(q_cisla),
            "cisla_chybi_ve_zdroji": _cisla_vystup(cisla_chybi_v_textu(q_cisla, text))}


# ---------------------------------------------------------------------------
# Citát: nejlepší shoda doslovného úryvku v surovém textu zdroje
# ---------------------------------------------------------------------------
# Normalizace 1:1 (délka se nemění, takže pozice jdou zpět na původní text): všechny uvozovky a apostrofy
# -> ", všechny pomlčky -> -, nezlomitelné mezery -> mezera; pak malá písmena a rozdělení na slova (_NEMEZERA).
_CITAT_MAPA = str.maketrans({**{c: '"' for c in "\"“”„‟″〝〞＂«»'‘’‚‛′‹›`´＇"},
                             **{c: "-" for c in "‐‑‒–—―−﹘﹣－"},
                             **{c: " " for c in "      "}})
_VYPUSTKA = re.compile(r"\s*(?:\[\s*(?:\.\s*){3}\]|\[\s*…\s*\]|\(\s*(?:\.\s*){3}\)|\(\s*…\s*\)|(?:\.\s*){3}|…)\s*")
# Slovo = pomlčka samostatně, nebo úsek bez mezer, uvozovek a pomlček: „accuracy—measured“ i „accuracy - measured“
# dají stejná slova a uvozovky/apostrofy (i chybějící) shodu nerozbijí („“deep research”“ = „deep research“).
_NEMEZERA = re.compile(r'-|[^\s"-]+')
_INTERPUNKCE = ".,;:!?\"()[]{}-–—'"
_RAD_CITATU = {"doslovne": 3, "temer": 2, "nenalezen": 1, "nelze": 0}


def _citat_slova(s: str) -> Tuple[List[str], List[Tuple[int, int]]]:
    t = s.translate(_CITAT_MAPA)
    mala = t.lower()
    if len(mala) != len(t):  # vzácné znaky, které se malými písmeny prodlouží (İ): ponech je, ať sedí pozice
        mala = "".join(c.lower() if len(c.lower()) == 1 else c for c in t)
    useky = [m.span() for m in _NEMEZERA.finditer(mala)]
    return [mala[a:b] for a, b in useky], useky


def _pasaz_citatu(text: str, useky: List[Tuple[int, int]], starty: List[int], n0: int, n1: int) -> str:
    """Úsek normalizovaného textu [n0, n1) -> původní text (<= MAX_PASAZ, bez pokynů pro AI)."""
    def puvodni(off: int) -> int:
        i = max(0, min(bisect.bisect_right(starty, off) - 1, len(starty) - 1))
        a, b = useky[i]
        return min(a + (off - starty[i]), b)
    kus = " ".join(text[puvodni(n0):puvodni(n1)].split())
    kus = _RIDICI.sub("", kus)
    if len(kus) > MAX_PASAZ:
        kus = kus[:MAX_PASAZ - 1] + "…"
    return "[vynecháno: úsek obsahuje pokyn pro AI]" if obsahuje_pokyn(kus) else kus


def najdi_citat(citat: Optional[str], text: Optional[str]) -> dict:
    """Nejlepší shoda citátu v textu: {"stav": doslovne|temer|nenalezen|nelze, "podobnost": 0–1, "pasaz"}.
    1) doslovně po normalizaci (str.find, i po úsecích odděleným výpustkou „…“);
    2) jinak hrubý průchod posuvným oknem o délce citátu ve slovech (počet společných slov, O(n))
       a zpřesnění nejlepších MAX_KANDIDATU_CITAT oken přes difflib (cena nezávisí na délce textu)."""
    nelze = {"stav": "nelze", "podobnost": 0.0, "pasaz": ""}
    useky_citatu = [" ".join(_citat_slova(u)[0]) for u in _VYPUSTKA.split(citat or "")]
    useky_citatu = [u for u in useky_citatu if u]
    if not useky_citatu:
        return nelze | {"poznamka": "prázdný citát"}
    if not text:
        return nelze | {"poznamka": "text zdroje není načtený"}
    slova, useky = _citat_slova(text)
    if not slova:
        return nelze | {"poznamka": "zdroj bez textu"}
    norm = " ".join(slova)
    starty: List[int] = []
    pozice = 0
    for w in slova:
        starty.append(pozice)
        pozice += len(w) + 1
    # 1) Doslovně (úseky v pořadí, mezera mezi nimi <= MAX_MEZERA_VYPUSTKY).
    od, prvni, posledni = 0, None, None
    for u in useky_citatu:
        i = norm.find(u, od)
        if i < 0 or (posledni is not None and i - posledni > MAX_MEZERA_VYPUSTKY):
            break
        prvni = i if prvni is None else prvni
        posledni = od = i + len(u)
    else:
        return {"stav": "doslovne", "podobnost": 1.0, "pasaz": _pasaz_citatu(text, useky, starty, prvni, posledni)}
    # 2) Přibližně.
    nc = " ".join(useky_citatu)
    poznamka = None
    if len(nc) > MAX_CITAT:
        nc = nc[:MAX_CITAT].rsplit(" ", 1)[0]
        poznamka = f"citát zkrácen na {MAX_CITAT} znaků pro přibližné hledání"
    hledana = Counter(w.strip(_INTERPUNKCE) for w in nc.split(" "))
    hledana.pop("", None)
    klice = [w.strip(_INTERPUNKCE) for w in slova]
    n = len(klice)
    okno = max(1, min(len(nc.split(" ")), n))
    prekryv: List[int] = []
    v_okne: Counter = Counter()
    shoda = 0
    for j, w in enumerate(klice):
        if w in hledana:
            v_okne[w] += 1
            if v_okne[w] <= hledana[w]:
                shoda += 1
        if j >= okno:
            u = klice[j - okno]
            if u in hledana:
                if v_okne[u] <= hledana[u]:
                    shoda -= 1
                v_okne[u] -= 1
        if j >= okno - 1:
            prekryv.append(shoda)
    vybrana: List[int] = []
    for i in heapq.nlargest(MAX_KANDIDATU_CITAT * 8, range(len(prekryv)), key=prekryv.__getitem__):
        if prekryv[i] <= 0 or len(vybrana) >= MAX_KANDIDATU_CITAT:
            break
        if all(abs(i - j) >= okno for j in vybrana):
            vybrana.append(i)
    nejlepsi = (0.0, None, None)
    okraj = max(3, okno // 4)
    for i in vybrana:
        a, b = max(0, i - okraj), min(n, i + okno + okraj)
        r0 = starty[a]
        oblast = norm[r0:starty[b - 1] + len(slova[b - 1])]
        bloky = [bl for bl in SequenceMatcher(None, nc, oblast, autojunk=False).get_matching_blocks()
                 if bl.size >= 3]
        if not bloky:
            continue
        s0, s1 = bloky[0].b, bloky[-1].b + bloky[-1].size
        while s0 > 0 and oblast[s0 - 1] != " ":  # na hranice slov
            s0 -= 1
        while s1 < len(oblast) and oblast[s1] != " ":
            s1 += 1
        podobnost = SequenceMatcher(None, nc, oblast[s0:s1], autojunk=False).ratio()
        if podobnost > nejlepsi[0]:
            nejlepsi = (podobnost, r0 + s0, r0 + s1)
    podobnost = round(nejlepsi[0], 3)
    if podobnost >= PRAH_CITAT_DOSLOVNE:
        stav = "doslovne"
    elif podobnost >= PRAH_CITAT_TEMER:
        stav = "temer"
    else:
        stav = "nenalezen"
    vysl = {"stav": stav, "podobnost": podobnost,
            "pasaz": _pasaz_citatu(text, useky, starty, nejlepsi[1], nejlepsi[2]) if nejlepsi[1] is not None else ""}
    if poznamka:
        vysl["poznamka"] = poznamka
    return vysl


# ---------------------------------------------------------------------------
# Pasáže: načtení textu se zálohami a vyhodnocení
# ---------------------------------------------------------------------------
def _identifikatory(kandidati: List[dict], doi: Optional[str], texty: List[Optional[Text]]) -> dict:
    ids: dict = {}
    d = normalizuj_doi(doi) if doi else None
    for z in kandidati:
        if z["typ"] == "doi":
            d = d or z["id"]
        elif z["typ"] == "pmc":
            ids.setdefault("pmcid", z["id"])
        elif z["typ"] == "pubmed":
            ids.setdefault("pmid", z["id"])
        elif z["typ"] == "arxiv":
            ids.setdefault("arxiv", z["id"])
        d = d or _doi_z_url(z.get("url"))
    for t in texty:
        d = d or (t.doi if t else None)
    if not d and ids.get("arxiv"):
        d = normalizuj_doi("10.48550/arXiv." + re.sub(r"v\d+$", "", ids["arxiv"]))
    if d:
        ids["doi"] = d
    return ids


def _zaloha_po_selhani(selhani: List[Tuple[dict, Text]], ids: dict,
                       zalohy: List[str]) -> Tuple[Optional[Text], Optional[dict]]:
    """Žádný zdroj nedal text: 401/403 a nenačtené PDF -> Wayback; 5xx -> abstrakt z Europe PMC.
    Odmítnutí proxy relace se neobchází."""
    epmc_zkousen = any(z["typ"] in ("doi", "pmc", "pubmed") for z, _ in selhani)
    potreba_epmc = False
    for z, t in selhani:
        if t.proxy:
            zalohy.append(f"{z['typ']}: odmítnuto proxy relace, zálohy se nezkoušejí")
            continue
        selhalo_stazeni = t.chyba_site or (t.http is not None and not 200 <= t.http < 300)
        if t.http in (401, 403) or (t.pdf and selhalo_stazeni and _pdf_ctecky()):
            cil = z.get("url") if z["typ"] == "github" else (t.url or z.get("url"))
            if cil:
                tw = _text_wayback(cil, clanek=t.clanek)
                if tw.text:
                    return tw, z
                zalohy.append(f"wayback: {tw.duvod}")
        if t.http is not None and t.http >= 500:
            potreba_epmc = True
    if potreba_epmc and not epmc_zkousen and any(ids.get(k) for k in ("doi", "pmid", "pmcid")):
        te = _text_epmc(ids)
        if te.text:
            return te, selhani[0][0]
        zalohy.append(f"europepmc: {te.duvod}")
    return None, None


def _kroky_tenkeho_textu(z: Optional[dict], t: Text, ids: dict, vyzkousene: set) -> List[Tuple[str, object]]:
    """Zálohy pro tenký text článku v pořadí: arXiv PDF, Europe PMC (plný text / abstrakt), OpenAlex
    (OA kopie / abstrakt), Wayback (nejnovější snímek)."""
    typ = (z or {}).get("typ", "")
    kroky: List[Tuple[str, object]] = []
    if typ == "arxiv":
        if _pdf_ctecky():
            kroky.append(("arxiv-pdf", lambda: _text_arxiv_pdf(z["id"])))
        return kroky  # snímek abs stránky ani OpenAlex u arXivu nic nového nepřinesou
    if any(ids.get(k) for k in ("doi", "pmid", "pmcid")) and not t.zdroj.startswith("europepmc"):
        kroky.append(("europepmc", lambda: _text_epmc(ids)))
    if ids.get("doi") and not t.zdroj.startswith("openalex"):
        kroky.append(("openalex", lambda: _text_openalex(ids["doi"], vyzkousene)))
    # Cíl snímku: zadaná URL, jinak stránka, ze které text je; abstrakt z Europe PMC URL nemá -> doi.org/DOI
    # (Wayback přesměrování z doi.org na snímek vydavatele sleduje).
    cil = (z or {}).get("url") or t.url or (f"https://doi.org/{ids['doi']}" if ids.get("doi") else None)
    if cil and typ not in ("github", "pubmed") and not t.zdroj.startswith("wayback") \
            and "web.archive.org" not in cil:
        kroky.append(("wayback", lambda: _text_wayback(cil, clanek=True)))
    return kroky


# Fráze zástěny v textu bez diakritiky a malými písmeny: (druh, vzor). Vzory se navzájem nepřekrývají, aby
# jedna fráze („Accept all cookies“) nepočítala víc než svá slova.
_FRAZE_ZASTENY = tuple((druh, re.compile(vzor)) for druh, vzor in (
    ("souhlas s cookies", r"\bcookies?\b"),
    ("souhlas s cookies", r"\bsouhlas\w*"),
    ("souhlas s cookies", r"\bconsent\w*"),
    ("souhlas s cookies", r"\baccept all\b"),
    ("souhlas s cookies", r"\b(?:reject|decline) all\b"),
    ("souhlas s cookies", r"\bprijmout (?:vse|vsechn\w*)\b"),
    ("souhlas s cookies", r"\bodmitnout (?:vse|vsechn\w*)\b"),
    ("souhlas s cookies", r"\b(?:manage|privacy) (?:preferences|settings|choices)\b|\bnastaveni soukromi\b"),
    ("přihlášení", r"\bsign (?:in|up)\b|\blog ?in\b"),
    ("přihlášení", r"\bprihlas\w*"),
    ("přihlášení", r"\bcreate (?:an |a free )?account\b|\bzalozte si ucet\b"),
    ("JavaScript", r"\b(?:enable|turn on|activate|allow|zapnete|zapnout|povolte|povolit) (?:the )?javascript\b"
                   r"|\bjavascript (?:is )?(?:disabled|required|vypnut\w*)\b"),
    ("kontrola robota", r"\bcaptcha\b|\bare you a robot\b|\bnejste robot\b"
                        r"|\b(?:verify|confirm) (?:that )?you are (?:a )?human\b"),
    ("kontrola robota", r"\bchecking (?:your browser|if the site connection is secure)\b|\bjust a moment\b"),
    ("předplatné", r"\bsubscribe to (?:continue|read)\w*|\bsubscribers? only\b|\bpredplat\w*"),
    ("přístup odepřen", r"\baccess (?:denied|forbidden)\b|\bpristup (?:odepren|zamitnut)\b"),
))


def rozpoznej_zastenu(text: Optional[str]) -> Optional[str]:
    """Druh zástěny (souhlas s cookies, přihlášení, JavaScript, kontrola robota, předplatné, přístup odepřen)
    u krátkého textu s typickými frázemi, jinak None. Dlouhý text s cookie lištou zástěna není."""
    if not text or len(text) >= MIN_CLANEK_TEXT:
        return None
    t = " ".join(_normalizuj(text).split())
    druhy = [druh for druh, vzor in _FRAZE_ZASTENY if vzor.search(t)]
    if len(druhy) >= MIN_FRAZI_ZASTENY or (druhy and len(text) < MAX_TEXT_JEDNA_FRAZE):
        return Counter(druhy).most_common(1)[0][0]
    return None


def _vyhodnot(dotaz: str, t: Text, k: int, citat: Optional[str], clanek: bool) -> dict:
    """Pasáže a citát v textu. Krátký text (< MIN_CLANEK_TEXT, jakákoli stránka) bez nalezené pasáže =
    castecne_nacteno; zástěna bez nalezené pasáže a citátu = nenacteno. Zálohy (_zalohy) jen u článku a zástěny."""
    v = pasaze_z_textu(dotaz, t.text, k)
    kratky = len(t.text) < MIN_CLANEK_TEXT
    if citat:
        v["citat"] = najdi_citat(citat, t.text)
    nalez = v["stav"] == "nalezeno" or _slovnik(v.get("citat")).get("stav") in ("doslovne", "temer")
    zastena = None if nalez else rozpoznej_zastenu(t.text)
    if zastena:
        v.update(stav="nenacteno", skore_max=0.0, pasaze=[], cisla_chybi_ve_zdroji=[], zastena=zastena,
                 duvod=f"zástěna ({zastena}): místo obsahu jen {len(t.text)} znaků zástěny; text zdroje nenačten")
        if citat:
            v["citat"] = najdi_citat(citat, None)
    elif kratky and v["stav"] != "nalezeno":
        v["stav"] = "castecne_nacteno"
        v["duvod"] = f"krátký, možná jen částečný text ({len(t.text)} znaků < {MIN_CLANEK_TEXT}); " + v["duvod"]
    v["_kratky"] = kratky
    v["_zalohy"] = bool(zastena) or ((clanek or t.clanek) and kratky)
    return v


def _klic_vysledku(v: dict) -> tuple:
    return (v["stav"] == "nalezeno", _RAD_CITATU.get(_slovnik(v.get("citat")).get("stav"), 0),
            not v["_kratky"], v["skore_max"])


def _staci(v: dict, citat: Optional[str]) -> bool:
    """Další zálohy netřeba: nejde o článek ani zástěnu, text je úplný, nebo pasáž nalezena (a citát doslovně)."""
    if not v["_zalohy"]:
        return True
    return v["stav"] == "nalezeno" and (not citat or v["citat"]["stav"] == "doslovne")


def najdi_pasaze(tvrzeni: str, url: Optional[str] = None, doi: Optional[str] = None, k: int = 3,
                 tvrzeni_en: Optional[str] = None, citat: Optional[str] = None) -> dict:
    """Pasáže zdroje k tvrzení. Skóruje se podle tvrzeni_en, je-li zadané (zdroje bývají anglicky);
    citat = doslovný úryvek ze zdroje -> pole "citat"."""
    k = max(1, min(int(k or 3), 20))
    en = (tvrzeni_en or "").strip()
    dotaz = en or (tvrzeni or "").strip()
    citat = (citat or "").strip() or None
    zaklad = {"stav": "nenacteno", "duvod": "", "skore_max": 0.0, "pasaze": [], "zdroj_textu": "",
              "delka_textu": 0, "vynechano_pokynu": 0, "cisla_v_tvrzeni": _cisla_vystup(cisla_tvrzeni(dotaz)),
              "skorovano_podle": "tvrzeni_en" if en else "tvrzeni"}
    if citat:
        zaklad["citat"] = najdi_citat(citat, None)
    if not dotaz:
        return zaklad | {"duvod": "prázdné tvrzení"}
    kandidati = []
    if url:
        kandidati.append(rozpoznej_zdroj(url=url))
    if doi:
        z = rozpoznej_zdroj(doi=doi)
        if z["typ"] != "neplatna" and all((z["typ"], z["id"]) != (c["typ"], c["id"]) for c in kandidati):
            kandidati.append(z)
    if not kandidati:
        return zaklad | {"duvod": "chybí URL i DOI"}
    duvody: List[str] = []
    selhani: List[Tuple[dict, Text]] = []
    t: Optional[Text] = None
    z_textu: Optional[dict] = None
    for z in kandidati:
        t = ziskej_text(z)
        if t.text:
            z_textu = z
            break
        duvody.append(f"{z['typ']}: {t.duvod}")
        selhani.append((z, t))
    ids = _identifikatory(kandidati, doi, [t] + [s for _, s in selhani])
    zalohy: List[str] = []
    if not (t and t.text):
        t, z_textu = _zaloha_po_selhani(selhani, ids, zalohy)
        if not (t and t.text):
            return zaklad | {"duvod": "; ".join(duvody + zalohy)}
    clanek = bool(normalizuj_doi(doi)) if doi else False
    vyzkousene = {_klic_zdroje(z) for z in kandidati} | ({_klic_zdroje({"url": t.url})} if t.url else set())
    nejlepsi, nejlepsi_t = _vyhodnot(dotaz, t, k, citat, clanek), t
    if not _staci(nejlepsi, citat):
        for popis, ziskej in _kroky_tenkeho_textu(z_textu, t, ids, vyzkousene):
            tz = ziskej()
            if not tz.text:
                zalohy.append(f"{popis}: {tz.duvod}")
                continue
            zalohy.append(f"{popis}: {tz.zdroj} ({len(tz.text)} znaků" + (f"; {tz.duvod}" if tz.duvod else "") + ")")
            v = _vyhodnot(dotaz, tz, k, citat, clanek)
            if _klic_vysledku(v) > _klic_vysledku(nejlepsi):
                nejlepsi, nejlepsi_t = v, tz
            if _staci(nejlepsi, citat):
                break
    t, vysl = nejlepsi_t, nejlepsi
    vysl.pop("_kratky", None)
    vysl.pop("_zalohy", None)
    poznamky = [p for p in (t.duvod, "text oříznut na 3 MB" if t.oriznuto else "") if p]
    if duvody:
        poznamky.insert(0, "záloha po: " + "; ".join(duvody))
    if zalohy:
        poznamky.append("zálohy: " + "; ".join(zalohy))
    if poznamky:
        vysl["duvod"] += " | " + "; ".join(poznamky)
    # Cílová URL po přesměrování je řízená serverem (Location může mít desítky kB): jen zkráceně.
    return zaklad | vysl | {"zdroj_textu": t.zdroj, "delka_textu": len(t.text),
                            "url_textu": _zkrat(t.url, 300) if t.url and povolena_url(t.url) else None}


# ---------------------------------------------------------------------------
# Štítky: deterministické pravidlo z G1, G2, nezávislých zdrojů a úrovně důkazu
# ---------------------------------------------------------------------------
# PRAVIDLO_STITKU je PŘEDPOKLAD KE KALIBRACI, ne validovaná metoda (pro dlouhé zprávy žádná není).
# Revize po ~100 verdiktech (A/B test F5, G2, namátkové kontroly autora); popis: references/evidence.md, oddíl 4.
PRAVIDLO_STITKU = {
    "verze": "stitky-1",
    "fakt_min_zdroju": 2,                       # nezávislé potvrzené zdroje pro „fakt“
    "fakt_urovne": ("vysoka", "stredni"),       # úroveň důkazu nutná pro „fakt“
    "podlozene_urovne": ("vysoka", "stredni"),  # 1 potvrzený zdroj stačí na „podložené“ jen při této úrovni
    "podlozene_min_zdroju_nizka": 2,            # při nízké úrovni „podložené“ až od tolika nezávislých zdrojů
    "uroven_chybi": "nizka",                    # chybějící úroveň důkazu se počítá jako tato (s výhradou)
    "strop_vyhrady": "podložené",               # výhrada (vyjádření obav, chybějící čísla, citát) = nejvýš
}
STITKY = ("fakt", "podložené", "odhad", "sporné", "neznámé")
AKCE = ("ponechat", "vyradit", "preformulovat")
VERDIKTY_G2 = ("potvrzeno", "castecne", "vyvraceno", "neoveritelne")
UROVNE_DUKAZU = ("vysoka", "stredni", "nizka", "velmi_nizka")
MAX_VSTUP_BAJTU = 20 * 1024 * 1024
# Síla štítku: skript štítek sběrače jen zeslabí, nikdy nezesílí (M0-lite, SKILL.md krok 4).
SILA_STITKU = {"fakt": 4, "podložené": 3, "sporné": 2, "odhad": 2, "neznámé": 1}
_STITKY_SBERACE = {"fakt": "fakt", "fact": "fakt", "podlozene": "podložené", "supported": "podložené",
                   "sporne": "sporné", "disputed": "sporné", "contested": "sporné", "odhad": "odhad",
                   "estimate": "odhad", "nezname": "neznámé", "unknown": "neznámé"}
# G2 se spustí, když G1 najde vadu u víc než tohoto podílu citací (SKILL.md, krok 5c).
PODIL_VAD_PRO_G2 = 0.20


def _klic_textu(x) -> str:
    """Bez diakritiky, malá písmena, mezery a pomlčky jako podtržítko: „Velmi nízká“ -> velmi_nizka."""
    return re.sub(r"[\s\-]+", "_", _normalizuj(str(x or "")).strip())


def norm_verdikt(x) -> Optional[str]:
    if isinstance(x, dict):
        x = x.get("verdikt")
    k = _klic_textu(x)
    return k if k in VERDIKTY_G2 else None


def norm_uroven(x) -> Optional[str]:
    k = _klic_textu(x)
    return k if k in UROVNE_DUKAZU else None


def norm_stitek(x) -> Optional[str]:
    """Štítek sběrače („Podlozene“, „FAKT“, „disputed“) -> jeden z STITKY; neplatný či chybějící = None."""
    if not isinstance(x, str):
        return None
    return _STITKY_SBERACE.get(_klic_textu(x))


def tvrde_vady_g1(g1: dict) -> List[str]:
    """Tvrdé vady zdroje z G1: zdroj se pro tvrzení nepočítá. Mrtvý odkaz neplatí, když DOI sedí."""
    g1 = _slovnik(g1)
    vady: List[str] = []
    doi = _slovnik(g1.get("doi"))
    if _slovnik(g1.get("url")).get("stav") == "mrtvy" and doi.get("stav") != "ok":
        vady.append("mrtvý odkaz")
    if doi.get("stav") == "neexistuje":
        vady.append("DOI neexistuje")
    elif doi.get("stav") == "nesedi":
        vady.append("DOI nesedí s metadaty")
    if _slovnik(g1.get("retrakce")).get("stav") == "retrahovano":
        vady.append("retrakce")
    return vady


def _uplny_text(p: dict) -> bool:
    """Text zdroje je plně načten: pasáž nalezena, nebo nenalezena v dlouhém textu (>= MIN_CLANEK_TEXT);
    zástěna ani částečný text ne. Délka se kontroluje i u starších výstupů davka (krátký text s „nenalezeno“)."""
    p = _slovnik(p)
    delka = p.get("delka_textu")
    delka = delka if isinstance(delka, int) and not isinstance(delka, bool) else 0
    if p.get("zastena"):
        return False
    if p.get("stav") == "nalezeno":
        return delka > 0
    return p.get("stav") == "nenalezeno" and delka >= MIN_CLANEK_TEXT


def _cisla_nesedi(g1: dict) -> List[str]:
    """Čísla tvrzení, která v plně načteném textu zdroje nejsou (prázdné = sedí nebo nelze posoudit)."""
    p = _slovnik(_slovnik(g1).get("pasaze"))
    if not _uplny_text(p):
        return []
    return [str(c) for c in _seznam(p.get("cisla_chybi_ve_zdroji"))]


def _klic_tvrzeni(r: dict, klice: Optional[Dict[str, str]] = None) -> Optional[str]:
    """Tvrzení, ke kterému řádek G1 patří: zadaná mapa > pole tvrzeni_id > předpona id „t3-1“ → „t3“."""
    rid = str(r.get("id") or "")
    if klice and klice.get(rid):
        return str(klice[rid])
    if r.get("tvrzeni_id") not in (None, ""):
        return str(r.get("tvrzeni_id"))
    m = re.fullmatch(r"(.+)-\d+", rid)
    return m.group(1) if m else None


def cisla_po_tvrzenich(radky, klice: Optional[Dict[str, str]] = None) -> List[dict]:
    """Čísla tvrzení s více zdroji se hledají ve všech jeho plně načtených zdrojích dohromady: číslo, které má
    jiný plně načtený zdroj téhož tvrzení, není vada (A/B4 2026-11-05, Q04: polovina „čísla chybí“ byla v jiném
    citovaném zdroji). Vrací nový seznam; změněné řádky jsou kopie s pasaze.cisla_v_jinem_zdroji."""
    radky = [r for r in (radky or []) if isinstance(r, dict)]
    nalezena: Dict[str, set] = {}
    for r in radky:
        k = _klic_tvrzeni(r, klice)
        p = _slovnik(r.get("pasaze"))
        if k is None or not _uplny_text(p):
            continue
        chybi = {str(c) for c in _seznam(p.get("cisla_chybi_ve_zdroji"))}
        nalezena.setdefault(k, set()).update(str(c) for c in _seznam(p.get("cisla_v_tvrzeni")) if str(c) not in chybi)
    vysl: List[dict] = []
    for r in radky:
        k = _klic_tvrzeni(r, klice)
        p = _slovnik(r.get("pasaze"))
        chybi = [str(c) for c in _seznam(p.get("cisla_chybi_ve_zdroji"))]
        jinde = [c for c in chybi if c in nalezena.get(k, set())] if k is not None else []
        if jinde:
            r = dict(r, pasaze=dict(p, cisla_chybi_ve_zdroji=[c for c in chybi if c not in jinde],
                                    cisla_v_jinem_zdroji=jinde))
        vysl.append(r)
    return vysl


def vyhrady_g1(g1: dict) -> List[str]:
    """Výhrady zdroje z G1: zdroj se počítá, ale štítek nejvýš PRAVIDLO_STITKU["strop_vyhrady"]."""
    g1 = _slovnik(g1)
    vyhrady: List[str] = []
    if _slovnik(g1.get("retrakce")).get("stav") == "vyjadreni_obav":
        vyhrady.append("vyjádření obav k článku")
    p = _slovnik(g1.get("pasaze"))
    cisla_nesedi = _cisla_nesedi(g1)
    if cisla_nesedi:
        vyhrady.append(f"čísla tvrzení ve zdroji nejsou ({', '.join(cisla_nesedi[:5])})")
    if _uplny_text(p) and _slovnik(p.get("citat")).get("stav") == "nenalezen":
        vyhrady.append("citát ve zdroji nenalezen (možná parafráze)")
    return vyhrady


def ma_vadu_g1(g1: dict) -> bool:
    """Vada G1 pro podmínku spuštění G2: tvrdá vada nebo nesedící čísla v plně načteném textu. Citát je jen
    nápověda; nenačtený či částečný text a zástěna vada nejsou (počítají se zvlášť jako „nenačteno“)."""
    return bool(tvrde_vady_g1(g1) or _cisla_nesedi(g1))


def nenacteno_g1(g1: dict) -> bool:
    """Citace bez vady, jejíž text zdroje není plně načten (nenačteno, zástěna, částečný text): čísla ani citát
    nejde posoudit. Disjunktní s ma_vadu_g1."""
    return not ma_vadu_g1(g1) and not _uplny_text(_slovnik(_slovnik(g1).get("pasaze")))


def souhrn_g1(radky) -> dict:
    """Souhrn G1 nad řádky výstupu davka: vady (tvrdé vady + nesedící čísla v plně načteném textu) a zvlášť
    nenačtené citace (z toho zástěna a částečný text), oba podíly. g2_doporucen jen podle vad (> PODIL_VAD_PRO_G2)."""
    radky = [r for r in (radky or []) if isinstance(r, dict)]
    n = len(radky)
    s_vadou = sum(1 for r in radky if ma_vadu_g1(r))
    tvrde = sum(1 for r in radky if tvrde_vady_g1(r))
    nenac = [_slovnik(r.get("pasaze")) for r in radky if nenacteno_g1(r)]
    return {"citaci": n, "s_vadou": s_vadou, "tvrde_vady": tvrde, "cisla_nesedi": s_vadou - tvrde,
            "podil_vad": round(s_vadou / n, 3) if n else 0.0,
            "nenacteno": len(nenac), "zastena": sum(1 for p in nenac if p.get("zastena")),
            "castecne_nacteno": sum(1 for p in nenac if not p.get("zastena") and p.get("stav") != "nenacteno"),
            "podil_nenacteno": round(len(nenac) / n, 3) if n else 0.0,
            "g2_doporucen": bool(n) and s_vadou / n > PODIL_VAD_PRO_G2}


# Katalogy, repozitáře a platformy vydavatelů: na jednom hostu jsou díla různých autorů, takže nezávislost
# určuje dílo (cesta URL), ne host. Jinde platí konzervativně „stejný host = stejný vydavatel“.
_HOSTY_DEL = ("doi.org", "ncbi.nlm.nih.gov", "europepmc.org", "ebi.ac.uk", "arxiv.org", "biorxiv.org", "medrxiv.org",
              "osf.io", "psyarxiv.com", "ssrn.com", "semanticscholar.org", "openalex.org", "researchgate.net",
              "scholar.google.com", "jstor.org", "sciencedirect.com", "springer.com", "wiley.com", "tandfonline.com",
              "sagepub.com", "oup.com", "nature.com", "science.org", "cell.com", "frontiersin.org", "mdpi.com",
              "plos.org", "bmj.com", "thelancet.com", "jamanetwork.com", "nejm.org", "apa.org", "cochranelibrary.com",
              "elifesciences.org", "pnas.org", "acm.org", "ieee.org", "aclanthology.org", "openreview.net",
              "neurips.cc", "huggingface.co", "github.com")


def _host_del(host: str) -> bool:
    return any(host == h or host.endswith("." + h) for h in _HOSTY_DEL)


def _skupina_zdroje(z: dict, zid: str) -> str:
    """Klíč nezávislosti: zadaná skupina > DOI (i z URL) > dílo na hostu katalogu či vydavatele > host URL > id.
    Stejný host mimo katalogy = stejný vydavatel (konzervativně)."""
    if z.get("skupina"):
        return "s:" + _klic_textu(z["skupina"])
    url = str(z.get("url") or "")
    doi = normalizuj_doi(str(z.get("doi") or "")) or (_doi_z_url(url) if povolena_url(url) else None)
    if doi:
        return "doi:" + doi.lower()
    if povolena_url(url):
        c = urllib.parse.urlsplit(url)
        host = (c.hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if host and _host_del(host):
            cesta = re.sub(r"/+$", "", urllib.parse.unquote(c.path)).lower()
            return "dilo:" + host + cesta + ("?" + c.query if c.query else "")
        if host:
            return "host:" + host
    return "id:" + zid


def _ma_g1(z, zid: str, g1_mapa: Dict[str, dict]) -> bool:
    return (isinstance(z, dict) and isinstance(z.get("g1"), dict)) or zid in g1_mapa


def _zdroje_bez_g1(tvrzeni: list, g1_mapa: Dict[str, dict]) -> List[str]:
    """Id zdrojů, ke kterým není řádek G1 (ani ve vstupu, ani ve výstupu davka): doplnit do dávky."""
    chybi: List[str] = []
    for t in tvrzeni:
        zdroje = t.get("zdroje") or []
        for i, z in enumerate([zdroje] if isinstance(zdroje, (dict, str)) else zdroje):
            zid = str((z.get("id") if isinstance(z, dict) else z) or f"{t.get('id') or ''}-{i + 1}")
            if not _ma_g1(z, zid, g1_mapa) and zid not in chybi:
                chybi.append(zid)
    return chybi


def _stitek_sberace(vysl: dict, zdroje: list, sberac: Optional[str], g1_mapa: Dict[str, dict]) -> dict:
    """Režim bez G2 (výchozí M0-lite): štítek dává sběrač; skript ho jen zeslabí vadou G1, nikdy nezesílí.
    Tvrdá vada vyřadí zdroj; bez použitelného zdroje = neověřeno (vyřadit); „fakt“ potřebuje ≥ 2 nezávislé
    použitelné zdroje; výhrada G1 (i zdroj bez řádku G1) = nejvýš PRAVIDLO_STITKU["strop_vyhrady"]."""
    tid = vysl["id"]
    skupiny: set = set()
    for i, z in enumerate(zdroje):
        if not isinstance(z, dict):
            z = {"id": z}
        zid = str(z.get("id") or f"{tid}-{i + 1}")
        vysl["zdroje"].append(zid)
        if not _ma_g1(z, zid, g1_mapa):  # G1 má proběhnout nad všemi citacemi; chybějící řádek není „bez vad“
            vysl["vyhrady"].append(f"{zid}: G1 neproběhl (zdroj chybí ve výstupu davka)")
        g1 = z["g1"] if isinstance(z.get("g1"), dict) else _slovnik(g1_mapa.get(zid))
        vady = tvrde_vady_g1(g1)
        if vady:
            vysl["vyrazene_zdroje"].append({"id": zid, "duvod": ", ".join(vady)})
            continue
        vysl["vyhrady"] += [f"{zid}: {v}" for v in vyhrady_g1(g1)]
        skupiny.add(_skupina_zdroje(z, zid))
    vysl["neovereno"] = len(zdroje) - len(vysl["vyrazene_zdroje"])  # G2 neproběhl
    stitek, akce, duvod = sberac or "neznámé", "ponechat", "štítek sběrače"
    if sberac is None:
        vysl["vyhrady"].append("štítek sběrače chybí nebo je neplatný (počítáno jako neznámé)")
        duvod = "štítek sběrače chybí"
    if not zdroje:
        if stitek != "odhad":
            stitek, duvod = "neznámé", "tvrzení nemá zdroj"
    elif not skupiny:
        stitek, akce, duvod = "neznámé", "vyradit", "všechny zdroje mají tvrdou vadu G1 (neověřeno)"
    else:
        if vysl["vyrazene_zdroje"]:
            duvod += f"; G1 vyřadil {len(vysl['vyrazene_zdroje'])} zdroj(e)"
        if stitek == "fakt" and len(skupiny) < PRAVIDLO_STITKU["fakt_min_zdroju"]:
            stitek = "podložené"
            duvod += "; po G1 méně než 2 nezávislé zdroje"
        if stitek == "fakt" and vysl["vyhrady"]:
            stitek = PRAVIDLO_STITKU["strop_vyhrady"]
            duvod += "; výhrada G1 snižuje štítek"
    return vysl | {"stitek": stitek, "akce": akce, "duvod": duvod}


def urci_stitek(t: dict, g1_mapa: Optional[Dict[str, dict]] = None) -> dict:
    """Štítek a akce jednoho tvrzení. t = {id, stitek_sberace?, uroven_dukazu?, nezavislych_zdroju?, odhad?,
    zdroje: [{id, g2?, skupina?, doi?, url?, g1?}]}; g1_mapa = id zdroje -> řádek výstupu davka.
    Režimy: „sberac“ (je stitek_sberace a G2 neproběhl: štítek sběrače zeslabený G1), „g2“ (pravidlo
    z verdiktů G2) a „g2+sberac“ (pravidlo G2, ale nikdy silnější než štítek sběrače)."""
    g1_mapa = g1_mapa or {}
    pravidlo = PRAVIDLO_STITKU
    tid = str(t.get("id") or "")
    zdroje = t.get("zdroje") or []
    if isinstance(zdroje, (dict, str)):
        zdroje = [zdroje]
    ma_sberace = "stitek_sberace" in t
    sberac = norm_stitek(t.get("stitek_sberace"))
    g2_probehl = any(isinstance(z, dict) and norm_verdikt(z.get("g2")) for z in zdroje)
    vysl = {"id": tid, "stitek": None, "akce": "ponechat", "duvod": "", "pro": 0, "castecne": 0, "proti": 0,
            "neovereno": 0, "uroven_dukazu": None, "zdroje": [], "vyrazene_zdroje": [], "vyhrady": [],
            "pravidlo": pravidlo["verze"], "rezim": "g2", "stitek_sberace": sberac}
    if ma_sberace and not g2_probehl:
        return _stitek_sberace(vysl | {"rezim": "sberac"}, zdroje, sberac, g1_mapa)
    vysl = urci_stitek_g2(vysl, t, zdroje, g1_mapa)
    if sberac:  # neplatný štítek sběrače strop nedává: tvrzení prošlo G2
        vysl["rezim"] = "g2+sberac"
        if vysl["stitek"] and SILA_STITKU[vysl["stitek"]] > SILA_STITKU[sberac]:
            vysl["stitek"] = sberac
            vysl["duvod"] += f"; nejvýš štítek sběrače ({sberac})"
    return vysl


def urci_stitek_g2(vysl: dict, t: dict, zdroje: list, g1_mapa: Dict[str, dict]) -> dict:
    """Pravidlo z verdiktů G2, počtu nezávislých zdrojů a úrovně důkazu (references/evidence.md, oddíl 4)."""
    pravidlo = PRAVIDLO_STITKU
    tid = vysl["id"]
    if t.get("odhad") is True:
        return vysl | {"stitek": "odhad", "duvod": "vlastní výpočet či úvaha z uvedených dat (uveď postup)"}
    uroven = norm_uroven(t.get("uroven_dukazu"))
    if uroven is None:
        uroven = pravidlo["uroven_chybi"]
        vysl["vyhrady"].append(f"úroveň důkazu chybí (počítáno jako {uroven})")
    vysl["uroven_dukazu"] = uroven
    pro_skupiny: set = set()
    for i, z in enumerate(zdroje):
        if not isinstance(z, dict):
            z = {"id": z}
        zid = str(z.get("id") or f"{tid}-{i + 1}")
        vysl["zdroje"].append(zid)
        g1 = z["g1"] if isinstance(z.get("g1"), dict) else _slovnik(g1_mapa.get(zid))
        vady = tvrde_vady_g1(g1)
        if vady:
            vysl["vyrazene_zdroje"].append({"id": zid, "duvod": ", ".join(vady)})
            continue
        vysl["vyhrady"] += [f"{zid}: {v}" for v in vyhrady_g1(g1)]
        verdikt = norm_verdikt(z.get("g2"))
        if verdikt == "potvrzeno":
            pro_skupiny.add(_skupina_zdroje(z, zid))
        elif verdikt == "castecne":
            vysl["castecne"] += 1
        elif verdikt == "vyvraceno":
            vysl["proti"] += 1
        else:
            vysl["neovereno"] += 1
    n_pro = len(pro_skupiny)
    strop = t.get("nezavislych_zdroju")
    if isinstance(strop, int) and not isinstance(strop, bool) and strop >= 0:
        n_pro = min(n_pro, strop)  # hlavní agent ví, že zdroje opisují tentýž primární zdroj
    vysl["pro"] = n_pro
    pouzitelne = len(zdroje) - len(vysl["vyrazene_zdroje"])

    if not zdroje:
        stitek, akce, duvod = "neznámé", "ponechat", "tvrzení nemá zdroj"
    elif pouzitelne == 0:
        stitek, akce, duvod = "neznámé", "vyradit", "všechny zdroje mají tvrdou vadu G1"
    elif vysl["proti"] and not (n_pro or vysl["castecne"]):
        stitek, akce, duvod = None, "vyradit", "G2 tvrzení vyvrátil a žádný zdroj ho nepotvrzuje"
    elif vysl["proti"]:
        stitek, akce, duvod = "sporné", "ponechat", "G2: některé zdroje tvrzení potvrzují, jiné vyvracejí"
    elif n_pro >= pravidlo["fakt_min_zdroju"] and uroven in pravidlo["fakt_urovne"]:
        stitek, akce, duvod = "fakt", "ponechat", f"{n_pro} nezávislé potvrzené zdroje, úroveň {uroven}"
    elif n_pro >= 1 and uroven in pravidlo["podlozene_urovne"]:
        stitek, akce, duvod = "podložené", "ponechat", f"{n_pro} potvrzený zdroj, úroveň {uroven}"
    elif n_pro >= pravidlo["podlozene_min_zdroju_nizka"] and uroven == "nizka":
        stitek, akce, duvod = "podložené", "ponechat", f"{n_pro} nezávislé potvrzené zdroje nízké úrovně"
    elif n_pro >= 1:
        stitek, akce, duvod = "neznámé", "ponechat", f"důkazy nestačí ({n_pro} potvrzený zdroj, úroveň {uroven})"
    elif vysl["castecne"]:
        stitek, akce, duvod = "neznámé", "preformulovat", "G2 potvrdil jen část: zúžit tvrzení a ověřit znovu"
    else:
        stitek, akce, duvod = "neznámé", "ponechat", "G2 tvrzení neověřil"
    if stitek == "fakt" and vysl["vyhrady"]:
        stitek = pravidlo["strop_vyhrady"]
        duvod += "; výhrada snižuje štítek"
    return vysl | {"stitek": stitek, "akce": akce, "duvod": duvod}


def _nacti_text(cesta: str, max_bajtu: int = MAX_VSTUP_BAJTU) -> str:
    with open(cesta, "rb") as f:
        data = f.read(max_bajtu + 1)
    if len(data) > max_bajtu:
        raise ValueError(f"soubor je větší než {max_bajtu} B")
    return data.decode("utf-8-sig", errors="replace")


def nacti_json_nebo_jsonl(cesta: str):
    """JSON (objekt či seznam), nebo JSONL (seznam objektů; prázdné a vadné řádky se přeskočí)."""
    text = _nacti_text(cesta)
    try:
        return json.loads(text)
    except ValueError:
        pass
    radky = []
    for r in text.splitlines():
        if not r.strip():
            continue
        try:
            obj = json.loads(r)
        except ValueError:
            continue
        if isinstance(obj, dict):
            radky.append(obj)
    return radky


def _podle_id(radky) -> Dict[str, dict]:
    if isinstance(radky, dict):
        for klic in ("radky", "verdikty", "tvrzeni", "zaznamy"):
            if isinstance(radky.get(klic), list):
                radky = radky[klic]
                break
        else:
            radky = [radky]
    return {str(r.get("id")): r for r in _seznam(radky) if isinstance(r, dict) and r.get("id") is not None}


def stitky(vstup: str, g1: Optional[str] = None) -> dict:
    """Příkaz stitky. VSTUP = seznam tvrzení, nebo {"tvrzeni": [...], "g1": "davka.jsonl"}."""
    data = nacti_json_nebo_jsonl(vstup)
    tvrzeni = data.get("tvrzeni") if isinstance(data, dict) else data
    if not isinstance(tvrzeni, list):
        return {"stav": "chyba", "duvod": "vstup musí být seznam tvrzení nebo objekt s polem „tvrzeni“"}
    cesta_g1 = g1 or (data.get("g1") if isinstance(data, dict) and isinstance(data.get("g1"), str) else None)
    g1_mapa: Dict[str, dict] = {}
    if cesta_g1:
        if not os.path.isabs(cesta_g1) and not g1:
            cesta_g1 = os.path.join(os.path.dirname(os.path.abspath(vstup)), cesta_g1)
        g1_data = nacti_json_nebo_jsonl(cesta_g1)
        klice = {str(z.get("id")): str(t.get("id")) for t in tvrzeni if isinstance(t, dict)
                 for z in _seznam(t.get("zdroje")) if isinstance(z, dict) and z.get("id") and t.get("id")}
        g1_mapa = _podle_id(cisla_po_tvrzenich(list(_podle_id(g1_data).values()), klice))
    vysledky = [urci_stitek(t, g1_mapa) for t in tvrzeni if isinstance(t, dict)]
    souhrn = Counter(v["stitek"] or "–" for v in vysledky if v["akce"] != "vyradit")
    souhrn_dict = {k: souhrn.get(k, 0) for k in STITKY}
    souhrn_dict["vyradit"] = sum(1 for v in vysledky if v["akce"] == "vyradit")
    souhrn_dict["preformulovat"] = sum(1 for v in vysledky if v["akce"] == "preformulovat")
    return {"stav": "ok", "pravidlo": dict(PRAVIDLO_STITKU, poznamka="předpoklad ke kalibraci"),
            "souhrn": souhrn_dict, "g1": souhrn_g1(g1_mapa.values()) if g1_mapa else None,
            "zdroje_bez_g1": _zdroje_bez_g1([t for t in tvrzeni if isinstance(t, dict)], g1_mapa),
            "tvrzeni": vysledky}


# ---------------------------------------------------------------------------
# Vytažení tvrzení s citacemi z Markdown zprávy (příjem cizího výstupu)
# ---------------------------------------------------------------------------
MAX_ZPRAVA_BAJTU = 5 * 1024 * 1024
MAX_TVRZENI_ZPRAVY = 1000
MAX_DELKA_TVRZENI = 600
MIN_SLOV_TVRZENI = 3
MAX_ROZSAH_ZNACEK = 20       # „[1–40]“ se nerozvine do 40 zdrojů, jen do prvních 20

_V_ZNAK, _V_KONEC = "", ""   # zástupná značka citace v textu (soukromé znaky Unicode)
_ZASTUPCE = re.compile(_V_ZNAK + r"(\d+)" + _V_KONEC)
_NADPIS = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_NADPIS_ZDROJU = re.compile(r"^(?:zdroje|zdroj|sources?|references?|reference|literatura|bibliograf\w*|citace|"
                            r"citations?|works\s+cited|odkazy|footnotes|cited\s+works)\b", re.I)
# oddíly, které nejsou tělem zprávy ani seznamem zdrojů (vlastní příloha s tabulkou verdiktů)
_NADPIS_PRILOHY = re.compile(r"^(?:příloha|priloha|appendix|tabulka\s+verdikt\w*|verdikty\s+bran)\b", re.I)
_DEF_ODKAZU = re.compile(r"^\s{0,3}\[(\^?[^\]\n]{1,100})\]:\s*(.*)$")
_POLOZKA_ZDROJU = re.compile(r"^\s*(?:[-*+]\s+)?(?:\[(\d{1,4})\]|(\d{1,4})[.)])\s+(.*)$")
_URL_V_TEXTU = re.compile(r"https?://[^\s<>\"'\]\)]+(?:\([^\s<>\"'()]*\)[^\s<>\"'\]\)]*)*", re.I)
_DOI_V_ZPRAVE = re.compile(r"\b(?:doi:\s*)?(10\.\d{4,9}/[^\s\"'<>\]\)]+)", re.I)
_MD_INLINE = re.compile(r"(!?)\[([^\]\n]{0,500})\]\(\s*(<[^<>\n]{1,2000}>|(?:[^\s()]|\([^\s()]{0,500}\)){1,2000})"
                        r"(?:\s+\"[^\"\n]{0,300}\")?\s*\)")
_MD_REF_ODKAZ = re.compile(r"\[([^\]\n]{1,500})\]\[([^\]\n]{0,100})\]")
_MD_POZNAMKA = re.compile(r"\[\^([^\]\s]{1,50})\]")
_MD_CISLO = re.compile(r"\[(\d{1,4}(?:\s*[-–,]\s*\d{1,4}){0,30})\]")
_MD_AUTOODKAZ = re.compile(r"<(https?://[^<>\s]{1,2000})>", re.I)
_PLOT = re.compile(r"^\s{0,3}(```|~~~)")
_ODRAZKA = re.compile(r"^\s*(?:[-*+]|\d{1,9}[.)])\s+(?:\[[ xX]\]\s+)?")
_CESKE_ZNAKY = re.compile(r"[ěščřžůťďňĚŠČŘŽŮŤĎŇ]")
_CALLOUT = re.compile(r"^\s*\[![\w-]+\][+-]?.*$")
_KONCOVA_SPOJKA = re.compile(r"(?:\s*(?:[,;:]|\bsee\b|\bviz\b|\bsrov\.?|\bcf\.?))+\s*$", re.I)


def _cista_url(url: str) -> Optional[str]:
    url = (url or "").strip().rstrip(".,;:!?")
    while url.endswith(")") and url.count("(") < url.count(")"):
        url = url[:-1]
    return url if povolena_url(url) and len(url) <= 2000 else None


def _zdroj_z_textu(text: str) -> Optional[dict]:
    """Zdroj z textu položky seznamu zdrojů či definice: první URL a DOI (z URL nebo z textu)."""
    m = _URL_V_TEXTU.search(text or "")
    url = _cista_url(m.group()) if m else None
    doi = _doi_z_url(url) if url else None
    if not doi:
        bez_url = _URL_V_TEXTU.sub(" ", text or "")
        md = _DOI_V_ZPRAVE.search(bez_url)
        doi = normalizuj_doi(md.group(1)) if md else None
    if not (url or doi):
        return None
    popis = _bezpecny_kus(_MD_INLINE.sub(lambda x: x.group(2), text or ""), 200).strip()
    return {"url": url, "doi": doi, "popis": popis}


def _zdroj_z_url(url: str) -> Optional[dict]:
    url = _cista_url(url)
    if not url:
        return None
    return {"url": url, "doi": _doi_z_url(url), "popis": ""}


def _rozvin_znacky(obsah: str) -> List[str]:
    cisla_out: List[str] = []
    for cast in re.split(r"\s*,\s*", obsah):
        m = re.fullmatch(r"(\d{1,4})\s*[-–]\s*(\d{1,4})", cast)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a <= b:
                cisla_out += [str(i) for i in range(a, min(b, a + MAX_ROZSAH_ZNACEK - 1) + 1)]
        elif cast.isdigit():
            cisla_out.append(str(int(cast)))
    return cisla_out


def _definice_zpravy(radky: List[str]) -> Tuple[Dict[str, dict], set]:
    """1. průchod: definice odkazů a poznámek kdekoli a číslované položky v oddílu zdrojů.
    Vrací (štítek -> zdroj, množina čísel řádků, které nejsou tělem zprávy)."""
    definice: Dict[str, dict] = {}
    mimo_telo: set = set()
    v_plotu = False
    oddil = ""          # "" = tělo, "zdroje" = seznam zdrojů, "priloha" = mimo tělo bez zdrojů
    uroven_oddilu = 0
    if radky and radky[0].strip() == "---":  # YAML hlavička (vlastnosti Obsidianu)
        for j in range(1, min(len(radky), 200)):
            if radky[j].strip() in ("---", "..."):
                mimo_telo.update(range(0, j + 1))
                break
    for i, r in enumerate(radky):
        if i in mimo_telo:
            continue
        if _PLOT.match(r):
            v_plotu = not v_plotu
            mimo_telo.add(i)
            continue
        if v_plotu:
            mimo_telo.add(i)
            continue
        n = _NADPIS.match(r)
        if n:
            uroven = len(n.group(1))
            nazev = re.sub(r"[*_`]", "", n.group(2)).strip()
            if _NADPIS_ZDROJU.match(nazev):
                oddil, uroven_oddilu = "zdroje", uroven
            elif _NADPIS_PRILOHY.match(nazev):
                oddil, uroven_oddilu = "priloha", uroven
            elif oddil and uroven <= uroven_oddilu:
                oddil = ""
            continue
        d = _DEF_ODKAZU.match(r)
        if d:
            zdroj = _zdroj_z_textu(d.group(2))
            if zdroj:
                definice.setdefault(d.group(1).strip().lower(), zdroj)
            mimo_telo.add(i)
            continue
        if oddil == "priloha":
            mimo_telo.add(i)
        elif oddil == "zdroje":
            mimo_telo.add(i)
            p = _POLOZKA_ZDROJU.match(r)
            zdroj = _zdroj_z_textu(p.group(3) if p else r)
            if p and zdroj:
                definice.setdefault(str(int(p.group(1) or p.group(2))), zdroj)
    return definice, mimo_telo


def _jednotky_tela(radky: List[str], mimo_telo: set) -> List[Tuple[int, str]]:
    """2. průchod: odstavce, položky seznamů a řádky tabulek jako (číslo prvního řádku, text)."""
    jednotky: List[Tuple[int, str]] = []
    aktualni: List[str] = []
    start = 0

    def uzavri():
        nonlocal aktualni
        if aktualni:
            jednotky.append((start + 1, " ".join(aktualni)))
        aktualni = []

    for i, r in enumerate(radky):
        if i in mimo_telo or not r.strip() or _NADPIS.match(r) or _MD_LINKA.match(r) \
                or _MD_ODDELOVAC_TABULKY.match(r):
            uzavri()
            continue
        radek = _CALLOUT.sub("", _MD_CITACE.sub("", r))  # záhlaví calloutu Obsidianu i s titulkem
        if not radek.strip():
            uzavri()
            continue
        if radek.lstrip().startswith("|"):
            uzavri()
            bunky = [b.strip() for b in radek.strip().strip("|").split("|")]
            jednotky.append((i + 1, " – ".join(b for b in bunky if b)))
            continue
        if _ODRAZKA.match(radek):
            uzavri()
            start = i
            aktualni = [_ODRAZKA.sub("", radek, count=1).strip()]
            continue
        if not aktualni:
            start = i
        aktualni.append(radek.strip())
    uzavri()
    return jednotky


def _nahrad_citace(text: str, definice: Dict[str, dict], tabulka: List[dict]) -> str:
    """Citace v textu nahradí zástupnými značkami; tabulka[i] = {"druh": odkaz|znacka, "text", "zdroje"}."""

    def pridej(druh: str, zdroje: List[dict], viditelny: str = "") -> str:
        tabulka.append({"druh": druh, "text": viditelny, "zdroje": [z for z in zdroje if z]})
        return f"{_V_ZNAK}{len(tabulka) - 1}{_V_KONEC}"

    def inline(m):
        if m.group(1):  # obrázek
            return ""
        viditelny, cil = m.group(2), m.group(3).strip("<>")
        zdroj = _zdroj_z_url(cil)
        if not zdroj:
            return viditelny
        if re.fullmatch(r"\s*\[?\d{1,4}\]?\s*", viditelny or ""):
            return pridej("znacka", [zdroj])
        return pridej("odkaz", [zdroj], viditelny)

    def ref_odkaz(m):
        if _MD_CISLO.fullmatch(m.group(0)[: len(m.group(1)) + 2]) and re.fullmatch(r"\d{1,4}", m.group(2).strip()):
            # „[1][2]“ = dvě číselné značky za sebou, ne odkaz s textem „1“ a štítkem „2“
            zdroje = [definice[c] for c in _rozvin_znacky(m.group(1)) + [str(int(m.group(2)))] if c in definice]
            return pridej("znacka", zdroje) if zdroje else m.group(0)
        stitek = (m.group(2) or m.group(1)).strip().lower()
        zdroj = definice.get(stitek)
        if not zdroj:
            return m.group(0)
        if re.fullmatch(r"\d{1,4}", m.group(1).strip()):
            return pridej("znacka", [zdroj])
        return pridej("odkaz", [zdroj], m.group(1))

    def poznamka(m):
        zdroj = definice.get("^" + m.group(1).lower())
        return pridej("znacka", [zdroj]) if zdroj else m.group(0)

    def cislo(m):
        zdroje = [definice[c] for c in _rozvin_znacky(m.group(1)) if c in definice]
        return pridej("znacka", zdroje) if zdroje else m.group(0)

    def holy_url(m):
        zdroj = _zdroj_z_url(m.group(1) if m.lastindex else m.group(0))
        return pridej("znacka", [zdroj]) if zdroj else m.group(0)

    def holy_doi(m):
        doi = normalizuj_doi(m.group(1))
        if not doi:
            return m.group(0)
        return pridej("znacka", [{"url": None, "doi": doi, "popis": ""}])

    text = _MD_INLINE.sub(inline, text)
    text = _MD_REF_ODKAZ.sub(ref_odkaz, text)
    text = _MD_POZNAMKA.sub(poznamka, text)
    text = _MD_CISLO.sub(cislo, text)
    text = _MD_AUTOODKAZ.sub(holy_url, text)
    text = _URL_V_TEXTU.sub(holy_url, text)
    return _DOI_V_ZPRAVE.sub(holy_doi, text)


_ZNACKY_ZA_TECKOU = re.compile(r"([.!?…])((?:\s*" + _V_ZNAK + r"\d+" + _V_KONEC + r")+)")


def _presun_znacky(text: str, tabulka: List[dict]) -> str:
    """Značka za koncem věty („…effect.[1] Next“) patří k větě před ní; odkaz s textem zůstává za tečkou."""

    def presun(m):
        idx = _ZASTUPCE.findall(m.group(2))
        znacky = "".join(f"{_V_ZNAK}{c}{_V_KONEC}" for c in idx if tabulka[int(c)]["druh"] == "znacka")
        ostatni = "".join(f" {_V_ZNAK}{c}{_V_KONEC}" for c in idx if tabulka[int(c)]["druh"] != "znacka")
        return znacky + m.group(1) + ostatni

    return _ZNACKY_ZA_TECKOU.sub(presun, text)


def _cisty_text_tvrzeni(veta: str, tabulka: List[dict]) -> str:
    t = _ZASTUPCE.sub(lambda m: tabulka[int(m.group(1))]["text"] if tabulka[int(m.group(1))]["druh"] == "odkaz"
                      else "", veta)
    t = _MD_ZVYRAZNENI.sub("", t).replace("`", "")
    t = re.sub(r"\(\s*[,;]?\s*\)", "", t)          # prázdné závorky po odebraných značkách
    t = re.sub(r"\s+([.,;:!?)])", r"\1", " ".join(t.split()))
    t = _RIDICI.sub("", t).strip(" -–—•")
    konec = re.search(r"[.!?…]$", t)
    t = _KONCOVA_SPOJKA.sub("", t[:-1] if konec else t) + (konec.group() if konec else "")
    if len(t) > MAX_DELKA_TVRZENI:
        t = t[: MAX_DELKA_TVRZENI - 1] + "…"
    return t


def vytahni_tvrzeni(markdown: str) -> Tuple[List[dict], dict]:
    """Tvrzení s citacemi z Markdownu: věta nebo odrážka obsahující odkaz (URL, DOI, [n], [^n]) = tvrzení.
    Vrací (řádky pro davka: jeden řádek na dvojici tvrzení–zdroj, statistiky)."""
    markdown = _MD_KOMENTAR.sub("", markdown.replace("\r\n", "\n").replace("\r", "\n"))
    markdown = markdown.replace(_V_ZNAK, "").replace(_V_KONEC, "")
    radky = markdown.split("\n")
    definice, mimo_telo = _definice_zpravy(radky)
    stat = {"zdroju_v_seznamu": len(definice), "kratkych": 0, "pres_limit": 0, "bez_zdroje": 0}
    vystup: List[dict] = []
    n_tvrzeni = 0
    for cislo_radku, jednotka in _jednotky_tela(radky, mimo_telo):
        tabulka: List[dict] = []
        text = _nahrad_citace(jednotka, definice, tabulka)
        if not tabulka:
            continue
        text = _presun_znacky(text, tabulka)
        for veta in rozdel_na_vety(text):
            indexy = [int(c) for c in _ZASTUPCE.findall(veta)]
            if not indexy:
                continue
            cisty = _cisty_text_tvrzeni(veta, tabulka)
            if len(_SLOVO_RE.findall(cisty)) < MIN_SLOV_TVRZENI:
                stat["kratkych"] += 1
                continue
            if n_tvrzeni >= MAX_TVRZENI_ZPRAVY:
                stat["pres_limit"] += 1
                continue
            n_tvrzeni += 1
            tid = f"t{n_tvrzeni}"
            zdroje: List[dict] = []
            videne = set()
            for ix in indexy:
                for z in tabulka[ix]["zdroje"]:
                    klic = (z.get("url") or "", z.get("doi") or "")
                    if klic not in videne:
                        videne.add(klic)
                        zdroje.append(z)
            zaklad = {"tvrzeni_id": tid, "tvrzeni": cisty, "radek": cislo_radku}
            if not _CESKE_ZNAKY.search(cisty):
                zaklad["tvrzeni_en"] = cisty
            if obsahuje_pokyn(cisty):
                zaklad["obsahuje_pokyny_pro_AI"] = True
            if not zdroje:
                stat["bez_zdroje"] += 1
                vystup.append({"id": f"{tid}-0", **zaklad, "bez_zdroje": True})
                continue
            for k, z in enumerate(zdroje, 1):
                radek = {"id": f"{tid}-{k}", **zaklad}
                if z.get("url"):
                    radek["url"] = z["url"]
                if z.get("doi"):
                    radek["doi"] = z["doi"]
                if z.get("popis"):
                    radek["zdroj_popis"] = z["popis"]
                vystup.append(radek)
    stat["tvrzeni"] = n_tvrzeni
    stat["radku"] = len(vystup)
    return vystup, stat


def vytahni(zprava: str, vystup: Optional[str] = None) -> dict:
    """Příkaz vytahni: tvrzení s citacemi ze zprávy do JSONL (vstup pro davka)."""
    text = _nacti_text(zprava, MAX_ZPRAVA_BAJTU)
    radky, stat = vytahni_tvrzeni(text)
    if not vystup:
        zaklad = zprava[:-3] if zprava.lower().endswith(".md") else zprava
        vystup = zaklad + ".tvrzeni.jsonl"
    with open(vystup, "w", encoding="utf-8") as f:
        for r in radky:
            try:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            except UnicodeEncodeError:
                f.write(json.dumps(r) + "\n")
    return {"stav": "ok", **stat, "vystup": vystup}


# ---------------------------------------------------------------------------
# Tabulka verdiktů bran (příloha zprávy)
# ---------------------------------------------------------------------------
_POPIS_URL = {"ok": "ok", "mrtvy": "mrtvý", "nenacteno": "nenačteno"}
_POPIS_DOI = {"ok": "ok", "nesedi": "nesedí", "neexistuje": "neexistuje", "nenacteno": "nenačteno"}
_POPIS_RETRAKCE = {"bez_zaznamu": "bez záznamu", "retrahovano": "retrahováno", "vyjadreni_obav": "vyjádření obav",
                   "oprava": "oprava", "nenacteno": "nenačteno"}
_POPIS_CITATU = {"doslovne": "doslovně", "temer": "téměř", "nenalezen": "nenalezen", "nelze": "nelze"}
_POPIS_NAPOVEDY = {"nalezeno": "silná", "nenalezeno": "slabá", "castecne_nacteno": "částečně načteno",
                   "nenacteno": "nenačteno"}
_POPIS_G2 = {"potvrzeno": "potvrzeno", "castecne": "částečně", "vyvraceno": "vyvráceno",
             "neoveritelne": "neověřitelné"}
MAX_BUNKA = 100


def _bunka(x, n: int = MAX_BUNKA) -> str:
    """Text buňky tabulky. Tvrzení pocházejí z webu a zpráva jde do Obsidianu: bez kódu, který by spustil
    (obrácený apostrof = inline kód či plot, `$=` = inline dotaz Dataview) a bez HTML značek."""
    t = " ".join(_RIDICI.sub("", str(x if x is not None else "")).split())
    t = t.replace("`", "'").replace("$=", "$ =").replace("<", "&lt;").replace(">", "&gt;")
    if len(t) > n:
        t = t[: n - 1] + "…"
    return t.replace("\\", "\\\\").replace("|", "\\|") or "–"


def _zdroj_bunka(vstup: dict) -> str:
    doi = normalizuj_doi(str(vstup.get("doi") or ""))
    if doi:
        return "doi:" + doi
    url = str(vstup.get("url") or "")
    if povolena_url(url):
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        return host[4:] if host.startswith("www.") else host
    return "–"


def tabulka_verdiktu(davka_radky: List[dict], g2: Dict[str, dict], tvrzeni: Dict[str, dict],
                     stitky_vysl: Optional[dict] = None, g3: Optional[dict] = None) -> Tuple[str, dict]:
    """Markdown tabulka verdiktů bran a souhrn; jeden řádek tabulky = jedna dvojice tvrzení–zdroj. Souhrn G1
    odliší vady (tvrdé vady + nesedící čísla v plně načteném textu) od nenačtených citací a uvede oba podíly."""
    davka_radky = cisla_po_tvrzenich(davka_radky, {rid: str(_slovnik(v).get("tvrzeni_id"))
                                                   for rid, v in (tvrzeni or {}).items()
                                                   if _slovnik(v).get("tvrzeni_id") not in (None, "")})
    stitek_zdroje: Dict[str, dict] = {}
    if stitky_vysl:
        for t in _seznam(stitky_vysl.get("tvrzeni")):
            if isinstance(t, dict):
                for zid in _seznam(t.get("zdroje")):
                    stitek_zdroje[str(zid)] = t
                stitek_zdroje.setdefault("tvrzeni:" + str(t.get("id")), t)
    s = Counter({k: 0 for k in ("citaci", "s_vadou", "mrtvy", "doi_vada", "retrakce", "cisla_nesedi",
                                "citat_nenalezen", "nenacteno", "zastena", "castecne_nacteno", "bez_textu",
                                "g2_chybi")})
    radky_md = ["| ID | Tvrzení | Zdroj | Odkaz | DOI | Retrakce | Citát | Nápověda | G2 | Štítek |",
                "|---|---|---|---|---|---|---|---|---|---|"]
    for r in davka_radky:
        rid = str(r.get("id"))
        vstup = _slovnik(tvrzeni.get(rid))
        url = _slovnik(r.get("url")).get("stav")
        doi = _slovnik(r.get("doi")).get("stav")
        retrakce = _slovnik(r.get("retrakce"))
        retr = retrakce.get("stav")
        pas = _slovnik(r.get("pasaze"))
        citat = _slovnik(pas.get("citat")).get("stav")
        uplny = _uplny_text(pas)
        if citat == "nenalezen" and not uplny:
            citat = "nelze"  # v neúplném textu se citát posoudit nedá
        verdikt = norm_verdikt(g2.get(rid))
        tvrde = tvrde_vady_g1(r)
        cisla_nesedi = _cisla_nesedi(r)
        s["citaci"] += 1
        s["s_vadou"] += bool(tvrde or cisla_nesedi)
        s["mrtvy"] += url == "mrtvy"
        s["doi_vada"] += doi in ("nesedi", "neexistuje")
        s["retrakce"] += retr == "retrahovano"
        s["cisla_nesedi"] += bool(cisla_nesedi and not tvrde)
        s["citat_nenalezen"] += citat == "nenalezen"
        if nenacteno_g1(r):
            s["nenacteno"] += 1
            s["zastena" if pas.get("zastena") else "bez_textu" if pas.get("stav") == "nenacteno"
              else "castecne_nacteno"] += 1
        s["g2_" + (verdikt or "chybi")] += 1
        retr_txt = "je oznámení" if retr != "retrahovano" and _seznam(retrakce.get("oznameni_k")) \
            else _POPIS_RETRAKCE.get(retr, "–")
        if pas.get("zastena"):
            napoveda = "zástěna"
        elif pas.get("stav") in ("nalezeno", "nenalezeno") and not uplny:
            napoveda = _POPIS_NAPOVEDY["castecne_nacteno"]  # starší výstup davka: krátký text s „nenalezeno“
        else:
            napoveda = _POPIS_NAPOVEDY.get(pas.get("stav"), "–")
            if uplny and isinstance(pas.get("skore_max"), (int, float)):
                napoveda += f" ({pas['skore_max']:.2f})".replace(".", ",")
        if cisla_nesedi:
            napoveda += "; čísla chybí"
        t = stitek_zdroje.get(rid) or stitek_zdroje.get("tvrzeni:" + str(vstup.get("tvrzeni_id")))
        stitek_txt = "–"
        if t:
            stitek_txt = "vyřadit" if t.get("akce") == "vyradit" else (t.get("stitek") or "–")
            if t.get("akce") == "preformulovat":
                stitek_txt += " (přeformulovat)"
            elif t.get("akce") != "vyradit" and t.get("stitek_sberace") and t.get("stitek") != t["stitek_sberace"]:
                stitek_txt += f" (sběrač: {t['stitek_sberace']})"
        radky_md.append("| " + " | ".join([
            _bunka(rid, 20), _bunka(vstup.get("tvrzeni") or vstup.get("tvrzeni_en")), _bunka(_zdroj_bunka(vstup), 60),
            _POPIS_URL.get(url, "–"), _POPIS_DOI.get(doi, "–"), retr_txt,
            _POPIS_CITATU.get(citat, "–"), _bunka(napoveda, 40), _POPIS_G2.get(verdikt, "–"), _bunka(stitek_txt, 30),
        ]) + " |")
    n = s["citaci"]
    podil = round(100 * s["s_vadou"] / n) if n else 0
    podil_nenacteno = round(100 * s["nenacteno"] / n) if n else 0
    g2_doporucen = bool(n) and s["s_vadou"] / n > PODIL_VAD_PRO_G2
    souhrn = [
        f"- **G1:** citací {n} – vada u {s['s_vadou']} z {n} citací ({podil} %): mrtvý odkaz {s['mrtvy']}, "
        f"DOI nesedí či neexistuje {s['doi_vada']}, retrakce {s['retrakce']}, nesedící čísla {s['cisla_nesedi']}; "
        f"nenačteno {s['nenacteno']} z {n} citací ({podil_nenacteno} %): zástěna {s['zastena']}, "
        f"částečný text {s['castecne_nacteno']}, bez textu {s['bez_textu']} (není vada); citát nenalezen "
        f"v plném textu {s['citat_nenalezen']} (jen nápověda). Podle vad G2 doporučen: "
        f"{'ano' if g2_doporucen else 'ne'} (práh {round(100 * PODIL_VAD_PRO_G2)} %).",
        f"- **G2:** ověřeno {n - s['g2_chybi']} z {n} citací – potvrzeno {s['g2_potvrzeno']}, "
        f"částečně {s['g2_castecne']}, vyvráceno {s['g2_vyvraceno']}, neověřitelné {s['g2_neoveritelne']}."
        if s["g2_chybi"] < n else "- **G2:** neproběhl.",
    ]
    if g3:
        souhrn.append(f"- **G3:** pro {_bunka(g3.get('pro'), 10)}, proti {_bunka(g3.get('proti'), 10)}.")
    if stitky_vysl and isinstance(stitky_vysl.get("souhrn"), dict):
        so = stitky_vysl["souhrn"]
        souhrn.append("- **Štítky:** " + ", ".join(f"{k} {so.get(k, 0)}" for k in STITKY)
                      + f", vyřazeno {so.get('vyradit', 0)}, přeformulovat {so.get('preformulovat', 0)}.")
    md = "\n".join(souhrn) + "\n\n" + "\n".join(radky_md) + "\n"
    return md, dict(s)


def verdikty(davka_vystup: str, g2: Optional[str] = None, tvrzeni: Optional[str] = None,
             stitky_cesta: Optional[str] = None, g3: Optional[str] = None, vystup: Optional[str] = None) -> dict:
    """Příkaz verdikty: tabulka verdiktů bran v Markdownu (do přílohy zprávy)."""
    radky = nacti_json_nebo_jsonl(davka_vystup)
    radky = [r for r in _seznam(radky if isinstance(radky, list) else [radky]) if isinstance(r, dict)]
    g2_mapa = _podle_id(nacti_json_nebo_jsonl(g2)) if g2 else {}
    t_mapa = _podle_id(nacti_json_nebo_jsonl(tvrzeni)) if tvrzeni else {}
    st = nacti_json_nebo_jsonl(stitky_cesta) if stitky_cesta else None
    g3_data = nacti_json_nebo_jsonl(g3) if g3 else None
    md, souhrn = tabulka_verdiktu(radky, g2_mapa, t_mapa, st if isinstance(st, dict) else None,
                                  g3_data if isinstance(g3_data, dict) else None)
    if vystup:
        with open(vystup, "w", encoding="utf-8") as f:
            f.write(md)
    return {"stav": "ok", "radku": len(radky), "souhrn": souhrn, "markdown": md, "vystup": vystup}


# ---------------------------------------------------------------------------
# Zadání ověřovače G2 (pasáže doslova ze skriptu, ne přepsané hlavním agentem)
# ---------------------------------------------------------------------------
MAX_G2_DAVKA = 8               # tvrzení na jedno volání ověřovače (references/role.md)
MAX_PASAZI_G2 = 3


def zadani_g2(davka_radky: List[dict], tvrzeni: Dict[str, dict], idy: Optional[List[str]] = None,
              po: int = MAX_G2_DAVKA) -> dict:
    """Zadání G2: jeden prvek na řádek dávky (dvojice tvrzení–zdroj) v pořadí idy (jinak v pořadí dávky).
    Pasáže = první 3 ze skriptu vždy; silna_napoveda = stav pasáží „nalezeno“ (skóre nad PRAH)."""
    podle_id = {str(r.get("id")): r for r in davka_radky if isinstance(r, dict) and r.get("id") is not None}
    poradi = [str(i) for i in idy] if idy else list(podle_id)
    po = max(1, min(int(po or MAX_G2_DAVKA), MAX_G2_DAVKA))
    polozky, preskoceno, videne = [], [], set()
    for rid in poradi:
        if rid in videne:
            continue
        videne.add(rid)
        r = podle_id.get(rid)
        vstup = _slovnik(tvrzeni.get(rid))
        if r is None:
            preskoceno.append({"id": rid, "duvod": "id není ve výstupu dávky"})
            continue
        vady = tvrde_vady_g1(r)
        if vady:
            preskoceno.append({"id": rid, "duvod": ", ".join(vady)})
            continue
        pas = _slovnik(r.get("pasaze"))
        citat_stav = _slovnik(pas.get("citat")).get("stav")
        if citat_stav == "nenalezen" and not _uplny_text(pas):
            citat_stav = "nelze"  # neúplný text nebo zástěna: citát se posoudit nedá
        pasaze = [{"text": _bezpecny_kus(x.get("text"), MAX_PASAZ), "skore": x.get("skore")}
                  for x in _seznam(pas.get("pasaze"))[:MAX_PASAZI_G2] if isinstance(x, dict) and x.get("text")]
        polozky.append({
            "id": rid,
            "tvrzeni_en": _zkrat(str(vstup.get("tvrzeni_en") or vstup.get("tvrzeni") or ""), MAX_DELKA_TVRZENI),
            "url": vstup.get("url") or None,
            "doi": normalizuj_doi(str(vstup.get("doi") or "")) or None,
            "citat": _zkrat(str(vstup.get("citat")), 300) if vstup.get("citat") else None,
            "citat_stav": citat_stav,
            "pasaze": pasaze,
            "silna_napoveda": pas.get("stav") == "nalezeno",
            "cisla_chybi_ve_zdroji": _cisla_nesedi(r)[:10],  # jen z plně načteného textu
        })
    davky = [polozky[i:i + po] for i in range(0, len(polozky), po)]
    return {"stav": "ok", "polozek": len(polozky), "davek": len(davky), "davky": davky, "preskoceno": preskoceno}


# ---------------------------------------------------------------------------
# Dávka
# ---------------------------------------------------------------------------
def zpracuj_radek(radek: dict, k: int = 3) -> dict:
    vysl = {"id": radek.get("id")}
    url = radek.get("url") or None
    doi = radek.get("doi") or None
    tvrzeni = radek.get("tvrzeni") or ""
    if url:
        vysl["url"] = zkontroluj_url(str(url))
    if doi:
        rok = radek.get("rok")
        try:
            rok = int(rok) if rok is not None else None
        except (TypeError, ValueError):
            rok = None
        vysl["doi"] = over_doi(str(doi), radek.get("nazev"), radek.get("autor"), rok)
        vysl["retrakce"] = over_retrakci(str(doi))
    tvrzeni_en = radek.get("tvrzeni_en") or None
    citat = radek.get("citat") or None
    if (tvrzeni or tvrzeni_en) and (url or doi):
        vysl["pasaze"] = najdi_pasaze(str(tvrzeni), str(url) if url else None, str(doi) if doi else None, k,
                                      tvrzeni_en=str(tvrzeni_en) if tvrzeni_en else None,
                                      citat=str(citat) if citat else None)
    else:
        vysl["pasaze"] = {"stav": "nenacteno", "duvod": "chybí tvrzení nebo zdroj (url/doi)", "skore_max": 0.0,
                          "pasaze": [], "zdroj_textu": "", "delka_textu": 0, "vynechano_pokynu": 0}
        if citat:
            vysl["pasaze"]["citat"] = najdi_citat(str(citat), None)
    return vysl


def davka(vstup: str, vystup: str, k: int = 3) -> dict:
    radky: List[Tuple[int, Optional[dict], Optional[str]]] = []
    with open(vstup, encoding="utf-8", errors="replace") as f:  # vadný bajt nesmí shodit celou dávku
        for cislo, r in enumerate(f, 1):
            if not r.strip():
                continue
            try:
                obj = json.loads(r)
                if not isinstance(obj, dict):
                    raise ValueError("řádek není objekt")
                radky.append((cislo, obj, None))
            except ValueError as e:
                radky.append((cislo, None, f"neplatný JSON na řádku {cislo}: {e}"[:200]))

    def prace(polozka):
        cislo, obj, chyba = polozka
        if chyba:
            return {"id": None, "radek": cislo, "chyba": chyba}
        try:
            return zpracuj_radek(obj, k)
        except Exception as e:  # jeden řádek nesmí shodit dávku
            return {"id": obj.get("id"), "radek": cislo, "chyba": f"{type(e).__name__}: {e}"[:300]}

    chybnych = 0
    with open(vystup, "w", encoding="utf-8") as out, \
            concurrent.futures.ThreadPoolExecutor(max_workers=MAX_SOUBEZNE) as ex:
        for v in ex.map(prace, radky):
            if "chyba" in v:
                chybnych += 1
            radek = json.dumps(v, ensure_ascii=False)
            try:
                radek.encode("utf-8")
            except UnicodeEncodeError:
                # Osamocený surrogate (např. "\ud83d" ve vstupu nebo v metadatech Crossrefu) by
                # shodil celou dávku; ASCII JSON ho zapíše jako platný escape.
                radek = json.dumps(v)
            out.write(radek + "\n")
            out.flush()
    return {"stav": "ok", "radku": len(radky), "chybnych_radku": chybnych, "vystup": vystup}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
class _ChybaArgumentu(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _ChybaArgumentu(message)


def _vypis(obj) -> None:
    data = json.dumps(obj, ensure_ascii=False)
    try:
        sys.stdout.write(data + "\n")
    except UnicodeEncodeError:
        sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main(argv: Optional[List[str]] = None) -> int:
    p = _Parser(prog="citace.py", description="Prototyp ověřování citací (výstup JSON).")
    sub = p.add_subparsers(dest="prikaz")
    s = sub.add_parser("url", help="stav odkazu")
    s.add_argument("url")
    s = sub.add_parser("doi", help="metadata DOI a porovnání")
    s.add_argument("doi")
    s.add_argument("--nazev")
    s.add_argument("--autor")
    s.add_argument("--rok", type=int)
    s = sub.add_parser("retrakce", help="retrakce / vyjádření obav / opravy")
    s.add_argument("doi")
    s = sub.add_parser("pasaze", help="pasáže zdroje k tvrzení")
    s.add_argument("--tvrzeni", required=True)
    s.add_argument("--tvrzeni-en", dest="tvrzeni_en", help="anglická podoba tvrzení (skóruje se podle ní)")
    s.add_argument("--citat", help="doslovný citát ze zdroje, jak ho uvedl sběrač")
    s.add_argument("--url")
    s.add_argument("--doi")
    s.add_argument("--k", type=int, default=3)
    s = sub.add_parser("davka", help="dávka JSONL")
    s.add_argument("vstup")
    s.add_argument("vystup")
    s.add_argument("--k", type=int, default=3)
    s = sub.add_parser("stitky", help="štítky tvrzení (sběrač zeslabený G1, nebo pravidlo G2)")
    s.add_argument("vstup")
    s.add_argument("--g1", help="výstup davka (JSONL); jinak pole „g1“ ve vstupu")
    s = sub.add_parser("vytahni", help="tvrzení s citacemi z Markdown zprávy do JSONL")
    s.add_argument("zprava")
    s.add_argument("--vystup")
    s = sub.add_parser("zadani-g2", help="zadání ověřovače G2 po dávkách z výstupu davka")
    s.add_argument("davka_vystup")
    s.add_argument("--tvrzeni", required=True, help="vstup dávky (JSONL): tvrzeni_en, url, doi, citat")
    s.add_argument("--id", nargs="+", help="jen tato id řádků dávky (klíčová tvrzení), v tomto pořadí")
    s.add_argument("--po", type=int, default=MAX_G2_DAVKA, help=f"tvrzení na dávku (≤ {MAX_G2_DAVKA})")
    s = sub.add_parser("verdikty", help="tabulka verdiktů bran v Markdownu")
    s.add_argument("davka_vystup")
    s.add_argument("--g2", help="verdikty ověřovače (JSON/JSONL s id řádku dávky)")
    s.add_argument("--tvrzeni", help="vstup dávky (JSONL) kvůli textu tvrzení")
    s.add_argument("--stitky", help="výstup příkazu stitky (JSON)")
    s.add_argument("--g3", help="JSON s poli pro a proti (z MVP 1.1; M0-lite ho nepoužívá)")
    s.add_argument("--vystup", help="kam zapsat tabulku (.md)")
    try:
        a = p.parse_args(argv)
        if not a.prikaz:
            raise _ChybaArgumentu("chybí příkaz (url, doi, retrakce, pasaze, davka, stitky, vytahni, zadani-g2, "
                                  "verdikty)")
        if a.prikaz == "url":
            _vypis(zkontroluj_url(a.url))
        elif a.prikaz == "doi":
            _vypis(over_doi(a.doi, a.nazev, a.autor, a.rok))
        elif a.prikaz == "retrakce":
            _vypis(over_retrakci(a.doi))
        elif a.prikaz == "pasaze":
            if not a.url and not a.doi:
                raise _ChybaArgumentu("pasaze vyžaduje --url nebo --doi")
            _vypis(najdi_pasaze(a.tvrzeni, a.url, a.doi, a.k, tvrzeni_en=a.tvrzeni_en, citat=a.citat))
        elif a.prikaz == "davka":
            _vypis(davka(a.vstup, a.vystup, a.k))
        elif a.prikaz == "stitky":
            vysl = stitky(a.vstup, a.g1)
            _vypis(vysl)
            return 0 if vysl.get("stav") == "ok" else 2
        elif a.prikaz == "vytahni":
            _vypis(vytahni(a.zprava, a.vystup))
        elif a.prikaz == "zadani-g2":
            radky = nacti_json_nebo_jsonl(a.davka_vystup)
            radky = [r for r in _seznam(radky if isinstance(radky, list) else [radky]) if isinstance(r, dict)]
            _vypis(zadani_g2(radky, _podle_id(nacti_json_nebo_jsonl(a.tvrzeni)), a.id, a.po))
        elif a.prikaz == "verdikty":
            _vypis(verdikty(a.davka_vystup, a.g2, a.tvrzeni, a.stitky, a.g3, a.vystup))
        return 0
    except _ChybaArgumentu as e:
        _vypis({"stav": "chyba", "duvod": f"argumenty: {e}"[:300]})
        return 2
    except OSError as e:
        _vypis({"stav": "chyba", "duvod": f"soubor: {e}"[:300]})
        return 1
    except ValueError as e:
        _vypis({"stav": "chyba", "duvod": f"vstup: {e}"[:300]})
        return 2
    except Exception as e:  # pojistka: výstup vždy JSON
        _vypis({"stav": "chyba", "duvod": f"{type(e).__name__}: {e}"[:300]})
        return 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
