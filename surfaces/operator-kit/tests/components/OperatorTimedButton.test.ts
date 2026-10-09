import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Button from "@nuxt/ui/components/Button.vue";
import OperatorTimedButton from "../../app/components/OperatorTimedButton.vue";

const TIMED_EXTRA = new Set(["relative", "isolate", "overflow-hidden", "tabular-nums"]);
const tokens = (el: Element) => new Set(el.className.split(/\s+/).filter(Boolean));

// O botão com prazo: o fundo esvazia até a janela fechar; o rótulo é fixo; o tempo
// mora numa descrição fixa; ao fim, `expire` uma vez e o botão some ou desabilita.

const T0 = Date.parse("2026-10-09T13:42:10Z");

async function mountTimed(props: Record<string, unknown> = {}) {
  return mountSuspended(OperatorTimedButton, {
    props: { label: "Desfazer", until: T0 + 5000, duration: 5000, ...props },
    attrs: { "aria-label": "Desfazer o Pronto do pedido W07" },
  });
}

/** O atraso negativo da animação, em ms (o relógio de teste anda junto com o real). */
function delayMs(style: string | undefined): number {
  return Number(/animation-delay: -(\d+)ms/.exec(style ?? "")?.[1] ?? Number.NaN);
}

describe("OperatorTimedButton", () => {
  beforeEach(() => {
    vi.useFakeTimers({
      shouldAdvanceTime: true,
      toFake: ["Date", "setTimeout", "clearTimeout", "setInterval", "clearInterval"],
    });
    vi.setSystemTime(T0);
  });
  afterEach(() => vi.useRealTimers());

  it("o fundo começa cheio, numa animação só do tamanho da janela", async () => {
    const button = await mountTimed();
    const fill = button.get("[data-timed-fill]");
    expect(fill.attributes("aria-hidden")).toBe("true");
    expect(fill.attributes("style")).toContain("animation-duration: 5000ms");
    expect(delayMs(fill.attributes("style"))).toBeLessThan(250);
    expect(button.find("[data-timed-count]").exists()).toBe(false);
  });

  it("montado no meio da janela, continua de onde ela está (prazo absoluto)", async () => {
    vi.setSystemTime(T0 + 3000);
    const button = await mountTimed();
    const delay = delayMs(button.get("[data-timed-fill]").attributes("style"));
    expect(delay).toBeGreaterThanOrEqual(3000);
    expect(delay).toBeLessThan(3250);
  });

  it("rótulo fixo para o leitor de tela; o tempo vai na descrição, sem mudar a cada segundo", async () => {
    const button = await mountTimed();
    const el = button.get("button");
    expect(el.attributes("aria-label")).toBe("Desfazer o Pronto do pedido W07");
    const description = button.get("[data-timed-description]");
    expect(el.attributes("aria-describedby")).toBe(description.attributes("id"));
    const before = description.text();
    expect(before).toMatch(/^Disponível até \d{2}:\d{2}:\d{2}\.$/);
    vi.advanceTimersByTime(2000);
    await button.vm.$nextTick();
    expect(description.text()).toBe(before);
  });

  it("a região educada fala ao abrir e ao fechar, e só", async () => {
    const button = await mountTimed();
    const live = button.get("[data-timed-announcement]");
    expect(live.attributes("aria-live")).toBe("polite");
    vi.advanceTimersByTime(60);
    await button.vm.$nextTick();
    expect(live.text()).toMatch(/^Desfazer: disponível até /);
    const opened = live.text();
    vi.advanceTimersByTime(2000);
    await button.vm.$nextTick();
    expect(live.text()).toBe(opened);
    vi.advanceTimersByTime(3100);
    await button.vm.$nextTick();
    expect(live.text()).toBe("Desfazer: o prazo acabou.");
  });

  it("toque dentro da janela sai como click; ao fim, `expire` uma vez e o botão some", async () => {
    const button = await mountTimed();
    await button.get("button").trigger("click");
    expect(button.emitted("click")).toHaveLength(1);
    vi.advanceTimersByTime(5100);
    await button.vm.$nextTick();
    expect(button.emitted("expire")).toHaveLength(1);
    expect(button.find("button").exists()).toBe(false);
    vi.advanceTimersByTime(5000);
    expect(button.emitted("expire")).toHaveLength(1);
  });

  it("`when-expired=\"disable\"`: fica no lugar, desabilitado, e o toque não sai", async () => {
    const button = await mountTimed({ whenExpired: "disable" });
    vi.advanceTimersByTime(5100);
    await button.vm.$nextTick();
    const el = button.get("button");
    expect(el.attributes("disabled")).toBeDefined();
    expect(button.get("[data-timed-description]").text()).toBe("O prazo acabou.");
    await el.trigger("click");
    expect(button.emitted("click")).toBeUndefined();
  });

  it("aba em segundo plano: na volta, a janela que passou fecha na hora", async () => {
    const button = await mountTimed();
    vi.setSystemTime(T0 + 60_000); // o relógio andou sem os timers rodarem
    document.dispatchEvent(new Event("visibilitychange"));
    await button.vm.$nextTick();
    expect(button.emitted("expire")).toHaveLength(1);
  });

  it("prazo que já passou ao montar: fecha sem mostrar o botão", async () => {
    vi.setSystemTime(T0 + 9000);
    const button = await mountTimed();
    expect(button.emitted("expire")).toHaveLength(1);
    expect(button.find("button").exists()).toBe(false);
  });

  it("movimento reduzido: nada anima, só o número de segundos, uma vez por segundo", async () => {
    const button = await mountTimed({ reducedMotion: true });
    expect(button.find("[data-timed-fill]").exists()).toBe(false);
    const count = button.get("[data-timed-count]");
    expect(count.attributes("aria-hidden")).toBe("true");
    expect(count.text()).toBe("5 s");
    vi.advanceTimersByTime(1000);
    await button.vm.$nextTick();
    expect(button.get("[data-timed-count]").text()).toBe("4 s");
  });

  it("prazo do servidor com `server-now`: o desvio do relógio do dispositivo sai da conta", async () => {
    // O servidor está 2 s à frente; o prazo dele (T0 + 7 s) é daqui a 5 s.
    const button = await mountTimed({
      until: new Date(T0 + 7000).toISOString(),
      since: new Date(T0 + 2000).toISOString(),
      duration: undefined,
      serverNow: new Date(T0 + 2000).toISOString(),
    });
    expect(button.get("[data-timed-fill]").attributes("style")).toContain("animation-duration: 5000ms");
    vi.advanceTimersByTime(4500);
    await button.vm.$nextTick();
    expect(button.emitted("expire")).toBeUndefined();
    vi.advanceTimersByTime(600);
    await button.vm.$nextTick();
    expect(button.emitted("expire")).toHaveLength(1);
  });

  // A menor interferência possível (dono, 09/10/2026): o botão com prazo é o botão de
  // origem, classe por classe; a peça só acrescenta o que segura a camada atrás do texto.
  for (const variant of ["solid", "outline"] as const) {
    for (const color of ["primary", "neutral", "error"] as const) {
      for (const size of ["md", "xl"] as const) {
        it(`herda a aparência do botão de origem: ${variant} ${color} ${size}`, async () => {
          const origin = await mountSuspended(Button, {
            props: { label: "Pronto 0131", variant, color, size, block: true },
          });
          const timed = await mountTimed({ label: "Desfazer 0131", variant, color, size, block: true });
          const before = tokens(origin.get("button").element);
          const after = tokens(timed.get("button").element);
          for (const token of before) expect(after, `classe ${token}`).toContain(token);
          for (const token of after) {
            if (!before.has(token)) expect(TIMED_EXTRA, `classe nova ${token}`).toContain(token);
          }
          origin.unmount();
        });
      }
    }
  }

  it("o fundo que esvazia é a própria cor, translúcida, nunca outra", async () => {
    const solid = await mountTimed({ variant: "solid", color: "primary" });
    expect(solid.get("[data-timed-fill]").classes()).toContain("bg-(--ui-bg-inverted)/30");
    const outline = await mountTimed({ variant: "outline", color: "error" });
    expect(outline.get("[data-timed-fill]").classes()).toContain("bg-current/10");
    // As duas esvaziam na mesma direção: a janela que sobra encolhe para a esquerda.
    expect(outline.get("[data-timed-fill]").classes()).toContain("origin-left");
  });

  it("um prazo novo reabre a janela", async () => {
    const button = await mountTimed({ whenExpired: "disable" });
    vi.advanceTimersByTime(5100);
    await button.vm.$nextTick();
    await button.setProps({ until: Date.now() + 5000 });
    expect(button.get("button").attributes("disabled")).toBeUndefined();
    expect(button.find("[data-timed-fill]").exists()).toBe(true);
  });
});
