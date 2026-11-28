// Renders the README wordmark to docs/wordmark-{light,dark}.png (transparent, 2x): node wordmark.mjs
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { mkdirSync } from 'node:fs';
import { launch } from './lib.mjs';

const docs = join(dirname(fileURLToPath(import.meta.url)), '..', 'docs');
const W = 620, H = 170;
mkdirSync(docs, { recursive: true });
for (const [theme, ink, accent] of [['light', '#1d1b17', '#b5560f'], ['dark', '#ece5d6', '#f08a5d']]) {
  const page = await launch({ width: W, height: H, scale: 2 });
  try {
    await page.send('Emulation.setDefaultBackgroundColorOverride', { color: { r: 0, g: 0, b: 0, a: 0 } });
    const html = `<body style="margin:0;height:${H}px;display:flex;align-items:center;justify-content:center;color:${ink};` +
      `font:400 132px/1 'Iowan Old Style','New York',Palatino,Georgia,serif;letter-spacing:-.02em">Cite<span style="color:${accent}">Story</span>`;
    await page.goto('data:text/html,' + encodeURIComponent(html));
    await page.shot(join(docs, `wordmark-${theme}.png`));
  } finally { await page.close(); }
}
