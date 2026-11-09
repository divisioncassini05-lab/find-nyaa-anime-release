import path from 'node:path';
import os from 'node:os';

const fail = (code) => Object.assign(new Error(code), { code });

export function statePath(env = process.env, platform = process.platform, home = os.homedir()) {
  const p = platform === 'win32' ? path.win32 : path.posix;
  let base = env.ANIME_DSH_HOME || (platform === 'win32'
    ? p.join(env.LOCALAPPDATA || p.join(home, 'AppData', 'Local'), 'DSH', 'AnimeRelease')
    : platform === 'darwin' ? p.join(home, 'Library', 'Application Support', 'DSH', 'AnimeRelease')
      : p.join(env.XDG_DATA_HOME || p.join(home, '.local', 'share'), 'dsh', 'anime-release'));
  if (/^~([/\\]|$)/u.test(base)) base = p.join(home, base.slice(2));
  if (!p.isAbsolute(base)) throw fail('invalid_data_directory');
  return p.join(base, 'airing_watch_state.json');
}
