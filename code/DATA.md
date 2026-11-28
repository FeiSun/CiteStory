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

# `site/year.js` — data for Year

Written by `code/build_year.py` from the same payload and the full author lists. One global, `window.CITATION_YEAR`:

| field | shape | notes |
|---|---|---|
| `owner`, `snapshot` | `"Fei Sun"`, ISO time | |
| `papers` | `[{t, y, n}]` | versions merged by normalized title, ordered by `n` (citing works, dated or not). `y` is the earliest OpenAlex publication year of its versions, or null |
| `stats` | `{works, undated}` | dated and undated citing works of the whole record |
| `year` | `2026` | the year the page looks back on: the latest year with citing works, or in January and February the year before it when that year has any; null for a record with no dated citing works |
| `review` | `{...}` | that year, as below |
| `history` | `[[year, n]]` | dated citing works of every year up to `year`, including years with none |
| `known` | `[city id]` | cities with a citing work in an earlier year (for the fog) |

The year (`review`):

| field | shape | notes |
|---|---|---|
| `n`, `yo`, `before`, `complete` | numbers, bool | citing works dated this year; how many of them are year-only; dated works of earlier years; false for the snapshot year |
| `works` | `[[i, day, flags, [paper index], since]]` | in date order. `i` indexes `CITATION_DATA.works`; `day` is the day of the year (1 = 1 January), using the same clamped and spread dates as the other pages. `flags`: 1 = only the year is known, 2 = an author signed an earlier citing work (earlier the same year counts), 4 = signed by the owner or a co-author. A work is exactly one of own (4), returning (2) or new. `since` = the earliest year in which any of its authors cited the owner (outside the owner's circle), or null for own works |
| `days` | `{quiet, span, busiest: [[date, n]], run: {n, start, end}}` | `span` = days from 2 January to 31 December or the snapshot; `quiet` = those with no work dated to the day; year-only works are ignored. `run` = the longest run of consecutive days with a work dated to each |
| `papers` | `{cited, counts: [[paper, n, n the year before]], born, route, crossed, oldest, companions}` | `born` = the papers on the Scholar profile whose year is this year (the year written in the venue when it is within a year of the profile's, else the profile's): `{t, p, n, countries, first: {i, date, yo, c, place} or null, stop}`, where `p` is null for a paper OpenAlex has not matched, and `countries` counts where its readers outside the owner's circle are, `first` is the earliest dated citing work not signed by the owner or a co-author (it may be from an earlier year, for a paper that was a preprint first; `c` is its first listed city id or null, `place` the same in English) and `stop` indexes `route`. `route` = conference editions from `code/venues.json` in date order: `{name, city, country, lat, lon, start, papers}`, `papers` indexing `born`. `crossed` = `{p, mark, from, to}`: the highest of 10, 50, 100, 500, 1,000, 5,000, 10,000, 50,000 that the paper's dated citing works passed this year. `oldest` = `{p, y, n}`, the cited paper with the earliest year among those cited this year by someone outside the owner's circle. `companions` = `{n, new, papers, cut, unsure}` or null: distinct co-author names on the profile rows of the year's new papers (the owner left out by initial and family name), how many are on no earlier row, how many rows had names, whether any row of the year cuts its list short, and (`unsure`) whether any earlier row does, which makes `new` approximate |
| `marks` | `[{mark, i, date, yo}]` | the 100th, 1,000th, … dated citing work of the whole record, when it falls in this year. Year-only works sit on a spread day, so the order is approximate |
| `readers` | `{returning, fresh, own, people, new_people, citers, insts, streaks, deep, back}` | counts of works by the three kinds above. `citers` = up to five authors with at least two works this year: `{name, n}`; `insts` = the same for institutions; `streaks` = `[[length, authors]]` for authors with an OpenAlex id who cited in this and each of the `length - 1` years before (3 or more). `deep` = `{i, n, from, to}` or null: the citing work that cites most of the owner's papers at once (at least four) and the span of their years. `back` = `{n, gap, names, last}` or null: authors with an OpenAlex id who cited this year after five or more years without citing, the longest gap, up to three names with it, and `last` = `[[year, people]]`, the year each of them had last cited. `streak_names` = up to three names of those with the longest streak, most citing works this year first. Names in `citers` and `credits` have footnote marks (`*`, `†`, `¹`) cut from their end. All of these leave out works signed by the owner or a co-author |
| `places` | `{countries, cities, new_cities, new_countries, new_works, opened, far, near, firsts}` | a city or country is new when no dated work of an earlier year has an author there. `new_countries` = `{iso, c, p, i, date, yo, art}` (first work of the year from there; `art` = `{name, zh, d}`, a line drawing of city `c` from `code/landmarks.json`, present only when that city is listed); `opened` = `[[paper, new cities]]`; `far` = farthest city of the year from home, `near` = nearest new city (both need home coordinates); `firsts` = the first work ever from a continent (`kind: "continent"`), from south of the equator (`"south"`) or from inside the Arctic Circle (`"arctic"`) |
| `ends` | `{first, last}` | the first and the latest citing work of the year with an exact date, outside the owner's circle: `{i, date, yo, c, place, p}`, `c` being the first listed city id or null |
| `distance` | `{km, n, earths}` or null | over the `n` citing works outside the owner's circle that have a city: the sum of the distance from home to the nearest of their cities; `earths` = km / 40,075 |
| `topics` | `[{t, n, k: [row], rise, fresh}]` | up to eight two- or three-word phrases found in most titles of the year's citing works outside the owner's circle (English titles; singular and plural merged, as are the spellings listed in `SAME`; shown the way most titles write it; generic words dropped). `k` indexes `works`; `rise` = the phrase's share of titles this year over its share in all earlier years (null when earlier years have fewer than 100 titles); `fresh` = true when those earlier years have 100 titles or more and none has the phrase. Empty when fewer than 30 titles |
| `credits` | `[name]` | every name of an author of the year's citing works outside the owner's circle, once, in order of first appearance (names equal but for case, width, spaces or the kind of hyphen are one; namesakes share it); `readers.people` counts the same people, including any without a name or with a number where the name should be, which are left out here; footnote marks at the end of a name are cut off |
| `zh`, `home_zh` (top level) | `{city id: name}`, name | Chinese names of the cities listed in `code/city_names_zh.json`, and of the home label; conference stops in `papers.route` carry `city_zh`. A city that is not listed is named in English |
| `credit_works` | `[[row]]` | for each name in `credits`, the positions in `works` of the citing works this year signed with that name |
| `desks` | `{healthcare, archive}` | each `{n, names, at}`, present when non-zero (`at` = `[[lon, lat, institution, works]]` for those with coordinates): citing works outside the owner's circle with an author at an institution of that OpenAlex type, and up to three of those institutions, most frequent first |
| `scripts` | `[[script, n, [row]]]` | titles of citing works outside the owner's circle written in another script (`cyrillic`, `ja`, `zh`, `ko`, `arabic`, `greek`, `devanagari`, `thai`, `hebrew`): the script holds a third of the title's letters or more, and any kana makes it Japanese |
| `regulars` | `[index]` | positions in `credits` of the people counted in `readers.streaks` |

`code/venues.json` lists conference series: a case-insensitive regular expression tested against the venue on the
Scholar profile, and for the year looked back on the city, country, coordinates and first day. A paper whose venue and year are not
listed has `stop: null`.

`code/landmarks.json` holds a small line drawing for a city, keyed `"City, CC"` with the city's name as `data.js` writes it and the ISO-3166 alpha-2 code: `{name, zh, d}`, where `d` is an SVG path in a box 100 wide and 70 high, drawn as a stroke, and may contain only path commands and numbers. A new country whose first city is not listed gets the outline of the country instead.
