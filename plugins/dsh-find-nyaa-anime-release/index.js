import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { sep } from 'node:path';
import { CHANNEL, snapshotHandler } from './host/snapshot.js';
import { registerPanelRoutes } from './host/panel-routes.js';

export const name = 'find-nyaa-anime-release';
export const inject = ['skills'];

const directory = fileURLToPath(new URL('./skills/find-nyaa-anime-release/', import.meta.url));
const skillFile = new URL('./skills/find-nyaa-anime-release/SKILL.md', import.meta.url);
const summary = Object.freeze({
  name,
  description: 'Find and verify Nyaa anime episodes, complete seasons and movies; check Chinese subtitles, return magnets or deliver reviewed releases to qBittorrent. Use DSH scheduling tools for explicitly requested tracking.',
  invocation: { modelInvocable: true, userInvocable: true },
  provider: 'dsh-find-nyaa-anime-release',
  source: 'bundled',
  resourceBase: { kind: 'directory', path: directory.split(sep).join('/') },
});

export function apply(ctx) {
  ctx.inject(['connection'], registerPanelRoutes);
  // Optional: the same package remains a headless Skill provider.
  ctx.inject(['connection', 'webServer'], (scoped) => {
    // /api has one interceptor owned by DSH's gateway, not by extensions.
    scoped.connection.rpc.handle(CHANNEL, snapshotHandler(undefined, undefined, () => scoped.get('schedule')));
  });
  // The registry owns disposal. No copying into ~/.codex or ~/.dsh/skills.
  ctx.skills.registerProvider(() => ({
    name: summary.provider,
    list: async () => [{ ...summary, rank: 600, locator: skillFile.href }],
    async get(_candidate, options = {}) {
      const raw = await readFile(skillFile, { encoding: 'utf8', signal: options.signal });
      const end = /^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/u.exec(raw);
      if (!end) throw new Error('Bundled skill has invalid frontmatter');
      return { ...summary, content: raw.slice(end[0].length).trim() };
    },
  }));
}
