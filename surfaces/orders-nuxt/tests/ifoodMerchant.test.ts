// A loja no iFood, ao vivo (homologação do módulo Merchant, DEV-2026-044): a resposta
// do topo, as pausas e o aviso do horário, puros.
import { describe, expect, it, vi } from "vitest";
import {
  checkLook,
  divergentDays,
  hoursAlert,
  merchantLine,
  pauseHint,
  pauseListingNote,
  pauseOrigin,
  pausePeriod,
  storeHeadline,
  tabFromQuery,
  visibleChecks,
} from "../app/presentation/ifoodMerchant";
import type {
  IFoodInterruptionRow,
  IFoodMerchantDetail,
  IFoodOpeningHours,
} from "../app/types/ifoodMerchant";

const detail = (over: Partial<IFoodMerchantDetail> = {}): IFoodMerchantDetail => ({
  enabled: true,
  merchant_id: "m",
  detail: [{ label: "Loja de teste", value: "Sim", code: "TEST", hint: "" }],
  detail_error: "",
  available: true,
  operations: [
    {
      operation: "Entrega",
      sales_channel: "App do iFood",
      available: true,
      state: "OK",
      state_label: "Aberta",
      title: "Loja aberta",
      description: "",
      checks: [],
    },
  ],
  status_error: "",
  checked_at_display: "21/11 11h",
  ...over,
});

const pause = (over: Partial<IFoodInterruptionRow> = {}): IFoodInterruptionRow => ({
  id: "p",
  description: "",
  starts_at_display: "21/11 11h",
  ends_at_display: "21/11 11h30",
  origin: "portal",
  origin_label: "Portal do Parceiro",
  in_effect: true,
  period_display: "Hoje, das 11h às 11h30",
  resume_display: "às 11h30",
  removable: true,
  listed_by_ifood: true,
  ...over,
});

const week = (over: Partial<IFoodOpeningHours> = {}): IFoodOpeningHours => ({
  enabled: true,
  days: [
    { day: "saturday", label: "Sábado", house: "10h às 19h", ifood: "9h às 18h", matches: false },
    { day: "monday", label: "Segunda", house: "9h às 18h", ifood: "9h às 18h", matches: true },
  ],
  matches: false,
  governs: true,
  error: "",
  checked_at_display: "11h",
  written_at_display: "",
  written_recently: false,
  ...over,
});

describe("a resposta do topo", () => {
  it("aberta: a resposta, sem texto cru do iFood", () => {
    expect(storeHeadline(detail())).toMatchObject({
      title: "O iFood está recebendo pedidos",
      tone: "success",
      badge: "Aberta",
      reason: "Aberta no iFood",
    });
  });
  it("fechada por pausa: diz quando volta", () => {
    const pausedChecks = [
      { code: "unavailabilities", label: "Pausas", state: "CLOSED", state_label: "Fechada", title: "Em Pausa programada", description: "" },
    ];
    const closed = detail({
      available: false,
      operations: [{ ...detail().operations[0]!, title: "Loja fechada", checks: pausedChecks }],
    });
    expect(storeHeadline(closed, [pause()])).toMatchObject({
      title: "O iFood não está recebendo pedidos",
      tone: "warning",
      reason: "Fechada por uma pausa (volta às 11h30)",
    });
    expect(visibleChecks(closed)).toEqual([]);
  });
  it("sem resposta do status, diz que não deu para saber", () => {
    expect(storeHeadline(detail({ status_error: "403" })).tone).toBe("neutral");
  });
  it("a loja do app numa linha, marcando a loja de teste", () => {
    const merchants = {
      enabled: true as const,
      error: "",
      merchants: [{ id: "m", name: "Teste - Nelson Boulangerie", corporate_name: "", is_current: true }],
    };
    expect(merchantLine(merchants, detail())).toBe("Teste - Nelson Boulangerie · loja de teste");
  });
  it("validação com ícone e cor, sem o id", () => {
    const base = { code: "x", label: "Pausas", state_label: "", title: "", description: "" };
    expect(checkLook({ ...base, state: "OK" }).tone).toBe("success");
    expect(checkLook({ ...base, state: "CLOSED" }).tone).toBe("warning");
    expect(checkLook({ ...base, state: "ERROR" }).tone).toBe("error");
  });
});

describe("pausas", () => {
  it("período, origem e como sai", () => {
    expect(pausePeriod(pause())).toBe("Hoje, das 11h às 11h30");
    expect(pauseOrigin(pause({ description: "Portal do Parceiro" }))).toBe("Portal do Parceiro");
    expect(pauseOrigin(pause({ description: "Reforma" }))).toBe("Portal do Parceiro: Reforma");
    expect(pauseHint(pause())).toBe("");
    expect(pauseHint(pause({ origin: "switch", removable: false }))).toContain("ligado de novo");
    expect(pauseHint(pause({ origin: "calendar", removable: false }))).toContain("calendário");
    expect(pauseListingNote(pause({ listed_by_ifood: false }))).toContain("ainda não a mostra");
  });
});

describe("aviso do horário", () => {
  it("diferente: aviso com a gravação pronta", () => {
    const write = vi.fn();
    const alert = hoursAlert(week(), write)!;
    expect(alert.color).toBe("warning");
    expect(alert.description).toContain("sábado");
    alert.action!.onSelect!(new Event("click"));
    expect(write).toHaveBeenCalled();
    expect(divergentDays(week())).toEqual(["Sábado"]);
  });
  it("gravado há pouco: espera o iFood mostrar, sem alarme", () => {
    const alert = hoursAlert(week({ written_recently: true, written_at_display: "às 13h40" }), () => {})!;
    expect(alert.color).toBe("info");
    expect(alert.title).toBe("Horário gravado no iFood às 13h40");
    expect(alert.action).toBeUndefined(); // nada a repetir: só o X
  });
  it("igual, sem grade ou sem resposta: nenhum aviso", () => {
    expect(hoursAlert(week({ matches: true }), () => {})).toBeNull();
    expect(hoursAlert(week({ governs: false }), () => {})).toBeNull();
    expect(hoursAlert(week({ error: "403" }), () => {})).toBeNull();
  });
});

describe("abas", () => {
  it("a aba vem da query, e o que não existe cai em Agora", () => {
    expect(tabFromQuery("hours")).toBe("hours");
    expect(tabFromQuery(["registry"])).toBe("registry");
    expect(tabFromQuery("qualquer")).toBe("now");
    expect(tabFromQuery(undefined)).toBe("now");
  });
});
