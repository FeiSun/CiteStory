// Frame-exact page recorder: headless Chrome over CDP, with the page's clock replaced
// by a virtual one that advances exactly one frame per screenshot.
// No dependencies: Node's built-in WebSocket, the installed Chrome, and ffmpeg.
import { spawn } from 'node:child_process';
import { mkdtempSync, readFileSync, existsSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
export const FPS = 60;
export const sleep = ms => new Promise(r => setTimeout(r, ms));

// Runs in the page before any of its scripts. Time only moves when __vt.step() is called.
const VIRTUAL_CLOCK = `(() => {
  if (window.__vt) return;
  let now = 0, id = 0;
  const origin = Date.now();
  const rafs = new Map(), timers = new Map(), anims = new Map(), done = new WeakSet();
  const RealDate = Date;
  performance.now = () => now;
  class VDate extends RealDate {
    constructor(...a) { if (a.length) super(...a); else super(origin + now); }
    static now() { return origin + now; }
  }
  window.Date = VDate;
  window.requestAnimationFrame = cb => { rafs.set(++id, cb); return id; };
  window.cancelAnimationFrame = i => { rafs.delete(i); };
  const add = (cb, ms, every, args) => {
    if (typeof cb !== 'function') return 0;
    timers.set(++id, { cb, at: now + Math.max(0, +ms || 0), every, args });
    return id;
  };
  window.setTimeout = (cb, ms, ...a) => add(cb, ms, 0, a);
  window.setInterval = (cb, ms, ...a) => add(cb, ms, Math.max(1, +ms || 0), a);
  window.clearTimeout = window.clearInterval = i => { timers.delete(i); };
  const run = (f, ...a) => { try { f(...a); } catch (e) { console.error(e); } };
  window.__vt = {
    get now() { return now; },
    step(dt) {
      const end = now + dt;
      for (let guard = 0; guard < 1000; guard++) {
        let next = null, nid = 0;
        for (const [i, t] of timers) if (t.at <= end && (!next || t.at < next.at)) { next = t; nid = i; }
        if (!next) break;
        now = Math.max(now, next.at);
        if (next.every) next.at += next.every; else timers.delete(nid);
        run(next.cb, ...next.args);
      }
      now = end;
      const due = [...rafs.values()]; rafs.clear();
      for (const cb of due) run(cb, now);
      // CSS transitions and animations follow the virtual clock too.
      for (const a of document.getAnimations()) {
        if (done.has(a)) continue;   // a finished animation with a fill stays listed; do not restart it
        if (!anims.has(a)) { anims.set(a, now); try { a.pause(); } catch (e) {} }
        const t = now - anims.get(a);
        const total = a.effect ? a.effect.getComputedTiming().endTime : 0;
        try { if (Number.isFinite(total) && t >= total) { a.finish(); anims.delete(a); done.add(a); } else a.currentTime = t; } catch (e) {}
      }
    }
  };
})();`;

export async function launch({ width, height, scale = 1 }) {
  const profile = mkdtempSync(join(tmpdir(), 'citestory-promo-'));
  const proc = spawn(CHROME, [
    '--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`,
    `--window-size=${width},${height}`, '--hide-scrollbars', '--mute-audio',
    '--no-first-run', '--no-default-browser-check', '--disable-extensions',
    '--autoplay-policy=no-user-gesture-required', '--allow-file-access-from-files',
    '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
    'about:blank',
  ], { stdio: 'ignore' });
  const portFile = join(profile, 'DevToolsActivePort');
  for (let i = 0; i < 100 && !existsSync(portFile); i++) await sleep(100);
  const [port, path] = readFileSync(portFile, 'utf8').trim().split('\n');
  const ws = new WebSocket(`ws://127.0.0.1:${port}${path}`);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let seq = 0; const pending = new Map(); const logs = [];
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) {
      const { res, rej } = pending.get(m.id); pending.delete(m.id);
      m.error ? rej(new Error(m.error.message)) : res(m.result);
    } else if (m.method === 'Runtime.exceptionThrown') logs.push('EXC ' + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
    else if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') logs.push('ERR ' + m.params.args.map(a => a.value ?? a.description).join(' '));
  };
  let sessionId;
  const send = (method, params = {}, sid = sessionId) => new Promise((res, rej) => {
    const id = ++seq; pending.set(id, { res, rej });
    ws.send(JSON.stringify({ id, method, params, sessionId: sid }));
  });
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' }, undefined);
  ({ sessionId } = await send('Target.attachToTarget', { targetId, flatten: true }, undefined));
  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: scale, mobile: false });
  await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: 'light' }, { name: 'prefers-reduced-motion', value: 'no-preference' }] });
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `try{localStorage.setItem('theme','light')}catch(e){}` + VIRTUAL_CLOCK });

  const page = {
    logs, send,
    async eval(expr) {
      const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
      return r.result.value;
    },
    async goto(url) { await send('Page.navigate', { url }); await sleep(300); },
    step(ms = 1000 / FPS) { return page.eval(`__vt.step(${ms})`); },
    // Let virtual time run freely (not recorded) for `ms`, yielding so network and workers progress.
    async run(ms, { until } = {}) {
      for (let t = 0; t < ms; t += 1000 / FPS) {
        await page.step(); await sleep(2);
        if (until && await page.eval(until)) return true;
      }
      return !until;
    },
    async png() { return Buffer.from((await send('Page.captureScreenshot', { format: 'png' })).data, 'base64'); },
    async shot(file) { writeFileSync(file, await page.png()); },
    async close() {
      try { await send('Browser.close', {}, undefined); } catch (e) {}
      proc.kill(); await sleep(300); rmSync(profile, { recursive: true, force: true });
    },
  };
  return page;
}

// Pipes PNG frames into ffmpeg and writes a near-lossless intermediate clip.
export function encoder(file) {
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'png', '-i', '-',
    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '6', '-pix_fmt', 'yuv444p', file], { stdio: ['pipe', 'inherit', 'inherit'] });
  return {
    write: buf => new Promise(res => ff.stdin.write(buf) ? res() : ff.stdin.once('drain', res)),
    end: () => new Promise(res => { ff.on('close', res); ff.stdin.end(); }),
  };
}
