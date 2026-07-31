"""Canonical broker identity resolution.

The core data-engineering problem: "Zerodha" the brand, "ZERODHA BROKING
LIMITED" on the SEBI registry, "Zerodha Broking Ltd." in an NSE circular and
"ZERODHA BROKING LTD" in a BSE turnover file are one entity. Everything the
site publishes hangs off getting that right.

Strategy, cheapest-first:
  1. exact match on a normalised alias
  2. containment either way on normalised strings
  3. token-overlap score above a threshold, with a margin over the runner-up

No fuzzy match is accepted without a margin - an ambiguous match is worse than
no match, because it silently attributes one broker's complaints to another.
"""
from __future__ import annotations

import re

from .common import log

_NOISE = {
    "limited", "ltd", "private", "pvt", "public", "company", "co", "and", "&",
    "the", "india", "indian", "services", "service", "securities", "security",
    "broking", "brokers", "broker", "share", "shares", "stock", "stocks",
    "financial", "finance", "capital", "markets", "market", "investment",
    "investments", "holdings", "group", "llp", "inc", "corporation",
}


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(s, drop_noise=True):
    t = [w for w in norm(s).split() if len(w) > 1]
    if drop_noise:
        core = [w for w in t if w not in _NOISE]
        # never reduce a name to nothing - "Sharekhan Limited" is all-noise-adjacent
        return core or t
    return t


class Resolver:
    def __init__(self, brokers):
        self.brokers = brokers
        self.by_id = {b["id"]: b for b in brokers}
        self.exact = {}
        self.token_sets = {}
        for b in brokers:
            names = set(b.get("aliases") or [])
            names.add(b.get("brand", ""))
            names.add(b.get("legal_name", ""))
            for n in names:
                if n:
                    self.exact.setdefault(norm(n), b["id"])
            self.token_sets[b["id"]] = set(tokens(b.get("legal_name") or b["brand"])) | set(
                tokens(b.get("brand"))
            )
        self.stats = {"exact": 0, "contains": 0, "token": 0, "ambiguous": 0, "miss": 0}

    def resolve(self, raw_name, threshold=0.62, margin=0.12):
        """Return (broker_id, method, score) or (None, reason, score)."""
        n = norm(raw_name)
        if not n:
            return None, "empty", 0.0

        if n in self.exact:
            self.stats["exact"] += 1
            return self.exact[n], "exact", 1.0

        # containment: registry names are usually the brand plus corporate suffix
        hits = [bid for alias, bid in self.exact.items() if len(alias) >= 5 and (alias in n or n in alias)]
        if len(set(hits)) == 1:
            self.stats["contains"] += 1
            return hits[0], "contains", 0.9

        cand = set(tokens(raw_name))
        if not cand:
            self.stats["miss"] += 1
            return None, "no_tokens", 0.0

        scored = []
        for bid, ts in self.token_sets.items():
            if not ts:
                continue
            inter = len(cand & ts)
            if not inter:
                continue
            scored.append((inter / len(cand | ts), bid))
        if not scored:
            self.stats["miss"] += 1
            return None, "no_overlap", 0.0

        scored.sort(reverse=True)
        best, bid = scored[0]
        second = scored[1][0] if len(scored) > 1 else 0.0
        if best >= threshold and (best - second) >= margin:
            self.stats["token"] += 1
            return bid, "token", round(best, 3)
        if best >= threshold:
            self.stats["ambiguous"] += 1
            return None, "ambiguous", round(best, 3)
        self.stats["miss"] += 1
        return None, "below_threshold", round(best, 3)

    def alias_index(self):
        """Lowercased alias -> broker_id, for cheap substring scanning of free text."""
        idx = {}
        for b in self.brokers:
            names = set(b.get("aliases") or [])
            names.add((b.get("brand") or "").lower())
            names.add((b.get("legal_name") or "").lower())
            idx[b["id"]] = sorted({a.lower() for a in names if a and len(a) >= 4})
        return idx

    def report(self):
        log(
            "identity: exact=%(exact)d contains=%(contains)d token=%(token)d "
            "ambiguous=%(ambiguous)d miss=%(miss)d" % self.stats
        )
        return dict(self.stats)
