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

    def test_scholar_name_drops_titles_and_keeps_native_script(self):
        self.assertEqual(owner_names("Prof. Wei Wang (王伟), IEEE Fellow", ["W. Wang"]), ["Wei Wang", "王伟", "W. Wang"])
        self.assertTrue(name_match("王伟", owner_keys(owner_names("Wei Wang (王伟)"))))

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

    def test_institution_rows_keep_name_and_kind_only(self):
        rows = institution_rows({"https://openalex.org/I1": dict(institution(), display_name="A", type="education"),
                                 "https://openalex.org/I2": {"display_name": "B", "type": "archive"},
                                 "https://openalex.org/I3": {"display_name": "C"}})
        self.assertEqual(rows["I1"], {"display_name": "A", "k": "u"})
        self.assertEqual((rows["I2"]["k"], rows["I3"]["k"]), ("r", "h"))


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
