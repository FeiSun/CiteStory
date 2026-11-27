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
