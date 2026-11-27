import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
// Views are laid out at 1280x720 and rendered at 1.3x (1664x936), then framed on a 1920x1080 stage with a caption strip below.
export const W = 1280, H = 720, SCALE = 1.3;
export const SITE = pathToFileURL(join(here, '..', 'profiles', 'feisun', 'site')).href + '/';
export const OUT = join(here, 'out');
export const STAGE = pathToFileURL(join(here, 'stage.html')).href;
