import { readFile, writeFile, rename, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { statePath } from './paths.js';
import { bangumiRequest, networkCodes } from './bangumi-network.js';
import { sameConnection, withBangumiLock } from './bangumi-session.js';

const API = 'https://api.bgm.tv';
const CACHE_TTL_MS = 10 * 60 * 1000;
const MAX_BYTES = 4 * 1024 * 1024;
const LIBRARY_VERSION = 2;
const METADATA_TTL_MS = 7 * 24 * 60 * 60 * 1000;
const fail = (code) => Object.assign(new Error(code), { code });

export function bangumiConfigPath(file = statePath()) {
  return file.replace(/\.json$/u, '.bangumi.json');
}

export function bangumiCachePath(file = statePath()) {
  return file.replace(/\.json$/u, '.bangumi-library.json');
}

async function readJson(file) {
  try {
    const raw = await readFile(file, 'utf8');
    if (Buffer.byteLength(raw, 'utf8') > MAX_BYTES) throw fail('bangumi_cache_too_large');
    return JSON.parse(raw.replace(/^\uFEFF/u, ''));
  } catch (error) {
    if (error.code === 'ENOENT') return null;
    throw error;
  }
}

async function writeJson(file, value) {
  await mkdir(path.dirname(file), { recursive: true });
  const temporary = `${file}.${randomUUID()}.tmp`;
  await writeFile(temporary, JSON.stringify(value), { encoding: 'utf8', mode: 0o600 });
  await rename(temporary, file);
}

async function readCache(file) {
  try { return await readJson(file); }
  catch { return null; }
}

async function commitForConnection(file, config, action) {
  return withBangumiLock(file, async () => {
    if (!sameConnection(config, await readJson(bangumiConfigPath(file)))) throw fail('bangumi_connection_changed');
    return action();
  });
}

function validConfig(value) {
  return value && value.version === 1 && Number.isInteger(value.account_id) && value.account_id > 0
    && typeof value.username === 'string' && value.username.trim();
}

async function tokenFor(config) {
  if (typeof config.token_file === 'string' && config.token_file) {
    let raw;
    try { raw = await readFile(config.token_file, 'utf8'); }
    catch { throw fail('bangumi_token_required'); }
    const token = raw.replace(/^\uFEFF/u, '').trim();
    if (token && !/\s/u.test(token)) return token;
    throw fail('bangumi_token_required');
  }
  const token = process.env[config.token_env || 'BANGUMI_ACCESS_TOKEN']?.trim();
  if (!token || /\s/u.test(token)) throw fail('bangumi_token_required');
  return token;
}

export function coverUrl(images) {
  for (const value of [images?.common, images?.medium, images?.large, images?.small, images?.grid]) {
    try {
      const url = new URL(value);
      if (['https:', 'http:'].includes(url.protocol) && url.hostname === 'lain.bgm.tv'
          && !url.username && !url.password && !url.port && url.pathname.startsWith('/pic/cover/')) {
        url.protocol = 'https:';
        return url.href;
      }
    } catch { /* Missing or untrusted image URLs keep the local placeholder. */ }
  }
  return null;
}

export function libraryItem(row) {
  const subject = row.subject || {};
  const title = subject.name_cn || subject.name;
  if (typeof title !== 'string' || !title.trim() || !Number.isInteger(row.subject_id || subject.id)) return null;
  const subjectId = Number(row.subject_id || subject.id);
  return {
    subject_id: subjectId,
    title,
    original_title: typeof subject.name === 'string' ? subject.name : null,
    cover_url: coverUrl(subject.images),
    aliases: Array.isArray(subject.aliases) ? subject.aliases.filter((name) => typeof name === 'string') : [],
    collection_type: Number.isInteger(row.type) ? row.type : null,
    watched_count: Number.isInteger(row.ep_status) && row.ep_status >= 0 ? row.ep_status : 0,
    episode_count: Number.isInteger(subject.eps) && subject.eps > 0 ? subject.eps : null,
    rating: Number.isInteger(row.rate) && row.rate > 0 ? row.rate : null,
    comment: typeof row.comment === 'string' ? row.comment.slice(0, 1000) : '',
    tags: Array.isArray(row.tags) ? row.tags.filter((tag) => typeof tag === 'string').slice(0, 30) : [],
    type: typeof subject.platform === 'string' && subject.platform.trim() ? subject.platform.trim() : null,
    date: typeof subject.date === 'string' ? subject.date : null,
    collection_date: typeof row.created_at === 'string' ? row.created_at
      : typeof row.added_at === 'string' ? row.added_at
        : typeof row.updated_at === 'string' ? row.updated_at : typeof row.lasttouch === 'string' ? row.lasttouch : null,
    updated_at: typeof row.updated_at === 'string' ? row.updated_at
      : typeof row.lasttouch === 'string' ? row.lasttouch : null,
  };
}

async function apiJson(token, route, signal, request = bangumiRequest, payload, method = 'POST') {
  const url = `${API}${route}`;
  const timeout = AbortSignal.timeout(8000);
  const requestSignal = signal ? AbortSignal.any([signal, timeout]) : timeout;
  let response;
  try {
    response = await request(url, { ...(payload ? { method, body: JSON.stringify(payload) } : {}), headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'User-Agent': 'AnimeRelease/0.2',
    }, signal: requestSignal });
  } catch (error) {
    if (signal?.aborted) throw fail('cancelled');
    if (networkCodes.includes(error.code)) throw error;
    throw fail('bangumi_network_unavailable');
  }
  if (!response.ok) throw fail(`bangumi_http_${response.status}`);
  return response.status === 204 ? null : response.json();
}

async function completeEpisodes(token, subject, signal, request) {
  const total = subject.eps;
  if (!Number.isSafeInteger(total) || total < 1 || total > 1000) return 'unknown_total';
  const route = `/v0/users/-/collections/${subject.id}/episodes`;
  const read = () => apiJson(token, `${route}?episode_type=0&limit=1000&offset=0`, signal, request);
  const before = await read();
  const valid = (page) => page?.total === total && Array.isArray(page.data) && page.data.length === total
    && new Set(page.data.map((r) => r.episode?.id)).size === total
    && page.data.every((r) => Number.isSafeInteger(r.episode?.id) && r.episode.id > 0
      && r.episode.subject_id === subject.id && r.episode.type === 0);
  if (!valid(before)) return 'coverage_unconfirmed';
  const ids = before.data.filter((r) => r.type !== 2).map((r) => r.episode.id);
  if (ids.length) await apiJson(token, route, signal, request, { episode_id: ids, type: 2 }, 'PATCH');
  const after = ids.length ? await read() : before;
  const expected = new Set(before.data.map((r) => r.episode.id));
  if (!valid(after) || after.data.some((r) => r.type !== 2 || !expected.has(r.episode.id))) throw fail('bangumi_progress_not_confirmed');
  return 'synced';
}

export async function updateBangumiCollection({ file = statePath(), subjectId, collectionType, throughEpisode = null, preserveWatched = false, signal, request = bangumiRequest } = {}) {
  if (!Number.isSafeInteger(subjectId) || subjectId < 1 || ![1, 2, 3, 4, 5].includes(collectionType)) throw fail('invalid_request');
  if (throughEpisode !== null && (!Number.isSafeInteger(throughEpisode) || throughEpisode < 1 || throughEpisode > 1000)) throw fail('invalid_request');
  const config = await readJson(bangumiConfigPath(file));
  if (!validConfig(config)) throw fail('bangumi_token_required');
  const token = await tokenFor(config);
  const me = await apiJson(token, '/v0/me', signal, request);
  if (me.id !== config.account_id) throw fail('bangumi_account_conflict');
  const subject = await apiJson(token, `/v0/subjects/${subjectId}`, signal, request);
  if (subject.id !== subjectId || subject.type !== 2) throw fail('bangumi_invalid_subject');
  const collectionRoute = `/v0/users/${encodeURIComponent(config.username)}/collections/${subjectId}`;
  let preservedWatched = false;
  if (preserveWatched) {
    let before;
    try { before = await apiJson(token, collectionRoute, signal, request); }
    catch (error) { if (error.code !== 'bangumi_http_404') throw error; }
    if (before?.type === 2) {
      // Startup may preserve the flag only; an explicit progress click must still
      // verify and fill its episode scope even when the whole work says watched.
      if (throughEpisode === null && collectionType !== 2) return { status: 'bangumi_collection_updated', collectionType: 2, progress: 'not_requested', preservedWatched: true };
      collectionType = 2;
      preservedWatched = true;
    }
  }
  if (!preservedWatched) await apiJson(token, `/v0/users/-/collections/${subjectId}`, signal, request, { type: collectionType });
  const after = await apiJson(token, `/v0/users/${encodeURIComponent(config.username)}/collections/${subjectId}`, signal, request);
  if (after.type !== collectionType) throw fail('bangumi_write_not_confirmed');
  let progress = 'not_requested';
  if (collectionType === 2 || throughEpisode !== null) {
    try { progress = throughEpisode === null ? await completeEpisodes(token, subject, signal, request)
      : await syncThroughEpisode(token, subject, throughEpisode, signal, request); }
    catch { progress = 'pending'; }
    if (progress === 'synced') {
      const verified = await apiJson(token, `/v0/users/${encodeURIComponent(config.username)}/collections/${subjectId}`, signal, request);
      if (verified.type !== collectionType) throw fail('bangumi_write_not_confirmed');
    }
  }
  const cached = await readJson(bangumiCachePath(file));
  if (cached?.account_id === config.account_id) {
    const row = cached.items?.find((item) => item.subject_id === subjectId);
    if (row) { row.collection_type = collectionType; if (progress === 'synced') row.watched_count = throughEpisode === null ? subject.eps : Math.max(row.watched_count || 0, throughEpisode); }
    cached.checked_at = null;
    await writeJson(bangumiCachePath(file), cached);
  }
  return { status: 'bangumi_collection_updated', collectionType, progress, ...(preservedWatched ? { preservedWatched: true } : {}), ...(progress === 'synced' ? { syncedEpisode: throughEpisode ?? subject.eps } : {}) };
}

async function syncThroughEpisode(token, subject, through, signal, request) {
  // Episode sort is the subject's numbering. Never use collection ep_status (books only).
  const route = `/v0/users/-/collections/${subject.id}/episodes`;
  const read = async () => {
    const rows = [];
    for (let offset = 0; offset < 1000; offset += 100) {
      const page = await apiJson(token, `${route}?episode_type=0&limit=100&offset=${offset}`, signal, request);
      if (!Array.isArray(page?.data)) throw fail('bangumi_invalid_page');
      rows.push(...page.data);
      if (rows.length >= page.total || page.data.length < 100) return rows;
    }
    throw fail('bangumi_invalid_page');
  };
  const select = (rows) => {
    const result = [];
    for (let number = 1; number <= through; number++) {
      const matches = rows.filter((r) => r.episode?.type === 0 && r.episode.subject_id === subject.id && r.episode.sort === number);
      if (matches.length !== 1 || !Number.isSafeInteger(matches[0].episode.id) || matches[0].episode.id <= 0) return null;
      result.push(matches[0]);
    }
    return new Set(result.map((r) => r.episode.id)).size === through ? result : null;
  };
  const before = select(await read());
  if (!before) return 'coverage_unconfirmed';
  const ids = before.filter((r) => r.type !== 2).map((r) => r.episode.id);
  for (let i = 0; i < ids.length; i += 100) await apiJson(token, route, signal, request, { episode_id: ids.slice(i, i + 100), type: 2 }, 'PATCH');
  const after = ids.length ? select(await read()) : before;
  if (!after || after.some((r, i) => r.type !== 2 || r.episode.id !== before[i].episode.id)) throw fail('bangumi_progress_not_confirmed');
  return 'synced';
}

const metadataPath = (file) => file.replace(/\.json$/u, '.bangumi-subjects.json');
const freshMetadata = (entry) => entry && Date.now() - Date.parse(entry.checked_at) < METADATA_TTL_MS;
async function withMetadata(items, file) {
  const cache = await readCache(metadataPath(file));
  return items.map((row) => {
    const entry = cache?.items?.[row.subject_id];
    return freshMetadata(entry) ? { ...row, type: entry.type || row.type, date: entry.date || row.date,
      cover_url: row.cover_url || entry.cover_url, metadata_checked: true } : row;
  });
}

export async function readBangumiLibrary({ file = statePath(), refresh = false, signal, request = bangumiRequest } = {}) {
  signal?.throwIfAborted();
  const config = await readJson(bangumiConfigPath(file));
  if (!validConfig(config)) return { status: 'not_configured', items: [], checked_at: null };
  const cacheFile = bangumiCachePath(file);
  const cached = await readCache(cacheFile);
  const usableCache = cached?.version === LIBRARY_VERSION && cached.account_id === config.account_id
    && Number.isFinite(Date.parse(cached.checked_at)) && Array.isArray(cached.items);
  const token = await tokenFor(config);
  if (!refresh && usableCache && Date.now() - Date.parse(cached.checked_at) < CACHE_TTL_MS) {
    return commitForConnection(file, config, async () => ({ status: 'ready', cached: true, account_id: config.account_id, username: config.username,
      checked_at: cached.checked_at, items: await withMetadata(cached.items, file) }));
  }
  const rows = [];
  let complete = false;
  try {
  for (let offset = 0; offset < 10000; offset += 100) {
    signal?.throwIfAborted();
    const page = await apiJson(token, `/v0/users/${encodeURIComponent(config.username)}/collections?subject_type=2&limit=100&offset=${offset}`, signal, request);
    if (!page || !Array.isArray(page.data)) throw fail('bangumi_invalid_page');
    rows.push(...page.data);
    if (Number.isInteger(page.total) ? rows.length >= page.total : page.data.length < 100) { complete = true; break; }
    if (!page.data.length) break;
  }
  if (!complete) throw fail('bangumi_library_incomplete');
  } catch (error) {
    signal?.throwIfAborted();
    const retryable = networkCodes.includes(error.code) || ['bangumi_network_unavailable', 'bangumi_http_429', 'bangumi_library_incomplete'].includes(error.code)
      || /^bangumi_http_5\d\d$/u.test(error.code || '');
    if (!usableCache || !retryable) throw error;
    return commitForConnection(file, config, async () => ({ status: 'stale', cached: true, warning: error.code,
      account_id: config.account_id, username: config.username, checked_at: cached.checked_at,
      items: await withMetadata(cached.items, file) }));
  }
  const items = rows.map(libraryItem).filter(Boolean);
  const checkedAt = new Date().toISOString();
  signal?.throwIfAborted();
  await commitForConnection(file, config, () => writeJson(cacheFile, { version: LIBRARY_VERSION, account_id: config.account_id, username: config.username,
    checked_at: checkedAt, items }));
  return { status: 'ready', cached: false, account_id: config.account_id, username: config.username,
    checked_at: checkedAt, items: await withMetadata(items, file) };
}

export async function readBangumiMetadata({ file = statePath(), ids, signal, request = bangumiRequest } = {}) {
  if (!Array.isArray(ids) || !ids.length || ids.length > 24 || ids.some((id) => !Number.isSafeInteger(id) || id <= 0)) throw fail('invalid_request');
  const config = await readJson(bangumiConfigPath(file));
  const library = await readJson(bangumiCachePath(file));
  if (!validConfig(config) || library?.account_id !== config.account_id) throw fail('bangumi_token_required');
  const allowed = new Set(library.items.map((row) => row.subject_id));
  if (ids.some((id) => !allowed.has(id))) throw fail('invalid_request');
  const cached = await readCache(metadataPath(file));
  const entries = { ...(cached?.items || {}) };
  const token = await tokenFor(config);
  const queue = [...new Set(ids)]; const items = []; const unresolved = [];
  const timeout = AbortSignal.timeout(10000);
  const budget = signal ? AbortSignal.any([signal, timeout]) : timeout;
  await Promise.all(Array.from({ length: Math.min(4, queue.length) }, async () => {
    while (queue.length) {
      const id = queue.shift();
      if (freshMetadata(entries[id])) { items.push({ subject_id: id, ...entries[id] }); continue; }
      try {
        budget.throwIfAborted();
        const subject = await apiJson(token, `/v0/subjects/${id}`, budget, request);
        if (subject?.id !== id || subject.type !== 2) throw fail('bangumi_invalid_subject');
        const entry = { type: typeof subject.platform === 'string' ? subject.platform : null,
          date: typeof subject.date === 'string' ? subject.date : null, cover_url: coverUrl(subject.images),
          checked_at: new Date().toISOString(), metadata_checked: true };
        entries[id] = entry; items.push({ subject_id: id, ...entry });
      } catch { unresolved.push(id); }
    }
  }));
  signal?.throwIfAborted();
  // Cache only the current library's public metadata, never credentials or failed lookups.
  await commitForConnection(file, config, () => writeJson(metadataPath(file), { version: 1, items: Object.fromEntries(Object.entries(entries).filter(([id]) => allowed.has(Number(id)))) }));
  return { items, unresolved };
}

export function bangumiHandler(reader = readBangumiLibrary, metadataReader = readBangumiMetadata) {
  return async (endpoint, payload, signal, peer) => {
    const error = (code) => ({ ok: false, error: { code, message: code, details: {} } });
    if (peer?.principal?.kind !== 'owner') return error('forbidden');
    if (!['bangumi/library', 'bangumi/metadata'].includes(endpoint)) return error('not_found');
    const metadata = endpoint === 'bangumi/metadata';
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)
      || Object.keys(payload).some((key) => key !== (metadata ? 'ids' : 'refresh'))
      || (metadata ? !Array.isArray(payload.ids) || !payload.ids.length || payload.ids.length > 24 || payload.ids.some((id) => !Number.isSafeInteger(id) || id <= 0)
        : payload.refresh !== undefined && typeof payload.refresh !== 'boolean')) {
      return error('invalid_request');
    }
    const combinedSignal = peer.signal ? (signal ? AbortSignal.any([signal, peer.signal]) : peer.signal) : signal;
    try {
      combinedSignal?.throwIfAborted();
      const value = await (metadata ? metadataReader({ ids: payload.ids, signal: combinedSignal }) : reader({ refresh: payload.refresh === true, signal: combinedSignal }));
      combinedSignal?.throwIfAborted();
      return { ok: true, value };
    } catch (e) {
      const safe = new Set(['cancelled', 'bangumi_cache_too_large', 'bangumi_token_required', 'bangumi_connection_changed', 'bangumi_library_incomplete',
        'bangumi_network_unavailable', 'bangumi_invalid_page', 'bangumi_http_401', 'bangumi_http_403', 'bangumi_http_429']);
      return error(combinedSignal?.aborted ? 'cancelled' : safe.has(e.code) || networkCodes.includes(e.code) ? e.code : 'bangumi_read_failed');
    }
  };
}
