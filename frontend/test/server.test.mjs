import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { once } from 'node:events';
import { createServer } from '../server.mjs';

test('gateway forwards bearer only, preserves SSE/errors and blocks identity injection', async t => {
  let observed;
  const upstream = http.createServer((req, res) => {
    observed = req.headers;
    if (req.url.endsWith('/BAD')) { res.writeHead(404, { 'Content-Type': 'application/json' }); res.end('{"message":"订单不存在"}'); }
    else if (req.url.endsWith('/stream')) { res.writeHead(200, { 'Content-Type': 'text/event-stream' }); res.write('event: metadata\ndata: {}\n\n'); setTimeout(() => res.end('event: done\ndata: {}\n\n'), 20); }
    else { res.setHeader('Content-Type', 'application/json'); res.end('{}'); }
  }).listen(0, '127.0.0.1'); await once(upstream, 'listening');
  const app = createServer({ businessPort: upstream.address().port, agentPort: upstream.address().port }).listen(0, '127.0.0.1'); await once(app, 'listening');
  t.after(() => { app.closeAllConnections(); app.close(); upstream.closeAllConnections(); upstream.close(); });
  const url = `http://127.0.0.1:${app.address().port}`;
  let r = await fetch(url + '/api/v1/agent/chat/stream', { method: 'POST', headers: { Authorization: 'Bearer test-user-jwt', 'X-Tenant-Id': 'forged', 'X-User-Id': 'ATTACKER', 'X-Internal-Service-Token': 'must-not-forward' }, body: '{}' });
  assert.equal(r.status, 200); assert.match(await r.text(), /event: done/);
  assert.equal(observed.authorization, 'Bearer test-user-jwt');
  assert.equal(observed['x-user-id'], undefined); assert.equal(observed['x-tenant-id'], undefined); assert.equal(observed['x-internal-service-token'], undefined);
  assert.equal((await fetch(url + '/api/demo')).status, 404);
  assert.equal((await fetch(url + '/internal/v1/orders/A1001')).status, 404);
  r = await fetch(url + '/api/v1/auth/login', { method: 'POST', body: '{"username":"user","password":"test"}' }); assert.equal(r.status, 200);
  r = await fetch(url + '/api/v1/orders/BAD'); assert.equal(r.status, 404); assert.equal((await r.json()).message, '订单不存在');
  assert.equal((await fetch(url + '/api/v1/orders/A1001/refund-requests', { method: 'POST' })).status, 404);
  assert.equal((await fetch(url + '/api/v1/agent/threads', { method: 'POST', headers: { Origin: 'https://evil.example' } })).status, 403);
  assert.equal((await fetch(url + '/.env')).status, 404);
  r = await fetch(url + '/'); assert.equal(r.status, 200); assert.match(await r.text(), /售后服务助手/);
});
