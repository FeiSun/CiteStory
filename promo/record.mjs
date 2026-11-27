// Records scenes to out/clips/<name>.mp4.
//   node record.mjs [scene ...]        record the named scenes (default: all)
//   STILLS=30 node record.mjs atlas    save every 30th frame to out/stills instead of encoding
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { launch, encoder, sleep, FPS } from './lib.mjs';
import { W, H, OUT } from './config.mjs';
import { scenes } from './scenes.mjs';

const STILLS = +process.env.STILLS || 0;
mkdirSync(join(OUT, 'clips'), { recursive: true });
mkdirSync(join(OUT, 'stills'), { recursive: true });

const names = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(scenes);
for (const name of names) {
  const scene = scenes[name];
  if (!scene) throw new Error('unknown scene ' + name);
  const t0 = Date.now();
  const page = await launch({ width: scene.width || W, height: scene.height || H, scale: scene.scale });
  const enc = STILLS ? null : encoder(join(OUT, 'clips', name + '.mp4'));
  let n = 0;
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
        if (settle) for (let k = 0; k < 150 && !(await page.eval(settle)); k++) await sleep(20);
        if (enc) await enc.write(await page.png());
        else if (n % STILLS === 0) await page.shot(join(OUT, 'stills', `${name}-${String(n).padStart(4, '0')}.png`));
        n++;
        if (until && await page.eval(until)) break;
      }
    },
  };
  try { await scene.run(page, rec); }
  finally {
    if (enc) await enc.end();
    if (page.logs.length) console.log([...new Set(page.logs)].slice(0, 8).join('\n'));
    await page.close();
  }
  console.log(`${name}: ${n} frames (${(n / FPS).toFixed(2)}s) in ${((Date.now() - t0) / 1000).toFixed(0)}s`);
}
