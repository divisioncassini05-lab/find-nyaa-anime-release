import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { createBangumiRequest, proxyEnvironment, networkError } from '../host/bangumi-network.js';

test('proxy resolution prefers environment, respects exclusions and uses enabled system settings', () => {
  assert.deepEqual(proxyEnvironment({ https_proxy: 'http://env:8080', NO_PROXY: 'api.bgm.tv' }, { ProxyEnable: 1, ProxyServer: 'system:1' }), { HTTPS_PROXY: 'http://env:8080/', NO_PROXY: 'api.bgm.tv' });
  assert.equal(proxyEnvironment({}, { ProxyEnable: 1, ProxyServer: 'http=localhost:1;https=localhost:2' }).HTTPS_PROXY, 'http://localhost:2/');
  assert.equal(proxyEnvironment({}, { ProxyEnable: 0, ProxyServer: 'localhost:1' }).HTTPS_PROXY, undefined);
  assert.throws(() => proxyEnvironment({ HTTPS_PROXY: 'socks5://localhost:1' }), { code: 'bangumi_proxy_unsupported' });
});

test('private proxy agent preserves authorization and is destroyed after bounded response', async () => {
  let destroyed = false; let received;
  class Agent { constructor(options) { assert.equal(options.proxyEnv.HTTPS_PROXY, 'http://proxy/'); } destroy() { destroyed = true; } }
  const request = (url, options, callback) => {
    received = options; assert.equal(url.origin, 'https://api.bgm.tv');
    const req = new EventEmitter(); req.end = () => {};
    queueMicrotask(() => {
      const res = new EventEmitter(); res.statusCode = 200; res.headers = { 'content-type': 'application/json' };
      callback(res); res.emit('data', Buffer.from('{"id":123}')); res.emit('end');
    }); return req;
  };
  const send = createBangumiRequest({ env: () => ({ HTTPS_PROXY: 'http://proxy:80' }), AgentClass: Agent, request, readSystem: () => { throw Error('not used'); } });
  const result = await send('https://api.bgm.tv/v0/me', { headers: { Authorization: 'Bearer fixture' } });
  assert.equal(received.headers.Authorization, 'Bearer fixture');
  assert.deepEqual(await result.json(), { id: 123 }); assert.equal(destroyed, true);
});

test('direct and timeout cases never change global network settings or expose raw errors', async () => {
  let called = false;
  const send = createBangumiRequest({ env: () => ({}), readSystem: async () => ({}), direct: async () => { called = true; return new Response('{}'); } });
  await send('https://api.bgm.tv/v0/me'); assert.equal(called, true);
  await assert.rejects(send('https://example.com/'), { code: 'bangumi_invalid_origin' });
  assert.equal(networkError({ cause: { code: 'ECONNRESET', message: 'secret token' } }).code, 'bangumi_connection_reset');
  assert.equal(networkError({ code: 'ENOTFOUND' }).code, 'bangumi_dns_failed');
  const signal = AbortSignal.abort(new DOMException('timeout', 'TimeoutError'));
  assert.equal(networkError({}, signal).code, 'bangumi_timeout');
});

test('no proxy and disabled system proxy keep direct networking', async () => {
  for (const system of [{}, { ProxyEnable: 0, ProxyServer: 'unused.invalid:99' }]) {
    let direct = 0;
    const send = createBangumiRequest({ env: () => ({}), readSystem: async () => system,
      AgentClass: class { constructor() { assert.fail('must not create a proxy Agent'); } },
      direct: async () => { direct++; return new Response('{}'); } });
    await send('https://api.bgm.tv/v0/me'); assert.equal(direct, 1);
  }
});

test('explicit empty proxy disables system fallback and environment keys are case-aware', async () => {
  let direct = 0;
  const send = createBangumiRequest({ env: () => ({ HTTPS_PROXY: '' }),
    readSystem: () => assert.fail('explicit environment policy must not read system fallback'),
    direct: async () => { direct++; return new Response('{}'); } });
  await send('https://api.bgm.tv/v0/me'); assert.equal(direct, 1);
  assert.equal(proxyEnvironment({ https_proxy: 'http://lower.invalid:1', HTTPS_PROXY: 'http://upper.invalid:2' }).HTTPS_PROXY, 'http://lower.invalid:1/');
  assert.equal(proxyEnvironment({ ALL_PROXY: 'http://all.invalid:3' }).HTTPS_PROXY, 'http://all.invalid:3/');
  assert.equal(proxyEnvironment({ HTTPS_PROXY: 'http://proxy.invalid', no_proxy: '*', NO_PROXY: 'ignored.invalid' }).NO_PROXY, '*');
});

test('proxy failure does not silently bypass user routing policy', async () => {
  let destroyed = false;
  const send = createBangumiRequest({ env: () => ({ HTTPS_PROXY: 'http://offline.invalid:9' }),
    AgentClass: class { destroy() { destroyed = true; } },
    direct: () => assert.fail('must not bypass configured proxy'),
    request: () => { const req = new EventEmitter(); req.end = () => {}; queueMicrotask(() => req.emit('error', Object.assign(new Error('private network detail'), { code: 'ECONNREFUSED' }))); return req; } });
  await assert.rejects(send('https://api.bgm.tv/v0/me'), { code: 'bangumi_proxy_refused', message: 'bangumi_proxy_refused' });
  assert.equal(destroyed, true);
});

test('proxy writes preserve method/body and accept no-content responses', async () => {
  let body;
  const send = createBangumiRequest({ env: () => ({ HTTPS_PROXY: 'http://proxy.invalid' }), AgentClass: class { destroy() {} },
    request: (_url, options, callback) => {
      assert.equal(options.method, 'POST'); const req = new EventEmitter();
      req.end = (value) => { body = value; const res = new EventEmitter(); res.statusCode = 204; res.headers = {};
        queueMicrotask(() => { callback(res); res.emit('end'); }); };
      return req;
    } });
  assert.equal((await send('https://api.bgm.tv/v0/users/-/collections/123', { method: 'POST', body: '{"type":4}' })).status, 204);
  assert.equal(body, '{"type":4}');
});
