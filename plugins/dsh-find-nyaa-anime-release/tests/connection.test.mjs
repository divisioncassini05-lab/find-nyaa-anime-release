import assert from 'node:assert/strict';
import test from 'node:test';
import { createServer, request as httpRequest } from 'node:http';
import { once } from 'node:events';
import { createRequire } from 'node:module';
import { mkdtemp, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import * as plugin from '../index.js';

test('desktop worker registers panel routes without webServer or a separate HTTP channel', {
  skip: !process.env.DSH_TEST_NODE_MODULES,
}, async () => {
  const req = createRequire(path.join(path.resolve(process.env.DSH_TEST_NODE_MODULES), '../package.json'));
  const load = async (name) => import(pathToFileURL(req.resolve(name)).href);
  const { Context } = await load('@deepseek-ai/cordis');
  const { SkillRegistry } = await load('@deepseek-ai/dsh-skill');
  const { HostConnectionService } = await load('@deepseek-ai/dsh-client-connection');
  const ctx = new Context();
  const dir = await mkdtemp(path.join(os.tmpdir(), 'anime-worker-'));
  const oldHome = process.env.ANIME_DSH_HOME;
  const oldFetch = globalThis.fetch;
  process.env.ANIME_DSH_HOME = dir;
  try {
    await ctx.plugin(SkillRegistry);
    const connection = new HostConnectionService(ctx, [], { isAuthenticated: () => false, authenticateApi: () => undefined });
    const fork = ctx.plugin(plugin); await fork;
    await new Promise((resolve) => setImmediate(resolve));
    const handler = connection.createSharedFetchHandler('/api');
    const call = async (endpoint, payload = {}) => {
      const method = `anime-release/${endpoint}`;
      return handler.fetch(new Request(`http://worker/api/${method}`, { method: 'POST',
        body: JSON.stringify({ type: 'client-request', rpcId: 'worker-test', method, payload }) }), connection.browserPeer);
    };
    assert.equal(ctx.get('webServer'), undefined);
    assert.equal((await (await call('config/status')).json()).result.value.bangumi.connected, false);
    const connected = await (await call('config/bangumi/connect', { token: '' })).json();
    assert.equal(connected.result.error.code, 'bangumi_token_required');
    await call('config/bangumi/disconnect');
    const malformed = await handler.fetch(new Request('http://worker/api/anime-release/config/status', { method: 'POST', body: '{}' }), connection.browserPeer);
    assert.equal(malformed.status, 400);
    await fork.dispose();
    assert.equal((await call('config/status')).status, 404);
  } finally {
    globalThis.fetch = oldFetch;
    if (oldHome === undefined) delete process.env.ANIME_DSH_HOME; else process.env.ANIME_DSH_HOME = oldHome;
    await ctx.fiber.dispose(); await rm(dir, { recursive: true, force: true });
  }
});

for (const coreFirst of [true, false]) {
  test(`real Connection preserves core RPC with plugin ${coreFirst ? 'after' : 'before'} gateway`, {
    skip: !process.env.DSH_TEST_NODE_MODULES,
  }, async () => {
    const req = createRequire(path.join(path.resolve(process.env.DSH_TEST_NODE_MODULES), '../package.json'));
    const load = async (name) => import(pathToFileURL(req.resolve(name)).href);
    const { Context, Service } = await load('@deepseek-ai/cordis');
    const { SkillRegistry } = await load('@deepseek-ai/dsh-skill');
    const { HostConnectionService } = await load('@deepseek-ai/dsh-client-connection');
    const ctx = new Context();
    const routes = new Map();
    const dir = await mkdtemp(path.join(os.tmpdir(), 'anime-connection-'));
    const previousHome = process.env.ANIME_DSH_HOME;
    process.env.ANIME_DSH_HOME = dir;
    class WebServer extends Service {
      constructor(context) { super(context, 'webServer'); this.host = '127.0.0.1'; this.protocol = 'http:'; }
      register(route) {
        assert.ok(!routes.has(route.path), `duplicate route: ${route.path}`);
        routes.set(route.path, route);
        return () => routes.delete(route.path);
      }
    }
    class ScheduleFixture extends Service {
      constructor(context) { super(context, 'schedule'); }
    }
    const server = createServer(async (request, response) => {
      try {
        const route = [...routes.values()].find((entry) => request.url.startsWith(`${entry.path}/`));
        if (!route) { response.writeHead(404); response.end(); return; }
        await route.handler(request, response);
      } catch { response.writeHead(500); response.end('fixture handler failure'); }
    });
    try {
      await ctx.plugin(WebServer);
      await ctx.plugin(SkillRegistry);
      await ctx.plugin(ScheduleFixture);
      const connection = new HostConnectionService(ctx, [], {
        isAuthenticated: (request) => request.headers.cookie === 'fixture=owner',
        authenticateApi: () => undefined,
      });
      const mountCore = () => connection.rpc.intercept('/api',
        (endpoint) => ['settings/describe', 'llm/listConfigurableProviders'].includes(endpoint),
        async (endpoint) => ({ ok: true, value: { endpoint } }));
      if (coreFirst) mountCore();
      const fork = ctx.plugin(plugin);
      await fork;
      await new Promise((resolve) => setImmediate(resolve));
      if (!coreFirst) mountCore();
      server.listen(0, '127.0.0.1');
      await once(server, 'listening');
      const origin = `http://127.0.0.1:${server.address().port}`;
      const coreHandler = connection.createSharedFetchHandler('/api');
      const coreRead = async (endpoint) => {
        const response = await coreHandler.fetch(new Request(`${origin}/api/${endpoint}`, {
          method: 'POST', headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ type: 'client-request', rpcId: 'fixture', method: endpoint, payload: { args: {} } }),
        }), connection.browserPeer);
        assert.equal(response.status, 200);
        assert.deepEqual((await response.json()).result, { ok: true, value: { endpoint } });
      };
      const read = async (endpoint, authorized = true) => {
        // Ephemeral ports may be on Fetch's browser-only forbidden-port list.
        return new Promise((resolve, reject) => {
        const request = httpRequest(`${origin}/anime-release/${endpoint}`, {
          method: 'POST', headers: { 'content-type': 'application/json', ...(authorized ? { cookie: 'fixture=owner' } : {}) },
        }, (response) => {
          let text = ''; response.setEncoding('utf8');
          response.on('data', (chunk) => { text += chunk; });
          response.on('end', () => resolve({ response: { status: response.statusCode }, text }));
          response.on('error', reject);
        });
        request.on('error', reject);
        request.end(JSON.stringify({ type: 'client-request', rpcId: 'fixture', method: endpoint, payload: {} }));
        });
      };
      await coreRead('settings/describe');
      await coreRead('llm/listConfigurableProviders');
      const sharedRead = async (endpoint, payload = {}, peer = connection.browserPeer) => {
        const method = `anime-release/${endpoint}`;
        return coreHandler.fetch(new Request(`${origin}/api/${method}`, {
          method: 'POST', headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ type: 'client-request', rpcId: 'native-fixture', method, payload }),
        }), peer);
      };
      for (const endpoint of ['snapshot', 'config/status', 'plans/list', 'bangumi/library']) {
        const response = await sharedRead(endpoint);
        assert.equal(response.status, 200);
        const data = await response.json();
        assert.equal(data.rpcId, 'native-fixture');
        assert.equal(data.result.ok, true, JSON.stringify(data));
      }
      const missingToken = await (await sharedRead('config/bangumi/connect', { token: '' })).json();
      assert.equal(missingToken.result.error.code, 'bangumi_token_required');
      assert.equal((await sharedRead('config/status', {}, { principal: { kind: 'guest' } })).status, 403);
      const snapshot = await read('snapshot');
      assert.equal(snapshot.response.status, 200, snapshot.text);
      assert.deepEqual(JSON.parse(snapshot.text).result, { ok: true, value: { exists: false, shows: [] } });
      assert.equal((await read('snapshot', false)).response.status, 401);
      const plans = await read('plans/list');
      assert.equal(JSON.parse(plans.text).result.value.schedulerAvailable, true);
      const unknown = await read('settings/describe');
      assert.equal(JSON.parse(unknown.text).result.error.code, 'not_found');
      await fork.dispose();
      assert.equal((await sharedRead('config/status')).status, 404);
      assert.ok(!routes.has('/anime-release'));
      await coreRead('settings/describe');
      await coreRead('llm/listConfigurableProviders');
    } finally {
      server.closeAllConnections();
      if (server.listening) await new Promise((resolve) => server.close(resolve));
      await ctx.fiber.dispose();
      if (previousHome === undefined) delete process.env.ANIME_DSH_HOME;
      else process.env.ANIME_DSH_HOME = previousHome;
      await rm(dir, { recursive: true, force: true });
    }
  });
}
