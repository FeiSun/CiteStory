import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join, resolve } from 'node:path';
import { existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
// Views are laid out at 1280x720 and rendered at 1.3x (1664x936), then framed on a 1920x1080 stage with a caption strip below.
export const W = 1280, H = 720, SCALE = 1.3;
export const OUT = join(here, 'out');
export const STAGE = pathToFileURL(join(here, 'stage.html')).href;

// The built site of the profile to film: CITESTORY_PROFILE=profiles/<name> (relative to the repository root, or absolute).
export function site(file) {
  const profile = process.env.CITESTORY_PROFILE;
  if (!profile) throw new Error('Set CITESTORY_PROFILE to the profile folder to film, e.g. CITESTORY_PROFILE=profiles/me node record.mjs');
  const dir = resolve(here, '..', profile, 'site');
  if (!existsSync(join(dir, 'index.html'))) throw new Error(`${dir} has no built site; run: python3 code/citestory.py build ${profile}`);
  return pathToFileURL(join(dir, file)).href;
}

// The address shown on the end card: CITESTORY_REPO, else the GitHub remote of this checkout, else none.
export const REPO = process.env.CITESTORY_REPO ?? (() => {
  try {
    const url = execFileSync('git', ['-C', here, 'remote', 'get-url', 'origin'], { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
    const m = url.match(/github\.com[:/]([\w.-]+\/[\w.-]+?)(?:\.git)?$/);
    return m ? 'github.com/' + m[1] : '';
  } catch (e) { return ''; }
})();
