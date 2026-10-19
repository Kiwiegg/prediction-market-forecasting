"""Content-addressed public responses shared by the expanded dataset commands."""

import hashlib
import json
import shutil
import urllib.parse
from pathlib import Path

from investigate_kalshi import BASE, Client

SPORT = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"


def source_id(path, params=None):
    url = path if path.startswith("https://") else BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(sorted(params.items()))
    return hashlib.sha256(url.encode()).hexdigest()


class Sources(Client):
    def __init__(self, output, offline=False, reuse=()):
        super().__init__(Path(output), offline)
        self.reuse = [Path(p) / "raw" for p in reuse]
        self.page_source_ids = {}

    def get(self, path, params=None):
        key = source_id(path, params)
        if not (self.raw / (key + ".json")).exists():
            for folder in self.reuse:
                if (folder / (key + ".json")).exists():
                    for suffix in (".body.gz", ".json"):
                        shutil.copyfile(folder / (key + suffix), self.raw / (key + suffix))
                    break
        return super().get(path, params)

    def provenance(self, key):
        m = json.loads((self.raw / (key + ".json")).read_text())
        return {"source_id": key, "url": m["url"], "http_status": m["status"],
                "retrieved_at_utc": m["attempts"][-1]["finished_at"],
                "response_http_date": m["headers"].get("Date"),
                "body_sha256": m["body_sha256"], "raw_file": "raw/" + key + ".body.gz"}

    def pages(self, path, params, field):
        initial = source_id(path, params)
        rows, seen, sources = [], set(), []
        self.page_source_ids[initial] = sources
        while True:
            sources.append(source_id(path, params))
            result = self.get(path, params)
            if result is None or field not in result:
                return rows, False
            rows.extend(result[field])
            cursor = result.get("cursor")
            if not cursor:
                return rows, True
            if cursor in seen:
                raise RuntimeError(f"Repeated pagination cursor: {path}")
            seen.add(cursor)
            params = dict(params, cursor=cursor)
