# Promo video

Scripts that film the built pages of one profile and cut them into the README video. Each page runs in
headless Chrome on a virtual clock that moves one frame per screenshot, so the recording is frame-exact on any machine.

## Needs

- Node 22 or later (for its built-in WebSocket); no npm packages.
- Chrome or Chromium. The usual install is found on macOS, Windows and Linux; otherwise set `CHROME_PATH`.
- `ffmpeg` and `ffprobe` on `PATH`.
- A built site: `python3 code/citestory.py build profiles/<name>`.
- Network access while recording Atlas, for its map tiles.

## Run

From this folder:

```bash
CITESTORY_PROFILE=profiles/<name> node record.mjs            # every scene into out/clips/
CITESTORY_PROFILE=profiles/<name> node record.mjs race flow  # only these scenes
STILLS=30 CITESTORY_PROFILE=profiles/<name> node record.mjs atlas   # every 30th frame into out/stills/, no video
node compose.mjs                                             # out/citestory-promo.mp4 from the clips
node wordmark.mjs                                            # docs/wordmark-{light,dark}.png
```

`CITESTORY_PROFILE` is relative to the repository root, or absolute. The end card shows `CITESTORY_REPO`
(e.g. `github.com/you/CiteStory`), else this checkout's GitHub remote, else no address. Other people's names
are blurred in the Regulars and Record shots. Everything is written to `out/`, which git ignores.
