#!/usr/bin/env python3
"""Resolve Gundam Wiki links, and record only the ones that actually exist.

    python resolve_wiki.py            # writes `wiki:` back into the YAML
    python resolve_wiki.py --check    # re-verify what is recorded, change nothing

Every event, work, source and faction gets a link. A search URL always
resolves to something, which is exactly why it is the wrong default: it
looks like a working link and lands the reader on a result list.

So each name is resolved against the wiki's own API:

  1. Ask for the exact title, following redirects. If the page exists, use
     the canonical title it redirects to.
  2. If it does not exist, take the top search hit -- but only accept it if
     it is close enough to the name asked for. A confident wrong article is
     worse than a search page.
  3. Otherwise record nothing, and the page falls back to search.

Re-runnable. Titles move, and a link that rotted should be found by a check
rather than by a reader.
"""

import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

try:
    import yaml
except ImportError:
    sys.exit("Missing deps. Run: pip install pyyaml")

API = "https://gundam.fandom.com/api.php"
PAGE = "https://gundam.fandom.com/wiki/"
UA = "gundam-timeline-linkcheck/1.0 (+https://github.com/ssegota/gundam-timeline)"
HERE = pathlib.Path(__file__).resolve().parent


def api(**params):
    params.setdefault("format", "json")
    params["action"] = "query"
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))


def norm(s):
    return re.sub(r"[^a-z0-9 ]", " ", s.lower()).split()


def close_enough(asked, got):
    """Is the top search hit really the article for this name?

    Substring either way, or a strong token overlap. Loose enough to accept
    "Battle of Loum" for "Battle of Loum (event)", tight enough to reject a
    hit that merely mentions the words.
    """
    a, g = norm(asked), norm(got)
    if not a or not g:
        return False
    sa, sg = " ".join(a), " ".join(g)
    if sa in sg or sg in sa:
        return True
    inter = len(set(a) & set(g))
    return inter / max(len(set(a)), len(set(g))) >= 0.6


def resolve(names):
    """name -> canonical article title, or None."""
    out = {}
    todo = list(names)
    for i in range(0, len(todo), 40):                     # exact titles, batched
        batch = todo[i:i + 40]
        d = api(titles="|".join(batch), redirects=1)
        q = d.get("query", {})
        canon = {r["from"]: r["to"] for r in q.get("redirects", [])}
        norm_map = {r["from"]: r["to"] for r in q.get("normalized", [])}
        present = {p["title"] for p in q.get("pages", {}).values() if "missing" not in p}
        for name in batch:
            t = norm_map.get(name, name)
            t = canon.get(t, t)
            if t in present:
                out[name] = t
        time.sleep(0.4)

    missing = [n for n in todo if n not in out]
    for n in missing:                                     # search, one at a time
        try:
            d = api(list="search", srsearch=n, srlimit=1)
            hits = d.get("query", {}).get("search", [])
        except Exception:
            hits = []
        if hits and close_enough(n, hits[0]["title"]):
            out[n] = hits[0]["title"]
        time.sleep(0.4)
    return out


def url_for(title):
    return PAGE + urllib.parse.quote(title.replace(" ", "_"), safe="/:()!,'&-")


# ----------------------------------------------------------------- gather

FIELDS = {"evt": "label", "ser": "title", "src": "title", "fac": "name"}


def entities():
    """(file, line index of the id, prefix, display name) for everything linkable."""
    found = []
    for path in sorted(HERE.glob("*.yaml")):
        lines = path.read_text(encoding="utf-8").split("\n")
        for i, ln in enumerate(lines):
            m = re.match(r"^  - id: ((evt|ser|src|fac)\.[\w.\-]+)\s*$", ln)
            if not m:
                continue
            pref = m.group(2)
            key = FIELDS[pref]
            for j in range(i + 1, min(i + 6, len(lines))):
                mm = re.match(rf"^    {key}: (.*)$", lines[j])
                if mm:
                    name = mm.group(1).strip()
                    if name[:1] in "\"'" and name[-1:] == name[:1]:
                        name = name[1:-1]
                    found.append((path, i, m.group(1), name))
                    break
    return found


def main():
    check = "--check" in sys.argv
    ents = entities()
    names = sorted({n for _, _, _, n in ents})
    print(f"{len(ents)} linkable entries, {len(names)} distinct names")

    resolved = resolve(names)
    print(f"resolved to a real article: {len(resolved)}/{len(names)}")

    if check:
        bad = [n for n in names if n not in resolved]
        print("no article (search fallback):")
        for n in bad:
            print("   ", n)
        return

    by_file = {}
    for path, idx, _id, name in ents:
        by_file.setdefault(path, []).append((idx, name))

    written = 0
    for path, items in by_file.items():
        lines = path.read_text(encoding="utf-8").split("\n")
        lines = [l for l in lines if not re.match(r"^    wiki: ", l)]   # idempotent
        # recompute indices after the strip
        fresh = []
        for i, ln in enumerate(lines):
            m = re.match(r"^  - id: ((evt|ser|src|fac)\.[\w.\-]+)\s*$", ln)
            if m:
                pref = m.group(2)
                key = FIELDS[pref]
                for j in range(i + 1, min(i + 6, len(lines))):
                    mm = re.match(rf"^    {key}: (.*)$", lines[j])
                    if mm:
                        nm = mm.group(1).strip()
                        if nm[:1] in "\"'" and nm[-1:] == nm[:1]:
                            nm = nm[1:-1]
                        fresh.append((i, nm))
                        break
        for i, nm in reversed(fresh):
            t = resolved.get(nm)
            if t:
                lines.insert(i + 1, f"    wiki: {json.dumps(url_for(t))}")
                written += 1
        path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {written} verified links")


main()
