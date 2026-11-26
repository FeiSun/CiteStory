#!/usr/bin/env python3
"""Aggregate institution cities and build one profile's pages from its data folder (run through citestory.py)."""
import csv
import json
import math
from pathlib import Path

import build_views
from fetch_citation_geo import normalized_title, owner_keys, owner_names

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
    return rows, {"citing_works": len(works), "mapped_works": len(mapped),
                  "unmapped_works": len(works) - len(mapped), "cities": len(rows),
                  "countries": len({c["country"] for c in rows if c["country"]}),
                  "no_affiliation_works": missing_affiliations,
                  "possibly_truncated_works": truncated,
                  "institution_count": len(institutions)}


def short(oa_id):
    return oa_id.rsplit("/", 1)[-1] if isinstance(oa_id, str) else oa_id


def page_works(works, snapshot):
    """Keep what the map pages show: short OpenAlex ids, and only authors who carry an affiliation.

    A year-only date (OpenAlex writes 1 January) is spread over the year, as in views.js."""
    return [{"id": short(w["id"]), "title": w.get("title"), "doi": w.get("doi"), "year": w.get("year"),
             "date": build_views.page_date(w, snapshot), "yo": str(w.get("date") or "")[5:] == "01-01",
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
DETAILS_LOADER = """
(function(){var p=null;window.loadCitationDetails=function(){if(p)return p;p=new Promise(function(ok,fail){
 if(window.CITATION_DETAILS)return ok();var s=document.createElement('script');s.src='data-details.js';s.async=true;
 s.onload=function(){ok();};s.onerror=function(){p=null;fail(new Error('data-details.js failed to load'));};document.head.appendChild(s);})
 .then(function(){var d=window.CITATION_DETAILS||{},w=window.CITATION_DATA.works;for(var i=0;i<w.length;i++){var x=d[w[i].id];
  if(x){w[i].title=x.title;w[i].doi=x.doi;w[i].authors=x.authors;}}window.CITATION_DATA.detailsLoaded=true;
  window.dispatchEvent(new Event('citation-details'));});return p;};
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


def script_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


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


def basemap():
    """Countries as simplified polygons plus English name and continent, without Antarctica."""
    world = json.loads(BASEMAP.read_text(encoding="utf-8"))
    land, countries = [], {}
    for feature in world["features"]:
        props, geom = feature.get("properties", {}), feature["geometry"]
        if props.get("CONTINENT") == "Antarctica":
            continue
        iso = iso_code(props)
        # Name every country, even one too small to keep a shape (Macao).
        if iso and (iso not in countries or props.get("ISO_A2") == iso):
            countries[iso] = {"name": props.get("NAME") or props.get("NAME_EN"), "continent": props.get("CONTINENT"),
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
            "lat": city["lat"], "lon": city["lon"], "country": city["country"]}


def build(data, site):
    """Read a complete snapshot from `data` and write the pages and their data files to `site`."""
    if not (data / "manifest.json").exists():
        raise SystemExit(f"No complete snapshot in {data}; run citestory.py update first.")
    targets = json.loads((data / "targets.json").read_text(encoding="utf-8"))
    manifest = json.loads((data / "manifest.json").read_text(encoding="utf-8"))
    raw = list(json.loads((data / "citing.json").read_text(encoding="utf-8")).values())
    institutions = json.loads((data / "institutions.json").read_text(encoding="utf-8"))
    snapshot = build_views.date.fromisoformat(str(manifest["as_of"])[:10])
    cities, stats = aggregate(raw, institutions)
    if not cities:
        raise SystemExit("No geolocated citation evidence; refusing to create a placeholder map.")
    home = home_place(targets, institutions)
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
                     "doi": t.get("doi"), "publication_year": t.get("publication_year"),
                     "cited_by_count": cited_by.get(t["id"], 0), "scholar_title": t.get("scholar_title")}
                    for t in targets["works"]]
    payload = {"owner": targets["owner"], "home": home, "targets": page_targets,
               "works": core_works, "cities": page_cities(cities), "institutions": names, "stats": stats,
               "manifest": {k: manifest.get(k) for k in ("as_of", "complete", "missing_institution_ids")},
               "scholar_count": len(targets["scholar"]),
               "unmatched": [{"title": r["title"], "citations": r["scholar_citations"]} for r in targets["scholar"] if not r["openalex_ids"]],
               "land": land, "countries": countries}
    site.mkdir(parents=True, exist_ok=True)
    for old in list(site.glob("*.html")) + list(site.glob("*.js")):    # site/ holds build output only
        old.unlink()
    # One shared data file; every page loads it with <script src>, which also works from file://.
    (site / "data.js").write_text("window.CITATION_DATA=" + script_json(payload) + ";\n" + DETAILS_LOADER, encoding="utf-8")
    (site / "data-details.js").write_text("window.CITATION_DETAILS=" + script_json(details) + ";\n", encoding="utf-8")
    owner_ids = {a for t in targets["works"] for a in t.get("owner_authors", [])}
    coauthor_ids = {a for t in targets["works"] for a in t.get("authors", [])} - owner_ids
    # bylines with no OpenAlex author id are recognised as the owner by name (aliases since this field was added)
    owner_name_keys = owner_keys(owner_names(targets["owner"], targets.get("aliases", ())))
    view_stats = build_views.write(site, payload, details, raw, owner_ids, coauthor_ids, owner_name_keys)
    picker = (TEMPLATES / "_picker.html").read_text(encoding="utf-8")   # shared paper picker, inlined where a page asks for it
    shell = (TEMPLATES / "_shell.html").read_text(encoding="utf-8")     # shared tokens, chrome and helpers of the pages on views.js
    css, js = maplibre_tags(TILES["maplibre"])
    for name in PAGES:
        html = (TEMPLATES / name).read_text(encoding="utf-8").replace("<!--SHELL-->", shell).replace("<!--PAPER_PICKER-->", picker)
        if name == "index.html":
            summary = {"owner": payload["owner"], "home": home["label"], "stats": stats, "manifest": {"as_of": manifest.get("as_of")}}
            html = html.replace("__INDEX_SUMMARY__", script_json(summary))
        if name == "atlas.html":
            html = (html.replace("__TILES__", json.dumps(TILES)).replace("__MAPLIBRE_CSS__", css)
                    .replace("__MAPLIBRE_JS__", js))
        (site / name).write_text(html, encoding="utf-8")
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
