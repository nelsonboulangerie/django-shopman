import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, defineComponent, h, nextTick, ref, watch } from "vue";
import { flushPromises, mount } from "@vue/test-utils";

import ShortageDialog from "../../app/components/ShortageDialog.vue";
import type { ProductionShortageError } from "../../app/types/production";
import { nuxtUiStubs } from "../support/nuxtUiStubs";

// WP-F11 (P1-14, P1-24): a falta de insumo diz o quê e quanto na medida da
// bancada, avisa na abertura sem travar, e no fechamento sai pela assinatura da
// lista com PIN (decisão 3 do dono, D-042), nunca por texto livre.
const authorizeProductionShortage = vi.fn();
vi.mock("~/generated/productionContract", () => ({
  authorizeProductionShortage: (...args: unknown[]) => authorizeProductionShortage(...args),
}));

const butter = {
  sku: "INS-MANTEIGA",
  name: "Manteiga",
  unit: "kg",
  needed: "1",
  available: "0.7",
  shortage: "0.3",
  shortage_display: "300 g",
  needed_display: "1000 g",
  available_display: "700 g",
  produced_here: false,
};

function materialShortage(
  stage: "start" | "finish",
  extra: Partial<Record<string, unknown>> = {},
): ProductionShortageError {
  return {
    code: "material_shortage",
    stage,
    work_order_ref: "WO-2026-00022",
    idempotency_key: "k",
    possibilities: [
      { kind: "retry", label: stage === "start" ? "Revisar quantidade" : "Tentar novamente", enabled: true, proof: "", href: "" },
      { kind: "purchase", label: "Pedir no Compras", enabled: true, proof: "", href: "https://compras.test" },
      ...(stage === "start"
        ? [{ kind: "confirm", label: "Abrir assim mesmo", enabled: true, proof: "aviso-assinado", href: "" }]
        : []),
    ],
    missing: [butter],
    authorizers: [],
    ...extra,
  } as unknown as ProductionShortageError;
}

const withAuthorizer = (): ProductionShortageError =>
  materialShortage("finish", {
    possibilities: [
      { kind: "retry", label: "Tentar novamente", enabled: true, proof: "", href: "" },
      { kind: "force", label: "Fechar com autorização", enabled: true, proof: "falta-assinada", href: "" },
    ],
    authorizers: [{ id: 7, username: "joyce", name: "Joyce", pin_digits: 4 }],
  });

const ManagerAuthStub = defineComponent({
  name: "OperatorManagerAuth",
  props: ["open", "action", "detail", "operatorName", "managers", "busy", "error"],
  emits: ["update:open", "authorize", "authorizeBadge"],
  setup(props, { slots }) {
    return () =>
      props.open ? h("div", { "data-auth": "" }, [slots.context?.(), h("p", { "data-auth-error": "" }, props.error)]) : null;
  },
});

beforeEach(() => {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("watch", watch);
  vi.stubGlobal("useOperatorAppLink", () => ({ attrsFor: () => ({ target: "_blank", rel: "noopener" }) }));
  vi.stubGlobal("useNuxtData", () => ({ data: ref({ operator: { name: "Diofer" } }) }));
  vi.stubGlobal("httpErrorMessage", (err: { message?: string }, fallback: string) => err?.message || fallback);
  authorizeProductionShortage.mockReset();
});
afterEach(() => vi.unstubAllGlobals());

function mountDialog(shortage: ProductionShortageError | null) {
  return mount(ShortageDialog, {
    props: { shortage },
    global: { stubs: { ...nuxtUiStubs, OperatorManagerAuth: ManagerAuthStub } },
  });
}

describe("ShortageDialog — falta de insumo na abertura (aviso)", () => {
  it("diz quanto falta de quê, na medida da bancada", () => {
    const wrapper = mountDialog(materialShortage("start"));
    const item = wrapper.get("[data-shortage-item]").text().replace(/\s+/g, " ");

    expect(item).toContain("Falta 300 g de manteiga");
    expect(item).toContain("precisa 1000 g · tem 700 g");
    expect(item).not.toContain("INS-MANTEIGA");
    expect(wrapper.findComponent({ name: "NuxtModal" }).props("title")).toBe("Falta insumo para este lote");
  });

  it("oferece Pedir no Compras e Abrir assim mesmo, e abrir devolve a prova", async () => {
    const wrapper = mountDialog(materialShortage("start"));

    expect(wrapper.get("[data-shortage-purchase]").attributes("href")).toBe("https://compras.test");
    expect(wrapper.get("[data-shortage-open-anyway]").text()).toBe("Abrir assim mesmo");
    await wrapper.get("[data-shortage-open-anyway]").trigger("click");
    await wrapper.get("[data-shortage-review]").trigger("click");

    expect(wrapper.emitted("open-anyway")).toEqual([["aviso-assinado"]]);
    expect(wrapper.emitted("review")).toHaveLength(1);
    expect(wrapper.find("textarea").exists()).toBe(false);
    expect(wrapper.find("[data-shortage-authorize]").exists()).toBe(false);
  });
});

describe("ShortageDialog — o que a casa produz não se pede ao Compras", () => {
  it("massa em falta: a frase fala em produzir, sem Compras", () => {
    const massa = { ...butter, sku: "MASSA-CIABATTA", name: "Massa de ciabatta", produced_here: true };
    const opening = mountDialog(
      materialShortage("start", {
        missing: [massa],
        possibilities: [
          { kind: "retry", label: "Revisar quantidade", enabled: true, proof: "", href: "" },
          { kind: "confirm", label: "Abrir assim mesmo", enabled: true, proof: "p", href: "" },
        ],
      }),
    );
    expect(opening.get("[data-shortage-item]").text()).toContain("Falta 300 g de massa de ciabatta");
    expect(opening.findComponent({ name: "NuxtModal" }).props("description")).toContain("o que falta entra no estoque");
    expect(opening.findComponent({ name: "NuxtModal" }).props("description")).not.toContain("Compras");

    const closing = mountDialog(materialShortage("finish", { missing: [massa], possibilities: [] }));
    expect(closing.findComponent({ name: "NuxtModal" }).props("description")).toBe(
      "O estoque não tem o que este lote consome. Produza o que falta e tente de novo.",
    );
  });
});

describe("ShortageDialog — falta de insumo no fechamento (assinatura)", () => {
  it("sem quem autorize, não há campo de texto livre nem botão de forçar", () => {
    const wrapper = mountDialog(materialShortage("finish"));
    const modal = wrapper.findComponent({ name: "NuxtModal" });

    expect(modal.props("title")).toBe("Falta insumo para fechar");
    expect(modal.props("description")).toContain("Compras");
    expect(wrapper.find("textarea").exists()).toBe(false);
    expect(wrapper.find("[data-shortage-authorize]").exists()).toBe(false);
    expect(wrapper.find("[data-shortage-open-anyway]").exists()).toBe(false);
  });

  it("a Gerente escolhe o nome, assina com o PIN e o lote segue com a prova assinada", async () => {
    authorizeProductionShortage.mockResolvedValue({ override_proof: "com-joyce", authorizer_name: "Joyce" });
    const wrapper = mountDialog(withAuthorizer());

    expect(wrapper.find("textarea").exists()).toBe(false);
    await wrapper.get("[data-shortage-authorize]").trigger("click");
    const auth = wrapper.findComponent(ManagerAuthStub);
    expect(auth.props("managers")).toEqual([{ id: 7, username: "joyce", name: "Joyce", pin_digits: 4 }]);
    expect(auth.props("operatorName")).toBe("Diofer");
    expect(auth.props("action")).toBe("production_shortage");
    expect(auth.props("detail")).toBe("Falta 300 g de manteiga.");

    auth.vm.$emit("authorize", "joyce", "2468");
    await flushPromises();

    expect(authorizeProductionShortage).toHaveBeenCalledWith({
      override_proof: "falta-assinada",
      username: "joyce",
      pin: "2468",
    });
    expect(wrapper.emitted("confirm")).toEqual([["Autorizado por Joyce, com PIN.", "com-joyce"]]);
  });

  it("PIN errado fica na tela de quem autoriza, com a frase do servidor", async () => {
    authorizeProductionShortage.mockRejectedValue({ message: "PIN incorreto. Restam 4 tentativas antes da trava." });
    const wrapper = mountDialog(withAuthorizer());
    await wrapper.get("[data-shortage-authorize]").trigger("click");

    wrapper.findComponent(ManagerAuthStub).vm.$emit("authorize", "joyce", "1111");
    await flushPromises();

    expect(wrapper.emitted("confirm")).toBeUndefined();
    expect(wrapper.get("[data-auth-error]").text()).toBe("PIN incorreto. Restam 4 tentativas antes da trava.");
  });

  it("o crachá também assina", async () => {
    authorizeProductionShortage.mockResolvedValue({ override_proof: "cracha", authorizer_name: "Joyce" });
    const wrapper = mountDialog(withAuthorizer());
    await wrapper.get("[data-shortage-authorize]").trigger("click");

    wrapper.findComponent(ManagerAuthStub).vm.$emit("authorizeBadge", "TOKEN");
    await flushPromises();

    expect(authorizeProductionShortage).toHaveBeenCalledWith({ override_proof: "falta-assinada", badge: "TOKEN" });
    expect(wrapper.emitted("confirm")?.[0]?.[1]).toBe("cracha");
  });

  it("ao fechar, título e frase continuam os do último envelope", async () => {
    const wrapper = mountDialog(materialShortage("finish"));
    const modal = wrapper.findComponent({ name: "NuxtModal" });

    await wrapper.setProps({ shortage: null });
    await nextTick();

    expect(modal.props("title")).toBe("Falta insumo para fechar");
    expect(modal.props("description")).not.toContain("undefined");
  });
});

// WP-F06 (decisão 1 do dono, 23/11/2026): rendeu menos que o encomendado, o lote
// fecha com a verdade. Antes a tela mandava "informar pelo menos 6.000 un." e o
// "Revisar quantidade" não fazia nada.
const shortLot = {
  code: "order_shortage",
  work_order_ref: "WO-2026-00034",
  idempotency_key: "k",
  possibilities: [
    { kind: "retry", label: "Revisar quantidade", enabled: true, proof: "" },
    { kind: "confirm", label: "Fechar com 4", enabled: true, proof: "assinada" },
  ],
  required: "6.000",
  requested: "4.000",
  order_refs: ["NB-261123-B57"],
  orders: [{ ref: "NB-261123-B57", qty: "6" }],
} as unknown as ProductionShortageError;

describe("ShortageDialog — o lote curto fecha com a verdade", () => {
  function mountShortLot(allowShortLot: boolean) {
    return mount(ShortageDialog, {
      props: { shortage: shortLot, allowShortLot },
      global: { stubs: { ...nuxtUiStubs, OperatorManagerAuth: ManagerAuthStub } },
    });
  }

  it("diz quanto rendeu, quanto falta e quem fica descoberto", () => {
    const wrapper = mountShortLot(true);
    const modal = wrapper.findComponent({ name: "NuxtModal" });

    expect(modal.props("title")).toBe("Rendeu menos que o encomendado");
    expect(modal.props("description")).toBe("Rendeu 4. Faltam 2 para as encomendas.");
    const order = wrapper.get("[data-short-lot-order]");
    expect(order.findAll("span").map((span) => span.text())).toEqual(["NB-261123-B57", "6 un."]);
    // Só o que é sempre verdade: a lista e o aviso ao Gestor saem de réguas diferentes
    // até o WP-F08 (#3457), então a tela não promete o aviso.
    expect(wrapper.get("[data-short-lot-outcome]").text()).toBe("O lote fecha com 4 e o pão entra no estoque.");
    expect(wrapper.html()).not.toContain("Promessa em risco");
    expect(wrapper.html()).not.toContain("pelo menos");
  });

  it("fecha com a prova da recusa, e revisar devolve à contagem", async () => {
    const wrapper = mountShortLot(true);

    expect(wrapper.get("[data-short-lot-confirm]").text()).toBe("Fechar com 4");
    await wrapper.get("[data-short-lot-confirm]").trigger("click");
    await wrapper.get("[data-short-lot-review]").trigger("click");

    expect(wrapper.emitted("close-short-lot")).toEqual([["assinada"]]);
    expect(wrapper.emitted("review")).toHaveLength(1);
  });

  it("uma unidade e um pedido no singular", () => {
    const wrapper = mount(ShortageDialog, {
      props: { shortage: { ...shortLot, required: "2", requested: "1" } as ProductionShortageError, allowShortLot: true },
      global: { stubs: { ...nuxtUiStubs, OperatorManagerAuth: ManagerAuthStub } },
    });

    expect(wrapper.findComponent({ name: "NuxtModal" }).props("description")).toBe("Rendeu 1. Falta 1 para as encomendas.");
    expect(wrapper.get("[data-short-lot-outcome]").text()).toBe("O lote fecha com 1 e o pão entra no estoque.");
  });

  it("rendeu zero: não diz que o pão entra no estoque", () => {
    const wrapper = mount(ShortageDialog, {
      props: { shortage: { ...shortLot, requested: "0" } as ProductionShortageError, allowShortLot: true },
      global: { stubs: { ...nuxtUiStubs, OperatorManagerAuth: ManagerAuthStub } },
    });

    expect(wrapper.findComponent({ name: "NuxtModal" }).props("description")).toBe("Rendeu 0. Faltam 6 para as encomendas.");
    expect(wrapper.get("[data-short-lot-outcome]").text()).toBe("O lote fecha sem nada para o estoque.");
  });

  it("a tela que não sabe fechar o lote curto não oferece o botão", () => {
    const wrapper = mountShortLot(false);

    expect(wrapper.find("[data-short-lot-confirm]").exists()).toBe(false);
    expect(wrapper.findComponent({ name: "NuxtModal" }).props("title")).toBe("Quantidade não cobre pedidos");
  });
});
