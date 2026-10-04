import { describe, expect, it } from "vitest";
import { failureSubtitle, lotLine, reviewSubtitle } from "~/presentation/decisions";
import { historyWhen } from "~/presentation/marketingHistory";
import { deviceLabel, fromB64url, nativeOptions, toB64url } from "~/utils/deviceSeal";
import type { DecisionItem } from "~/types/decisions";

// V6-MKT: as linhas da fila e do histórico na voz da v4, e a tradução do WebAuthn.
const TZ = "America/Sao_Paulo";
const NOW = Date.parse("2026-10-04T13:30:00Z"); // 10:30 em São Paulo

function item(overrides: Partial<DecisionItem> = {}): DecisionItem {
  return {
    ref: "review:41",
    kind: "review",
    announcement_id: 41,
    announcement_version: 1,
    campaign_name: "Lote pronto",
    trigger: "production_finished",
    product_name: "Croissant",
    image_url: "",
    lot_quantity: "24",
    lot_finished_at: "2026-10-04T13:01:00Z",
    delivered_platform_refs: [],
    delivered_people: 0,
    platform_refs: ["instagram", "whatsapp"],
    reach: { posts: 1, people: 86 },
    deadline_at: null,
    scheduled_for: null,
    created_at: "2026-10-04T13:02:00Z",
    failures: [],
    href: "/announcements/41#review",
    ...overrides,
  };
}

describe("o fato do lote no cartão de revisão", () => {
  it("diz quantas unidades saíram e quando, na voz do forno", () => {
    expect(lotLine(item(), TZ, NOW)).toBe("24 un saíram às 10:01");
    expect(lotLine(item({ lot_quantity: "2.5", lot_finished_at: null }), TZ, NOW)).toBe("2,5 un saíram");
    expect(lotLine(item({ lot_quantity: "" }), TZ, NOW)).toBe("");
  });

  it("junta o fato do lote ao destino, e sem lote cai no nome da campanha", () => {
    expect(reviewSubtitle(item(), TZ, NOW)).toMatch(/^24 un saíram às 10:01 · /);
    expect(reviewSubtitle(item({ lot_quantity: "" }), TZ, NOW)).not.toContain("saíram");
  });
});

describe("o cartão de falha conta o que já foi entregue", () => {
  it("nomeia o anúncio pela hora e soma quem recebeu", () => {
    const line = failureSubtitle(
      item({ kind: "retry_failed", delivered_platform_refs: ["facebook", "whatsapp"], delivered_people: 52 }),
      TZ,
    );
    expect(line).toMatch(/^Croissant das 10:01 · /);
    expect(line).toMatch(/entregues \(52\)$/);
  });

  it("sem nada entregue, fica só o anúncio", () => {
    expect(failureSubtitle(item({ kind: "retry_failed" }), TZ)).toBe("Croissant das 10:01");
  });
});

describe("o quando do histórico", () => {
  it("fala hoje, ontem e a data, sem travessão", () => {
    expect(historyWhen("2026-10-04T12:15:00Z", TZ, NOW)).toBe("hoje às 09:15");
    expect(historyWhen("2026-10-03T21:40:00Z", TZ, NOW)).toBe("ontem às 18:40");
    expect(historyWhen("2026-09-28T11:00:00Z", TZ, NOW)).toBe("28/09 às 08:00");
    expect(historyWhen("2025-12-20T11:00:00Z", TZ, NOW)).toBe("20/12/2025 às 08:00");
    expect(historyWhen("não é data", TZ, NOW)).toBe("");
  });
});

describe("a digital do dispositivo", () => {
  it("converte base64url nos dois sentidos sem perder byte", () => {
    const bytes = new Uint8Array([0, 250, 251, 252, 253, 254, 255, 62, 63]);
    const encoded = toB64url(bytes.buffer);
    expect(encoded).not.toMatch(/[+/=]/);
    expect(Array.from(fromB64url(encoded))).toEqual(Array.from(bytes));
  });

  it("entrega ao navegador o desafio e as credenciais como bytes", () => {
    const native = nativeOptions({
      challenge: "AAEC",
      allowCredentials: [{ id: "AAAA", type: "public-key" }],
    });
    expect(native.challenge).toBeInstanceOf(Uint8Array);
    const [credential] = native.allowCredentials as { id: Uint8Array }[];
    expect(credential.id).toBeInstanceOf(Uint8Array);
  });

  it("dá ao dispositivo o nome que a pessoa reconhece", () => {
    expect(deviceLabel("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0)")).toBe("iPhone");
    expect(deviceLabel("Mozilla/5.0 (Linux; Android 15; Pixel 9) Mobile")).toBe("Celular Android");
    expect(deviceLabel("Mozilla/5.0 (X11; Linux x86_64)")).toBe("Computador");
  });
});
