import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';

const run = promisify(execFile);
const script = fileURLToPath(new URL('../skills/find-nyaa-anime-release/scripts/dsh_panel_run.py', import.meta.url));
const pending = new Map();

export async function submitPlanDownload(file, id, infoHash, signal) {
  const interpreters = process.env.ANIME_DSH_PYTHON ? [[process.env.ANIME_DSH_PYTHON, []]]
    : process.platform === 'win32' ? [['python', []], ['py', ['-3']], ['python3', []]] : [['python3', []], ['python', []]];
  for (const [exe, prefix] of interpreters) {
    try {
      const { stdout } = await run(exe, [...prefix, '-X', 'utf8', script, '--state', file, '--plan-id', id, 'download', infoHash],
        { windowsHide: true, timeout: 90000, maxBuffer: 512 * 1024, signal });
      const result = JSON.parse(stdout);
      if (!['download_submitted', 'download_pending', 'resource_review_required'].includes(result.status)) throw new Error('invalid_result');
      return result;
    } catch (error) {
      if (!['ENOENT', 'EACCES'].includes(error.code)) throw Object.assign(new Error('download_failed'), { code: 'download_failed' });
    }
  }
  throw Object.assign(new Error('python_unavailable'), { code: 'python_unavailable' });
}

export async function readPlanEvidence(file) {
  if (pending.has(file)) return pending.get(file);
  const task = (async () => {
    const interpreters = process.env.ANIME_DSH_PYTHON ? [[process.env.ANIME_DSH_PYTHON, []]]
      : process.platform === 'win32' ? [['python', []], ['py', ['-3']], ['python3', []]] : [['python3', []], ['python', []]];
    for (const [exe, prefix] of interpreters) {
      try {
        const { stdout } = await run(exe, [...prefix, '-X', 'utf8', script, '--state', file, 'snapshot'],
          { windowsHide: true, timeout: 10000, maxBuffer: 2 * 1024 * 1024 });
        return JSON.parse(stdout);
      } catch (error) {
        if (!['ENOENT', 'EACCES'].includes(error.code)) throw Object.assign(new Error('history_check_incomplete'), { code: 'history_check_incomplete' });
      }
    }
    throw Object.assign(new Error('python_unavailable'), { code: 'python_unavailable' });
  })();
  pending.set(file, task);
  try { return await task; } finally { pending.delete(file); }
}
