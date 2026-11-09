import { snapshotHandler } from './snapshot.js';

const endpoints = ['snapshot', 'bangumi/library', 'bangumi/metadata', 'config/status', 'config/bangumi/connect',
  'config/bangumi/disconnect', 'config/qbittorrent/save', 'config/qbittorrent/test',
  'plans/list', 'plans/save', 'plans/requirements', 'plans/schedule', 'plans/download', 'plans/check', 'plans/pause', 'plans/schedulePause', 'plans/delete', 'plans/sync', 'plans/collection'];

export function registerPanelRoutes(ctx) {
  const handle = snapshotHandler(undefined, undefined, () => ctx.get('schedule'));
  for (const endpoint of endpoints) {
    ctx.connection.fetch.register({
      path: `/api/anime-release/${endpoint}`, methods: ['POST'], requestBody: 'buffered',
      async fetch(request) {
        let envelope;
        try { envelope = await request.json(); } catch { return new Response('invalid JSON', { status: 400 }); }
        if (envelope?.type !== 'client-request' || typeof envelope.rpcId !== 'string'
          || !envelope.rpcId || envelope.rpcId.length > 200 || envelope.method !== `anime-release/${endpoint}`) {
          return new Response('invalid RPC envelope', { status: 400 });
        }
        // Connection's exact-route dispatcher admits owner Peers only, in both
        // HTTP and worker-local carriers. Never expose a parallel unauthenticated server.
        const result = await handle(endpoint, envelope.payload, request.signal,
          { principal: { kind: 'owner' }, signal: request.signal });
        return Response.json({ type: 'server-response', rpcId: envelope.rpcId, result });
      },
    });
  }
}
