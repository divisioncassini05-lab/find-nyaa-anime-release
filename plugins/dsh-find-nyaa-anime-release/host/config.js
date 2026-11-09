import { mkdir, readFile, rename, unlink, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { bangumiConfigPath, bangumiCachePath } from './bangumi.js';
import { statePath } from './paths.js';
import { bangumiRequest, networkCodes } from './bangumi-network.js';
import { sameConnection, withBangumiLock } from './bangumi-session.js';

const API = 'https://api.bgm.tv';
const fail = (code) => Object.assign(new Error(code), { code });

function setupPath(file = statePath()) {
  return file.replace(/\.json$/u, '.setup.json');
}

function tokenPath(file = statePath()) {
  return file.replace(/\.json$/u, '.bangumi.token');
}

async function readJson(file) {
  try { return JSON.parse(await readFile(file, 'utf8')); }
  catch (error) { if (error.code === 'ENOENT') return {}; throw error; }
}

async function writeJson(file, value) {
  await mkdir(path.dirname(file), { recursive: true });
  const temporary = `${file}.${randomUUID()}.tmp`;
  await writeFile(temporary, JSON.stringify(value), { encoding: 'utf8', mode: 0o600 });
  await rename(temporary, file);
}

function publicConfig(bangumi, qbittorrent) {
  return {
    bangumi: {
      connected: Number.isInteger(bangumi.account_id) && typeof bangumi.username === 'string',
      username: typeof bangumi.username === 'string' ? bangumi.username : null,
      account_id: Number.isInteger(bangumi.account_id) ? bangumi.account_id : null,
    },
    qbittorrent: {
      configured: Boolean(qbittorrent.qbittorrent_exe || qbittorrent.web_url),
      executable: qbittorrent.qbittorrent_exe || null,
      download_directory: qbittorrent.download_directory || null,
      web_url: qbittorrent.web_url || null,
      username: qbittorrent.web_username || null,
      password_configured: Boolean(qbittorrent.web_password),
      client: qbittorrent.client || (qbittorrent.web_url ? 'webapi' : 'desktop'),
      auto_submit: qbittorrent.auto_submit === true,
    },
  };
}

export async function readConfig({ file = statePath() } = {}) {
  const [bangumi, qbittorrent] = await Promise.all([readJson(bangumiConfigPath(file)), readJson(setupPath(file))]);
  return publicConfig(bangumi, qbittorrent);
}

async function verifyBangumi(token, signal, request) {
  if (typeof token !== 'string' || !token.trim() || /\s/u.test(token.trim())) throw fail('bangumi_token_required');
  const timeout = AbortSignal.timeout(8000);
  const requestSignal = signal ? AbortSignal.any([signal, timeout]) : timeout;
  let response;
  try {
    response = await request(`${API}/v0/me`, {
      headers: { Authorization: `Bearer ${token.trim()}`, Accept: 'application/json', 'User-Agent': 'AnimeRelease/0.2' },
      signal: requestSignal,
    });
  } catch (error) {
    if (signal?.aborted) throw fail('cancelled');
    if (networkCodes.includes(error.code)) throw error;
    throw fail('bangumi_network_unavailable');
  }
  if (response.status === 401) throw fail('bangumi_http_401');
  if (response.status === 403) throw fail('bangumi_http_403');
  if (!response.ok) throw fail(`bangumi_http_${response.status}`);
  const profile = await response.json();
  if (!Number.isInteger(profile?.id) || typeof profile.username !== 'string' || !profile.username.trim()) throw fail('bangumi_invalid_profile');
  return { id: profile.id, username: profile.username.trim(), token: token.trim() };
}

function ownedCredential(file, credential) {
  return typeof credential === 'string' && (credential === tokenPath(file)
    || (path.dirname(credential) === path.dirname(tokenPath(file))
      && credential.startsWith(tokenPath(file) + '.') && /^[0-9a-f-]{36}$/u.test(credential.slice(tokenPath(file).length + 1))));
}

export async function connectBangumi({ token, file = statePath(), signal, request = bangumiRequest } = {}) {
  const before = await readJson(bangumiConfigPath(file));
  const profile = await verifyBangumi(token, signal, request);
  return withBangumiLock(file, async () => {
    signal?.throwIfAborted();
    const existing = await readJson(bangumiConfigPath(file));
    if (!sameConnection(before, existing)) throw fail('bangumi_connection_changed');
    if (existing.account_id && existing.account_id !== profile.id) throw fail('bangumi_account_conflict');
    const connectionId = randomUUID();
    const credential = `${tokenPath(file)}.${connectionId}`;
    await mkdir(path.dirname(credential), { recursive: true });
    await writeFile(credential, profile.token, { encoding: 'utf8', mode: 0o600 });
    try {
      await writeJson(bangumiConfigPath(file), { ...existing, version: 1, account_id: profile.id, username: profile.username,
        token_file: credential, connection_id: connectionId, delivery_as_watched: true });
    } catch (error) { await unlink(credential).catch(() => {}); throw error; }
    if (ownedCredential(file, existing.token_file)) await unlink(existing.token_file).catch(() => {});
    return { status: 'connected', username: profile.username, account_id: profile.id };
  });
}

export async function disconnectBangumi({ file = statePath() } = {}) {
  return withBangumiLock(file, async () => {
  const config = await readJson(bangumiConfigPath(file));
  await unlink(bangumiConfigPath(file)).catch((error) => { if (error.code !== 'ENOENT') throw error; });
  if (ownedCredential(file, config.token_file)) await unlink(config.token_file).catch((error) => { if (error.code !== 'ENOENT') throw error; });
  await unlink(bangumiCachePath(file)).catch((error) => { if (error.code !== 'ENOENT') throw error; });
  return { status: 'disconnected' };
  });
}

export async function saveQbittorrent({ values, file = statePath() } = {}) {
  if (!values || typeof values !== 'object' || Array.isArray(values)) throw fail('invalid_request');
  const allowed = new Set(['qbittorrent_exe', 'download_directory', 'web_url', 'web_username', 'web_password', 'client', 'auto_submit']);
  if (Object.keys(values).some((key) => !allowed.has(key))) throw fail('invalid_request');
  const current = await readJson(setupPath(file));
  const next = { ...current, version: 1, completed: true };
  for (const key of allowed) if (values[key] !== undefined) {
    if (key === 'auto_submit') { if (typeof values[key] !== 'boolean') throw fail('invalid_request'); next[key] = values[key]; continue; }
    if (typeof values[key] !== 'string' || values[key].length > 1000) throw fail('invalid_request');
    if (values[key].trim()) next[key] = key === 'web_password' ? values[key] : values[key].trim();
    else delete next[key];
  }
  if (next.client && !['webapi', 'desktop'].includes(next.client)) throw fail('invalid_request');
  if (next.web_url) validateWebUrl(next.web_url);
  await writeJson(setupPath(file), next);
  return { status: 'saved' };
}

function validateWebUrl(value) {
  let url;
  try { url = new URL(value); } catch { throw fail('invalid_qb_url'); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw fail('invalid_qb_url');
  return url.href.replace(/\/$/u, '');
}

export async function testQbittorrent({ values = {}, file = statePath(), signal, request = fetch } = {}) {
  if (Object.keys(values).some((key) => !['web_url', 'web_username', 'web_password'].includes(key))) throw fail('invalid_request');
  const settings = { ...await readJson(setupPath(file)), ...values };
  const base = validateWebUrl(settings.web_url);
  const timeout = AbortSignal.timeout(8000);
  const requestSignal = signal ? AbortSignal.any([signal, timeout]) : timeout;
  try {
    const login = await request(`${base}/api/v2/auth/login`, { method: 'POST', redirect: 'error', signal: requestSignal,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', Referer: base + '/' },
      body: new URLSearchParams({ username: settings.web_username || '', password: settings.web_password || '' }) });
    if (!login.ok || (await login.text()).trim() !== 'Ok.') throw fail('qb_auth_failed');
    const cookie = login.headers.get('set-cookie')?.match(/(?:^|[;,]\s*)SID=([^;,]+)/u)?.[1];
    const response = await request(`${base}/api/v2/app/version`, { redirect: 'error', signal: requestSignal,
      headers: { Referer: base + '/', ...(cookie ? { Cookie: `SID=${cookie}` } : {}) } });
    if (!response.ok) throw fail('qb_auth_failed');
    const version = (await response.text()).trim();
    if (!/^v?\d+\.\d+(?:\.\d+)?(?:[\w.-]*)$/u.test(version)) throw fail('qb_invalid_response');
    return { status: 'connected', version };
  } catch (error) {
    if (['qb_auth_failed', 'qb_invalid_response'].includes(error.code)) throw error;
    throw fail(signal?.aborted ? 'cancelled' : 'qb_network_unavailable');
  }
}

function requestError(code) { return { ok: false, error: { code, message: code, details: {} } }; }

export function configHandler() {
  return async (endpoint, payload, signal, peer) => {
    if (peer?.principal?.kind !== 'owner') return requestError('forbidden');
    const combinedSignal = peer.signal ? (signal ? AbortSignal.any([signal, peer.signal]) : peer.signal) : signal;
    try {
      combinedSignal?.throwIfAborted();
      if (endpoint === 'config/status') {
        if (payload && (typeof payload !== 'object' || Array.isArray(payload) || Object.keys(payload).length)) return requestError('invalid_request');
        return { ok: true, value: await readConfig() };
      }
      if (endpoint === 'config/bangumi/connect') {
        if (!payload || typeof payload.token !== 'string' || Object.keys(payload).some((key) => key !== 'token')) return requestError('invalid_request');
        return { ok: true, value: await connectBangumi({ token: payload.token, signal: combinedSignal }) };
      }
      if (endpoint === 'config/bangumi/disconnect') {
        if (payload && (typeof payload !== 'object' || Array.isArray(payload) || Object.keys(payload).length)) return requestError('invalid_request');
        return { ok: true, value: await disconnectBangumi() };
      }
      if (endpoint === 'config/qbittorrent/save') {
        return { ok: true, value: await saveQbittorrent({ values: payload }) };
      }
      if (endpoint === 'config/qbittorrent/test') {
        return { ok: true, value: await testQbittorrent({ values: payload, signal: combinedSignal }) };
      }
      return requestError('not_found');
    } catch (error) {
      const safe = new Set(['cancelled', 'invalid_request', 'bangumi_connection_changed', 'bangumi_token_required', 'bangumi_network_unavailable', 'bangumi_http_401', 'bangumi_http_403', 'bangumi_invalid_profile', 'bangumi_account_conflict', 'invalid_qb_url', 'qb_auth_failed', 'qb_invalid_response', 'qb_network_unavailable']);
      return requestError(combinedSignal?.aborted ? 'cancelled' : safe.has(error.code) || networkCodes.includes(error.code) ? error.code : 'config_failed');
    }
  };
}
