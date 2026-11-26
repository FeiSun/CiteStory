# Putting the pages on an al-folio site

1. Copy the built pages into the site repository. The simplest is to set `deploy_to` in
   `profiles/<name>/profile.json` to `<site>/assets/citation-geography`; every `citestory.py update` (or `build`)
   then copies the nine pages and four data files there. By hand:

   ```sh
   mkdir -p <site>/assets/citation-geography
   cp profiles/<name>/site/* <site>/assets/citation-geography/
   ```

   `site/` holds only what the pages need, so copying all of it is right. Commit and push the site as usual.

2. Copy `_projects/citation_geography.md` from this folder into `<site>/_projects/`. It appears on the
   projects page; adjust `importance` and `category` to fit your list.

3. Keep the site's minifiers away from these files. In `<site>/_config.yml`, append the folder to the
   existing `jekyll-minifier` → `exclude` list (keep the entries already there), and to `jekyll-terser`'s
   exclusions if your version has that plugin. For example, if the list was `["robots.txt"]`:

   ```yaml
   jekyll-minifier:
     exclude: ["robots.txt", "assets/citation-geography/*"]
   ```

   Then check locally with `bundle exec jekyll serve` (or the repo's Docker setup) that
   `/projects/citation_geography/` shows the embedded map and that the links open.

## What the pages do on the site

- **Theme**: they read and write the same `localStorage` key as al-folio (`theme`: `light`, `dark` or
  `system`), so switching the site's theme switches the visualizations, and the reverse.
- **Embedded Atlas** (`atlas.html?embed`): the page drops its own theme button and notes, takes the site's
  background (`#fff` / `#1c1c1d`), text and rule colours, and reports its height to the project page,
  which resizes the iframe. Typography stays the visualizations' own serif. In the embed, the map zooms
  with Ctrl/⌘ + scroll so the page itself still scrolls.
- **Full pages** keep their own layout; each links back to `index.html`.

## Notes

- Data comes in two files: `data.js` (about 630 KB gzipped) draws the pages, and `data-details.js` (about
  1.1 MB gzipped: paper titles, DOIs, authors) loads in the background after the page appears. GitHub Pages
  gzips both automatically. `index.html` loads neither.
- The live-map page loads MapLibre GL JS 5.24.0 from unpkg (pinned with an integrity hash) and requests
  tiles from OpenFreeMap, which is free and needs no key.
