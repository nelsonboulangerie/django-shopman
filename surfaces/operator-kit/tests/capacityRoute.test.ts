// GET /health/capacity: só operador identificado (quem decide é o Django),
// sem cache, sem número inventado; e o que vai ao Django sai deste processo.
import { IncomingMessage, ServerResponse } from "node:http";
import { Socket } from "node:net";
import { createEvent, type H3Event } from "h3";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  capacityReportBody,
  reportCapacityToDjango,
  resolveOperatorServiceName,
} from "../server/utils/capacityReport";
import { handleCapacityRequest } from "../server/utils/capacityRoute";
import type { ContainerCapacityReading } from "../server/utils/containerCapacity";

const DJANGO = "http://django.internal:8000";
const THRESHOLDS = { attention_percent: 75, critical_percent: 90, sustain_minutes: 5 };

const READING: ContainerCapacityReading = {
  available: true,
  source: "cgroup-v2",
  memory: { used_bytes: 330_000_000, limit_bytes: 536_870_912, percent: 61.5 },
  cpu: { percent: 18.2, limit_cores: 1, window_ms: 30_000 },
  measured_at: "2026-09-17T15:00:00.000Z",
};

const NO_CGROUP: ContainerCapacityReading = {
  available: false,
  source: "none",
  memory: null,
  cpu: null,
  measured_at: "2026-09-17T15:00:00.000Z",
};

function makeEvent(headers: Record<string, string> = {}): { event: H3Event; res: ServerResponse } {
  const request = new IncomingMessage(new Socket());
  request.method = "GET";
  request.url = "/health/capacity";
  request.headers = headers;
  const response = new ServerResponse(request);
  return { event: createEvent(request, response), res: response };
}

beforeEach(() => {
  vi.stubGlobal("useRuntimeConfig", () => ({
    djangoBaseUrl: DJANGO,
    djangoProxySecret: "",
    operatorServiceName: "",
    public: { operatorPwa: { app: "pos" } },
  }));
});

describe("handleCapacityRequest", () => {
  it("operador identificado: leitura + limites do Admin, privada e sem cache", async () => {
    const { event, res } = makeEvent();
    const report = vi.fn().mockResolvedValue({
      status: 200,
      data: { service: "pos", level: "normal", recorded: true, thresholds: THRESHOLDS },
    });

    const body = await handleCapacityRequest(event, { read: async () => READING, report });

    expect(report).toHaveBeenCalledWith(event, "pos", READING);
    expect(body).toEqual({
      service: "pos",
      available: true,
      source: "cgroup-v2",
      memory: READING.memory,
      cpu: READING.cpu,
      measured_at: READING.measured_at,
      level: "normal",
      thresholds: THRESHOLDS,
    });
    expect(String(res.getHeader("cache-control"))).toContain("no-store");
    expect(res.statusCode).toBe(200);
  });

  it("sessão caída: 403 com o código do Django, e nenhum número", async () => {
    const { event, res } = makeEvent();
    const report = vi.fn().mockResolvedValue({
      status: 403,
      data: { detail: "As credenciais não foram fornecidas.", error: { code: "not_authenticated" } },
    });

    const body = await handleCapacityRequest(event, { read: async () => READING, report });

    expect(res.statusCode).toBe(403);
    expect(body).toEqual({
      detail: "As credenciais não foram fornecidas.",
      error: { code: "not_authenticated" },
    });
    expect(JSON.stringify(body)).not.toContain("61.5");
  });

  it("Django fora do ar: 502 sem leitura (não há quem confirme o operador)", async () => {
    const { event, res } = makeEvent();
    const report = vi.fn().mockRejectedValue(new Error("ECONNREFUSED"));

    const body = await handleCapacityRequest(event, { read: async () => READING, report });

    expect(res.statusCode).toBe(502);
    expect(body).toEqual({ detail: "Não foi possível conferir o acesso agora." });
  });

  it("resposta inesperada do Django vira 502 sem vazar o corpo", async () => {
    const { event, res } = makeEvent();
    const report = vi.fn().mockResolvedValue({ status: 500, data: { error: { code: "boom", trace: "x" } } });

    const body = await handleCapacityRequest(event, { read: async () => READING, report });

    expect(res.statusCode).toBe(502);
    expect(body).toEqual({ detail: "Leitura de capacidade indisponível." });
  });

  it("sem cgroup: available false, sem número — e ainda assim autenticado pelo Django", async () => {
    const { event, res } = makeEvent();
    const report = vi.fn().mockResolvedValue({
      status: 200,
      data: { level: "unknown", recorded: false, thresholds: THRESHOLDS },
    });

    const body = await handleCapacityRequest(event, { read: async () => NO_CGROUP, report });

    expect(res.statusCode).toBe(200);
    expect(body).toMatchObject({ available: false, source: "none", memory: null, cpu: null, level: "unknown", thresholds: THRESHOLDS });
  });
});

describe("reportCapacityToDjango", () => {
  it("manda a amostra com o cookie do operador traduzido, CSRF e Origin do Django", async () => {
    const raw = vi.fn().mockResolvedValue({ status: 200, _data: { thresholds: THRESHOLDS } });
    vi.stubGlobal("$fetch", Object.assign(vi.fn(), { raw }));
    const { event } = makeEvent({
      cookie: "sessionid=admin-crua; shopman_operator_sessionid=op-123; shopman_operator_csrftoken=tok%2B1",
      "x-forwarded-for": "203.0.113.9",
    });

    const result = await reportCapacityToDjango(event, "operator-floor", READING);

    expect(result).toEqual({ status: 200, data: { thresholds: THRESHOLDS } });
    const [url, options] = raw.mock.calls[0]!;
    expect(url).toBe(`${DJANGO}/api/v1/backstage/operator/capacity/`);
    expect(options.method).toBe("POST");
    expect(options.body).toEqual({
      service: "operator-floor",
      available: true,
      memory_percent: 61.5,
      cpu_percent: 18.2,
    });
    // O cookie cru do Admin morre na porta; o do operador vira o nome que o Django conhece.
    expect(options.headers.cookie).toBe("sessionid=op-123; csrftoken=tok%2B1");
    expect(options.headers["x-csrftoken"]).toBe("tok+1");
    expect(options.headers.origin).toBe(DJANGO);
    expect(options.headers["x-forwarded-for"]).toBe("203.0.113.9");
    expect(options.headers["x-shopman-proxy-secret"]).toBeUndefined();
  });

  it("sem leitura, o corpo não carrega percentual", () => {
    expect(capacityReportBody("pos", { ...READING, available: false })).toEqual({
      service: "pos",
      available: false,
      memory_percent: null,
      cpu_percent: null,
    });
  });
});

describe("resolveOperatorServiceName", () => {
  it("o deploy nomeia o serviço quando vários apps dividem o contêiner", () => {
    expect(resolveOperatorServiceName({ operatorServiceName: "operator-floor", public: { operatorPwa: { app: "pos" } } }))
      .toBe("operator-floor");
  });

  it("sem a env vale a identidade do app; lixo nunca é repassado", () => {
    expect(resolveOperatorServiceName({ operatorServiceName: "", public: { operatorPwa: { app: "kds" } } })).toBe("kds");
    expect(resolveOperatorServiceName({ operatorServiceName: "../etc passwd", public: { operatorPwa: { app: "kds" } } }))
      .toBe("kds");
    expect(resolveOperatorServiceName({})).toBe("operator");
  });
});
