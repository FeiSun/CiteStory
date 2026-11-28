"""Data for the pages that are not maps: Constellation, Race, Regulars and Record.

`transform` turns the page payload of build_citation_geo.py into one compact object,
`window.CITATION_VIEWS` (site/views.js), and a list of titles aligned with its works,
`window.CITATION_VIEW_DETAILS` (site/views-details.js, loaded on demand). Standard library only.
"""
import calendar
from collections import Counter, defaultdict
from datetime import date, timedelta
import hashlib
import json
import math
import random
import re

from fetch_citation_geo import name_match, normalized_title as normalized, short as short_id

YEAR_ONLY, OWN = 2, 1     # bits of a work's flags in views.js (year.js has its own, see build_year.py)


def year_only_day(work_id, year, snapshot):
    """A stable day in `year` (up to the snapshot) for a work whose date is only its year, so year-only works
    spread over the year instead of piling up on one day."""
    start = date(year, 1, 1)
    end = min(date(year, 12, 31), snapshot) if snapshot >= start else start
    span = (end - start).days + 1
    return start + timedelta(days=int(hashlib.sha1(str(short_id(work_id)).encode()).hexdigest(), 16) % span)


def work_day(work, snapshot):
    """(date clamped to the snapshot, year_only); (None, False) when undated.

    OpenAlex writes YYYY-01-01 when it only knows the year."""
    year_only = bool(work.get('yo'))     # set by the build on a date it already spread
    year = work.get('year')
    try:
        day = date.fromisoformat(str(work.get('date') or ''))
        if day.month == 1 and day.day == 1:
            year = day.year
            raise ValueError
    except ValueError:
        if not isinstance(year, int) or isinstance(year, bool) or not 1900 <= year <= 2200:
            return None, False
        day, year_only = year_only_day(work.get('id'), year, snapshot), True
    return min(day, snapshot), year_only


def page_date(work, snapshot):
    """The ISO date the map pages use: as work_day, so the map pages and views.js place a work on the same day."""
    day, _ = work_day(work, snapshot)
    return day.isoformat() if day else None


def fractional_time(work, snapshot):
    """(fractional calendar year clamped to the snapshot, year_only); (None, False) when undated."""
    day, year_only = work_day(work, snapshot)
    if day is None:
        return None, False
    days = 366 if calendar.isleap(day.year) else 365
    return round(day.year + (day - date(day.year, 1, 1)).days / days, 3), year_only


def layout(papers, links, seed=7, steps=700):
    """Deterministic force layout of the cited papers: co-cited papers attract. Node radius ~ sqrt(citations).

    Every pair repels, so the cost grows with the square of the papers: about 2 s for 100, 3 min for 1,000.
    Cutting off distant pairs was tried and packed large records visibly worse."""
    rng = random.Random(seed)
    n = len(papers)
    radius = [0.9 * math.sqrt(max(p['n'], 1)) + 3 for p in papers]
    pos = []
    for i in range(n):  # golden-angle spiral start keeps big papers central
        a, r = i * 2.39996, 14 * math.sqrt(i + 1)
        pos.append([r * math.cos(a) + rng.uniform(-1, 1), r * math.sin(a) + rng.uniform(-1, 1)])
    strongest = max([w for _, _, w in links] or [1])
    for step in range(steps):
        cool = 1 - step / steps
        force = [[0.0, 0.0] for _ in range(n)]
        for i in range(n):
            xi, yi = pos[i]
            force[i][0] -= 0.012 * xi  # gravity
            force[i][1] -= 0.012 * yi
            for j in range(i + 1, n):
                dx, dy = xi - pos[j][0], yi - pos[j][1]
                d = math.hypot(dx, dy) or 0.01
                gap = radius[i] + radius[j] + 6
                push = 900 / (d * d) + (gap - d) * 0.5 if d < gap else 900 / (d * d)
                fx, fy = dx / d * push, dy / d * push
                force[i][0] += fx; force[i][1] += fy
                force[j][0] -= fx; force[j][1] -= fy
        for i, j, w in links:
            dx, dy = pos[j][0] - pos[i][0], pos[j][1] - pos[i][1]
            d = math.hypot(dx, dy) or 0.01
            rest = radius[i] + radius[j] + 10
            pull = 0.02 * (0.25 + w / strongest) * (d - rest)
            fx, fy = dx / d * pull, dy / d * pull
            force[i][0] += fx; force[i][1] += fy
            force[j][0] -= fx; force[j][1] -= fy
        for i in range(n):
            fx, fy = force[i]
            m = math.hypot(fx, fy)
            cap = 6 * cool + 0.3
            if m > cap:
                fx, fy = fx / m * cap, fy / m * cap
            pos[i][0] += fx; pos[i][1] += fy
    xs = [p[0] for p in pos]; ys = [p[1] for p in pos]
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    span = max(max(abs(x - cx) + radius[i] for i, x in enumerate(xs)),
               max(abs(y - cy) + radius[i] for i, y in enumerate(ys))) or 1
    return [[round((p[0] - cx) / span, 4), round((p[1] - cy) / span, 4), round(radius[i] / span, 4)]
            for i, p in enumerate(pos)]


def paper_id(key):
    """The short id a page puts in ?paper=: stable while the paper's (normalized) title stays the same."""
    return hashlib.sha1(str(key).encode('utf-8')).hexdigest()[:8]


def clean_name(name):
    """A byline without the footnote marks some sources leave at its end ("Rui Wang*", "Qi Li¹")."""
    return re.sub(r"[\s\d¹²³⁴-⁹⁰*†‡§¶✉]+$", "", name) or name


def byline(authors):
    names = [clean_name(a['name']) for a in authors or [] if a.get('name')]
    if not names:
        return ''
    return names[0] if len(names) == 1 else names[0] + ' et al.'


def transform(source, details, authors=None, owner_ids=(), coauthor_ids=(), citer_limit=60, owner_names=frozenset()):
    """Return (views, view_details). `source` is the CITATION_DATA payload, `details` maps work id to
    {title, doi, authors}. `authors` maps work id to its full author list [{id, name}] (details keeps only
    authors with an affiliation). `owner_ids` are the owner's OpenAlex author ids (never listed as citers);
    `owner_names` are the owner's name keys, used for authors without an id; `coauthor_ids` the other authors
    of the owner's papers (`own: 1`)."""
    if authors is None:
        authors = {k: v.get('authors') or [] for k, v in details.items()}
    owner_ids, coauthor_ids = set(owner_ids), set(coauthor_ids)
    snapshot_text = str(source['manifest']['as_of'])
    snapshot = date.fromisoformat(snapshot_text[:10])
    target_ids = {t['id'] for t in source['targets']}
    groups, group_of = {}, {}
    for t in source['targets']:     # versions of one paper share a normalized title
        title = str(t.get('scholar_title') or t['title'])
        key = t.get('key') or normalized(title) or t['id']
        g = groups.setdefault(key, {'title': title, 'link': None, 'rank': None, 'years': [], 'works': set()})
        # the link, as on Flow: a published (non-arXiv) DOI first, then the version with the most citations
        doi = t.get('doi') or ''
        rank = (bool(doi) and 'arxiv' not in doi.lower(), t.get('cited_by_count') or 0)
        if g['rank'] is None or rank > g['rank']:
            g['rank'], g['link'] = rank, doi or f"https://openalex.org/{t['id']}"
        if isinstance(t.get('publication_year'), int):
            g['years'].append(t['publication_year'])
        group_of[t['id']] = key

    staged, seen = [], set()
    for w in source['works']:
        if w['id'] in seen:
            continue
        seen.add(w['id'])
        keys = sorted({group_of[t] for t in w.get('targets', []) if t in group_of})
        if not keys:
            continue
        for k in keys:
            groups[k]['works'].add(w['id'])
        staged.append((w, keys))

    order = sorted(groups, key=lambda k: (-len(groups[k]['works']), groups[k]['title'].lower()))
    index = {k: i for i, k in enumerate(order)}
    times = [fractional_time(w, snapshot) for w, _ in staged]
    dated = [math.floor(t) for t, _ in times if t is not None]
    first_year = min(dated) if dated else snapshot.year
    years = list(range(first_year, snapshot.year + 1))

    papers = [{'id': paper_id(k), 't': groups[k]['title'], 'y': min(groups[k]['years']) if groups[k]['years'] else None,
               'n': len(groups[k]['works']), 'u': 0, 'yr': [0] * len(years), 'link': groups[k]['link']} for k in order]

    cities = {c['id']: c for c in source.get('cities', [])}
    countries = source.get('countries', {})
    place_index, places = {}, []

    def place(work):
        for cid in work.get('cities') or []:
            c = cities.get(cid)
            if not c:
                continue
            if cid not in place_index:
                country = countries.get(c.get('country'), {}).get('name') or c.get('country') or ''
                place_index[cid] = len(places)
                places.append([c['name'] + (', ' + country if country else ''), round(c['lon'], 1)])
            return place_index[cid]
        return -1

    works, pair = [], Counter()
    for (w, keys), (t, year_only) in zip(staged, times):
        p = sorted(index[k] for k in keys)
        for pi in p:
            if t is None:
                papers[pi]['u'] += 1
            else:
                papers[pi]['yr'][math.floor(t) - years[0]] += 1
        for a in range(len(p)):
            for b in range(a + 1, len(p)):
                pair[(p[a], p[b])] += 1
        works.append({'id': w['id'], 't': t, 'p': p, 'place': place(w),
                      'flags': (OWN if w['id'] in target_ids else 0) | (YEAR_ONLY if year_only else 0)})
    works.sort(key=lambda x: (x['t'] is None, x['t'] or 0, x['id']))
    position = {w['id']: i for i, w in enumerate(works)}
    for paper in papers:
        assert sum(paper['yr']) + paper['u'] == paper['n']

    links = [(a, b, c) for (a, b), c in pair.items()]
    for paper, (x, y, r) in zip(papers, layout(papers, links)):
        paper['x'], paper['z'], paper['r'] = x, y, r
    pairs = sorted(([a, b, c] for a, b, c in links), key=lambda x: (-x[2], x[0], x[1]))

    # authors with the most distinct citing works; co-authors of the owner's papers are flagged
    author_works, author_name, author_inst = defaultdict(set), {}, defaultdict(Counter)
    for w in works:
        for a in authors.get(w['id']) or []:
            if not a.get('name'):
                continue
            aid = short_id(a.get('id')) or 'name:' + a['name'].lower()
            if aid in owner_ids or (not a.get('id') and owner_names and name_match(a['name'], owner_names)):
                continue
            author_works[aid].add(w['id'])
            author_name.setdefault(aid, clean_name(a['name']))
            for inst in a.get('institutions') or []:
                author_inst[aid][short_id(inst)] += 1
    own_authors = coauthor_ids & set(author_works)
    insts = source.get('institutions', {})
    ranked = sorted(author_works, key=lambda a: (-len(author_works[a]), author_name[a]))
    rank = {a: i for i, a in enumerate(ranked)}
    outside = [a for a in ranked if a not in own_authors][:citer_limit]
    own = [a for a in ranked if a in own_authors][:12]
    citers = []
    for aid in sorted(outside + own, key=rank.get):
        top = author_inst[aid].most_common(1)
        citers.append({'name': author_name[aid], 'own': 1 if aid in own_authors else 0,
                       'inst': insts.get(top[0][0], {}).get('display_name', '') if top else '',
                       'w': sorted(position[i] for i in author_works[aid])})

    view_details = []
    for w in works:
        d = details.get(w['id']) or {}
        view_details.append([d.get('title') or '', byline(authors.get(w['id'])), d.get('doi') or f"https://openalex.org/{w['id']}"])

    views = {
        'owner': str(source.get('owner') or ''), 'snapshot': snapshot_text, 'years': years,
        'stats': {'papers': len(papers), 'works': len(works), 'undated': sum(w['t'] is None for w in works),
                  'multi': sum(len(w['p']) > 1 for w in works)},
        'papers': papers, 'pairs': pairs[:600],
        'works': [[w['t'], w['p'], w['place'], w['flags']] for w in works],
        'places': places, 'citers': citers,
    }
    return views, view_details


def full_authors(raw_works):
    """short work id -> every author [{id, name, institutions}], from citing.json (unfiltered)."""
    return {short_id(w.get('id')): w.get('authors') or [] for w in raw_works}


def script_json(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':'))
            .replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029'))


def write(output, source, details, raw_works, owner_ids=(), coauthor_ids=(), owner_names=frozenset()):
    views, view_details = transform(source, details, full_authors(raw_works), owner_ids, coauthor_ids,
                                    owner_names=owner_names)
    (output / 'views.js').write_text('window.CITATION_VIEWS=' + script_json(views) + ';\n', encoding='utf-8')
    (output / 'views-details.js').write_text('window.CITATION_VIEW_DETAILS=' + script_json(view_details) + ';\n',
                                             encoding='utf-8')
    return views['stats']
