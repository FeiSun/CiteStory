# `site/data.js` — data contract for every page

Each page in `code/templates/` is copied to `profiles/<name>/site/` by `code/build_citation_geo.py`
and loads the shared data with `<script src="data.js"></script>` (works from `file://`, no server).
The script defines one global, `window.CITATION_DATA`:

| field | shape | notes |
|---|---|---|
| `owner` | `"Fei Sun"` | name on the Google Scholar profile (or `name` in profile.json) |
| `home` | `{name, label, lat, lon, country, city}` | the owner's institution; `label` is the city name; `city` is the id in `cities` of the home city (a district folded into its city counts), or null when no citing paper comes from there. Always present: the build stops when no home can be placed |
| `targets` | `[{id, title, openalex_title, key, pid, doi, publication_year, cited_by_count, scholar_title}]` | the owner's papers in OpenAlex (107 records). `cited_by_count` is the number of citing works in this snapshot, counted at build time. `title` is the title on the Google Scholar profile and is what pages show, always in full (no abbreviations or acronyms); `openalex_title` is OpenAlex's spelling. Preprint and proceedings versions of one paper are separate records with the same `key` (the normalized title: NFKC, case-folded, letters and digits of any script; the id when empty). Group by `key` → 102 papers. `pid` = `paper_id(key)` (`build_views.py`), the 8-hex id the pages put in `?paper=` |
| `works` | `[{id, year, date, targets, cities, inst}]`, later also `title, doi, authors` | 11,405 papers that cite the owner. `year` is never later than the snapshot's. `date` is `YYYY-MM-DD` or null (no year either); a date OpenAlex gave as 1 January, or only a year, is moved to a stable day in that year (the same day as in `views.js`) and the work carries `yo: 1`; `targets` = ids of the owner's papers it cites; `cities` = city ids of its authors' institutions (may be empty); `inst` = the distinct institution ids of its authors. `title`, `doi` and `authors` (`[{name, institutions:[institution id]}]`, only authors with an affiliation) arrive from `data-details.js` after first paint, see below |
| `cities` | `[{id, name, country, region, lat, lon, works, institutions, count}]` | 1,337 cities. `country` is ISO-3166 alpha-2; `works` = citing work ids; `count` = number of those works |
| `institutions` | `{id: {display_name, k, n}}` | `k` = kind, from OpenAlex's type: `u` university, `c` company, `r` research or government, `h` healthcare and other; `n` = citing papers with an author at that institution |
| `countries` | `{ISO2: {name, continent, subregion}}` | English names from Natural Earth |
| `land` | `[{iso, polygons:[[outerRing, ...holes]]}]` | Natural Earth 1:50m countries, simplified, Antarctica removed. Rings are `[[lon, lat], ...]`. Natural Earth already splits shapes at ±180° (Russia, Fiji), so no ring crosses the antimeridian; a projection with a seam elsewhere (Greenland at 30°W) must handle it |
| `stats` | `{citing_works, mapped_works, unmapped_works, cities, countries, no_affiliation_works, possibly_truncated_works, institution_count, misdated_works}` | `misdated_works` = citing works dated two or more years before every paper they cite; the build drops their date (`date` and `year` null) and they are treated as undated everywhere |
| `manifest` | `{as_of, complete, ...}` | `as_of` is the ISO snapshot time (2026-11-25). Some journal works carry dates after it; treat them as dated `as_of` |
| `scholar_count`, `unmatched` | `108`, `[{title, citations}]` | Scholar papers not found in OpenAlex (6) |

Links: a work opens at `doi` if present, else `https://openalex.org/<id>`.

## Details load after first paint

To keep the first download small (about 630 KB gzipped instead of 1.6 MB), each paper's `title`, `doi` and
`authors` live in `site/data-details.js` (about 1.1 MB gzipped). `data.js` starts loading it on the
window `load` event. When it arrives, the loader writes those three fields onto the same objects in
`CITATION_DATA.works`, sets `CITATION_DATA.detailsLoaded = true` and dispatches a `citation-details` event on
`window`. `window.loadCitationDetails()` returns a promise for the same moment (call it to be sure).

A page must therefore:
- draw everything that needs only the core fields at once (maps, timelines, counts, institution totals via
  `inst` or `institutions[id].n`);
- keep references to the original work objects (or copy the three fields across on the event);
- show a short "Loading papers…" state where titles or author names are needed before the event, and
  re-render those views when `citation-details` fires (including a detail panel already open).

Counting rules every page must keep:
- A citing work counts once per city; a work with authors in several cities counts in each, so city totals sum to more than the number of works.
- Country and continent totals count each work once per country / continent.
- Self-citations are included. Institution coordinates are usually the headquarters or main campus.
- 744 works have no affiliation and cannot be placed; say so where totals are shown.

# `site/views.js` — data for Constellation, Race, Regulars and Record

Written by `code/build_views.py` from the same payload. One global, `window.CITATION_VIEWS`:

| field | shape | notes |
|---|---|---|
| `owner`, `snapshot` | `"Fei Sun"`, ISO time | |
| `years` | `[2012, …, 2026]` | first dated citing work to the snapshot year |
| `stats` | `{papers, works, undated, multi}` | `multi` = citing works that cite two or more papers |
| `papers` | `[{id, t, y, n, u, yr, link, x, z, r}]` | versions merged by normalized title, ordered by `n` (citing works). `id` is the same `pid` as in `data.js`. `y` earliest publication year, `u` undated citing works, `yr` citing works per entry of `years` (`sum(yr) + u == n`). `x, z, r` are the star position and halo radius from a deterministic force layout, normalized so every halo fits in [-1, 1] |
| `pairs` | `[[a, b, count]]` | paper indices cited by the same work, strongest first (at most 600) |
| `works` | `[[t, [paper index], place, flags]]` | sorted by `t`, undated last. `t` is a fractional calendar year clamped to the snapshot, or null. `place` indexes `places` (first located city), or -1. `flags`: 1 = the work is one of the owner's own papers, 2 = only the year is known (OpenAlex wrote 1 January) and the work was placed on a stable day in that year |
| `places` | `[[label, longitude]]` | `"City, Country"` |
| `citers` | `[{name, own, inst, w}]` | the 60 outside authors with the most citing works plus up to 12 co-authors (`own: 1`: an author of any of the owner's papers); `w` = indices into `works`, in order; `inst` = the institution they sign with most often. Authors are keyed by OpenAlex author id and counted over every author of a work, with or without an affiliation; the owner is never listed |

`site/views-details.js` defines `window.CITATION_VIEW_DETAILS`, an array aligned with `works`:
`[title, byline, link]`; the byline names the work's first author, affiliated or not. Pages load it on first use with `Shell.details()`.

Rules these pages keep: a citing work counts once per paper, whatever the number of versions it cites;
undated works are counted in totals ("All years", "Now") but never drawn at a date.
