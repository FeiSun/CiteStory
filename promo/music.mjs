// Writes the soundtrack as a WAV: a soft pad that changes chord with each shot, and a plucked arpeggio over it.
// Synthesised here, so there is nothing to download or license.
import { writeFileSync } from 'node:fs';

const SR = 48000, STEP = 0.3;                                   // eighth notes at 100 bpm
const CHORDS = [[50, 57, 64, 66], [47, 57, 62, 66], [43, 59, 62, 66], [45, 57, 62, 64]];   // D, Bm7, Gmaj7, Asus4
const ACCENT = [1, .5, .7, .5, .85, .5, .7, .55], ORDER = [0, 2, 1, 3, 2, 1, 3, 2];
const hz = m => 440 * 2 ** ((m - 69) / 12);

// cuts: start time of each shot in seconds; total: length of the video
export function writeMusic(file, cuts, total) {
  const n = Math.ceil(total * SR);
  const pad = [new Float32Array(n), new Float32Array(n)], pluck = [new Float32Array(n), new Float32Array(n)];
  // one chord per shot, two for a long shot; the end card resolves to D
  const segs = [];
  cuts.forEach((a, k) => { const b = k + 1 < cuts.length ? cuts[k + 1] : total; segs.push(a); if (b - a > 6 && k < cuts.length - 1) segs.push((a + b) / 2); });
  const chord = k => k === segs.length - 1 ? CHORDS[0] : k === segs.length - 2 ? CHORDS[3] : CHORDS[k % 4];
  const segAt = t => { let k = 0; while (k + 1 < segs.length && segs[k + 1] <= t) k++; return k; };

  const TAU = 2 * Math.PI;
  segs.forEach((t0, k) => {
    const dur = (k + 1 < segs.length ? segs[k + 1] : total) - t0, att = 0.7, rel = 1.1;
    const i0 = Math.floor(t0 * SR), i1 = Math.min(n, Math.ceil((t0 + dur + rel) * SR));
    chord(k).forEach((m, j) => [0, 1].forEach(ch => {
      const w = TAU * hz(m) * (ch ? 1.002 : 0.998) / SR, amp = j ? 0.7 : 1.1;
      for (let i = i0; i < i1; i++) {
        const t = (i - i0) / SR, e = Math.min(1, t / att) * (t > dur ? Math.max(0, 1 - (t - dur) / rel) : 1), p = w * (i - i0);
        pad[ch][i] += amp * e * e * (Math.sin(p) + 0.28 * Math.sin(2 * p) + 0.1 * Math.sin(3 * p));
      }
    }));
  });

  // arpeggio: from the first view to the end card
  const from = cuts[1], to = cuts[cuts.length - 1];
  for (let s = 0, t0 = from; t0 < to; s++, t0 = from + s * STEP) {
    const c = chord(segAt(t0)), notes = [c[1] + 12, c[2] + 12, c[3] + 12, c[1] + 24];
    const w = TAU * hz(notes[ORDER[s % 8]]) / SR, pan = s % 2 ? 0.72 : 0.28;
    const amp = ACCENT[s % 8] * Math.min(1, 0.4 + (t0 - from) / 10) * Math.min(1, (to - t0) / 3 + 0.25);
    const i0 = Math.floor(t0 * SR), i1 = Math.min(n, i0 + SR * 1.6);
    for (let i = i0; i < i1; i++) {
      const t = (i - i0) / SR, v = amp * Math.min(1, t / 0.004) * Math.exp(-t / 0.22) * (Math.sin(w * (i - i0)) + 0.2 * Math.sin(2 * w * (i - i0)));
      pluck[0][i] += v * (1 - pan); pluck[1][i] += v * pan;
    }
  }
  // ping-pong echo on the arpeggio
  const d = Math.round(0.45 * SR);
  for (let i = d; i < n; i++) { pluck[0][i] += 0.36 * pluck[1][i - d]; pluck[1][i] += 0.36 * pluck[0][i - d]; }

  const mix = [0, 1].map(ch => pad[ch].map((v, i) => {
    const t = i / SR;
    return (0.1 * v + 0.3 * pluck[ch][i]) * Math.min(1, t / 0.4) * Math.min(1, (total - t) / 2.2);
  }));
  let peak = 0; for (const b of mix) for (const v of b) peak = Math.max(peak, Math.abs(v));
  const wav = Buffer.alloc(44 + n * 4);
  wav.write('RIFF', 0); wav.writeUInt32LE(36 + n * 4, 4); wav.write('WAVEfmt ', 8); wav.writeUInt32LE(16, 16);
  wav.writeUInt16LE(1, 20); wav.writeUInt16LE(2, 22); wav.writeUInt32LE(SR, 24); wav.writeUInt32LE(SR * 4, 28);
  wav.writeUInt16LE(4, 32); wav.writeUInt16LE(16, 34); wav.write('data', 36); wav.writeUInt32LE(n * 4, 40);
  for (let i = 0; i < n; i++) for (const ch of [0, 1]) wav.writeInt16LE(Math.round(mix[ch][i] / peak * 0.6 * 32767), 44 + i * 4 + ch * 2);
  writeFileSync(file, wav);
}
