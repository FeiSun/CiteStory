// Records scenes to out/clips/<name>.mp4 (see README.md).
//   CITESTORY_PROFILE=profiles/me node record.mjs [scene ...]        record the named scenes (default: all)
//   STILLS=30 CITESTORY_PROFILE=profiles/me node record.mjs atlas    save every 30th frame to out/stills instead of encoding
import { mkdirSync, renameSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { launch, encoder, sleep, FPS } from './lib.mjs';
import { W, H, OUT } from './config.mjs';
import { scenes } from './scenes.mjs';

const STILLS = +process.env.STILLS || 0;
mkdirSync(join(OUT, 'clips'), { recursive: true });
mkdirSync(join(OUT, 'stills'), { recursive: true });

const names = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(scenes);
const unknown = names.filter(n => !scenes[n]);
if (unknown.length) throw new Error(`unknown scene ${unknown.join(', ')}; scenes: ${Object.keys(scenes).join(', ')}`);
for (const name of names) {
  const scene = scenes[name];
  const t0 = Date.now();
  let page = null, enc = null, n = 0;
  const clip = join(OUT, 'clips', name + '.mp4'), partial = join(OUT, 'clips', name + '.partial.mp4');
  const rec = {
    // Capture `seconds` of video. speed: virtual seconds per video second (number or u => number, u in 0..1).
    // each: (i, u) => JS run in the page before the frame. settle: page expression that must be true before the shot.
    // until: page expression; the capture stops early once it is true.
    async capture(seconds, { speed = 1, each, settle, until } = {}) {
      const total = Math.round(seconds * FPS);
      for (let i = 0; i < total; i++) {
        const u = total > 1 ? i / (total - 1) : 1;
        if (each) { const js = each(i, u); if (js) await page.eval(js); }
        await page.step(1000 / FPS * (typeof speed === 'function' ? speed(u) : speed));
        if (settle) {                          // e.g. map tiles: wait up to 3 s, and never record a frame that is not ready
          let ready = false;
          for (let k = 0; k < 150 && !(ready = await page.eval(settle)); k++) await sleep(20);
          if (!ready) throw new Error(`${name}: frame ${n} still not ready after 3 s (${settle})`);
        }
        if (enc) await enc.write(await page.png());
        else if (n % STILLS === 0) await page.shot(join(OUT, 'stills', `${name}-${String(n).padStart(4, '0')}.png`));
        n++;
        if (until && await page.eval(until)) break;
      }
    },
  };
  try {
    page = await launch({ width: scene.width || W, height: scene.height || H, scale: scene.scale });
    enc = STILLS ? null : encoder(partial);     // written beside the clip, which it replaces only when the take succeeds
    await scene.run(page, rec);
    if (enc) { const e = enc; enc = null; await e.end(); renameSync(partial, clip); }
  } catch (err) {
    if (enc) await enc.end().catch(() => {});     // a failed take: close ffmpeg, keep the first error
    enc = null;
    rmSync(partial, { force: true });              // and the last good clip stays
    throw err;
  } finally {
    if (page) {
      if (page.logs.length) console.log([...new Set(page.logs)].slice(0, 8).join('\n'));
      await page.close();
    }
  }
  console.log(`${name}: ${n} frames (${(n / FPS).toFixed(2)}s) in ${((Date.now() - t0) / 1000).toFixed(0)}s`);
}
