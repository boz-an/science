"""Small HTTP layer: timeouts, retries, a private disk cache, key redaction.

Standard library only. API keys never appear in error messages, and cache
file names are hashes, so a key that is part of a URL is never written to
disk in plain text.
"""

import hashlib
import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_UA = "Mozilla/5.0 (compatible; finance-desk/0.1)"
SECRET_PARAMS = {"apikey", "api_key", "token", "key", "secret"}


class DataError(Exception):
    """Raised when data cannot be fetched or parsed. Never swallowed silently."""


def cache_dir():
    base = os.environ.get("FINDESK_CACHE")
    if not base:
        root = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
        base = os.path.join(root, "finance-desk")
    return base


def caching_enabled():
    return os.environ.get("FINDESK_NO_CACHE") != "1"


def redact(url):
    """Return the URL with secret query parameters masked."""
    parts = urllib.parse.urlsplit(url)
    query = [
        (k, "***" if k.lower() in SECRET_PARAMS else v)
        for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), ""))


def _cache_path(url):
    return os.path.join(cache_dir(), hashlib.sha256(url.encode("utf-8")).hexdigest())


def _cache_read(url, ttl):
    if not ttl or not caching_enabled():
        return None
    path = _cache_path(url)
    try:
        if time.time() - os.stat(path).st_mtime < ttl:
            with open(path, "rb") as fh:
                return fh.read()
    except OSError:
        pass
    return None


def _cache_write(url, data):
    if not caching_enabled():
        return
    d = cache_dir()
    try:
        os.makedirs(d, mode=0o700, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, 0o600)
        os.replace(tmp, _cache_path(url))
    except OSError:
        pass  # a cache failure must never break a lookup


def fetch(url, headers=None, ttl=0, timeout=20, retries=2):
    """GET a URL and return bytes. Raises DataError on failure."""
    cached = _cache_read(url, ttl)
    if cached is not None:
        return cached
    hdrs = {"User-Agent": DEFAULT_UA, "Accept": "*/*"}
    if headers:
        hdrs.update(headers)
    last_error = "unknown error"
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            if ttl:
                _cache_write(url, data)
            return data
        except urllib.error.HTTPError as exc:
            last_error = "HTTP %s from %s" % (exc.code, redact(url))
            if exc.code in (400, 401, 403, 404, 422):
                break  # retrying will not help
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = "network error for %s: %s" % (redact(url), getattr(exc, "reason", exc))
        if attempt < retries:
            time.sleep(0.75 * (attempt + 1))
    raise DataError(last_error)


def fetch_json(url, headers=None, ttl=0, timeout=20):
    raw = fetch(url, headers=headers, ttl=ttl, timeout=timeout)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DataError("invalid JSON from %s: %s" % (redact(url), exc))
