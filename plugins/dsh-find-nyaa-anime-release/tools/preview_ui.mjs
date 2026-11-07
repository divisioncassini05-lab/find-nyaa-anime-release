import http from 'node:http';
import { readFile } from 'node:fs/promises';
const files = new Map([['/', ['index.html', 'text/html; charset=utf-8']], ['/app.js', ['app.js', 'text/javascript; charset=utf-8']], ['/app.js.LEGAL.txt', ['app.js.LEGAL.txt', 'text/plain; charset=utf-8']]]);
const port = Number(process.env.PORT || 4319);
const server = http.createServer(async (req, res) => {
  const item = files.get(new URL(req.url, 'http://localhost').pathname);
  if (!item || !['GET', 'HEAD'].includes(req.method)) { res.writeHead(404); res.end(); return; }
  try {
    const data = await readFile(new URL('../.preview/' + item[0], import.meta.url));
    res.writeHead(200, {'Content-Type':item[1], 'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff'});
    res.end(req.method === 'HEAD' ? undefined : data);
  } catch { res.writeHead(503); res.end('Run npm run build first.'); }
});
server.listen(port, '127.0.0.1', () => console.log(`UI preview: http://127.0.0.1:${port}`));
