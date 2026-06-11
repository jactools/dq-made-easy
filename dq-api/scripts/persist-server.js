const http = require("http");
const fs = require("fs");
const path = require("path");

const PORT = process.env.PORT || 4001;
const csvPath = path.resolve(
  __dirname,
  "..",
  "mock-data",
  "rule-attributes.csv",
);

function sendJson(res, status, obj) {
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  });
  res.end(JSON.stringify(obj));
}

const server = http.createServer((req, res) => {
  if (req.method === "OPTIONS") {
    // CORS preflight
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    });
    return res.end();
  }

  if (req.method === "POST" && req.url === "/persist-rule-attributes") {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      try {
        const json = JSON.parse(body || "{}");
        const entries = Array.isArray(json.entries) ? json.entries : [];
        if (!fs.existsSync(path.dirname(csvPath)))
          fs.mkdirSync(path.dirname(csvPath), { recursive: true });
        if (!fs.existsSync(csvPath))
          fs.writeFileSync(csvPath, "ruleId,attributeId\n");
        const lines = entries
          .map((e) => `${String(e.ruleId)},${String(e.attributeId)}\n`)
          .join("");
        fs.appendFileSync(csvPath, lines);
        return sendJson(res, 201, { added: entries.length });
      } catch (err) {
        return sendJson(res, 400, {
          error: String(err && err.message ? err.message : err),
        });
      }
    });
    return;
  }

  // simple status
  if (req.method === "GET" && req.url === "/") {
    return sendJson(res, 200, { status: "persist-server", csv: csvPath });
  }

  res.writeHead(404, { "Content-Type": "text/plain" });
  res.end("Not found");
});

server.listen(PORT, () =>
  console.log(`persist-server listening on http://localhost:${PORT}`),
);
