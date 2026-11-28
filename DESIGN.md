# Design notes

**English** | [简体中文](DESIGN.zh-CN.md)

Why the nine pages look and behave as they do. The [README](README.md) says what each view shows; this
file says why it was built that way, what was tried and dropped, and which rules all the views share. The
constants quoted here are the ones in `code/templates/` and `code/build_views.py`; if you change one, change
it here too.

## Contents

- [The brief](#the-brief)
- [Rules shared by every view](#rules-shared-by-every-view)
- [Atlas](#atlas)
- [Reach](#reach)
- [Story](#story)
- [Flow](#flow)
- [Constellation](#constellation)
- [Race](#race)
- [Regulars](#regulars)
- [Record](#record)
- [Year](#year)
- [Tried and dropped](#tried-and-dropped)

## The brief

The project started from one question: starting from one person's papers, can we find every paper that
cites them, find where its authors work, and show on a world map which cities read the work? The bar for the
result was set at the same time: elegant, simple, with a sense of design, and surprising enough that people
want to look. A second goal grew alongside: every picture should also say something true that the citation
count alone cannot.

Each view answers one question, and no two answer the same one:

| view | question |
|---|---|
| Atlas | Which cities read the work, and in what order did they arrive? |
| Reach | How far from home did it travel, and in which directions? |
| Story | What happened, told in order, with the numbers in the text? |
| Flow | Which paper took the work to which parts of the world? |
| Constellation | Which papers are cited together, and how did each one's readership build up? |
| Race | Which paper led when, and which took off fastest? |
| Regulars | Who keeps coming back? |
| Record | What does the history sound like? |
| Year | What did one year bring: which new papers, readers and places? |

The tool is not about one person. Nothing in `code/` names a person or a paper; the owner, home city
and titles all come from the data. The one table of places is `code/venues.json`, which lists where
conferences met.

## Rules shared by every view

**A mark is a paper.** Wherever a view draws one mark per citing paper (a dot, a square, a cut), the mark
stands for a real paper you can hover and open. Totals count each citing paper once, even when it cites
several of the owner's papers, because the views ask who reads the work and where; counting it three times
would make its city look three times as busy. Per-paper numbers (Flow's paper column, Race, Constellation's
halos, the paper picker) count it once for each paper it cites, as Google Scholar does. The README's
[How the numbers are made](README.md#how-the-numbers-are-made) gives the full rules.

**Show only what the data supports.** OpenAlex gives most institutions a city-level point, not a campus, so
no view draws institutions at their own position. Arcs run straight along great circles; they show a
connection, not a route. Text is computed from the data, comparison words are chosen from the computed
values, and a Story chapter that the data cannot support is left out rather than written vaguely.

**Square root for size.** Counts are very uneven: one city or one paper often has a hundred times the next.
Glow, arc strength, dot radius in Reach, ribbon thickness in Race and the yearly sparklines use the square
root of the count, so the long tail of places and papers with one or two citations stays visible. The
Atlas scales against the largest city other than home, because home is inflated by self-citations and
nearby colleagues.

**Time.** OpenAlex writes 1 January when it knows only the year. Those papers are spread over their year by
a stable hash of their id at build time, so the animations do not jump every January and every page places a
paper on the same day. Pages that show single papers draw them hollow or fainter and give only the year.
Papers dated after the snapshot are moved back to the snapshot date. Undated papers are counted only at the
end, in the "All years" state.

The pages with a play button that share `_shell.html` (Constellation, Race, Record) play calendar time on a
clock that is 35% linear and 65% by citation density, so the busy recent years get more of the playback time
than the sparse early ones. Race's "Since publication" clock is linear.

**One paper across views.** Atlas, Reach, Story, Flow, Constellation, Race and Record can each focus on one paper.
Choosing it writes `?paper=` to the address, so the page can be bookmarked or shared, and an "Open in" row
under the paper links to the same paper in the other views. The id is a hash of the paper's normalized
title, so it survives rebuilds and new snapshots while the title on the profile stays the same.

**Look.** The pages were made to sit inside an [al-folio](https://github.com/alshedivat/al-folio) homepage:
serif headings (Iowan Old Style, then Palatino and Georgia), a warm paper background in the light theme and
dark navy in the dark one, hairline rules, pill-shaped segmented buttons and a side column of 340–380 px.
They share al-folio's `theme` key in `localStorage`, so a page and the site switch theme together, and every
page applies the saved theme before the first paint, so it does not flash. Without a saved choice they follow
the system, and fall back to light.

In Constellation, Regulars and Record the accent colour marks a citing paper that cites two or more of the
owner's papers. Constellation also uses it for the selected star and the threads to its partners.

**Words.** No captions that explain how to use the page, no secondary labels, short nouns. Paper titles
come from the Scholar profile and are never turned into acronyms. The picker, the detail headings, Flow and
Record show them in full, wrapping long ones. Where space is short (canvas labels, tooltips and list rows in
Constellation, Race and Regulars) they are cut at the subtitle colon or a word boundary, with an ellipsis.
Explanations live in each page's "About the data" panel, where readers go looking for them.

**Static and small.** Plain HTML, CSS and JavaScript with no framework or build step; the Python pipeline
uses the standard library only. Data ships as `<script src>` files so the pages open from disk. The shared
parts are inlined at build time, so each page is one file. Paper titles, DOIs and authors are in a second
data file that loads after the page appears. Animations run only while something moves, and with reduced
motion each page shows its end state, and play steps through the years one at a time.

## Atlas

**Form.** A globe that turns to home and unfolds into a flat street map, with a point of light for each city
and an arc from home. Play, and the citations arrive in order.

**Why this form.** A map answers "where" at a glance, and the order of arrival turns it into a story. The
opening globe gives the sense of a whole world; the flat map is better for reading. The unfold uses
MapLibre's projection interpolated by zoom, from a vertical-perspective globe to Mercator, so it is one
continuous motion rather than a cut. Real tiles (OpenFreeMap, no key) replaced the first, self-drawn map
because they let you zoom to street level and read city names.

**Choices.**
- A city's glow and arc strength follow the square root of its count, against the largest city other than
  home. Arcs fall into six strength buckets.
- When a city first appears, a short comet runs along its arc and lands with a ring. A small feed names the
  paper behind each new light, so every light can be traced to a real paper. When that paper also had
  authors in a city that was already lit, the feed names that city ("with co-authors in …"). It states who
  wrote the paper, not how the work reached the new city.
- Playback takes about nine seconds of wall-clock time (less for a history under eleven years), whatever
  the frame rate. The page autoplays once,
  unless the reader prefers reduced motion; any press of play or pause takes over. With reduced motion, play
  steps through the years one at a time instead of animating.
- Lights add up (`lighter` blending) on the dark map and darken (`multiply`) on the light one.
- Search finds cities, countries and institutions, ignoring accents.
- `?embed` drops the page's chrome, takes the host site's colours, zooms only with Ctrl/⌘ + scroll so the
  host page still scrolls, and reports its height to the host.

**Dropped.** A layer of institution dots, coloured by type, at high zoom: OpenAlex mostly gives a city
point, so the dots claimed a precision the data does not have. Arcs bundled through hand-drawn corridors
("trans-Pacific trunk"): a citation is not a flight, and the corridors were invented. A self-drawn dark Equal
Earth map that worked offline: superseded by real tiles.

## Reach

**Form.** The world redrawn as a disc around the owner's city, in the azimuthal equidistant projection:
every point sits at its true distance and true bearing from home, and the rim is the antipode.

**Why this form.** "How far did the ideas travel?" is a question about distance from one point, and this is
the one projection in which distance from that point can be read with a ruler. Straight rays from the centre
are the true shortest routes.

**Choices.**
- Rings at 2,000, 5,000, 10,000 and 15,000 km; the rim is labelled "antipode".
- A Linear / Square root switch. Half the placed papers are often within a thousand kilometres or so of home,
  which crowds the centre; the square root spreads it out while keeping bearings and ring values true. With
  it on, rings are added at 500 and 1,000 km.
- Rays are faint for cities with one or two papers and stronger from three and from twenty.
- A rose of 36 ten-degree bins outside the rim shows the directions the work went in.
- A dashed ring marks the median distance. Cities first reached in the year before the date shown are drawn
  in the accent colour, so playback shows the frontier moving.
- A paper picker narrows everything to one paper; dot sizes are then scaled to that paper's largest city.
- The histogram on the right uses the disc's own radius scale, in 40 bands, with a cumulative curve. For the
  distance figures each paper counts once, at its author city nearest to home, so a paper with one local
  author and one distant one does not count as travelling far.

## Story

**Form.** A scrolling long read beside a sticky picture. One dot per citing paper, the same dots throughout:
they start on the map, leave it to become columns of papers per year, bands by continent and rows by
institution, and come back.

**Why this form.** Scrollytelling lets the text and the picture take turns, and keeping the same dots
throughout lets the reader see that the bar chart is made of the papers that were just on the map. An
earlier version faded between separate charts; it was replaced by this one because the continuity is the
point.

**Choices.**
- **Dot counts match the text.** A paper with authors in two cities is a dot in each city; when a chart
  counts papers, the two dots merge. So the number of dots in each scene equals the number in its text.
- On the map each city is a sunflower spiral of dots, oldest at the centre, so area is proportional to count.
  The map is Equal Earth centred on 10°E. Dots are drawn with WebGL.
- Dots leave the map from west to east, along slightly curved paths, so the eye can follow them.
- In the share chart, years with fewer than 30 continent tallies are faded, and the band edges start at the
  first year that reaches 30, so a tiny early year does not look as weighty as a large one.
- The text is written from rules, not for one person:
  - the takeoff year is the year before the sharpest relative rise (the largest ratio between one year and
    the next), counting only rises to at least 5% of the peak year;
  - "the slow years" appear only when there are at least two years before the takeoff and four in all;
  - the three most-cited papers are compared on citations and on countries, with the heading chosen from the
    result;
  - the continent chapter needs at least three continents, and the home chapter needs citations from the
    home city itself;
  - the farthest cities are measured by great-circle distance, with how close each comes to the antipode;
  - countries that appear exactly once are listed and highlighted.

**Dropped.** A dark default theme, marketing-style copy, a floating command bar and a decorative ring of
leftover dots, all from an earlier proposal; the step dots at the side are enough navigation.

## Flow

**Form.** No map at all: three columns, papers to continents to countries, joined by ribbons.

**Why this form.** A map makes it hard to ask about one paper. A Sankey diagram answers "which paper is read
mostly in one country, and which one spread widely?" directly, and a year range shows how that changed.

**Choices.**
- The top 12 papers, with the rest in "Other papers", or all of them. The 16 largest countries, grouped
  under their continent, with the rest in "Elsewhere".
- Papers are ordered by their centre of mass across the continent column, which reduces crossings; the order
  is computed once over all years, so ribbons do not jump when the year range changes.
- Colour is the continent, carried into its countries.
- Ribbon widths count each (citing paper, cited paper, country) once, so the ribbons from a paper add up to
  its full spread. The numbers on the nodes and in the panel count each citing paper once per node. The page
  states both.
- On a phone, "All papers" makes a long chart. That was kept: every row stays a usable touch target, and
  "Top 12" is the readable default.

## Constellation

**Form.** Each of the owner's papers is a star. Its citing papers are dots in rings around it, one ring per
year, the oldest inside. Stars that are cited together sit close together, and lines join the strongest
pairs.

**Why this form.** A network diagram of thousands of papers is a hairball. Folding each paper's citations
into its own halo keeps the picture readable, and two questions answer themselves: how did this paper's
readership build up (the rings), and which papers are read together (the distances and lines).

**Choices.**
- Dots are packed by the golden angle, so each dot takes the same area and a ring's area is that year's
  count. A wide band is a busy year.
- A citing paper that cites several of the owner's papers is drawn in the accent colour in each of their
  halos, on the side of the ring that faces the others. Hovering it joins its copies.
- Star positions come from a force layout run once at build time, with a fixed seed: papers cited together
  attract. The layout is reproducible, and the browser does no physics.
- Lines are the maximum spanning forest of the pairs cited together at least three times, so the strongest
  links show without a web of every pair. They appear as time reaches them.
- Each line is a shallow arc between the two star centres that stops 6 px short of both halos. Where it passes
  under another star it fades, so it never seems to end at a third star. Stars whose halos touch get no line:
  the closeness already says it.
- Canvas labels are shortened to 22 characters (44 when the halo is large or the star is selected or
  hovered), and tooltips and list rows to 24–46. The panel heading and the picker show full titles.

**Dropped.** Dragging stars with elastic threads: the layout is computed from the data, so a dragged star
would mean nothing.

## Race

**Form.** Each paper is a ribbon through time. Its lane is its rank by cumulative citations, its thickness
grows with the square root of its count, and where two ribbons cross, one paper overtook the other. A board
on the right shows the ranking at the playhead.

**Why this form.** A bar chart race shows each moment and forgets it. A bump chart keeps the whole history
visible: you can see who led in 2019 while watching 2024. The bars were dropped and the ribbons became the
chart.

**Choices.**
- A paper enters the ranking at 10 citations (fewer for a small profile: a tenth of the top paper's count),
  so early years are not ranked by noise.
- Ranks are sampled twice a month and smoothed with a moving average of about six months. The window closes
  at the playhead, so a ribbon's head always sits on its true rank.
- An overtake is listed only if the new order holds for six months.
- Twelve lanes (eight on a phone). The ten most-cited papers have their own colours; the rest are neutral.
- The "Since publication" clock starts every paper at its own publication date, so an old paper's head start
  disappears and you can see which one took off fastest. A paper younger than the clock continues as a dotted
  line.

## Regulars

**Form.** The authors who cite the work most, one row each, one square per citing paper, stacked by quarter.

**Why this form.** It is the one view about people rather than papers. Behind a citation count there is
usually a small group of readers who come back again and again. A unit chart lets you count their papers and
see their rhythm: a tall stack is a busy quarter, a long row is a reader who kept coming back.

**Choices.**
- Squares, not dots: overlapping dots hid the count.
- The axis starts at the first percentile of the shown authors' dates; anything earlier goes into an
  "earlier" column, so one early outlier does not stretch the axis.
- Co-authors, meaning anyone on any of the owner's papers, are hidden by default and shown with one switch.
  Citations among collaborators are a different thing from reach.
- Authors are merged by OpenAlex author id, and the full author lists are used, including authors with no
  listed affiliation.
- Three orders: most papers, earliest, and longest span.
- The page lists other people's names from public records. The README asks you to think about that before
  you publish it.

## Record

**Form.** The citation history cut into a record that turns once a year. Every citing paper is a cut in the
groove, from the label outwards. Play it, turn it by hand, or move the needle across the years. With sound
on, you hear it.

**Why this form.** Rhythm is something the ear reads better than the eye. Early sparse years sound sparse,
a breakout sounds like one, and the papers cited together sound together.

**Geometry.** Radius is linear in time, from the label to the rim. A cut is under the needle when its time
is the playhead's. Papers on the same day sit side by side; year-only papers are spread around their year
and drawn fainter. A cut that cites several papers is longer and drawn in the accent colour. The record stays
dark in both themes.

**Sound.**
- Nothing is created until you press Sound: the page is silent by default, and the audio context starts
  inside that click, as browsers require.
- Each of the owner's papers has a fixed note, one of sixteen pitches of D Lydian between D4 and G♯6. The
  notes are handed out by consonance, most-cited paper first: the top three papers play D, A and F♯ (the
  D major triad), the next two add E and B (the pentatonic), then come C♯ and G♯, the note that makes the
  scale Lydian. Papers 8 to 16 repeat that order an octave up. Every later paper shares those nine upper
  notes and plays at 0.7 of the level. The papers heard most therefore sound settled together, and a
  rarely cited paper is heard as colour on top. In the example data the first sixteen papers receive 80%
  of the citations.
- Cuts that pass the needle within one step of 125 ms sound together, as one chord. The first cut after
  a silence sounds at once and starts the grid, so a lone cut is heard exactly as it passes and a busy
  stretch becomes a steady pulse of eight steps a second.
- A step plays two layers. Bells (a triangle wave with a little FM) play the papers cited most by the
  step's cuts that cite one paper. Plucked strings (Karplus–Strong) play the papers cited most by its
  cuts that cite several. Each layer has at most three notes, strummed 24 ms apart, and a paper needs at
  least 35% of the leading paper's count to be included.
- The two layers are balanced by the share of the step's cuts that cite several papers (an equal-power
  crossfade). A single cut is therefore all bell or all string, as the accent colour says, and in a busy
  step the strings are as loud as co-citation is common. The ripple on the record takes its colour from
  the same share.
- The number of cuts in a step sets how loud and bright it is, on a log scale that tops out at 128 cuts:
  the level runs from 0.4 to 1, the bell's FM depth and filter open, and the notes get shorter. Density
  is heard as fullness, not as speed. In the example data a step holds from one cut to about 200.
- With a paper chosen, every step plays only that paper's note; the bell and string balance still follows
  the cuts.
- The sound is panned by the longitude of the citing city, averaged over the cuts of the step.
- A low D (D2 with D3 above it, which small speakers can play) swells into the reverb at each new year.
- A move of more than 400 cuts at once, such as a click on the slider, plays only the cut it lands on.
- Turning the record by hand changes the pitch with the speed, from 0.7 to 1.5 times.
- The echo is three steps long, so it falls on the grid. A limiter sits at the end as protection: in a
  measured playback of the example data it reduced the level by at most 0.3 dB.

**Dropped.** One note per cut with a cap of sixteen notes a second: playback lingers on the busy years, yet
from 2020 on almost every step held more cuts than the cap let through, so the growth could not be heard,
and which cut sounded depended on where the cap's window happened to fall. Notes handed out in scale order,
repeating every sixteen papers, which put the three most-cited papers a tone apart. A six-colour palette in
which colour was the paper's index modulo six, so no colour identified a paper. A spectrum display, a noise
floor, technical labels and a glass panel, all decoration.

## Year

**Form.** The latest calendar year in a handful of full-screen scenes. The year's citing papers are the dots, and
they are the same dots throughout: they spell the year, stack into a calendar, stack again over the years the papers they
cite were written in, split into new and returning readers, fly to the map, shrink to a few stamps, become one column
among all the years, wait behind the names of the year's readers, and end as the map of a card.

**Why this form.** The other eight pages look at the whole record. A year is the unit people remember and
the one this data is most honest at: most dates are exact to the day and the rest to the year, and nothing here needs finer than that. A
look back is also a different kind of reading, closer to a keepsake than a chart, so each screen says one
thing in one or two sentences. It reuses Story's idea, continuity of the dots, and changes how it moves.

**Choices.**
- **Scrolling drives the dots.** Story plays a transition once a step is reached. Here a dot's position is
  a function of the scroll position, so the reader's hand moves the dots and can stop half way. Dots leave
  in date order where time is the subject (the cover, the calendar, the last column) and at random
  elsewhere. With reduced motion the scenes switch without the flight.
- **Every sentence is computed in the build.** `build_year.py` writes the facts and the page only draws
  them, so a number in the text cannot disagree with the dots. A scene whose facts are missing is left out.
- **The year is spelled by its own dots.** The digits hold exactly as many dots as there are citing papers,
  filled from left to right in the order the papers appeared. A faint numeral stays underneath so that a
  year with a dozen citations still reads.
- **Effort first.** The second scene is the owner's own new papers and the conferences they went to, in
  date order. New papers are taken from the Scholar profile, not OpenAlex: a fresh paper is often not yet
  matched, and its year is the one written in its venue ("SIGIR 2026") rather than its preprint's. The route has
  a paper folded into a plane flying the route from one meeting to the next (thin lines from each conference to its paper's first reader were tried and taken out: they crossed the map and were not explained). Conference cities come from `code/venues.json`; nothing is drawn for a paper whose conference is not listed.
- **Moments, not totals.** The text prefers a date and a place to a sum: the busiest day, the first reader
  of a new paper, the nearest new city, the first citation from inside the Arctic Circle.
- **Readers are people outside the author list.** Papers signed by the owner or by any co-author are shown
  as their own group and left out of the names, the institutions and the streaks.
- **Three scenes, three shapes.** The papers are clusters, the readers are columns and the topics are rows.
  An earlier version drew all three as discs of dots, one after another, and they ran together. Readers stand
  in columns by the year their longest-standing author first cited this work, so the papers of new readers make
  one tall column and old friends reach back to the first years. Brackets over the last years count the people
  who cited it every year up to this one, and arcs under the axis, one per person, join the year someone last
  cited it to this one for those who came back after five years or more; the first new reader of the year is
  marked. Topics are ribbons of dots, longest first, like a ranked list.
- **The days are a ring.** With the readers and the last scene both in columns, the calendar became a ring:
  1 January at the top, clockwise, one ray of dots for each day. A ray grows with the square root of its
  count, so that a quiet day still shows beside a day of 125; the busiest days are named at the tip, and an
  arc outside marks the longest run of days. Labels say what they count, the day on one line and the count under it ("Busiest: 6 November" / "125 papers"); the
  paper that made the record's round number (the 10,000th) and the year's first and latest papers are ringed on
  their rays and named.
- **Labels sit in the open.** A label goes where there are no dots, with a line to what it names, rather than on a
  plate over the dots. The one paper that cited eight of the owner's papers at once is a point above the clusters
  with a line down to each of the eight.
- **Stamps stand straight.** A slight tilt was tried and looked careless; the postmark carries the month the
  paper arrived.
- **What is unusual is drawn where it is.** Hospitals and libraries or archives are small road signs on the
  map, a white cross or open book in a rounded ink square (a circled plus read as "add"; red is left out, the red cross being a protected emblem), with a key under the map rather than on it; titles in other scripts are small round clusters in one band under the phrases, each named in its own
  script (Кириллица, 日本語, Ελληνικά); a ribbon of eleven dots looked like a stub. Chinese titles are left out of that: on a page made in China they are not unusual.
- **The year among the years** shows last year's count beside this year's, and a bracket over the first years
  whose papers together are still fewer than this year's alone ("2012–2022 together: 2,068"). A running-total line
  was tried and taken out: it crossed the bars and labels and said what the opening already says.
- **Text is ragged right.** Justified text, as in a paper, was tried: in a column this narrow it opened uneven
  gaps between words. Paragraphs are set ragged right with `text-wrap: pretty`, which keeps a last word from
  standing alone and evens the right edge.
- **A page for one reader.** Next to "Save name card" a found name can be copied as a link, `?for=Name`. Opened,
  the page greets that person on the cover and puts a breathing gold halo around their dots in every scene, so
  they can follow their own papers through the days, the clusters and the map; the list of names stops on
  their name. Names are matched as the search matches them (case and accents aside).
- **The ring can be dialled.** Inside the ring the pointer reads dots, as in every other scene. The dial is a
  single hand, resting on 1 January with a knob just outside the rays (a drawn track looked heavy): pointing at it previews a day; holding
  and turning it moves the hand, and each day rings its notes (the day's most cited papers, as Listen plays
  them). Let go during Listen and the year plays on from there. On a phone a touch on the rim turns the dial
  instead of scrolling.
- **Tools sit by the picture.** Listen is a small player under the ring (play/pause and ½×, 1×, 2×), and every
  scene has a small round save icon at the picture's lower right, in place of text buttons under the prose. On
  a phone the player sits at the picture's top right and saving stays in the top bar. The final card keeps its
  own buttons.
- **A paper is not a reader.** The ring names the year's first citing paper (2 January, Can Tho); the readers
  scene names the first new reader, the first author who had never cited before (2 January, Jinan). The Can Tho
  paper has an author who had cited before, so the two differ.
- **A name is only a name.** Search results list names without a city or day: namesakes share a line, so one
  place and day would describe only one of them.
- **Places in the reader's language.** City names come in Chinese from a hand-made list,
  `code/city_names_zh.json`, which covers the cities named in the text and those most often cited from (about
  85% of the sample's dots); others stay in English. In Chinese the country comes first (越南芹苴).
- **New cities on the globe turned to home.** The scene of new cities is the world as on the Reach page: an
  azimuthal equidistant disc with home in the middle, north up, the rim the far side of the earth, the radius
  growing with the square root of the distance (rings at 500, 2,000, 5,000, 10,000 and 15,000 km). The land is
  drawn in the same projection, the new cities are lit, and the places reached before stay faint where they are,
  so the world map seems to turn round home. A first try without land, dots only, read as a chart rather than
  the world.
- **Conference labels on two lines.** On the route, the meeting ("4  ACL") is one line and the city ("San Diego
  ×2") the next.
- **Fog.** On the map, fog covers everything no reader has been placed in, up to and including this year.
  Each city reached opens a hole of fixed size, so one paper does not clear a country. New places are lit
  in the next scene, and each new country or region gets a stamp: its outline, the day, and the paper that
  got there first.
- **What the readers were working on.** The two- and three-word phrases that recur in the titles of the
  year's citing papers, singular and plural merged, spellings of one word merged from a short list
  ("recommender system" and "recommendation system" are one phrase, shown the way most titles write it), generic words left out, the longer phrase kept when it
  covers most uses of the shorter one. A phrase whose share of titles is at least twice its share in earlier
  years is marked; for the sample data, "generative recommendation" in 2026 (about ten times).
- **Distance, added up.** From home to the nearest author of each citing paper, summed over the year and
  given in turns around the Earth. It is a measure of spread, not of travel, and the text says how it is
  measured.
- **A card at the end.** The last scene is a 1080 × 1350 card with few parts. A masthead with the author,
  home city and year. A heading that is the page's own sentence, "The authors may never have been to most
  of these places. The papers have.", the second sentence on a line of its own in the accent, the colour of
  the journeys under it. A map of land alone, with no sea, frame or legend, that runs past the text margins:
  a line in the accent from home to each country reached for the first time, a dashed line to the farthest
  city, which is named on the map with its distance. The owner's own year is on the map too: a black diamond
  for each meeting where the year's papers were presented, named with its city and short date, and a ring
  for the year's first citation. Each label sits level with its mark, on the side away from home; only a
  label that would crowd another label or mark, cover a line or leave the map moves, first a little up or
  down beside its mark, then above or below it. Five figures without rules between them, from the
  owner outwards: new papers, citations, readers, cities, countries and regions. One line with an accent dot that
  says what the accent means and counts the first arrivals, and under it the stamps, the same ones as in
  the stamps scene with their postmarks, in rows from the left on six columns (four when there are at most
  four; up to eighteen in three rows, then "+N"), with the arrival city when there are one or two rows. In
  a year without new countries the distance and the recurring title phrases stand there. Last a line of
  thanks to the readers, set as a note by hand: italic, and in Chinese Kaiti. An earlier card had a
  subtitle, a continent legend, sub-lines under each figure and dividers between them, and said several
  things twice; the continents need no legend on a map. On the page the card
  is drawn without its dots and the year's dots fly in to become its map; the saved picture has them
  drawn in. It follows the theme and language in use. Share uses the system share sheet where the browser
  has one, otherwise the picture is saved. "Save PDF" draws the same card as SVG on a page of its size and
  opens the browser's print dialog, so lines, dots and text stay vector and the fonts are embedded; no PDF
  library is needed.
- **A paper is a cluster; the years are bands.** Every cited paper is one cluster of the papers that cited
  it, so eighty-seven papers are eighty-seven things to see and the largest is the most cited. The clusters
  stand in bands by the year the paper was written, and a band is as wide as its clusters need. An earlier
  version stacked the papers in one column a year on an even axis; the layers could not be told apart and
  half the axis was empty, and it did not read at a glance. The one citing paper that cites most of them at
  once is a line from cluster to cluster, oldest first.
- **Stamps carry the country and a view of the city.** A country reached for the first time gets a stamp with
  a perforated edge and a fine frame, the same on the page and on the card: the outline of the country with a dot where the city is, and beside it a small line drawing
  of the city the paper arrived in: a fort, a bridge, a ger below a mountain. The
  drawings are strokes in the ink colour, kept in `code/landmarks.json`; they were drawn by hand,
  compared with photographs where there were any, and are simplified, and the stamp names what it shows. A city with no drawing has the outline alone. Photographs were considered and not used: they would have to be downloaded and credited one
  by one, and a photograph does not sit with a page made of dots and lines.
- **Every scene can be saved.** Each scene has a button (on a narrow screen, one icon in the top bar) that draws it again as a 1080 × 1350 picture with
  its heading, one of its sentences and the same last line as the card, because a reader may care for one
  scene more than for the summary. Pictures are saved at twice that size so that they stay sharp on a
  phone.
- **A few close-ups.** Next to the totals the text names small things that are exact: the longest run of
  days that each brought a citing paper, the oldest paper still cited, the co-authors of the year's new
  papers and how many are new, and in the credits the names that have come back three years running, in
  bold. Co-authors are counted from the Scholar profile's abbreviated names, so the text says "at least"
  when a list is cut short.
- **Colour says one thing.** A dot has the colour of a continent: that of its paper's first listed city, and
  on a map that of the city it sits in, so a map never shows an Asian colour in Europe. The rust accent is
  kept, on dots, for a place reached for the first time. A fainter dot is known only by year. The legend is
  on the cover only, with the counts; the card says what the accent means in one line.
- **The year can be heard.** On the ring, Listen sweeps a hand around the year at two days to a beat,
  about 25 seconds for a full year. It uses Record's notes and bell, so a paper sounds the same on both
  pages: the most cited paper is the low D. Days already heard stay lit. Nothing is created before the
  button is pressed, and leaving the scene stops it.
- **Credits.** Before the card, the names of every author of the year's citing papers outside the owner's
  circle roll by, in the order they first appeared, as film credits do. For the sample data that is 13,062
  names; nobody reads them all, and that is the point. The names are public bylines as OpenAlex spells them. A
  name appears once: namesakes, and one person OpenAlex has split into two ids, share a line.
  A search box finds a name (accents may be left out); the found name, or one under the pointer, holds the
  list, and the dots of that person's papers light up with a line to each. A found name can be saved as its
  own card: the name, where and when their papers came from, what they cited, and their places on a map of
  the year. Someone sent the page looks for their own name first; the card gives them a reason to pass it on.
- **A few desks out of the usual.** The map scene says how many papers came from hospitals and from
  archives and libraries (OpenAlex institution types `healthcare` and `archive`), and the topics scene how
  many titles are written in another script (counted by Unicode block; a title in Spanish or Portuguese
  cannot be told apart, so only scripts are named).
- **The card is an invitation.** Its last line gives the address of the page when it is served from the
  public web, and otherwise where the tool is, so that someone who is sent the picture can see the page or
  make their own.
- **One year.** The page looks back on the latest year only, chosen in the build; in January and February
  that is the year just ended. A switch between years was built and removed: it made the page an archive,
  and a look back is about now.
- **No comparisons with other people and no declines.** A year in progress is incomplete, so the text only
  says that something rose when it already has; it never says that something fell.
- **It works for a small year.** Dot size follows the count, so twelve citations fill the screen as
  completely as three thousand.
- Text is in English and Chinese, chosen from the browser and switchable. Place and institution names stay
  as the sources give them.

**Dropped.** A day-and-night line sweeping the map: the data has dates, not hours, so it would show something
nobody measured. Sentences about holidays and conference weeks: the page does not know where the owner was.
A line for the owner's own sentence about the year (it belongs to the owner, not the data, and
can come later). A yearly centre of gravity of the citations: for the sample data it stayed within 1,600 km
of home for seven years. Drawing arrival times as rings on Reach: in the sample data a city's distance from
home says nothing about when it first cites (rank correlation −0.06).

## Tried and dropped

- **Other views.** A word stream of the phrases in citing papers' titles; terrain, loom and ring artworks;
  a particle long read; a three-dimensional reef of citations among the citing papers; and a shelf of the
  books each year's readers cite alongside. They were dropped or folded into the eight. The artworks were
  designed on invented, evenly spread data; the real record is usually dominated by one paper and one
  continent, which left them half empty or one colour. The particle idea lives on in Story.
- **Ideas that did not fit the data.** Several generations of citation ripples (in a dense field, everything
  is reached in two steps); a "domain escape" view (OpenAlex gives no reliable field for most citing works);
  a 24-hour relay by longitude (longitude says nothing about when a paper was read).
- **Measures not built.** The Sleeping Beauty coefficient, the disruption (CD) index and the
  Wang–Song–Barabási citation model were discussed and left for later.
