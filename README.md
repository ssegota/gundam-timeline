# Gundam Timeline Dataset

A source-attributed, machine-readable chronology of the Gundam
continuities, built to be rendered graphically.

The hard part of this project is not volume. It is that the canon
contradicts itself, the dates are frequently imprecise, and works released
decades apart describe the same events differently. This dataset is
structured around that fact rather than in spite of it.

**Status:** 100 events across 44 series in 19 continuities — every Gundam
continuity that has one, plus three declared as stubs. The UC spine is
verified against reference compilations (eleven dates were wrong);
everything added in the 2026-08 expansion is seeded at main-spine depth and
is not verified at all. See [Verification](#verification).

---

## Design principles

### 1. Record claims, not facts

The naive schema is `event.date = "0079.09.18"`. It breaks the first time a
later work contradicts an earlier one, because the only way to record the
new value is to destroy the old one.

Instead, every assertion is attributed:

```yaml
claims:
  - property: cause_of_death
    value: Sudden death, cause not established in the text
    sources: [src.uc.msg-tv]
  - property: cause_of_death
    value: Assassination, attributed to the Zabi family
    sources: [src.uc.origin]
```

"What killed Zeon Zum Deikun" then becomes a query with a resolution
policy, rather than a column somebody has to keep editing. The contradiction
is data. You can render it.

This costs verbosity on the ~85% of entries where nothing is in dispute.
That trade is worth making, because you cannot predict in advance which
entries will turn out to be contested, and retrofitting attribution onto a
flat table means re-reading every source.

### 2. Dates are ranges with precision, never timestamps

Sources give you precise dates (`0079.01.03`), year-only (`0087`), vague
brackets (*the late 0080s*), and relative anchors (*ten years after*). All
four must round-trip.

Dates are authored as strings where **the literal carries its own
precision**:

| Literal      | Precision | Resolves to          |
|--------------|-----------|----------------------|
| `0079`       | year      | first–last day of 0079 |
| `0079.09`    | month     | first–last day of 0079.09 |
| `0079.09.18` | day       | that day             |

Ingest converts each literal to a `(min, max)` day-ordinal pair relative to
the era epoch. All sorting, overlap, and containment logic downstream is
integer comparison; the render layer converts back for display.

The ordinal uses a flat 360-day civil year. No source specifies a UC
calendar, so anything more elaborate would be invention. Ordering is
correct, which is all the queries need.

Relative dating is first-class:

```yaml
- anchor:
    relative_to: evt.uc.0123.cosmo-babylonia-war
    offset_years: 10
    direction: after
  sources: [src.uc.crossbone]
```

And so is having no date at all:

```yaml
- undated: true
  sources: [src.build.gunpla-builders]
```

`undated` is a **third state**, not a missing value. It means the source
establishes that something happened and supplies neither a date nor an
ordering hook. It is distinct from an absent date claim (nobody has entered
one yet) and from an imprecise one (a year with no month). It exists
because the Build continuity has no calendar — not a vague one, none — and
the SD Gundam settings have no chronology of any kind. For those,
inventing an era to satisfy the schema would be precisely the fabrication
this project exists to avoid.

12 of 100 events carry no absolute date: 5 ordered by anchor, 7 fully
undated. `validate.py` prints that split on every run, because a dataset
that silently contains unplaceable events is one nobody remembers to check.
**Consumers must not sort on these.** Placing an undated event at the
origin of a shared axis asserts that Gunpla battles happen at UC 0001.

### 3. Series are entities, not tags

You asked for this specifically and it changes the schema more than it
looks like it should.

A series has a **list** of coverage spans, not one range:

```yaml
covers:
  - start: "0001.01.31"
    end: "0001.01.31"
    weight: prologue
  - start: "0096.03"
    end: "0096.04"
    weight: main
```

That is Unicorn. A single start/end pair would draw it as a 95-year bar
because of one prologue scene. Weights are `main`, `prologue`, `flashback`,
`epilogue`; renderers should draw `main` solid and the rest hairline.

The `release_year` field is real-world while `covers` is in-universe.
Keeping both is what makes retcon direction visible — a 2010 work covering
UC 0001 is exactly where contradictions live.

A span may also carry its own `timeline`, when the work crosses an era
boundary:

```yaml
covers:
  - start: "0022"          # Mars Century — the series' home era
    end: "0022"
    weight: main
  - start: "0195"          # After Colony — its predecessor
    end: "0196"
    timeline: tl.ac
    weight: flashback
```

That is Frozen Teardrop, whose present is Mars Century and whose flashbacks
are After Colony. Without a per-span timeline the only options were to drop
the flashbacks or move the whole work into AC — the first loses half the
book, the second files a Mars Century work under the wrong era on every
render. The series' own `timeline` remains its home era and governs its id
namespace; a span's timeline governs only where that span is drawn.

Spans can be `undated: true` as well, for the same reason date claims can.

### 4. Depiction is not the same as reference

`depicted_in` means the series dramatises the event. `referenced_in` means
it establishes the event as backstory through dialogue or narration.

This distinction was not in the original design. It came out of the
validator: four events were flagged as dated outside the coverage span of a
series that listed them. The instinct is to widen the span, which would
have made Zeta Gundam render as starting in UC 0083 — visibly wrong. The
warning was correct and the model was wrong.

Only `depicted_in` is subject to the coverage check.

### 5. Timelines have edges

Continuities are not a flat enum. Regild Century follows UC; the Correct
Century is implied to contain everything; GQuuuuuuX branches from it. The
relation types are `succeeds`, `contains`, `diverges_from`, `contested_by`,
`parallel_to`, and they live in `timelines.yaml`.

Nineteen continuities are now declared and there are **eleven** relations
between them, six of which are one continuity pointing at the others.
`parallel_to` remains deliberately unused: the independent continuities
have no stated relationship to anything, and asserting editorial edges
would manufacture a structure no source claims. The graph is supposed to be
mostly disconnected.

`depicts_as_fiction` was added to the enum in 2026-08 for the Build
continuity, whose characters build and battle models of mobile suits from
works that, in their world, are *stories*. None of the existing types means
that. `contains` is what the Correct Century does to the Universal Century
— one history enclosing another — and using it here would assert that the
One Year War happened in the Build continuity's past. It did not. It was on
television.

`contested_by` finally has its first use, on Mars Century against After
Colony: Frozen Teardrop's standing as a continuation of AC is genuinely
disputed, and the dataset's job is to make that visible rather than to
adjudicate it.

### 6. Every entity id is namespaced by its timeline

Gundam AGE has an Earth Federation. So does the Universal Century. They are
different organisations, and `fac.efed` cannot mean both.

Each timeline owns an id namespace — its `abbrev`, lowercased, with runs of
non-alphanumerics folded to a hyphen. `tl.uc` owns `uc.`; the GQuuuuuuX
branch (`UC-G`) owns `uc-g.`. Every `ser.`, `src.`, `fac.` and `evt.` id
must sit in the namespace of the timeline it declares:

```
fac.uc.efed        Earth Federation (Universal Century)
fac.ag.efed        Earth Federation (Advanced Generation)
evt.ce.0070.bloody-valentine
```

`validate.py` enforces this. It was retrofitted onto the UC in one pass at
37 events; the same change at 200 would have been a different kind of day.

`fac` also carries a required `timeline` field, as `ser` and `src` already
did. Factions were the one entity type without one, which is exactly why
the second continuity's Federation had nowhere to live.

---

## Layout

```
data/
  timelines.yaml     continuities, epochs, inter-timeline relations
  sources.yaml       every citable work, with canonicity tier
  series.yaml        series with in-universe coverage spans
  factions.yaml      factions with active spans and succession edges
  events/
    uc-0001-0078-prewar.yaml          Universal Century
    uc-0079-0080-one-year-war.yaml
    uc-0083-0089.yaml
    uc-0093-0097.yaml
    uc-0105-0223-late.yaml
    fc-0020-0060.yaml                 Future Century
    ac-0175-0196.yaml                 After Colony
    aw-0001-0015.yaml                 After War
    cc-2345.yaml                      Correct Century
    ce-0070-0075.yaml                 Cosmic Era
    ad-2091-2314.yaml                 Anno Domini
    ag-0101-0164.yaml                 Advanced Generation
    rc-1014.yaml                      Regild Century
    pd-0001-0325.yaml                 Post Disaster
    as-0101-0123.yaml                 Ad Stella
    mc-0001-0022.yaml                 Mars Century
    build.yaml                        Build — no calendar, hence no years
    sd.yaml                           SD Gundam Force and SD Gundam World
schema/
  common.schema.json     ids, dates, claims, coverage spans
  events.schema.json
  entities.schema.json
scripts/
  validate.py
  build_site.py          renders the dataset to a single HTML page
  site_template.html     the app shell; data + font injected at build time
  fonts_b64.json         subset display face, base64 (build input)
site/
  index.html             generated — open this
  artifact.html          generated — same page, no document shell
```

Files are split by period and continuity purely to keep diffs reviewable.
Ids are global and namespaced by prefix and timeline, so nothing depends on
which file an entry lives in — move entries freely. `validate.py` finds
event files by their top-level `events` key rather than by path or
filename, so a new continuity needs no registration anywhere.

---

## Source tiers and resolution

Each source carries a `tier`:

| Tier | Kind |
|------|------|
| 1 | theatrical film, TV broadcast |
| 2 | OVA, ONA |
| 3 | manga, novel |
| 4 | games, technical documentation, encyclopedias |

**These are a display-ordering convention, not a canonicity ruling.** They
exist so the resolver has a deterministic default. Reasonable people order
these differently; renumber them and the whole dataset re-resolves, which
is the point.

Tier 4 was unused until the 2026-08 verification pass, which is itself a
finding: dates that no narrative work states were being cited to narrative
works. They now cite `src.uc.chronology`. If a tier stays empty, suspect
that its contents are hiding in another tier rather than that it is not
needed.

Default policy for a contested property:

1. Prefer the lowest tier number.
2. On a tie, prefer the more precise date literal.
3. On a tie, prefer the earlier `release_year`.
4. If any claim carries `resolution: unresolved`, do not pick — the sources
   deliberately leave it open, and collapsing it is a factual error.

Rule 4 exists because of Amuro Ray at UC 0093. No source confirms his death
and none depicts his survival. Rendering "died UC 0093" is wrong;
rendering an ongoing thread is also wrong. The third state is necessary.

---

## Confidence flags

Distinct from tier — this is about how much *this project* trusts an entry,
not how canonical the source is.

| Flag | Meaning |
|------|---------|
| `certain` | Explicit in the source |
| `approximate` | Real but imprecisely dated |
| `disputed` | Sources actively conflict |
| `interpretive` | A widely-held reading, not an explicit statement |
| `editorial` | An inference by this project, not a claim by any source |
| `inherited` | Taken from a parent timeline |
| `needs-verification` | Entered but not yet checked against the work |

`editorial` and `needs-verification` must be visually distinct in any
render. The moment a guess is displayed the same as a sourced fact, the
dataset stops being trustworthy — and it will be *your* guess that misleads
you, six months from now, when you have forgotten making it.

---

## Adding an event

```yaml
- id: evt.uc.0079.side7-raid        # evt.<timeline>.<year>.<slug>
  label: Zeon raid on Side 7
  type: battle                       # battle|war|political|technological|
                                     # atrocity|disaster|personal
  timeline: tl.uc
  date:
    - start: "0079.09.18"
      sources: [src.uc.msg-tv]
  participants: [fac.uc.principality-zeon, fac.uc.efsf]
  summary: >
    One or two sentences, in your own words.
  depicted_in: [ser.uc.msg]
```

Required: `id`, `label`, `timeline`, `date`, `summary`. Every date claim and
every property claim needs at least one source id — the validator enforces
this, and there is no exemption mechanism on purpose. The `<timeline>`
segment must be the namespace that timeline owns; see
[principle 6](#6-every-entity-id-is-namespaced-by-its-timeline).

**Events a source places only in sequence** take `undated` where the id
convention wants a year, and an `anchor` with no `offset_years`:

```yaml
- id: evt.fc.undated.devil-gundam-theft
  date:
    - anchor:
        relative_to: evt.fc.0060.thirteenth-gundam-fight
        direction: before
      sources: [src.fc.g-gundam]
```

This is a gap in the convention rather than a flourish. An event the source
orders but never dates has no year to name it with, and inventing one
encodes a guess in the id, where no confidence flag can reach it. Two
entries use it so far — the Devil Gundam theft and the Black History.

Write summaries yourself. Do not paste them from a wiki: the large Gundam
wikis are share-alike licensed, and importing their prose would bind this
project to those terms. Dates, names, and factual chronology are not
copyrightable and can be compiled freely — it is the *prose* that carries
the licence. One original sentence per event avoids the whole issue.

---

## Validation

```bash
pip install pyyaml jsonschema
python scripts/validate.py            # errors fail, warnings do not
python scripts/validate.py --strict   # warnings fail too — use in CI
```

The script resolves both the split layout above and a flat one-directory
copy, and identifies event files by their top-level `events` key rather
than by path — so `ac-0195.yaml` needs no registration when it arrives.

Three layers:

1. **Structural** — each file against its JSON Schema.
2. **Referential** — every referenced id exists. Catches typos in
   `sources`, `participants`, `depicted_in`, `related`, and faction
   succession chains.
3. **Semantic** — dates parse, `end` does not precede `start`, declared
   precision matches the literal, and `depicted_in` agrees with the target
   series' coverage spans.
Layers 2–4 do not run if layer 1 found anything. Every later check assumes
the shapes the schema guarantees — `check_coverage` reads `c["start"]`
because the schema promised it exists — so running them over structurally
invalid data raises a `KeyError` partway through. Since errors print at the
end, the traceback then *replaces* the report: the structural error is
found and never shown. That bug was itself found by negative-testing the
coverage schema, which is the argument for negative-testing validators.

4. **Cross-entity** — added 2026-08 with the expansion:
   - ids sit in their timeline's namespace (**error**);
   - `depicted_in` does not cross timelines (**error**) — ordinals are
     era-relative, so comparing CE 0071 against UC 0071 is not merely
     unhelpful, it returns a confident answer about two dates that share no
     epoch;
   - a faction does not begin before its own `predecessor` (**error**);
   - a faction's `active` span contains every event naming it as a
     participant (**warning**);
   - `depicted_in` resolves against the series' span *in the event's own
     era*, so a work covering two eras is checked against the right one
     (**error** if the series has no span in that era at all).

Layer 4 earns its keep immediately. The faction-span rule fired on its
first run against already-corrected UC data and found a fault the date pass
had missed: the Treaty of Granada listed the *pre-war* Republic of Zeon as
a signatory — a state dissolved eleven years before the signing. The file
already carried a note saying the post-war republic was a name collision
that "needs explicit handling", and then merged the two anyway.
`fac.uc.republic-zeon-2` now exists.

Layer 3 is where the value is. It found the depiction/reference bug
described above, and it will catch the same class of error every time you
add a series with a flashback.

Current state: **0 errors, 1 warning** across 100 events — the one warning
is informational, reporting that `evt.uc.0133.jupiter-conflict` carries two
competing date claims. That is intended; contested dates are always
reported so they never go unnoticed.

Every layer-4 rule and both new schema constraints have been
negative-tested by reintroducing a known fault and confirming each fires. A
rule that has only ever passed is not known to work — and in this codebase
that is not a slogan, since negative-testing is what turned up the
crash-instead-of-report bug above.

---

## The site

```bash
pip install pyyaml jsonschema
python validate.py          # errors fail, warnings do not
python build_site.py        # writes site/index.html — open it, no server needed
```

`site/` is generated and is not committed. Every push to `main` runs
`.github/workflows/pages.yml`, which validates the dataset, rebuilds the page
and publishes it to GitHub Pages. The YAML stays the source of truth, so the
published site cannot drift from the data it claims to render.

The page embeds a subset of Noto Sans Display under the SIL Open Font
License 1.1. `THIRD-PARTY-FONTS.txt` carries that licence, because the OFL
requires it to travel with the font.

One Python script, one HTML template, no toolchain and no runtime
dependencies. The YAML is read once at build time and embedded as JSON, so
the output opens straight off the filesystem. `site/artifact.html` is the
same page without the document shell, for hosts that supply their own.

It is an app shell, not a document: a sidebar listing all 19 continuities
(colour dot, abbreviation, event count) beside a main pane that switches
between two views.

**The star chart** is the overview — one rail per continuity, era badge at
the head, every work along it as a wordmark. Rails pack into two columns with
dense eras spanning both, which roughly halves the height. Works are placed
by **sequence, not elapsed time**: eras share no clock, so a common scale
would be a lie, and the rail is a shelf rather than an axis. Rail *length*
is proportional to how many works an era holds; rail *drop* is set by label
density and is never traded away, because a clamped drop stacks a dense
era's labels on top of each other.

Within those constraints the layout is **scattered rather than gridded**: a
seeded generator gives each rail its own slope, indent and trailing gap, so
the map reads as composed instead of tabulated. The seed is fixed and reset
on every draw — a map that rearranges itself when you drag the window is
worse than a tidy one. Jitter is drawn only from genuinely unused width, so
no label can be pushed into a neighbour.

It carries its own **search**, over work titles, era names and abbreviations,
coverage spans and release years. Non-matching rails fade to context rather
than disappear, because removing them would collapse the layout and hide how
much of the chart the search passed over. Matching rails **sort to the top**:
without that the only hits can sit below the fold, and the chart reads as
though nothing happened. The entrance animation is suppressed while a search
is active, since it ends at full opacity and would fight the dimming.

**Any rail head, sidebar row, or relation name opens that continuity** —
the star chart is the navigation. That view is the analytical one: three bands on
the era's own real axis (works, events, factions), a live search over
labels, summaries and source titles, type filters, and a flagged-only
toggle.

**A continuity with no calendar gets an order diagram instead of an axis.**
Build and the SD Gundam settings carry no dates at all, so no axis can be
drawn and none is faked. But "no dates" is not "no structure": Build's
events are anchored to each other with stated intervals, and that partial
order is drawn as chains of linked nodes with the offsets on the edges
(`+7 yr`, `interval unknown`). Build's **two chains are rendered separately
and labelled as unordered against each other**, because no source
establishes which came first and joining them would invent the missing
edge — the same point the anchor model makes in `build.yaml`. Events with
neither a date nor a relation land in a "no ordering hook" group.

The card header follows the data — `— chart`, `— order, not dates`, or
`— nothing recorded` — because a header promising a chart above an empty
card reads as a broken render rather than as the honest answer it is.

### Themes

Four, from the suits, switchable in the sidebar and remembered:

| Theme | Ground | Reading |
|---|---|---|
| **RX-78-2** | light | white with Federation blue, red and gold |
| **Char** | dark | Sazabi crimson on near-black, gold secondary |
| **Unicorn** | light | pearl with psycho-frame red and a gold V-fin |
| **Banshee** | dark | black with Norn gold |

The picker sits at the foot of the sidebar and shows each theme as an
**illustrated mecha head** in its own palette, so you choose by suit rather
than by colour chip. Those glyphs are
original geometric drawings, not traced character art — the official designs
are copyrighted, and at 46px only silhouette and colour survive anyway. Each
carries the cues that separate its suit from the others: a faceted helmet
with a full V-fin and twin eyes; a rounded dome with a mono-eye slot and a
commander blade; a single horn over a sealed visor; that horn split in two. Banshee's two prongs are
drawn with a deliberate gap; abutted they merge into one wide horn and
become indistinguishable from Unicorn at that size.

Each theme defines the **complete** token set — no colour is left to be
inherited from another theme, which is the failure mode that renders one
theme's text on another's ground. The page background follows the theme's mode: dark
themes get a starfield, light themes get a soft gradient mesh, because a
starfield has no light-mode equivalent and inverting one just makes grey
confetti.

### Rendering rules it keeps

- **One axis per continuity, never a shared one.** Ordinals are
  era-relative, so a combined axis would place CE 0071 and UC 0071 at the
  same point. The era's abbreviation labels the axis for the same reason.
- **Undated events are drawn off the axis**, in a tray that states what is
  known — an anchor with a direction, or nothing. 12 of 100 land there.
- **Factions never bring an axis into existence.** In a continuity with no
  calendar their `active` start is `"0001"` because `faction.active` has no
  `undated` escape. Those views render axis-less with factions listed.
- **`main` spans solid; prologue, flashback and epilogue dashed hairlines**,
  so Unicorn's one-day UC 0001 prologue cannot masquerade as 95 years.
- **Anything flagged is dashed *and* chipped** — `editorial` → *guess*,
  `needs-verification` → *unchecked*, `disputed` → *contested*. Never
  colour alone.
- **The map labels a work by its `main` span**, not its first: Unicorn's
  first span is the UC 0001 prologue and Wing's is an AC 0175 flashback, so
  taking `spans[0]` files both works under the wrong era entirely.
- **Cross-era spans appear on both charts.** Frozen Teardrop shows on the
  Mars Century rail and on the After Colony one marked `↗`.

### Colour, type, logos

Each continuity carries its own hue — more than the eight a categorical
palette allows, legitimate **only because hue is never the encoding here**.
Every rail has a badge, every work its title, every flag its word; colour
reinforces identity that position and text already carry. Where colour
*would* encode, in the explore chart's three bands, it stays within the
theme's validated slots. Event *type* is a filter and a label rather than a
hue: eight types cannot be kept colourblind-safe as scattered dots. Every
value in the chart is also in the table below it.

Display type is Noto Sans Display ExtraCondensed Black Italic (SIL Open
Font License 1.1), subset to Latin and digits and inlined as a 9.5 KB woff2
data URI — an artifact CSP blocks font CDNs outright, and a silent fallback
would drop the page's only typographic voice with no error to notice.
`fonts_b64.json` holds that payload and is a build input, not output.

**The official series logos are trademarked artwork and are not
reproduced.** Titles are set in an original typographic treatment pitched
at the same register — heavy condensed italic — which is a design choice
about the words, not a copy of the marks. Illustration is original and
abstract (starfield, gradient mesh, glow) for the same reason.

**Gundam Wiki links** are `Special:Search` "go" URLs built from each label —
`…/Special:Search?search=Battle+of+Loum&fulltext=0`. MediaWiki jumps
straight to an article when the title matches exactly and shows results
when it doesn't, so a link never 404s. Hand-written slugs were declined on
purpose: a guessed article path is a confident wrong value of exactly the
kind this dataset exists to avoid, and there is no schema field to flag it
with. If someone verifies real article titles, add a `wiki` field and
prefer it over the generated URL.

---

## Verification

**Pass 1 (2026-08): every UC date checked against reference compilations.**
Not against the works themselves. That distinction is the reason
`src.uc.chronology` carries `needs-verification` even though the dates it
supports are now the best available: a compilation can be wrong in the same
way twice, and agreement between two of them is weaker evidence than it
looks.

Eleven dates were wrong. The three that mattered:

- **30 Bunch gassing** was dated UC 0087.02; it is UC 0085.07.31. A
  two-year error that made the AEUG form two years before the atrocity it
  formed in response to.
- **Republic of Zeon** was dated UC 0069, one year after Deikun's death; it
  is UC 0058, ten years before it. The old value made the Zabi takeover and
  the declaration of independence the same act, inverting the politics the
  whole pre-war file rests on.
- **Titans dissolution** was dated UC 0087.02 while the Titans were still
  listed as fighting a war that ran to UC 0088 — contradicted by this
  dataset's own `gryps-conclusion` event.

The remaining eight were single-step errors: Operation British's end
conflated with Loum's, the Laplace incident off by a month at both ends,
the Principality off by two years, Deikun's death carrying a day borrowed
from a different event, the Sleeves starting four years before their own
predecessor, Axis starting six years late, the AEUG ending before a war it
fought in, and a `latest_event` of UC 0223 for which no entry exists.

Two structural notes from the same pass, both marked in the data:

- Many corrected dates were attributed to `src.uc.msg-tv`, which does not
  state them. The 1979 series gives no calendar date for the founding of
  the Republic of Zeon. Those are now `src.uc.chronology`, which is what
  put tier 4 into use for the first time.
- Moving the Titans to UC 0083.12.04 pushed the event outside ser.uc.0083's
  coverage. The fix was an `epilogue` span, not a wider `main` span — the
  same call described in [Depiction is not reference](#4-depiction-is-not-the-same-as-reference).

Still unverified:

- **Everything against a primary work.** Pass 1 raises the floor; it does
  not reach the bar the design principles set.
- The Origin's account of Loum, still deliberately at low specificity.
- `evt.uc.0058.republic-declared` — day-level 14 September rests on one
  line, and The Origin's Munzo naming may make this the dataset's first
  genuine *date* dispute.
- Battle of Loum's close (15–16 vs 15–17) and Odessa's bounds (6–9 vs
  7–11); compilations disagree, and the disagreement is between reference
  works rather than between narrative sources, so it is noted rather than
  recorded as competing claims.
- The GQuuuuuuX branch, now spans-only from the work's premise.
- Late-era faction spans (Mafty, Crossbone Vanguard, Zanscare, League
  Militaire), all `approximate` and none contradicted by an event.

**Pass 2 (2026-08): the ten new continuities are NOT verified.** Dates were
taken from reference compilations in a single sweep and cross-checked
against each other where two existed, which is a lower standard than pass 1
applied to the UC and much lower than reading the works. Treat the whole
non-UC half of this dataset as pass-1-pending.

What is solid: era placement of all 34 series, and the day-precision dates
in After Colony (AC 0175.04.07, AC 0195.04.07, AC 0195.12.24, AC 0196.12.24)
and the Cosmic Era (CE 0070.02.14, CE 0071.01.25, CE 0073.10.02), which are
repeated consistently across sources.

Weakest and flagged in the data:

- `evt.ce.0075.foundation-conflict` and `ser.ce.seed-freedom` —
  `needs-verification`; the year comes from summary material only.
- The end of the second Cosmic Era war, given variously as CE 0073 and
  CE 0074.
- `evt.as.0123.quiet-zero` — placed in the later year on sequence alone.
- Everything in the Future Century. The work dates almost nothing, and its
  own stated tournament cadence contradicts its own dated tournaments — see
  the `schedule_consistency` claim on `evt.fc.0060.thirteenth-gundam-fight`.
- Every `editorial` faction start outside the UC. See Known gaps.

**Pass 3 (2026-08): Mars Century, Build, SD Gundam.** Same standard as pass
2 — reference compilations, single sweep, unverified against the works.
Specific cautions:

- **Mars Century rests on one disputed source.** Frozen Teardrop is the
  only work in the era and its status as a continuation of After Colony is
  itself contested. MC 0001 = AC 0182 and the two-Earth-years-per-Martian-
  year rate are both from that single source. The AC-era flashback bounds
  on `ser.mc.frozen-teardrop` are `needs-verification`; some chronologies
  run After Colony to AC 0197 and place part of that material there.
- **The Build ordering is a partial order, not a sequence.** The Build
  Fighters chain and the Build Divers chain are each internally ordered and
  the relationship *between* them is not established by any source. Build
  Metaverse confirms they share a universe without saying which came first.
  Anything that linearises this has invented the missing edge.
- **SD Gundam is undated by nature, not by omission.** Nothing will ever
  make those events datable, and three further SD settings (Knight, Musha,
  Command Chronicles) are declared as `stub` and deliberately unpopulated.

The UC 0093–0123 gap is real, not missing data. One major work covers
thirty years. So is the PD 0001–0323 gap, which is three centuries wide
with two points in it. A linear render should show that emptiness, because
the emptiness is the accurate picture — and it should show the Build and SD
continuities off the axis entirely, for the same reason.

## Known gaps

- **No `date` disputes yet.** Current conflicts are all at the property
  level. The nearest candidate is now on the table: The Origin calls
  pre-Zabi Side 3 the Autonomous Republic of Munzo and appears to place
  Deikun's declaration of independence at his death rather than a decade
  earlier, which would put it in direct conflict with UC 0058. Recorded as
  a property claim flagged `needs-verification` until someone reads the
  volumes, because a date dispute asserted from a summary is not a dispute.
- **Non-UC faction spans are mostly fiction.** The UC gives founding dates.
  Almost none of the other continuities do, so `active.start` for 51 of the
  68 factions is the earliest point this *dataset* attests them — the first
  event that names them — flagged `editorial`. Read those as left-censored
  bounds, not birth dates. A render drawing them as lifespans will imply
  organisations that sprang into being on the day the camera found them.
  This is the single largest source of wrongness in the expansion.
- **No people, locations, or mobile suits.** The `per.` and `loc.` id
  prefixes are reserved in the schema but unused. Pilot allegiance over
  time is the dataset a Sankey render would need, and it is the obvious
  next expansion now that every continuity is seeded.
- **Depth, not breadth, is what remains.** There are no uncatalogued
  *continuities* left, but there are many uncatalogued works inside them —
  most of all in the UC (G-Saviour at 0223, Gaia Gear at 0203, Advance of
  Zeta, Blue Destiny, Twilight AXIS, Moon Gundam, Cucuruz Doan's Island,
  Requiem for Vengeance), and then the SEED Astray family, 00P/00F/00I,
  G-Unit, Urdr-Hunt. Gaia Gear is explicitly disowned by its rights holder
  and is a second candidate for `contested_by`.
- **No ingest script.** Ordinal conversion is specified but not yet
  implemented outside the validator's internal helper.

---

## What the expansion cost the schema

Thirteen continuities were added in 2026-08, in two passes. Four additive
schema changes were forced, each by data that could not otherwise be
recorded truthfully:

| Change | Forced by |
|---|---|
| `undated: true` on date claims and coverage spans | Build and SD Gundam have no calendar at all |
| `timeline` on a coverage span | Frozen Teardrop is Mars Century with After Colony flashbacks |
| `depicts_as_fiction` relation type | Build's characters build models of the other continuities |
| `competition` event type | An entire continuity whose every event is a tournament |

All four are additive and none breaks existing data. Two more holes of the
same shape were found and **left open** rather than patched in the same
pass, because neither has a clean answer yet:

- **`epoch` carries an offset but not a rate.** Mars Century runs at
  roughly half After Colony's speed, so MC and AC years are different units
  despite both being four-digit era dates. `at.start: "0182"` on the
  `succeeds` relation records where MC 0001 falls in AC and cannot record
  how fast the two diverge after that. MC 0022 is about AC 0226; anything
  computing AC 0204 has assumed 1:1.
- **`faction.active` has no `undated` escape.** Date claims and coverage
  spans got one; faction spans did not, so `fac.sd-f.sdg` sits at `"0001"`
  in a continuity with no year 1. It is the only literal that satisfies the
  pattern without asserting anything, which is a poor reason for a value to
  exist.

Of the four problems the previous pass predicted, two were real and
structural, one was real and cosmetic, and one turned out to be luck rather
than design.

**Fixed — ordinals were era-blind.** `ordinal("0079")` returns the same
integer whatever era it came from, and `check_coverage` compared event and
series ordinals without checking they shared a timeline. Now an error. This
was the one that would have produced a confident wrong chart in silence.

**Fixed — ids carried no timeline.** Now principle 6, enforced. Gundam AGE's
Earth Federation is `fac.ag.efed` and the UC's is `fac.uc.efed`.

**Still open — `eraDate` hard-codes a four-digit year.** AS 122 is authored
`"0122"`, CE 71 as `"0071"`. It works, and Anno Domini's real Gregorian
years fit the same pattern unpadded. Cosmetic now that comparisons are
timeline-scoped, but the padding is still what made the era-blindness
invisible rather than obvious — and Mars Century is the proof that two
identically-shaped literals can denominate different units.

**Now visible — tiers encode a UC-shaped hierarchy.** The first ten
continuities added were all TV-first, so tier 1 covered them and the
ordering never had to arbitrate. Mars Century broke that: its sole text is
a novel, which sits at tier 3, beneath adaptations of unrelated eras it has
no relationship with. Because tier is documented as a display convention
rather than a canonicity ruling, this is not yet a claim about worth — but
it is now visibly a convention designed around one continuity's shelf, and
it probably needs to become per-timeline.

Three further limits surfaced that nobody predicted:

1. **Calendars that begin at a catastrophe cannot express the
   catastrophe.** After War starts at the end of the Seventh Space War;
   Post Disaster starts at the end of the Calamity War. Both wars therefore
   sit at `"0001"` by construction, with their real start before the epoch
   and unrepresentable. The UC has the same problem in miniature — the
   Earth Federation predates UC 0001. Three of eleven continuities. The
   dates are flagged `interpretive` and annotated, which is honest but not
   a fix; a real fix needs signed offsets from the epoch.

2. **`predecessor` is single-valued and succession is not.** The Earth
   Sphere Federation succeeds three power blocs at once. Two of those edges
   are unrepresentable and the one recorded is arbitrary among equals. The
   UC never needed this because its factions renamed themselves in a line.

3. **An anchor expresses sequence but not a join.** `anchor` takes one
   `relative_to`, so "after the end of two separate chains" cannot be
   said — two claims would read as competing datings rather than as a
   conjunction. `evt.build.undated.metaverse-convergence` is plainly later
   than both Build chains and is recorded as `undated` with the ordering in
   prose, because a wrong structure is worse than an absent one.

4. **Cross-continuity observations have nowhere structural to live.** The
   Heliopolis raid restages the Side 7 raid; the A-Laws are the Titans
   again; After War and the Correct Century both run salvage economies for
   the same reason. These are recorded as `editorial` claims on events
   rather than as `parallel_to` relations, because the relation types
   describe continuity and two works arriving at the same idea
   independently is not that. There are now enough of them that a renderer
   might reasonably want `editorial` claims as a toggleable layer.

Note also that `timelines.relations[].at.event` deliberately points into the
*parent* timeline, since a divergence point is the last event two
continuities share. The new namespace rule does not touch relation targets,
but any future rule requiring references to stay within a timeline has to
exempt it.
