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
async function mark(wrapper: Wrapper, lineId: string, shiftKey = false) {
  await wrapper.find(`[data-pos-line-mark="${lineId}"]`).trigger("click", { shiftKey });
}
const block = (wrapper: Wrapper) => wrapper.find("[data-pos-line-editor]");

describe("PosCartPanel — marcar sem modo", () => {
  it("não há botão Selecionar nem cabeçalho trocado: o cabeçalho é sempre o da comanda", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    expect(wrapper.find("[data-pos-select-lines]").exists()).toBe(false);
    await mark(wrapper, "L-PAO");
    expect(wrapper.find("[data-pos-selection-bar]").exists()).toBe(false);
    expect(wrapper.find("[data-pos-ticket-header]").text()).toContain("4 itens");
  });

  it("a linha aberta é a primeira marcada: marcar outra vira o bloco de N com o objeto no título", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    // No balcão o editor nasce aberto na última lançada (Café).
    expect(block(wrapper).attributes("data-pos-block")).toBe("line");
    await mark(wrapper, "L-PAO");
    expect(block(wrapper).attributes("data-pos-block")).toBe("marked");
    expect(wrapper.find("[data-pos-marked-title]").text()).toBe(`2 linhas marcadas · 3 itens · ${formatBRL(1100)}`);
    expect(wrapper.find('[data-pos-line-mark="L-CAFE"]').exists()).toBe(true);
    expect(wrapper.findAll("[data-pos-line-marked]")).toHaveLength(2);
  });

  it("as posições não mudam: Transferir no canto da quantidade, Remover, Desconto e Observação no mesmo lugar", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    const cells = () => wrapper.findAll("[data-pos-controls-block] [data-pos-control-cell]").map((c) => c.attributes("data-pos-control-cell"));
    expect(cells()).toEqual(["qty", "remove", "discount", "note", "fire", "split"]);
    await mark(wrapper, "L-PAO");
    expect(cells()).toEqual(["move", "remove", "discount", "note", "fire", "split"]);
  });

  it("desmarcar até sobrar uma volta ao editor dela", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await mark(wrapper, "L-PAO");
    await mark(wrapper, "L-QUICHE");
    expect(wrapper.find("[data-pos-marked-title]").text()).toContain("3 linhas marcadas");
    await mark(wrapper, "L-CAFE");
    await mark(wrapper, "L-PAO");
    expect(block(wrapper).attributes("data-pos-block")).toBe("line");
    expect(wrapper.find("[data-pos-line-editor-title]").text()).toContain("Quiche");
  });

  it("Shift + clique marca o intervalo; Esc desmarca tudo", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props(), attachTo: document.body });
    await wrapper.find('[data-item-select="L-PAO"]').trigger("click");
    await mark(wrapper, "L-CAFE", true);
    expect(wrapper.find("[data-pos-marked-title]").text()).toContain("3 linhas marcadas");
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll("[data-pos-line-marked]")).toHaveLength(0);
    expect(block(wrapper).attributes("data-pos-block")).toBe("line");
  });

  it("Espaço na linha em foco marca, como a caixa", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper.find('[data-item-select="L-PAO"]').trigger("keydown", { key: " " });
    expect(wrapper.findAll("[data-pos-line-marked]")).toHaveLength(2);
  });

  it("com marcas, clicar numa linha marca (não joga as marcas fora)", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await mark(wrapper, "L-PAO");
    await wrapper.find('[data-item-select="L-QUICHE"]').trigger("click");
    expect(wrapper.findAll("[data-pos-line-marked]")).toHaveLength(3);
  });

  it("com marcas, um dígito não faz nada (a quantidade é de uma linha)", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props(), attachTo: document.body });
    await mark(wrapper, "L-PAO");
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "3", bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("setQty")).toBeUndefined();
    expect(wrapper.find("[data-pos-discount-panel]").exists()).toBe(false);
  });
});

describe("PosCartPanel — o pé segue o foco; o Pagamento não", () => {
  it("com marcas, Enviar diz 'Enviar N marcadas' e envia só elas; o Pagamento segue a comanda inteira", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await mark(wrapper, "L-PAO");
    const fire = wrapper.find("[data-pos-fire]");
    expect(fire.text()).toContain("Enviar 2 marcadas");
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
    expect(vm.fireSelection()).toBe(true);
    expect(wrapper.emitted("fireLines")).toHaveLength(1);
    expect(vm.moveSelection()).toBe(true);
    expect(wrapper.emitted("move")?.[0]).toEqual([["L-PAO", "L-CAFE"], "transfer"]);
  });

  it("ato em lote concluído limpa as marcas; no erro, ficam", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await mark(wrapper, "L-PAO");
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
    expect(wrapper.find("[data-pos-fire]").text()).toContain("Marcadas já enviadas");
    expect(wrapper.find("[data-pos-fire]").attributes("disabled")).toBeDefined();
  });

  it("Remover N confirma E oferece Desfazer, como remover 1", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await mark(wrapper, "L-PAO");
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
    await wrapper.find("[data-pos-line-note]").trigger("click");
    expect(wrapper.find("[data-pos-note-help]").text()).toContain("2 linhas marcadas");
    await wrapper.find("[data-pos-note-panel] textarea").setValue("para viagem");
    await wrapper.find("[data-pos-edit-apply]").trigger("click");
    expect(wrapper.emitted("setNotes")).toEqual([["L-PAO", "para viagem"], ["L-CAFE", "para viagem"]]);
  });

  it("o envio automático espera o rascunho e as marcas", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    const last = () => wrapper.emitted("autoFireHold")!.at(-1)![0];
    expect(last()).toBe(false);
    await mark(wrapper, "L-PAO");
    expect(last()).toBe(true);
  });
});

describe("PosCartPanel — a porta da comanda e as do raro", () => {
  it("o cabeçalho tem 'Comanda ⋯' (Transferir itens, Juntar, Liberar); some na edição de encomenda", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    expect(wrapper.find("[data-pos-tab-menu]").exists()).toBe(true);
    const editing = await mountSuspended(PosCartPanel, { props: props({ primaryLabel: "Salvar alterações", hideMove: true }) });
    expect(editing.find("[data-pos-tab-menu]").exists()).toBe(false);
  });

  it("a linha aberta tem ⋯ com o raro dela; a expansão só lê", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    expect(wrapper.find("[data-pos-line-menu]").exists()).toBe(true);
    await wrapper.find('[data-item-select="L-CAFE"]').trigger("keydown", { key: "ArrowRight" });
    expect(wrapper.find('[role="region"]').findAll("button")).toHaveLength(0);
  });
});

describe("PosCartPanel — a linha que já está na cozinha", () => {
  const fired = [item({ sku: "CROISSANT", name: "Croissant", fired: true, kitchen_status: "pending" } as Partial<POSCartItem> & { sku: string; name: string })];

  it("+ numa linha enviada vai numa linha NOVA, a enviar, e o editor segue a nova", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ items: fired }) });
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
    expect(wrapper.find("[data-pos-kitchen-offline]").text()).toContain("cozinha sem conexão");
    expect(wrapper.find("[data-pos-fire]").attributes("disabled")).toBeDefined();
    expect(wrapper.find("[data-pos-line-discount]").attributes("disabled")).toBeDefined();
    expect(wrapper.find("[data-pos-block-offline]").text()).toContain("desconto volta com a conexão");
    expect(wrapper.find("[data-pos-line-note]").attributes("disabled")).toBeUndefined();
    expect(wrapper.find('[aria-label="Aumentar"]').attributes("disabled")).toBeUndefined();
  });
});

describe("PosCartPanel — envio automático com o quando", () => {
  it("ligado: o cabeçalho diz quando vai, e a linha diz que vai sozinha", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ autoFire: true, autoFireSkus: ["PAO"], kitchenStations: { PAO: "Forno", CAFE: "Bar" } }),
    });
    expect(wrapper.find("[data-pos-auto-fire]").attributes("aria-label")).toBe("envio automático: ao sair ou após 90 s parada");
    expect(wrapper.text()).toContain("vai sozinho");
    expect(wrapper.text()).toContain("vai à cozinha");
  });
});
