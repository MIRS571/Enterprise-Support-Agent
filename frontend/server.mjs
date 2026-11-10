import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const root = new URL('./public/', import.meta.url);
const files = new Map([['/', ['index.html', 'text/html']], ['/app.js', ['app.js', 'text/javascript']], ['/state.js', ['state.js', 'text/javascript']], ['/sse.js', ['sse.js', 'text/javascript']], ['/style.css', ['style.css', 'text/css']]]);

export function createServer({ businessPort = 8080, agentPort = 8000 } = {}) {
  return http.createServer(async (req, res) => {
    const host = req.headers.host || '';
    if (!/^(127\.0\.0\.1|localhost)(:\d+)?$/.test(host)) {
      res.writeHead(403).end('Local demo only'); return;
    }
    if (req.headers.origin && ![`http://${host}`].includes(req.headers.origin)) {
      res.writeHead(403).end('Cross-origin request rejected'); return;
    }
    if (req.headers['sec-fetch-site'] === 'cross-site') { res.writeHead(403).end(); return; }
    const path = (req.url || '/').split('?')[0];
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'");
    const isAuthWrite = path === '/api/v1/auth/login' || path === '/api/v1/auth/logout';
    const isThread = path === '/api/v1/agent/threads' || path === '/api/v1/agent/chat/stream' || /^\/api\/v1\/agent\/threads\/[a-zA-Z0-9_-]{1,128}\/resume$/.test(path);
    const isRead = path === '/api/v1/auth/me' || path === '/api/v1/system/info' || /^\/api\/v1\/orders\/[a-zA-Z0-9_-]{1,64}$/.test(path);
    const health = path === '/api/agent-health';
    if (((isThread || isAuthWrite) && req.method === 'POST') || ((isRead || health) && req.method === 'GET')) {
      // No user/tenant/internal identity headers are accepted from the browser.
      const headers = { 'Accept': req.headers.accept || 'application/json', 'Content-Type': 'application/json' };
      if (req.headers.authorization && !health) headers.Authorization = req.headers.authorization;
      if (req.headers['idempotency-key']) headers['Idempotency-Key'] = req.headers['idempotency-key'];
      const upstream = http.request({ hostname: '127.0.0.1', port: health ? agentPort : businessPort, path: health ? '/api/v1/health' : path, method: req.method, headers }, response => {
        res.writeHead(response.statusCode, { 'Content-Type': response.headers['content-type'] || 'application/json', 'Cache-Control': 'no-cache, no-transform', 'X-Accel-Buffering': 'no' });
        response.on('error', () => res.destroy());
        response.pipe(res);
      });
      upstream.setTimeout(120000, () => upstream.destroy(new Error('Upstream timeout')));
      upstream.on('error', () => {
        if (res.headersSent) res.destroy();
        else { res.writeHead(502, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ message: '服务连接失败或超时，请检查 Java / Python 是否启动。' })); }
      });
      res.on('close', () => upstream.destroy());
      let size = 0;
      req.on('data', chunk => { size += chunk.length; if (size > 32768) { upstream.destroy(); req.destroy(); } });
      req.pipe(upstream); return;
    }
    const file = files.get(path);
    if (req.method !== 'GET' || !file) { res.writeHead(404).end('Not found'); return; }
    try { const data = await readFile(new URL(file[0], root)); res.setHeader('Content-Type', `${file[1]}; charset=utf-8`); res.end(data); }
    catch { res.writeHead(500).end('Could not load page'); }
  });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const port = Number(process.env.FRONTEND_PORT || 5175);
  createServer().listen(port, '127.0.0.1', () => console.log(`Support Agent demo: http://127.0.0.1:${port}`));
}
