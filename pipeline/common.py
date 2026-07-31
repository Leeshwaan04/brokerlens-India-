"""Shared plumbing for every ingestion adapter.

Deliberately stdlib-only: this pipeline has to run on a bare python3 in a cron
container with no pip install step. urllib + http.cookiejar covers everything we
need, including NSE's cookie-gated APIs.
"""
from __future__ import annotations

import gzip
import hashlib
import http.cookiejar
import io
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(DATA, "raw")
CACHE = os.path.join(DATA, "cache")
CANONICAL = os.path.join(DATA, "canonical")
MANUAL = os.path.join(DATA, "manual")
CONFIG = os.path.join(ROOT, "config")
SITE_DATA = os.path.join(ROOT, "site", "data")

# A source we do not control could return an unbounded body - through compromise,
# a misconfiguration, or simply an error page that streams forever. Cap what we
# are willing to hold in memory, and cap decompression separately: a 1KB zip can
# expand to gigabytes.
MAX_RESPONSE_BYTES = 64 * 1024 * 1024      # 64MB; MCX's 1.28MB is the real-world max
MAX_UNZIPPED_BYTES = 256 * 1024 * 1024     # 256MB across all members of one archive
MAX_COMPRESSION_RATIO = 200                # refuse anything expanding more than 200x

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

for _d in (RAW, CACHE, CANONICAL, MANUAL, SITE_DATA):
    os.makedirs(_d, exist_ok=True)


# --------------------------------------------------------------------------- log

_T0 = time.time()


def log(msg, level="info"):
    mark = {"info": "  ", "ok": "ok", "warn": "!!", "err": "XX"}.get(level, "  ")
    sys.stderr.write("[%6.1fs] %s %s\n" % (time.time() - _T0, mark, msg))
    sys.stderr.flush()


# -------------------------------------------------------------------------- http


class Fetcher:
    """One Fetcher per host family, so cookie jars stay isolated.

    NSE hands out its session cookies only from an HTML page load; hitting an
    /api/ path cold returns 401/403. `warm()` does that handshake once and the
    jar carries it for the rest of the run.
    """

    def __init__(self, name, referer=None, warm_urls=(), timeout=30, cache_ttl=3600):
        self.name = name
        self.referer = referer
        self.warm_urls = warm_urls
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self.jar = http.cookiejar.CookieJar()
        ctx = ssl.create_default_context()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            urllib.request.HTTPSHandler(context=ctx),
            urllib.request.HTTPRedirectHandler(),
        )
        self._warmed = False

    def _headers(self, extra=None):
        # Akamai Bot Manager (MCX, and NSE/BSE's edge) scores requests on the
        # presence and consistency of client hints and Sec-Fetch metadata, not
        # just User-Agent. Sending the full set a real Chrome sends is the
        # difference between 403 and 200 on mcxindia.com.
        h = {
            "User-Agent": UA,
            "Accept": "application/json, text/csv, text/html, */*",
            "Accept-Language": "en-IN,en-GB;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive",
        }
        if self.referer:
            h["Referer"] = self.referer
        if extra:
            h.update(extra)
        return h

    # Header profile for a top-level page load rather than an XHR.
    DOC_HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }

    def warm(self):
        if self._warmed:
            return
        for u in self.warm_urls:
            try:
                self._raw(u, headers=dict(self.DOC_HEADERS))
                time.sleep(0.4)
            except Exception as exc:  # a cold jar is recoverable; a crash is not
                log("%s warm-up failed on %s: %s" % (self.name, u, exc), "warn")
        self._warmed = True

    def _raw(self, url, data=None, headers=None, method=None):
        req = urllib.request.Request(
            url, data=data, headers=self._headers(headers), method=method
        )
        resp = self.opener.open(req, timeout=self.timeout)

        declared = resp.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > MAX_RESPONSE_BYTES:
            resp.close()
            raise ValueError("response declares %s bytes, over the %d byte cap"
                             % (declared, MAX_RESPONSE_BYTES))

        # Read with a hard ceiling: a missing/lying Content-Length must not let a
        # source stream unbounded data into memory.
        body = resp.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            resp.close()
            raise ValueError("response exceeded the %d byte cap" % MAX_RESPONSE_BYTES)

        if resp.headers.get("Content-Encoding") == "gzip":
            compressed = len(body)
            body = gzip.decompress(body)
            if len(body) > MAX_RESPONSE_BYTES or (
                    compressed and len(body) / compressed > MAX_COMPRESSION_RATIO
                    and len(body) > 8 * 1024 * 1024):
                raise ValueError("gzip body expanded %dx to %d bytes - refusing"
                                 % (len(body) / max(compressed, 1), len(body)))
        return body, resp

    def _cache_path(self, url, data):
        key = hashlib.sha1((url + (data.decode("utf-8", "ignore") if data else "")).encode()).hexdigest()[:20]
        return os.path.join(CACHE, "%s_%s.bin" % (self.name, key))

    def get(self, url, data=None, headers=None, retries=3, use_cache=True, ttl=None):
        """Returns bytes, or None if the source is unavailable.

        Adapters must treat None as "source down" and keep the previous
        canonical values rather than publishing a hole.
        """
        ttl = self.cache_ttl if ttl is None else ttl
        cp = self._cache_path(url, data)
        if use_cache and ttl > 0 and os.path.exists(cp):
            age = time.time() - os.path.getmtime(cp)
            if age < ttl:
                log("%s cache hit (%.0fm old) %s" % (self.name, age / 60, _short(url)))
                with open(cp, "rb") as fh:
                    return fh.read()

        self.warm()
        delay = 1.0
        for attempt in range(1, retries + 1):
            try:
                body, resp = self._raw(url, data=data, headers=headers)
                if resp.status >= 400:
                    raise urllib.error.HTTPError(url, resp.status, "http error", resp.headers, None)
                log("%s %s %s -> %d bytes" % (self.name, resp.status, _short(url), len(body)), "ok")
                if use_cache:
                    _atomic_bytes(cp, body)
                return body
            except Exception as exc:
                log(
                    "%s attempt %d/%d failed %s: %s"
                    % (self.name, attempt, retries, _short(url), exc),
                    "warn",
                )
                if attempt < retries:
                    time.sleep(delay)
                    delay *= 2
                    self._warmed = False  # force a fresh handshake
        # last resort: a stale cache entry beats no data at all
        if os.path.exists(cp):
            log("%s serving STALE cache for %s" % (self.name, _short(url)), "warn")
            with open(cp, "rb") as fh:
                return fh.read()
        return None

    def get_json(self, url, **kw):
        body = self.get(url, **kw)
        if not body:
            return None
        try:
            return json.loads(body.decode("utf-8", "replace"))
        except Exception as exc:
            log("%s bad json from %s: %s" % (self.name, _short(url), exc), "warn")
            return None

    def get_text(self, url, **kw):
        body = self.get(url, **kw)
        return body.decode("utf-8", "replace") if body else None

    def post_form(self, url, fields, headers=None, **kw):
        data = urllib.parse.urlencode(fields).encode()
        h = {"Content-Type": "application/x-www-form-urlencoded"}
        if headers:
            h.update(headers)
        return self.get(url, data=data, headers=h, **kw)

    def get_zip_member(self, url, member=None, **kw):
        """Extract one member, refusing decompression bombs.

        zipfile happily inflates a small archive into gigabytes. The declared
        file_size is checked BEFORE reading, and the ratio is checked after, so a
        lying header cannot get past either.
        """
        body = self.get(url, **kw)
        if not body:
            return None
        try:
            zf = zipfile.ZipFile(io.BytesIO(body))
            name = member or zf.namelist()[0]
            info = zf.getinfo(name)

            if info.file_size > MAX_UNZIPPED_BYTES:
                raise ValueError("member %s declares %d bytes, over the cap"
                                 % (name, info.file_size))
            if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO \
                    and info.file_size > 8 * 1024 * 1024:
                raise ValueError("member %s expands %dx - refusing as a zip bomb"
                                 % (name, info.file_size / info.compress_size))

            with zf.open(name) as fh:
                data = fh.read(MAX_UNZIPPED_BYTES + 1)
            if len(data) > MAX_UNZIPPED_BYTES:
                raise ValueError("member %s exceeded the unzipped cap" % name)
            return data.decode("utf-8", "replace")
        except Exception as exc:
            log("zip extract failed %s: %s" % (_short(url), exc), "warn")
            return None


def _short(url, n=68):
    return url if len(url) <= n else url[:n - 3] + "..."


# ------------------------------------------------------------------ preset hosts


def nse():
    return Fetcher(
        "nse",
        referer="https://www.nseindia.com/",
        warm_urls=["https://www.nseindia.com/"],
    )


def nse_archives():
    return Fetcher("nsearch", referer="https://www.nseindia.com/")


def bse():
    # BSE 302-redirects api calls and drops them without a Referer.
    return Fetcher("bse", referer="https://www.bseindia.com/")


def sebi():
    return Fetcher("sebi", referer="https://www.sebi.gov.in/", timeout=45)


# ------------------------------------------------------------------------- io


def _atomic_bytes(path, body):
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(body)
    os.replace(tmp, path)


def write_json(path, obj, compact=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        if compact:
            json.dump(obj, fh, separators=(",", ":"), ensure_ascii=False)
        else:
            json.dump(obj, fh, indent=2, ensure_ascii=False, sort_keys=False)
    os.replace(tmp, path)
    return os.path.getsize(path)


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def snapshot(name, obj):
    """Keep every raw pull, dated. Data lineage is the product here."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    write_json(os.path.join(RAW, name, "%s.json" % day), obj)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ html/text


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def strip_tags(s):
    import html as _html

    return _WS.sub(" ", _html.unescape(_TAG.sub(" ", s or ""))).strip()


def tables(html):
    """Yield tables as lists of row-cell-lists. Good enough for SEBI/NSE markup."""
    for tbl in re.findall(r"<table[^>]*>(.*?)</table>", html or "", re.S | re.I):
        rows = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.S | re.I):
            cells = [
                strip_tags(c)
                for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)
            ]
            if cells:
                rows.append(cells)
        if rows:
            yield rows


# SEBI renders record sets as stacks of .card-view > .title/.value pairs,
# with SINGLE-quoted class attributes in AJAX fragments and DOUBLE-quoted ones
# in server-rendered pages. Both forms have to parse.
_CARD_BLOCK = re.compile(
    r"<div class=['\"]fixed-table-body card-table['\"]>(.*?)"
    r"(?=<div class=['\"]fixed-table-body card-table['\"]>|\Z)",
    re.S,
)
_CARD_PAIR = re.compile(
    r"<div class=['\"]card-view['\"]>\s*<div class=['\"]title['\"]>\s*<span>(.*?)</span>\s*</div>\s*"
    r"<div class=['\"]value[^'\"]*['\"]>\s*<span>(.*?)</span>",
    re.S,
)


def card_records(html):
    """Yield one dict per SEBI card block: {normalised_label: value}."""
    for block in _CARD_BLOCK.findall(html or ""):
        rec = {}
        for k, v in _CARD_PAIR.findall(block):
            key = strip_tags(k).rstrip(":").strip().lower()
            key = re.sub(r"[^a-z0-9]+", "_", key).strip("_")
            val = strip_tags(v)
            if key and val:
                rec[key] = val
        if rec:
            yield rec


def to_num(s):
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return s
    t = re.sub(r"[^0-9.\-]", "", str(s))
    if t in ("", "-", ".", "-."):
        return None
    try:
        v = float(t)
        return int(v) if v.is_integer() else v
    except ValueError:
        return None


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)
