# Design notes

**English** | [简体中文](DESIGN.zh-CN.md)

Why the eight pages look and behave as they do. The [README](README.md) says what each view shows; this
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

The tool is not about one person. Nothing in `code/` names a person, a paper or a place; the owner, home city
and titles all come from the data.

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
motion each page shows its end state.

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
  paper behind each new light, so every light can be traced to a real paper.
- Playback takes about nine seconds of wall-clock time (less for a history under eleven years), whatever
  the frame rate. The page autoplays once,
  unless the reader prefers reduced motion; any press of play or pause takes over.
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
