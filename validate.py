#!/usr/bin/env python3
"""Validate the timeline dataset.

Three layers, because JSON Schema alone catches only the first:
  1. structural  -- shape of each file against its schema
  2. referential -- every id referenced actually exists
  3. semantic    -- dates parse and order correctly, coverage is consistent

Exit code is non-zero on any error. Warnings do not fail the build.
Usage: python scripts/validate.py [--strict]
"""

import re
import sys
import json
import pathlib
from collections import defaultdict

try:
    import yaml
    from jsonschema import Draft202012Validator, RefResolver
except ImportError:
    sys.exit("Missing deps. Run: pip install pyyaml jsonschema")

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SCHEMA = ROOT / "schema"
EVENTS = DATA / "events"

# Fall back to a flat layout. Copies of this dataset circulate as a single
# directory with no data/schema/scripts split, and the validator refusing to
# start is a worse failure than any it exists to report -- it fails with a
# KeyError on a schema lookup, which reads like a corrupt schema rather than
# a missing directory. Ids are global and filenames are cosmetic by design,
# so both layouts are legitimate.
if not SCHEMA.is_dir():
    ROOT = DATA = SCHEMA = EVENTS = pathlib.Path(__file__).resolve().parent

errors: list[str] = []
warnings: list[str] = []


def load(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def event_files():
    """Event files, identified by content rather than by location.

    Selecting on the top-level `events` key works in both layouts, and keeps
    working when other continuities arrive under their own filename
    conventions -- nothing here should have to learn what `ac-` means.
    """
    found = []
    for path in sorted(EVENTS.glob("*.yaml")):
        doc = load(path)
        if isinstance(doc, dict) and "events" in doc:
            found.append(path)
    return found


def load_schemas():
    store = {}
    for p in SCHEMA.glob("*.schema.json"):
        doc = json.loads(p.read_text(encoding="utf-8"))
        store[p.name] = doc
        if "$id" in doc:
            store[doc["$id"]] = doc
    return store


def validator_for(schema, store):
    resolver = RefResolver(base_uri="", referrer=schema, store=store)
    return Draft202012Validator(schema, resolver=resolver)


# ---------------------------------------------------------------- structural

def check_structure(store):
    entities = store["entities.schema.json"]["$defs"]
    plan = [
        (DATA / "timelines.yaml", entities["timelinesFile"]),
        (DATA / "sources.yaml", entities["sourcesFile"]),
        (DATA / "series.yaml", entities["seriesFile"]),
        (DATA / "factions.yaml", entities["factionsFile"]),
    ]
    for path in event_files():
        plan.append((path, store["events.schema.json"]))

    for path, schema in plan:
        if not path.exists():
            errors.append(f"missing file: {path.relative_to(ROOT)}")
            continue
        v = validator_for(schema, store)
        for err in sorted(v.iter_errors(load(path)), key=lambda e: list(e.path)):
            loc = "/".join(str(p) for p in err.path) or "(root)"
            errors.append(f"{path.relative_to(ROOT)} :: {loc} :: {err.message}")


# --------------------------------------------------------------- referential

def collect():
    reg = defaultdict(set)
    tl = load(DATA / "timelines.yaml")
    for t in tl.get("timelines", []):
        reg["tl"].add(t["id"])
    for s in load(DATA / "sources.yaml").get("sources", []):
        reg["src"].add(s["id"])
    for s in load(DATA / "series.yaml").get("series", []):
        reg["ser"].add(s["id"])
    for f in load(DATA / "factions.yaml").get("factions", []):
        reg["fac"].add(f["id"])
    events = []
    for path in event_files():
        for e in load(path).get("events", []):
            e["_file"] = path.relative_to(ROOT)
            events.append(e)
            reg["evt"].add(e["id"])
    return reg, events, tl


def known(reg, ident):
    return ident in reg.get(ident.split(".")[0], set())


def check_references(reg, events, tl):
    for e in events:
        where = f"{e['_file']} :: {e['id']}"
        for ident in [e.get("timeline")] + e.get("participants", []) \
                + e.get("depicted_in", []) + e.get("referenced_in", []) \
                + e.get("related", []):
            if ident and not known(reg, ident):
                errors.append(f"{where} :: unknown reference {ident}")
        for d in e.get("date", []):
            if not d.get("sources"):
                errors.append(f"{where} :: date claim has no source")
            for s in d.get("sources", []):
                if not known(reg, s):
                    errors.append(f"{where} :: unknown source {s}")
        for c in e.get("claims", []):
            if not c.get("sources"):
                errors.append(f"{where} :: claim '{c.get('property')}' has no source")
            for s in c.get("sources", []):
                if not known(reg, s):
                    errors.append(f"{where} :: unknown source {s}")

    for s in load(DATA / "series.yaml").get("series", []):
        for ident in (s["timeline"], s["source"]):
            if not known(reg, ident):
                errors.append(f"series.yaml :: {s['id']} :: unknown reference {ident}")

    for f in load(DATA / "factions.yaml").get("factions", []):
        for key in ("parent", "predecessor"):
            if f.get(key) and not known(reg, f[key]):
                errors.append(f"factions.yaml :: {f['id']} :: unknown {key} {f[key]}")

    for r in tl.get("relations", []):
        for ident in (r["from"], r["to"]):
            if not known(reg, ident):
                errors.append(f"timelines.yaml :: relation :: unknown timeline {ident}")


# ------------------------------------------------------------------ semantic

def ordinal(literal, upper=False):
    """Convert an era date literal to a (day-ordinal, precision) pair.

    Deliberately uses a flat 360-day civil year: no source specifies a UC
    calendar, so anything more elaborate would be invention. Ordering is
    correct, which is all downstream code needs.
    """
    parts = literal.split(".")
    year = int(parts[0])
    if len(parts) == 1:
        month, day, prec = (12, 30, "year") if upper else (1, 1, "year")
    elif len(parts) == 2:
        month, prec = int(parts[1]), "month"
        day = 30 if upper else 1
    else:
        month, day, prec = int(parts[1]), int(parts[2]), "day"
    return (year - 1) * 360 + (month - 1) * 30 + (day - 1), prec


def check_semantics(events):
    for e in events:
        where = f"{e['_file']} :: {e['id']}"
        for d in e.get("date", []):
            if "start" not in d:
                continue
            lo, prec = ordinal(d["start"])
            if "end" in d:
                hi, _ = ordinal(d["end"], upper=True)
                if hi < lo:
                    errors.append(f"{where} :: end precedes start ({d['start']} > {d['end']})")
            declared = d.get("precision")
            if declared and declared != "range" and declared != prec:
                warnings.append(
                    f"{where} :: declared precision '{declared}' disagrees with "
                    f"literal '{d['start']}' (implies '{prec}')")
            if len(e.get("date", [])) > 1 and "confidence" not in d:
                warnings.append(f"{where} :: competing date claim without confidence")

    for e in events:
        if len(e.get("date", [])) > 1:
            warnings.append(f"{e['_file']} :: {e['id']} :: contested date, {len(e['date'])} claims")


def check_coverage(events):
    """series.covers and event.depicted_in must not disagree.

    Ordinals are era-relative, so CE 0071 and UC 0071 collapse to the same
    integer. Comparing across timelines is not merely unhelpful, it is
    silently wrong: it returns a confident answer about two dates that share
    no epoch. Guard on `timeline` before comparing anything.
    """
    # A series' spans may sit in more than one era, so the envelope is
    # per-timeline rather than one pair of ordinals. Undated spans are
    # recorded as present-but-unplaceable and take part in no comparison.
    spans = {}
    for s in load(DATA / "series.yaml").get("series", []):
        by_tl = {}
        undated = False
        for c in s["covers"]:
            if c.get("undated"):
                undated = True
                continue
            tl_id = c.get("timeline", s["timeline"])
            lo, hi = ordinal(c["start"])[0], ordinal(c["end"], upper=True)[0]
            prev = by_tl.get(tl_id)
            by_tl[tl_id] = (min(lo, prev[0]), max(hi, prev[1])) if prev else (lo, hi)
        spans[s["id"]] = (by_tl, undated, s["title"])

    for e in events:
        for sid in e.get("depicted_in", []):
            if sid not in spans:
                continue
            by_tl, undated, title = spans[sid]
            if undated and not by_tl:
                continue
            envelope = by_tl.get(e.get("timeline"))
            if envelope is None:
                errors.append(
                    f"{e['_file']} :: {e['id']} :: depicted_in {sid}, which has "
                    f"no coverage span in {e.get('timeline')} — add one with an "
                    f"explicit `timeline`, or the comparison is between eras "
                    f"that share no epoch")
                continue
            d = e["date"][0]
            if "start" not in d:
                continue
            lo, hi = envelope
            elo, _ = ordinal(d["start"])
            ehi, _ = ordinal(d.get("end", d["start"]), upper=True)
            if ehi < lo or elo > hi:
                warnings.append(
                    f"{e['_file']} :: {e['id']} :: dated outside the coverage "
                    f"span of {title} — widen series.covers or recheck the date")


def check_entity_spans(events):
    """Faction active spans must agree with the events that name them.

    Three of the eleven date faults found in the 2026-08 UC pass were this
    shape: a faction dissolved before a war it is listed as fighting, or
    beginning before the predecessor it succeeds. Both are mechanical.
    """
    facs = {f["id"]: f for f in load(DATA / "factions.yaml").get("factions", [])}

    for f in facs.values():
        for key in ("predecessor", "parent"):
            other = facs.get(f.get(key))
            if other and other.get("timeline") != f.get("timeline"):
                errors.append(f"factions.yaml :: {f['id']} :: {key} "
                              f"{f[key]} is in another timeline")
        pred = facs.get(f.get("predecessor"))
        if pred and pred.get("timeline") == f.get("timeline"):
            if ordinal(f["active"]["start"])[0] < ordinal(pred["active"]["start"])[0]:
                errors.append(
                    f"factions.yaml :: {f['id']} :: starts before its own "
                    f"predecessor {pred['id']}")

    for e in events:
        d = e["date"][0]
        if "start" not in d:
            continue
        elo, _ = ordinal(d["start"])
        ehi, _ = ordinal(d.get("end", d["start"]), upper=True)
        for fid in e.get("participants", []):
            f = facs.get(fid)
            if not f or f.get("timeline") != e.get("timeline"):
                continue
            flo, _ = ordinal(f["active"]["start"])
            fhi = (ordinal(f["active"]["end"], upper=True)[0]
                   if "end" in f["active"] else None)
            if ehi < flo or (fhi is not None and elo > fhi):
                warnings.append(
                    f"{e['_file']} :: {e['id']} :: participant {fid} is outside "
                    f"its active span — widen the faction or recheck the date")


def check_namespaces(events, tl):
    """Entity ids must be namespaced by the timeline they belong to.

    `fac.efed` cannot be both the UC's Earth Federation and the Advanced
    Generation's. The namespace segment is the timeline's abbrev, lowercased,
    with runs of non-alphanumerics folded to a hyphen — so tl.uc owns `uc.`
    and the GQuuuuuuX branch (UC-G) owns `uc-g.`.
    """
    timelines = {t["id"]: t for t in tl.get("timelines", [])}

    def namespace(tl_id):
        t = timelines.get(tl_id)
        if not t:
            return None
        return re.sub(r"[^a-z0-9]+", "-", t["abbrev"].lower()).strip("-")

    rows = [("series.yaml", s) for s in load(DATA / "series.yaml").get("series", [])]
    rows += [("sources.yaml", s) for s in load(DATA / "sources.yaml").get("sources", [])]
    rows += [("factions.yaml", f) for f in load(DATA / "factions.yaml").get("factions", [])]
    rows += [(str(e["_file"]), e) for e in events]

    for where, ent in rows:
        ns = namespace(ent.get("timeline"))
        if ns is None:
            continue
        parts = ent["id"].split(".")
        if len(parts) < 3 or parts[1] != ns:
            errors.append(
                f"{where} :: {ent['id']} :: id should be namespaced "
                f"'{parts[0]}.{ns}.…' for timeline {ent['timeline']}")


def main():
    strict = "--strict" in sys.argv
    store = load_schemas()

    check_structure(store)
    if errors:
        # Stop here. Every later layer assumes the shapes the schema
        # guarantees -- check_coverage reads c["start"] because the schema
        # promised it exists. Running them over structurally invalid data
        # raises a KeyError partway through, and because errors are printed
        # at the end, the traceback replaces the report instead of
        # accompanying it: the structural error IS found and then never
        # shown. Found by negative-testing the coverage schema, which is the
        # argument for negative-testing validators at all.
        return report(strict)

    reg, events, tl = collect()
    check_references(reg, events, tl)
    check_semantics(events)
    check_coverage(events)
    check_entity_spans(events)
    check_namespaces(events, tl)
    return report(strict, events, reg)


def report(strict, events=None, reg=None):
    for w in warnings:
        print(f"WARN  {w}")
    for err in errors:
        print(f"ERROR {err}")

    if events is not None:
        # Undated and relatively-dated events are reported as a count rather
        # than as warnings. They are intended data, not defects, but a dataset
        # that silently contains unplaceable events is one nobody checks.
        unplaced = sum(1 for e in events if not any("start" in d for d in e["date"]))
        anchored = sum(1 for e in events
                       if any("anchor" in d for d in e["date"])
                       and not any("start" in d for d in e["date"]))

        print(f"\n{len(events)} events, {len(reg['ser'])} series, "
              f"{len(reg['src'])} sources, {len(reg['fac'])} factions, "
              f"{len(reg['tl'])} timelines")
        print(f"{unplaced} events carry no absolute date "
              f"({anchored} ordered by anchor, {unplaced - anchored} fully undated)")
    else:
        print("\nstructural errors — later checks skipped")

    print(f"{len(errors)} errors, {len(warnings)} warnings")

    if errors or (strict and warnings):
        sys.exit(1)


if __name__ == "__main__":
    main()
