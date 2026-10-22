// Headless test of the Cutting Room Inbox upload path, using the page's own code.
//
//   node scripts/test_inbox_upload.mjs <file> <out-dir>
//
// Serves ui/edit-inbox.html with a stand-in `window.claude` whose `assets.upload` and
// `db.add` post to this script, picks <file> through the page's file input, queues the job
// with the real form, and writes what the page produced to <out-dir>:
//   pieces/<n>.bin   every piece exactly as the page would upload it
//   job.json         the job document the page would add (piece ids = local names)
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_PATH || "playwright");

const [file, out] = process.argv.slice(2);
if (!file || !out) { console.error("usage: test_inbox_upload.mjs <file> <out-dir>"); process.exit(1); }
const page = fs.readFileSync(new URL("../ui/edit-inbox.html", import.meta.url), "utf8");
fs.mkdirSync(path.join(out, "pieces"), { recursive: true });

let n = 0, job = null;
const server = http.createServer((req, res) => {
  if (req.method === "GET") { res.writeHead(200, { "content-type": "text/html" }); res.end(`<!doctype html><html><head><meta charset="utf-8"></head><body>${page}</body></html>`); return; }
  const chunks = [];
  req.on("data", (c) => chunks.push(c));
  req.on("end", () => {
    const body = Buffer.concat(chunks);
    if (req.url === "/piece") {
      const id = `piece-${String(n++).padStart(4, "0")}`;
      fs.writeFileSync(path.join(out, "pieces", id + ".bin"), body);
      res.end(JSON.stringify({ id, type: req.headers["content-type"] }));
    } else if (req.url === "/job") { job = JSON.parse(body); fs.writeFileSync(path.join(out, "job.json"), JSON.stringify(job, null, 1)); res.end('{"id":"local-job"}'); }
    else { res.writeHead(404); res.end(); }
  });
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}`;

const browser = await chromium.launch();
const ctx = await browser.newContext();
await ctx.addInitScript(() => {
  const empty = { onSnapshot: (cb) => { cb({ docs: [] }); return () => {}; } };
  const query = { orderBy: () => ({ limit: () => empty }), add: async (doc) => { const r = await fetch("/job", { method: "POST", body: JSON.stringify(doc) }); return r.json(); } };
  const caps = {
    db: { collection: () => query },
    assets: {
      upload: async (blob, opts) => { const r = await fetch("/piece", { method: "POST", body: blob, headers: { "content-type": (opts && opts.type) || blob.type } }); return r.json(); },
      list: async () => ({ assets: [], usage: { files: 0, bytes: 0, maxBytes: 1073741824, maxFiles: 5000 } }),
      delete: async () => ({ deleted: true }),
    },
  };
  window.claude = { use: async (name) => caps[name] || null };
});
const tab = await ctx.newPage();
tab.on("pageerror", (e) => console.error("page error:", e.message));
await tab.goto(base);
await tab.click("#tabUpload");
const t0 = Date.now();
await tab.setInputFiles("#picker", file);
await tab.waitForFunction(() => /✓/.test(document.getElementById("files").textContent), null, { timeout: 30 * 60 * 1000, polling: 500 });
const secs = ((Date.now() - t0) / 1000).toFixed(1);
await tab.fill("#name", "Upload path test");
await tab.fill("#brief", "End-to-end test of the upload route with a >500 MB .mov.");
await tab.click("#submit");
await tab.waitForFunction(() => /Queued/.test(document.getElementById("formMsg").textContent), null, { timeout: 30000 });
const msg = await tab.textContent("#formMsg");
await browser.close(); server.close();
console.log(JSON.stringify({ pieces: n, seconds: Number(secs), formMsg: msg, files: job && job.files.map((f) => ({ name: f.name, size: f.size, pieceSize: f.pieceSize, chunks: f.chunks.length })) }));
