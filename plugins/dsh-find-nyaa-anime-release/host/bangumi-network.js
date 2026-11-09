import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { Agent, request as httpsRequest } from 'node:https';

const run = promisify(execFile);
const fail = (code) => Object.assign(new Error(code), { code });
let systemCache;

export function proxyEnvironment(env, system = {}) {
  const value = (name) => env[name.toLowerCase()] ?? env[name];
  const explicit = value('HTTPS_PROXY') ?? value('HTTP_PROXY') ?? value('ALL_PROXY');
  const proxy = explicit ?? (system.ProxyEnable === 1 ? system.ProxyServer : undefined);
  let httpsProxy;
  if (proxy) {
    const candidate = proxy.includes('=')
      ? proxy.split(';').map((v) => v.trim()).find((v) => v.startsWith('https='))?.slice(6)
      : proxy;
    if (candidate) {
      const url = new URL(candidate.includes('://') ? candidate : `http://${candidate}`);
      if (!['http:', 'https:'].includes(url.protocol)) throw fail('bangumi_proxy_unsupported');
      httpsProxy = url.href;
    }
  }
  return { ...(httpsProxy ? { HTTPS_PROXY: httpsProxy } : {}), NO_PROXY: value('NO_PROXY') || '' };
}

async function systemProxy() {
  if (process.platform !== 'win32') return {};
  if (systemCache && Date.now() - systemCache.at < 30000) return systemCache.value;
  try {
    const script = "$p=Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings'; @{ProxyEnable=$p.ProxyEnable;ProxyServer=$p.ProxyServer}|ConvertTo-Json -Compress";
    const { stdout } = await run('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script], { windowsHide: true, timeout: 2500, maxBuffer: 16384 });
    const value = JSON.parse(stdout.replace(/^\uFEFF/u, ''));
    systemCache = { at: Date.now(), value }; return value;
  } catch { return {}; }
}

export function networkError(error, signal) {
  if (signal?.aborted) return fail(signal.reason?.name === 'TimeoutError' ? 'bangumi_timeout' : 'cancelled');
  const code = error?.cause?.code || error?.code;
  if (['ENOTFOUND', 'EAI_AGAIN'].includes(code)) return fail('bangumi_dns_failed');
  if (['CERT_HAS_EXPIRED', 'DEPTH_ZERO_SELF_SIGNED_CERT', 'UNABLE_TO_VERIFY_LEAF_SIGNATURE', 'ERR_TLS_CERT_ALTNAME_INVALID'].includes(code)) return fail('bangumi_tls_failed');
  if (code === 'ECONNRESET') return fail('bangumi_connection_reset');
  if (code === 'ECONNREFUSED') return fail('bangumi_proxy_refused');
  return fail(error?.code === 'bangumi_proxy_unsupported' ? error.code : 'bangumi_network_unavailable');
}

export function createBangumiRequest({ env = () => process.env, readSystem = systemProxy, request = httpsRequest, AgentClass = Agent, direct = (...args) => fetch(...args) } = {}) {
  return async (input, init = {}) => {
    const url = new URL(input);
    if (url.origin !== 'https://api.bgm.tv') throw fail('bangumi_invalid_origin');
    let agent;
    try {
      const variables = env();
      const hasExplicit = ['https_proxy', 'HTTPS_PROXY', 'http_proxy', 'HTTP_PROXY', 'all_proxy', 'ALL_PROXY'].some((k) => variables[k] !== undefined);
      const proxyEnv = proxyEnvironment(variables, hasExplicit ? {} : await readSystem());
      if (!proxyEnv.HTTPS_PROXY) return await direct(url, init);
      // A private standard-library Agent; no process-wide dispatcher changes.
      agent = new AgentClass({ proxyEnv });
      return await new Promise((resolve, reject) => {
        const req = request(url, { agent, method: init.method || 'GET', headers: init.headers, signal: init.signal }, (res) => {
          const chunks = []; let size = 0;
          res.on('error', reject);
          res.on('data', (chunk) => {
            size += chunk.length;
            if (size > 4 * 1024 * 1024) { res.destroy(fail('bangumi_response_too_large')); return; }
            chunks.push(chunk);
          });
          res.on('end', () => resolve(new Response([204, 205, 304].includes(res.statusCode) ? null : Buffer.concat(chunks), { status: res.statusCode, headers: res.headers })));
        });
        req.on('error', reject);
        req.end(init.body);
      });
    } catch (error) { throw networkError(error, init.signal); }
    finally { agent?.destroy(); }
  };
}

export const bangumiRequest = createBangumiRequest();
export const networkCodes = ['bangumi_timeout', 'bangumi_dns_failed', 'bangumi_tls_failed', 'bangumi_connection_reset', 'bangumi_proxy_refused', 'bangumi_proxy_unsupported'];
