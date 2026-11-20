// A pergunta que a Concierge levou à equipe sobe em degraus (dono, 19/11/2026): chega
// como aviso de tela no topo (`OperatorPageHeader`), cujo "Responder" abre esta janela
// com o campo; ela só interrompe a tela sozinha quando o prazo vence.
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
  const dialog = () => document.querySelector("[role=dialog]");

  async function mount(minutes: number, extra: Record<string, unknown> = {}) {
    vi.useFakeTimers({ now: NOW, toFake: ["Date"] });
    useOperatorInboxAlerts().value = { items: [question(minutes, extra)], count: 1, ack: vi.fn(), answer: vi.fn() };
    mounted = await mountSuspended(OperatorUrgentAlert, { attachTo: document.body });
    await nextTick();
  }

  it("com o prazo correndo, não interrompe a tela", async () => {
    await mount(7);
    expect(dialog()).toBeNull();
  });

  it("o Responder do aviso abre a janela com o campo; fecha sem responder, e quem responde tira tudo", async () => {
    await mount(7);
    useAnswerWindowRequest().value = 31;
    await vi.waitFor(() => expect(dialog()).not.toBeNull());
    expect(dialog()!.querySelector("[data-operator-inbox-answer]")).not.toBeNull();
    dialog()!.querySelector<HTMLButtonElement>("[data-operator-urgent-close]")!.click();
    await vi.waitFor(() => expect(dialog()).toBeNull());
    expect(useAnswerWindowRequest().value).toBeNull();
    useAnswerWindowRequest().value = 31;
    await vi.waitFor(() => expect(dialog()).not.toBeNull());
    useOperatorInboxAlerts().value = { items: [], count: 0, ack: vi.fn(), answer: vi.fn() };
    await vi.waitFor(() => expect(dialog()).toBeNull());
    useAnswerWindowRequest().value = null;
  });

  it("vencido o prazo, a janela interrompe a tela", async () => {
    await mount(-1);
    await vi.waitFor(() => expect(dialog()).not.toBeNull());
    expect(dialog()!.textContent).toContain("Passou do prazo");
  });
});
