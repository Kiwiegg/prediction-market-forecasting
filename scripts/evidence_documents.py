"""Immutable, hashed document captures. Historical retrieval uses an explicit allowlist."""

import gzip
import hashlib
import json
import time
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from investigate_kalshi import iso


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


class DocumentStore:
    def __init__(self, folder, offline=True, allowed_url=None):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        self.allowed_url = allowed_url or (lambda url: False)
        self._locks = {}
        self._guard = threading.Lock()

    def get(self, url):
        with self._guard:
            lock = self._locks.setdefault(url, threading.Lock())
        with lock:
            return self._get(url)

    def _get(self, url):
        if not self.allowed_url(url):
            raise ValueError("Document URL is outside the approved source policy")
        key = digest(url.encode())
        meta_file = self.folder / (key + ".json")
        body_file = self.folder / (key + ".body.gz")
        if meta_file.exists():
            meta = json.loads(meta_file.read_text())
            body = gzip.decompress(body_file.read_bytes())
            if meta["url"] != url or digest(body) != meta["body_sha256"]:
                raise ValueError("Document capture hash mismatch")
            return meta, body
        if self.offline:
            raise RuntimeError("Missing offline document capture: " + url)
        attempts = []
        for attempt in range(3):
            started = iso(time.time())
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "nba-evidence-research/1.0"})
                # Refuse redirects rather than follow an unapproved historical source.
                class NoRedirect(urllib.request.HTTPRedirectHandler):
                    def redirect_request(self, req, fp, code, msg, headers, newurl):
                        return None
                with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
                    body, status = response.read(5_000_001), response.status
                    headers = dict(response.headers.items())
            except urllib.error.HTTPError as exc:
                body, status, headers = exc.read(5_000_001), exc.code, dict(exc.headers.items())
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                body, status, headers = str(exc).encode(), 0, {}
            attempts.append({"started_at_utc": started, "finished_at_utc": iso(time.time()), "http_status": status})
            if status not in (0, 429, 500, 502, 503, 504) or attempt == 2:
                break
            time.sleep(2 ** attempt)
        meta = {"source_id": key, "url": url, "http_status": status,
                "retrieved_at_utc": attempts[-1]["finished_at_utc"], "attempts": attempts,
                "headers": {k.lower(): v for k, v in headers.items()}, "body_sha256": digest(body),
                "body_size": len(body), "truncated": len(body) > 5_000_000}
        body_file.write_bytes(gzip.compress(body, mtime=0))
        meta_file.write_text(json.dumps(meta, sort_keys=True, indent=2) + "\n")
        print(f"DOCUMENT {status} {url}", flush=True)
        return meta, body
