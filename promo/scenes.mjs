// One entry per shot. Each drives a real page of the generated site; nothing is mocked.
// Playback lengths (20, 26 s; Reach's 1.15 years a second) and Flow's 0.62 s tween mirror the values in the templates;
// Atlas is driven through its page globals (map, projBusy, S, TEND). Change them together.
import { site, SCALE, STAGE, REPO } from './config.mjs';

// Running order, with the caption shown under each view.
export const SHOTS = [
  ['atlas', 'Atlas', 'Where in the world'],
  ['reach', 'Reach', 'How far it travelled'],
  ['story', 'Story', 'How it spread'],
  ['flow', 'Flow', 'From papers to places'],
  ['constellation', 'Constellation', 'Papers and their neighbours'],
  ['race', 'Race', 'Who led, and when'],
  ['regulars', 'Regulars', 'Who keeps coming back'],
  ['record', 'Record', 'One turn for every year'],
];

const view = (file, run) => ({ scale: SCALE, run: async (page, rec) => { await page.goto(site(file)); await page.run(1500); await run(page, rec); } });
const click = id => `document.getElementById(${JSON.stringify(id)}).click()`;
// Other people's names are blurred in the video: it travels further than the site does.
const blur = sel => `document.head.appendChild(Object.assign(document.createElement('style'), { textContent: ${JSON.stringify(sel + '{filter:blur(7px)}')} }))`;
const ease = t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

// Play a page's replay (lasting `full` seconds at 1x, or as long as a page expression says) within `secs` of video,
// then hold on the finished picture. `lead` > 0 runs the sparse early years faster than the busy late ones.
const replay = (file, full, secs, hold = 0.7, lead = 0) => view(file, async (page, rec) => {
  if (typeof full === 'string') full = await page.eval(full);
  await page.eval(click('playBtn')); await page.run(40);
  await rec.capture(secs, { speed: u => (full + 0.3) / secs * (1 + lead - 2 * lead * u) });
  await rec.capture(hold);
});

const card = (mode, secs) => ({ width: 1920, height: 1080, scale: 1, run: async (page, rec) => {
  await page.goto(STAGE + '?mode=' + mode + '&repo=' + encodeURIComponent(REPO)); await rec.capture(secs);
} });

export const scenes = {
  intro: card('intro', 2.4),
  outro: card('outro', 4.2),
  // The page's own opening: the globe turns in, unfolds into the flat map, and the replay runs.
  atlas: { scale: SCALE, run: async (page, rec) => {
    await page.goto(site('atlas.html'));
    if (!await page.run(30000, { until: `(() => { try { return map.loaded(); } catch (e) { return false; } })()` }))
      throw new Error('atlas: the map did not load within 30 s of virtual time (no network, or the tile server is down)');
    const settle = `map.areTilesLoaded()`;
    await rec.capture(1.6, { settle });                                         // the globe turns in
    // MapLibre draws a single world while the projection changes, which leaves part of the wide view empty: pass through it quickly
    await rec.capture(2, { settle, speed: 3, until: `!projBusy` });
    await rec.capture(8, { settle, speed: 1.6, until: `S.t >= TEND` });         // the replay
    await rec.capture(0.6, { settle });
  } },

  // Reach plays 1.15 years a second, slower for a short record so it lasts at least 9 s: its length follows the data
  reach: replay('reach.html', `(() => { const s = document.getElementById('year'), span = s.max - s.min;
    return span / Math.min(1.15, Math.max(0.2, span / 9)); })()`, 4.2, 0.6, 0.5),

  // Scroll the essay: the dots leave the map for year columns, continent bands, city clusters and institution rows.
  story: view('story.html', async (page, rec) => {
    const tops = await page.eval(`[...document.querySelectorAll('.step')].map(s => { const r = s.getBoundingClientRect(); return r.top + scrollY + r.height / 2 - innerHeight / 2; })`);
    const stops = [0, 3, 7, 9, 10].filter(k => k < tops.length).map(k => tops[k]);     // steps of the essay whose picture changes; an essay with fewer steps uses those it has
    const dwell = 1.1, travel = 0.7, total = stops.length * dwell + (stops.length - 1) * travel + 0.6;   // a longer last hold
    await page.eval(`scrollTo(0, ${stops[0]})`); await page.run(3000);
    await rec.capture(total, { speed: 1.5, each: (i, u) => {
      let t = u * total, k = 0;
      while (k < stops.length - 1 && t > dwell + travel) { t -= dwell + travel; k++; }
      const f = k < stops.length - 1 ? ease(Math.max(0, Math.min(1, (t - dwell) / travel))) : 0;
      return `scrollTo(0, ${stops[k] + (stops[Math.min(k + 1, stops.length - 1)] - stops[k]) * f})`;
    } });
  }),

  // Open the year range from the early years to all of them; the page's own 0.62 s tween is slowed to fill the shot.
  flow: view('flow.html', async (page, rec) => {
    const [y0, y1] = await page.eval(`[+document.getElementById('y1').min, +document.getElementById('y1').max]`);
    const setYear = y => `(() => { const e = document.getElementById('y1'); e.value = ${y}; e.dispatchEvent(new Event('input', { bubbles: true })); })()`;
    await page.eval(`scrollTo(0, document.getElementById('chart').getBoundingClientRect().top + scrollY - 104)`);
    await page.eval(setYear(Math.min(y1 - 1, Math.max(y0, Math.round((y0 + y1) / 2))))); await page.run(1500);   // from mid-career, so a short record still moves
    await rec.capture(0.5);
    await page.eval(setYear(y1));
    await rec.capture(2.7, { speed: 0.62 / 2.7 });
    await rec.capture(0.6);
  }),

  constellation: replay('constellation.html', 20, 4.2),
  race: replay('race.html', 26, 4.4, 0.7, 0.6),

  // The chart is static on the page; the video reveals it along its time axis.
  regulars: view('regulars.html', async (page, rec) => {
    await page.eval(blur('#chart text.name')); await page.run(100);
    await rec.capture(3.4, { each: (i, u) => `document.getElementById('chart').style.clipPath = 'inset(0 ${(60 * (1 - ease(Math.min(1, u * 1.12)))).toFixed(3)}% 0 0)'` });
  }),

  record: view('record.html', async (page, rec) => {
    await page.eval(blur('#nBy'));
    // start in the busy outer grooves: 70% of the way through the record's time
    await page.eval(`(() => { const e = document.getElementById('time'); e.value = +e.min + 0.7 * (e.max - e.min); e.dispatchEvent(new Event('input', { bubbles: true })); })()`);
    await page.run(200);
    await page.eval(click('playBtn'));
    await page.run(40);
    await rec.capture(4.8, { speed: 1.3 });
  }),
};
