import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick, ref } from "vue";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { useNextFocus, type RevealTarget } from "../../app/composables/useNextFocus";
import type { RevealOptions } from "../../app/presentation/nextFocus";

// O mecanismo de próximo foco, exercitado no DOM (happy-dom): a página declara
// a chave, os blocos se marcam, e o composable rola + foca. O `scrollIntoView`
// é a fronteira com o browser — espionado, não simulado.
// Espelha a suíte do storefront (tests/composables/useNextFocus.test.ts).

interface Harness {
  key: { value: string | null };
  reveal: (target: RevealTarget, options?: RevealOptions) => void;
  unmount: () => void;
}

async function mountFocusPage(initialKey: string | null, options: RevealOptions = {}): Promise<Harness> {
  const key = ref<string | null>(initialKey);
  let api!: ReturnType<typeof useNextFocus>;
  const Page = defineComponent({
    setup() {
      api = useNextFocus(key, options);
      return () =>
        h("main", [
          h("section", { "data-focus-target": "customer", tabindex: "-1" }, [
            h("input", { id: "phone", "data-focus-control": "" }),
          ]),
          h("section", { "data-focus-target": "payment" }, [h("button", { id: "pix" }, "Pix")]),
          h("p", { id: "error", role: "alert" }, "Escolha a forma de pagamento."),
        ]);
    },
  });
  const wrapper = await mountSuspended(Page, { attachTo: document.body });
  await nextTick();
  return { key, reveal: api.reveal, unmount: () => wrapper.unmount() };
}

// O reveal é agendado pelo watcher pós-render e corre no tick seguinte ao
// flush: dois ticks garantem que a página já reagiu (ou não reagiu) à chave.
async function settle() {
  await nextTick();
  await nextTick();
}

let scrolledSpy: ReturnType<typeof vi.fn>;

function lastScroll() {
  const call = scrolledSpy.mock.calls.at(-1);
  return call
    ? { element: scrolledSpy.mock.contexts.at(-1) as Element, options: call[0] as ScrollIntoViewOptions }
    : null;
}

function withReducedMotion(reduced: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: reduced && query.includes("prefers-reduced-motion"),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

beforeEach(() => {
  scrolledSpy = vi.fn();
  Element.prototype.scrollIntoView = scrolledSpy as unknown as Element["scrollIntoView"];
  withReducedMotion(false);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

describe("useNextFocus — a página segue o foco", () => {
  it("quando a chave muda, leva o bloco à linha de foco e o foca", async () => {
    const page = await mountFocusPage("customer");
    scrolledSpy.mockClear();

    page.key.value = "payment";
    await settle();

    const payment = document.querySelector('[data-focus-target="payment"]')!;
    expect(lastScroll()).toEqual({ element: payment, options: { block: "start", behavior: "smooth" } });
    // Bloco sem controle marcado: o próprio bloco vira focável e recebe o foco,
    // para o leitor de tela anunciar a seção.
    expect(payment.getAttribute("tabindex")).toBe("-1");
    expect(document.activeElement).toBe(payment);
    page.unmount();
  });

  it("bloco com data-focus-control entrega o foco ao controle (a próxima ação é digitar)", async () => {
    const page = await mountFocusPage("payment");

    page.key.value = "customer";
    await settle();

    expect(document.activeElement?.id).toBe("phone");
    expect(lastScroll()?.element).toBe(document.querySelector('[data-focus-target="customer"]'));
    page.unmount();
  });

  it("na montagem não salta se o bloco já está inteiro na área visível", async () => {
    // happy-dom mede tudo em 0×0 no topo: visível. Nada de rolagem ao chegar.
    const page = await mountFocusPage("payment");
    expect(scrolledSpy).not.toHaveBeenCalled();
    expect(document.activeElement).not.toBe(document.querySelector('[data-focus-target="payment"]'));
    page.unmount();
  });

  it("na montagem rola se o foco está fora da área visível (estado restaurado lá embaixo)", async () => {
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
      top: 1400, bottom: 1700, left: 0, right: 0, width: 0, height: 300, x: 0, y: 1400, toJSON: () => ({}),
    });
    const page = await mountFocusPage("payment");
    expect(lastScroll()?.element).toBe(document.querySelector('[data-focus-target="payment"]'));
    page.unmount();
  });

  it("chave vazia ou repetida não mexe na página", async () => {
    const page = await mountFocusPage("customer");
    scrolledSpy.mockClear();

    page.key.value = null;
    await settle();
    page.key.value = "customer";
    await settle();
    // customer → null → customer: o bloco voltou a ser o foco, então rola uma
    // vez; null em si nunca rola.
    expect(scrolledSpy).toHaveBeenCalledTimes(1);

    page.key.value = "customer";
    await settle();
    expect(scrolledSpy).toHaveBeenCalledTimes(1);
    page.unmount();
  });

  it("reveal explícito mostra um elemento (center) sem mover o foco quando pedido", async () => {
    const page = await mountFocusPage("payment");
    const before = document.activeElement;

    page.reveal(() => document.getElementById("error"), { align: "center", focus: false });
    await settle();

    expect(lastScroll()).toEqual({
      element: document.getElementById("error"),
      options: { block: "center", behavior: "smooth" },
    });
    expect(document.activeElement).toBe(before);
    page.unmount();
  });

  it("o pedido mais novo vence: o foco automático da renderização passa na frente do reveal do mesmo handler", async () => {
    const page = await mountFocusPage("customer");
    scrolledSpy.mockClear();

    // O mesmo handler muda o foco da página E pede para mostrar o erro: a
    // página se organiza em torno da nova seção, não do detalhe.
    page.key.value = "payment";
    page.reveal(() => document.getElementById("error"), { align: "center" });
    await settle();

    expect(scrolledSpy).toHaveBeenCalledTimes(1);
    expect(lastScroll()?.element).toBe(document.querySelector('[data-focus-target="payment"]'));
    page.unmount();
  });

  it("espera um bloco que ainda vai montar, sem ficar rondando para sempre", async () => {
    const page = await mountFocusPage("customer");
    scrolledSpy.mockClear();

    page.key.value = "later";
    await settle();
    expect(scrolledSpy).not.toHaveBeenCalled();

    const late = document.createElement("section");
    late.setAttribute("data-focus-target", "later");
    document.body.appendChild(late);
    await vi.waitFor(() => expect(lastScroll()?.element).toBe(late));

    // Um alvo que nunca aparece desiste depois de poucos quadros.
    scrolledSpy.mockClear();
    page.key.value = "never";
    await new Promise((resolve) => setTimeout(resolve, 400));
    expect(scrolledSpy).not.toHaveBeenCalled();
    page.unmount();
  });

  it("controle nativamente focável como alvo não ganha tabindex=-1 (ficaria fora do Tab)", async () => {
    const page = await mountFocusPage("customer");

    page.reveal(() => document.getElementById("pix"), { align: "center" });
    await settle();

    const pix = document.getElementById("pix")!;
    expect(document.activeElement).toBe(pix);
    expect(pix.hasAttribute("tabindex")).toBe(false);
    page.unmount();
  });

  it("sem fonte, só o reveal imperativo existe — nada roda na montagem", async () => {
    let api!: ReturnType<typeof useNextFocus>;
    const Page = defineComponent({
      setup() {
        api = useNextFocus();
        return () => h("main", [h("section", { "data-focus-target": "only" })]);
      },
    });
    const wrapper = await mountSuspended(Page, { attachTo: document.body });
    await settle();
    expect(scrolledSpy).not.toHaveBeenCalled();

    api.reveal("only");
    await settle();
    expect(lastScroll()?.element).toBe(document.querySelector('[data-focus-target="only"]'));
    wrapper.unmount();
  });

  it("respeita prefers-reduced-motion: mesmo destino, sem animação", async () => {
    withReducedMotion(true);
    const page = await mountFocusPage("customer");

    page.key.value = "payment";
    await settle();

    expect(lastScroll()?.options).toEqual({ block: "start", behavior: "auto" });
    page.unmount();
  });

  it("depois de desmontar, nada mais rola", async () => {
    const page = await mountFocusPage("customer");
    scrolledSpy.mockClear();

    page.key.value = "payment";
    page.unmount();
    await settle();

    expect(scrolledSpy).not.toHaveBeenCalled();
  });
});
