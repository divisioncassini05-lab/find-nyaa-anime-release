import { open } from 'node:fs/promises';
import { bangumiHandler } from './bangumi.js';
import { configHandler } from './config.js';
import { plansHandler } from './plans.js';
import { statePath } from './paths.js';

export { statePath } from './paths.js';

export const CHANNEL = '/anime-release';
export const ENDPOINT = 'snapshot';
const MAX_BYTES = 4 * 1024 * 1024;
const phases = new Set(['airing', 'finale_pending_evidence', 'completed', 'blocked']);
const fail = (code) => Object.assign(new Error(code), { code });

function latestDelivery(show) {
  const deliveries = Array.isArray(show?.deliveries) ? show.deliveries : [];
  const candidates = deliveries.map((delivery) => {
    const operation = show.operations?.[delivery.operation_id];
    if (delivery.accepted !== true || operation?.committed !== true || operation.status !== 'accepted'
      || !['submitted', 'submitted_verified', 'already_present'].includes(delivery.status)) return null;
    const request = operation?.request;
    const sourceUrl = typeof request?.source_url === 'string' && /^https:\/\/nyaa\.si\/view\/\d+$/u.test(request.source_url)
      ? request.source_url : null;
    const episode = operation?.episode;
    const checkedAt = typeof delivery.checked_at === 'string' ? delivery.checked_at : null;
    if (!Number.isSafeInteger(episode) || episode < 1 || !checkedAt || !Number.isFinite(Date.parse(checkedAt))) return null;
    return { episode, checkedAt, ...(sourceUrl ? { sourceUrl } : {}) };
  }).filter(Boolean).sort((a, b) => Date.parse(b.checkedAt) - Date.parse(a.checkedAt));
  return candidates[0] || null;
}

export function projectState(data) {
  if (!data || data.version !== 3) throw fail('migration_required');
  if (!Array.isArray(data.shows) || data.shows.length > 500) throw fail('invalid_state');
  const ids = new Set();
  const integer = (n, min = 0) => Number.isSafeInteger(n) && n >= min;
  return data.shows.map((show) => {
    const { track_id: id, identity, progress: p, lifecycle, broadcast } = show || {};
    if (typeof id !== 'string' || !id || id.length > 200 || ids.has(id)
      || typeof identity?.title !== 'string' || !identity.title.trim() || identity.title.length > 500
      || !phases.has(lifecycle?.phase) || !integer(p?.handled_episode)
      || !integer(p?.latest_release_episode)
      || !(p?.target_episode === null || integer(p?.target_episode, 1))
      || (lifecycle.phase === 'completed' && p.target_episode !== null)
      || !(broadcast?.total_episodes == null || integer(broadcast.total_episodes, 1))) throw fail('invalid_state');
    ids.add(id);
    const cloud = show.bangumi;
    const delivery = latestDelivery(show);
    if (cloud && (!Array.isArray(cloud.watched_episodes)
      || !cloud.watched_episodes.every((n) => integer(n, 1))
      || ![null, 1, 2, 3, 4, 5].includes(cloud.collection_type))) throw fail('invalid_state');
    // Only UI fields cross the Host boundary: never operations, magnets, credentials or paths.
    return {
      id, title: identity.title,
      ...(Array.isArray(identity.aliases) ? { aliases: identity.aliases.filter((name) => typeof name === 'string') } : {}),
      ...(cloud?.subject_id ? { bangumiSubjectId: cloud.subject_id } : identity.provider_bindings?.bangumi?.entry_id ? { bangumiSubjectId: identity.provider_bindings.bangumi.entry_id } : {}),
      season: typeof identity.season === 'string' && /^S\d{1,3}$/iu.test(identity.season) ? identity.season : null,
      handled: p.handled_episode, latest: p.latest_release_episode, target: p.target_episode,
      total: broadcast?.total_episodes ?? null, phase: lifecycle.phase,
      waiting: Boolean(lifecycle.waiting_reason),
      ...(cloud ? { watchSource: 'bangumi', watchedCount: new Set(cloud.watched_episodes).size,
        collectionType: cloud.collection_type,
        syncPending: (show.outbox || []).filter((a) => a.kind === 'bangumi_watched' && a.status !== 'done').length } : {}),
      pending: Object.values(show.operations || {}).filter((op) => op && !op.committed
        && ['prepared', 'recovering', 'accepted'].includes(op.status)).length,
      ...(delivery ? { latestDelivery: delivery } : {}),
    };
  });
}

export async function readSnapshot({ file = statePath(), signal } = {}) {
  signal?.throwIfAborted();
  let handle;
  try {
    handle = await open(file, 'r');
    const stats = await handle.stat();
    if (!stats.isFile() || stats.size > MAX_BYTES) throw fail('state_too_large');
    const buffer = Buffer.alloc(MAX_BYTES + 1);
    let used = 0;
    while (used < buffer.length) {
      signal?.throwIfAborted();
      const { bytesRead } = await handle.read(buffer, used, buffer.length - used, null);
      if (!bytesRead) break;
      used += bytesRead;
    }
    if (used > MAX_BYTES) throw fail('state_too_large');
    signal?.throwIfAborted();
    const shows = projectState(JSON.parse(buffer.subarray(0, used).toString('utf8')));
    return { exists: true, shows };
  } catch (error) {
    if (error.code === 'ENOENT') return { exists: false, shows: [] };
    throw error;
  } finally { await handle?.close(); }
}

export function snapshotHandler(reader = readSnapshot, libraryReader, scheduler = () => null) {
  const readLibrary = libraryReader ? bangumiHandler(libraryReader) : bangumiHandler();
  const readConfig = configHandler();
  const managePlans = plansHandler({ scheduler });
  return async (endpoint, payload, signal, peer) => {
    const error = (code) => ({ ok: false, error: { code, message: code, details: {} } });
    if (peer?.principal?.kind !== 'owner') return error('forbidden');
    if (endpoint === 'bangumi/library' || endpoint === 'bangumi/metadata') return readLibrary(endpoint, payload, signal, peer);
    if (endpoint.startsWith('config/')) return readConfig(endpoint, payload, signal, peer);
    if (endpoint.startsWith('plans/')) return managePlans(endpoint, payload, signal, peer);
    if (endpoint !== ENDPOINT) return error('not_found');
    signal = peer.signal ? (signal ? AbortSignal.any([signal, peer.signal]) : peer.signal) : signal;
    if (!payload || typeof payload !== 'object' || Array.isArray(payload) || Object.keys(payload).length) return error('invalid_request');
    try {
      signal?.throwIfAborted();
      const value = await reader({ signal });
      signal?.throwIfAborted();
      return { ok: true, value };
    } catch (e) {
      const safe = new Set(['migration_required', 'invalid_state', 'state_too_large', 'invalid_data_directory']);
      return error(signal?.aborted ? 'cancelled' : safe.has(e.code) ? e.code : 'state_read_failed');
    }
  };
}
