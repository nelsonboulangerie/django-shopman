// "Avisos": uma caixa, um item, um selo (V6-KIT, K01/T-01/K05).
//
// As promessas que o dono cobrou continuam aqui, e vieram do sino da caixa pessoal:
// (1) NÃO INTERROMPE, nada aparece por cima de quem está atendendo até alguém tocar;
// (2) REALCE, NUNCA SILO, o suspeito fica na mesma lista, marcado. As novas: os alertas
// da operação moram no MESMO painel (outra aba), com um selo somado, o "Visto" e o
// lugar exato; a capacidade do serviço entra na caixa quando passa do limite; e o
// painel abre num portal, com a cor do popover (o título não some no creme do rail).
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";

import OperatorInbox from "../../app/components/OperatorInbox.vue";
import type { CapacityResponse } from "../../app/types/capacity";

const ROTINA = {
  pk: 1,
  category: "sign_in" as const,
  title: "Sua conta foi usada (PIN)",
  message: "29/08 às 09:12 · pdv-main",
  action_url: "/account/sign-ins",
  action_data: { sign_in_event_id: 1, anomalies: [], highlight: false },
  is_actionable: true,
  is_read: false,
  created_at: "2026-08-29T09:12:00Z",
  created_at_display: "29/08 às 09:12",
};

const SUSPEITO = {
  ...ROTINA,
  pk: 2,
  title: "Sua conta foi usada (crachá)",
  message: "29/08 às 03:40 · pdv-main\nAtenção: entrou com crachá.",
  action_data: { sign_in_event_id: 2, anomalies: ["badge"], highlight: true },
};

const items = ref<unknown[]>([]);
const unread = ref(0);
const signIns = ref<unknown[]>([]);
const markRead = vi.fn();
const loadSignIns = vi.fn();

vi.mock("../../app/composables/useNotifications", () => ({
  useNotifications: () => ({
    items,
    unread,
    loading: ref(false),
    error: ref(""),
    signInError: ref(""),
    refresh: vi.fn(),
    markRead,
    signIns,
    loadSignIns,
    realtime: ref("live"),
  }),
}));

const reading = ref<CapacityResponse | null>(null);
const authorized = ref(false);
vi.mock("../../app/composables/useOperatorCapacity", () => ({
  useOperatorCapacity: () => ({ reading, authorized, stale: ref(false), refresh: vi.fn() }),
}));

function capacity(percent: number): CapacityResponse {
  return {
    service: "orders",
    available: true,
    source: "cgroup-v2",
    memory: { used_bytes: 1, limit_bytes: 2, percent },
    cpu: { percent: 10, limit_cores: 1, window_ms: 30_000 },
    measured_at: new Date().toISOString(),
    level: "normal",
    thresholds: { attention_percent: 75, critical_percent: 90, sustain_minutes: 5 },
  };
}

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;
const mount = async (placement: "header" | "rail" = "header") =>
  (mounted = await mountSuspended(OperatorInbox, {
    props: { placement },
    global: { stubs: { Icon: true } },
    attachTo: document.body,
  }));
const panel = () => document.querySelector<HTMLElement>("[data-operator-inbox-panel]");
async function openPanel() {
  await mounted!.get("[data-operator-inbox-trigger]").trigger("click");
  await nextTick();
}
function click(selector: string) {
  document.querySelector<HTMLElement>(selector)!.click();
  return nextTick();
}
function clickButton(label: string) {
  const button = [...document.querySelectorAll<HTMLButtonElement>("button")].find((item) => item.textContent?.includes(label));
  button!.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, button: 0 }));
  button!.click();
  return nextTick();
}

describe("OperatorInbox", () => {
  beforeEach(() => {
    items.value = [];
    unread.value = 0;
    signIns.value = [];
    reading.value = null;
    authorized.value = false;
    markRead.mockReset();
    loadSignIns.mockReset();
    useOperatorInboxAlerts().value = null;
  });

  afterEach(() => {
    mounted?.unmount();
    mounted = null;
    useOperatorInboxAlerts().value = null;
  });

  it("NÃO interrompe: nada de painel aberto sem alguém pedir", async () => {
    items.value = [SUSPEITO];
    unread.value = 1;
    await mount();
    expect(panel()).toBeNull();
  });

  it("um item só, chamado Avisos, com o selo somando alertas e não lidos", async () => {
    unread.value = 2;
    useOperatorInboxAlerts().value = { items: [], count: 3 };
    await mount("rail");
    const trigger = mounted!.get("[data-operator-inbox-trigger]");
    expect(trigger.attributes("aria-label")).toBe("Avisos (5 pedem sua atenção)");
  });

  it("o contador some quando não há nada", async () => {
    await mount();
    expect(mounted!.get("[data-operator-inbox-trigger]").attributes("aria-label")).toBe("Avisos");
    unread.value = 3;
    await nextTick();
    expect(mounted!.get("[data-operator-inbox-trigger]").attributes("aria-label")).toBe("Avisos (3 pedem sua atenção)");
  });

  it("o painel abre num portal, com a cor do popover e o título visível (K05)", async () => {
    await mount("rail");
    await openPanel();
    const node = panel()!;
    expect(mounted!.element.contains(node)).toBe(false);
    expect(node.closest("[data-reka-popper-content-wrapper]")).not.toBeNull();
    expect(node.querySelector("h2")?.textContent).toBe("Avisos");
  });

  it("alertas da operação e caixa pessoal no MESMO painel, em duas abas", async () => {
    const ack = vi.fn();
    items.value = [ROTINA];
    unread.value = 1;
    useOperatorInboxAlerts().value = {
      items: [
        { key: 7, tone: "critical", eyebrow: "Crítico · Pagamento", message: "Pix do W07 falhou", meta: "21:55 · pedido W07", canAck: true, href: "/W07", hrefLabel: "Abrir o pedido" },
      ],
      count: 1,
      ack,
    };
    await mount();
    await openPanel();
    const alert = document.querySelector<HTMLElement>("[data-operator-inbox-alert]")!;
    expect(alert.textContent).toContain("Pix do W07 falhou");
    expect(alert.querySelector("a")?.getAttribute("href")).toBe("/W07");
    await click("[data-alert-ack]");
    expect(ack).toHaveBeenCalledWith(7);
    await clickButton("Para você");
    expect(document.querySelectorAll("[data-notification-item]")).toHaveLength(1);
  });

  it("sem fonte de alertas, a caixa é só a pessoal (sem abas)", async () => {
    items.value = [ROTINA];
    await mount();
    await openPanel();
    expect(document.querySelector("[data-operator-inbox-tab]")).toBeNull();
    expect(document.querySelectorAll("[data-notification-item]")).toHaveLength(1);
  });

  it("a capacidade acima do crítico entra na caixa e conta no selo", async () => {
    authorized.value = true;
    reading.value = capacity(95);
    await mount();
    expect(mounted!.get("[data-operator-inbox-trigger]").attributes("aria-label")).toBe("Avisos (1 pede sua atenção)");
    await openPanel();
    const item = document.querySelector<HTMLElement>("[data-operator-inbox-capacity]")!;
    expect(item.textContent).toContain("Capacidade do serviço · Crítica");
    expect(item.textContent).toContain("Memória 95%");
  });

  it("capacidade normal não aparece na caixa (mora no menu do operador)", async () => {
    authorized.value = true;
    reading.value = capacity(40);
    items.value = [ROTINA];
    await mount();
    await openPanel();
    expect(document.querySelector("[data-operator-inbox-capacity]")).toBeNull();
  });

  it("REALCE, NUNCA SILO: rotina e suspeito na MESMA lista", async () => {
    items.value = [ROTINA, SUSPEITO];
    unread.value = 2;
    await mount();
    await openPanel();
    const linhas = document.querySelectorAll<HTMLElement>("[data-notification-item]");
    expect(linhas).toHaveLength(2);
    expect(linhas[0]!.dataset.highlight).toBeUndefined();
    expect(linhas[1]!.dataset.highlight).toBe("true");
    expect(panel()!.textContent).toContain("entrou com crachá");
  });

  it("caixa vazia diz que está vazia", async () => {
    await mount();
    await openPanel();
    expect(panel()!.textContent).toContain("Nada por aqui");
  });

  it("marcar como lida não navega para lugar nenhum", async () => {
    items.value = [ROTINA];
    await mount();
    await openPanel();
    [...document.querySelectorAll<HTMLButtonElement>("[data-operator-inbox-panel] button")]
      .find((b) => b.textContent?.trim() === "Marcar como lida")!
      .click();
    expect(markRead).toHaveBeenCalledWith(1);
  });

  it("'Meus acessos' abre o log no MESMO painel, sem mandar para outro domínio", async () => {
    items.value = [ROTINA];
    signIns.value = [
      {
        pk: 9,
        method: "badge",
        method_display: "crachá",
        outcome: "success",
        outcome_display: "entrou",
        station_ref: "pdv-main",
        station_display: "pdv-main",
        ip_address: "",
        created_at: "",
        created_at_display: "29/08 às 06:12",
        anomalies: ["badge"],
        anomaly_labels: ["entrou com crachá"],
        highlight: true,
      },
    ];
    await mount();
    await openPanel();
    await click("[data-see-sign-ins]");
    await nextTick();
    expect(loadSignIns).toHaveBeenCalled();
    const linhas = document.querySelectorAll<HTMLElement>("[data-sign-in-item]");
    expect(linhas).toHaveLength(1);
    expect(linhas[0]!.dataset.highlight).toBe("true");
    expect(panel()!.textContent).toContain("crachá · pdv-main");
    expect(panel()!.querySelectorAll("a")).toHaveLength(0);
  });
});
