// Frames each view on the stage, then joins everything with crossfades: node compose.mjs [out.mp4]
import { execFileSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { launch, FPS } from './lib.mjs';
import { OUT, STAGE } from './config.mjs';
import { SHOTS } from './scenes.mjs';
import { writeMusic } from './music.mjs';

const PUSH = 0.7, BG = '0xe6dfd2', WIN = { x: 128, y: 40 };
const out = process.argv[2] || join(OUT, 'citestory-promo.mp4');
const clip = n => join(OUT, 'clips', n + '.mp4');
const frame = n => join(OUT, 'frames', n + '.png');
const seconds = f => +execFileSync('ffprobe', ['-v', 'error', '-count_packets', '-select_streams', 'v:0', '-show_entries', 'stream=nb_read_packets', '-of', 'csv=p=0', f]).toString().trim() / FPS;

// 1. caption frames, with a transparent window for the view
mkdirSync(join(OUT, 'frames'), { recursive: true });
const page = await launch({ width: 1920, height: 1080, scale: 1 });
await page.send('Emulation.setDefaultBackgroundColorOverride', { color: { r: 0, g: 0, b: 0, a: 0 } });
for (const [i, [id, name, tag]] of SHOTS.entries()) {
  await page.goto(`${STAGE}?mode=frame&name=${encodeURIComponent(name)}&tag=${encodeURIComponent(tag)}&i=${i}&n=${SHOTS.length}`);
  await page.shot(frame(id));
}
await page.close();

// 2. one filter graph: each shot pushes the one before it off to the left
const parts = ['intro', ...SHOTS.map(s => s[0]), 'outro'];
const args = ['-y', '-loglevel', 'error'];
const filters = []; const ins = []; let at = 0, total = 0;
parts.forEach((p, k) => {
  const d = seconds(clip(p)), framed = k > 0 && k < parts.length - 1;
  args.push('-i', clip(p));
  let src = `[${k}:v]`;
  if (framed) {
    filters.push(`${src}pad=1920:1080:${WIN.x}:${WIN.y}:color=${BG}[p${k}]`, `movie='${frame(p).replace(/'/g, "\\'")}'[f${k}]`, `[p${k}][f${k}]overlay[c${k}]`);
    src = `[c${k}]`;
  }
  filters.push(`${src}setpts=PTS-STARTPTS+${at.toFixed(4)}/TB[v${k}]`);
  ins.push(at); total = at + d; at = total - PUSH;
});
filters.push(`color=c=${BG}:s=1920x1080:r=${FPS}:d=${total.toFixed(4)}[bg]`);
// smootherstep of the push that starts at time a
const E = a => { const p = `clip((t-${a.toFixed(4)})/${PUSH},0,1)`; return `(${p}*${p}*${p}*(${p}*(${p}*6-15)+10))`; };
let acc = '[bg]';
parts.forEach((p, k) => {
  const x = (k ? `W*(1-${E(ins[k])})` : '0') + (k < parts.length - 1 ? `-W*${E(ins[k + 1])}` : '');
  filters.push(`${acc}[v${k}]overlay=x='${x}':y=0:eof_action=pass[a${k}]`); acc = `[a${k}]`;
});
filters.push(`${acc}format=yuv420p[out]`);
const music = join(OUT, 'music.wav');
writeMusic(music, ins, total);   // chords change with the shots
args.push('-i', music, '-filter_complex', filters.join(';'), '-map', '[out]', '-map', `${parts.length}:a`, '-c:a', 'aac', '-b:a', '192k', '-t', total.toFixed(4), '-r', String(FPS),
  '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-movflags', '+faststart', out);
execFileSync('ffmpeg', args, { stdio: 'inherit' });
console.log(`${out}: ${total.toFixed(2)}s`);
