import { afterEach, describe, expect, it, vi } from "vitest";
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { mount } from "@vue/test-utils";

import KdsTicketCard from "../../app/components/KdsTicketCard.vue";
import type { KDSTicketProjection } from "../../app/types/kds";

// Auto-imports do Nuxt que o SFC usa como globais (sem runtime Nuxt aqui). Reatividade
// Vue REAL.
vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);
vi.stubGlobal("nextTick", nextTick);
vi.stubGlobal("onBeforeUnmount", onBeforeUnmount);

function ticket(over: Partial<KDSTicketProjection> = {}): KDSTicketProjection {
  return {
    pk: 1,
    order_ref: "WEB-20260625-0007",
    channel_icon: "language",
    customer_name: "Ana",
    fulfillment_icon: "storefront",
    created_at_display: "08:00",
    elapsed_seconds: 90,
    target_seconds: 600,
    timer_class: "timer-ok",
    items: [
      {
        sku: "A",
        name: "Pão na Chapa",
        qty: 2,
        notes: "",
        stock_warning: "",
      },
      {
        sku: "B",
        name: "Café",
        qty: 1,
        notes: "sem açúcar",
        stock_warning: "",
      },
    ],
    status: "in_progress",
    previous_tab_ref: "",
    is_scheduled: false,
    is_expedition: false,
    status_label: "",
    is_cancelled: false,
    cancelled_at_display: "",
    completed_at_display: "",
    kitchen_note: "",
    customer_note: "",
    test_order_label: "",
    ...over,
  };
}

const stubs = { Icon: true };
const mountCard = (props: Record<string, unknown>) =>
  mount(KdsTicketCard, { props, global: { stubs } });

describe("KdsTicketCard — render", () => {
  it("mostra o código (final da ref), a minutagem e os itens", () => {
    const t = mountCard({ ticket: ticket() }).text();
    expect(t).toContain("0007"); // hero code = final da ref
    expect(t).toContain("Pão na Chapa");
    expect(t).toContain("2×");
    expect(t).toContain("1×");
    expect(t).toContain("1m"); // 90s → "1m" (elapsedLabel)
  });

  it("mantém a antiga comanda riscada depois que o pedido ganha nova referência", () => {
    const wrapper = mountCard({ ticket: ticket({ order_ref: "A42", previous_tab_ref: "Mesa 5" }) });
    expect(wrapper.text()).toContain("A42");
    expect(wrapper.text()).toContain("Comanda Mesa 5");
    expect(wrapper.find(".line-through").exists()).toBe(true);
  });

  it("renderiza a nota do item (observação da cozinha)", () => {
    expect(mountCard({ ticket: ticket() }).text()).toContain("sem açúcar");
  });

  it("mostra a nota da cozinha (operador) e a nota do cliente quando presentes", () => {
    const t = mountCard({
      ticket: ticket({ kitchen_note: "Bem assado. Sem cebola.", customer_note: "Cortar ao meio" }),
    }).text();
    expect(t).toContain("Bem assado. Sem cebola.");
    expect(t).toContain("Cortar ao meio");
  });

  it("sem notas de pedido → não renderiza o banner de notas", () => {
    // Sem kitchen_note/customer_note o bloco de notas do pedido não aparece
    // (apenas a observação por-item, se houver).
    const t = mountCard({
      ticket: ticket({ items: [{ sku: "A", name: "Pão", qty: 1, notes: "", stock_warning: "" }] }),
    }).text();
    expect(t).not.toContain("Bem assado");
  });

  it("mostra o aviso de estoque quando presente", () => {
    const w = mountCard({
      ticket: ticket({
        items: [
          {
            sku: "A",
            name: "Pão",
            qty: 1,
            notes: "",
            stock_warning: "Massa acabando",
          },
        ],
      }),
    });
    expect(w.text()).toContain("Massa acabando");
  });

  it("mostra encomenda futura como prévia, com a DATA, e sem botão de ação", () => {
    const wrapper = mountCard({
      ticket: ticket({ is_scheduled: true, status: "scheduled" }),
      serviceDate: "2026-09-19",
    });
    // "libera na data" obrigava a lembrar do seletor lá no topo do cabeçalho.
    expect(wrapper.text()).toContain("Prévia · começa em 19/09");
    expect(wrapper.text()).toContain("19/09");
    expect(wrapper.text()).not.toContain("Agendado");
    expect(wrapper.find("button[data-kds-action]").exists()).toBe(false);
  });

  it("nunca trunca nome de item nem observação: quebram linha", () => {
    const longo = "Croissant de amêndoas recheado com creme de pistache e framboesa";
    const w = mountCard({
      ticket: ticket({
        items: [{ sku: "A", name: longo, qty: 1, notes: "sem açúcar de confeiteiro, embalar separado", stock_warning: "" }],
      }),
    });
    expect(w.text()).toContain(longo);
    expect(w.find("ul").html()).not.toContain("truncate");
    expect(w.find("ul").html()).not.toContain("line-clamp");
  });

  it("marca ticket adicional e pedido de entrega na linha de contexto", () => {
    const t = mountCard({
      ticket: ticket({ fulfillment_icon: "local_shipping" }),
      addition: true,
    }).text();
    expect(t).toContain("Adicional");
    expect(t).toContain("Entrega");
  });

  it("escala de densidade mapeia aos papéis do canon: compact=title text-xl, roomy=display text-4xl", () => {
    expect(
      mountCard({ ticket: ticket(), density: "compact" })
        .find("article p")
        .classes(),
    ).toContain("text-xl");
    expect(
      mountCard({ ticket: ticket(), density: "roomy" })
        .find("article p")
        .classes(),
    ).toContain("text-4xl");
  });
});

describe("KdsTicketCard — os dois gestos", () => {
  afterEach(() => vi.useRealTimers());

  it("pendente: o botão diz o ato e emite start", async () => {
    const w = mountCard({ ticket: ticket({ status: "pending" }) });
    const action = w.get("button[data-kds-action]");
    expect(action.text()).toContain("Iniciar preparo");
    await action.trigger("click");
    expect(w.emitted("start")).toHaveLength(1);
    expect(w.emitted("finish")).toBeUndefined();
  });

  it("em preparo (já armado): o botão vira Finalizar preparo e emite finish", async () => {
    const w = mountCard({ ticket: ticket({ status: "in_progress" }) });
    const action = w.get("button[data-kds-action]");
    expect(action.text()).toContain("Finalizar preparo");
    await action.trigger("click");
    expect(w.emitted("finish")).toHaveLength(1);
  });

  it("toque duplo não inicia e finaliza: o botão só arma depois do intervalo", async () => {
    vi.useFakeTimers();
    const w = mountCard({ ticket: ticket({ status: "pending" }) });
    await w.get("button[data-kds-action]").trigger("click");
    await w.setProps({ ticket: ticket({ status: "in_progress" }) }); // otimista
    // O rótulo já é o do próximo ato — o que não passa é o toque.
    expect(w.get("button[data-kds-action]").text()).toContain("Finalizar preparo");
    expect(w.get("button[data-kds-action]").attributes("disabled")).toBeDefined();
    await w.get("button[data-kds-action]").trigger("click"); // o quique do dedo
    expect(w.emitted("finish")).toBeUndefined();
    vi.advanceTimersByTime(1000);
    await nextTick();
    expect(w.get("button[data-kds-action]").attributes("disabled")).toBeUndefined();
    await w.get("button[data-kds-action]").trigger("click");
    expect(w.emitted("finish")).toHaveLength(1);
  });

  it("item cancelado: o botão diz PARA ONDE ir e emite blocked, nunca finish", async () => {
    const w = mountCard({ ticket: ticket({ status: "in_progress" }), blocked: true });
    const action = w.get("button[data-kds-action]");
    expect(action.text()).toContain("Item cancelado");
    expect(action.text()).toContain("cartão vermelho");
    await action.trigger("click");
    expect(w.emitted("blocked")).toHaveLength(1);
    expect(w.emitted("finish")).toBeUndefined();
  });

  it("a área de leitura abre o detalhe e NUNCA dispara o ato", async () => {
    // A inversão do desenho: a área grande faz o que é seguro; o ato exige o botão.
    const w = mountCard({ ticket: ticket({ status: "pending" }) });
    await w.get("[data-kds-open]").trigger("click");
    expect(w.emitted("open")).toHaveLength(1);
    expect(w.emitted("start")).toBeUndefined();
    expect(w.emitted("finish")).toBeUndefined();
  });
});

describe("KdsTicketCard — o Desfazer mora no card", () => {
  it("finalizado dentro da janela: o card fica, apagado, com o Desfazer no lugar do ato", async () => {
    const w = mountCard({ ticket: ticket({ status: "in_progress" }), finishing: true });
    // O pedido continua legível — é o mesmo card, não um aviso no topo da tela.
    expect(w.text()).toContain("0007");
    expect(w.text()).toContain("Pão na Chapa");
    expect(w.get("[data-kds-undo]").text()).toContain("Finalizado");
    const action = w.get("button[data-kds-action]");
    expect(action.text()).toContain("Desfazer");
    await action.trigger("click");
    expect(w.emitted("undo")).toHaveLength(1);
    expect(w.emitted("finish")).toBeUndefined();
  });

  it("durante a janela a área de leitura não aceita toque: o único gesto é desfazer", () => {
    const w = mountCard({ ticket: ticket({ status: "in_progress" }), finishing: true });
    expect(w.find("[data-kds-open]").exists()).toBe(false);
  });

  it("o Desfazer ganha até de um pedido travado por cancelamento", async () => {
    const w = mountCard({
      ticket: ticket({ status: "in_progress" }),
      blocked: true,
      finishing: true,
    });
    expect(w.get("button[data-kds-action]").text()).toContain("Desfazer");
  });
});

describe("KdsTicketCard — o canon do kit", () => {
  it("o botão de ação nunca desce do alvo de toque (h-11), nem no compact", () => {
    for (const [density, height] of [
      ["compact", "h-11"],
      ["cozy", "h-11"],
      ["roomy", "h-14"],
    ] as const) {
      const action = mountCard({ ticket: ticket({ status: "pending" }), density }).get(
        "button[data-kds-action]",
      );
      expect(action.classes()).toContain(height);
    }
  });

  it("o destaque do próximo usa borda + tint, nunca ring (ring = foco de teclado)", () => {
    const w = mountCard({ ticket: ticket(), next: true });
    const classes = w.get("article").classes();
    expect(classes.some((c) => c.startsWith("ring"))).toBe(false);
    expect(classes).toContain("border-primary");
  });

  // A trava do servidor não cria ticket para pedido de teste; este card só
  // existe para o que já estava no painel. O aviso vem antes do código.
  it("avisa antes do código quando o ticket é de um pedido de teste", () => {
    const w = mountCard({ ticket: ticket({ test_order_label: "Pedido de teste do iFood" }) });
    expect(w.get("[data-kds-test-order]").text()).toContain("Pedido de teste do iFood");
    expect(w.get("[data-kds-test-order]").text()).toContain("não produzir");
  });

  it("não avisa nada num ticket de pedido de verdade", () => {
    expect(mountCard({ ticket: ticket() }).find("[data-kds-test-order]").exists()).toBe(false);
  });
});

describe("KdsTicketCard — a anatomia da Saída", () => {
  it("a linha de chamada diz Entrega ou Retirada, como na Saída", () => {
    const entrega = mountCard({ ticket: ticket({ fulfillment_icon: "local_shipping" }) });
    const retirada = mountCard({ ticket: ticket({ fulfillment_icon: "storefront" }) });
    expect(entrega.text()).toContain("Entrega");
    expect(retirada.text()).toContain("Retirada");
  });

  it("o cliente mora embaixo do código, fora da linha do relógio", () => {
    const w = mountCard({ ticket: ticket({ customer_name: "Mariana" }) });
    const html = w.html();
    expect(html.indexOf("0007")).toBeLessThan(html.indexOf("Mariana"));
    expect(html.indexOf("Mariana")).toBeLessThan(html.indexOf("1m"));
  });

  it("o botão fica DENTRO da moldura, arredondado, e não uma laje colada na borda", () => {
    const w = mountCard({ ticket: ticket({ status: "pending" }) });
    const action = w.get("button[data-kds-action]");
    expect(action.classes()).toContain("rounded-md");
    expect(action.element.parentElement?.className).toContain("px-4");
  });

  it("Iniciar e Finalizar têm a mesma cor: um contornado, o outro sólido (decisão de 21/09)", () => {
    const iniciar = mountCard({ ticket: ticket({ status: "pending" }) }).get("button[data-kds-action]");
    expect(iniciar.classes()).toContain("border-foreground");
    expect(iniciar.classes()).toContain("text-foreground");
    expect(iniciar.classes().some((c) => c === "bg-foreground" || c.includes("primary"))).toBe(false);
    const finalizar = mountCard({ ticket: ticket({ status: "in_progress" }) }).get("button[data-kds-action]");
    expect(finalizar.classes()).toContain("bg-foreground");
  });

  it("à direita do código há UM chip (o relógio); a marca do detalhe não tem moldura", () => {
    const w = mountCard({ ticket: ticket() });
    const header = w.get("article").element.querySelector("[class*='justify-between']")!;
    expect(header.querySelectorAll(".border").length).toBe(1);
  });

  it("prévia agendada ocupa o lugar do botão como TEXTO, não como controle", () => {
    const w = mountCard({ ticket: ticket({ is_scheduled: true, status: "scheduled" }), serviceDate: "2026-09-19" });
    const inert = w.get("[data-kds-action]");
    expect(inert.element.tagName).toBe("P");
    expect(inert.text()).toContain("Prévia · começa em 19/09");
  });
});
