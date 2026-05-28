import { createServer, IncomingMessage, ServerResponse } from "node:http";
import { DatabaseSync } from "node:sqlite";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { z } from "zod";

const PORT = parseInt(process.env.PORT || "3000");
const HOST = process.env.HOST || "0.0.0.0";
const DB_PATH = process.env.DB_PATH || "data/db/docs.sqlite";

const db = new DatabaseSync(DB_PATH, { readOnly: true });

function createMcpServer() {
  const server = new McpServer({ name: "freewheel-docs", version: "1.0.0" });

  server.tool(
    "search_docs",
    "Search FreeWheel knowledge hub docs (FTS5 full-text search)",
    { query: z.string().describe("Search query"), limit: z.number().optional().default(5) },
    async ({ query, limit }) => {
      const rows = db.prepare(
        `SELECT p.page_id, p.title, p.url, p.file,
                snippet(pages_fts, 1, '>>>', '<<<', '...', 40) AS snippet, rank
         FROM pages_fts fts JOIN pages p ON fts.rowid = p.id
         WHERE pages_fts MATCH ? ORDER BY rank LIMIT ?`
      ).all(query, limit);
      return { content: [{ type: "text", text: JSON.stringify(rows, null, 2) }] };
    }
  );

  server.tool(
    "get_page",
    "Get full content of a doc page by page_id",
    { page_id: z.string().describe("Page ID (numeric, from index.json)") },
    async ({ page_id }) => {
      const row = db.prepare(
        "SELECT page_id, title, url, file, content FROM pages WHERE page_id = ?"
      ).get(page_id);
      if (!row) return { content: [{ type: "text", text: `Page ${page_id} not found` }] };
      return { content: [{ type: "text", text: JSON.stringify(row, null, 2) }] };
    }
  );

  return server;
}

const httpServer = createServer(async (req: IncomingMessage, res: ServerResponse) => {
  if (req.url === "/health" && req.method === "GET") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end('{"ok":true}');
    return;
  }

  if (req.url === "/mcp") {
    const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined });
    const mcp = createMcpServer();
    await mcp.connect(transport);

    if (req.method === "POST") {
      const chunks: Buffer[] = [];
      for await (const chunk of req) chunks.push(chunk);
      const body = JSON.parse(Buffer.concat(chunks).toString());
      await transport.handleRequest(req, res, body);
    } else {
      await transport.handleRequest(req, res);
    }
    return;
  }

  res.writeHead(404);
  res.end("Not Found");
});

httpServer.listen(PORT, HOST, () => {
  console.log(`MCP server listening on http://${HOST}:${PORT}`);
  console.log(`  /health → {ok:true}`);
  console.log(`  /mcp   → Streamable HTTP MCP`);
});
