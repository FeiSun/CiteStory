// Frame-exact page recorder: headless Chrome over CDP, with the page's clock replaced
// by a virtual one that advances exactly one frame per screenshot.
// No dependencies: Node's built-in WebSocket (Node 22+), an installed Chrome or Chromium, and ffmpeg.
import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, existsSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

export const FPS = 60;
export const sleep = ms => new Promise(r => setTimeout(r, ms));

if (typeof WebSocket !== 'function') throw new Error(`Node 22 or later is needed (this is ${process.version}): the recorder uses Node's built-in WebSocket.`);

// CHROME_PATH, else the usual install on this platform
function chromePath() {
  if (process.env.CHROME_PATH) return process.env.CHROME_PATH;
  const known = {
    darwin: ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Chromium.app/Contents/MacOS/Chromium'],
    win32: [join(process.env.PROGRAMFILES || 'C:\\Program Files', 'Google', 'Chrome', 'Application', 'chrome.exe'),
            join(process.env['PROGRAMFILES(X86)'] || 'C:\\Program Files (x86)', 'Google', 'Chrome', 'Application', 'chrome.exe')],
  }[process.platform];
  if (known) { const found = known.find(existsSync); if (found) return found; }
  for (const name of ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser']) if (!spawnSync(name, ['--version']).error) return name;
  throw new Error('Chrome was not found; set CHROME_PATH to the Chrome or Chromium executable.');
}

// ffmpeg and ffprobe must be on PATH
export function requireTool(name) {
  if (spawnSync(name, ['-version'], { stdio: 'ignore' }).error) throw new Error(`${name} was not found on PATH; install ffmpeg (it includes ffprobe).`);
}

// Runs in the page before any of its scripts. Time only moves when __vt.step() is called.
const VIRTUAL_CLOCK = `(() => {
  if (window.__vt) return;
  let now = 0, id = 0;
  const origin = Date.now();
  const rafs = new Map(), timers = new Map(), anims = new WeakMap(), done = new WeakSet();
  const RealDate = Date;
  performance.now = () => now;
  // Date() without new returns a string, as the real one does
  function VDate(...a) {
    if (!new.target) return new RealDate(origin + now).toString();
    return a.length ? new RealDate(...a) : new RealDate(origin + now);
  }
  VDate.prototype = RealDate.prototype; VDate.parse = RealDate.parse; VDate.UTC = RealDate.UTC;
  VDate.now = () => origin + now;
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
  const chrome = chromePath();
  const profile = mkdtempSync(join(tmpdir(), 'citestory-promo-'));
  const proc = spawn(chrome, [
    '--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`,
    `--window-size=${width},${height}`, '--hide-scrollbars', '--mute-audio',
    '--no-first-run', '--no-default-browser-check', '--disable-extensions',
    '--autoplay-policy=no-user-gesture-required', '--allow-file-access-from-files',
    '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
    'about:blank',
  ], { stdio: 'ignore' });
  let spawnError = null;
  proc.on('error', e => { spawnError = e; });
  const exited = new Promise(res => proc.once('exit', res));
  async function kill() {                      // stop Chrome and remove its throwaway profile
    if (proc.exitCode === null && proc.signalCode === null) { proc.kill(); await Promise.race([exited, sleep(3000)]); }
    rmSync(profile, { recursive: true, force: true });
  }
  let ws;
  try {
    const portFile = join(profile, 'DevToolsActivePort');
    for (let i = 0; i < 100 && !existsSync(portFile) && !spawnError && proc.exitCode === null; i++) await sleep(100);
    if (spawnError) throw new Error(`Chrome could not be started (${chrome}): ${spawnError.message}`);
    if (!existsSync(portFile)) throw new Error(`Chrome (${chrome}) did not open its debugging port within 10 s.`);
    const [port, path] = readFileSync(portFile, 'utf8').trim().split('\n');
    ws = new WebSocket(`ws://127.0.0.1:${port}${path}`);
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error('Could not connect to Chrome.')); });
  } catch (e) { await kill(); throw e; }
  let seq = 0; const pending = new Map(); const logs = []; const waiters = new Map();
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) {
      const { res, rej } = pending.get(m.id); pending.delete(m.id);
      m.error ? rej(new Error(m.error.message)) : res(m.result);
    } else if (waiters.has(m.method)) { const w = waiters.get(m.method); waiters.delete(m.method); w(m.params); }
    else if (m.method === 'Runtime.exceptionThrown') logs.push('EXC ' + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
    else if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') logs.push('ERR ' + m.params.args.map(a => a.value ?? a.description).join(' '));
  };
  ws.onclose = () => { for (const { rej } of pending.values()) rej(new Error('Chrome closed the connection.')); pending.clear(); };
  let sessionId;
  const send = (method, params = {}, sid = sessionId) => new Promise((res, rej) => {
    const id = ++seq; pending.set(id, { res, rej });
    ws.send(JSON.stringify({ id, method, params, sessionId: sid }));
  });
  // the next event of this kind, or an error after `ms`
  const next = (method, ms) => new Promise((res, rej) => {
    const t = setTimeout(() => { waiters.delete(method); rej(new Error(`${method} did not arrive within ${ms / 1000} s`)); }, ms);
    waiters.set(method, p => { clearTimeout(t); res(p); });
  });
  try {
    const { targetId } = await send('Target.createTarget', { url: 'about:blank' }, undefined);
    ({ sessionId } = await send('Target.attachToTarget', { targetId, flatten: true }, undefined));
    await send('Page.enable'); await send('Runtime.enable');
    await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: scale, mobile: false });
    await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: 'light' }, { name: 'prefers-reduced-motion', value: 'no-preference' }] });
    await send('Page.addScriptToEvaluateOnNewDocument', { source: `try{localStorage.setItem('theme','light')}catch(e){}` + VIRTUAL_CLOCK });
  } catch (e) { ws.close(); await kill(); throw e; }

  const page = {
    logs, send,
    async eval(expr) {
      const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
      return r.result.value;
    },
    async goto(url) {                          // resolves once the page and its scripts (data.js) have loaded
      const loaded = next('Page.loadEventFired', 60000);
      const r = await send('Page.navigate', { url });
      if (r.errorText) { loaded.catch(() => {}); throw new Error(`Could not open ${url}: ${r.errorText}`); }
      await loaded;
    },
    step(ms = 1000 / FPS) { return page.eval(`__vt.step(${ms})`); },
    // Let virtual time run freely (not recorded) for `ms`, yielding so network and workers progress.
    // With `until`, returns whether that page expression became true in time.
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
      try { await Promise.race([send('Browser.close', {}, undefined), sleep(2000)]); } catch (e) {}
      ws.close(); await kill();
    },
  };
  return page;
}

// Pipes PNG frames into ffmpeg and writes a near-lossless intermediate clip. write() and end() reject when ffmpeg fails.
export function encoder(file) {
  requireTool('ffmpeg');
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'png', '-i', '-',
    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '6', '-pix_fmt', 'yuv444p', file], { stdio: ['pipe', 'inherit', 'inherit'] });
  let failure = null;
  const fail = e => { failure = failure || e; };
  ff.on('error', fail);
  ff.stdin.on('error', fail);               // EPIPE when ffmpeg has stopped reading
  const closed = new Promise(res => ff.on('close', (code, signal) => {
    if (code !== 0) fail(new Error(`ffmpeg exited with ${code ?? signal} while writing ${file}`));
    res();
  }));
  const stopped = () => closed.then(() => { throw failure || new Error('ffmpeg stopped early'); });
  return {
    write: buf => failure ? Promise.reject(failure)
      : ff.stdin.write(buf) ? Promise.resolve() : Promise.race([new Promise(res => ff.stdin.once('drain', res)), stopped()]),
    end: async () => { ff.stdin.end(); await closed; if (failure) throw failure; },
  };
}
