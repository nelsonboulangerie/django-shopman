// WP-G08, o diálogo "Resolver" da promessa em risco, montado: lê as escolhas ao abrir,
// mostra o fato, uma escolha por linha, a mensagem ao cliente da escolha marcada e o
// botão com o nome do que ela faz. As frases são as do servidor; a tela não reescreve.
import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, ref } from "vue";
import { flushPromises, mount } from "@vue/test-utils";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import OrderPromiseResolveDialog from "../../app/components/OrderPromiseResolveDialog.vue";
import { useOrderIntention } from "../../app/composables/useOrderIntention";
import type { PromiseResolution } from "../../app/presentation/promiseResolution";
import {
  CANCEL_MESSAGE,
  EDIT_ITEMS,
  REMOVE_MESSAGE,
  RESCHEDULE_MESSAGE,
  RESOLUTION_REF,
  SWAP_MESSAGE,
  cancelChoice,
  closed,
  removeChoice,
  rescheduleChoice,
  resolution,
  swapChoice,
} from "../support/promiseResolution";

const env = installNuxtGlobals();
const sonner = { error: vi.fn(), success: vi.fn(), info: vi.fn() };
vi.stubGlobal("useSonner", sonner);
vi.stubGlobal("useNuxtData", () => ({ data: ref({ operator: { id: 7 } }) }));
vi.stubGlobal("useOrderIntention", useOrderIntention);
const writeText = vi.fn(async () => undefined);
Object.defineProperty(globalThis.navigator, "clipboard", { value: { writeText }, configurable: true });

const READ = `/api/v1/backstage/orders/${RESOLUTION_REF}/promise-resolution/`;
const EDIT = `/api/v1/backstage/orders/${RESOLUTION_REF}/edit/`;

const managerAuth = defineComponent({
  name: "OperatorManagerAuth",
  props: ["open", "action", "managers", "error", "operatorName", "busy"],
  emits: ["authorize", "authorizeBadge", "update:open"],
  template: `<div v-if="open" data-manager-auth :data-action="action" :data-error="error" :data-operator="operatorName">
    <slot name="context" />
    <button data-sign @click="$emit('authorize', 'ana', '4321')">Assinar</button>
    <button data-sign-badge @click="$emit('authorizeBadge', 'cracha-1')">Crachá</button>
    <button data-dismiss @click="$emit('update:open', false)">Fechar</button>
  </div>`,
});
const screenState = defineComponent({
  name: "OperatorScreenState",
  props: ["state", "what", "description"],
  emits: ["retry"],
  template: `<div :data-screen-state="state">{{ what }} {{ description }}
    <button v-if="state === 'error'" data-retry @click="$emit('retry')">Tentar de novo</button>
  </div>`,
});
// O rádio com o DETALHE de cada opção escrito, como o do Nuxt UI: o do harness comum só
// desenha o nome, e aqui o detalhe (e o motivo da travada) é o que se confere.
const radioGroup = defineComponent({
  name: "NuxtRadioGroup",
  inheritAttrs: false,
  props: { modelValue: { type: String, default: "" }, items: { type: Array as () => Array<Record<string, unknown>>, default: () => [] } },
  emits: ["update:modelValue"],
  setup(props, { attrs, emit }) {
    return () =>
      h("div", { ...attrs, role: "radiogroup" }, props.items.map((item) =>
        h("button", {
          ...Object.fromEntries(Object.entries(item).filter(([key]) => key.startsWith("data-"))),
          type: "button", role: "radio", disabled: Boolean(item.disabled),
          "aria-checked": String(item.value === props.modelValue),
          onClick: () => emit("update:modelValue", item.value),
        }, [
          h("span", { "data-slot": "label" }, String(item.label ?? "")),
          item.description ? h("span", { "data-slot": "description" }, String(item.description)) : null,
        ]),
      ));
  },
});
const stubs = { Icon: true, OperatorManagerAuth: managerAuth, OperatorScreenState: screenState, NuxtRadioGroup: radioGroup };
const MANAGERS = [{ username: "ana", name: "Ana" }];

function render(props: Record<string, unknown> = {}) {
  return mount(OrderPromiseResolveDialog, {
    props: { open: true, orderRef: RESOLUTION_REF, managers: MANAGERS, ...props },
    global: { stubs },
  });
}
/** Abre com a leitura do servidor já na tela. */
async function opened(read: PromiseResolution = resolution(), props: Record<string, unknown> = {}) {
  env.fetchMock.mockResolvedValueOnce(read);
  const w = render(props);
  await flushPromises();
  return w;
}
const pick = (w: ReturnType<typeof render>, key: string) => w.get(`[data-resolve-choice="${key}"]`).trigger("click");
const conclude = (w: ReturnType<typeof render>) => w.get("[data-resolve-conclude]");
const refusal = (status: number, body: Record<string, unknown>) => ({ status, data: body });
/** Travado de verdade? (O link do harness escreve `disabled="false"`; o botão omite.) */
const locked = (element: ReturnType<typeof conclude>) => !["false", undefined].includes(element.attributes("disabled"));

beforeEach(() => {
  env.reset();
  for (const spy of Object.values(sonner)) spy.mockReset();
  writeText.mockReset().mockResolvedValue(undefined);
});

describe("OrderPromiseResolveDialog: abrir", () => {
  it("fechado, não lê nada", async () => {
    const w = render({ open: false });
    await flushPromises();
    expect(env.fetchMock).not.toHaveBeenCalled();
    expect(w.find("[data-promise-resolve-dialog]").exists()).toBe(false);
  });

  it("ao abrir, lê as escolhas deste pedido e diz que está carregando", async () => {
    let finish!: (value: unknown) => void;
    env.fetchMock.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const w = render();
    await flushPromises();
    expect(env.fetchMock).toHaveBeenCalledWith(READ, { timeout: 8000 });
    expect(w.get("h2").text()).toBe("Promessa em risco no pedido N75");
    expect(w.get('[data-screen-state="loading"]').text()).toContain("as escolhas deste pedido");
    // Enquanto lê, só há "Voltar": nenhum botão que conclui.
    expect(w.find("[data-resolve-conclude]").exists()).toBe(false);
    expect(w.get("[data-resolve-back]").text()).toBe("Voltar");
    finish(resolution());
    await flushPromises();
    expect(w.find("[data-resolve-content]").exists()).toBe(true);
  });

  it("a leitura que falha diz a frase e oferece \"Tentar de novo\", que lê outra vez", async () => {
    env.fetchMock.mockRejectedValueOnce(refusal(500, { detail: "O servidor não respondeu." }));
    const w = render();
    await flushPromises();
    const failed = w.get('[data-screen-state="error"]');
    expect(failed.text()).toContain("O servidor não respondeu.");
    expect(w.find("[data-resolve-conclude]").exists()).toBe(false);
    env.fetchMock.mockResolvedValueOnce(resolution());
    await failed.get("[data-retry]").trigger("click");
    await flushPromises();
    expect(env.fetchMock).toHaveBeenCalledTimes(2);
    expect(w.find("[data-resolve-content]").exists()).toBe(true);
  });

  it("409: fecha dizendo a frase do servidor e pede a releitura da página", async () => {
    env.fetchMock.mockRejectedValueOnce(refusal(409, { detail: "Este pedido não tem mais promessa em risco." }));
    const w = render();
    await flushPromises();
    expect(sonner.info).toHaveBeenCalledWith("Este pedido não tem mais promessa em risco.");
    expect(w.emitted("changed")).toHaveLength(1);
    expect(w.emitted("update:open")?.at(-1)).toEqual([false]);
  });

  it("cada abertura lê de novo, e a escolha anterior não fica marcada", async () => {
    const w = await opened();
    await pick(w, "reschedule");
    await w.setProps({ open: false });
    env.fetchMock.mockResolvedValueOnce(resolution());
    await w.setProps({ open: true });
    await flushPromises();
    expect(env.fetchMock).toHaveBeenCalledTimes(2);
    expect(w.findAll('[role="radio"][aria-checked="true"]')).toHaveLength(0);
    expect(conclude(w).text()).toBe("Escolha o que fazer");
  });
});

describe("OrderPromiseResolveDialog: o conteúdo, de cima para baixo", () => {
  it("o fato, com as frases do aviso, uma por item em falta", async () => {
    const w = await opened(resolution({
      facts: [
        "Faltam 4x Focaccia Cebola, Bacon e Tomilho. O lote de hoje foi cancelado.",
        "Faltam 2x Brioche. O lote de hoje fechou com menos.",
      ],
    }));
    expect(w.findAll("[data-resolve-fact]").map((fact) => fact.text())).toEqual([
      "Faltam 4x Focaccia Cebola, Bacon e Tomilho. O lote de hoje foi cancelado.",
      "Faltam 2x Brioche. O lote de hoje fechou com menos.",
    ]);
    expect(w.get("[data-resolve-facts]").attributes("color")).toBe("error");
  });

  it("\"O que fazer\": uma escolha por linha, na ordem do servidor, com o detalhe ao lado", async () => {
    const w = await opened();
    const group = w.get("[data-resolve-choices]");
    expect(group.attributes("legend")).toBe("O que fazer");
    expect(group.findAll('[role="radio"]').map((radio) => [
      radio.get('[data-slot="label"]').text(), radio.find('[data-slot="description"]').exists() ? radio.get('[data-slot="description"]').text() : "",
    ])).toEqual([
      ["Trocar por Campagne Passas & Castanhas", "6 disponíveis hoje"],
      ["Remarcar para outro dia ou outro lote", ""],
      ["Tirar só o item que falta e devolver a diferença", "R$ 44,00 serão estornados ao Pix do cliente."],
      ["Cancelar o pedido inteiro", "R$ 62,00 serão estornados ao Pix do cliente."],
    ]);
  });

  it("nada vem marcado sozinho: sem escolha, o botão que conclui fica travado e diz o que falta", async () => {
    const w = await opened();
    expect(w.findAll('[role="radio"][aria-checked="true"]')).toHaveLength(0);
    expect(conclude(w).text()).toBe("Escolha o que fazer");
    expect(locked(conclude(w))).toBe(true);
    // O lugar da mensagem existe desde o início, e diz o que falta para ela aparecer.
    expect(w.get("[data-resolve-message-pending]").text()).toBe("Escolha o que fazer para ver a mensagem.");
    expect(w.find("[data-resolve-copy]").exists()).toBe(false);
  });

  it("escolha fechada continua na lista: mostra o motivo ESCRITO (nunca só em `title`) e não se marca", async () => {
    const w = await opened(resolution({
      choices: [
        closed(swapChoice(), "Pedido em preparo não pode ser editado."),
        rescheduleChoice(),
        closed(removeChoice(), "É o único item do pedido: cancele o pedido."),
        cancelChoice(),
      ],
    }));
    for (const [key, reason] of [
      ["swap:FOCACCIA-CBT:CAMPAGNE-PC", "Pedido em preparo não pode ser editado."],
      ["remove", "É o único item do pedido: cancele o pedido."],
    ] as const) {
      const locked = w.get(`[data-resolve-choice="${key}"]`);
      expect(locked.attributes("disabled")).toBeDefined();
      expect(locked.get('[data-slot="description"]').text()).toBe(reason);
      expect(locked.attributes("title")).toBeUndefined();
    }
    // As abertas seguem valendo.
    await pick(w, "reschedule");
    expect(conclude(w).text()).toBe("Remarcar no PDV");
  });

  for (const [key, message, label] of [
    ["swap:FOCACCIA-CBT:CAMPAGNE-PC", SWAP_MESSAGE, "Trocar no PDV"],
    ["reschedule", RESCHEDULE_MESSAGE, "Remarcar no PDV"],
    ["remove", REMOVE_MESSAGE, "Tirar o item"],
    ["cancel", CANCEL_MESSAGE, "Cancelar pedido"],
  ] as const)
    it(`marcar "${key}": a mensagem é a dessa escolha e o botão diz "${label}"`, async () => {
      const w = await opened();
      await pick(w, key);
      expect(w.get("[data-resolve-message]").text()).toBe(message);
      expect(conclude(w).text()).toBe(label);
      expect(locked(conclude(w))).toBe(false);
      expect(w.get("[data-resolve-message-block]").text()).toContain("Mensagem para Nelson Dias");
    });

  it("a nota interina do servidor fica escrita, em letra pequena", async () => {
    const w = await opened();
    expect(w.get("[data-resolve-interim]").text()).toBe(
      "O envio automático ainda não existe: copie a mensagem ou chame o cliente no WhatsApp.",
    );
    expect(w.get("[data-resolve-interim]").classes()).toContain("text-xs");
  });
});

describe("OrderPromiseResolveDialog: a mensagem ao cliente", () => {
  it("\"Copiar mensagem\" copia a mensagem da escolha e confirma por escrito", async () => {
    const w = await opened();
    await pick(w, "remove");
    expect(w.find("[data-resolve-copied]").exists()).toBe(false);
    await w.get("[data-resolve-copy]").trigger("click");
    await flushPromises();
    expect(w.get("[data-resolve-copy]").text()).toBe("Copiar mensagem");
    expect(writeText).toHaveBeenCalledWith(REMOVE_MESSAGE);
    expect(w.get("[data-resolve-copied]").text()).toBe("Mensagem copiada.");
    // Trocar de escolha: a confirmação era da mensagem anterior.
    await pick(w, "cancel");
    expect(w.find("[data-resolve-copied]").exists()).toBe(false);
  });

  it("sem área de transferência, diz o que fazer em vez de fingir que copiou", async () => {
    writeText.mockRejectedValueOnce(new Error("denied"));
    const w = await opened();
    await pick(w, "reschedule");
    await w.get("[data-resolve-copy]").trigger("click");
    await flushPromises();
    expect(w.get("[data-resolve-copied]").text()).toBe("Não deu para copiar. Selecione a mensagem e copie à mão.");
  });

  it("\"Chamar no WhatsApp\" é só um link, em outra aba, com a mensagem da escolha: nada é enviado daqui", async () => {
    const w = await opened();
    await pick(w, "swap:FOCACCIA-CBT:CAMPAGNE-PC");
    const link = w.get("[data-resolve-whatsapp]");
    expect(link.text()).toBe("Chamar no WhatsApp");
    expect(link.element.tagName).toBe("A");
    expect(link.attributes("href")).toBe(swapChoice().whatsapp_url);
    expect(link.attributes("target")).toBe("_blank");
    await link.trigger("click");
    expect(env.fetchMock).toHaveBeenCalledTimes(1); // só a leitura
  });

  it("pedido sem WhatsApp: \"Chamar no WhatsApp\" travado, com o motivo escrito", async () => {
    const w = await opened(resolution({
      contact: { enabled: false, reason: "Este pedido não tem WhatsApp do cliente." },
      choices: [rescheduleChoice({ whatsapp_url: "" }), cancelChoice({ whatsapp_url: "" })],
    }));
    await pick(w, "reschedule");
    // A mensagem continua pronta para copiar e mandar por outro meio.
    expect(w.get("[data-resolve-message]").text()).toBe(RESCHEDULE_MESSAGE);
    const locked = w.get("[data-resolve-whatsapp]");
    expect(locked.element.tagName).toBe("BUTTON");
    expect(locked.attributes("disabled")).toBeDefined();
    expect(w.get("[data-resolve-contact-reason]").text()).toBe("Este pedido não tem WhatsApp do cliente.");
    // Copiar continua valendo: a mensagem serve para outro meio.
    expect(w.get("[data-resolve-copy]").attributes("disabled")).toBeUndefined();
  });
});

describe("OrderPromiseResolveDialog: concluir", () => {
  it("trocar e remarcar abrem o PDV, com o endereço do servidor, e o diálogo fecha", async () => {
    const w = await opened();
    await pick(w, "swap:FOCACCIA-CBT:CAMPAGNE-PC");
    expect(conclude(w).element.tagName).toBe("A");
    expect(conclude(w).attributes("href")).toBe(`https://pdv.example.test/preorders/${RESOLUTION_REF}?swap=FOCACCIA-CBT`);
    expect(conclude(w).attributes("external")).toBeDefined();
    await pick(w, "reschedule");
    expect(conclude(w).attributes("href")).toBe(`https://pdv.example.test/preorders/${RESOLUTION_REF}`);
    await conclude(w).trigger("click");
    expect(w.emitted("update:open")?.at(-1)).toEqual([false]);
    // Nada é gravado pelo Gestor: o gesto mora no PDV.
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
  });

  it("cancelar fecha este diálogo e avisa quem monta, que abre o cancelar que já existe (o gerente é de lá)", async () => {
    const w = await opened();
    await pick(w, "cancel");
    // Pedido pago vem com `requires_manager_approval`: aqui não sobe PIN nem aviso de gerente.
    expect(w.find("[data-resolve-manager-hint]").exists()).toBe(false);
    expect(conclude(w).attributes("color")).toBe("error");
    await conclude(w).trigger("click");
    expect(w.emitted("update:open")?.at(-1)).toEqual([false]);
    expect(w.emitted("cancel")).toEqual([[RESOLUTION_REF]]);
    expect(w.find("[data-manager-auth]").exists()).toBe(false);
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
  });

  it("tirar o item sem gerente: grava a lista final do servidor, fecha, diz o que foi feito e pede a releitura", async () => {
    const w = await opened(resolution({
      choices: [removeChoice({ requires_manager_approval: false })],
    }));
    await pick(w, "remove");
    expect(w.find("[data-resolve-manager-hint]").exists()).toBe(false);
    env.fetchMock.mockResolvedValueOnce({ outcome: "applied" });
    await conclude(w).trigger("click");
    await flushPromises();
    const [path, options] = env.fetchMock.mock.calls[1]!;
    expect(path).toBe(EDIT);
    expect(options.body).toEqual({ items: EDIT_ITEMS, base_revision: "edit-rev-1", expected_actor_id: 7 });
    expect(sonner.success).toHaveBeenCalledWith("O que faltava saiu do pedido. R$ 44,00 serão estornados ao Pix do cliente.");
    expect(w.emitted("changed")).toHaveLength(1);
    expect(w.emitted("update:open")?.at(-1)).toEqual([false]);
    expect(w.find("[data-manager-auth]").exists()).toBe(false);
  });

  it("tirar o item que pede gerente: avisa antes, sobe o diálogo de sempre com a frase do dinheiro, e a assinatura vai junto", async () => {
    const w = await opened(resolution({
      choices: [removeChoice()],
    }), { viewerName: "Joyce" });
    await pick(w, "remove");
    expect(w.get("[data-resolve-manager-hint]").text()).toBe("Um gerente autoriza no próximo passo.");
    await conclude(w).trigger("click");
    // Nada foi gravado ainda: primeiro o gerente.
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    const auth = w.get("[data-manager-auth]");
    expect(auth.attributes("data-action")).toBe("order_edit_refund");
    expect(auth.attributes("data-operator")).toBe("Joyce");
    expect(auth.get("[data-resolve-manager-detail]").text()).toBe("R$ 44,00 serão estornados ao Pix do cliente.");
    // O diálogo das escolhas sai da frente enquanto o gerente assina.
    expect(w.find("[data-promise-resolve-dialog]").exists()).toBe(false);
    env.fetchMock.mockResolvedValueOnce({ outcome: "applied" });
    await auth.get("[data-sign]").trigger("click");
    await flushPromises();
    expect(env.fetchMock.mock.calls[1]![1].body.manager_approval).toEqual({ username: "ana", pin: "4321" });
    expect(w.emitted("changed")).toHaveLength(1);
    expect(w.emitted("update:open")?.at(-1)).toEqual([false]);
  });

  it("o crachá do gerente também assina", async () => {
    const w = await opened(resolution({
      choices: [removeChoice()],
    }));
    await pick(w, "remove");
    await conclude(w).trigger("click");
    env.fetchMock.mockResolvedValueOnce({ outcome: "applied" });
    await w.get("[data-sign-badge]").trigger("click");
    await flushPromises();
    expect(env.fetchMock.mock.calls[1]![1].body.manager_approval).toEqual({ badge: "cracha-1" });
  });

  it("PIN errado fica no diálogo do gerente, com a frase do servidor", async () => {
    const w = await opened(resolution({
      choices: [removeChoice()],
    }));
    await pick(w, "remove");
    await conclude(w).trigger("click");
    env.fetchMock.mockRejectedValueOnce(refusal(403, { detail: "Aprovação gerencial inválida.", error: { code: "manager_approval_invalid", message: "Aprovação gerencial inválida." } }));
    await w.get("[data-sign]").trigger("click");
    await flushPromises();
    expect(w.get("[data-manager-auth]").attributes("data-error")).toBe("Aprovação gerencial inválida.");
    expect(w.emitted("update:open")).toBeUndefined();
    expect(w.emitted("changed")).toBeUndefined();
  });

  it("o servidor pede gerente sem a leitura ter avisado: o mesmo diálogo sobe", async () => {
    const w = await opened(resolution({
      choices: [removeChoice({ requires_manager_approval: false })],
    }));
    await pick(w, "remove");
    env.fetchMock.mockRejectedValueOnce(refusal(403, { detail: "Peça a um gerente.", error: { code: "manager_approval_required", message: "Peça a um gerente." } }));
    await conclude(w).trigger("click");
    await flushPromises();
    expect(w.get("[data-manager-auth]").attributes("data-error")).toBe("");
    expect(sonner.error).not.toHaveBeenCalled();
  });

  it("a recusa fica escrita no diálogo, que continua aberto com a escolha marcada", async () => {
    const w = await opened(resolution({
      choices: [rescheduleChoice(), removeChoice({ requires_manager_approval: false })],
    }));
    await pick(w, "remove");
    env.fetchMock.mockRejectedValueOnce(refusal(400, { detail: "Pedido em preparo não pode ser editado.", outcome: "not_applied" }));
    await conclude(w).trigger("click");
    await flushPromises();
    expect(w.get("[data-resolve-error]").text()).toBe("Pedido em preparo não pode ser editado.");
    expect(w.get("[data-resolve-footer]").find("[data-resolve-error]").exists()).toBe(true);
    expect(w.emitted("update:open")).toBeUndefined();
    expect(w.emitted("changed")).toBeUndefined();
    expect(w.get('[data-resolve-choice="remove"]').attributes("aria-checked")).toBe("true");
    // Outra escolha: a recusa era da anterior.
    await pick(w, "reschedule");
    expect(w.find("[data-resolve-error]").exists()).toBe(false);
  });

  it("\"Voltar\" fecha sem gravar nada", async () => {
    const w = await opened();
    await pick(w, "remove");
    await w.get("[data-resolve-back]").trigger("click");
    expect(w.emitted("update:open")?.at(-1)).toEqual([false]);
    expect(w.emitted("changed")).toBeUndefined();
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
  });
});
