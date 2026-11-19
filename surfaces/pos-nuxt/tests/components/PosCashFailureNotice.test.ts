// O erro do gesto de caixa mora DENTRO do diálogo (WP-E6, auditoria da prévia): o
// toast nascia atrás do véu do diálogo "Saída de caixa", apagado. Aqui: aparece na
// falha, é `role="alert"`, tem X, e some quando a repetição confirma.
import { computed, defineComponent, h } from "vue";
import { describe, expect, it, vi } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosCashFailureNotice from "~/components/PosCashFailureNotice.vue";
import { usePosCashSession } from "~/composables/usePosCashSession";

import { makeProjection } from "../composables/_posSaleHarness";

// `importOriginal` mantém o `Toaster` (o shell o monta); só o `toast` é espionado.
vi.mock("vue-sonner", async (importOriginal) => ({
  ...(await importOriginal<typeof import("vue-sonner")>()),
  toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn(), dismiss: vi.fn() },
}));

const MESSAGE = "O movimento não entrou no livro-caixa. A gaveta não abriu e o valor segue na tela. Tente de novo agora: a mesma tentativa não vira dois lançamentos.";

describe("PosCashFailureNotice", () => {
  it("mostra a falha do próprio gesto como alerta, com X que dispensa", async () => {
    const wrapper = await mountSuspended(PosCashFailureNotice, {
      props: { failure: { gesture: "movement", message: MESSAGE }, gesture: "movement" },
    });
    const notice = wrapper.get("[data-cash-failure]");
    expect(notice.attributes("role")).toBe("alert");
    expect(notice.text()).toContain("O movimento não entrou no livro-caixa.");
    const close = notice.find("button");
    expect(close.exists()).toBe(true);
    await close.trigger("click");
    expect(wrapper.emitted("dismiss")).toHaveLength(1);
  });

  it("não mostra a falha de OUTRO gesto, nem nada sem falha", async () => {
    const other = await mountSuspended(PosCashFailureNotice, {
      props: { failure: { gesture: "close_shift", message: "O caixa não fechou." }, gesture: "movement" },
    });
    expect(other.find("[data-cash-failure]").exists()).toBe(false);
    const none = await mountSuspended(PosCashFailureNotice, { props: { failure: null, gesture: "movement" } });
    expect(none.find("[data-cash-failure]").exists()).toBe(false);
  });

  it("aparece na falha da saída e some quando a repetição confirma", async () => {
    const actionCall = vi
      .fn()
      .mockRejectedValueOnce(new Error("rede caiu"))
      .mockResolvedValueOnce({ entry_id: 9 })
      .mockResolvedValue({ payload_b64: "", title: "" });
    let session!: ReturnType<typeof usePosCashSession>;
    const Host = defineComponent({
      setup() {
        session = usePosCashSession({
          pos: computed(() => makeProjection()),
          actions: computed(() => []),
          refresh: vi.fn().mockResolvedValue(undefined),
          action: { call: actionCall },
        });
        return () =>
          h(PosCashFailureNotice, {
            failure: session.cashFailure.value,
            gesture: "movement",
            onDismiss: session.dismissCashFailure,
          });
      },
    });
    const wrapper = await mountSuspended(Host);
    const movement = { kind: "sangria", amount: "50,00", reason: "Sangria" };

    await session.registerCashMovement(movement);
    await wrapper.vm.$nextTick();
    expect(wrapper.get("[data-cash-failure]").text()).toContain("Tente de novo agora");

    await session.registerCashMovement(movement);
    await wrapper.vm.$nextTick();
    expect(wrapper.find("[data-cash-failure]").exists()).toBe(false);
  });
});
