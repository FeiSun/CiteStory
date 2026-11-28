# Implementation notes

## 2026-11-26: Promo video of the eight views

- Assumptions/decisions:
  - 16:9, 1920x1080, 60 fps, about 43 s, light theme, English text (chosen by the author). No audio.
  - Recorded from `profiles/feisun/site`, the real generated pages. Each view is laid out at 1280x720, rendered at 1.3x and framed on a stage with a caption strip.
  - Order: intro, Atlas, Reach, Story, Flow, Constellation, Race, Regulars, Record, outro. Shots are joined by a 0.7 s horizontal push.
  - Record's caption says "One turn for every year", not "Listen to it", because the video is silent.
- Tradeoffs/deviations:
  - Replays are time-lapsed (Race about 6x, Constellation about 5x, Reach about 3x, Atlas 1.6x, Story 1.5x, Record 1.3x from 2022 on). Reach and Race run their sparse early years faster than the late ones.
  - Regulars has no animation on the page; the video wipes the chart in along its time axis. Flow opens the year range from 2012–2020 to all years once, with the page's 0.62 s tween slowed to 2.7 s.
  - Atlas: MapLibre draws a single world while the globe unfolds, which leaves part of the wide view empty, so the unfold runs at 3x.
  - Story stops at five of its fourteen sections (1, 4, 8, 10, 11).
  - Regulars shows other people's names, as the README screenshot does.
- Implementation notes:
  - `promo/lib.mjs` drives headless Chrome over CDP with Node's built-in WebSocket; no packages. A script injected before the page's own replaces `performance.now`, `Date`, `requestAnimationFrame` and timers with a virtual clock, and drives CSS animations and transitions through `document.getAnimations()`. One clock step per screenshot gives exact 60 fps however slowly the page renders.
  - A finished CSS animation with a fill mode stays in `getAnimations()`; the clock keeps a set of finished ones so they are not restarted.
  - Atlas waits for `map.areTilesLoaded()` before each frame, so it needs the network (MapLibre, OpenFreeMap).
  - `promo/scenes.mjs` holds the shots and captions, `promo/stage.html` the intro, outro and caption frames, `promo/compose.mjs` the ffmpeg graph. ffmpeg here is 4.2, which has no `xfade`; the push is done with `overlay` x expressions.
  - Rebuild: `node promo/record.mjs && node promo/compose.mjs` (about 6 minutes). `STILLS=40 node promo/record.mjs atlas` saves stills instead of a clip.
  - `promo/out/` is ignored by git: it is derived from a personal profile.
- Tests:
  - Checked contact sheets and full-size frames of every shot, the transitions and both cards. ffprobe: 1920x1080, yuv420p, 60 fps, 42.75 s. freezedetect: no still stretch over 0.6 s inside a view; the intro text holds 1 s and the end card 2.4 s.
  - One independent review of the first cut; fixed what it confirmed (Atlas unfold gap and long end hold, blank first frame, Story pace and cut-off ending, Regulars hold, outro without the product name, jerky Flow, Record stuck in the quiet years).
- Follow-ups:
  - No music or sound. The Record page's own audio is not captured.
  - A vertical 9:16 cut would need the pages recorded at a narrow layout.

## 2026-11-26: Promo video: blurred names and a soundtrack

- Assumptions/decisions:
  - Other people's names are blurred in the video only (CSS `filter: blur(7px)` injected by the recorder): the name and institution label of each Regulars row (`#chart text.name`) and the author line in Record (`#nBy`). The site itself is unchanged. The profile owner's name, paper titles, cities and the institution table stay readable.
  - The music is synthesised by `promo/music.mjs`, so nothing is downloaded and there is no licence to track: a soft pad in D major (D, Bm7, Gmaj7, Asus4) that changes chord at each shot, two chords for a shot longer than 6 s, and a plucked arpeggio at 100 bpm with a ping-pong echo. It fades out over the end card.
- Tradeoffs/deviations:
  - This is simple additive synthesis, not a produced track. Record's own sonification is still not in the video.
- Implementation notes:
  - `compose.mjs` passes the shot start times to `writeMusic`, writes `out/music.wav` and muxes it as AAC 192 kb/s stereo.
- Tests:
  - Frames at 33.6 s and 37.5 s: names unreadable, everything else sharp. Audio stream present, 42.75 s, mean −17.3 dB, peak −4.4 dB. Spectrogram shows the chord changes and the arpeggio as intended. Nobody has listened to it yet: the author should.
- Follow-ups:
  - To use another track, replace `out/music.wav` in the `ffmpeg` inputs of `compose.mjs`.

## 2026-11-26: README opening with wordmark, badges and the promo animation

- Assumptions/decisions:
  - Both READMEs open with a centred wordmark ("Cite" in ink, "Story" in the accent orange, as in the video), the tagline, four badges, links to the eight views and the language switch.
  - The wordmark is a PNG, because GitHub strips colour from README text and an SVG would fall back to another serif off the Mac. `docs/wordmark-light.png` and `docs/wordmark-dark.png` are switched with GitHub's `#gh-light-mode-only` / `#gh-dark-mode-only` fragments, which follow the GitHub theme setting; a `<picture>` with `prefers-color-scheme` followed the operating system instead and showed the light-ink version on GitHub's light theme; `node promo/wordmark.mjs` regenerates them.
  - The first animation is now `docs/screenshots/promo.webp`, made from the promo video (960x540, 30 fps, 1283 frames, 12.2 MB, silent). GitHub does not play a video file from the repository in a README, so the video itself is not embedded.
  - `atlas.webp` moved under the Atlas heading, replacing the sentence that pointed to the top of the page.
- Tradeoffs/deviations:
  - The badges are loaded from img.shields.io, a third-party service, on every view of the README.
  - The static-HTML badge URL uses `%20` instead of `_`: GitHub's image proxy had cached a failed fetch of the first URL, and a new URL makes it fetch again.
  - `promo.webp` adds 12.2 MB to the repository. It was 5.8 MB at 12.5 fps, which the author found too choppy; quality 38 at 30 fps saved 2 MB but showed blocks in the flat background.
- Implementation notes:
  - Made with `ffmpeg -vf fps=30,scale=960:540` to PNG frames, then `img2webp -lossy -q 55 -m 4 -d 33`.
- Tests:
  - Rendered the opening at GitHub's content width in light and dark: wordmark, badges, links and animation display as intended. Anchors were derived from the headings, not clicked on GitHub.
- Follow-ups:
  - To have the video with sound on GitHub, drag the MP4 into the README editor on github.com and use the URL it produces.

## 2026-11-27: Fixes from an outside review (Gemini) of the eight views and the pipeline

- Assumptions/decisions:
  - Each claim was checked against the source before changing anything. Fixed: Constellation thread width and halo extent, Race end-of-record overtakes, Atlas replay end and feed, Atlas country rows, Story split dots, Regulars label width, island continents, title matching, preprint→published re-match, citing.json write volume, stale file counts in the docs.
  - Not changed: Race "Since publication" opening at age 4 and Play continuing from there (the playhead is where the reader left it; 0–4 is already drawn). Atlas detail refresh comparing `c.name`: refresh only ever redraws the city on top of the stack, so a same-name city cannot be confused there.
- Tradeoffs/deviations:
  - Constellation: the halo (ring tint, outline, label and hit radius, figure-line ends) now uses `extent[j]`, the outermost shown slot, instead of `count[j]`. Mid-year it can jump by up to one year's band when a work that cites several papers is placed on the outer side of its year ring. Dot placement is unchanged.
  - Race: at the final calendar sample, an overtake counts only if it also holds without the undated works that join there.
  - Atlas: replay and scrubbing stop at `TLAST` (the snapshot, or the last dated work) and then show all years; the year axis still runs to the end of the last year. A city whose first work is undated is shown as "undated" in the feed.
  - `match_papers` searches a known Scholar row again only when its venue or year changed since the previous snapshot (what Scholar shows when it merges a preprint with its published version), and keeps the works found before. A merge that leaves venue and year unchanged is still missed; `--restart` does not help, because matches come from `data/targets.json`.
  - `title_match`: the fuzzy path (ratio ≥ 0.95) now also needs the same numbers and Roman numerals (Part I/II, (2021)/(2024), Version 2/3). None of the current profile's matches used the fuzzy path.
  - `pending/citing.json` is saved every 10 pages, at the end of each group and before any error ends the run (a `finally`), instead of after every page. A run killed without Python unwinding (SIGKILL, power loss) fetches again at most 10 pages.
- Implementation notes:
  - Continents: `CONTINENT_FIX` (MU, SC, SH, IO → Africa; MV → Asia; GS → South America) and `EXTRA_COUNTRIES` (RE, YT, GP, MQ, GF, which Natural Earth folds into France) in `build_citation_geo.py`.
  - Regulars measures names and institutions with a canvas `measureText` in the page's fonts and cuts them with an ellipsis to the label column.
  - Atlas finds the year range with a loop instead of `Math.min(...array)`, which throws past ~65k arguments in Safari.
  - The "sent only N" error in `collect_citing` printed 0 because `received` was reset first; fixed while moving that block.
- Tests:
  - 57 unit tests pass (4 new: title numbers, re-match on venue change, batched saves, island continents).
  - Rebuilt `profiles/feisun/site` and checked in the browser: Constellation threads and halo mid-year, Atlas replay ends "Through Oct 2026" then all years, feed titles present, a country row moves the map; Regulars labels end at x=289 with squares from x=314; Race and Story load and scroll with no console errors.
- Follow-ups:
  - Feature ideas from the review (amplifier papers, CD index, intellectual neighbourhood, firestarter cities, Reach paper picker, cross-view links, poster export) are not implemented; see the reply in the session.

## 2026-11-27: Reach paper filter, ?paper= links across views, first-reached cities

- Assumptions/decisions:
  - The shared paper key is `paper_id(key)` = first 8 hex of sha1(normalized title) (`build_views.py`); `id` on views.js papers, `pid` on data.js targets. It stays stable across rebuilds while the Scholar title stays the same.
  - Six views take part: Atlas, Reach, Flow, Constellation, Race, Record. Story (long read) and Regulars (authors) do not; Year was left untouched as asked.
  - "Firestarter" was done as a fact, not a claim: the Atlas feed adds "with co-authors in X" when a city's first citing paper also had authors in a city already lit (strictly earlier), and Story's last step gives the count (741 of 1,307 cities today). No new view.
- Implementation notes:
  - New partial `templates/_views.html` (`PaperViews`: get/set ?paper= via history.replaceState, plus the "Open in" row), inlined into `_picker.html` and `flow.html` by the build. PaperPicker gained `here` and `initial()`; it writes the URL on every change but not at construction, so ?paper= survives until the page reads it.
  - Reach keeps `allWorks` and a filtered `works`; `settle()`, `rank()` and `countYears()` recompute first-cited times, final counts, dot scale, label order, rose max and spark; detail lists use `o.on`. The slider range stays global; a replay from the end starts at the first citation (Atlas does the same now).
  - Atlas now groups targets by the build's `key` (it used JS `toLowerCase`, which can split titles that Python's `casefold` joins).
  - Race keeps the chosen paper across the Calendar / Since publication switch.
- Tests:
  - 60 unit tests pass (new: paper ids in views, matching ids in both data files and the partial inlined in the pages).
  - Browser: every view opens on the paper from ?paper=, choosing or clearing a paper updates the URL, Reach recomputes for small and large papers (including a selected city), and the Atlas feed shows the co-author line. Checked the light theme and mobile. No console errors.
  - A fresh reviewer found no severe bugs. Five findings were fixed: Atlas grouping key, Story year-only ordering, Story denominator, Reach replay start, Race mode switch clearing the paper. Link spacing was also tightened.
- Follow-ups:
  - Poster export, the CD index and merging the two details files are not done.

## 2026-11-27: Second Gemini review: date certainty, Flow links, fetch gaps, Constellation lines

- Assumptions/decisions:
  - A year-only work (`yo`) sits on a hashed day of its year. "Already on the map" (Atlas co-author mark, Story's first-reached count) now needs certainty: year-only dates are the interval [year, year+1) and count as earlier only across a year boundary. Story: 741 → 729 cities for feisun, matching the review's 12.
  - Recent-paper lists (Flow, Atlas, Reach, Story) put year-only works after the dated works of the same year.
  - Constellation lines: shallow quadratic arcs between centres, drawn before rings/dots, each clipped (evenodd) away from its own two halos with a 6 px margin. Where a line passes under another star it is faded (`destination-out` at 0.65 over every halo), so it never reads as ending at a third star. Opacity 0.2–0.6, width 0.6–1.9. A first version cut every halo; the reviewer showed that hid most links at the default zoom and made cut ends look like links to a third star.
  - Removed `al-folio/` (project page and setup notes): putting the pages on a site is the site's job. The theme key and `?embed` mode stay.
- Tradeoffs/deviations:
  - Pairs whose halos (plus margins) touch get no line: closeness already shows the link. The selected star's accent threads still run centre to centre, unchanged.
  - `awaiting_published` re-searches a recent row (this year or last) with a non-preprint venue while all matched works are preprints (no DOI or an arXiv DOI). A published version without a DOI (ICLR, NeurIPS) keeps it re-searching for up to two years: one search per such row per update.
  - The arXiv lookup by DOI checks the owner on the byline but not the title, since the DOI is the identity.
- Implementation notes:
  - Flow: a `?paper=` paper ranked below the top 12 opens "All papers"; a paper with no located citing papers is pinned too (the panel shows its empty state).
  - Atlas: replay speed is the chosen paper's span / 9 s (min 0.2 years/s), so a recent paper no longer finishes before the globe unfolds; changing paper mid-replay resets the clock. The embed's "Open full page" href follows the chosen paper (set on filter change and at start).
  - The arXiv id is read from `arXiv:NNNN.NNNNN` or the CoRR form `abs/NNNN.NNNNN`.
  - Build: `page_date` dates year-only/undated-with-year works as views.js does; `yo` comes from `work_day`; `page_year` clamps a forthcoming year to the snapshot (W7225898716: 2027 → 2026).
  - Reach and Story got `<meta name="referrer" content="no-referrer">` (Atlas keeps its own policy for tiles). Regulars re-renders when fonts load. Record suspends the AudioContext 400 ms after sound off.
  - Checked, not changed: the `before` dict in match_papers collapses duplicate Scholar titles; the only effect is an extra search. The six unmatched feisun rows: two have arXiv ids and should now match; the cause for the other four (three ICLR 2026, one Chinese journal) was not verified against the API.
- Tests:
  - 63 unit tests pass (new: published-version re-search and its stop, arXiv DOI lookup, page_works year-only date and year clamp).
  - A fresh reviewer found no logic bugs; fixed its Constellation finding (above) and four low ones (Atlas clock on paper change, full-page href, CoRR arXiv form, two stale comments). Not changed: DOI-less published versions keep `awaiting_published` re-searching (cost noted above); Flow "Show top 12" can leave a pin on a hidden node (existing pattern).
  - Browser: Flow with a rank-31 paper (All papers, pinned) and a paper with no locations (empty state); Atlas with a 2025 paper replays over ~9 s after the globe; Story shows 729/578; Constellation in light and dark. No console errors.
- Follow-ups:
  - Not done: data file size reduction, promo/ portability (Chrome path, profile path), Gemini's feature ideas.

## 2026-11-27: Unmatched papers checked against OpenAlex, matching by author id, golden-angle window tried

- Assumptions/decisions:
  - Removed `al-folio/`: putting the pages on a site is the site's job (user's call). The theme key and `?embed` stay.
  - Matching: before any title search, list every work under the owner's OpenAlex author ids (profile `openalex_author_ids`, the previous snapshot's `owner_authors`, and ids found so far in this run) and match rows there with the same title and owner checks. Only rows with nothing new there are searched. The list is fetched when at least 5 rows are still to match, and again for each new id found; more than 2,000 works under the ids means they likely merge other people, so the list is skipped.
- Tradeoffs/deviations:
  - A version not under any owner id (no author id, e.g. W7106830025, a 0-citation conference video record) is no longer found when the list already matched the row. 2 of 92 rows lose such a version on feisun, both with 0 citations.
  - Golden-angle window (Gemini's idea): restricting a multi-citing dot to free slots within ±k of its time rank. Measured on feisun: 13 consecutive golden-angle slots leave a 32.5° gap (not 14°). ±10 cut the worst mid-year halo overshoot from 1,382 slots to 10, but the facing error rose (median 12° → 19°), and on screen BERT4Rec's red half-disc dissolved into a mottle across the disc. Reverted: the end-state picture matters more than the mid-replay halo, which `extent[j]` already keeps correct.
- Implementation notes:
  - OpenAlex check of the 6 unmatched feisun rows (top-50 search, title.search filter, arXiv DOI): none of the four (three ICLR 2026, the 计算机学报 survey) nor "A Survey on Unlearning in LLMs" (arXiv 2510.25117) is in OpenAlex; a deeper search would not help. "Detect Before You Attribute" is in OpenAlex under its first arXiv title ("Cascade Failure Attribution for Multi-Agent Systems") and now matches through the arXiv DOI lookup.
  - `hit_record` and `owner_pool` factored out of `match_papers`.
- Tests:
  - 64 unit tests pass (new: rows matched from the owner's works skip the title search).
  - Live first-run match for feisun (no previous snapshot): 59 requests instead of 108; 103 rows matched (102 before, plus the arXiv one).
- Follow-ups:
  - None.

## 2026-11-27: Third Gemini review

- Assumptions/decisions:
  - Atlas and Story: another city counts as already on the map when any of its papers certainly came before (a year-only one ends with its year), not only its first paper by spread date. Tightens the bound for 41 cities on feisun; the total stays 729 because those cities' co-author cities were already counted through other cities.
  - Matching: a row whose author-id list match is only a preprint while Scholar shows a published venue (`awaiting_published`) is searched by title too. Ids found late in the run are listed at the end, and every row matched this run takes further versions from the full list at no cost. Live first-run for feisun: 60 requests (59 before this change), 107 versions.
  - Flow: changing Top 12 / All papers drops a pinned "Other papers" node or link, and re-resolves a pinned paper to its node in the new layout.
- Tradeoffs/deviations:
  - Reach slows a short replay (min(1.15, span/9) years/s, at least 0.2) and stops playback when the paper changes. Atlas keeps playing and resets its clock, as before.
- Implementation notes:
  - Constellation: `together(p)` (p.n at "All years", else the count so far) drives figure lines, threads and both panels.
  - Regulars: newest first, year-only after that year's dated papers, undated last.
  - Atlas picker mini chart skips undated works. Story omits a missing publication year and "since Infinity". Race: `vmax` at least 1; in "Since publication", the dotted part past a paper's age has a 7 px pick radius and the tooltip says "now (age)". Record: the suspend timer is cleared on every toggle.
- Tests:
  - 65 unit tests pass (new: a preprint-only list match is searched too).
  - Browser: Story 729/578 and null-safe text; Atlas feed co-author marks during replay; Flow "Other papers" then "Show all papers" leaves no stale pin; Regulars order; Race tooltip "now (7 y 11 mo)"; Constellation. No console errors.
- Follow-ups:
  - Not done (suggestions): a `doctor` summary after update, Story/Regulars links into `?paper=`, a GitHub Actions example.

## 2026-11-27: Fourth Gemini review

- Assumptions/decisions:
  - `openalex_author_ids` accept an id in any case, a URL or an author page address (`author_id`), are saved in targets.json and join the owner ids in the build (Regulars and the other views leave them out as readers). Ids the profile names are always listed, even with fewer than 5 rows left to match.
  - Home: when `home` is not set, it is guessed again after the institutions are fetched (the owner's institutions are fetched too), counting only institutions with a city. An umbrella body without a city no longer stops the build.
  - The build names the home city (`home.city`): the city with the home institution's city id, else one of the same country with the same name within 25 km or any within 8 km (merge_nearby's rule), else null. Atlas and Story use it; the old 0.35° nearest-city match could bind Shenzhen's home to Hong Kong.
  - Story, when no citing paper comes from the home city: no city is highlighted or labelled home; the home marker sits at the institution's coordinates.
  - Constellation: a star nobody cites yet cannot be selected (it is not in the paper list); a replay with a paper selected starts at its first citation (`player.setStart`).
  - views.js paper links prefer a published (non-arXiv) DOI, then the most-cited version, as Flow does.
- Tradeoffs/deviations:
  - Not changed: README "the eight views" describes the promo video, which shows eight views (Year is not in it), so it does not contradict "nine pages". promo/ stays a personal recording tool with fixed paths.
  - Not done (suggestions): build-time overrides from profile.json, merging the two details files.
- Tests:
  - 68 unit tests pass (new: author id forms, home guess skipping a cityless body, home city match vs a cross-border neighbour, published DOI link).
  - feisun: home.city = Beijing; no arXiv link where a published DOI exists. Browser: Story home text, Atlas, Constellation replay from 2019 with BERT4Rec selected. No console errors.

## 2026-11-27: Fifth Gemini review (fixes to the fourth round)

- Assumptions/decisions:
  - Regression fixed: the Story explorer's home dot had been commented out by a `//` note I appended mid-line in the previous round. Checked every line added this session for code after a line comment; none other.
  - Story: the home country (text, peers, country count) is the institution's country (`HOME_ISO`), not the country of a stand-in city across a border.
  - `home` in profile.json accepts an id in any case, a URL or a page address (`author_id(v, "i")`); anything else stops `update` with a clear message.
  - `guess_home` picks its three recent years among works with a placed institution.
  - `home_city`: the home institution's city id, through merge_nearby's map (now passed from `aggregate`); then a same-name city within 25 km; then a city within 8 km with at least ten citing papers. A town of its own (Boston beside Cambridge with a few papers) is no longer taken for home.
  - Constellation: an uncited star shows no pointer and a click on it acts as empty sky; the "Cited together" rows go through `choose` (replay start, announcement); choosing a paper whose first citation is after the current time stops and moves to the end, as Record does.
- Tests:
  - 68 unit tests pass (extended: merged home key, Cambridge/Boston, recent years without a city, institution id forms).
  - Browser: Story home dot and ring drawn (canvas call count), "· home" on Beijing; Constellation pair row then Play starts Mar 2019. No console errors.

## 2026-11-28: Full code review and fixes (all views except Year, Python pipeline, promo)

- Assumptions/decisions:
  - Out of scope, left as is: moving Reach, Atlas, Story, Flow and index onto `_shell.html` and unifying their tokens and theme code (a redesign, not a fix); Atlas's dense one-line style; `year.html` (excluded from the review, and edited by other work during this one).
  - New contract: `data.js`'s details loader sets `CITATION_DATA.detailsFailed` and fires `citation-details-failed` when `data-details.js` cannot load; Atlas, Reach and Story show "could not be loaded" instead of loading forever. The shell's `views-details.js` loader stays failed instead of retrying on every pointer move.
  - Reduced motion: every view reads the media query live; Play steps one year at a time instead of animating (it did nothing before in Race and Constellation, and ran the full animation in Atlas).
  - Country names: the build takes Natural Earth's `NAME_LONG` when `NAME` is abbreviated ("Dem. Rep. Congo"), so Story's own name patches are gone and every page gets the full names.
  - Story now takes part in `?paper=` and is listed in `_views.html`.
- Tradeoffs/deviations:
  - Force layout kept exact (O(700·n²) in pure Python: about 2 s for 100 papers, 3 min for 1,000). A grid cutoff was tried and measured on 1,000 synthetic papers: 51 s / 31 overlapping pairs at a 120-unit cutoff, 107 s / 11 at 200, 144 s / 6 at 300, against 171 s / 2 exact. The quality loss outweighed the gain; documented in the docstring.
  - Plural merging: `-ies` now becomes `-y` (studies, strategies, queries), with a list of `-ie` words (selfies, zombies…) as exceptions.
  - Reach's ring labels now sit in the emptiest bearing sector instead of a fixed 118° that only suited an East Asian home.
- Implementation notes:
  - Bugs fixed (highest first):
    - Record: a flick doubled requestAnimationFrame callbacks every frame and hung the tab.
    - Python 3.9 timeouts: `socket.timeout` is not a `TimeoutError` there, so it went uncaught.
    - Reach: month labels were one month early at 4 of 12 slider stops.
    - Race and Constellation: Float32 time arrays were compared with double times.
    - Atlas: added an error and timeout fallback for the basemap.
    - Build: writes `site.partial/` and swaps folders by rename, keeping non-build files in `site/`, and removes the partial folder on failure.
    - Flow: label font size disagreed with its CSS.
    - Accessibility and focus fixes across pages.
    - WebGL context loss handled in Story and Record.
  - Review fixes:
    - `Client.get` retries only request and parse errors; a local cache or log write error is raised as it is.
    - Race's events section no longer reappears empty.
    - Atlas treats only a failed style fetch as fatal.
    - A promo take is encoded to `<name>.partial.mp4` and replaces the clip only on success.
    - Second review: `site/` as a symlink is resolved and its folder rebuilt; a `site.old` left by a run stopped
      mid-swap is put back first; Atlas also treats a URL-less network error before the style as fatal; a failed
      final encode removes its partial file; irregular plurals (theses, indices, matrices…) join `ONE`.
  - Shared helpers: `Shell.fitText`, `Shell.chip` and `Shell.onDensityChange` replace copies in Race, Regulars and Constellation.
  - Python de-duplication: `short` and `script_json` each exist once; `get_paper_list` lost its unused argument.
  - Dead code removed: Atlas's Equal Earth block, half of Story's `MapView`, Race's `ahead`/`hue`/`playing`, and more.
  - Promo:
    - Profile from `CITESTORY_PROFILE`, Chrome from `CHROME_PATH`.
    - Node and ffmpeg are checked up front.
    - Chrome and temp profiles are cleaned up on failure.
    - No ffmpeg filter paths.
    - New `promo/README.md`.
  - Docs: DATA.md antimeridian sentence corrected (no basemap ring crosses ±180°); `?paper=` lists include Story; reduced-motion Play described.
- Tests:
  - 69 unit tests pass. New or extended:
    - timeouts and dropped connections retried, then reported;
    - a disk error is not retried;
    - a failed build keeps the old site, a user file and no staging folder;
    - an interrupted swap is recovered, and a symlinked site/ keeps its link;
    - -ies / -ie plurals.
  - `node --check` on every inline script of every template and every promo `.mjs`.
  - Rebuilt `profiles/feisun/site`. In the browser all pages load without console errors:
    - Atlas map loads, and its fallback note was seen and cleared.
    - Record: a flick keeps one pending frame.
    - Race labels are ellipsized.
  - Two independent reviews of the diff; their confirmed findings are fixed.
- Follow-ups:
  - The shell migration above.
  - The promo recorder was only syntax-checked and probed, not run end to end.
  - `build_year.km` (haversine) and `build_citation_geo.km` (acos) are two distance functions with different signatures.

## 2026-11-28: Fixes from an outside (Gemini) review

- Assumptions/decisions:
  - Every finding was checked against the code first. All held up except the size of the Flow promo risk, which was smaller than claimed.
  - Snapshot timestamps: new ones are written to the second (`timespec="seconds"`). The build trims microseconds from older ones, so every page gets a standard ISO time. Reach also falls back to the current date when parsing fails.
  - The resume check keeps the count from the listing's first page. A run resumed days later then sees the same total it started with.
  - A byline with no OpenAlex id is no longer carried across years in `seen_people`, matching `since`, streaks and `back`.
  - The first work from each place now prefers one with a real date. Works known only by their year come after it, in `year_cities` and `year_countries`, and therefore also in `firsts`, `far`, `near` and `new_cities`.
  - `clean_name` moved to `build_views.py`, so the names in views.js and its bylines lose footnote marks too.
- Tradeoffs/deviations:
  - `code/templates/s.js` was not deleted: it came from other work in this folder, so the user decides.
  - The suggested data split (`land` out of data.js, one shared details file) was not done. Reach and Story do use `land`, and the split changes the data contract.
- Implementation notes:
  - Name matching:
    - CJK names written with spaces also produce the joined key.
    - Owner names of three or more tokens add initials keys, for example "JP Dupont".
    - Strings of titles such as "Prof. Dr." are stripped.
  - Front end:
    - Flow shows "could not be loaded" when details fail.
    - Race and Reach guard against a zero time span.
    - When the map loads after the 20 s fallback, Atlas skips the intro (`mapGaveUp`).
    - Atlas, Reach and Flow add the owner's name to their titles.
  - `profile.json`: bad JSON, a value that is not an object, and string fields that are not strings now each stop with a message.
  - Promo:
    - Reach's length is computed from its slider range.
    - Flow starts from the middle of the record.
    - compose.mjs writes `.partial.mp4` and renames it when done.
  - Docs: DATA.md now covers `k`, `fresh` and the `y` rule. Both README trees list `city_names_zh.json`, `_views.html` and `promo/`. `.gitignore` covers `.pytest_cache/` and `*.pyc`.
- Tests:
  - 73 unit tests pass. New ones cover streak order with split ids, no-id bylines across years, dated works winning a place, resume after the count grew, hyphenated initials, spaced Chinese names, title strings, and bylines without marks.
  - pyflakes is clean, and `node --check` passes on the changed scripts.
  - The real site was rebuilt (`as_of` now ends at seconds).
  - In the browser:
    - Titles carry the owner's name.
    - Flow shows the failure message.
    - Atlas stays put when the map loads after a forced fallback.
    - Race shows 14 events.
    - No console errors.
- Follow-ups:
  - The single-time-point guards in Race and Reach were not tried on a real one-year record.
  - The promo scripts were syntax-checked only.
