---
layout: page
title: Citation geography
description: Where my papers are read, city by city
importance: 1
category: work
---

Every paper that cites my work, placed at the cities of its authors' institutions. Press play to watch
the citations spread from the first one to today, switch between the globe and the map, search a city or an
institution, or pick a paper to see how far it travelled. Data from Google Scholar and OpenAlex.

<iframe class="citation-geo" src="{{ '/assets/citation-geography/atlas.html?embed' | relative_url }}"
        title="Citation Atlas: an interactive map of the cities that cite my papers"
        loading="lazy" style="width:100%; height:640px; border:0; display:block; margin:1.5rem 0;"></iframe>

The same data, seen differently:

- [Reach]({{ '/assets/citation-geography/reach.html' | relative_url }}): the world measured from my institution, every city at its true distance and bearing.
- [Story]({{ '/assets/citation-geography/story.html' | relative_url }}): an illustrated long read: the first citations, the breakout papers, and the spread across continents.
- [Flow]({{ '/assets/citation-geography/flow.html' | relative_url }}): ribbons from each paper to the countries that cite it.

<script>
  // The embedded page reports its height; size the iframe to it (same-origin messages only).
  window.addEventListener("message", function (e) {
    if (e.origin !== window.location.origin || !e.data || e.data.type !== "citation-geo-height") return;
    document.querySelectorAll("iframe.citation-geo").forEach(function (f) {
      if (f.contentWindow === e.source) f.style.height = Math.max(320, Math.min(4000, e.data.height | 0)) + "px";
    });
  });
</script>
