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


# A containing alias must account for at least this share of the candidate name,
# so a 6-character brand cannot claim a 40-character unrelated company.
CONTAINS_MIN_RATIO = 0.55


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _whole_word_in(needle, haystack):
    """True if `needle` occurs in `haystack` on word boundaries.

    Plain `in` matched "arihant" inside "ARIHANT ACADEMY" (fine) but equally
    inside any longer word, and matched brand words like "choice" or "ventura"
    inside unrelated prose. Both strings are already normalised to lowercase
    words separated by single spaces, so boundary checking is a token-window
    comparison rather than a regex.
    """
    if not needle or not haystack:
        return False
    n_tokens, h_tokens = needle.split(), haystack.split()
    if not n_tokens or len(n_tokens) > len(h_tokens):
        return False
    for i in range(len(h_tokens) - len(n_tokens) + 1):
        if h_tokens[i:i + len(n_tokens)] == n_tokens:
            return True
    return False


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

    def resolve(self, raw_name, threshold=0.62, margin=0.12, strict=False):
        """Return (broker_id, method, score) or (None, reason, score).

        `strict=True` refuses everything except an exact normalised match. Use it
        for any ADVERSE attribution (defaulter list, disciplinary circulars):
        wrongly telling readers that a named, regulated firm is a defaulter is
        not a data-quality issue, it is a defamation exposure, and the cost of a
        miss is only a gap.
        """
        n = norm(raw_name)
        if not n:
            return None, "empty", 0.0

        if n in self.exact:
            self.stats["exact"] += 1
            return self.exact[n], "exact", 1.0

        if strict:
            self.stats["miss"] += 1
            return None, "strict_no_exact_match", 0.0

        # Containment: registry names are usually the brand plus a corporate
        # suffix. This must be WHOLE-WORD. A bare substring test resolved
        # "ARIHANT ACADEMY LIMITED" to the broker Arihant and "VENTURA TEXTILES"
        # to Ventura, at 0.9 confidence, because it matched inside unrelated
        # company names. It must also be unambiguous AND carry enough of the
        # candidate name to be meaningful.
        hits = set()
        for alias, bid in self.exact.items():
            if len(alias) < 5:
                continue
            if _whole_word_in(alias, n) or _whole_word_in(n, alias):
                hits.add(bid)
        if len(hits) == 1:
            bid = next(iter(hits))
            # Guard against a short alias swallowing a long unrelated name:
            # require the alias to account for a real share of the candidate.
            longer, shorter = max(len(n), 1), 0
            for alias, abid in self.exact.items():
                if abid == bid and (_whole_word_in(alias, n) or _whole_word_in(n, alias)):
                    shorter = max(shorter, len(alias))
            if shorter / longer >= CONTAINS_MIN_RATIO:
                self.stats["contains"] += 1
                return bid, "contains", 0.9
            self.stats["ambiguous"] += 1
            return None, "contains_too_weak", round(shorter / longer, 3)

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
