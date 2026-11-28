import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_citation_geo import aggregate, city_info, institution_rows, script_json
import build_citation_geo
import build_views
import fetch_citation_geo
from fetch_citation_geo import (APIError, Client, ScholarBlocked, api_key, compact_work, fetch_scholar, guess_home,
                                 name_match, owner_keys, owner_names, scholar_profile, title_match)


def institution(city="Example", country="AA", lat=10, lon=20, region=""):
    return {"country_code": country, "geo": {"city": city, "country_code": country,
             "region": region, "latitude": lat, "longitude": lon}}


class CitationGeoTests(unittest.TestCase):
    def test_one_work_counts_once_per_city_across_authors_and_institutions(self):
        works = [{"id": "W1", "authors": [{"institutions": ["I1", "I2"]}, {"institutions": ["I1", "I3"]}]}]
        cities, stats = aggregate(works, {"I1": institution(), "I2": institution(),
                                         "I3": institution("Other", lat=40)})
        self.assertEqual([c["count"] for c in cities], [1, 1])
        self.assertEqual(stats["mapped_works"], 1)
        self.assertEqual(stats["citing_works"], 1)

    def test_duplicate_places_merge_but_neighbouring_towns_stay_apart(self):
        def inst(city, lat, lon):
            return {"country_code": "AA", "geo": {"city": city, "country_code": "AA", "latitude": lat, "longitude": lon,
                                                    "geonames_city_id": city + str(lat)}}
        institutions = {"I1": inst("Big", 10, 10), "I2": inst("District", 10.02, 10.02), "I3": inst("Big", 10.05, 10),
                        "I4": inst("Twin", 10.03, 10.0)}
        works = [{"id": f"W{n}", "authors": [{"institutions": ["I1"]}]} for n in range(20)]
        works += [{"id": "D1", "authors": [{"institutions": ["I2"]}]},
                  {"id": "S1", "authors": [{"institutions": ["I3"]}]},
                  {"id": "W0x", "authors": [{"institutions": ["I1", "I2"]}]}]
        works += [{"id": f"T{n}", "authors": [{"institutions": ["I4"]}]} for n in range(15)]
        cities, _ = aggregate(works, institutions)
        by = {c["name"]: c for c in cities}
        self.assertEqual(sorted(by), ["Big", "Twin"])          # district and same-name copy folded in
        self.assertEqual(by["Big"]["count"], 23)                # W0x counted once after the merge
        self.assertEqual(by["Twin"]["count"], 15)               # similar-sized neighbour stays separate
        self.assertEqual(next(w for w in works if w["id"] == "W0x")["cities"], [by["Big"]["id"]])

    def test_city_identity_separates_homonyms(self):
        self.assertNotEqual(city_info(institution())["id"], city_info(institution(country="BB"))["id"])
        self.assertNotEqual(city_info(institution())["id"], city_info(institution(region="Other"))["id"])

    def test_missing_and_invalid_coordinates_do_not_create_false_locations(self):
        for lat in [None, "", math.nan, math.inf, 91, True]:
            self.assertIsNone(city_info(institution(lat=lat)))
        self.assertIsNone(city_info(institution(city="")))
        self.assertIsNotNone(city_info(institution(lat=0, lon=0)))
        cities, stats = aggregate([{"id": "W1", "authors": []}], {})
        self.assertEqual(cities, [])
        self.assertEqual(stats["unmapped_works"], 1)
        self.assertEqual(stats["no_affiliation_works"], 1)

    def test_multiple_cited_targets_preserved_without_duplicating_work(self):
        work = {"id": "W1", "referenced_works": ["T1", "T2", "Else"], "authorships": []}
        row = compact_work(work, {"T1", "T2"})
        self.assertEqual(row["targets"], ["T1", "T2"])
        self.assertEqual(row["id"], "W1")

    def test_html_json_cannot_escape_script_element(self):
        value = {"title": "</script><img src=x onerror=alert(1)>\u2028"}
        text = script_json(value)
        self.assertNotIn("</script", text)
        self.assertEqual(json.loads(text), value)

    def test_scholar_page_rows_owner_and_count(self):
        page = ('<div id=gsc_prf_in>Ada Li</div><span id=gsc_a_nn>Articles 1–2</span><tbody>'
                '<tr class="gsc_a_tr x"><td><a href="?citation_for_view=U:abc" class=gsc_a_at>A &amp; <b>B</b>: Test</a>'
                '<div class=gs_gray>A Li, B Wu</div><div class=gs_gray>KDD<span class="gs_oph">, 2020</span></div>'
                '<td><a class="gsc_a_ac gs_ibl">12</a><td><span class="gsc_a_h gsc_a_hc gs_ibl">2020</span>'
                '<tr class=gsc_a_tr><td><a class=gsc_a_at>Second</a><td><a class="gsc_a_ac gs_ibl"></a><td><span class="gsc_a_h gsc_a_hc gs_ibl"></span></tbody>')
        p = scholar_profile(page)
        self.assertEqual(p["owner"], "Ada Li")
        self.assertEqual(p["listed"], 2)
        self.assertEqual([r["title"] for r in p["papers"]], ["A & B: Test", "Second"])
        self.assertEqual((p["papers"][0]["scholar_citations"], p["papers"][0]["year"], p["papers"][0]["venue"]), (12, 2020, "KDD"))
        self.assertEqual((p["papers"][1]["scholar_citations"], p["papers"][1]["year"]), (0, None))

    def test_title_matching_is_strict(self):
        self.assertTrue(title_match("BERT4Rec: Test", "BERT4Rec — test"))
        self.assertFalse(title_match("BERT4Rec: Test", "BERT4Rec: Another Test"))
        self.assertFalse(title_match("Short", "Shorts"))
        self.assertTrue(title_match("分布式单词表示综述", "分布式单词表示综述"))
        self.assertTrue(title_match("Deep learning based recommender system: a survey and new perspectives",
                                    "Deep learning based recommender systems: a survey and new perspective"))

    def test_title_matching_tells_parts_years_and_versions_apart(self):
        for a, b in [("Large Language Models for Recommendation: Part I", "Large Language Models for Recommendation: Part II"),
                     ("A Survey on Graph Neural Networks (2021)", "A Survey on Graph Neural Networks (2024)"),
                     ("Graph Neural Networks for Recommendation, Version 2", "Graph Neural Networks for Recommendation, Version 3")]:
            self.assertFalse(title_match(a, b), a)
        self.assertTrue(title_match("BERT4Rec: Sequential Recommendation with Transformers, Part II",
                                    "BERT4Rec: sequential recommendation with transformer, part II"))

    def test_owner_name_readings(self):
        keys = owner_keys(owner_names("Fei Sun"))
        for name in ["Fei Sun", "Sun Fei", "F. Sun", "Sun, F."]:
            self.assertTrue(name_match(name, keys), name)
        for name in ["Fei Sung", "Fang Sun", "Feis Un", "Sun"]:
            self.assertFalse(name_match(name, keys), name)
        jordan = owner_keys(owner_names("Michael I. Jordan"))
        for name in ["Michael Jordan", "M. I. Jordan", "Michael I. Jordan"]:
            self.assertTrue(name_match(name, jordan), name)
        self.assertTrue(name_match("Junyan Zhu", owner_keys(owner_names("Jun-Yan Zhu"))))
        dupont = owner_keys(owner_names("Jean-Pierre Dupont"))
        for name in ["JP Dupont", "J.-P. Dupont", "J. P. Dupont", "Dupont JP"]:
            self.assertTrue(name_match(name, dupont), name)
        self.assertFalse(name_match("JM Dupont", dupont))
        wang = owner_keys(owner_names("Wei Wang (王伟)"))
        self.assertTrue(name_match("王 伟", wang))       # Chinese bylines are often spaced
        self.assertFalse(name_match("王 伟", owner_keys(owner_names("Wei Wang (王韦)"))))

    def test_scholar_name_drops_titles_and_keeps_native_script(self):
        self.assertEqual(owner_names("Prof. Wei Wang (王伟), IEEE Fellow", ["W. Wang"]), ["Wei Wang", "王伟", "W. Wang"])
        self.assertTrue(name_match("王伟", owner_keys(owner_names("Wei Wang (王伟)"))))
        for title in ["Prof. Dr. Anna Schmidt", "Assoc. Prof. Anna Schmidt", "Dr Anna Schmidt"]:
            self.assertEqual(owner_names(title), ["Anna Schmidt"], title)

    def test_home_is_most_frequent_recent_owner_affiliation(self):
        def w(year, *inst):
            return {"publication_year": year, "owner_institutions": list(inst)}
        found = [w(2026, "I1"), w(2025, "I1"), w(2024, "I2"), w(2010, "I3"), w(2010, "I3"), w(2010, "I3"), w(2027)]
        self.assertEqual(guess_home(found), "I1")
        self.assertEqual(guess_home([w(2010, "I3"), w(2026)]), "I3")     # no recent affiliation: any year
        self.assertIsNone(guess_home([w(2026)]))

    def test_api_key_read_from_env_file_when_environment_unset(self):
        with tempfile.TemporaryDirectory() as folder:
            env = Path(folder) / ".env"
            env.write_text("# local\nOTHER=1\nexport OPENALEX_API_KEY='synthetic-test-only'\n")
            with patch.dict(fetch_citation_geo.os.environ, {}, clear=True):
                self.assertEqual(api_key(env), "synthetic-test-only")
                self.assertIsNone(api_key(Path(folder) / "missing"))
            with patch.dict(fetch_citation_geo.os.environ, {"OPENALEX_API_KEY": "from-env"}):
                self.assertEqual(api_key(env), "from-env")

    def test_rate_limit_never_leaks_response_or_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            client = Client(Path(folder))
            client.key = "synthetic-test-only"
            error = HTTPError("https://api.openalex.org/works", 429, "synthetic-test-only", {}, None)
            with patch.object(fetch_citation_geo, "urlopen", side_effect=error), patch.object(fetch_citation_geo.time, "sleep"):
                with self.assertRaises(APIError) as caught:
                    client.get("works")
            self.assertIn("429", str(caught.exception))
            self.assertNotIn(client.key, str(caught.exception))
            self.assertEqual(client.calls, 1)

    def test_timeouts_and_dropped_connections_are_retried_then_reported(self):
        import http.client
        import socket
        for error in (socket.timeout("timed out"), http.client.RemoteDisconnected("closed"), ConnectionResetError()):
            with tempfile.TemporaryDirectory() as folder:
                client = Client(Path(folder))
                with patch.object(fetch_citation_geo, "urlopen", side_effect=error), patch.object(fetch_citation_geo.time, "sleep"):
                    with self.assertRaises(APIError):
                        client.get("works")
                self.assertEqual(client.calls, 3)
        # a response that arrived but cannot be cached is a local error: reported as it is, not fetched again
        class Reply:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n): return b'{"results": []}'
        with tempfile.TemporaryDirectory() as folder:
            client = Client(Path(folder), cache=Path(folder) / "cache")
            with patch.object(fetch_citation_geo, "urlopen", return_value=Reply()), patch.object(fetch_citation_geo.time, "sleep"), \
                    patch.object(Path, "write_text", side_effect=PermissionError("read-only")):
                with self.assertRaises(PermissionError):
                    client.get("works")
            self.assertEqual(client.calls, 1)
        with patch.object(fetch_citation_geo.time, "sleep"), self.assertRaises(ScholarBlocked):
            fetch_scholar("https://scholar.google.com/citations?user=abcdefgh", opener=lambda u: (_ for _ in ()).throw(socket.timeout()))


class ScholarFetch(unittest.TestCase):
    ROW = ('<tr class="gsc_a_tr"><td><a href="?citation_for_view=U:{0}" class="gsc_a_at">Paper {0}</a>'
           '<div class="gs_gray">A Li</div><div class="gs_gray">KDD</div><td><a class="gsc_a_ac gs_ibl">1</a>'
           '<td><span class="gsc_a_h gsc_a_hc gs_ibl">2020</span></tbody>')

    def opener(self, pages):
        seen = []

        class Reply:
            def __init__(self, body):
                self.body = body.encode()

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self, n):
                return self.body

        def open_(url):
            seen.append(url)
            return Reply(pages[len(seen) - 1])
        return open_, seen

    def test_pages_until_a_short_page(self):
        page1 = "<div id=gsc_prf_in>Ada Li</div>" + "".join(self.ROW.format(i) for i in range(100))
        page2 = "<div id=gsc_prf_in>Ada Li</div>" + self.ROW.format(100)
        open_, seen = self.opener([page1, page2])
        result = fetch_scholar("https://scholar.google.com/citations?user=abcDEF123456&hl=zh-CN", open_, pause=0)
        self.assertEqual((result["owner"], len(result["papers"])), ("Ada Li", 101))
        self.assertIn("cstart=100", seen[1])
        self.assertIn("user=abcDEF123456", seen[0])

    def test_captcha_and_bad_url(self):
        open_, _ = self.opener(["<form id=gs_captcha_f>unusual traffic</form>"])
        with self.assertRaises(ScholarBlocked):
            fetch_scholar("https://scholar.google.com/citations?user=abcDEF123456", open_, pause=0)
        with self.assertRaises(APIError):
            fetch_scholar("https://scholar.google.com/citations?hl=en", open_, pause=0)


class Refresh(unittest.TestCase):
    """A refresh is built in data/pending/ and replaces the previous snapshot only when complete."""
    SCHOLAR = {"owner": "Ada Li", "papers": [{"title": "Alpha Paper Title", "scholar_citations": 3}], "listed": 1,
               "more": False, "source": "url"}
    TARGET = {"id": "https://openalex.org/W1", "title": "Alpha paper title", "publication_year": 2020,
              "authorships": [{"author": {"id": "https://openalex.org/A1", "display_name": "Ada Li"},
                               "institutions": [{"id": "https://openalex.org/I1"}]},
                              {"author": {"id": "https://openalex.org/A2", "display_name": "Bo Wu"}, "institutions": []}]}
    CITING = {"id": "https://openalex.org/W2", "title": "Citing", "publication_date": "2021-03-04", "publication_year": 2021,
              "referenced_works": ["https://openalex.org/W1"],
              "authorships": [{"author": {"id": "https://openalex.org/A9", "display_name": "Cy"},
                               "institutions": [{"id": "https://openalex.org/I2"}]}]}

    def run_refresh(self, data, replies, restart=False):
        client_get = patch.object(Client, "get", side_effect=replies)
        with patch.object(fetch_citation_geo, "get_paper_list", return_value=dict(self.SCHOLAR)), client_get:
            return fetch_citation_geo.refresh({}, data, restart=restart)

    def test_interrupted_refresh_keeps_previous_snapshot_then_resumes(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            (data / "manifest.json").write_text(json.dumps({"as_of": "2026-01-01T00:00:00Z", "complete": True}))
            search = {"meta": {"count": 1}, "results": [self.TARGET]}
            page = {"meta": {"count": 1, "next_cursor": "c2"}, "results": [self.CITING]}
            done = {"meta": {"count": 1, "next_cursor": None}, "results": []}
            self.assertFalse(self.run_refresh(data, [search, page, APIError("rate limited")]))
            self.assertEqual(json.loads((data / "manifest.json").read_text())["as_of"], "2026-01-01T00:00:00Z")
            pending = json.loads((data / "pending" / "manifest.json").read_text())
            self.assertEqual(pending["queries"]["0"]["cursor"], "c2")
            insts = {"meta": {"count": 2}, "results": [{"id": "https://openalex.org/I1"}, {"id": "https://openalex.org/I2"}]}
            self.assertTrue(self.run_refresh(data, [done, insts]))      # resumes at the cursor; no new search
            self.assertFalse((data / "pending").exists())
            manifest = json.loads((data / "manifest.json").read_text())
            self.assertTrue(manifest["complete"])
            self.assertNotEqual(manifest["as_of"], "2026-01-01T00:00:00Z")
            targets = json.loads((data / "targets.json").read_text())
            work = targets["works"][0]
            self.assertEqual((work["owner_authors"], work["authors"], targets["home"]), (["A1"], ["A1", "A2"], "https://openalex.org/I1"))
            self.assertEqual(list(json.loads((data / "citing.json").read_text())), ["https://openalex.org/W2"])

    def test_estimated_count_tolerates_a_small_shortfall_only(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            search = {"meta": {"count": 1}, "results": [self.TARGET]}
            short = {"meta": {"count": 101, "next_cursor": None}, "results": [self.CITING] * 100}   # 100 of 101
            insts = {"meta": {"count": 2}, "results": [{"id": "https://openalex.org/I1"}, {"id": "https://openalex.org/I2"}]}
            self.assertTrue(self.run_refresh(data, [search, short, insts]))
            half = {"meta": {"count": 200, "next_cursor": None}, "results": [self.CITING] * 100}
            self.assertFalse(self.run_refresh(data, [half]))
            state = json.loads((data / "pending" / "manifest.json").read_text())["queries"]["0"]
            self.assertEqual((state["complete"], state["cursor"], state["received"]), (False, "*", 0))   # the group is retried

    def test_a_listing_resumed_after_newer_works_appeared_is_not_thrown_away(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            search = {"meta": {"count": 1}, "results": [self.TARGET]}
            first = {"meta": {"count": 100, "next_cursor": "c2"}, "results": [self.CITING] * 99}
            self.assertFalse(self.run_refresh(data, [search, first, APIError("daily limit")]))
            later = {"meta": {"count": 115, "next_cursor": None}, "results": []}     # OpenAlex indexed 15 more since
            insts = {"meta": {"count": 2}, "results": [{"id": "https://openalex.org/I1"}, {"id": "https://openalex.org/I2"}]}
            self.assertTrue(self.run_refresh(data, [later, insts]))

    def test_next_refresh_reuses_matches_and_restart_discards_pending(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            search = {"meta": {"count": 1}, "results": [self.TARGET]}
            page = {"meta": {"count": 1, "next_cursor": None}, "results": [self.CITING]}
            insts = {"meta": {"count": 2}, "results": [{"id": "https://openalex.org/I1"}, {"id": "https://openalex.org/I2"}]}
            self.assertTrue(self.run_refresh(data, [search, page, insts]))
            self.assertFalse(self.run_refresh(data, [APIError("rate limited")]))    # no search: match reused
            self.assertTrue((data / "pending").exists())
            self.assertTrue(self.run_refresh(data, [page], restart=True))         # institutions already cached

    def test_a_row_whose_venue_changed_is_searched_again_and_keeps_its_works(self):
        published = dict(self.TARGET, id="https://openalex.org/W5")
        previous = {"scholar": [{"title": "Alpha Paper Title", "venue": "arXiv preprint", "year": 2020}],
                    "works": [{"id": "https://openalex.org/W1", "scholar_title": "Alpha Paper Title", "authors": ["A1"]}]}
        profile = {"owner": "Ada Li", "papers": [{"title": "Alpha Paper Title", "venue": "arXiv preprint", "year": 2020}]}
        client = type("C", (), {"get": lambda *a, **k: self.fail("searched an unchanged row")})()
        accepted, _ = fetch_citation_geo.match_papers(client, profile, previous)
        self.assertEqual(list(accepted), ["https://openalex.org/W1"])
        profile["papers"][0]["venue"] = "KDD"         # Scholar merged the preprint with the published version
        reply = {"meta": {"count": 2}, "results": [self.TARGET, published]}
        client = type("C", (), {"get": lambda *a, **k: reply})()
        accepted, rows = fetch_citation_geo.match_papers(client, profile, previous)
        self.assertEqual(sorted(accepted), ["https://openalex.org/W1", "https://openalex.org/W5"])
        self.assertEqual(rows[0]["openalex_ids"], ["https://openalex.org/W1", "https://openalex.org/W5"])

    def test_page_works_date_a_year_only_work_and_clamp_a_forthcoming_year(self):
        from datetime import date
        snap = date(2026, 11, 26)
        base = {"targets": [], "cities": [], "authors": []}
        rows = build_citation_geo.page_works([dict(base, id="W1", year=2021, date=None),
                                              dict(base, id="W2", year=2027, date="2027-02-02"),
                                              dict(base, id="W3", year=2024, date="2024-05-06")], snap)
        self.assertEqual([(r["date"][:4], r["year"], r["yo"]) for r in rows],
                         [("2021", 2021, True), ("2026", 2026, False), ("2024", 2024, False)])
        self.assertEqual(rows[0]["date"], build_views.page_date({"id": "W1", "date": "2021-01-01"}, snap))   # as views.js

    def test_a_recent_published_row_matched_only_to_a_preprint_is_searched_again(self):
        year = fetch_citation_geo.datetime.now(fetch_citation_geo.timezone.utc).year
        preprint = {"id": "https://openalex.org/W1", "doi": "https://doi.org/10.48550/arxiv.2401.00001",
                    "scholar_title": "Alpha Paper Title", "authors": ["A1"]}
        previous = {"scholar": [{"title": "Alpha Paper Title", "venue": "ICLR", "year": year}], "works": [preprint]}
        profile = {"owner": "Ada Li", "papers": [{"title": "Alpha Paper Title", "venue": "ICLR", "year": year}]}
        published = dict(self.TARGET, id="https://openalex.org/W5")
        client = type("C", (), {"get": lambda *a, **k: {"meta": {"count": 1}, "results": [published]}})()
        accepted, _ = fetch_citation_geo.match_papers(client, profile, previous)
        self.assertEqual(sorted(accepted), ["https://openalex.org/W1", "https://openalex.org/W5"])
        previous["works"][0] = dict(preprint, doi="https://doi.org/10.1/x")       # a published version is matched
        client = type("C", (), {"get": lambda *a, **k: self.fail("searched a row that has its published version")})()
        fetch_citation_geo.match_papers(client, profile, previous)

    def test_rows_are_matched_from_the_owners_works_before_any_title_search(self):
        titles = ["Alpha Paper Title"] + [f"Other Paper Number {i}" for i in range(5)]
        profile = {"owner": "Ada Li", "papers": [{"title": t} for t in titles]}
        asked = []
        def get(_, path, params):
            asked.append(params)
            if "filter" in params:
                return {"meta": {"count": 1, "next_cursor": None}, "results": [self.TARGET]}
            return {"meta": {"count": 0}, "results": []}
        accepted, rows = fetch_citation_geo.match_papers(type("C", (), {"get": get})(), profile, owner_ids={"A1"})
        self.assertEqual(list(accepted), ["https://openalex.org/W1"])
        self.assertEqual(asked[0]["filter"], "author.id:A1")
        self.assertEqual([p["search"] for p in asked if "search" in p], titles[1:])     # Alpha needed no search
        self.assertEqual(rows[0]["openalex_ids"], ["https://openalex.org/W1"])

    def test_a_row_the_owner_list_matches_only_to_a_preprint_is_searched_too(self):
        year = fetch_citation_geo.datetime.now(fetch_citation_geo.timezone.utc).year
        titles = ["Alpha Paper Title"] + [f"Other Paper Number {i}" for i in range(5)]
        profile = {"owner": "Ada Li", "papers": [{"title": t, "venue": "ICLR", "year": year} for t in titles]}
        preprint = dict(self.TARGET, doi="https://doi.org/10.48550/arxiv.2401.00001")
        published = dict(self.TARGET, id="https://openalex.org/W5")
        def get(_, path, params):
            if "filter" in params:
                return {"meta": {"count": 1, "next_cursor": None}, "results": [preprint]}
            return {"meta": {"count": 1}, "results": [published] if params["search"] == titles[0] else []}
        accepted, _ = fetch_citation_geo.match_papers(type("C", (), {"get": get})(), profile, owner_ids={"A1"})
        self.assertEqual(sorted(accepted), ["https://openalex.org/W1", "https://openalex.org/W5"])

    def test_author_ids_in_any_form_and_a_home_with_a_city(self):
        for v in ["A5101467161", "a5101467161", "https://openalex.org/A5101467161", "https://openalex.org/authors/a5101467161/"]:
            self.assertEqual(fetch_citation_geo.author_id(v), "A5101467161")
        self.assertIsNone(fetch_citation_geo.author_id("not an id"))
        works = [{"publication_year": 2025, "owner_institutions": ["I_ACADEMY", "I_INSTITUTE"]},
                 {"publication_year": 2025, "owner_institutions": ["I_ACADEMY"]}]
        self.assertEqual(fetch_citation_geo.guess_home(works), "I_ACADEMY")
        insts = {"I_ACADEMY": {"geo": {"city": None}},
                 "I_INSTITUTE": {"geo": {"city": "Hefei", "latitude": 31.8, "longitude": 117.2}}}
        self.assertEqual(fetch_citation_geo.guess_home(works, insts), "I_INSTITUTE")     # the umbrella body has no city
        recent = [{"publication_year": 2026, "owner_institutions": ["I_ACADEMY"]},
                  {"publication_year": 2020, "owner_institutions": ["I_INSTITUTE"]}]
        self.assertEqual(fetch_citation_geo.guess_home(recent, insts), "I_INSTITUTE")    # recent years only with a city
        for v in ["I4210090176", "i4210090176", "https://openalex.org/institutions/i4210090176/"]:
            self.assertEqual(fetch_citation_geo.author_id(v, "i"), "I4210090176")

    def test_a_row_the_title_search_misses_is_found_by_its_arxiv_id(self):
        profile = {"owner": "Ada Li", "papers": [{"title": "Alpha Paper Title", "venue": "arXiv preprint arXiv:2510.25117"}]}
        asked = []
        def get(_, path, params):
            asked.append(params)
            return {"meta": {"count": 1}, "results": [self.TARGET] if "filter" in params else []}
        accepted, _ = fetch_citation_geo.match_papers(type("C", (), {"get": get})(), profile)
        self.assertEqual(list(accepted), ["https://openalex.org/W1"])
        self.assertEqual(asked[1]["filter"], "doi:10.48550/arxiv.2510.25117")

    def test_citing_pages_are_saved_in_batches_and_before_an_error(self):
        with tempfile.TemporaryDirectory() as folder:
            pending = Path(folder)
            pages = [{"meta": {"count": 99, "next_cursor": f"c{n}"},
                      "results": [dict(self.CITING, id=f"https://openalex.org/W{n}")]} for n in range(2, 5)]
            writes = []
            real = fetch_citation_geo.write_json
            with patch.object(Client, "get", side_effect=pages + [APIError("budget")]), \
                    patch.object(fetch_citation_geo, "write_json", side_effect=lambda *a, **k: (writes.append(a[0].name), real(*a, **k))):
                with self.assertRaises(APIError):
                    fetch_citation_geo.collect_citing(Client(pending), pending, {"https://openalex.org/W1"})
            self.assertEqual(writes, ["citing.json", "manifest.json"])          # once, not once per page
            self.assertEqual(len(json.loads((pending / "citing.json").read_text())), 3)
            self.assertEqual(json.loads((pending / "manifest.json").read_text())["queries"]["0"]["cursor"], "c4")

    def test_island_countries_have_a_continent(self):
        from build_citation_geo import basemap
        _, countries = basemap()
        self.assertEqual([countries[c]["continent"] for c in ("MU", "SC", "MV", "RE", "GF")],
                         ["Africa", "Africa", "Asia", "Africa", "South America"])

    def test_institution_rows_keep_name_and_kind_only(self):
        rows = institution_rows({"https://openalex.org/I1": dict(institution(), display_name="A", type="education"),
                                 "https://openalex.org/I2": {"display_name": "B", "type": "archive"},
                                 "https://openalex.org/I3": {"display_name": "C"}})
        self.assertEqual(rows["I1"], {"display_name": "A", "k": "u"})
        self.assertEqual((rows["I2"]["k"], rows["I3"]["k"]), ("r", "h"))


class HomeCity(unittest.TestCase):
    def test_home_city_is_matched_by_id_name_or_a_close_merge_never_a_neighbour(self):
        home = {"label": "Shenzhen", "country": "CN", "lat": 22.54, "lon": 114.06, "key": "geonames:1"}
        hk = {"id": "geonames:2", "name": "Hong Kong", "country": "HK", "lat": 22.28, "lon": 114.16}
        dg = {"id": "geonames:3", "name": "Dongguan", "country": "CN", "lat": 23.02, "lon": 113.75}
        self.assertIsNone(build_citation_geo.home_city(home, [hk, dg]))
        sz = {"id": "geonames:9", "name": "Shenzhen", "country": "CN", "lat": 22.55, "lon": 114.05}
        self.assertEqual(build_citation_geo.home_city(home, [hk, dg, sz]), "geonames:9")
        self.assertEqual(build_citation_geo.home_city(home, [dict(sz, id="geonames:1", name="Futian")]), "geonames:1")
        self.assertEqual(build_citation_geo.home_city(home, [sz], {"geonames:1": "geonames:9"}), "geonames:9")   # folded in
        cambridge = {"label": "Cambridge", "country": "US", "lat": 42.373, "lon": -71.11, "key": "geonames:10"}
        boston = {"id": "geonames:11", "name": "Boston", "country": "US", "lat": 42.358, "lon": -71.06, "count": 2}
        self.assertIsNone(build_citation_geo.home_city(cambridge, [boston]))              # a town of its own
        self.assertEqual(build_citation_geo.home_city(cambridge, [dict(boston, count=300)]), "geonames:11")   # a district beside its city


class BuildTest(unittest.TestCase):
    def test_build_counts_citations_from_the_snapshot_and_writes_utf8(self):
        import build_citation_geo
        with tempfile.TemporaryDirectory() as folder:
            data, site = Path(folder) / "data", Path(folder) / "site"
            data.mkdir()
            target = {"id": "https://openalex.org/W1", "title": "Alpha", "scholar_title": "Alpha", "publication_year": 2020,
                      "cited_by_count": 99, "authors": ["A1"], "owner_authors": ["A1"], "owner_institutions": []}
            targets = {"owner": "张三", "home": "https://openalex.org/I1", "works": [target],
                       "scholar": [{"title": "Alpha", "scholar_citations": 5, "openalex_ids": [target["id"]]}]}
            citing = {f"https://openalex.org/W{n}": {"id": f"https://openalex.org/W{n}", "title": "Über", "doi": None,
                                                    "year": 2021, "date": "2021-03-04", "targets": [target["id"]],
                                                    "authors": [{"id": "https://openalex.org/A9", "name": "Müller 李",
                                                                 "institutions": ["https://openalex.org/I1"]}]}
                      for n in (2, 3)}
            files = {"targets.json": targets, "citing.json": citing,
                     "institutions.json": {"https://openalex.org/I1": dict(institution("Zürich"), display_name="ETH Zürich")},
                     "manifest.json": {"as_of": "2026-01-01T00:00:00Z", "complete": True}}
            for name, value in files.items():
                (data / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            build_citation_geo.build(data, site)
            text = (site / "data.js").read_bytes().decode("utf-8")
            payload = json.loads(text[len("window.CITATION_DATA="):text.index(";\n")])
            self.assertEqual(payload["targets"][0]["cited_by_count"], 2)        # not the stale 99
            self.assertEqual((payload["owner"], payload["home"]["label"]), ("张三", "Zürich"))
            self.assertIn("Müller 李", (site / "views-details.js").read_bytes().decode("utf-8"))
            # ?paper= links between views: both data files give the paper the same short id
            views = (site / "views.js").read_text(encoding="utf-8")
            views = json.loads(views[len("window.CITATION_VIEWS="):views.rindex(";")])
            self.assertRegex(payload["targets"][0]["pid"], r"^[0-9a-f]{8}$")
            self.assertEqual(views["papers"][0]["id"], payload["targets"][0]["pid"])
            for page in ("atlas.html", "reach.html", "flow.html", "race.html"):
                html = (site / page).read_text(encoding="utf-8")
                self.assertIn("window.PaperViews=", html)
                self.assertNotIn("<!--PAPER_", html)
            # a build that fails halfway leaves the previous pages in place and nothing beside them
            (site / "CNAME").write_text("cites.example.org", encoding="utf-8")     # not build output: kept
            before = sorted(p.name for p in site.iterdir())
            with patch.object(build_citation_geo.build_year, "write", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    build_citation_geo.build(data, site)
            self.assertEqual(sorted(p.name for p in site.iterdir()), before)
            self.assertEqual(text, (site / "data.js").read_text(encoding="utf-8"))
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), ["data", "site"])
            build_citation_geo.build(data, site)
            self.assertEqual(sorted(p.name for p in site.iterdir()), before)
            self.assertEqual((site / "CNAME").read_text(encoding="utf-8"), "cites.example.org")
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), ["data", "site"])
            # a run stopped between the two renames left only site.old: the next build puts it back first
            (site / "assets").mkdir()
            (site / "assets" / "logo.svg").write_text("<svg/>", encoding="utf-8")
            site.replace(Path(folder) / "site.old")
            build_citation_geo.build(data, site)
            self.assertEqual((site / "assets" / "logo.svg").read_text(encoding="utf-8"), "<svg/>")
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), ["data", "site"])
            # site/ as a link to the web folder: the folder itself is rebuilt and the link stays
            web = Path(folder) / "web"
            site.replace(web)
            site.symlink_to(web, target_is_directory=True)
            build_citation_geo.build(data, site)
            build_citation_geo.build(data, site)
            self.assertTrue(site.is_symlink())
            self.assertEqual((web / "CNAME").read_text(encoding="utf-8"), "cites.example.org")
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), ["data", "site", "web"])

    def test_every_file_read_and_write_names_its_encoding(self):
        """The platform default (cp1252 on Windows) would garble or reject names in other scripts."""
        import ast
        for path in Path(__file__).parent.glob("*.py"):
            if path.name.startswith("test_"):
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in ("read_text", "write_text", "open")
                        and not (node.func.attr == "open" and isinstance(node.func.value, ast.Name))):
                    self.assertIn("encoding", [k.arg for k in node.keywords], f"{path.name}:{node.lineno}")

    def test_env_file_is_read_from_the_repository_only(self):
        self.assertEqual(api_key.__defaults__[0], (fetch_citation_geo.HERE / ".env",))
        self.assertEqual(fetch_citation_geo.HERE, Path(fetch_citation_geo.__file__).resolve().parents[1])


if __name__ == "__main__":
    unittest.main()
