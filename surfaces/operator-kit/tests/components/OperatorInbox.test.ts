// "Avisos": uma caixa, um item, um selo (V6-KIT, K01/T-01/K05).
//
// As promessas que o dono cobrou continuam aqui, e vieram do sino da caixa pessoal:
// (1) NÃO INTERROMPE, nada aparece por cima de quem está atendendo até alguém tocar;
// (2) REALCE, NUNCA SILO, o suspeito fica na mesma lista, marcado. As novas: os alertas
// da operação moram no MESMO painel (outra aba), com um selo somado, o "Visto" e o
// lugar exato; a capacidade do serviço entra na caixa quando passa do limite; e o
// painel abre num portal, com a cor do popover (o título não some no creme do rail).
import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";
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
const settled = ref(true);
const signIns = ref<unknown[]>([]);
const markRead = vi.fn();
const loadSignIns = vi.fn();
const { markAllRead, notMe, confirmAnswer } = vi.hoisted(() => ({
  markAllRead: vi.fn(),
  notMe: vi.fn(),
  confirmAnswer: vi.fn(),
}));
mockNuxtImport("useConfirm", () => () => confirmAnswer);
// O toast é do app hospedeiro (o kit não o declara fora do catálogo).
const sonner = { success: vi.fn(), error: vi.fn() };
vi.stubGlobal("useSonner", sonner);

vi.mock("../../app/composables/useNotifications", () => ({
  useNotifications: () => ({
    items,
    unread,
    settled,
    loading: ref(false),
    error: ref(""),
    signInError: ref(""),
    refresh: vi.fn(),
    markRead,
    markAllRead,
    notMe,
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
    settled.value = true;
    signIns.value = [];
    reading.value = null;
    authorized.value = false;
    markRead.mockReset();
    loadSignIns.mockReset();
    markAllRead.mockReset();
    notMe.mockReset();
    confirmAnswer.mockReset();
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

  // Beta 05/11 (MKT-22): o selo pintava "1" (a operação) e logo "9+" (com a caixa pessoal).
  it("antes da primeira leitura da caixa pessoal, o selo não pinta número", async () => {
    settled.value = false;
    unread.value = 28;
    useOperatorInboxAlerts().value = { items: [], count: 1 };
    await mount("rail");
    const trigger = () => mounted!.get("[data-operator-inbox-trigger]");
    expect(trigger().attributes("aria-label")).toBe("Avisos");
    settled.value = true;
    await nextTick();
    expect(trigger().attributes("aria-label")).toBe("Avisos (29 pedem sua atenção)");
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

  it("o gesto que resolve ali mesmo (P2-19: Aceitar) é o botão cheio, e o Abrir vira contorno", async () => {
    const act = vi.fn();
    useOperatorInboxAlerts().value = {
      items: [
        {
          key: 9, tone: "warning", eyebrow: "Aviso · Pedido parado", message: "O pedido W09 espera aceite.",
          meta: "21:55 · pedido W09", canAck: true, href: "/W09", hrefLabel: "Abrir o pedido", actLabel: "Aceitar",
        },
      ],
      count: 1,
      ack: vi.fn(),
      act,
    };
    await mount();
    await openPanel();
    const botao = document.querySelector<HTMLElement>("[data-alert-act]")!;
    expect(botao.textContent).toContain("Aceitar");
    await click("[data-alert-act]");
    expect(act).toHaveBeenCalledWith(9);
  });

  it("sem quem execute (o app não declarou act), o gesto direto não aparece", async () => {
    useOperatorInboxAlerts().value = {
      items: [{ key: 9, tone: "warning", message: "x", href: "/W09", hrefLabel: "Abrir o pedido", actLabel: "Aceitar" }],
      count: 1,
    };
    await mount();
    await openPanel();
    expect(document.querySelector("[data-alert-act]")).toBeNull();
    expect(document.querySelector("[data-alert-open]")).not.toBeNull();
  });

  // O "vou verificar" da Concierge (WP-07): o aviso se resolve com uma resposta escrita.
  const VERIFICAR = {
    key: 31, tone: "warning" as const, eyebrow: "Aviso · WhatsApp",
    message: "Pergunta do cliente: “vocês têm estacionamento”.", canAck: true,
    answer: {
      label: "Responder ao cliente", placeholder: "Escreva a resposta para o cliente", maxLength: 300,
      hint: "Sai pela Concierge como “A equipe confirmou: …”.", altLabel: "Assumir a conversa",
    },
  };
  async function type(text: string) {
    const field = document.querySelector<HTMLTextAreaElement>("[data-operator-inbox-answer-field] textarea, textarea[data-operator-inbox-answer-field]")!;
    field.value = text;
    field.dispatchEvent(new Event("input", { bubbles: true }));
    await nextTick();
  }
  const sendButton = () => document.querySelector<HTMLButtonElement>("[data-operator-inbox-answer-send]")!;

  it("o aviso com resposta mostra o campo e os dois gestos, no lugar do gesto direto", async () => {
    useOperatorInboxAlerts().value = { items: [VERIFICAR], count: 1, ack: vi.fn(), answer: vi.fn(), answerAlt: vi.fn() };
    await mount();
    await openPanel();
    expect(document.querySelector("[data-operator-inbox-answer]")).not.toBeNull();
    expect(sendButton().textContent).toContain("Responder ao cliente");
    expect(sendButton().disabled).toBe(true);
    expect(document.querySelector("[data-operator-inbox-answer-alt]")!.textContent).toContain("Assumir a conversa");
    expect(document.querySelector("[data-alert-act]")).toBeNull();
    expect(document.querySelector("[data-alert-ack]")).not.toBeNull();
  });

  // Sem "//" no fonte: a catraca de identificadores apaga do "//" ao fim da linha.
  const LIVE_CHAT = ["https:", "", "app.manychat.com", "fb486126", "chat", "4605"].join("/");
  const ADMIN = ["https:", "", "admin.exemplo.com", "admin", "shop", ""].join("/");

  it("o gesto alternativo com destino abre a aba no clique e roda o gesto junto", async () => {
    const answerAlt = vi.fn().mockResolvedValue(null);
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    useOperatorInboxAlerts().value = {
      items: [{ ...VERIFICAR, answer: { ...VERIFICAR.answer, altHref: LIVE_CHAT } }],
      count: 1, answer: vi.fn(), answerAlt,
    };
    await mount();
    await openPanel();
    document.querySelector<HTMLButtonElement>("[data-operator-inbox-answer-alt]")!.click();
    await nextTick();
    expect(open).toHaveBeenCalledWith(LIVE_CHAT, "_blank", "noopener");
    expect(answerAlt).toHaveBeenCalledWith(31);
    open.mockRestore();
  });

  it("sem destino, o aviso diz por que e mostra o botão que configura", async () => {
    useOperatorInboxAlerts().value = {
      items: [{
        ...VERIFICAR,
        answer: {
          ...VERIFICAR.answer,
          altNote: "Assumir não abre a conversa do ManyChat: falta a conta do Live Chat no Admin.",
          altNoteHref: ADMIN, altNoteLabel: "Configurar o Live Chat",
        },
      }],
      count: 1, answer: vi.fn(), answerAlt: vi.fn(),
    };
    await mount();
    await openPanel();
    expect(document.querySelector("[data-operator-inbox-answer-alt-note]")!.textContent).toContain("falta a conta do Live Chat");
    expect(document.querySelector("[data-operator-inbox-answer-alt-note-link]")!.textContent).toContain("Configurar o Live Chat");
  });

  it("o aviso com resposta diz o canal como selo e quem espera no título, sem gravidade nem tipo", async () => {
    useOperatorInboxAlerts().value = {
      items: [{ ...VERIFICAR, origin: "WhatsApp", originIcon: "i-lucide-message-circle", subject: "Ana espera a resposta da equipe" }],
      count: 1,
      answer: vi.fn(),
    };
    await mount();
    await openPanel();
    const title = document.querySelector("[data-operator-inbox-answer-title]")!;
    expect(document.querySelector("[data-operator-inbox-origin]")!.textContent).toContain("WhatsApp");
    expect(title.textContent).toContain("Ana espera a resposta da equipe");
    expect(panel()!.textContent).not.toContain("Aviso · WhatsApp");
  });

  it("respondeu: a resposta sai e o campo se esvazia", async () => {
    const answer = vi.fn().mockResolvedValue(null);
    useOperatorInboxAlerts().value = { items: [VERIFICAR], count: 1, answer };
    await mount();
    await openPanel();
    await type("  Temos sim, duas vagas.  ");
    await click("[data-operator-inbox-answer-send]");
    await nextTick();
    expect(answer).toHaveBeenCalledWith(31, "Temos sim, duas vagas.");
    expect(document.querySelector("[data-operator-inbox-answer-error]")).toBeNull();
    expect(document.querySelector<HTMLTextAreaElement>("textarea")!.value).toBe("");
  });

  it("erro de envio: a frase aparece no cartão e a resposta digitada não se perde", async () => {
    const answer = vi.fn().mockResolvedValue("A janela de 24 horas do WhatsApp fechou: a resposta não sai mais por aqui. Assuma a conversa.");
    useOperatorInboxAlerts().value = { items: [VERIFICAR], count: 1, answer };
    await mount();
    await openPanel();
    await type("Temos sim, duas vagas.");
    await click("[data-operator-inbox-answer-send]");
    await nextTick();
    expect(document.querySelector("[data-operator-inbox-answer-error]")!.textContent).toContain("janela de 24 horas");
    expect(document.querySelector<HTMLTextAreaElement>("textarea")!.value).toBe("Temos sim, duas vagas.");
  });

  it("erro definitivo (janela fechada): o envio se desliga e Assumir vira o principal, com o texto mantido", async () => {
    const answer = vi.fn().mockResolvedValue({ message: "A janela de 24 horas do WhatsApp fechou.", final: true });
    useOperatorInboxAlerts().value = { items: [VERIFICAR], count: 1, answer, answerAlt: vi.fn() };
    await mount();
    await openPanel();
    await type("Temos sim, duas vagas.");
    await click("[data-operator-inbox-answer-send]");
    await nextTick();
    expect(sendButton().disabled).toBe(true);
    expect(document.querySelector("[data-operator-inbox-answer-alt]")!.hasAttribute("data-operator-inbox-answer-primary")).toBe(true);
    expect(document.querySelector<HTMLTextAreaElement>("textarea")!.value).toBe("Temos sim, duas vagas.");
  });

  it("assumiu: o gesto alternativo vai ao app", async () => {
    const answerAlt = vi.fn().mockResolvedValue(null);
    useOperatorInboxAlerts().value = { items: [VERIFICAR], count: 1, answer: vi.fn(), answerAlt };
    await mount();
    await openPanel();
    await click("[data-operator-inbox-answer-alt]");
    expect(answerAlt).toHaveBeenCalledWith(31);
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

  it("aviso pessoal que pede um gesto leva aonde ele se faz (dono, 09/10/2026)", async () => {
    items.value = [
      {
        ...ROTINA,
        pk: 7,
        category: "production" as const,
        title: "Lote aguardando revisão de qualidade",
        message: "Pão de forma foi finalizado e entrou na fila da Qualidade.",
        action_url: `https://prod.example.test/quality?q=WO-7&date=2026-10-09`,
        action_label: "Revisar a qualidade do lote",
        action_data: {},
      },
    ];
    unread.value = 1;
    await mount();
    await openPanel();
    const abrir = document.querySelector<HTMLAnchorElement>("[data-notification-open]");
    expect(abrir?.textContent).toContain("Revisar a qualidade do lote");
    expect(abrir?.getAttribute("href")).toBe(`https://prod.example.test/quality?q=WO-7&date=2026-10-09`);
    abrir!.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    expect(markRead).toHaveBeenCalledWith(7);
  });

  it("sem destino declarado pelo servidor, o aviso pessoal não ganha botão", async () => {
    items.value = [ROTINA];
    await mount();
    await openPanel();
    expect(document.querySelector("[data-notification-open]")).toBeNull();
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

  // Beta 05/11 (CEN-01): o sino afogado em acessos, os lotes da Qualidade no fim, e o
  // "Não fui eu" que o servidor já sabia fazer sem botão na tela.
  it("a operação vem antes dos acessos, e os de rotina viram uma linha que se abre ali", async () => {
    const lote = {
      ...ROTINA,
      pk: 50,
      category: "production" as const,
      title: "Lote aguardando revisão de qualidade",
      is_actionable: false,
    };
    items.value = [
      ROTINA,
      { ...ROTINA, pk: 3 },
      { ...ROTINA, pk: 4 },
      SUSPEITO,
      lote,
    ];
    unread.value = 5;
    await mount();
    await openPanel();
    let rows = [...document.querySelectorAll<HTMLElement>("[data-notification-item]")];
    expect(rows[0]!.textContent).toContain("Lote aguardando revisão de qualidade");
    expect(rows).toHaveLength(2);
    expect(rows[1]!.dataset.highlight).toBe("true");
    const routineGroup = document.querySelector<HTMLButtonElement>("[data-notifications-routine]")!;
    expect(routineGroup.textContent).toContain("3 acessos seus sem nada fora do comum");
    routineGroup.click();
    await nextTick();
    rows = [...document.querySelectorAll<HTMLElement>("[data-notification-item]")];
    expect(rows).toHaveLength(5);
  });

  it("marcar todas como lidas, num toque", async () => {
    items.value = [ROTINA, SUSPEITO];
    unread.value = 2;
    await mount();
    await openPanel();
    await click("[data-notifications-read-all]");
    expect(markAllRead).toHaveBeenCalledTimes(1);
  });

  it("'Não fui eu' pergunta com as palavras do servidor e só então encerra os acessos", async () => {
    items.value = [SUSPEITO];
    unread.value = 1;
    notMe.mockResolvedValueOnce({ needsConfirmation: "Isto encerra as sessões abertas da sua conta." });
    notMe.mockResolvedValueOnce("done");
    confirmAnswer.mockResolvedValueOnce(true);
    await mount();
    await openPanel();
    await click("[data-notification-not-me]");
    await vi.waitFor(() => expect(sonner.success).toHaveBeenCalled());
    expect(confirmAnswer).toHaveBeenCalledWith(
      expect.objectContaining({ description: "Isto encerra as sessões abertas da sua conta." }),
    );
    expect(notMe.mock.calls).toEqual([[2, false], [2, true]]);
  });

  it("o giro do 'Não fui eu' fica no acesso tocado; os outros só esperam", async () => {
    items.value = [SUSPEITO, { ...SUSPEITO, pk: 9 }];
    let release!: (value: "done") => void;
    notMe.mockReturnValueOnce(new Promise((resolve) => { release = resolve; }));
    await mount();
    await openPanel();
    const buttons = () => [...document.querySelectorAll<HTMLButtonElement>("[data-notification-not-me]")];
    expect(buttons()).toHaveLength(2);
    buttons()[0]!.click();
    await nextTick();
    expect(buttons().map((button) => button.disabled)).toEqual([true, true]);
    const spinning = (button: HTMLButtonElement) => Boolean(button.querySelector(".animate-spin"));
    expect(buttons().map(spinning)).toEqual([true, false]);
    release("done");
  });

  it("desistir do 'Não fui eu' não encerra nada", async () => {
    items.value = [SUSPEITO];
    notMe.mockResolvedValueOnce({ needsConfirmation: "Isto encerra as sessões." });
    confirmAnswer.mockResolvedValueOnce(false);
    await mount();
    await openPanel();
    await click("[data-notification-not-me]");
    await vi.waitFor(() => expect(confirmAnswer).toHaveBeenCalled());
    expect(notMe).toHaveBeenCalledTimes(1);
  });

  it("o leitor de tela não lê códigos crus em inglês (beta 05/11, CEN-08 e CEN-13)", async () => {
    items.value = [SUSPEITO];
    await mount();
    await openPanel();
    expect(panel()!.textContent).not.toMatch(/\bbadge\b|outside_hours|after_failure/);
  });
});
