#!/usr/bin/env python3
"""Aggregate institution cities and build one profile's pages from its data folder (run through citestory.py)."""
import csv
import json
import math
import shutil
from pathlib import Path
import re

import build_views
from build_views import script_json
from fetch_citation_geo import normalized_title, owner_keys, owner_names, short

CODE = Path(__file__).resolve().parent
TEMPLATES = CODE / "templates"
BASEMAP = CODE / "basemap" / "ne_50m_admin_0_countries.geojson"
SIMPLIFY_DEG = 0.035      # Douglas-Peucker tolerance; ~4 km, invisible at world scale
MIN_RING_AREA = 0.01      # square degrees; drops specks smaller than a small island


def city_info(institution):
    geo = institution.get("geo") or {}
    lat, lon = geo.get("latitude"), geo.get("longitude")
    if not geo.get("city") or isinstance(lat, bool) or isinstance(lon, bool):
        return None
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    country = geo.get("country_code") or institution.get("country_code") or ""
    region = geo.get("region") or ""
    geonames = geo.get("geonames_city_id")
    key = ("geonames:" + str(geonames)) if geonames else "|".join([country, region.casefold(), geo["city"].casefold()])
    return {"id": key, "name": geo["city"], "country": country, "region": region,
            "lat": lat, "lon": lon}


def km(a, b):
    p1, p2, dl = math.radians(a["lat"]), math.radians(b["lat"]), math.radians(b["lon"] - a["lon"])
    return 6371 * math.acos(max(-1, min(1, math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl))))


def merge_nearby(cities):
    """Fold duplicate places into one city, in place; return {merged id: kept id}.

    OpenAlex can give one place two geonames ids (Krakow twice) or name a district instead of its city
    (Jinrongjie in Beijing). Merge a city into another of the same country when it has the same name within
    25 km, or lies within 8 km of one with at least ten times its papers. Distinct towns of similar size
    stay apart (Cambridge and Boston, 4 km)."""
    order = sorted(cities, key=lambda k: (-len(cities[k]["works"]), k))
    merged = {}
    for i, small in enumerate(reversed(order)):
        a = cities[small]
        for big in order:
            if big == small or big in merged:
                continue
            b = cities[big]
            if b["country"] != a["country"] or len(b["works"]) < len(a["works"]):
                continue
            if len(b["works"]) == len(a["works"]) and big > small:
                continue
            d = km(a, b)
            same_name = a["name"].casefold() == b["name"].casefold() and d < 25
            if same_name or (d < 8 and len(b["works"]) >= 10 * len(a["works"])):
                b["works"] |= a["works"]
                b["institutions"] |= a["institutions"]
                merged[small] = big
                break
    for small in merged:
        del cities[small]
    # a city merged into one that was itself merged later points at the final survivor
    for small, big in list(merged.items()):
        while big in merged:
            big = merged[big]
        merged[small] = big
    return merged


def aggregate(works, institutions):
    cities = {}
    mapped = set()
    missing_affiliations = 0
    truncated = 0
    for work in works:
        found = set()
        institution_ids = {i for a in work["authors"] for i in a["institutions"]}
        if not institution_ids:
            missing_affiliations += 1
        truncated += bool(work.get("possibly_truncated_authors"))
        for iid in sorted(institution_ids):
            city = city_info(institutions.get(iid, {}))
            if city is None:
                continue
            key = city["id"]
            if key not in cities:
                cities[key] = dict(city, works=set(), institutions=set())
            cities[key]["institutions"].add(iid)
            cities[key]["works"].add(work["id"])
            found.add(key)
        work["cities"] = sorted(found)
        if found:
            mapped.add(work["id"])
    merged = merge_nearby(cities)
    for work in works:
        work["cities"] = sorted({merged.get(c, c) for c in work["cities"]})
    rows = []
    for city in cities.values():
        rows.append(dict(city, works=sorted(city["works"]), institutions=sorted(city["institutions"]),
                         count=len(city["works"])))
    rows.sort(key=lambda c: (-c["count"], c["name"], c["id"]))
    return rows, {"merged": merged, "citing_works": len(works), "mapped_works": len(mapped),
                  "unmapped_works": len(works) - len(mapped), "cities": len(rows),
                  "countries": len({c["country"] for c in rows if c["country"]}),
                  "no_affiliation_works": missing_affiliations,
                  "possibly_truncated_works": truncated,
                  "institution_count": len(institutions)}


def undate_impossible(works, targets, slack=1):
    """Drop the date of a citing work that is older than every paper it cites; return how many.

    A wrong publication date in the source would otherwise become the first citation of the whole record.
    `slack` years are allowed because a preprint is often cited before the published version appears. The work
    keeps its place and its counts and is treated like any other undated work."""
    earliest, paper = {}, {}     # a paper's versions (preprint, proceedings) share a title: its earliest year counts
    for t in targets:
        paper[t["id"]] = key = normalized_title(t.get("scholar_title") or t.get("title")) or t["id"]
        year = t.get("publication_year")
        if isinstance(year, int) and not isinstance(year, bool):
            earliest[key] = min(year, earliest.get(key, year))
    dropped = 0
    for work in works:
        cited = [earliest[paper[t]] for t in work["targets"] if paper.get(t) in earliest]
        try:
            year = int(str(work.get("date") or work.get("year"))[:4])
        except ValueError:
            continue
        if cited and year < min(cited) - slack:
            work["date"] = work["year"] = None
            dropped += 1
    return dropped


def page_year(work, snapshot):
    """The work's year, no later than the snapshot's: a paper dated ahead of publication sits on the snapshot day."""
    year = work.get("year")
    return min(year, snapshot.year) if isinstance(year, int) and not isinstance(year, bool) else year


def page_works(works, snapshot):
    """Keep what the map pages show: short OpenAlex ids, and only authors who carry an affiliation.

    A year-only date (OpenAlex writes 1 January) is spread over the year, as in views.js."""
    return [{"id": short(w["id"]), "title": w.get("title"), "doi": w.get("doi"), "year": page_year(w, snapshot),
             "date": build_views.page_date(w, snapshot), "yo": build_views.work_day(w, snapshot)[1],
             "targets": [short(t) for t in w["targets"]], "cities": w["cities"],
             "authors": [{"name": a.get("name"), "institutions": [short(i) for i in a["institutions"]]}
                         for a in w["authors"] if a["institutions"]]} for w in works]


def split_works(works, snapshot):
    """Core fields every page needs at once, and the per-paper details loaded after first paint."""
    core, details = [], {}
    for w in page_works(works, snapshot):
        core.append({"id": w["id"], "year": w["year"], "date": w["date"], "targets": w["targets"], "cities": w["cities"],
                     "inst": sorted({i for a in w["authors"] for i in a["institutions"]})})
        if w["yo"]:
            core[-1]["yo"] = 1
        details[w["id"]] = {"title": w["title"], "doi": w["doi"], "authors": w["authors"]}
    return core, details


# Appended to data.js: fetch data-details.js once the page has loaded, merge each paper's title, doi and
# authors into CITATION_DATA.works (same objects), then announce it with a "citation-details" event.
# A failed load sets CITATION_DATA.detailsFailed and fires "citation-details-failed"; calling the loader
# again after a failure tries once more.
DETAILS_LOADER = """
(function(){var p=null;window.loadCitationDetails=function(){if(p)return p;p=new Promise(function(ok,fail){
 if(window.CITATION_DETAILS)return ok();var s=document.createElement('script');s.src='data-details.js';s.async=true;
 s.onload=function(){ok();};s.onerror=function(){s.remove();p=null;window.CITATION_DATA.detailsFailed=true;
  window.dispatchEvent(new Event('citation-details-failed'));fail(new Error('data-details.js failed to load'));};document.head.appendChild(s);})
 .then(function(){var d=window.CITATION_DETAILS||{},w=window.CITATION_DATA.works;for(var i=0;i<w.length;i++){var x=d[w[i].id];
  if(x){w[i].title=x.title;w[i].doi=x.doi;w[i].authors=x.authors;}}window.CITATION_DATA.detailsLoaded=true;
  window.CITATION_DATA.detailsFailed=false;window.dispatchEvent(new Event('citation-details'));});return p;};
 function start(){setTimeout(function(){window.loadCitationDetails().catch(function(){});},60);}
 if(document.readyState==='complete')start();else window.addEventListener('load',start);})();
"""


def page_cities(cities):
    return [dict(c, works=[short(w) for w in c["works"]], institutions=[short(i) for i in c["institutions"]],
                 lat=round(c["lat"], 4), lon=round(c["lon"], 4)) for c in cities]


# OpenAlex institution types, grouped into the four kinds the map colours
KIND = {"education": "u", "company": "c", "facility": "r", "government": "r", "nonprofit": "r", "archive": "r",
        "healthcare": "h", "other": "h"}


def institution_rows(institutions):
    """Name and kind of every institution (the map places cities, not institutions)."""
    return {short(iid): {"display_name": inst.get("display_name"), "k": KIND.get(inst.get("type"), "h")}
            for iid, inst in institutions.items()}


def iso_code(props):
    for key in ("ISO_A2", "ISO_A2_EH", "WB_A2"):
        value = props.get(key)
        if isinstance(value, str) and len(value) == 2 and value.isalpha():
            return value
    return None


def round_coords(value):
    return [round_coords(v) for v in value] if isinstance(value, list) else round(value, 2)


# MapLibre GL JS builds the live-basemap pages load from unpkg, pinned by Subresource Integrity hashes.
MAPLIBRE = {
    "5.24.0": {"js": "sha384-5+cfbwT0iiub6VsQAdn6yz16nr6sDiQoHx6tm4O8OVYXHYOxcffFmCJBL0dgdvGp",
               "css": "sha384-uTttxo/aOKbdE5RlD/SPzSDoDmNvGlUYPjONi2MN/b7c9HPSvW07OIuyP7uL6jxK"},
}


def maplibre_tags(version):
    base, sri = f"https://unpkg.com/maplibre-gl@{version}/dist/maplibre-gl", MAPLIBRE[version]
    return (f'<link rel="stylesheet" href="{base}.css" integrity="{sri["css"]}" crossorigin="anonymous">',
            f'<script src="{base}.js" integrity="{sri["js"]}" crossorigin="anonymous"></script>')


TILES = {   # free, no key; OpenMapTiles vector styles
    "name": "OpenFreeMap", "light": "https://tiles.openfreemap.org/styles/positron",
    "dark": "https://tiles.openfreemap.org/styles/dark",
    "credit": "OpenFreeMap, OpenMapTiles and OpenStreetMap contributors",
    "maplibre": "5.24.0", "globe": True}


def simplify(ring, tol=SIMPLIFY_DEG):
    """Douglas-Peucker on one closed ring of [lon, lat] points."""
    if len(ring) < 5:
        return ring
    keep = [False] * len(ring)
    keep[0] = keep[-1] = True
    stack = [(0, len(ring) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = ring[a], ring[b]
        dx, dy, best, idx = x2 - x1, y2 - y1, -1.0, -1
        norm = math.hypot(dx, dy) or 1e-12
        for k in range(a + 1, b):
            x, y = ring[k]
            d = abs(dy * (x - x1) - dx * (y - y1)) / norm if (dx or dy) else math.hypot(x - x1, y - y1)
            if d > best:
                best, idx = d, k
        if best > tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(ring, keep) if k]


def ring_area(ring):
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))) / 2


# Natural Earth files island states under "Seven seas (open ocean)", and has no row for the French overseas
# departments, which OpenAlex gives their own country codes.
CONTINENT_FIX = {"MU": "Africa", "SC": "Africa", "SH": "Africa", "IO": "Africa", "MV": "Asia", "GS": "South America"}
EXTRA_COUNTRIES = {"RE": ("Réunion", "Africa"), "YT": ("Mayotte", "Africa"), "GP": ("Guadeloupe", "North America"),
                   "MQ": ("Martinique", "North America"), "GF": ("French Guiana", "South America")}


def basemap():
    """Countries as simplified polygons plus English name and continent, without Antarctica."""
    world = json.loads(BASEMAP.read_text(encoding="utf-8"))
    land, countries = [], {}
    for iso, (name, continent) in EXTRA_COUNTRIES.items():
        countries[iso] = {"name": name, "continent": continent, "subregion": None}
    for feature in world["features"]:
        props, geom = feature.get("properties", {}), feature["geometry"]
        if props.get("CONTINENT") == "Antarctica":
            continue
        iso = iso_code(props)
        # Name every country, even one too small to keep a shape (Macao).
        if iso and (iso not in countries or props.get("ISO_A2") == iso):
            name = props.get("NAME") or props.get("NAME_EN")
            if name and "." in name and props.get("NAME_LONG"):     # "Dem. Rep. Congo", "Cayman Is.": the full name
                name = props["NAME_LONG"]
            countries[iso] = {"name": name, "continent": CONTINENT_FIX.get(iso, props.get("CONTINENT")),
                              "subregion": props.get("SUBREGION")}
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        out = []
        for poly in polys:
            rings = [simplify(r) for r in poly]
            if len(rings[0]) < 4 or ring_area(rings[0]) < MIN_RING_AREA:
                continue
            out.append([[[round(x, 2), round(y, 2)] for x, y in r] for r in rings if len(r) >= 4])
        if not out:
            continue
        land.append({"iso": iso, "polygons": out})
    return land, countries


PAGES = ["index.html", "atlas.html", "reach.html", "story.html", "flow.html",
         "constellation.html", "race.html", "regulars.html", "record.html"]
DATA_FILES = ["data.js", "data-details.js", "views.js", "views-details.js"]


def home_place(targets, institutions):
    home_id = targets.get("home")
    city = city_info(institutions.get(home_id, {})) if home_id else None
    if not city:
        raise SystemExit("No home institution with a known city. Set \"home\" in profile.json to the OpenAlex id of "
                         "your institution (search it at https://openalex.org, e.g. \"I4210090176\"), then run "
                         "citestory.py update again.")
    return {"name": institutions[home_id]["display_name"], "label": city["name"],
            "lat": city["lat"], "lon": city["lon"], "country": city["country"], "key": city["id"]}


def home_city(home, cities, merged=None):
    """The id of the mapped city that is home, or None when no citing paper comes from there.

    The home institution's own city, or the city merge_nearby folded it into. Failing that (the institution's city
    has no citing paper of its own, so it was never a city to merge), merge_nearby's rule: a city of the same name
    within 25 km first, then one within 8 km with at least ten citing papers (a district beside its city), so a
    neighbouring town of similar size (Cambridge and Boston) is never taken for home."""
    ids = {c["id"] for c in cities}
    key = (merged or {}).get(home["key"], home["key"])
    if key in ids:
        return key
    near = [(km(home, c), c) for c in cities if c["country"] == home["country"]]
    same = [x for x in near if x[1]["name"].casefold() == home["label"].casefold() and x[0] < 25]
    big = [x for x in near if x[0] < 8 and x[1].get("count", len(x[1].get("works", ()))) >= 10]
    for group in (same, big):
        if group:
            return min(group, key=lambda x: x[0])[1]["id"]
    return None


def swap_in(staging, site):
    """Put the freshly built folder in place of site/ by renaming folders, so site/ is never half old and half new.

    Anything in site/ that the build does not write (not .html or .js) is copied over first. site.old/ holds the
    previous site only while the two renames run: a run stopped between them leaves it, and the next run puts it back."""
    old = site.with_name(site.name + ".old")
    if old.exists() and not site.exists():
        old.replace(site)
    if not site.exists():
        staging.replace(site)
        return
    for extra in site.iterdir():
        if extra.suffix not in (".html", ".js"):
            if extra.is_dir() and not extra.is_symlink():
                shutil.copytree(extra, staging / extra.name, symlinks=True)
            else:
                shutil.copy2(extra, staging / extra.name, follow_symlinks=False)
    if old.exists():
        shutil.rmtree(old)
    site.replace(old)
    staging.replace(site)
    shutil.rmtree(old)


def build(data, site):
    """Read a complete snapshot from `data` and write the pages and their data files to `site`."""
    if not (data / "manifest.json").exists():
        raise SystemExit(f"No complete snapshot in {data}; run citestory.py update first.")
    targets = json.loads((data / "targets.json").read_text(encoding="utf-8"))
    if "aliases" not in targets and (data.parent / "profile.json").exists():     # a snapshot taken before aliases were saved with it
        try:
            listed = json.loads((data.parent / "profile.json").read_text(encoding="utf-8")).get("aliases")
        except (ValueError, AttributeError, OSError):
            listed = None
        targets["aliases"] = [a for a in listed if isinstance(a, str)] if isinstance(listed, list) else []
    manifest = json.loads((data / "manifest.json").read_text(encoding="utf-8"))
    if isinstance(manifest.get("as_of"), str):     # older snapshots carry microseconds, which a browser need not parse
        manifest["as_of"] = re.sub(r"(T\d\d:\d\d:\d\d)\.\d+", r"\1", manifest["as_of"])
    raw = list(json.loads((data / "citing.json").read_text(encoding="utf-8")).values())
    institutions = json.loads((data / "institutions.json").read_text(encoding="utf-8"))
    snapshot = build_views.date.fromisoformat(str(manifest["as_of"])[:10])
    misdated = undate_impossible(raw, targets["works"])
    cities, stats = aggregate(raw, institutions)
    merged = stats.pop("merged")
    stats["misdated_works"] = misdated
    if not cities:
        raise SystemExit("No geolocated citation evidence; refusing to create a placeholder map.")
    home = home_place(targets, institutions)
    home["city"] = home_city(home, cities, merged)
    del home["key"]
    land, countries = basemap()
    names = institution_rows(institutions)
    core_works, details = split_works(raw, snapshot)
    inst_n = {}
    for w in core_works:
        for i in w["inst"]:
            inst_n[i] = inst_n.get(i, 0) + 1
    for iid, inst in names.items():
        inst["n"] = inst_n.get(iid, 0)
    # Citing works per record in this snapshot; the count stored at matching time goes stale on later updates.
    cited_by = {}
    for w in raw:
        for t in w["targets"]:
            cited_by[t] = cited_by.get(t, 0) + 1
    # Pages show the title on the Scholar profile (the input), not OpenAlex's; `key` groups the versions of a paper.
    page_targets = [{"id": short(t["id"]), "title": t.get("scholar_title") or t["title"], "openalex_title": t["title"],
                     "key": normalized_title(t.get("scholar_title") or t["title"]) or short(t["id"]),
                     "pid": build_views.paper_id(normalized_title(t.get("scholar_title") or t["title"]) or short(t["id"])),
                     "doi": t.get("doi"), "publication_year": t.get("publication_year"),
                     "cited_by_count": cited_by.get(t["id"], 0), "scholar_title": t.get("scholar_title")}
                    for t in targets["works"]]
    payload = {"owner": targets["owner"], "home": home, "targets": page_targets,
               "works": core_works, "cities": page_cities(cities), "institutions": names, "stats": stats,
               "manifest": {k: manifest.get(k) for k in ("as_of", "complete", "missing_institution_ids")},
               "scholar_count": len(targets["scholar"]),
               "unmatched": [{"title": r["title"], "citations": r["scholar_citations"]} for r in targets["scholar"] if not r["openalex_ids"]],
               "land": land, "countries": countries}
    # Written beside site/ and swapped in at the end, so a build that fails leaves the previous pages in place.
    site = site.resolve()     # a site/ that is a link to the web folder: build beside the folder itself
    staging = site.parent / (site.name + ".partial")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        # One shared data file; every page loads it with <script src>, which also works from file://.
        (staging / "data.js").write_text("window.CITATION_DATA=" + script_json(payload) + ";\n" + DETAILS_LOADER, encoding="utf-8")
        (staging / "data-details.js").write_text("window.CITATION_DETAILS=" + script_json(details) + ";\n", encoding="utf-8")
        owner_ids = {a for t in targets["works"] for a in t.get("owner_authors", [])} | set(targets.get("openalex_author_ids", []))
        coauthor_ids = {a for t in targets["works"] for a in t.get("authors", [])} - owner_ids
        # bylines with no OpenAlex author id are recognised as the owner by name (aliases since this field was added)
        owner_name_keys = owner_keys(owner_names(targets["owner"], targets.get("aliases", ())))
        view_stats = build_views.write(staging, payload, details, raw, owner_ids, coauthor_ids, owner_name_keys)
        views = (TEMPLATES / "_views.html").read_text(encoding="utf-8")     # ?paper= and the links that carry it to the other views
        picker = (TEMPLATES / "_picker.html").read_text(encoding="utf-8").replace("<!--PAPER_VIEWS-->", views)   # shared paper picker
        shell = (TEMPLATES / "_shell.html").read_text(encoding="utf-8")     # shared tokens, chrome and helpers of the pages on views.js
        css, js = maplibre_tags(TILES["maplibre"])
        for name in PAGES:
            html = (TEMPLATES / name).read_text(encoding="utf-8").replace("<!--SHELL-->", shell).replace("<!--PAPER_PICKER-->", picker).replace("<!--PAPER_VIEWS-->", views)
            if name == "index.html":
                summary = {"owner": payload["owner"], "home": home["label"], "stats": stats, "manifest": {"as_of": manifest.get("as_of")}}
                html = html.replace("__INDEX_SUMMARY__", script_json(summary))
            if name == "atlas.html":
                html = (html.replace("__TILES__", json.dumps(TILES)).replace("__MAPLIBRE_CSS__", css)
                        .replace("__MAPLIBRE_JS__", js))
            (staging / name).write_text(html, encoding="utf-8")
        swap_in(staging, site)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    (data / "summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    with (data / "cities.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["city", "region", "country", "latitude", "longitude", "citing_works", "institutions"])
        writer.writeheader()
        writer.writerows({"city": c["name"], "region": c["region"], "country": c["country"],
                          "latitude": c["lat"], "longitude": c["lon"], "citing_works": c["count"],
                          "institutions": len(c["institutions"])} for c in cities)
    print(json.dumps(stats, ensure_ascii=False))
    print(json.dumps(view_stats, ensure_ascii=False))
    return stats
