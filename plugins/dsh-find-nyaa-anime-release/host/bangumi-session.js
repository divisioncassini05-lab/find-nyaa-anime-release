import path from 'node:path';

const queues = new Map();

// Serialize only local commits, never hold the lock while waiting for the network.
export function withBangumiLock(file, action) {
  const key = path.resolve(file);
  const task = (queues.get(key) || Promise.resolve()).catch(() => {}).then(action);
  queues.set(key, task);
  task.finally(() => { if (queues.get(key) === task) queues.delete(key); }).catch(() => {});
  return task;
}

export function sameConnection(a, b) {
  return ['account_id', 'username', 'token_file', 'token_env', 'connection_id'].every((key) => (a?.[key] ?? null) === (b?.[key] ?? null));
}
