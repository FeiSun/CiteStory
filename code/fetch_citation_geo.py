#!/usr/bin/env python3
"""Fetch one profile's data: the Scholar paper list, its OpenAlex matches, every citing work and its institutions.

A refresh is built in `<data>/pending/` and moved into `<data>/` only when complete, so an interrupted run never
leaves the site half-updated. Run it through `code/citestory.py`.
"""
import hashlib
import html
import http.client
import json
import os
import re
import shutil
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parents[1]          # repository root, holds .env
FIELDS = "id,title,doi,publication_year,publication_date,authorships,referenced_works"
SEARCH_FIELDS = "id,title,doi,publication_year,cited_by_count,authorships"
CHUNK = 40          # OpenAlex accepts at most 100 OR values in one filter
PER_PAGE = 200
SAVE_PAGES = 10      # citing pages between saves of pending/citing.json
REQUEST_BUDGET = 2000
BYTE_BUDGET = 2_000_000_000
SNAPSHOT_FILES = ("targets.json", "citing.json", "manifest.json")


def normalized_title(value):
    return "".join(c for c in unicodedata.normalize("NFKC", value or "").casefold() if c.isalnum())


CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af\u3040-\u30ff]+")


def name_tokens(value):
    return [normalized_title(t) for t in re.split(r"[\s,.\-‐]+", value or "") if normalized_title(t)]


def name_keys(value):
    """(family, given) readings of a name, with the family name first or last and middle names dropped.

    "Michael I. Jordan" -> (jordan, michaeli), (jordan, michael), (michael, ijordan), (michael, i)."""
    t = name_tokens(value)
    if len(t) < 2:
        return {(t[0], "")} if t else set()
    keys = {(t[-1], "".join(t[:-1])), (t[-1], t[0]), (t[0], "".join(t[1:])), (t[0], t[1])}
    if all(CJK.fullmatch(x) for x in t):     # "王 伟" is also written "王伟"
        keys.add(("".join(t), ""))
    return keys


def owner_keys(names):
    """Keys that identify the owner: every reading of each name, plus the initial of the given name."""
    keys = set()
    for n in names:
        for family, given in name_keys(n):
            keys.add((family, given))
            if given:
                keys.add((family, given[0]))
        t = name_tokens(n)
        if len(t) >= 3:     # "Jean-Pierre Dupont" is also "JP Dupont" or "J.-P. Dupont"
            keys.update({(t[-1], "".join(x[0] for x in t[:-1])), (t[0], "".join(x[0] for x in t[1:]))})
    return keys


def name_match(name, keys):
    return bool(name_keys(name) & keys)


def owner_names(scholar_name, aliases=()):
    """The Scholar display name without titles or notes ("Wei Wang (王伟), IEEE Fellow"), plus its parts and aliases."""
    names = []
    base = re.sub(r"\(.*?\)|（.*?）", " ", scholar_name or "")
    base = re.sub(r"^\s*(?:(?:assoc\.?|asst\.?|associate|assistant|prof\.?|professor|dr\.?)\s+)+", "",
                  base.split(",")[0], flags=re.I).strip()
    if base:
        names.append(base)
    for a, b in re.findall(r"\((.*?)\)|（(.*?)）", scholar_name or ""):
        if (a or b).strip():
            names.append((a or b).strip())
    names += [a for a in aliases if a]
    return list(dict.fromkeys(names))


def _text(fragment):
    return html.unescape(re.sub("<[^>]+>", "", fragment)).replace("\xa0", " ").strip()


def scholar_profile(source):
    """Parse a Google Scholar profile page (saved or fetched): owner name and every listed article row."""
    owner = next((n for n in (_text(x) for x in re.findall(r"id=\"?gsc_prf_in\"?[^>]*>(.*?)</div>", source, re.S)) if n), "")
    papers = []
    for row in re.split(r'<tr class="?gsc_a_tr', source)[1:]:
        row = row.split("</tbody>")[0]
        title = re.search(r"class=\"?gsc_a_at\"?[^>]*>(.*?)</a>", row, re.S)
        if not title:
            continue
        grays = re.findall(r"<div class=\"?gs_gray\"?>(.*?)</div>", row, re.S)
        cites = re.search(r"class=\"gsc_a_ac[^\"]*\"[^>]*>(\d*)</a>", row)
        year = re.search(r"class=\"gsc_a_h gsc_a_hc[^\"]*\"[^>]*>(\d*)</span>", row)
        link = re.search(r"citation_for_view=([\w:\-]+)", row)
        papers.append({"title": _text(title.group(1)),
                       "authors": _text(grays[0]) if grays else "",
                       "venue": _text(re.sub(r"<span class=\"gs_oph.*?</span>", "", grays[1], flags=re.S)) if len(grays) > 1 else "",
                       "scholar_citations": int(cites.group(1)) if cites and cites.group(1) else 0,
                       "year": int(year.group(1)) if year and year.group(1) else None,
                       "scholar_id": link.group(1) if link else None})
    total = re.search(r"id=\"?gsc_a_nn\"?[^>]*>(?:Articles )?1[–-](\d+)", source)
    more = re.search(r"id=\"?gsc_bpf_more\"?[^>]*>", source)
    return {"owner": owner, "papers": papers, "listed": int(total.group(1)) if total else None,
            "more": bool(more and "disabled" not in more.group(0))}


class APIError(Exception):
    pass


class ScholarBlocked(APIError):
    pass


def scholar_user(url):
    user = parse_qs(urlparse(url).query).get("user", [""])[0]
    if not re.fullmatch(r"[\w-]{6,20}", user):
        raise APIError("The Scholar URL has no user=… parameter, e.g. https://scholar.google.com/citations?user=XXXXXXXXXXXX")
    return user


def fetch_scholar(url, opener=None, pause=2.0):
    """Every article row of a public Scholar profile, 100 rows per request. Raises ScholarBlocked on a CAPTCHA or refusal."""
    opener = opener or (lambda u: urlopen(Request(u, headers={"User-Agent": "Mozilla/5.0 (compatible; citestory)",
                                                               "Accept-Language": "en"}), timeout=30))
    user, owner, papers = scholar_user(url), "", []
    for page in range(30):
        query = urlencode({"user": user, "hl": "en", "cstart": page * 100, "pagesize": 100})
        try:
            with opener("https://scholar.google.com/citations?" + query) as r:
                body = r.read(20_000_001).decode("utf-8", "replace")
        except HTTPError as exc:
            raise ScholarBlocked(f"Google Scholar answered HTTP {exc.code}.") from None
        except (OSError, http.client.HTTPException):     # URLError, socket.timeout (not TimeoutError on 3.9), resets
            raise ScholarBlocked("Google Scholar could not be reached.") from None
        if "gs_captcha" in body or "unusual traffic" in body or "gsc_prf_in" not in body:
            raise ScholarBlocked("Google Scholar asked for a CAPTCHA.")
        part = scholar_profile(body)
        owner = owner or part["owner"]
        papers += part["papers"]
        if len(part["papers"]) < 100:
            return {"owner": owner, "papers": papers, "listed": len(papers), "more": False}
        time.sleep(pause)
    raise APIError("More than 3,000 Scholar rows; stopping.")


def title_numbers(value):
    """Numbers and Roman numerals in a title ("Part II", "(2024)", "v2"), which tell a series or an edition apart."""
    words = re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", value or "").casefold())
    return [w for w in words if re.fullmatch(r"[ivx]+", w)] + re.findall(r"\d+", " ".join(words))


def title_match(a, b):
    na, nb = normalized_title(a), normalized_title(b)
    if not na or not nb:
        return False
    return na == nb or (min(len(na), len(nb)) >= 20 and title_numbers(a) == title_numbers(b)
                        and SequenceMatcher(None, na, nb).ratio() >= 0.95)


def owner_authorships(work, keys, author_ids=()):
    out = []
    for a in work.get("authorships", []):
        aid = (a.get("author") or {}).get("id")
        names = [(a.get("author") or {}).get("display_name"), a.get("raw_author_name")]
        if (aid and short(aid) in author_ids) or any(name_match(n, keys) for n in names if n):
            out.append(a)
    return out


def short(oa_id):
    return oa_id.rsplit("/", 1)[-1] if isinstance(oa_id, str) else oa_id


def api_key(env_files=(HERE / ".env",)):
    """Return the key from the process environment, else from the repository's .env (never printed or stored)."""
    if os.environ.get("OPENALEX_API_KEY"):
        return os.environ["OPENALEX_API_KEY"]
    for env_file in [env_files] if isinstance(env_files, Path) else env_files:
        if env_file.is_file():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                line = line[7:] if line.startswith("export ") else line
                name, sep, value = line.partition("=")
                if sep and name.strip() == "OPENALEX_API_KEY":
                    return value.strip().strip("'\"") or None
    return None


class Client:
    def __init__(self, log_folder, cache=None, max_requests=REQUEST_BUDGET):
        self.folder = log_folder
        self.cache = cache
        self.calls = 0
        self.bytes = 0
        self.max_requests = max_requests
        self.key = api_key()

    def get(self, endpoint, params=None, cache=True):
        params = params or {}
        query = endpoint + "?" + urlencode(params)
        path = self.cache / (hashlib.sha256(query.encode()).hexdigest() + ".json") if (cache and self.cache) else None
        if path and path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        headers = {"User-Agent": "citestory/2.0", "Accept": "application/json"}
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        for attempt in range(3):
            if self.calls >= self.max_requests or self.bytes >= BYTE_BUDGET:
                raise APIError("Request budget for this run reached; run again to resume.")
            time.sleep(0.15)
            self.calls += 1
            try:     # only the request and its body: a local disk error below is not a network error to retry
                with urlopen(Request("https://api.openalex.org/" + query, headers=headers), timeout=60) as r:
                    body = r.read(40_000_001)
                self.bytes += len(body)
                if len(body) > 40_000_000:
                    raise APIError("Response exceeds the 40 MB safety ceiling.")
                result = json.loads(body)
            except HTTPError as exc:
                self.log(endpoint, f"http {exc.code}")
                if exc.code == 429:
                    delay = exc.headers.get("Retry-After", "") if exc.headers else ""
                    if attempt == 0 and delay.isdigit() and int(delay) <= 45:
                        time.sleep(max(1, int(delay)))
                        continue
                    raise APIError("OpenAlex HTTP 429: rate limited; no further requests made. Resume later or set OPENALEX_API_KEY.") from None
                if exc.code in (500, 502, 503, 504) and attempt < 2:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise APIError(f"OpenAlex HTTP {exc.code}; response body and URL omitted.") from None
            except (OSError, http.client.HTTPException, ValueError):     # network, timeout, cut or garbled body
                self.log(endpoint, "network error")
                if attempt == 2:
                    raise APIError("OpenAlex connection failed; run again to resume.") from None
                time.sleep(3)
                continue
            # Do not persist notices or request metadata, which may contain credentials.
            if "meta" in result:
                clean = {"meta": {k: result["meta"].get(k) for k in ("count", "next_cursor")}}
                clean.update({k: result[k] for k in ("results", "group_by") if k in result})
            else:
                clean = result
            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(clean, ensure_ascii=False), encoding="utf-8")
            self.log(endpoint, "ok")
            return clean
        raise APIError("OpenAlex request incomplete.")

    def log(self, endpoint, outcome):
        """Append one line per network request (no URL parameters, no credentials) for auditing."""
        self.folder.mkdir(parents=True, exist_ok=True)
        with (self.folder / "requests.log").open("a", encoding="utf-8") as stream:
            stream.write(f"{datetime.now(timezone.utc).isoformat()}\t{endpoint}\t{outcome}\n")


def read_json(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path, value, indent=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=indent, separators=None if indent else (",", ":")), encoding="utf-8")
    tmp.replace(path)


PREPRINT_VENUE = re.compile(r"arxiv|preprint|\bcorr\b|biorxiv|medrxiv|ssrn", re.I)
ARXIV_ID = re.compile(r"(?:arxiv[:\s.]*|\bcorr\b.*?abs/)(\d{4}\.\d{4,5})", re.I)


def awaiting_published(paper, hits, this_year):
    """Scholar shows a published venue for a recent row, but every matched work is a preprint: OpenAlex often adds the
    published version a month or two after Scholar merges it, so the row is searched again on each update."""
    return (bool(hits) and (paper.get("year") or 0) >= this_year - 1 and not PREPRINT_VENUE.search(paper.get("venue") or "")
            and all(not h.get("doi") or "10.48550/" in str(h.get("doi")).lower() for h in hits))


POOL_MIN_ROWS = 5         # rows still to search before listing the owner's works pays off
POOL_MAX_WORKS = 2000     # more works than this under the ids: they likely merge other people; search instead


def owner_pool(client, ids):
    """Every OpenAlex work under these author ids, one request per 200 works; [] when there are too many."""
    ids, out = sorted(ids), []
    for i in range(0, len(ids), 50):
        cursor, first = "*", True
        while cursor:
            page = client.get("works", {"filter": "author.id:" + "|".join(ids[i:i + 50]), "per_page": 200,
                                        "cursor": cursor, "select": SEARCH_FIELDS})
            if first and (page["meta"].get("count") or 0) > POOL_MAX_WORKS:
                return []
            first = False
            out += page["results"]
            cursor = page["meta"].get("next_cursor") if page["results"] else None
    return out


def hit_record(w, mine, paper):
    ids = lambda authorships: [short((a.get("author") or {}).get("id")) for a in authorships if (a.get("author") or {}).get("id")]
    return {"id": w["id"], "title": w.get("title"), "doi": w.get("doi"),
            "publication_year": w.get("publication_year"), "cited_by_count": w.get("cited_by_count"),
            "scholar_title": paper["title"], "authors": ids(w.get("authorships", [])), "owner_authors": ids(mine),
            "owner_institutions": [i["id"] for a in mine for i in a.get("institutions", []) if i.get("id")]}


def match_papers(client, profile, previous=None, owner_ids=()):
    """Match each Scholar row to OpenAlex works whose title matches and whose byline has the owner.

    Rows already matched in the previous snapshot keep their works without a new search, unless the row's venue or
    year changed, or the row still waits for its published version (awaiting_published): Scholar shows the published
    venue once it merges a preprint with its published version, and the published version is often a separate OpenAlex
    work.

    A row to match is first looked for among the works listed under the owner's OpenAlex author ids (from the profile,
    the previous snapshot, and the rows matched so far): one request covers 200 works, where a title search costs one
    request per row. Only a row with nothing new there, or with only a preprint while Scholar shows the published venue,
    is searched by title, and a row the title search misses is looked up by the arXiv id its venue names, if any. Ids
    found late in the run are listed at the end, and every row matched in this run takes any further version from the
    full list."""
    owner = profile["owner"]
    keys = owner_keys(owner_names(owner, profile.get("aliases", ())))
    known = {}
    for w in (previous or {}).get("works", []):
        if "authors" in w:       # written by this version of the code
            known.setdefault(normalized_title(w.get("scholar_title")), []).append(w)
    before = {normalized_title(r.get("title")): r for r in (previous or {}).get("scholar", [])}
    this_year = datetime.now(timezone.utc).year
    plan = []
    for paper in profile["papers"]:
        key = normalized_title(paper["title"])
        hits, old = known.get(key), before.get(key)
        moved = old is not None and (old.get("venue"), old.get("year")) != (paper.get("venue"), paper.get("year"))
        plan.append((paper, hits, hits is None or moved or awaiting_published(paper, hits, this_year)))
    ids = set(owner_ids) | {a for ws in known.values() for w in ws for a in w.get("owner_authors", [])}
    pooled, pool = set(), []
    left = sum(need for _, _, need in plan)
    accepted, rows, plan_hits = {}, [], []
    for paper, hits, need in plan:
        if need:
            hits = list(hits or [])

            def add(works):
                n = 0
                for w in works:
                    mine = owner_authorships(w, keys, ids)
                    if mine and all(h["id"] != w["id"] for h in hits):
                        hits.append(hit_record(w, mine, paper))
                        n += 1
                return n

            if ids - pooled and (left >= POOL_MIN_ROWS or set(owner_ids) - pooled):     # ids the profile names: always
                pool += owner_pool(client, ids - pooled)
                pooled |= ids
            if not add([w for w in pool if title_match(w.get("title"), paper["title"])]) \
                    or awaiting_published(paper, hits, this_year):     # the list holds only a preprint: search too
                batch = client.get("works", {"search": paper["title"], "per_page": 10, "select": SEARCH_FIELDS})
                if not add([w for w in batch["results"] if title_match(w.get("title"), paper["title"])]) and not hits:
                    arxiv = ARXIV_ID.search(paper.get("venue") or "")
                    if arxiv:     # a title search ranks a new paper with a common title low; the venue names its arXiv id
                        add(client.get("works", {"filter": "doi:10.48550/arxiv." + arxiv.group(1),
                                                 "select": SEARCH_FIELDS})["results"])
            ids |= {a for h in hits for a in h.get("owner_authors", [])}
            left -= 1
        plan_hits.append((paper, hits, need))
    # ids found late in the run widen the list; rows matched this run take any further version from it (no request)
    if ids - pooled and pooled:
        pool += owner_pool(client, ids - pooled)
    for paper, hits, need in plan_hits:
        if need:
            for w in pool:
                mine = owner_authorships(w, keys, ids)
                if mine and title_match(w.get("title"), paper["title"]) and all(h["id"] != w["id"] for h in hits):
                    hits.append(hit_record(w, mine, paper))
        for w in hits:
            accepted[w["id"]] = dict(w, scholar_title=paper["title"])
        rows.append(dict(paper, openalex_ids=[w["id"] for w in hits]))
    return accepted, rows


def guess_home(works, institutions=None):
    """The owner's most frequent affiliation in their three most recent years of matched works (any year if none).

    Given the institution records, only one with a city counts: an umbrella body (an academy, a national lab
    network) is often listed beside the institute and has no city."""
    def placed(i):
        geo = ((institutions or {}).get(i) or {}).get("geo") or {}
        return institutions is None or bool(geo.get("city") and geo.get("latitude") is not None and geo.get("longitude") is not None)
    years = sorted({w.get("publication_year") or 0 for w in works if any(map(placed, w.get("owner_institutions", [])))},
                   reverse=True)[:3]
    counts = Counter(i for w in works if (w.get("publication_year") or 0) in years for i in w.get("owner_institutions", []) if placed(i))
    return counts.most_common(1)[0][0] if counts else None


def author_id(value, kind="a"):
    """An OpenAlex author id as OpenAlex writes it ("A5101467161"), from an id, a URL or a page address
    (any case, trailing slash allowed). kind="i" reads an institution id the same way."""
    m = re.search(r"\b(" + kind + r"\d+)/?$", str(value or "").strip(), re.I)
    return m.group(1).upper() if m else None


def compact_work(work, targets):
    return {"id": work["id"], "title": work.get("title"), "doi": work.get("doi"),
            "year": work.get("publication_year"), "date": work.get("publication_date"),
            "targets": sorted(set(work.get("referenced_works", [])) & targets),
            "possibly_truncated_authors": len(work.get("authorships", [])) >= 100,
            "authors": [{"id": (a.get("author") or {}).get("id"),
                         "name": (a.get("author") or {}).get("display_name"),
                         "institutions": sorted({i["id"] for i in a.get("institutions", []) if i.get("id")})}
                        for a in work.get("authorships", [])]}


def collect_citing(client, pending, target_ids):
    """Page every work citing the targets into pending/citing.json, resumable from the cursor in pending/manifest.json.

    The file is rewritten whole, so it is saved every SAVE_PAGES pages (and before any error ends the run) rather than
    every page, which for 50,000 citing works would write gigabytes. Works and cursors are saved together; a resumed
    run fetches again only the pages since the last save, and merging those works twice changes nothing."""
    path, manifest_path = pending / "citing.json", pending / "manifest.json"
    works = read_json(path, {})
    manifest = read_json(manifest_path, {})
    ordered = sorted(target_ids)
    chunks = [ordered[i:i + CHUNK] for i in range(0, len(ordered), CHUNK)]
    queries = manifest.setdefault("queries", {})
    unsaved = 0
    try:
        for index, chunk in enumerate(chunks):
            state = queries.setdefault(str(index), {"cursor": "*", "received": 0, "complete": False})
            criterion = "cites:" + "|".join(short(x) for x in chunk)
            while not state["complete"]:
                batch = client.get("works", {"filter": criterion, "select": FIELDS, "per_page": PER_PAGE,
                                             "cursor": state["cursor"]}, cache=False)
                for w in batch["results"]:
                    row = compact_work(w, target_ids)
                    if not row["targets"]:
                        continue
                    if w["id"] in works:   # a work citing papers in several chunks keeps every target
                        row["targets"] = sorted(set(row["targets"]) | set(works[w["id"]]["targets"]))
                    works[w["id"]] = row
                if state["cursor"] == "*" or not state.get("expected"):     # the count when the listing began: a run
                    state["expected"] = batch["meta"]["count"]                 # resumed days later sees newer works
                state.update(received=state["received"] + len(batch["results"]), cursor=batch["meta"].get("next_cursor"))
                state["complete"] = not batch["results"] or not state["cursor"]
                unsaved += 1
                # OpenAlex's count is an estimate: a few works short at the end is normal, many is a broken listing
                if state["complete"] and state["received"] < 0.99 * (state.get("expected") or 0):
                    sent = state["received"]
                    state.update(complete=False, cursor="*", received=0)
                    raise APIError(f"OpenAlex listed {state['expected']} works citing group {index + 1} but sent only "
                                   f"{sent}; run again to retry that group.")
                if state["complete"] or unsaved >= SAVE_PAGES:
                    write_json(path, works)
                    write_json(manifest_path, manifest, indent=2)
                    unsaved = 0
                print(f"  citing works, group {index + 1}/{len(chunks)}: {state['received']}/{state['expected']}; "
                      f"{len(works)} unique", flush=True)
    finally:
        if unsaved:
            write_json(path, works)
            write_json(manifest_path, manifest, indent=2)
    return works


def fetch_institutions(client, data, works, extra=()):
    """Cache geo records for every institution named on the citing works; return ids still missing."""
    institution_path = data / "institutions.json"
    institutions = read_json(institution_path, {})
    named = {i for w in works.values() for a in w["authors"] for i in a["institutions"]}
    pending = sorted((named | {i for i in extra if i}) - set(institutions))
    for offset in range(0, len(pending), 80):
        ids = [short(v) for v in pending[offset:offset + 80]]
        batch = client.get("institutions", {"filter": "openalex_id:" + "|".join(ids),
            "per_page": 100, "select": "id,display_name,country_code,geo,ror,type"}, cache=False)
        for i in batch["results"]:
            institutions[i["id"]] = i
        write_json(institution_path, institutions)
        print(f"  institutions: {len(institutions)}", flush=True)
    return sorted(named - set(institutions))


def get_paper_list(config):
    """The Scholar list: from the profile URL when given, else (or when Google refuses) from the saved page."""
    saved = config.get("scholar_html")
    if config.get("scholar_url"):
        try:
            result = fetch_scholar(config["scholar_url"])
            result["source"] = "url"
            return result
        except ScholarBlocked as exc:
            if not saved or not Path(saved).is_file():
                raise APIError(f"{exc} Save the profile page (click “Show more” until every article is listed) "
                               "and set \"scholar_html\" in profile.json.") from None
            print(f"{exc} Using the saved page {Path(saved).name} instead.", flush=True)
    if not saved or not Path(saved).is_file():
        raise APIError("profile.json needs \"scholar_url\" or a saved \"scholar_html\" page.")
    result = scholar_profile(Path(saved).read_text(encoding="utf-8"))
    result["source"] = "saved page"
    if result["more"] or (result["listed"] and result["listed"] > len(result["papers"])):
        print("Warning: the saved Scholar page does not list every article; click “Show more” until it is greyed out, "
              "then save it again.", flush=True)
    return result


def refresh(config, data, restart=False, max_requests=REQUEST_BUDGET):
    """Fetch a new snapshot into data/pending/ and promote it to data/ when complete. Returns True when promoted."""
    pending = data / "pending"
    if restart and pending.exists():
        shutil.rmtree(pending)
    client = Client(data, cache=pending / "cache", max_requests=max_requests)
    try:
        manifest = read_json(pending / "manifest.json")
        if manifest is None:
            scholar = get_paper_list(config)
            owner = config.get("name") or scholar["owner"]
            if not owner or not scholar["papers"]:
                raise APIError("No owner name or article rows found on the Scholar profile.")
            print(f"Scholar ({scholar['source']}): {owner}, {len(scholar['papers'])} articles.", flush=True)
            profile = {"owner": owner, "papers": scholar["papers"], "aliases": config.get("aliases", [])}
            author_ids = sorted({a for a in map(author_id, config.get("openalex_author_ids", [])) if a})
            accepted, rows = match_papers(client, profile, read_json(data / "targets.json"), set(author_ids))
            if not accepted:
                raise APIError("No Scholar article matched an OpenAlex work with the owner in its byline; "
                               "add the byline spelling to \"aliases\" in profile.json.")
            works = list(accepted.values())
            home = author_id(config.get("home"), "i")
            if config.get("home") and not home:
                raise APIError("\"home\" in profile.json is not an OpenAlex institution id (like \"I4210090176\").")
            home = ("https://openalex.org/" + home) if home else guess_home(works)
            targets = {"owner": owner, "aliases": config.get("aliases", []), "openalex_author_ids": author_ids,
                       "home_set": bool(config.get("home")), "source": scholar["source"],
                       "scholar_listed": scholar["listed"],
                       "scholar": rows, "works": works, "home": home}
            write_json(pending / "targets.json", targets, indent=2)
            matched = sum(1 for r in rows if r["openalex_ids"])
            print(f"Matched {matched}/{len(rows)} Scholar articles to {len(works)} OpenAlex works.", flush=True)
            manifest = {"as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"), "complete": False, "queries": {}}
            write_json(pending / "manifest.json", manifest, indent=2)
        else:
            print(f"Resuming the refresh started {manifest['as_of'][:16]}.", flush=True)
        targets = read_json(pending / "targets.json")
        works = collect_citing(client, pending, {w["id"] for w in targets["works"]})
        missing = fetch_institutions(client, data, works, [targets.get("home")]
                                     + [i for w in targets["works"] for i in w.get("owner_institutions", [])])
        if not targets.get("home_set"):     # the guess again, now that the owner's institutions have their cities
            targets["home"] = guess_home(targets["works"], read_json(data / "institutions.json", {})) or targets.get("home")
            write_json(pending / "targets.json", targets, indent=2)
        manifest = read_json(pending / "manifest.json")
        manifest.update(complete=True, missing_institution_ids=missing, unique_citing_works=len(works),
                        finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        write_json(pending / "manifest.json", manifest, indent=2)
        for name in SNAPSHOT_FILES:
            (pending / name).replace(data / name)
        shutil.rmtree(pending)
        print(f"Snapshot {manifest['as_of'][:10]}: {len(works)} citing works.", flush=True)
        return True
    except APIError as exc:
        print(str(exc), flush=True)
        print("The previous snapshot is unchanged; run the same command again to resume.", flush=True)
        return False
    finally:
        print(f"Network requests this run: {client.calls}", flush=True)
