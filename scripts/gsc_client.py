#!/usr/bin/env python3
"""Minimal Google Search Console API client.

Uses only the Python stdlib plus the system `openssl` binary for RS256 JWT
signing - no google-auth/google-api-python-client. Matches this project's
existing policy of zero pip dependencies for anything that runs as part of
the site pipeline (see scripts/vercel-build.sh); this script is a separate,
standalone tool, not part of that build.

Usage:
    python3 scripts/gsc_client.py sites
    python3 scripts/gsc_client.py performance <site-url> [days]
    python3 scripts/gsc_client.py sitemaps <site-url>
    python3 scripts/gsc_client.py inspect <site-url> <page-url>
"""
from __future__ import annotations

import base64
import datetime
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://oauth2.googleapis.com/token"
API_ROOT = "https://www.googleapis.com/webmasters/v3"
INSPECTION_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"

KEY_PATH = os.path.join(os.path.dirname(__file__), "..", "secrets", "gsc-service-account.json")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _sign_rs256(message: bytes, private_key_pem: str) -> bytes:
    # openssl needs the key as a file, not stdin alongside the message - write
    # it to a private temp file for the instant of signing, then remove it.
    fd, key_path = tempfile.mkstemp(suffix=".pem")
    try:
        os.write(fd, private_key_pem.encode())
        os.close(fd)
        os.chmod(key_path, 0o600)
        proc = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", key_path],
            input=message, capture_output=True, check=True,
        )
        return proc.stdout
    finally:
        os.unlink(key_path)


def _load_service_account():
    # CI (GitHub Actions) injects the key as an env var from a repo secret -
    # nothing under secrets/ ever leaves this machine or reaches git either
    # way, this just avoids requiring a checked-out file that can't exist in
    # a fresh CI runner.
    raw = os.environ.get("GSC_SERVICE_ACCOUNT_JSON")
    if raw:
        return json.loads(raw)
    with open(KEY_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_access_token(scope: str = SCOPE) -> str:
    sa = _load_service_account()
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": sa["client_email"],
        "scope": scope,
        "aud": TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }
    signing_input = "%s.%s" % (
        _b64url(json.dumps(header, separators=(",", ":")).encode()),
        _b64url(json.dumps(claims, separators=(",", ":")).encode()),
    )
    signature = _sign_rs256(signing_input.encode(), sa["private_key"])
    assertion = "%s.%s" % (signing_input, _b64url(signature))

    data = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion,
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)["access_token"]
    except urllib.error.HTTPError as e:
        raise SystemExit("Token request failed: %s %s" % (e.code, e.read().decode()))
    except (urllib.error.URLError, TimeoutError) as e:
        raise SystemExit("Token request timed out or unreachable: %s" % e)


def _api(url: str, token: str, method: str = "GET", body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer %s" % token,
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise SystemExit("API call failed: %s %s\n%s" % (e.code, url, e.read().decode()))
    except (urllib.error.URLError, TimeoutError) as e:
        raise SystemExit("API call timed out or unreachable: %s %s" % (url, e))


def cmd_sites(token: str):
    print(json.dumps(_api("%s/sites" % API_ROOT, token), indent=2))


def cmd_sitemaps(token: str, site_url: str):
    encoded = urllib.parse.quote(site_url, safe="")
    print(json.dumps(_api("%s/sites/%s/sitemaps" % (API_ROOT, encoded), token), indent=2))


def cmd_performance(token: str, site_url: str, days: int = 28):
    encoded = urllib.parse.quote(site_url, safe="")
    end = datetime.date.today() - datetime.timedelta(days=3)  # GSC data lags ~2-3 days
    start = end - datetime.timedelta(days=days)
    body = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": ["query"],
        "rowLimit": 25,
    }
    result = _api("%s/sites/%s/searchAnalytics/query" % (API_ROOT, encoded), token, "POST", body)
    print(json.dumps(result, indent=2))


def cmd_inspect(token: str, site_url: str, page_url: str):
    body = {"inspectionUrl": page_url, "siteUrl": site_url}
    print(json.dumps(_api(INSPECTION_URL, token, "POST", body), indent=2))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    cmd = sys.argv[1]
    token = get_access_token()
    if cmd == "sites":
        cmd_sites(token)
    elif cmd == "sitemaps":
        cmd_sitemaps(token, sys.argv[2])
    elif cmd == "performance":
        days = int(sys.argv[3]) if len(sys.argv) > 3 else 28
        cmd_performance(token, sys.argv[2], days)
    elif cmd == "inspect":
        cmd_inspect(token, sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
