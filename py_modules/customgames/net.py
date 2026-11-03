"""HTTP with retries for Decky's bundled Python (which may not find the system CA store by itself)."""

import json
import os
import shutil
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

UA = "decky-custom-games/0.1 (Steam Deck plugin; +https://github.com)"
_ctx: Optional[ssl.SSLContext] = None


def _ssl() -> ssl.SSLContext:
    global _ctx
    if _ctx is None:
        _ctx = ssl.create_default_context()
        for cafile in ("/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt", "/etc/ssl/cert.pem"):
            if os.path.isfile(cafile):
                try:
                    _ctx.load_verify_locations(cafile)
                except ssl.SSLError:
                    pass
                break
    return _ctx


class NetError(Exception):
    pass


def get(url: str, headers: Optional[dict] = None, timeout: int = 30, tries: int = 3) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_ssl()) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403, 404) or attempt == tries - 1:
                raise NetError(f"HTTP {e.code}: {url.split('?')[0]}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            if attempt == tries - 1:
                raise NetError(f"{e}: {url.split('?')[0]}") from e
        time.sleep(1.5 * (attempt + 1))
    raise NetError(url)


def get_json(url: str, params: Optional[dict] = None, headers: Optional[dict] = None, timeout: int = 30):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, safe=",/")
    body = get(url, headers, timeout)
    if not body.strip():  # seen during SteamGridDB outages: HTTP 200 with an empty body
        raise NetError(f"empty response: {url.split('?')[0]}")
    return json.loads(body)


def download(url: str, dest: str, timeout: int = 120) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    tmp = dest + ".part"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_ssl()) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            os.replace(tmp, dest)
            return dest
        except urllib.error.HTTPError as e:
            if e.code in (403, 404) or attempt == 2:
                raise NetError(f"HTTP {e.code}: {url.split('?')[0]}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            if attempt == 2:
                raise NetError(f"{e}: {url.split('?')[0]}") from e
        time.sleep(2 * (attempt + 1))
    raise NetError(url)
