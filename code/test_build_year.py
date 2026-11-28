import unittest

import build_citation_geo
import build_year as y


def source():
    targets = [
        {'id': 'T1', 'title': 'Alpha Paper', 'scholar_title': 'Alpha Paper', 'publication_year': 2019, 'doi': None},
        {'id': 'T1b', 'title': 'Alpha paper', 'scholar_title': 'Alpha paper', 'publication_year': 2018, 'doi': None},
        {'id': 'T2', 'title': 'Beta Paper', 'scholar_title': 'Beta Paper', 'publication_year': 2021, 'doi': None},
    ]
    works = [
        {'id': 'W1', 'date': '2020-03-01', 'year': 2020, 'targets': ['T1', 'T1b'], 'cities': ['lyon']},
        {'id': 'W2', 'date': '2020-06-01', 'year': 2020, 'targets': ['T1'], 'cities': ['lyon']},        # signed by a co-author
        {'id': 'W3', 'date': '2021-01-01', 'year': 2021, 'targets': ['T1'], 'cities': ['lyon', 'quito']},  # year only, returning reader
        {'id': 'W4', 'date': '2021-02-03', 'year': 2021, 'targets': ['T1', 'T2'], 'cities': ['tromso']},   # new reader, new places
        {'id': 'W5', 'date': '2021-02-03', 'year': 2021, 'targets': ['T2'], 'cities': []},                # the owner's own paper
        {'id': 'W6', 'date': None, 'year': None, 'targets': ['T1'], 'cities': ['quito']},                 # undated
        {'id': 'W7', 'date': '2099-05-01', 'year': 2099, 'targets': ['T1'], 'cities': []},                # dated after the snapshot
        {'id': 'W1', 'date': '2020-03-01', 'year': 2020, 'targets': ['T1'], 'cities': []},                # duplicate id ignored
        {'id': 'W9', 'date': '2020-01-05', 'year': 2020, 'targets': ['other'], 'cities': []},             # cites nothing of ours
    ]
    return {'owner': 'Sample Owner', 'targets': targets, 'works': works, 'manifest': {'as_of': '2022-03-10T00:00:00+00:00'},
            'home': {'lat': 45.76, 'lon': 4.84},
            'institutions': {'I1': {'display_name': 'Somewhere University'}, 'I2': {'display_name': 'Elsewhere Institute'}},
            'cities': [{'id': 'lyon', 'name': 'Lyon', 'country': 'FR', 'lat': 45.76, 'lon': 4.84},
                       {'id': 'quito', 'name': 'Quito', 'country': 'EC', 'lat': -0.18, 'lon': -78.47},
                       {'id': 'tromso', 'name': 'Tromsø', 'country': 'NO', 'lat': 69.65, 'lon': 18.96}],
            'countries': {'FR': {'name': 'France', 'continent': 'Europe'}, 'EC': {'name': 'Ecuador', 'continent': 'South America'},
                          'NO': {'name': 'Norway', 'continent': 'Europe'}}}


AUTHORS = {
    'W1': [{'id': 'https://openalex.org/A1', 'name': 'Ann', 'institutions': ['https://openalex.org/I1']}],
    'W2': [{'id': 'A8', 'name': 'Co Author', 'institutions': ['I1']}, {'id': 'A2', 'name': 'Bo', 'institutions': ['I2']}],
    'W3': [{'id': 'A1', 'name': 'Ann', 'institutions': ['I1']}],
    'W4': [{'id': 'A3', 'name': 'Cy', 'institutions': ['I2']}, {'id': None, 'name': 'Dee', 'institutions': []}],
    'W5': [{'id': None, 'name': 'Sample Owner', 'institutions': []}, {'id': 'A1', 'name': 'Ann', 'institutions': ['I1']}],
    'W6': [{'id': 'A1', 'name': 'Ann', 'institutions': []}],
    'W7': [{'id': 'A1', 'name': 'Ann', 'institutions': ['I1']}],
}
SCHOLAR = [{'title': 'Alpha Paper', 'venue': 'Test Conf 2019', 'year': 2019}, {'title': 'Beta Paper', 'venue': 'Proceedings of the Test Conf', 'year': 2021}]
VENUES = [('TestConf', y.re.compile(r'Test Conf', y.re.I),
           {2021: {'city': 'Rio', 'country': 'BR', 'lat': -22.9, 'lon': -43.2, 'start': '2021-04-23'}})]


def build(**kw):
    from fetch_citation_geo import owner_keys, owner_names
    return y.transform(source(), AUTHORS, SCHOLAR, owner_ids={'A0'}, coauthor_ids={'A8'},
                       owner_names=owner_keys(owner_names('Sample Owner')), venues=VENUES, **kw)


class Year(unittest.TestCase):
    def test_every_work_of_a_year_is_a_reader_a_returning_reader_or_the_owners_circle(self):
        out = build()
        self.assertEqual(sorted(out['years']), ['2020', '2021', '2022'])
        y20, y21 = out['years']['2020'], out['years']['2021']
        self.assertEqual((y20['n'], y20['readers']['fresh'], y20['readers']['own'], y20['readers']['returning']), (2, 1, 1, 0))
        # W3 (Ann again) returns; W4 is new; W5 is recognised as the owner's by name, without an author id
        self.assertEqual((y21['readers']['returning'], y21['readers']['fresh'], y21['readers']['own']), (1, 1, 1))
        flags = {row[0]: row[2] for row in y21['works']}
        self.assertEqual(flags[2], y.YEAR_ONLY | y.RETURNING)
        self.assertEqual(flags[4], y.OWN)
        self.assertEqual(sum(v['n'] for v in out['years'].values()) + out['stats']['undated'], out['stats']['works'])

    def test_a_second_paper_in_the_same_year_is_a_returning_reader(self):
        src = source()
        src['works'].append({'id': 'W8', 'date': '2021-06-06', 'year': 2021, 'targets': ['T1'], 'cities': []})
        authors = dict(AUTHORS, W8=[{'id': 'A3', 'name': 'Cy', 'institutions': []}])     # Cy first cited in February 2021
        out = y.transform(src, authors, SCHOLAR, venues=VENUES)
        flags = {row[0]: row[2] for row in out['years']['2021']['works']}
        self.assertEqual((flags[3] & y.RETURNING, flags[9] & y.RETURNING), (0, y.RETURNING))

    def test_new_papers_come_from_the_profile_and_the_year_written_in_the_venue(self):
        scholar = [{'title': 'Alpha Paper', 'venue': 'Test Conf 2021', 'year': 2020},      # OpenAlex says 2018 and 2019
                   {'title': 'Gamma Paper', 'venue': 'Test Conf 2021', 'year': 2021},      # not in OpenAlex at all
                   {'title': 'Delta Paper', 'venue': 'arXiv preprint arXiv:2105.01234', 'year': 2021},
                   {'title': 'Alpha paper', 'venue': 'duplicate row', 'year': 2021}]
        out = y.transform(source(), AUTHORS, scholar, venues=VENUES)
        born = out['years']['2021']['papers']['born']
        self.assertEqual([b['t'] for b in born], ['Alpha Paper', 'Gamma Paper', 'Delta Paper'])
        self.assertEqual([b['p'] is None for b in born], [False, True, True])
        self.assertEqual([b['stop'] for b in born], [0, 0, None])
        self.assertEqual(out['years']['2021']['papers']['route'][0]['papers'], [0, 1])
        self.assertEqual((y.venue_year('SIGIR 2026', 2025), y.venue_year('ICML 2019', 2025), y.venue_year('arXiv:2005.01234', 2020)),
                         (2026, 2025, 2020))

    def test_bookends_distance_and_phrases(self):
        src = source()
        src['works'] += [{'id': f'X{n}', 'date': '2021-05-%02d' % (n % 27 + 1), 'year': 2021, 'targets': ['T1'], 'cities': ['quito']}
                         for n in range(40)]
        titles = {f'X{n}': ('Graph Neural Networks for Recommendation' if n % 2 else 'Large Language Models as Judges') for n in range(40)}
        out = y.transform(src, AUTHORS, SCHOLAR, venues=VENUES, titles=titles)
        y21 = out['years']['2021']
        self.assertEqual((y21['ends']['first']['i'], y21['ends']['first']['date']), (3, '2021-02-03'))   # W3 is year only, W5 the owner's
        self.assertEqual(y21['ends']['last']['date'], '2021-05-27')
        self.assertEqual(y21['distance']['n'], 42)               # W3, W4 and the forty in Quito; not W5, which has no city
        quito, tromso = y.km(45.76, 4.84, -0.18, -78.47), y.km(45.76, 4.84, 69.65, 18.96)
        self.assertEqual(y21['distance']['km'], round(0 + tromso + 40 * quito))   # W3 has an author at home: 0 km
        topics = {t['t']: t['n'] for t in y21['topics']}
        self.assertEqual(topics, {'large language models': 20, 'graph neural networks': 20})     # shown as the titles write them
        self.assertEqual(y.phrases('基于图的推荐'), set())
        self.assertEqual(y.phrases('A Novel Approach to Graph Learning via Transformers'), {'graph learning'})
        self.assertEqual(y.phrases('Popularity Bias in News Recommendation'), {'popularity bias', 'news recommendation'})
        self.assertEqual(y.phrases('Does Graph Learning Help? Approaches for Time Series'), {'graph learning', 'graph learning help', 'learning help', 'time series'})
        self.assertEqual(y.phrases('BERT4Rec: GPT-4 Agents'), {'gpt-4 agent'})
        self.assertEqual(y.phrases('Un sistema de recomendación para la red'), set())


    def test_co_authors_never_count_as_readers(self):
        out = build()
        names = {c['name'] for v in out['years'].values() for c in v['readers']['citers']}
        self.assertNotIn('Co Author', names)
        self.assertNotIn('Bo', names)                    # Bo only appears on the co-author's paper
        self.assertEqual(out['years']['2020']['readers']['insts'], [])     # one paper is not a pattern
        self.assertEqual(out['years']['2020']['readers']['people'], 1)

    def test_new_places_are_new_to_the_whole_record(self):
        out = build()
        y20, y21 = out['years']['2020'], out['years']['2021']
        self.assertEqual(y20['places']['new_cities'], ['lyon'])
        self.assertEqual(sorted(y21['places']['new_cities']), ['quito', 'tromso'])
        self.assertEqual(sorted(c['iso'] for c in y21['places']['new_countries']), ['EC', 'NO'])
        self.assertEqual(y21['places']['new_works'], 2)
        self.assertEqual(y21['places']['far']['c'], 'quito')
        self.assertEqual(y21['places']['near']['c'], 'tromso')
        kinds = {(f['kind'], f['name']) for f in y21['places']['firsts']}
        self.assertEqual(kinds, {('continent', 'South America'), ('south', ''), ('arctic', '')})
        self.assertEqual({(f['kind'], f['name']) for f in y20['places']['firsts']}, {('continent', 'Europe')})

    def test_a_paper_born_this_year_gets_its_stop_and_its_first_outside_reader(self):
        out = build()
        born = out['years']['2021']['papers']['born']
        self.assertEqual(len(born), 1)
        self.assertEqual((born[0]['t'], out['papers'][born[0]['p']]['t']), ('Beta Paper', 'Beta Paper'))
        self.assertEqual(born[0]['first']['i'], 3)                       # W4, not the owner's own W5
        self.assertEqual(born[0]['first']['place'], 'Tromsø, Norway')
        self.assertEqual(born[0]['stop'], 0)
        self.assertEqual(out['years']['2021']['papers']['route'][0]['city'], 'Rio')
        self.assertEqual(out['years']['2020']['papers']['born'], [])
        self.assertEqual(out['years']['2019']['papers']['born'] if '2019' in out['years'] else [], [])     # no citing work in 2019

    def test_round_numbers_are_passed_in_the_year_the_count_crosses_them(self):
        src = source()
        src['works'] += [{'id': f'X{n}', 'date': '2021-05-0%d' % (n % 9 + 1), 'year': 2021, 'targets': ['T1'], 'cities': []} for n in range(9)]
        out = y.transform(src, AUTHORS, SCHOLAR, venues=VENUES)
        crossed = out['years']['2021']['papers']['crossed']
        alpha = next(p for p, paper in enumerate(out['papers']) if paper['t'] == 'Alpha Paper')
        self.assertEqual(crossed, [{'p': alpha, 'mark': 10, 'from': 2, 'to': 13}])
        self.assertEqual(out['years']['2020']['papers']['crossed'], [])

    def test_quiet_days_skip_the_first_of_january_and_stop_at_the_snapshot(self):
        out = build()
        self.assertEqual(out['years']['2021']['days'], {'quiet': 363, 'span': 364, 'busiest': [['2021-02-03', 2]],
                                                         'run': {'n': 1, 'start': '2021-02-03', 'end': '2021-02-03'}})
        y22 = out['years']['2022']                                          # W7 is dated 2099: moved to the snapshot day
        self.assertEqual((y22['n'], y22['complete'], y22['days']['span']), (1, False, 68))
        self.assertEqual(y22['works'][0][1], 69)                            # 10 March is day 69


    def test_runs_of_days_companions_the_oldest_paper_and_the_widest_reader(self):
        d = y.date
        self.assertEqual(y.longest_run([d(2021, 3, 1), d(2021, 3, 3), d(2021, 3, 4), d(2021, 3, 5), d(2021, 12, 31)]),
                         (3, d(2021, 3, 3), d(2021, 3, 5)))
        self.assertIsNone(y.longest_run([]))
        self.assertEqual(y.byline('S Owner*, J Liu*, Sample Owner, K Wu, ...', 'Sample Owner'), (['J Liu', 'K Wu'], True))
        self.assertEqual(y.byline('JP Dupont， 郭嘉丰', 'Jean-Pierre Dupont'), (['郭嘉丰'], False))
        self.assertEqual(y.byline('S Owner, ...', 'Sample Owner'), ([], True))
        self.assertEqual(y.byline('', 'Sample Owner'), ([], False))
        scholar = [dict(SCHOLAR[0], authors='S Owner, J Liu'), dict(SCHOLAR[1], authors='J Liu, S Owner, K Wu, M Ng')]
        out = y.transform(source(), AUTHORS, scholar, venues=VENUES)['years']
        self.assertEqual(out['2021']['papers']['companions'], {'n': 3, 'new': 2, 'papers': 1, 'cut': False, 'unsure': False})   # J Liu was there in 2019
        self.assertIsNone(out['2020']['papers']['companions'])
        self.assertEqual(out['2021']['papers']['oldest'], {'p': 0, 'y': 2018, 'n': 2})
        self.assertIsNone(out['2021']['readers']['deep'])                    # nobody cites four of these papers at once
        src = source()
        src['targets'] += [{'id': 'T%d' % k, 'title': 'Paper %d' % k, 'publication_year': 2010 + k, 'doi': None} for k in (3, 4)]
        src['works'][3]['targets'] = ['T1', 'T2', 'T3', 'T4']
        deep = y.transform(src, AUTHORS, SCHOLAR, venues=VENUES)['years']['2021']['readers']['deep']
        self.assertEqual((src['works'][deep['i']]['id'], deep['n'], deep['from'], deep['to']), ('W4', 4, 2013, 2021))
        self.assertEqual(build()['years']['2021']['regulars'], [])           # nobody has cited three years running

    def test_the_page_gets_one_year_and_what_it_needs_of_the_years_before(self):
        full = build()
        page = y.latest(full)                                                # snapshot 10 March 2022
        self.assertEqual((page['year'], page['review'], page['history']), (2022, full['years']['2022'], [[2020, 2], [2021, 3], [2022, 1]]))
        self.assertEqual(sorted(page['known']), ['lyon', 'quito', 'tromso'])
        self.assertNotIn('years', page)
        full['snapshot'] = '2022-02-10T00:00:00+00:00'                       # in February the year just ended is the one
        page = y.latest(full)
        self.assertEqual((page['year'], page['history'][-1], sorted(page['known'])), (2021, [2021, 3], ['lyon']))
        full['years'] = {k: dict(v, n=0) for k, v in full['years'].items()}
        self.assertIsNone(y.latest(full)['year'])

    def test_the_credits_name_every_reader_once_in_order_of_appearance(self):
        out = build()
        self.assertEqual(out['years']['2020']['credits'], ['Ann'])           # W2 is a co-author's paper: Bo is not a reader
        self.assertEqual(out['years']['2021']['credits'], ['Cy', 'Dee', 'Ann'])    # Ann's paper is known by year only and sits later
        self.assertEqual(len(out['years']['2021']['credits']), out['years']['2021']['readers']['people'])
        authors = dict(AUTHORS, W4=[{'id': 'A3', 'name': 'NIM.: 24206051014 Cy', 'institutions': []}])
        self.assertEqual(y.transform(source(), authors, SCHOLAR, coauthor_ids={'A8'}, owner_names=frozenset({'sample owner'}))['years']['2021']['credits'][-1:], ['Ann'])   # a number is not a name

    def test_spellings_of_one_phrase_are_merged_and_shown_as_most_titles_write_them(self):
        self.assertEqual(y.phrases('Recommender Systems'), y.phrases('A recommendation system'))
        self.assertEqual(y.phrases('Generative recommenders'), {'generative recommendation'})
        self.assertEqual(y.phrases('Query strategies for user studies'), y.phrases('A query strategy for a user study'))
        self.assertEqual(y.phrases('Case studies of graph networks'), {'graph network'})     # "study" is generic
        self.assertEqual([y.singular(w) for w in ('analyses', 'series', 'boxes', 'movies')], ['analysis', 'series', 'box', 'movie'])
        self.assertEqual(y.singular('selfies'), 'selfie')
        spelled = y.defaultdict(y.Counter)
        docs = [(k, y.phrases(t, spelled)) for k, t in enumerate(['Recommender systems'] * 20 + ['Recommendation systems'] * 12)]
        top = y.pick_topics(docs, y.Counter(), 0, spelled=spelled)[0]
        self.assertEqual((top['t'], top['n']), ('recommender systems', 32))   # counted as one phrase, shown as written
        self.assertEqual(y.phrases('Losses and biases of naive Bayes classes'), {'naive bayes', 'bayes class', 'naive bayes class'})


class Venues(unittest.TestCase):
    def test_the_shipped_table_loads_and_matches_only_its_own_series(self):
        series = y.load_venues()
        stop = y.venue_stop('Proceedings of the 64th Annual Meeting of the As…', 2026, series)
        self.assertEqual((stop['name'], stop['city']), ('ACL', 'San Diego'))
        self.assertEqual(y.venue_stop('SIGIR 2026', 2026, series)['city'], 'Melbourne')
        for venue, name in (('Proceedings of the 32nd ACM SIGKDD Conference on Knowledge Discovery and …', 'KDD'),
                            ('KDD 2026', 'KDD'), ('ACL 2026 Main', 'ACL'),
                            ('Findings of the Association for Computational Linguistics: EMNLP 2026', 'EMNLP'),
                            ('Proceedings of the 2026 Conference on Empirical Methods in Natural …', 'EMNLP'),
                            ('Proceedings of the 49th International ACM SIGIR Conference on Research and Development in …', 'SIGIR'),
                            ('Proceedings of the AAAI Conference on Artificial …', 'AAAI'),
                            ('Companion Proceedings of the ACM Web Conference 2026, 636-639', 'WWW'),
                            ('Proceedings of the ACM on Web Conference 2026, 4470-4481', 'WWW')):
            stop = y.venue_stop(venue, y.venue_year(venue, 2026), series)
            self.assertEqual(stop['name'] if stop else None, name, venue)
        for other in ('NAACL 2026', 'PAKDD 2026', 'SIGIR-AP 2026', 'arXiv preprint arXiv:2608.13417', '',
                      'Pacific-Asia Conference on Knowledge Discovery and Data Mining', 'KDD Cup 2026',
                      'ACM SIGIR Conference on Research and Development in Information Retrieval in the Asia Pacific Region',
                      'ACM SIGIR Forum', 'Proceedings of the 2026 Conference on Human Information Interaction and Retrieval (SIGIR CHIIR)',
                      'International AAAI Conference on Web and Social Media', 'AAAI/ACM Conference on AI, Ethics, and Society',
                      'Annual Meeting of the Association for Information Science and Technology',
                      'Transactions of the ACL', 'Journal of ACL Injury', 'ICLR 2026 Workshop on Agents',
                      'ECML PKDD 2026', 'TKDD', 'ACM SIGKDD Explorations Newsletter', 'Advances in Knowledge Discovery and Data Mining',
                      'Proceedings of the 2026 Annual International ACM SIGIR Conference on Research and …',
                      'ACM SIGIR Conference on Innovative Concepts and Theories in Information Retrieval (ICTIR)',
                      'Proceedings of the AAAI Conference on Human Computation and Crowdsourcing',
                      'Proceedings of the International AAAI Conference on Web …',
                      'Conference of the European Chapter of the ACL', 'Annual Meeting of the Association of American Geographers',
                      'Tiny Papers @ ICLR 2026', 'ICMLA 2026', 'APWeb-WAIM 2026', 'NAACL 2026 Workshop on Trustworthy NLP'):
            self.assertIsNone(y.venue_stop(other, 2026, series), other)
        self.assertIsNone(y.venue_stop('ACL 2025', y.venue_year('ACL 2025', 2026), series))   # last year's edition is not listed
        self.assertIsNone(y.venue_stop('ICLR 2031', 2031, series))          # an edition that is not listed


class Dates(unittest.TestCase):
    def test_a_citing_work_older_than_everything_it_cites_loses_its_date(self):
        targets = [{'id': 'T1', 'title': 'One', 'publication_year': 2019}, {'id': 'T2', 'title': 'Two', 'publication_year': 2015},
                   {'id': 'T3', 'title': 'Three', 'publication_year': None},
                   {'id': 'T4', 'title': 'Four', 'publication_year': 2019}, {'id': 'T4p', 'title': 'four', 'publication_year': 2016}]
        works = [{'id': 'a', 'date': '2012-02-24', 'year': 2012, 'targets': ['T1']},     # seven years too early
                 {'id': 'b', 'date': '2018-06-01', 'year': 2018, 'targets': ['T1']},     # a preprint cited a year early: kept
                 {'id': 'c', 'date': '2016-06-01', 'year': 2016, 'targets': ['T1', 'T2']},  # possible for T2: kept
                 {'id': 'd', 'date': None, 'year': 2012, 'targets': ['T1']},
                 {'id': 'e', 'date': '2001-01-01', 'year': 2001, 'targets': ['T3', 'unknown']},  # nothing to compare with
                 {'id': 'f', 'date': None, 'year': None, 'targets': ['T1']},
                 {'id': 'g', 'date': '2016-09-01', 'year': 2016, 'targets': ['T4']}]      # cites the 2019 record of a 2016 preprint: kept
        self.assertEqual(build_citation_geo.undate_impossible(works, targets), 2)
        self.assertEqual([(w['date'], w['year']) for w in works],
                         [(None, None), ('2018-06-01', 2018), ('2016-06-01', 2016), (None, None), ('2001-01-01', 2001), (None, None),
                          ('2016-09-01', 2016)])

    def test_places_are_given_as_city_ids_marks_are_cut_from_names_and_the_oldest_paper_has_an_outside_reader(self):
        out = build()['years']
        self.assertEqual(out['2021']['papers']['born'][0]['first']['c'], 'tromso')     # the page names the place in its own language
        self.assertEqual(out['2020']['ends']['first']['c'], 'lyon')
        authors = dict(AUTHORS, W4=[{'id': 'A3', 'name': 'Cy*', 'institutions': ['I2']}, {'id': 'A4', 'name': 'Dee\u00b9', 'institutions': []}])
        marked = y.transform(source(), authors, SCHOLAR, coauthor_ids={'A8'}, owner_names=frozenset({'sample owner'}))
        self.assertEqual(marked['years']['2021']['credits'][:2], ['Cy', 'Dee'])
        src = source()
        src['targets'].append({'id': 'T0', 'title': 'Old Paper', 'scholar_title': 'Old Paper', 'publication_year': 2001, 'doi': None})
        src['works'].append({'id': 'W8', 'date': '2021-03-03', 'year': 2021, 'targets': ['T0'], 'cities': []})
        own = dict(AUTHORS, W8=[{'id': 'A0', 'name': 'Sample Owner', 'institutions': []}])
        full = y.transform(src, own, SCHOLAR, owner_ids={'A0'}, coauthor_ids={'A8'})
        self.assertEqual(full['papers'][full['years']['2021']['papers']['oldest']['p']]['y'], 2018)     # the 2001 paper was cited only by its author

    def test_readers_since_reunions_and_chinese_names(self):
        out = build()['years']['2021']
        since = {row[0]: row[4] for row in out['works']}
        self.assertEqual(sorted(set(since.values()) - {None}), [2020, 2021])     # Ann first cited in 2020; Cy and Dee are new
        self.assertIsNone(out['readers']['back'])                               # nobody stayed away five years
        self.assertEqual(y.clean_name('Rui Wang*'), 'Rui Wang')
        self.assertEqual(y.clean_name('Qi Li\u00b9'), 'Qi Li')
        merged = y.credits_by_name(['a', 'b', 'c'], {'a': 'Hao Wang', 'b': 'Jun\u2010Hwa', 'c': 'hao  wang*'}, {'a': [3], 'b': [1], 'c': [0, 3]}, {'c': 3})
        self.assertEqual(merged, {'credits': ['Hao Wang', 'Jun\u2010Hwa'], 'regulars': [0], 'credit_works': [[0, 3], [1]]})
        year = {'review': {'papers': {'route': [{'city': 'Rio', 'country': 'BR'}]}}}
        y.chinese_names(year, source()['cities'], {('quito', 'EC'): '基多', ('rio', 'BR'): '里约'}, {'label': 'Quito', 'country': 'EC'})
        self.assertEqual(year['zh'], {'quito': '基多'})
        self.assertEqual(year['review']['papers']['route'][0]['city_zh'], '里约')
        self.assertEqual(year['home_zh'], '基多')
        self.assertTrue(y.load_city_names())

    def test_unusual_desks_other_scripts_reunions_and_the_works_of_each_name(self):
        src = source()
        src['works'].append({'id': 'W0', 'date': '2015-05-05', 'year': 2015, 'targets': ['T1'], 'cities': []})
        src['institutions'].update({'I3': {'display_name': 'A Hospital'}, 'I4': {'display_name': 'A Library'}})
        authors = dict(AUTHORS, W0=[{'id': 'A3', 'name': 'Cy', 'institutions': []}],
                       W4=[{'id': 'A3', 'name': 'Cy', 'institutions': ['I3']}, {'id': None, 'name': 'Dee', 'institutions': ['I4', 'I3']}])
        titles = {'W4': 'Рекомендательные системы', 'W3': 'β-VAE for recommendation'}
        from fetch_citation_geo import owner_keys, owner_names
        out = y.transform(src, authors, SCHOLAR, coauthor_ids={'A8'}, owner_names=owner_keys(owner_names('Sample Owner')), titles=titles,
                          inst_meta={'I3': {'type': 'healthcare', 'lat': 46.5, 'lon': 6.6}, 'I4': {'type': 'archive'}, 'I1': {'type': 'education'}})['years']['2021']
        self.assertEqual(out['desks'], {'healthcare': {'n': 1, 'names': ['A Hospital'], 'at': [[6.6, 46.5, 'A Hospital', 1]]},
                                        'archive': {'n': 1, 'names': ['A Library'], 'at': []}})     # a place without coordinates is not drawn
        self.assertEqual([(s, n, [out['works'][k][0] for k in ks]) for s, n, ks in out['scripts']], [('cyrillic', 1, [3])])   # W4; a Greek letter in a Latin title does not count
        self.assertEqual(out['readers']['back'], {'n': 1, 'gap': 6, 'names': ['Cy'], 'last': [[2015, 1]]})
        rows = {name: [out['works'][k][0] for k in ks] for name, ks in zip(out['credits'], out['credit_works'])}
        self.assertEqual(rows, {'Cy': [3], 'Dee': [3], 'Ann': [2]})              # positions in `works`, pointing at W4 and W3
        self.assertEqual([y.script_of(t) for t in ('マルチモーダル推薦', '基于 Python 的推荐系统', 'Αξιολογώντας συστήματα', 'β-VAE', None)],
                         ['ja', 'zh', 'greek', None, None])

    def test_a_new_country_carries_the_drawing_of_its_first_city(self):
        import json, tempfile
        from pathlib import Path
        marks = y.load_landmarks()
        self.assertTrue(marks)
        for (city, iso), m in marks.items():
            self.assertTrue(m['name'] and m['d'].startswith('M'), (city, iso))
        full = y.transform(source(), {}, landmarks={('quito', 'EC'): {'name': 'A view', 'zh': '', 'd': 'M0 0L1 1'}})
        new = {c['iso']: c for c in full['years']['2021']['places']['new_countries']}
        self.assertEqual(new['EC']['art']['d'], 'M0 0L1 1')
        self.assertNotIn('art', new['NO'])                # no drawing listed: the page draws the country's outline
        with tempfile.TemporaryDirectory() as tmp:
            for bad in ({'Quito': {'name': 'x', 'd': 'M0 0'}}, {'Quito, EC': {'name': 'x', 'd': 'M0 0"/><script>'}}):
                path = Path(tmp) / 'landmarks.json'
                path.write_text(json.dumps({'places': bad}), encoding='utf-8')
                with self.assertRaises(ValueError):
                    y.load_landmarks(path)


class Fixes(unittest.TestCase):
    def test_the_longest_regulars_keep_their_order_when_one_person_has_two_ids(self):
        src = source()
        src['works'] = []
        authors = {}
        def add(wid, day, who):
            src['works'].append({'id': wid, 'date': day, 'year': int(day[:4]), 'targets': ['T1'], 'cities': []})
            authors[wid] = [{'id': a, 'name': n, 'institutions': []} for a, n in who]
        everyone = [('A1', 'Alice'), ('A2', 'Alice'), ('B', 'Bea'), ('C', 'Cal'), ('D', 'Dan')]
        for year in (2019, 2020):
            add(f'W{year}', f'{year}-05-05', everyone)
        k = 0
        for a, n, count in [('A1', 'Alice', 10), ('B', 'Bea', 4), ('C', 'Cal', 3), ('D', 'Dan', 2), ('A2', 'Alice', 1)]:
            for _ in range(count):
                k += 1
                add(f'X{k}', f'2021-03-{k:02d}', [(a, n)])
        out = y.transform(src, authors)['years']['2021']['readers']
        self.assertEqual(out['streak_names'], ['Alice', 'Bea', 'Cal'])

    def test_a_byline_without_an_id_is_not_a_returning_reader_in_a_later_year(self):
        src = source()
        src['works'] = [{'id': 'W1', 'date': '2020-03-01', 'year': 2020, 'targets': ['T1'], 'cities': []},
                        {'id': 'W2', 'date': '2021-03-01', 'year': 2021, 'targets': ['T1'], 'cities': []}]
        authors = {w: [{'id': None, 'name': 'Wei Wang', 'institutions': []}] for w in ('W1', 'W2')}
        y21 = y.transform(src, authors)['years']['2021']
        self.assertEqual(y21['works'][0][2] & y.RETURNING, 0)
        self.assertEqual((y21['readers']['returning'], y21['readers']['new_people']), (0, 1))

    def test_a_place_is_reached_first_by_a_work_with_its_real_date(self):
        src = source()
        src['works'] = [{'id': 'W1', 'date': '2021-01-01', 'year': 2021, 'targets': ['T1'], 'cities': ['quito']},   # year only
                        {'id': 'W2', 'date': '2021-12-30', 'year': 2021, 'targets': ['T1'], 'cities': ['quito']}]
        places = y.transform(src, {})['years']['2021']['places']
        self.assertEqual([(c['iso'], c['date'], c['yo']) for c in places['new_countries']], [('EC', '2021-12-30', 0)])
        self.assertEqual([(f['kind'], f['date']) for f in places['firsts']], [('continent', '2021-12-30'), ('south', '2021-12-30')])


if __name__ == '__main__':
    unittest.main()
