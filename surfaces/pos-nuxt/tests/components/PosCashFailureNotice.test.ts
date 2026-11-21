// O erro do gesto de caixa mora DENTRO do diálogo (WP-E6, auditoria da prévia): o
// toast nascia atrás do véu do diálogo "Saída de caixa", apagado. Aqui: aparece na
// falha, é `role="alert"`, tem X, e some quando a repetição confirma.
import { computed, defineComponent, h } from "vue";
import { describe, expect, it, vi } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { flushPromises } from "@vue/test-utils";

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

  it("traz o botão que resolve: tocar repete o gesto, e ele espera junto", async () => {
    // Regra do dono (20/11): o aviso traz a ação pronta, nunca só o caminho escrito.
    const wrapper = await mountSuspended(PosCashFailureNotice, {
      props: {
        failure: { gesture: "request_change", message: "O pedido de troco não foi enviado. Ninguém foi avisado ainda. Tente de novo." },
        gesture: "request_change",
        actionLabel: "Tentar de novo",
      },
    });
    const notice = wrapper.get("[data-cash-failure]");
    const retry = notice.findAll("button").find((b) => b.text().includes("Tentar de novo"));
    expect(retry, "o aviso não traz o botão que resolve").toBeTruthy();
    await retry!.trigger("click");
    expect(wrapper.emitted("action")).toHaveLength(1);

    await wrapper.setProps({ busy: true });
    const waiting = wrapper.get("[data-cash-failure]").findAll("button").find((b) => b.text().includes("Tentar de novo"));
    expect(waiting!.attributes("disabled")).toBeDefined();
  });

  it("a falha traz o foco para o botão que resolve", async () => {
    // O botão do gesto se desabilita enquanto corre, e o navegador joga o foco no
    // `body`: sem isto, o teclado perdia o lugar fora do diálogo.
    const wrapper = await mountSuspended(PosCashFailureNotice, {
      props: { failure: null, gesture: "settle_account", actionLabel: "Tentar de novo" },
      attachTo: document.body,
    });
    await wrapper.setProps({ failure: { gesture: "settle_account", message: "O acerto não foi registrado. Tente de novo agora." } });
    await flushPromises();
    expect(document.activeElement?.textContent).toContain("Tentar de novo");
    wrapper.unmount();
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
