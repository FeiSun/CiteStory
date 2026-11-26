import unittest

import build_views as b


def source():
    targets = [
        {'id': 'T1', 'title': 'Alpha Paper', 'scholar_title': 'Alpha Paper', 'publication_year': 2019, 'doi': None},
        {'id': 'T1b', 'title': 'Alpha paper', 'scholar_title': 'Alpha paper', 'publication_year': 2018, 'doi': None},
        {'id': 'T2', 'title': 'Beta Paper', 'scholar_title': 'Beta Paper', 'publication_year': 2020, 'doi': 'https://doi.org/x'},
    ]
    works = [
        {'id': 'W1', 'date': '2020-03-01', 'year': 2020, 'targets': ['T1', 'T1b'], 'cities': ['c1']},   # two versions: counts once
        {'id': 'W2', 'date': '2021-01-01', 'year': 2021, 'targets': ['T1', 'T2'], 'cities': []},          # year only, co-citation
        {'id': 'W3', 'date': None, 'year': None, 'targets': ['T2'], 'cities': ['gone', 'c1']},            # undated
        {'id': 'T2', 'date': '2099-05-01', 'year': 2099, 'targets': ['T1'], 'cities': []},                # own paper, future date
        {'id': 'W1', 'date': '2020-03-01', 'year': 2020, 'targets': ['T1'], 'cities': []},                # duplicate id ignored
        {'id': 'W9', 'date': '2020-01-05', 'year': 2020, 'targets': ['other'], 'cities': []},             # cites nothing of ours
    ]
    return {'owner': 'Sample Owner', 'targets': targets, 'works': works, 'manifest': {'as_of': '2026-11-25T00:00:00+00:00'},
            'institutions': {'I1': {'display_name': 'Somewhere University'}},
            'cities': [{'id': 'c1', 'name': 'Lyon', 'country': 'FR', 'lat': 45.7, 'lon': 4.83}],
            'countries': {'FR': {'name': 'France'}}}


DETAILS = {
    'W1': {'title': 'First', 'doi': 'https://doi.org/w1', 'authors': [{'name': 'Ann', 'institutions': ['I1']}, {'name': 'Cy', 'institutions': []}]},
    'W2': {'title': 'Second', 'doi': None, 'authors': [{'name': 'A. Nn', 'institutions': ['I1']}]},
    'W3': {'title': None, 'doi': None, 'authors': [{'name': 'Bo', 'institutions': []}]},
    'T2': {'title': 'Beta Paper', 'doi': None, 'authors': [{'name': 'Owner', 'institutions': []}, {'name': 'Ann', 'institutions': ['I1']}]},
}
AUTHORS = {    # every author, with ids; DETAILS keeps only those with an affiliation
    'W1': [{'id': 'A1', 'name': 'Ann', 'institutions': ['I1']}, {'id': 'A3', 'name': 'Cy', 'institutions': []}],
    'W2': [{'id': None, 'name': 'Dee', 'institutions': []}, {'id': 'A1', 'name': 'A. Nn', 'institutions': ['I1']}],
    'W3': [{'id': 'A4', 'name': 'Bo', 'institutions': []}],
    'T2': [{'id': 'A0', 'name': 'Owner', 'institutions': []}, {'id': 'A1', 'name': 'Ann', 'institutions': ['I1']}],
}
OWNER, COAUTHORS = {'A0'}, {'A1'}


class Time(unittest.TestCase):
    def test_january_first_is_a_year_only_date_spread_over_the_year(self):
        snap = b.date(2026, 11, 25)
        t, year_only = b.fractional_time({'id': 'W1', 'date': '2021-01-01', 'year': 2021}, snap)
        self.assertTrue(year_only)
        self.assertTrue(2021 <= t < 2022)
        days = {b.page_date({'id': f'W{i}', 'date': '2021-01-01'}, snap) for i in range(50)}
        self.assertGreater(len(days), 30)                                  # not one pulse on one day
        self.assertEqual(b.page_date({'id': 'https://openalex.org/W7', 'date': '2021-01-01'}, snap),
                         b.page_date({'id': 'W7', 'date': '2021-01-01'}, snap))   # same day from full or short id
        self.assertEqual(b.fractional_time({'id': 'W7', 'date': b.page_date({'id': 'W7', 'date': '2021-01-01'}, snap),
                                            'yo': 1}, snap), b.fractional_time({'id': 'W7', 'date': '2021-01-01'}, snap))
        self.assertLessEqual(b.page_date({'id': 'W1', 'date': '2026-01-01'}, snap), '2026-11-25')
        self.assertEqual(b.fractional_time({'date': '2021-03-01', 'year': 2021}, snap)[1], False)

    def test_undated_and_future(self):
        snap = b.date(2026, 11, 25)
        self.assertEqual(b.fractional_time({'date': None, 'year': None}, snap), (None, False))
        self.assertEqual(b.fractional_time({'date': 'soon', 'year': True}, snap), (None, False))
        t, _ = b.fractional_time({'date': '2099-05-01', 'year': 2099}, snap)
        self.assertAlmostEqual(t, 2026 + 328 / 365, places=3)


class Transform(unittest.TestCase):
    def setUp(self):
        self.v, self.d = b.transform(source(), DETAILS, AUTHORS, OWNER, COAUTHORS)

    def test_versions_merge_and_each_work_counts_once(self):
        titles = [p['t'] for p in self.v['papers']]
        self.assertEqual(len(titles), 2)
        alpha = self.v['papers'][0]
        self.assertEqual((alpha['t'], alpha['y'], alpha['n']), ('Alpha Paper', 2018, 3))
        self.assertEqual(self.v['stats'], {'papers': 2, 'works': 4, 'undated': 1, 'multi': 1})

    def test_per_year_counts_and_undated_add_up(self):
        for p in self.v['papers']:
            self.assertEqual(sum(p['yr']) + p['u'], p['n'])
        self.assertEqual(self.v['papers'][1]['u'], 1)
        self.assertEqual(self.v['years'][0], 2020)
        self.assertEqual(self.v['years'][-1], 2026)

    def test_works_are_sorted_with_undated_last_and_flagged(self):
        times = [w[0] for w in self.v['works']]
        self.assertEqual(times[-1], None)
        self.assertEqual(times[:-1], sorted(times[:-1]))
        by_title = {d[0]: w for w, d in zip(self.v['works'], self.d)}
        self.assertEqual(by_title['Second'][3], b.YEAR_ONLY)
        self.assertEqual(by_title['Beta Paper'][3], b.OWN)
        self.assertEqual(by_title['First'][3], 0)
        self.assertEqual(by_title['Second'][1], [0, 1])

    def test_places_use_the_first_known_city(self):
        self.assertEqual(self.v['places'], [['Lyon, France', 4.8]])
        by_title = {d[0]: w for w, d in zip(self.v['works'], self.d)}
        self.assertEqual(by_title['First'][2], 0)
        self.assertEqual(by_title['Second'][2], -1)
        self.assertEqual(by_title[''][2], 0)       # W3: its first city id is unknown, the second is used

    def test_pairs_count_co_citations(self):
        self.assertEqual(self.v['pairs'], [[0, 1, 1]])

    def test_details_follow_the_work_order(self):
        self.assertEqual(len(self.d), len(self.v['works']))
        first = self.d[0]
        self.assertEqual(first, ['First', 'Ann et al.', 'https://doi.org/w1'])
        self.assertIn(['Second', 'Dee et al.', 'https://openalex.org/W2'], self.d)    # first author has no affiliation

    def test_authors_merge_by_id_and_point_at_works(self):
        ann = next(c for c in self.v['citers'] if c['name'] == 'Ann')
        self.assertEqual(len(ann['w']), 3)                 # W1, W2 (other spelling, same id), T2
        self.assertEqual(ann['own'], 1)                    # wrote one of the cited papers
        self.assertEqual(ann['inst'], 'Somewhere University')
        self.assertEqual(ann['w'], sorted(ann['w']))
        for i in ann['w']:
            self.assertIn(self.d[i][0], {'First', 'Second', 'Beta Paper'})
        bo = next(c for c in self.v['citers'] if c['name'] == 'Bo')
        self.assertEqual((bo['own'], bo['inst']), (0, ''))
        self.assertNotIn('Owner', [c['name'] for c in self.v['citers']])     # the owner is never a citer
        self.assertIn('Dee', [c['name'] for c in self.v['citers']])          # authors without an affiliation count

    def test_without_ids_authors_fall_back_to_names(self):
        v, _ = b.transform(source(), DETAILS)
        self.assertEqual(len(next(c for c in v['citers'] if c['name'] == 'Ann')['w']), 2)

    def test_owner_without_an_author_id_is_recognised_by_name(self):
        from fetch_citation_geo import owner_keys, owner_names
        authors = {'W1': [{'id': None, 'name': 'Zoe Q. Owner'}, {'id': 'A7', 'name': 'Eve'}],
                   'W2': [{'id': 'A8', 'name': 'Zoe Owner'}]}            # a namesake with an id stays
        v, _ = b.transform(source(), DETAILS, authors, owner_names=owner_keys(owner_names('Zoe Owner')))
        names = [c['name'] for c in v['citers']]
        self.assertNotIn('Zoe Q. Owner', names)
        self.assertIn('Zoe Owner', names)
        self.assertIn('Eve', names)

    def test_titles_without_latin_letters_stay_separate_papers(self):
        src = source()
        src['targets'] += [{'id': 'T3', 'title': '分布式单词表示综述', 'publication_year': 2014},
                           {'id': 'T4', 'title': '推荐系统研究', 'publication_year': 2015}]
        src['works'].append({'id': 'W5', 'date': '2022-02-02', 'year': 2022, 'targets': ['T3', 'T4'], 'cities': []})
        v, _ = b.transform(src, DETAILS)
        self.assertEqual(len(v['papers']), 4)

    def test_layout_is_deterministic_and_normalised(self):
        again, _ = b.transform(source(), DETAILS, AUTHORS, OWNER, COAUTHORS)
        for p, q in zip(self.v['papers'], again['papers']):
            self.assertEqual((p['x'], p['z'], p['r']), (q['x'], q['z'], q['r']))
            self.assertLessEqual(abs(p['x']) + p['r'], 1.0001)
            self.assertLessEqual(abs(p['z']) + p['r'], 1.0001)

    def test_script_json_cannot_close_the_script(self):
        self.assertNotIn('<', b.script_json({'t': '</script><b>'}))


if __name__ == '__main__':
    unittest.main()
