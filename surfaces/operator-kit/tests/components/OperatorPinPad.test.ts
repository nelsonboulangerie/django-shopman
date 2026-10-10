// O PIN da suíte (`OperatorPinPad`): o campo desenha a regra (4 casas, até 8), o
// PIN não fica no DOM, as teclas falam com quem chama, e o teclado físico só é
// ouvido quando a peça é pedida para isso (`keyboard`).
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";

import OperatorPinPad from "../../app/components/OperatorPinPad.vue";

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;

async function mount(props: Record<string, unknown>) {
  mounted = await mountSuspended(OperatorPinPad, {
    props,
    attachTo: document.body,
    global: { stubs: { Icon: true } },
  });
  return mounted;
}

// As casas visíveis; o reka guarda o valor junto num campo escondido do formulário.
const boxes = (wrapper: Awaited<ReturnType<typeof mount>>) =>
  wrapper
    .findAll("[data-operator-pin-field] input")
    .filter((box) => box.attributes("aria-hidden") !== "true" && box.attributes("type") !== "hidden");

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
});

describe("OperatorPinPad", () => {
  it("o campo nasce com 4 casas, o mínimo do PIN", async () => {
    const wrapper = await mount({ pin: "" });
    expect(boxes(wrapper)).toHaveLength(4);
  });

  it("ganha uma casa por dígito além do quarto, e para no oitavo", async () => {
    const wrapper = await mount({ pin: "123456" });
    expect(boxes(wrapper)).toHaveLength(6);
    await wrapper.setProps({ pin: "1234567890" });
    expect(boxes(wrapper)).toHaveLength(8);
  });

  it("mostra bolinhas, nunca os dígitos", async () => {
    const wrapper = await mount({ pin: "2468" });
    const values = boxes(wrapper).map((box) => (box.element as HTMLInputElement).value);
    expect(values).toEqual(["●", "●", "●", "●"]);
    expect(wrapper.html()).not.toContain("2468");
  });

  it("o campo só mostra: não recebe foco nem abre o teclado do sistema", async () => {
    const wrapper = await mount({ pin: "" });
    for (const box of boxes(wrapper)) {
      expect((box.element as HTMLInputElement).disabled).toBe(true);
    }
  });

  it("as teclas da tela emitem o dígito, o apagar e o confirmar", async () => {
    const wrapper = await mount({ pin: "1234", canSubmit: true });
    const digit = wrapper.findAll("button").find((b) => b.text() === "7");
    await digit!.trigger("click");
    await wrapper.find('button[aria-label="Apagar o último dígito"]').trigger("click");
    await wrapper.find('button[aria-label="Confirmar"]').trigger("click");
    expect(wrapper.emitted("digit")).toEqual([["7"]]);
    expect(wrapper.emitted("backspace")).toHaveLength(1);
    expect(wrapper.emitted("submit")).toHaveLength(1);
  });

  it("confirmar fica preso enquanto não pode submeter", async () => {
    const wrapper = await mount({ pin: "12", canSubmit: false });
    const confirm = wrapper.find('button[aria-label="Confirmar"]');
    expect((confirm.element as HTMLButtonElement).disabled).toBe(true);
  });

  it("sem `keyboard`, não ouve o teclado físico (quem chama já captura)", async () => {
    const wrapper = await mount({ pin: "" });
    wrapper.element.dispatchEvent(new KeyboardEvent("keydown", { key: "5", bubbles: true }));
    expect(wrapper.emitted("digit")).toBeUndefined();
  });

  it("com `keyboard`, dígito, Backspace e Enter do teclado físico valem", async () => {
    const wrapper = await mount({ pin: "1234", canSubmit: true, keyboard: true });
    for (const key of ["5", "Backspace", "Enter"]) {
      wrapper.element.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
    }
    expect(wrapper.emitted("digit")).toEqual([["5"]]);
    expect(wrapper.emitted("backspace")).toHaveLength(1);
    expect(wrapper.emitted("submit")).toHaveLength(1);
  });
});

describe("OperatorPinPad dentro da moldura da trava", () => {
  it("ouve o teclado na moldura (o overlay com o foco), não no documento", async () => {
    const frame = document.createElement("div");
    frame.setAttribute("data-operator-lock", "");
    frame.tabIndex = -1;
    document.body.appendChild(frame);
    mounted = await mountSuspended(OperatorPinPad, {
      props: { pin: "", keyboard: true },
      attachTo: frame,
      global: { stubs: { Icon: true } },
    });
    const outside = new KeyboardEvent("keydown", { key: "3", bubbles: true, cancelable: true });
    document.body.dispatchEvent(outside);
    expect(mounted.emitted("digit")).toBeUndefined();
    const inside = new KeyboardEvent("keydown", { key: "3", bubbles: true, cancelable: true });
    frame.dispatchEvent(inside);
    expect(mounted.emitted("digit")).toEqual([["3"]]);
    expect(inside.defaultPrevented).toBe(true);
  });
});
