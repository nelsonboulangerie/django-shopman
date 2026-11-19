// A pergunta que a Concierge levou à equipe sobe em degraus (dono, 19/11/2026): chega
// como a pílula invertida na base (assunto · até HHhMM, "Responder" e X); o X dispensa e
// ela volta no ritmo dos lembretes; só some de vez quando alguém responde ou assume (o
// aviso sai da fonte); vencido o prazo, a janela interrompe a tela.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";

import OperatorUrgentAlert from "../../app/components/OperatorUrgentAlert.vue";

vi.stubGlobal("useSonner", { success: vi.fn(), error: vi.fn() });

const NOW = Date.parse("2026-11-19T17:15:00Z");
const at = (minutes: number) => new Date(NOW + minutes * 60_000).toISOString();

function question(minutes: number, extra: Record<string, unknown> = {}) {
  return {
    key: 31,
    tone: "warning" as const,
    message: "“Amanhã tem croissant?”",
    canAck: true,
    origin: "WhatsApp",
    originIcon: "i-lucide-message-circle",
    subject: "Ana espera a resposta da equipe",
    respondByIso: at(minutes),
    deadlineKind: "house" as const,
    answer: { label: "Responder ao cliente", placeholder: "Escreva a resposta", maxLength: 300, altLabel: "Assumir a conversa" },
    ...extra,
  };
}

describe("OperatorUrgentAlert · a pergunta que espera resposta", () => {
  let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;
  afterEach(() => {
    mounted?.unmount();
    mounted = null;
    useOperatorInboxAlerts().value = null;
    vi.useRealTimers();
  });
  const pill = () => document.querySelector("[data-operator-answer-pill]");
  const dialog = () => document.querySelector("[role=dialog]");

  async function mount(minutes: number, extra: Record<string, unknown> = {}) {
    vi.useFakeTimers({ now: NOW, toFake: ["Date"] });
    useOperatorInboxAlerts().value = { items: [question(minutes, extra)], count: 1, ack: vi.fn(), answer: vi.fn() };
    mounted = await mountSuspended(OperatorUrgentAlert, { attachTo: document.body });
    await nextTick();
  }

  it("chega como a pílula, sem janela: assunto, até que horas, Responder e X", async () => {
    await mount(7);
    expect(dialog()).toBeNull();
    expect(pill()!.textContent).toContain("Ana espera a resposta da equipe");
    expect(pill()!.textContent).toMatch(/até \d{1,2}h(\d{2})?/);
    expect(pill()!.querySelector("[data-operator-answer-pill-open]")!.textContent).toContain("Responder");
    expect(pill()!.querySelector("[data-operator-answer-pill-close]")).not.toBeNull();
    expect(useAnswerPillShown().value).toBe(true);
  });

  it("o X dispensa, e ela volta no ritmo dos lembretes enquanto ninguém responde", async () => {
    await mount(8);
    pill()!.querySelector<HTMLButtonElement>("[data-operator-answer-pill-close]")!.click();
    await nextTick();
    expect(pill()).toBeNull();
    expect(useAnswerPillShown().value).toBe(false);
    // Faltam 8 min: volta em 2 min (um quarto do que falta).
    vi.setSystemTime(NOW + 2 * 60_000 + 1_000);
    await vi.waitFor(() => expect(pill()).not.toBeNull(), { timeout: 3000 });
  });

  it("Responder abre a janela com o campo; quem responde tira a pergunta da fonte e tudo some", async () => {
    await mount(7);
    pill()!.querySelector<HTMLButtonElement>("[data-operator-answer-pill-open]")!.click();
    await vi.waitFor(() => expect(dialog()).not.toBeNull());
    expect(dialog()!.querySelector("[data-operator-inbox-answer]")).not.toBeNull();
    expect(pill()).toBeNull();
    useOperatorInboxAlerts().value = { items: [], count: 0, ack: vi.fn(), answer: vi.fn() };
    await vi.waitFor(() => expect(dialog()).toBeNull());
    expect(pill()).toBeNull();
  });

  it("vencido o prazo, a janela interrompe a tela", async () => {
    await mount(-1);
    await vi.waitFor(() => expect(dialog()).not.toBeNull());
    expect(dialog()!.textContent).toContain("Passou do prazo");
  });
});
