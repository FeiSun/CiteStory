"""Data for the Year page: what one calendar year of citations looked like.

`transform` turns the page payload of build_citation_geo.py into `window.CITATION_YEAR` (site/year.js): for the
year the page looks back on, the citing works of that year and the facts the page states about them. Everything the page
says in words is computed here, so the words and the dots cannot disagree. Standard library only.
"""
from collections import Counter, defaultdict
from datetime import date, timedelta
import json
import math
from pathlib import Path
import re

from build_views import clean_name, full_authors, script_json, short_id, work_day
from fetch_citation_geo import name_match, normalized_title as normalized

VENUES = Path(__file__).resolve().parent / "venues.json"
LANDMARKS = Path(__file__).resolve().parent / "landmarks.json"
CITY_ZH = Path(__file__).resolve().parent / "city_names_zh.json"
MARKS = (10, 50, 100, 500, 1000, 5000, 10000, 50000)   # citing works of one paper
TOTAL_MARKS = (100, 1000, 10000, 100000)                # citing works of the whole record
YEAR_ONLY, RETURNING, OWN = 1, 2, 4                     # bits of a work's flags in year.js (not those of views.js)
ARCTIC = 66.5622
EARTH_KM = 40075
# words that carry no topic on their own; a title phrase may not contain them
GENERIC = set("""a an the of for and in on with via to from by using based towards toward is are as at its their it this that
be can into over under between through we our how what why when do does not no or vs versus beyond new novel approach approaches
method methods framework frameworks study toward improving enhancing improved efficient effective simple
de la el los las del para por con una un une des du le les et en em da do dos das com uma um di il per der die und""".split())
KEEP_S = {"news", "bias", "lens", "series", "species", "gas", "class", "process", "access", "analysis", "basis", "thesis",
          "physics", "graphics", "statistics", "dynamics", "robotics", "ethics", "metrics", "semantics", "economics", "mathematics"}
# spellings of one word: "recommender systems" and "recommendation systems" are one phrase
SAME = {"recommender": "recommendation", "modelling": "modeling", "labelled": "labeled", "pre-trained": "pretrained",
        "pre-training": "pretraining", "fine-tuning": "finetuning", "fine-tuned": "finetuned", "multi-modal": "multimodal"}
ONE = {"biases": "bias", "bayes": "bayes", "atlas": "atlas", "analyses": "analysis", "hypotheses": "hypothesis",
       "theses": "thesis", "crises": "crisis", "diagnoses": "diagnosis", "syntheses": "synthesis", "indices": "index",
       "matrices": "matrix", "vertices": "vertex"}
# plurals of words ending in -ie, which the -ies rule below would turn into -y
ONE.update({w + "s": w for w in ("movie", "cookie", "selfie", "zombie", "calorie", "rookie", "goalie", "smoothie",
                                  "brownie", "necktie", "genie", "freebie", "hippie", "prairie", "lingerie")})
CONTINENTS = {"Asia", "North America", "Europe", "Africa", "South America", "Oceania"}
TOP = 5


def load_venues(path=VENUES):
    """[(name, compiled pattern, {year: edition})] from venues.json; an edition must carry a city, a place and a start date."""
    series = []
    for row in json.loads(Path(path).read_text(encoding="utf-8"))["series"]:
        editions = {}
        for year, e in row["editions"].items():
            date.fromisoformat(e["start"])
            if not (-90 <= float(e["lat"]) <= 90 and -180 <= float(e["lon"]) <= 180):
                raise ValueError(f"{row['name']} {year}: latitude or longitude out of range")
            editions[int(year)] = {"city": str(e["city"]), "country": str(e.get("country") or ""),
                                   "lat": float(e["lat"]), "lon": float(e["lon"]), "start": e["start"]}
        series.append((str(row["name"]), re.compile(row["match"], re.I), editions))
    return series


def load_landmarks(path=LANDMARKS):
    """{(city name in lower case, country code): {name, zh, d}} from landmarks.json; `d` may hold only SVG path commands and numbers."""
    marks = {}
    for key, m in json.loads(Path(path).read_text(encoding="utf-8"))["places"].items():
        city, _, iso = key.rpartition(",")
        if not city.strip() or not re.fullmatch(r"[A-Z]{2}", iso.strip()):
            raise ValueError(f"{key}: a landmark is listed as 'City, CC'")
        if not isinstance(m, dict) or not isinstance(m.get("name"), str) or not m["name"] or not isinstance(m.get("d"), str):
            raise ValueError(f"{key}: a landmark needs a name and a drawing")
        if not re.fullmatch(r"M[MLHVCSQTAZmlhvcsqtaz0-9 ,.\-]*\d[MLHVCSQTAZmlhvcsqtaz0-9 ,.\-]*", m["d"]):
            raise ValueError(f"{key}: the drawing is not a plain SVG path")
        marks[(city.strip().lower(), iso.strip())] = {"name": str(m["name"]), "zh": str(m.get("zh") or ""), "d": m["d"]}
    return marks


def load_city_names(path=CITY_ZH):
    """{(city name in lower case, country code): name in Chinese} from city_names_zh.json."""
    names = {}
    for key, zh in json.loads(Path(path).read_text(encoding="utf-8"))["names"].items():
        city, _, iso = key.rpartition(",")
        if not city.strip() or not re.fullmatch(r"[A-Z]{2}", iso.strip()) or not isinstance(zh, str) or not zh.strip():
            raise ValueError(f"{key}: a Chinese name is listed as 'City, CC': name")
        names[(city.strip().lower(), iso.strip())] = zh.strip()
    return names


def chinese_names(year, cities, names, home=None):
    """Adds what the page needs to name places in Chinese: `zh` (city id -> name), and `city_zh` on conference stops."""
    if year.get("review") is None:
        return year
    # two cities of one name in one country (Suzhou in Jiangsu and in Anhui): the list means the most cited one
    best = {}
    for c in cities:
        key = (str(c["name"]).lower(), c.get("country"))
        if key in names and (key not in best or c.get("count", 0) > best[key].get("count", 0)):
            best[key] = c
    year["zh"] = {c["id"]: names[key] for key, c in best.items()}
    for stop in year["review"]["papers"]["route"]:
        zh = names.get((stop["city"].lower(), stop["country"]))
        if zh:
            stop["city_zh"] = zh
    if home and home.get("label") and names.get((str(home["label"]).lower(), home.get("country"))):
        year["home_zh"] = names[(str(home["label"]).lower(), home.get("country"))]
    return year


def venue_stop(venue, year, series):
    """The conference edition a Scholar venue string and a year point to, or None."""
    for name, pattern, editions in series:
        if venue and year in editions and pattern.search(venue):
            return dict(editions[year], name=name)
    return None


def venue_year(venue, listed):
    """The year written in a venue string ("SIGIR 2026", "Proceedings of the 2025 Conference …"), if it is within a
    year of the year listed on the profile; else the listed year. arXiv numbers (2608.13417) are not years."""
    for m in re.finditer(r"(?<![\d.:])((?:19|20)\d\d)(?![\d.])", venue or ""):
        y = int(m.group(1))
        if not isinstance(listed, int) or abs(y - listed) <= 1:
            return y
    return listed if isinstance(listed, int) and not isinstance(listed, bool) else None


def singular(word):
    """"networks" and "network" count as one phrase; "news", "bias" and "series" stay as they are."""
    if word in ONE:
        return ONE[word]
    if word.endswith("sses"):
        return word[:-2]
    if word in KEEP_S or len(word) <= 3 or not word.endswith("s") or word.endswith(("ss", "us", "is", "ics")):
        return word
    if word.endswith("ies") and len(word) > 4:     # studies, strategies, queries
        return word[:-3] + "y"
    if word.endswith("es") and word[:-2].endswith(("ch", "sh", "x")):     # approaches, indexes
        return word[:-2]
    return word[:-1]


def phrases(title, spelled=None):
    """The two- and three-word phrases of an English title, without generic words. Plurals and the spellings in SAME
    are merged; `spelled`, when given, counts how each phrase was written ({phrase: Counter})."""
    title = title or ""
    if any(c.isalpha() and not c.isascii() for c in title):     # titles in other languages and scripts are left out
        return set()
    out = set()
    for clause in re.split(r"[:;?!.,()\[\]]", title.lower()):     # a phrase does not run across punctuation
        words = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", clause)
        written, words = words, [singular(w) for w in words]
        drop = [w in GENERIC or s in GENERIC or w.isdigit() or len(w) < 2 for w, s in zip(written, words)]
        merged = [SAME.get(w, w) for w in words]
        for n in (2, 3):
            for i in range(len(words) - n + 1):
                if not any(drop[i:i + n]):
                    out.add(" ".join(merged[i:i + n]))
                    if spelled is not None:
                        spelled[" ".join(merged[i:i + n])][" ".join(written[i:i + n])] += 1
    return out


def pick_topics(docs, earlier, earlier_n, limit=8, spelled=None):
    """The phrases found in most titles of the year: [{t, n, k: [row], rise}]. `docs` = [(row, phrases)];
    `earlier` counts titles of earlier years per phrase. `rise` = this year's share over the earlier share.
    A phrase is shown the way most titles write it (`spelled`, from `phrases`)."""
    df, members = Counter(), defaultdict(list)
    for k, ph in docs:
        for x in ph:
            df[x] += 1
            members[x].append(k)
    floor = max(3, math.ceil(0.01 * len(docs)))
    cand = {x for x, c in df.items() if c >= floor}
    for x in [x for x in cand if len(x.split()) == 2]:     # "large language" gives way to "large language models"
        if any(len(y.split()) == 3 and f" {x} " in f" {y} " and df[y] >= 0.75 * df[x] for y in cand):
            cand.discard(x)
    picked = []
    for x in sorted(cand, key=lambda x: (-df[x], x)):
        if any(len(set(x.split()) & set(y.split())) >= 2 for y in picked):
            continue
        picked.append(x)
        if len(picked) == limit:
            break
    out = []
    for x in picked:
        rise = None
        if earlier_n >= 100 and earlier[x]:
            rise = round((df[x] / len(docs)) / (earlier[x] / earlier_n), 1)
        shown = max(spelled[x].items(), key=lambda kv: (kv[1], kv[0]))[0] if spelled and spelled.get(x) else x
        out.append({"t": shown, "n": df[x], "k": members[x], "rise": rise, "fresh": earlier_n >= 100 and not earlier[x]})
    return out


def byline(text, owner, owner_names=frozenset()):
    """(co-author names on a Scholar row, True when the row cuts the list short). Scholar writes "F Sun*, JP Liu, …":
    marks such as * are dropped, and the owner is left out by full name, by initials and family name, or by alias."""
    names = [re.sub(r"[^\w\s.'-]", "", n).strip() for n in re.split(r"[,，;；]", text or "")]
    cut = any(n in ("...", "…") or not n and "…" in text for n in names) or "..." in (text or "") or "…" in (text or "")
    parts = owner.lower().split()
    me = {owner.lower()}
    if len(parts) > 1:
        initials = [w[0] for chunk in parts[:-1] for w in re.split(r"[-\s]", chunk) if w]
        me |= {" ".join(initials) + " " + parts[-1], "".join(initials) + " " + parts[-1]}
    out = []
    for n in names:
        if not n or not any(c.isalpha() for c in n):
            continue
        if n.lower() in me or (owner_names and name_match(n, owner_names)):
            continue
        out.append(n)
    return out, cut


def longest_run(days):
    """The longest run of consecutive dates in `days`: (length, first, last), or None."""
    best = run = None
    for d in sorted(days):
        run = (run[0] + 1, run[1], d) if run and d == run[2] + timedelta(days=1) else (1, d, d)
        if not best or run[0] > best[0]:
            best = run
    return best


# writing systems a title can be told apart by; Latin titles in other languages cannot
SCRIPTS = (("ja", r"[\u3040-\u30ff]"), ("ko", r"[\uac00-\ud7af]"), ("zh", r"[\u4e00-\u9fff]"), ("cyrillic", r"[\u0400-\u04ff]"),
           ("arabic", r"[\u0600-\u06ff]"), ("greek", r"[\u0370-\u03ff]"), ("devanagari", r"[\u0900-\u097f]"), ("thai", r"[\u0e00-\u0e7f]"),
           ("hebrew", r"[\u0590-\u05ff]"))


def script_of(title):
    """The writing system of a title that is not written in Latin letters, or None. A title is in a script when that
    script holds a third of its letters or more (a Greek letter in "β-VAE" does not make a Greek title); kana makes it Japanese."""
    letters = [c for c in title or "" if c.isalpha()]
    if not letters:
        return None
    for name, pattern in SCRIPTS:
        n = len(re.findall(pattern, "".join(letters)))
        if name == "zh":
            n += len(re.findall(SCRIPTS[0][1], "".join(letters)))
        if n and (name == "ja" or n >= len(letters) / 3):
            return name
    return None


def name_key(name):
    """Two bylines are one name when they differ only in case, width, spaces or the kind of hyphen."""
    import unicodedata
    return re.sub(r"\s+", " ", re.sub(r"[\u2010-\u2015]", "-", unicodedata.normalize("NFKC", clean_name(name)))).casefold().strip()


def credits_by_name(people, author_name, wrote, regular):
    """The list of names: each name once, in order of first appearance. Namesakes, and one person split across two
    author ids, share a line; their works are put together, and the line is bold when any of them came every year."""
    order, works, bold = {}, defaultdict(set), set()
    for a in people:
        key = name_key(author_name[a])
        order.setdefault(key, clean_name(author_name[a]))
        works[key].update(wrote[a])
        if a in regular:
            bold.add(key)
    keys = list(order)
    return {"credits": [order[k] for k in keys], "regulars": [n for n, k in enumerate(keys) if k in bold],
            "credit_works": [sorted(works[k]) for k in keys]}


def km(lat1, lon1, lat2, lon2):
    r = math.pi / 180
    a, b = math.sin((lat2 - lat1) * r / 2), math.sin((lon2 - lon1) * r / 2)
    h = a * a + math.cos(lat1 * r) * math.cos(lat2 * r) * b * b
    return 2 * 6371.0088 * math.asin(min(1, math.sqrt(h)))


def transform(source, authors, scholar=(), owner_ids=(), coauthor_ids=(), owner_names=frozenset(), venues=(), titles=None, landmarks=None,
              inst_meta=None):
    """Return the CITATION_YEAR object.

    `source` is the CITATION_DATA payload. `authors` maps a work id to every author [{id, name, institutions}].
    `scholar` are the Scholar profile rows ({title, venue, year}): the owner's papers as listed, including those
    OpenAlex does not know. A paper is born in the year written in its venue, else the year on the profile.
    `titles` maps a work id to its title (for the phrases of the year). `owner_ids` and
    `coauthor_ids` are OpenAlex author ids: a work signed by any of them is the owner's circle (flag OWN) and is
    left out of everything said about readers. `owner_names` recognises the owner on a byline without an id. `inst_meta` maps an institution id to `{type, lat, lon}` (its OpenAlex type and place)."""
    owner_ids, coauthor_ids = {short_id(a) for a in owner_ids}, {short_id(a) for a in coauthor_ids}
    circle = owner_ids | coauthor_ids
    snapshot = date.fromisoformat(str(source["manifest"]["as_of"])[:10])
    cities = {c["id"]: c for c in source.get("cities", [])}
    countries = source.get("countries", {})
    institutions = source.get("institutions", {})
    home = source.get("home") or {}
    titles = titles or {}
    inst_meta = inst_meta or {}

    groups, group_of = {}, {}
    for t in source["targets"]:     # versions of one paper share a key, as on the other pages
        title = str(t.get("scholar_title") or t["title"])
        key = t.get("key") or normalized(title) or t["id"]
        g = groups.setdefault(key, {"title": title, "years": [], "works": set()})
        if isinstance(t.get("publication_year"), int):
            g["years"].append(t["publication_year"])
        group_of[t["id"]] = key

    staged, seen = [], set()
    for i, w in enumerate(source["works"]):
        if w["id"] in seen:
            continue
        seen.add(w["id"])
        keys = sorted({group_of[t] for t in w.get("targets", []) if t in group_of})
        if not keys:
            continue
        for k in keys:
            groups[k]["works"].add(w["id"])
        day, year_only = work_day(w, snapshot)
        staged.append({"i": i, "id": w["id"], "keys": keys, "day": day, "yo": year_only,
                       "cities": [c for c in w.get("cities") or [] if c in cities]})
    order = sorted(groups, key=lambda k: (-len(groups[k]["works"]), groups[k]["title"].lower()))
    index = {k: n for n, k in enumerate(order)}
    papers = [{"t": groups[k]["title"], "y": min(groups[k]["years"]) if groups[k]["years"] else None,
               "n": len(groups[k]["works"])} for k in order]

    listed, seen_titles = [], set()     # the owner's papers as the profile lists them
    for r in scholar:
        key = normalized(str(r.get("title") or ""))
        if key and key not in seen_titles:
            seen_titles.add(key)
            venue = str(r.get("venue") or "")
            listed.append({"t": str(r["title"]), "p": index.get(key), "venue": venue, "y": venue_year(venue, r.get("year")),
                           "with": byline(str(r.get("authors") or ""), str(source.get("owner") or ""), owner_names)})
    if not scholar:
        listed = [{"t": p["t"], "p": n, "venue": "", "y": p["y"], "with": ([], False)} for n, p in enumerate(papers)]

    def people(work):
        """(author keys, True when the owner or a co-author signed it)."""
        keys, own = [], False
        for a in authors.get(work["id"]) or []:
            aid = short_id(a.get("id"))
            if aid in circle or (not aid and a.get("name") and owner_names and name_match(a["name"], owner_names)):
                own = True
            elif aid or a.get("name"):
                keys.append(aid or "name:" + a["name"].lower())
        return keys, own

    for w in staged:
        w["p"] = sorted(index[k] for k in w["keys"])
        w["people"], w["own"] = people(w)
    dated = sorted((w for w in staged if w["day"]), key=lambda w: (w["day"], w["id"]))
    undated = len(staged) - len(dated)

    author_name, author_years = {}, defaultdict(set)
    for w in staged:
        for a in authors.get(w["id"]) or []:
            key = short_id(a.get("id")) or ("name:" + a["name"].lower() if a.get("name") else None)
            if key and a.get("name"):
                author_name.setdefault(key, a["name"])
    for w in dated:
        if not w["own"]:
            for a in set(w["people"]):
                author_years[a].add(w["day"].year)

    by_year = defaultdict(list)
    for w in dated:
        by_year[w["day"].year].append(w)
    first_reader = {}    # paper -> its earliest dated reader outside the owner's circle
    for w in dated:
        if not w["own"]:
            for p in w["p"]:
                first_reader.setdefault(p, w)
    paper_countries = defaultdict(set)     # where a paper's readers are, the owner's circle left out
    for w in staged:
        for p in () if w["own"] else w["p"]:
            paper_countries[p].update(cities[c]["country"] for c in w["cities"] if cities[c]["country"])

    def place_name(city_id):
        c = cities[city_id]
        country = countries.get(c["country"], {}).get("name") or c["country"]
        return c["name"] + (", " + country if country and country != c["name"] else "")

    def where(w):
        """The first listed city of a work, as an id (`c`, which the page names in its own language) and in English."""
        return {"c": w["cities"][0], "place": place_name(w["cities"][0])} if w["cities"] else {"c": None, "place": ""}

    def moment(w):
        return {"i": w["i"], "date": w["day"].isoformat(), "yo": 1 if w["yo"] else 0}

    home_ok = isinstance(home.get("lat"), (int, float)) and isinstance(home.get("lon"), (int, float))

    def away(c):
        return km(home["lat"], home["lon"], cities[c]["lat"], cities[c]["lon"])

    earlier_phrases, earlier_titles = Counter(), 0
    years = {}
    seen_people, seen_cities, seen_countries, seen_kinds = set(), set(), set(), set()
    cum, total = Counter(), 0
    last_year_counts = Counter()
    for year in range(min(by_year), snapshot.year + 1) if by_year else []:
        works = by_year.get(year, [])
        counts = Counter(p for w in works for p in w["p"])
        rows, readers = [], Counter()
        year_people, year_cities, year_countries = {}, {}, {}     # dicts keep the order of first appearance
        known = set(seen_people)     # everyone who has cited before this work, earlier this year included
        for w in works:
            bits = (YEAR_ONLY if w["yo"] else 0) | (OWN if w["own"] else 0)
            if not w["own"] and any(a in known for a in w["people"]):
                bits |= RETURNING
            if not w["own"]:
                known.update(w["people"])
            readers["own" if w["own"] else "returning" if bits & RETURNING else "fresh"] += 1
            since = None if w["own"] else min((min(author_years[a]) for a in w["people"] if author_years[a] and not a.startswith("name:")), default=year)
            rows.append([w["i"], (w["day"] - date(year, 1, 1)).days + 1, bits, w["p"], since])
            if not w["own"]:
                year_people.update(dict.fromkeys(w["people"]))
        # the first work from each place: a work with its real date before one known only by its year
        for w in sorted(works, key=lambda w: w["yo"]):     # stable: date order within each kind
            for c in w["cities"]:
                year_cities.setdefault(c, w)
                if cities[c]["country"]:
                    year_countries.setdefault(cities[c]["country"], (w, c))

        # days: the busiest, and the days with nothing at all (only days a paper can be dated to are counted)
        per_day = Counter(w["day"] for w in works if not w["yo"])
        end = min(date(year, 12, 31), snapshot)
        span = (end - date(year, 1, 2)).days + 1      # 1 January is how the source writes "year only"
        quiet = sum(1 for k in range(span) if date(year, 1, 2) + timedelta(days=k) not in per_day)
        busiest = sorted(per_day.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
        run = longest_run(per_day)

        # papers: born this year, and the round numbers passed
        born, route = [], {}
        for paper in listed:
            if paper["y"] != year:
                continue
            p = paper["p"]
            first = first_reader.get(p) if p is not None else None
            born.append({"t": paper["t"], "p": p, "n": papers[p]["n"] if p is not None else 0,
                         "countries": len(paper_countries[p]) if p is not None else 0,
                         "first": dict(moment(first), **where(first)) if first else None})
            stop = venue_stop(paper["venue"], year, venues)
            if stop:
                route.setdefault((stop["start"], stop["name"]), dict(stop, papers=[]))["papers"].append(len(born) - 1)
        route = [route[k] for k in sorted(route)]
        for n, stop in enumerate(route):
            for b in stop["papers"]:
                born[b]["stop"] = n
        for b in born:
            b.setdefault("stop", None)
        # who the new papers were written with, by the names on the profile; a name not on any earlier row is new
        # (names are abbreviated and long lists are cut short there: `cut` says the count is a minimum, `unsure` that a
        # name counted as new may have been hidden in an earlier list)
        mine = [paper for paper in listed if paper["y"] == year and (paper["with"][0] or paper["with"][1])]
        earlier = [paper for paper in listed if isinstance(paper["y"], int) and paper["y"] < year]
        before_names = {n.lower() for paper in earlier for n in paper["with"][0]}
        with_names = {n.lower() for paper in mine for n in paper["with"][0]}
        companions = {"n": len(with_names), "new": len(with_names - before_names), "papers": len(mine),
                      "cut": any(paper["with"][1] for paper in mine),
                      "unsure": any(paper["with"][1] for paper in earlier)} if with_names else None
        # the oldest paper still cited this year
        read = Counter(p for w in works if not w["own"] for p in w["p"])     # citing works from outside the owner's circle
        aged = [(papers[p]["y"], -n, p) for p, n in read.items() if isinstance(papers[p]["y"], int)]
        oldest = {"p": min(aged)[2], "y": min(aged)[0], "n": -min(aged)[1]} if aged else None
        crossed = []
        for p, n in counts.items():
            mark = max((m for m in MARKS if cum[p] < m <= cum[p] + n), default=None)
            if mark:
                crossed.append({"p": p, "mark": mark, "from": cum[p], "to": cum[p] + n})
        crossed.sort(key=lambda c: (-c["mark"], -c["to"], c["p"]))
        total_marks = [dict(moment(works[m - total - 1]), mark=m) for m in TOTAL_MARKS if total < m <= total + len(works)]

        # readers outside the owner's circle
        outside = [w for w in works if not w["own"]]
        position = {w["id"]: k for k, w in enumerate(works)}
        by_author, by_inst = Counter(), Counter()
        for w in outside:
            by_author.update(set(w["people"]))
            by_inst.update({short_id(i) for a in authors.get(w["id"]) or [] for i in a.get("institutions") or [] if i})
        citers = [{"name": clean_name(author_name.get(a, "")), "n": n}
                  for a, n in sorted(by_author.items(), key=lambda kv: (-kv[1], author_name.get(kv[0], "")))
                  if n >= 2 and author_name.get(a)][:TOP]
        insts = [{"name": institutions[i]["display_name"], "n": n}
                 for i, n in sorted(by_inst.items(), key=lambda kv: (-kv[1], kv[0]))
                 if n >= 2 and i in institutions and institutions[i].get("display_name")][:TOP]
        streaks, regular = Counter(), {}
        for a in year_people:
            if not a.startswith("name:"):       # a byline without an id cannot be followed across years
                length = 1
                while year - length in author_years[a]:
                    length += 1
                if length >= 3:
                    streaks[length] += 1
                    regular[a] = length
        # who came every year the longest: up to three names, those with the most citing works this year first
        longest = max(regular.values(), default=0)
        streak_names = {}     # one name per person split across ids: the spelling of the id with the most works
        for a in sorted((a for a, n in regular.items() if n == longest and author_name.get(a)),
                        key=lambda a: (-by_author[a], author_name[a])):
            streak_names.setdefault(name_key(author_name[a]), clean_name(author_name[a]))
        streak_names = list(streak_names.values())[:3]
        # people back after five years or more without citing
        gaps = {}
        for a in year_people:
            if not a.startswith("name:"):
                before = [y for y in author_years[a] if y < year]
                if before and year - max(before) >= 5:
                    gaps[a] = year - max(before)
        far_gap = max(gaps.values(), default=0)
        back = {"n": len(gaps), "gap": far_gap,
                "names": sorted(clean_name(author_name[a]) for a, g in gaps.items() if g == far_gap and author_name.get(a))[:3],
                "last": [[y, n] for y, n in sorted(Counter(year - g for g in gaps.values()).items())]} if gaps else None
        # the citing work that cites most of these papers at once
        wide = max(outside, key=lambda w: (len(w["p"]), -w["i"]), default=None)
        spans = [papers[p]["y"] for p in wide["p"] if isinstance(papers[p]["y"], int)] if wide else []
        deep = {"i": wide["i"], "n": len(wide["p"]), "from": min(spans), "to": max(spans)} if wide and len(wide["p"]) >= 4 and spans else None
        # the names as credited: footnote marks at the end ("Rui Wang*") are cut off below
        credited = [a for a in year_people if author_name.get(a) and not re.search(r"\d{4}", author_name[a])]     # a byline with a number in it is not a name
        wrote = defaultdict(list)     # the works of each name, by position in `works`
        for w in outside:
            for a in dict.fromkeys(w["people"]):
                wrote[a].append(position[w["id"]])
        # institutions out of the usual: hospitals, and archives, libraries and museums
        unusual = {"healthcare": Counter(), "archive": Counter()}
        for w in outside:
            for kind, ids in ((k, {short_id(i) for a in authors.get(w["id"]) or [] for i in a.get("institutions") or []
                                   if i and (inst_meta.get(short_id(i)) or {}).get("type") == k}) for k in unusual):
                if ids:
                    unusual[kind]["n"] += 1
                    unusual[kind].update(ids)
        desks = {}
        for kind, c in unusual.items():
            if c.get("n"):
                n = c.pop("n")
                ranked = [i for i, _ in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))]
                meta = {i: inst_meta.get(i) or {} for i in ranked}
                desks[kind] = {"n": n, "names": [institutions[i]["display_name"] for i in ranked if institutions.get(i, {}).get("display_name")][:3],
                               # where each of them is: [lon, lat, name, works]
                               "at": [[round(meta[i]["lon"], 3), round(meta[i]["lat"], 3), institutions.get(i, {}).get("display_name") or "", c[i]]
                                      for i in ranked if isinstance(meta[i].get("lat"), (int, float)) and isinstance(meta[i].get("lon"), (int, float))]}
        by_script = defaultdict(list)
        for w in outside:
            s = script_of(titles.get(w["id"]))
            if s:
                by_script[s].append(position[w["id"]])

        # places
        new_cities = [c for c in year_cities if c not in seen_cities]
        new_countries = [{"iso": iso, "c": c, "p": w["p"], **moment(w)}
                         for iso, (w, c) in year_countries.items() if iso not in seen_countries]
        new_countries.sort(key=lambda r: (r["yo"], r["date"], r["iso"]))     # those known only by year come last
        for r in new_countries:     # a drawing of the city the paper arrived in, when landmarks.json has one
            mark = (landmarks or {}).get((str(cities[r["c"]]["name"]).lower(), cities[r["c"]]["country"]))
            if mark:
                r["art"] = mark
        opened = Counter(p for c in new_cities for p in year_cities[c]["p"])
        places = {"countries": len(year_countries), "cities": len(year_cities), "new_cities": new_cities,
                  "new_countries": new_countries,
                  "new_works": sum(1 for w in works if any(c not in seen_cities for c in w["cities"])),
                  "opened": [[p, n] for p, n in sorted(opened.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP]],
                  "far": None, "near": None, "firsts": []}
        if home_ok:
            if year_cities:
                far = max(year_cities, key=lambda c: (away(c), c))
                places["far"] = dict(moment(year_cities[far]), c=far, km=round(away(far)), p=year_cities[far]["p"])
            if new_cities:
                near = min(new_cities, key=lambda c: (away(c), c))
                places["near"] = dict(moment(year_cities[near]), c=near, km=round(away(near)))
        for c, w in year_cities.items():     # insertion order is date order (dated works first), so the first of each kind wins
            continent = countries.get(cities[c]["country"], {}).get("continent")
            kinds = [("continent", continent if continent in CONTINENTS else None)]
            if cities[c]["lat"] < 0:
                kinds.append(("south", True))
            if cities[c]["lat"] > ARCTIC:
                kinds.append(("arctic", True))
            for kind in kinds:
                if kind[1] and kind not in seen_kinds:
                    seen_kinds.add(kind)
                    places["firsts"].append(dict(moment(w), kind=kind[0], c=c,
                                                 name=kind[1] if kind[0] == "continent" else ""))

        # the first and the latest reader of the year, the distance to all readers, the phrases of their titles
        exact = [w for w in outside if not w["yo"]]
        ends = {k: dict(moment(w), **where(w), p=w["p"])
                for k, w in (("first", exact[0] if exact else None), ("last", exact[-1] if exact else None)) if w}
        reach = [min(away(c) for c in w["cities"]) for w in outside if w["cities"]] if home_ok else []
        distance = {"km": round(sum(reach)), "n": len(reach), "earths": round(sum(reach) / EARTH_KM, 1)} if reach else None
        spelled = defaultdict(Counter)
        docs = [(position[w["id"]], phrases(titles.get(w["id"]), spelled)) for w in outside]
        docs = [d for d in docs if d[1]]
        topics = pick_topics(docs, earlier_phrases, earlier_titles, spelled=spelled) if len(docs) >= 30 else []

        years[str(year)] = {
            "n": len(works), "yo": sum(1 for w in works if w["yo"]), "before": total, "complete": year < snapshot.year,
            "works": rows,
            "days": {"quiet": quiet, "span": span, "busiest": [[d.isoformat(), n] for d, n in busiest],
                     "run": {"n": run[0], "start": run[1].isoformat(), "end": run[2].isoformat()} if run else None},
            "papers": {"cited": len(counts), "counts": [[p, n, last_year_counts[p]] for p, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))],
                       "born": born, "route": route, "crossed": crossed,
                       "oldest": oldest, "companions": companions},
            "marks": total_marks,
            "readers": {"returning": readers["returning"], "fresh": readers["fresh"], "own": readers["own"],
                        "people": len(year_people), "new_people": len(set(year_people) - seen_people),
                        "citers": citers, "insts": insts, "streaks": sorted(streaks.items()), "deep": deep, "back": back,
                        "streak_names": streak_names},
            "places": places, "ends": ends, "distance": distance, "topics": topics, "desks": desks,
            "scripts": [[s, len(ks), ks] for s, ks in sorted(by_script.items(), key=lambda kv: (-len(kv[1]), kv[0]))],
            **credits_by_name(credited, author_name, wrote, regular),
        }
        for _, ph in docs:
            earlier_phrases.update(ph)
        earlier_titles += len(docs)
        seen_people.update(a for a in year_people if not a.startswith("name:"))     # a byline without an id is not followed across years
        seen_cities.update(year_cities)
        seen_countries.update(year_countries)
        for p, n in counts.items():
            cum[p] += n
        total += len(works)
        last_year_counts = counts

    return {"owner": str(source.get("owner") or ""), "snapshot": str(source["manifest"]["as_of"]),
            "papers": [{"t": p["t"], "y": p["y"], "n": p["n"]} for p in papers],
            "stats": {"works": len(staged), "undated": undated}, "years": years}


def latest(full):
    """What the page loads: the one year it looks back on, and the little it needs of the years before.

    The year is the snapshot's; in January and February it is the year just ended, if that year has citing works."""
    snapshot = date.fromisoformat(str(full["snapshot"])[:10])
    with_works = [int(y) for y, d in full["years"].items() if d["n"]]
    if not with_works:
        return dict({k: full[k] for k in ("owner", "snapshot", "papers", "stats")}, year=None, review=None, history=[], known=[])
    year = max(with_works)
    if year == snapshot.year and snapshot.month <= 2 and year - 1 in with_works:
        year -= 1
    return {"owner": full["owner"], "snapshot": full["snapshot"], "papers": full["papers"], "stats": full["stats"],
            "year": year, "review": full["years"][str(year)],
            "history": [[int(y), d["n"]] for y, d in sorted(full["years"].items(), key=lambda kv: int(kv[0])) if int(y) <= year],
            "known": [c for y, d in full["years"].items() if int(y) < year for c in d["places"]["new_cities"]]}


def write(output, source, raw_works, scholar=(), owner_ids=(), coauthor_ids=(), owner_names=frozenset(), inst_meta=None):
    titles = {short_id(w.get("id")): w.get("title") for w in raw_works}
    year = latest(transform(source, full_authors(raw_works), scholar, owner_ids, coauthor_ids, owner_names, load_venues(), titles, load_landmarks(),
                            inst_meta))
    chinese_names(year, source["cities"], load_city_names(), source.get("home"))
    (output / "year.js").write_text("window.CITATION_YEAR=" + script_json(year) + ";\n", encoding="utf-8")
    return {"year": year["year"]}
