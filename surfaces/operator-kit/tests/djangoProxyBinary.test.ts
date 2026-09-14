import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { createApp, eventHandler, toNodeListener } from "h3";
import { ofetch } from "ofetch";
import { afterEach, expect, it, vi } from "vitest";
import { proxyDjangoPath } from "../server/utils/djangoProxy";

const servers: Server[] = [];
async function listen(server: Server) {
  servers.push(server);
  await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve));
  return `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
}
afterEach(async () => {
  await Promise.all(servers.splice(0).map(server => new Promise<void>(resolve => server.close(() => resolve()))));
  vi.unstubAllGlobals();
});

it("roundtrips authenticated evidence bytes through the canonical BFF as a private attachment", async () => {
  const bytes = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0, 0xff, 0x80, 0x0a]);
  let cookie = "";
  const upstream = await listen(createServer((req, res) => {
    cookie = req.headers.cookie || "";
    res.writeHead(200, { "content-type": "image/png", "content-disposition": 'attachment; filename="ifood-evidence.png"', "cache-control": "public, max-age=3600", "x-internal-secret": "private", "x-api-version": "1" });
    res.end(bytes);
  }));
  vi.stubGlobal("useRuntimeConfig", () => ({ djangoBaseUrl: upstream }));
  vi.stubGlobal("warnOnApiVersionMismatch", vi.fn());
  vi.stubGlobal("$fetch", ofetch);
  const app = createApp();
  app.use(eventHandler(event => proxyDjangoPath(event, "/api/v1/backstage/orders/IFOOD-1/ifood-handshake-evidence/")));
  const bff = await listen(createServer(toNodeListener(app)));
  const response = await fetch(`${bff}/?dispute_id=dispute-1&index=0`, {
    headers: {
      cookie: "sessionid=admin-direct; shopman_station_trust_pdv=station-1; shopman_operator_sessionid=isolated-test",
      accept: "text/html",
    },
  });
  expect(response.status).toBe(200);
  expect(Buffer.from(await response.arrayBuffer())).toEqual(bytes);
  expect(cookie).toBe("shopman_station_trust_pdv=station-1; sessionid=isolated-test");
  expect(cookie).not.toContain("admin-direct");
  expect(response.headers.get("content-type")).toBe("image/png");
  expect(response.headers.get("content-disposition")).toBe('attachment; filename="ifood-evidence.png"');
  expect(response.headers.get("cache-control")).toBe("private, no-store, max-age=0");
  expect(response.headers.get("x-content-type-options")).toBe("nosniff");
  expect(response.headers.get("x-internal-secret")).toBeNull();
});
