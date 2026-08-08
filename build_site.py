#!/usr/bin/env python3
"""Build a single self-contained HTML page from the timeline dataset.

    python build_site.py            # writes site/index.html

No server, no build toolchain, no runtime dependencies. The YAML is read
once here and embedded as JSON, so the output opens straight off the
filesystem. `pip install pyyaml` is the whole install step.

The render obeys the dataset's own rules, which are not decoration:

  * One axis per continuity, never a shared one. Ordinals are era-relative,
    so CE 0071 and UC 0071 are the same integer and different moments.
  * Undated events are drawn OFF the axis, in their own tray. Placing them
    at the origin would assert that Gunpla battles happen at UC 0001.
  * `main` coverage spans are solid; prologue/flashback/epilogue are
    hairline, so one prologue scene cannot draw Unicorn as a 95-year bar.
  * `editorial` and `needs-verification` are visually distinct from sourced
    fact everywhere they appear. The moment a guess renders like a citation
    the dataset stops being worth having.
"""

import io
import json
import pathlib
import re
import sys
import urllib.parse

try:
    import yaml
except ImportError:
    sys.exit("Missing deps. Run: pip install pyyaml")

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
EVENTS = DATA / "events"
OUT = ROOT / "site"
if not DATA.is_dir():                      # flat layout, same fallback as validate.py
    ROOT = DATA = EVENTS = pathlib.Path(__file__).resolve().parent
    OUT = ROOT / "site"

WIKI = "https://gundam.fandom.com/wiki/Special:Search?search={}&fulltext=0"


def load(p):
    with open(p, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def event_files():
    return [p for p in sorted(EVENTS.glob("*.yaml"))
            if isinstance(load(p), dict) and "events" in load(p)]


def ordinal(literal, upper=False):
    """Era date -> day ordinal. Flat 360-day year, as in validate.py.

    Era-relative by construction: only ever compare two ordinals from the
    same timeline.
    """
    parts = str(literal).split(".")
    year = int(parts[0])
    if len(parts) == 1:
        month, day = (12, 30) if upper else (1, 1)
    elif len(parts) == 2:
        month, day = int(parts[1]), (30 if upper else 1)
    else:
        month, day = int(parts[1]), int(parts[2])
    return (year - 1) * 360 + (month - 1) * 30 + (day - 1)


def wiki(term):
    return WIKI.format(urllib.parse.quote_plus(str(term)))


# `certain` and `approximate` are ordinary sourced states and get no chip.
# The rest are the ones the README insists must never look like citations.
FLAGS = {
    "editorial":          ("guess", "an inference by this project, not a claim by any source"),
    "needs-verification": ("unchecked", "entered but not yet checked against the work"),
    "disputed":           ("contested", "sources actively conflict"),
    "interpretive":       ("reading", "a widely-held reading, not an explicit statement"),
    "inherited":          ("inherited", "taken from a parent timeline"),
}


def flag(conf):
    return FLAGS.get(conf, (None, None))[0]


def build():
    timelines = load(DATA / "timelines.yaml")
    sources = {s["id"]: s for s in load(DATA / "sources.yaml")["sources"]}
    series = load(DATA / "series.yaml")["series"]
    factions = load(DATA / "factions.yaml")["factions"]

    events = []
    for path in event_files():
        for e in load(path)["events"]:
            e["_file"] = path.name
            events.append(e)

    tl_meta = {t["id"]: t for t in timelines["timelines"]}
    rels = [{k: v for k, v in r.items() if k != "note"}
            for r in timelines.get("relations", [])]
    out = {"timelines": [], "relations": rels,
           "totals": {"events": len(events), "series": len(series),
                      "sources": len(sources), "factions": len(factions),
                      "timelines": len(tl_meta)}}

    for tid, t in tl_meta.items():
        # Series spans are collected by the span's OWN timeline, so a work
        # whose flashbacks sit in a predecessor era appears on that era's
        # chart too. This is the only reason coverageSpan carries `timeline`.
        rows = []
        for s in series:
            spans = [c for c in s["covers"] if c.get("timeline", s["timeline"]) == tid]
            if not spans:
                continue
            rows.append({
                "id": s["id"], "title": s["title"], "home": s["timeline"],
                "foreign": s["timeline"] != tid,
                "release": s.get("release_year"), "format": s.get("format"),
                "focus": s.get("focus", ""),
                "source": s.get("source"),
                "wiki": wiki(s["title"]),
                "spans": [{
                    "lo": None if c.get("undated") else ordinal(c["start"]),
                    "hi": None if c.get("undated") else ordinal(c["end"], upper=True),
                    "start": c.get("start"), "end": c.get("end"),
                    "undated": bool(c.get("undated")),
                    "weight": c.get("weight", "main"),
                    "flag": flag(c.get("confidence")),
                } for c in spans],
            })

        facs = []
        for f in factions:
            if f.get("timeline") != tid:
                continue
            a = f["active"]
            facs.append({
                "id": f["id"], "name": f["name"], "abbrev": f.get("abbrev", ""),
                "lo": ordinal(a["start"]), "hi": ordinal(a["end"], upper=True) if "end" in a else None,
                "start": a["start"], "end": a.get("end"),
                "flag": flag(a.get("confidence")),
                "predecessor": f.get("predecessor"), "parent": f.get("parent"),
                "wiki": wiki(f["name"]),
            })

        evs = []
        for e in events:
            if e.get("timeline") != tid:
                continue
            d = e["date"][0]
            dated = "start" in d
            evs.append({
                "id": e["id"], "label": e["label"], "type": e.get("type", "—"),
                "lo": ordinal(d["start"]) if dated else None,
                "hi": ordinal(d.get("end", d["start"]), upper=True) if dated else None,
                "start": d.get("start"), "end": d.get("end"),
                "undated": bool(d.get("undated")),
                "anchor": d.get("anchor"),
                "contested": len(e["date"]) > 1,
                "flag": flag(d.get("confidence")),
                "summary": e.get("summary", "").strip(),
                "participants": e.get("participants", []),
                "depicted_in": e.get("depicted_in", []),
                "referenced_in": e.get("referenced_in", []),
                "related": e.get("related", []),
                "sources": sorted({s for dd in e["date"] for s in dd.get("sources", [])}),
                "claims": [{
                    "property": c["property"], "value": c["value"].strip(),
                    "sources": c.get("sources", []), "flag": flag(c.get("confidence")),
                    "resolution": c.get("resolution"),
                } for c in e.get("claims", [])],
                "wiki": wiki(e["label"]),
            })
        evs.sort(key=lambda x: (x["lo"] is None, x["lo"] or 0, x["label"]))

        # Only events and coverage spans may bring an axis into existence.
        # Factions must not: in a continuity with no calendar their `active`
        # start is "0001" because faction.active has no `undated` escape and
        # that is the one literal satisfying the pattern without asserting
        # anything. Letting it create an axis would draw SD Gundam a
        # chronology out of a schema artefact.
        dated = [x for x in evs if x["lo"] is not None]
        bounds = [x["lo"] for x in dated] + [x["hi"] for x in dated]
        for r in rows:
            bounds += [sp["lo"] for sp in r["spans"] if sp["lo"] is not None]
            bounds += [sp["hi"] for sp in r["spans"] if sp["hi"] is not None]
        if bounds:
            for f in facs:
                bounds += [f["lo"]] + ([f["hi"]] if f["hi"] is not None else [])

        out["timelines"].append({
            "id": tid, "name": t["name"], "abbrev": t["abbrev"],
            "status": t.get("status", "primary"),
            "blurb": (t.get("blurb") or "").strip(),
            # `note` is deliberately not emitted anywhere in this file. Those
            # are working notes about how the collection is built, and the
            # people reading the page came for Gundam.
            "epoch": {k: v for k, v in t.get("epoch", {}).items() if k != "note"},
            "span": t.get("span", {}),
            "series": rows, "factions": facs, "events": evs,
            "lo": min(bounds) if bounds else None,
            "hi": max(bounds) if bounds else None,
        })

    out["sources"] = {sid: {"title": s["title"], "kind": s["kind"],
                            "year": s.get("year"), "tier": s["tier"],
                            "timeline": s["timeline"],
                            "flag": flag(s.get("confidence")),
                            "wiki": wiki(s["title"])}
                      for sid, s in sources.items()}
    out["labels"] = {}
    for t in out["timelines"]:
        for f in t["factions"]:
            out["labels"][f["id"]] = f["name"]
        for s in t["series"]:
            out["labels"][s["id"]] = s["title"]
        for e in t["events"]:
            out["labels"][e["id"]] = e["label"]
    out["flagHelp"] = {v[0]: v[1] for v in FLAGS.values()}
    return out


def render(data):
    here = pathlib.Path(__file__).resolve().parent
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    tpl = (here / "site_template.html").read_text(encoding="utf-8")
    # Display face is embedded rather than linked: an artifact CSP blocks font
    # CDNs outright, and a silent fallback would drop the page's only
    # typographic voice without any error to notice.
    fonts = json.loads((here / "fonts_b64.json").read_text(encoding="utf-8"))
    return (tpl.replace("__FONT_DISPLAY__", fonts["display"])
               .replace("/*__DATA__*/null", payload))


def fragment(html):
    """The same page without the document shell.

    Hosts that wrap content in their own <!doctype>/<head>/<body> (the
    Artifact publisher, most CMSes) reject a nested full document. Derived
    from the same template rather than maintained separately, so the two can
    never drift.
    """
    title = re.search(r"<title>.*?</title>", html, re.S).group(0)
    style = re.search(r"<style>.*?</style>", html, re.S).group(0)
    body = re.search(r"<body>(.*)</body>", html, re.S).group(1)
    return f"{title}\n{style}\n{body.strip()}\n"


if __name__ == "__main__":
    data = build()
    OUT.mkdir(exist_ok=True)
    html = render(data)
    (OUT / "index.html").write_text(html, encoding="utf-8")
    (OUT / "artifact.html").write_text(fragment(html), encoding="utf-8")
    t = data["totals"]
    print(f"site/index.html     {len(html)/1024:.0f} KB   (open this one)")
    print(f"site/artifact.html  {len(fragment(html))/1024:.0f} KB   (no document shell, for embedding)")
    print(f"{t['events']} events, {t['series']} series, {t['sources']} sources, "
          f"{t['factions']} factions, {t['timelines']} timelines")
