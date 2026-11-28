// O prazo do Pix pendente é o do servidor (`payment.expires_at`); a constante
// só vale para o Pix que chegou sem prazo dito.
import { describe, expect, it } from "vitest";

import {
  PENDING_PIX_FALLBACK_MAX_AGE_MS,
  PENDING_PIX_GRACE_MS,
  pendingPixDeadlineMs,
  pendingPixExpired,
} from "../app/utils/pendingPixStore";

const since = "2026-10-23T12:00:00.000Z";
const t0 = Date.parse(since);

describe("pendingPixStore — prazo", () => {
  it("com expires_at, desiste no prazo do servidor mais a folga do aviso do banco", () => {
    const entry = { orderRef: "PED-1", since, expiresAt: "2026-10-23T12:30:00.000Z" };
    expect(pendingPixDeadlineMs(entry)).toBe(t0 + 30 * 60 * 1000 + PENDING_PIX_GRACE_MS);
    expect(pendingPixExpired(entry, t0 + 20 * 60 * 1000)).toBe(false);
    expect(pendingPixExpired(entry, t0 + 31 * 60 * 1000)).toBe(true);
  });

  it("um prazo CURTO também vale: não espera os 10 minutos", () => {
    const entry = { orderRef: "PED-1", since, expiresAt: "2026-10-23T12:02:00.000Z" };
    expect(pendingPixExpired(entry, t0 + 4 * 60 * 1000)).toBe(true);
  });

  it("sem expires_at, o teto de reserva conta da cobrança", () => {
    const entry = { orderRef: "PED-1", since };
    expect(pendingPixDeadlineMs(entry)).toBe(t0 + PENDING_PIX_FALLBACK_MAX_AGE_MS);
  });
});
