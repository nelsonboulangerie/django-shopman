// WP-G07 + WP-G08: o diálogo do "Avisar o cliente" aberto a partir do "Resolver" da
// promessa em risco traz o aviso sugerido e os itens em risco já marcados, para
// conferir. Pelo menu, nada vem marcado.
import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { flushPromises, mount } from "@vue/test-utils";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import OrderCustomerNoticeDialog from "../../app/components/OrderCustomerNoticeDialog.vue";
import type { CustomerNoticeOptions } from "../../app/presentation/customerNotice";

const env = installNuxtGlobals();
vi.stubGlobal("useSonner", { error: vi.fn(), success: vi.fn(), info: vi.fn() });

const REF = "WEB-2611-G8G-N75";

function options(over: Partial<Record<string, boolean>> = {}): CustomerNoticeOptions {
  const line = (line_id: string, name: string) => ({ line_id, name, qty: "2", qty_display: "2 unidades" });
  return {
    ref: REF,
    payload_schema: {},
    notices: [
      { kind: "delayed", label: "Vai atrasar", enabled: over.delayed ?? true, reason: "", delay_choices: [], lines: [] },
      {
        kind: "item_missing", label: "Faltou um item", enabled: over.item_missing ?? true, reason: "",
        delay_choices: [], lines: [line("L1", "Focaccia"), line("L2", "Croissant")],
      },
      { kind: "reschedule", label: "Precisamos remarcar", enabled: over.reschedule ?? false, reason: "Só a encomenda tem data combinada para remarcar.", delay_choices: [], lines: [] },
    ],
  } as unknown as CustomerNoticeOptions;
}

// Os grupos mostram o que está marcado: é o que se confere aqui.
const radioGroup = defineComponent({
  name: "NuxtRadioGroup",
  inheritAttrs: false,
  props: { modelValue: { type: String, default: "" } },
  setup(props, { attrs }) {
    return () => h("div", { ...attrs, "data-picked": props.modelValue });
  },
});
const checkboxGroup = defineComponent({
  name: "NuxtCheckboxGroup",
  inheritAttrs: false,
  props: { modelValue: { type: Array as () => string[], default: () => [] } },
  setup(props, { attrs }) {
    return () => h("div", { ...attrs, "data-picked": props.modelValue.join(",") });
  },
});
const stubs = { Icon: true, OperatorScreenState: true, NuxtRadioGroup: radioGroup, NuxtCheckboxGroup: checkboxGroup };

async function opened(read: CustomerNoticeOptions, props: Record<string, unknown> = {}) {
  env.fetchMock.mockResolvedValueOnce(read);
  env.fetchMock.mockResolvedValue({ kind: "item_missing", status_note: "Focaccia (2 unidades)", message: "Oi, Nelson!" });
  const w = mount(OrderCustomerNoticeDialog, {
    props: { open: true, orderRef: REF, ...props },
    global: { stubs },
  });
  await flushPromises();
  return w;
}

beforeEach(() => env.reset());

describe("OrderCustomerNoticeDialog: aberto pelo Resolver", () => {
  it("o aviso sugerido e os itens em risco vêm marcados", async () => {
    const w = await opened(options(), { initialKind: "item_missing", initialLines: ["L1"] });
    expect(w.get("[data-notice-kinds]").attributes("data-picked")).toBe("item_missing");
    expect(w.get("[data-notice-lines]").attributes("data-picked")).toBe("L1");
  });

  it("linha que não é deste pedido não se marca", async () => {
    const w = await opened(options(), { initialKind: "item_missing", initialLines: ["L1", "SUMIU"] });
    expect(w.get("[data-notice-lines]").attributes("data-picked")).toBe("L1");
  });

  it("o aviso sugerido que não cabe agora não vem marcado", async () => {
    const w = await opened(options(), { initialKind: "reschedule", initialLines: [] });
    expect(w.get("[data-notice-kinds]").attributes("data-picked")).toBe("");
  });

  it("pelo menu, nada vem marcado", async () => {
    const w = await opened(options());
    expect(w.get("[data-notice-kinds]").attributes("data-picked")).toBe("");
    expect(w.find("[data-notice-lines]").exists()).toBe(false);
  });
});
