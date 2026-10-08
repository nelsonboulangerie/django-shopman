import { mountSuspended } from "@nuxt/test-utils/runtime";
import { DOMWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { VueWrapper } from "vue";

import OperatorReasonDialog from "../../app/components/OperatorReasonDialog.vue";

// O diálogo de motivo do kit, testado com o Modal, Alert, Select, Textarea e
// Button canônicos do Nuxt UI (o conteúdo é teleportado para document.body).

const mounted: VueWrapper[] = [];
async function mount(props: Record<string, unknown> = {}) {
  const wrapper = await mountSuspended(OperatorReasonDialog, {
    props: {
      open: true,
      title: "Cancelar a encomenda de Ana?",
      description: "O que já foi pago volta no mesmo meio.",
      confirmLabel: "Cancelar encomenda",
      ...props,
    },
    attachTo: document.body,
  });
  mounted.push(wrapper as unknown as VueWrapper);
  return wrapper;
}
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

const dom = (selector: string) => new DOMWrapper(document.querySelector(selector) as Element);
const domAll = (selector: string) => [...document.querySelectorAll<HTMLElement>(selector)].map((element) => new DOMWrapper(element));

const groups = [
  { label: "Produto", presets: ["Item indisponível no momento"] },
  { label: "", presets: ["Pedido em duplicidade"] },
];

describe("OperatorReasonDialog", () => {
  it("diz a consequência e confirma pelo rótulo de quem chama", async () => {
    const w = await mount();
    expect(document.body.textContent).toContain("O que já foi pago volta no mesmo meio.");
    const confirm = dom("[data-reason-confirm]");
    expect(confirm.text()).toBe("Cancelar encomenda");
    expect(confirm.attributes("disabled")).toBeUndefined();
    await dom("[data-reason-input]").setValue("  Cliente desistiu  ");
    await confirm.trigger("click");
    expect(w.emitted("confirm")).toEqual([[{ reason: "Cliente desistiu", code: "" }]]);
  });

  it("motivo exigido: confirmar em branco não sai", async () => {
    await mount({ required: true });
    expect(dom("[data-reason-confirm]").attributes("disabled")).toBeDefined();
    await dom("[data-reason-input]").setValue("Fora de área");
    expect(dom("[data-reason-confirm]").attributes("disabled")).toBeUndefined();
  });

  it("motivos prontos: um toque escolhe; Outros exige texto e nunca vira o motivo", async () => {
    const w = await mount({ presets: groups });
    const chips = domAll("[data-reason-preset]");
    expect(chips.map((c) => c.text())).toEqual(["Item indisponível no momento", "Pedido em duplicidade"]);
    await chips[1]!.trigger("click");
    expect(chips[1]!.attributes("aria-pressed")).toBe("true");
    await dom("[data-testid='reason-other']").trigger("click");
    expect(chips[1]!.attributes("aria-pressed")).toBe("false");
    expect(dom("[data-reason-confirm]").attributes("disabled")).toBeDefined();
    await dom("[data-reason-input]").setValue("Forno em manutenção hoje");
    await dom("[data-reason-confirm]").trigger("click");
    expect(w.emitted("confirm")).toEqual([[{ reason: "Forno em manutenção hoje", code: "" }]]);
  });

  it("motivo codificado: escolhe da lista e espelha a descrição no motivo", async () => {
    const w = await mount({ coded: true, codedReasons: [{ code: "B", description: "Loja fechada" }], presets: groups });
    expect(document.querySelector("[data-reason-input]")).toBeNull();
    expect(document.querySelector("[data-reason-preset]")).toBeNull();
    expect(dom("[data-reason-confirm]").attributes("disabled")).toBeDefined();
    await dom("[data-reason-code]").trigger("click");
    const option = domAll('[role="option"]').find((item) => item.text().includes("Loja fechada"))!;
    option.element.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0 }));
    option.element.dispatchEvent(new PointerEvent("pointerup", { bubbles: true, button: 0 }));
    (option.element as HTMLElement).click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    await dom("[data-reason-confirm]").trigger("click");
    expect(w.emitted("confirm")).toEqual([[{ reason: "Loja fechada", code: "B" }]]);
  });

  it("fechar com texto digitado pergunta dentro do diálogo, sem window.confirm", async () => {
    const nativeConfirm = vi.fn(() => true);
    vi.stubGlobal("confirm", nativeConfirm);
    const w = await mount();
    await dom("[data-reason-input]").setValue("Cliente desistiu");
    await dom("[data-reason-back]").trigger("click");
    expect(w.emitted("update:open")).toBeUndefined();
    expect(document.querySelector("[data-reason-discard]")).not.toBeNull();
    await dom("[data-reason-keep]").trigger("click");
    expect((dom("[data-reason-input]").element as HTMLTextAreaElement).value).toBe("Cliente desistiu");
    await dom("[data-reason-back]").trigger("click");
    await dom("[data-reason-discard-confirm]").trigger("click");
    expect(w.emitted("update:open")).toEqual([[false]]);
    expect(nativeConfirm).not.toHaveBeenCalled();
  });

  it("ocupado: não fecha nem confirma de novo", async () => {
    const w = await mount({ busy: true });
    await dom("[data-reason-back]").trigger("click");
    await dom("[data-reason-confirm]").trigger("click");
    expect(w.emitted("update:open")).toBeUndefined();
    expect(w.emitted("confirm")).toBeUndefined();
  });

  it("erro ao ler os motivos: bloqueia e oferece consultar de novo", async () => {
    const w = await mount({ error: "Não foi possível consultar os motivos." });
    expect(document.body.textContent).toContain("Não foi possível consultar os motivos.");
    expect(dom("[data-reason-confirm]").attributes("disabled")).toBeDefined();
    await domAll("button").find((button) => button.text() === "Consultar novamente")!.trigger("click");
    expect(w.emitted("retry")).toHaveLength(1);
  });
});
