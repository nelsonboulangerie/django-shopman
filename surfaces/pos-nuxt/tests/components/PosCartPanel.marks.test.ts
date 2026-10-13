import { afterEach, describe, expect, it, vi } from "vitest";
import { enableAutoUnmount } from "@vue/test-utils";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosCartPanel from "~/components/PosCartPanel.vue";
import type { POSCartItem } from "~/types/pos";
import type { ActionAffordance } from "~/presentation/actions";
import { formatBRL } from "~/utils/posIntent";

enableAutoUnmount(afterEach);

const toastCalls = vi.hoisted(() => [] as Array<[string, { action?: { label: string; onClick: () => void } }]>);
vi.mock("vue-sonner", async (importOriginal) => ({
  ...(await importOriginal<typeof import("vue-sonner")>()),
  toast: (message: string, options: { action?: { label: string; onClick: () => void } }) => { toastCalls.push([message, options]); },
}));

// A COLUNA DA COMANDA (WP-PDV-COLUNA-COMANDA, decisões do dono de 10/10/2026): marcar sem
// modo, o bloco de 1 vira o de N nas mesmas posições, o pé segue o foco, a comanda tem a
// porta dela no cabeçalho e o Transferir embute comanda nova e juntar.

function affordance(overrides: Partial<ActionAffordance> = {}): ActionAffordance {
  return { ref: "fire_tab", present: true, label: "Enviar à cozinha", priority: "primary", enabled: true, reason: "", href: "/x", ...overrides };
}
function item(overrides: Partial<POSCartItem> & { sku: string; name: string }): POSCartItem {
  return { line_id: `L-${overrides.sku}`, price_q: 500, qty: 1, notes: "", ...overrides };
}
function props(overrides: Record<string, unknown> = {}) {
  return {
    items: [
      item({ sku: "PAO", name: "Pão" }),
      item({ sku: "QUICHE", name: "Quiche", price_q: 2490 }),
      item({ sku: "CAFE", name: "Café", price_q: 300, qty: 2 }),
    ],
    total: { status: "confirmed", display: formatBRL(3590) },
    requiresTab: false,
    hasOpenTab: true,
    loading: false,
    saving: false,
    fireAction: affordance(),
    unfireAction: affordance({ ref: "unfire_tab", label: "Cancelar envio" }),
    firing: false,
    ...overrides,
  };
}
type Wrapper = Awaited<ReturnType<typeof mountSuspended>>;
/** Tocar a linha marca só ela e abre o bloco dela (dono, 13/10/2026). */
async function open(wrapper: Wrapper, name = "Café") {
  await wrapper.find(`[aria-label="Editar ${name}"]`).trigger("click");
}
async function mark(wrapper: Wrapper, lineId: string, shiftKey = false) {
  await wrapper.find(`[data-pos-line-mark="${lineId}"]`).trigger("click", { shiftKey });
}
const block = (wrapper: Wrapper) => wrapper.find("[data-pos-line-editor]");

describe("PosCartPanel — marcar sem modo", () => {
  it("não há botão Selecionar nem cabeçalho trocado: o cabeçalho é sempre o da comanda", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    expect(wrapper.find("[data-pos-select-lines]").exists()).toBe(false);
    await mark(wrapper, "L-PAO");
    await mark(wrapper, "L-CAFE");
    expect(wrapper.find("[data-pos-selection-bar]").exists()).toBe(false);
    expect(wrapper.find("[data-pos-ticket-header]").text()).toContain("4 itens");
  });

  it("uma marca é o bloco de uma linha (com a quantidade); duas viram o bloco dos marcados, com o objeto em itens", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    // Nada marcado ao abrir: o bloco não existe.
    expect(block(wrapper).exists()).toBe(false);
    await mark(wrapper, "L-PAO");
    expect(block(wrapper).attributes("data-pos-block")).toBe("line");
    expect(wrapper.findAll("[data-pos-line-marked]")).toHaveLength(1);
    await mark(wrapper, "L-CAFE");
    expect(block(wrapper).attributes("data-pos-block")).toBe("marked");
    expect(wrapper.find("[data-pos-marked-title]").text().replace(/\s/g, " ")).toBe(`3 itens marcados· ${formatBRL(1100)}`.replace(/\s/g, " "));
    expect(wrapper.findAll("[data-pos-line-marked]")).toHaveLength(2);
  });

  it("as posições não mudam: um lugar só para tudo o que age nos marcados, Enviar | Transferir por último", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    const cells = () => wrapper.findAll("[data-pos-line-editor] [data-pos-controls-block] [data-pos-control-cell]").map((c) => c.attributes("data-pos-control-cell"));
    await mark(wrapper, "L-CAFE");
    expect(cells()).toEqual(["qty", "remove", "discount", "note", "fire", "transfer"]);
    await mark(wrapper, "L-PAO");
    expect(cells()).toEqual(["remove", "discount", "note", "fire", "transfer"]);
    expect(wrapper.findAll("[data-pos-tab-transfer], [data-pos-batch-move]")).toHaveLength(1);
    expect(wrapper.find("[data-pos-tab-transfer]").text()).toContain("Transferir marcados");
    await wrapper.find("[data-pos-tab-transfer]").trigger("click");
    expect(wrapper.emitted("move")?.[0]).toEqual([["L-PAO", "L-CAFE"]]);
  });

  it("desmarcar a última fecha o bloco; o pé volta a valer para a comanda", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await mark(wrapper, "L-PAO");
    await mark(wrapper, "L-CAFE");
    await mark(wrapper, "L-QUICHE");
    expect(wrapper.find("[data-pos-marked-title]").text()).toContain("4 itens marcados");
    await mark(wrapper, "L-CAFE");
    await mark(wrapper, "L-PAO");
    expect(wrapper.find("[data-pos-line-editor-title]").text()).toContain("Quiche");
    await mark(wrapper, "L-QUICHE");
    expect(block(wrapper).exists()).toBe(false);
    expect(wrapper.find("[data-pos-ticket-foot] [data-pos-tab-transfer]").text()).toContain("Transferir itens");
  });

  it("Shift + clique marca o intervalo; Esc desmarca tudo", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props(), attachTo: document.body });
    await wrapper.find('[data-item-select="L-PAO"]').trigger("click");
    await mark(wrapper, "L-CAFE", true);
    expect(wrapper.find("[data-pos-marked-title]").text()).toContain("4 itens marcados");
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll("[data-pos-line-marked]")).toHaveLength(0);
    expect(block(wrapper).exists()).toBe(false);
  });

  it("Espaço na linha em foco marca, como a caixa", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper.find('[data-item-select="L-PAO"]').trigger("keydown", { key: " " });
    expect(wrapper.findAll("[data-pos-line-marked]")).toHaveLength(1);
  });

  it("com marcas, clicar numa linha marca (não joga as marcas fora)", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await mark(wrapper, "L-PAO");
    await mark(wrapper, "L-CAFE");
    await wrapper.find('[data-item-select="L-QUICHE"]').trigger("click");
    expect(wrapper.findAll("[data-pos-line-marked]")).toHaveLength(3);
  });

  it("com marcas, um dígito não faz nada (a quantidade é de uma linha)", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props(), attachTo: document.body });
    await mark(wrapper, "L-PAO");
    await mark(wrapper, "L-CAFE");
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "3", bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("setQty")).toBeUndefined();
    expect(wrapper.find("[data-pos-discount-panel]").exists()).toBe(false);
  });
});

describe("PosCartPanel — o pé segue o foco; o Pagamento não", () => {
  it("com marcas, Enviar diz 'Enviar marcados' e envia só eles; o Pagamento segue a comanda inteira", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await mark(wrapper, "L-PAO");
    await mark(wrapper, "L-CAFE");
    const fire = wrapper.find("[data-pos-fire]");
    expect(fire.text()).toContain("Enviar marcados");
    expect(wrapper.find("[data-pos-primary]").text()).toContain(formatBRL(3590));
    await fire.trigger("click");
    expect(wrapper.emitted("fire")).toBeUndefined();
    expect(wrapper.emitted("fireLines")?.[0]?.[0]).toEqual(["L-PAO", "L-CAFE"]);
  });

  it("F9 com marcas é o mesmo gesto (fireSelection); sem marcas, devolve false", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    const vm = wrapper.vm as unknown as { fireSelection: () => boolean; moveSelection: () => boolean };
    expect(vm.fireSelection()).toBe(false);
    expect(vm.moveSelection()).toBe(false);
    await mark(wrapper, "L-PAO");
    await mark(wrapper, "L-CAFE");
    expect(vm.fireSelection()).toBe(true);
    expect(wrapper.emitted("fireLines")).toHaveLength(1);
    expect(vm.moveSelection()).toBe(true);
    expect(wrapper.emitted("move")?.[0]).toEqual([["L-PAO", "L-CAFE"]]);
  });

  it("ato em lote concluído limpa as marcas; no erro, ficam", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await mark(wrapper, "L-PAO");
    await mark(wrapper, "L-CAFE");
    await wrapper.find("[data-pos-fire]").trigger("click");
    (wrapper.emitted("fireLines")![0]![1] as (ok: boolean) => void)(false);
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll("[data-pos-line-marked]")).toHaveLength(2);
    await wrapper.find("[data-pos-fire]").trigger("click");
    (wrapper.emitted("fireLines")![1]![1] as (ok: boolean) => void)(true);
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll("[data-pos-line-marked]")).toHaveLength(0);
  });

  it("marcadas já na cozinha: o Enviar diz isso, apagado", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ items: [item({ sku: "PAO", name: "Pão", fired: true }), item({ sku: "CAFE", name: "Café", fired: true }), item({ sku: "BOLO", name: "Bolo" })] }),
    });
    await wrapper.find('[data-item-select="L-PAO"]').trigger("click");
    await mark(wrapper, "L-CAFE");
    expect(wrapper.find("[data-pos-fire]").text()).toContain("Marcados já na cozinha");
    expect(wrapper.find("[data-pos-fire]").attributes("disabled")).toBeDefined();
  });

  it("Remover N confirma E oferece Desfazer, como remover 1", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await mark(wrapper, "L-PAO");
    await mark(wrapper, "L-CAFE");
    await wrapper.find("[data-pos-line-remove]").trigger("click");
    expect(wrapper.emitted("remove")).toBeUndefined();
    const confirm = Array.from(document.querySelectorAll("button")).find((b) => b.textContent?.includes("Remover itens"));
    (confirm as HTMLElement).click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("remove")).toEqual([["L-PAO"], ["L-CAFE"]]);
    const [message, options] = toastCalls.at(-1)!;
    expect(message).toBe("3 itens removidos.");
    options.action!.onClick();
    expect(wrapper.emitted("restore")?.map((args) => (args[0] as POSCartItem).line_id)).toEqual(["L-PAO", "L-CAFE"]);
  });

  it("desconto nas marcadas: rascunho até Aplicar, vale para todas e limpa as marcas", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await mark(wrapper, "L-PAO");
    await mark(wrapper, "L-CAFE");
    await wrapper.find("[data-pos-line-discount]").trigger("click");
    const brl = wrapper.findAll("button").find((b) => b.text().trim() === "Em R$")!;
    await brl.trigger("click");
    await wrapper.find('[aria-label="Dígito 2"]').trigger("click");
    expect(wrapper.emitted("setDiscount")).toBeUndefined();
    await wrapper.find("[data-pos-edit-apply]").trigger("click");
    expect(wrapper.emitted("setDiscount")).toEqual([
      ["L-PAO", 2, "cortesia", "fixed"],
      ["L-CAFE", 2, "cortesia", "fixed"],
    ]);
    expect(wrapper.findAll("[data-pos-line-marked]")).toHaveLength(0);
  });

  it("no lote com peça pesada, desconto só em %", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ items: [item({ sku: "QUEIJO", name: "Queijo", qty: 0.312, weighed: { weight_g: 312 } as POSCartItem["weighed"] }), item({ sku: "PAO", name: "Pão" })] }),
    });
    await mark(wrapper, "L-QUEIJO");
    await wrapper.find("[data-pos-line-discount]").trigger("click");
    const brl = wrapper.findAll("button").find((b) => b.text().trim() === "Em R$")!;
    expect(brl.attributes("disabled")).toBeDefined();
  });

  it("observação nas marcadas: a mesma para todas", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await mark(wrapper, "L-PAO");
    await mark(wrapper, "L-CAFE");
    await wrapper.find("[data-pos-line-note]").trigger("click");
    expect(wrapper.find("[data-pos-note-help]").text()).toContain("todos os marcados");
    await wrapper.find("[data-pos-note-panel] textarea").setValue("para viagem");
    await wrapper.find("[data-pos-edit-apply]").trigger("click");
    expect(wrapper.emitted("setNotes")).toEqual([["L-PAO", "para viagem"], ["L-CAFE", "para viagem"]]);
  });

  it("o envio automático espera o rascunho e as marcas", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    const last = () => wrapper.emitted("autoFireHold")!.at(-1)![0];
    expect(last()).toBe(false);
    await mark(wrapper, "L-PAO");
    await mark(wrapper, "L-CAFE");
    expect(last()).toBe(true);
  });
});

describe("PosCartPanel — a porta da comanda e as do raro", () => {
  it("o cabeçalho tem 'Comanda ⋯' (só Liberar; Juntar é destino do Transferir, que mora no pé); some na edição de encomenda", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    expect(wrapper.find("[data-pos-tab-menu]").exists()).toBe(true);
    expect(wrapper.find("[data-pos-tab-menu]").attributes("aria-label")).toBe("Ações da comanda: liberar");
    // Na folha que paga direto (tablet, celular) não há pé: Transferir segue no ⋯.
    const sheet = await mountSuspended(PosCartPanel, {
      props: props({ sheet: true, quickPayments: [{ ref: "pix", label: "PIX", icon: "i-lucide-qr-code" }] }),
    });
    await sheet.find("[data-operator-action-bar-secondary]").trigger("click");
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(document.body.querySelector("[data-pos-sheet-pay]")).not.toBeNull();
    expect(document.body.querySelector("[data-pos-tab-transfer]")).toBeNull();
    expect(document.body.querySelector("[data-pos-tab-menu]")?.getAttribute("aria-label")).toBe("Ações da comanda: transferir itens, liberar");
    sheet.unmount();
    const editing = await mountSuspended(PosCartPanel, { props: props({ primaryLabel: "Salvar alterações", hideMove: true }) });
    expect(editing.find("[data-pos-tab-menu]").exists()).toBe(false);
  });

  it("a linha aberta tem ⋯ com o raro dela; a expansão só lê", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await open(wrapper);
    expect(wrapper.find("[data-pos-line-menu]").exists()).toBe(true);
    await wrapper.find('[data-item-select="L-CAFE"]').trigger("keydown", { key: "ArrowRight" });
    expect(wrapper.find('[role="region"]').findAll("button")).toHaveLength(0);
  });
});

describe("PosCartPanel — a linha que já está na cozinha", () => {
  const fired = [item({ sku: "CROISSANT", name: "Croissant", fired: true, kitchen_status: "pending" } as Partial<POSCartItem> & { sku: string; name: string })];

  it("+ numa linha enviada vai numa linha NOVA, a enviar, e o editor segue a nova", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ items: fired }) });
    await open(wrapper, "Croissant");
    await wrapper.find('[aria-label="Aumentar"]').trigger("click");
    expect(wrapper.emitted("increment")).toBeUndefined();
    const [lineId, qty, done] = wrapper.emitted("addLike")![0]! as [string, number, (id: string) => void];
    expect([lineId, qty]).toEqual(["L-CROISSANT", 1]);
    await wrapper.setProps({ items: [...fired, item({ sku: "CROISSANT", name: "Croissant", line_id: "L-novo" })] });
    done("L-novo");
    await wrapper.vm.$nextTick();
    expect(wrapper.find('[aria-current="true"] [data-item-select]').attributes("data-item-select")).toBe("L-novo");
  });

  it("observação nova numa linha enviada oferece reenviar, na cor do aviso, e se dispensa", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ items: fired }) });
    await open(wrapper, "Croissant");
    await wrapper.find("[data-pos-line-note]").trigger("click");
    await wrapper.find("[data-pos-note-panel] textarea").setValue("sem manteiga");
    await wrapper.find("[data-pos-edit-apply]").trigger("click");
    const offer = wrapper.find("[data-pos-resend-offer]");
    expect(offer.text()).toContain("A cozinha recebeu esta linha sem a observação.");
    const resend = offer.findAll("button").find((b) => b.text().includes("Reenviar com a observação"))!;
    await resend.trigger("click");
    expect(wrapper.emitted("resend")).toEqual([["L-CROISSANT"]]);
    expect(wrapper.find("[data-pos-resend-offer]").exists()).toBe(false);
  });
});

describe("PosCartPanel — sem conexão", () => {
  it("o que precisa do servidor fica apagado com o motivo; quantidade e observação seguem", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ offline: true }) });
    await open(wrapper);
    expect(wrapper.find("[data-pos-kitchen-offline]").text()).toContain("cozinha sem conexão");
    expect(wrapper.find("[data-pos-fire]").attributes("disabled")).toBeDefined();
    expect(wrapper.find("[data-pos-line-discount]").attributes("disabled")).toBeDefined();
    expect(wrapper.find("[data-pos-block-offline]").text()).toContain("Desconto volta com a conexão.");
    expect(wrapper.find("[data-pos-line-note]").attributes("disabled")).toBeUndefined();
    expect(wrapper.find('[aria-label="Aumentar"]').attributes("disabled")).toBeUndefined();
  });
});

describe("PosCartPanel — Envio: Auto · Manual, um controle de verdade (dono, 13/10)", () => {
  it("ligado: Auto pressionado, a dica diz o quando e o alcance, e a linha diz que vai sozinha", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ autoFire: true, autoFireSkus: ["PAO"], kitchenStations: { PAO: "Forno", CAFE: "Bar" } }),
    });
    const auto = wrapper.find("[data-pos-auto-fire]");
    expect(auto.attributes("data-auto-fire")).toBe("on");
    expect(auto.attributes("title")).toContain("90 s");
    expect(auto.attributes("title")).toContain("Forno e Bar, em todas as comandas");
    expect(wrapper.find('[data-pos-auto-fire-option="auto"]').attributes("aria-pressed")).toBe("true");
    expect(wrapper.text()).toContain("vai sozinho");
    expect(wrapper.text()).toContain("vai à cozinha");
    // Tocar o que já está escolhido não faz nada; tocar o outro pede a troca.
    await wrapper.find('[data-pos-auto-fire-option="auto"]').trigger("click");
    expect(wrapper.emitted("autoFireChange")).toBeUndefined();
    await wrapper.find('[data-pos-auto-fire-option="manual"]').trigger("click");
    expect(wrapper.emitted("autoFireChange")).toEqual([[false]]);
  });
  it("desligado: Manual pressionado, nunca 'desligado'; sem conexão, o controle apaga", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ autoFire: false }) });
    expect(wrapper.find('[data-pos-auto-fire-option="manual"]').attributes("aria-pressed")).toBe("true");
    expect(wrapper.find("[data-pos-ticket-header]").text()).not.toContain("desligado");
    await wrapper.find('[data-pos-auto-fire-option="auto"]').trigger("click");
    expect(wrapper.emitted("autoFireChange")).toEqual([[true]]);
    const offline = await mountSuspended(PosCartPanel, { props: props({ autoFire: false, offline: true }) });
    expect(offline.find('[data-pos-auto-fire-option="auto"]').attributes("disabled")).toBeDefined();
  });
});

describe("PosCartPanel — decisão 5: linha da cozinha que sai ou diminui cancela lá", () => {
  const sent = (overrides: Partial<POSCartItem> = {}) =>
    item({ sku: "CROISSANT", name: "Croissant", qty: 3, fired: true, fired_qty: 3, kitchen_status: "pending", ...overrides } as Partial<POSCartItem> & { sku: string; name: string });

  it("diminuir cancela na cozinha só a diferença e a coluna diz em palavra", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ items: [sent()] }) });
    await open(wrapper, "Croissant");
    await wrapper.find('[aria-label="Diminuir"]').trigger("click");
    expect(wrapper.emitted("decrement")).toEqual([["L-CROISSANT"]]);
    const [entries, done] = wrapper.emitted("cancelInKitchen")![0]! as [Array<{ lineId: string; units?: number }>, (ok: boolean) => void];
    expect(entries).toEqual([{ lineId: "L-CROISSANT", units: 1 }]);
    done(true);
    await wrapper.vm.$nextTick();
    expect(toastCalls.at(-1)![0]).toBe("1 Croissant cancelado na cozinha.");
    expect(wrapper.find("[data-pos-line-cancelled-units]").text()).toBe("1 cancelado na cozinha");
  });

  it("digitar menos numa linha enviada cancela a diferença (2 de 3)", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ items: [sent()] }), attachTo: document.body });
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "1", bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("setQty")).toEqual([["L-CROISSANT", 1]]);
    expect((wrapper.emitted("cancelInKitchen")![0]![0] as unknown[])).toEqual([{ lineId: "L-CROISSANT", units: 2 }]);
    (wrapper.emitted("cancelInKitchen")![0]![1] as (ok: boolean) => void)(true);
    expect(toastCalls.at(-1)![0]).toBe("2 Croissant cancelados na cozinha.");
  });

  it("remover uma linha enviada confirma 'Remover e cancelar na cozinha' e cancela a linha inteira", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ items: [sent()] }) });
    await open(wrapper, "Croissant");
    await wrapper.find("[data-pos-line-remove]").trigger("click");
    expect(document.body.textContent).toContain("sai da conta e é cancelado na cozinha");
    const confirm = Array.from(document.querySelectorAll("button")).find((b) => b.textContent?.includes("Remover e cancelar na cozinha"));
    (confirm as HTMLElement).click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("remove")).toEqual([["L-CROISSANT"]]);
    expect((wrapper.emitted("cancelInKitchen")![0]![0] as unknown[])).toEqual([{ lineId: "L-CROISSANT", units: undefined }]);
    (wrapper.emitted("cancelInKitchen")![0]![1] as (ok: boolean) => void)(true);
    const [message, options] = toastCalls.at(-1)!;
    expect(message).toBe("Croissant removido e cancelado na cozinha.");
    // Desfazer devolve a linha A ENVIAR: a cozinha já não a tem.
    options.action!.onClick();
    expect((wrapper.emitted("restore")![0]![0] as POSCartItem).fired).toBe(false);
  });

  it("item pronto sai só da conta, e a coluna diz isso", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ items: [sent({ kitchen_status: "done" })] }) });
    await open(wrapper, "Croissant");
    await wrapper.find('[aria-label="Diminuir"]').trigger("click");
    expect(wrapper.emitted("cancelInKitchen")).toBeUndefined();
    expect(toastCalls.at(-1)![0]).toBe("Croissant já estava pronto: saiu só da conta.");
  });

  it("se a cozinha não recebe, a coluna manda avisar de voz", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ items: [sent()] }) });
    await open(wrapper, "Croissant");
    await wrapper.find('[aria-label="Diminuir"]').trigger("click");
    (wrapper.emitted("cancelInKitchen")![0]![1] as (ok: boolean) => void)(false);
    expect(toastCalls.at(-1)![0]).toBe("Croissant saiu da conta, mas a cozinha não recebeu o cancelamento: avise de voz.");
  });
});
