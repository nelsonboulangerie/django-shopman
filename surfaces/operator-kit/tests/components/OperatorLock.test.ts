// Identificação do operador por CRACHÁ na tela de bloqueio.
//
// O leitor USB de crachá é um TECLADO: ele "digita" o token depressa e termina com
// Enter. O teste emula exatamente isso — `keydown` no elemento que estiver com o foco,
// mais o Enter final — em vez de escrever num campo por dentro. É a única emulação
// fiel: se o foco não estiver onde o código espera, o teste sente a mesma coisa que o
// balcão sentiria (o crachá simplesmente não faz nada).
//
// A regra de TEMPO (janela entre teclas) é pura e mora em `tests/operatorLock.test.ts`,
// sem relógio falso — aqui o assunto é foco e o Enter.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";

import OperatorLock from "../../app/components/OperatorLock.vue";

const BADGE = "a1b2c3d4e5f6"; // 12 hex: o formato de `issue_badge`

const unlock = vi.fn();
const changePin = vi.fn();
const mustChange = ref(false);

vi.mock("../../app/composables/useOperatorLock", () => ({
  useOperatorLock: () => ({
    eligible: ref([
      { id: 1, username: "bia", name: "Bia Forno" },
      { id: 2, username: "davi", name: "Davi Sousa" },
    ]),
    loadEligible: vi.fn(),
    unlock,
    changePin,
    changeError: ref(""),
    operator: ref(null),
    mustChange,
    busy: ref(false),
  }),
}));

/** Emula o leitor: teclas no elemento focado + Enter, como um HID de verdade.
 *  Sem espera entre teclas — é essa a velocidade do aparelho. */
function scan(token: string): { enterDefaultPrevented: boolean } {
  for (const char of token) {
    const target = (document.activeElement ?? document.body) as HTMLElement;
    target.dispatchEvent(
      new KeyboardEvent("keydown", { key: char, bubbles: true, cancelable: true }),
    );
  }
  const target = (document.activeElement ?? document.body) as HTMLElement;
  const enter = new KeyboardEvent("keydown", {
    key: "Enter",
    bubbles: true,
    cancelable: true,
  });
  target.dispatchEvent(enter);
  return { enterDefaultPrevented: enter.defaultPrevented };
}

// A captura vive no DOCUMENTO, então uma tela que ficou montada de um teste anterior
// continuaria ouvindo e o crachá contaria duas vezes. Desmontar entre os testes é o que
// mantém cada caso honesto — e prova, de quebra, que o listener sai no unmount.
let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;

const mount = async () => {
  mounted = await mountSuspended(OperatorLock, {
    props: { perm: "backstage.operate_pos" },
    attachTo: document.body, // foco real: sem anexar ao documento não há activeElement
    global: { stubs: { Icon: true, OperatorPinChange: true } },
  });
  return mounted;
};

describe("OperatorLock — crachá", () => {
  beforeEach(() => {
    unlock.mockReset().mockResolvedValue(true);
    changePin.mockReset();
    mustChange.value = false;
    vi.stubGlobal("useSonner", { error: vi.fn(), success: vi.fn() });
  });

  afterEach(() => {
    mounted?.unmount();
    mounted = null;
    document.body.innerHTML = "";
  });

  it("destrava com o crachá assim que a tela abre", async () => {
    await mount();

    scan(BADGE);

    expect(unlock).toHaveBeenCalledWith({ badge: BADGE });
  });

  it("continua lendo o crachá DEPOIS de o operador tocar na tela", async () => {
    const wrapper = await mount();

    // O operador toca no próprio nome (curiosidade, engano, hábito) e o foco vai para
    // o botão. É o caso comum do balcão, e era onde o crachá morria em silêncio.
    const name = wrapper.find("button");
    (name.element as HTMLButtonElement).focus();
    await name.trigger("click");

    scan(BADGE);

    expect(unlock).toHaveBeenCalledWith({ badge: BADGE });
  });

  it("o Enter do leitor não ativa o botão que estiver com o foco", async () => {
    const wrapper = await mount();
    const name = wrapper.find("button");
    (name.element as HTMLButtonElement).focus();

    const { enterDefaultPrevented } = scan(BADGE);

    // Consumido: o browser não converte esse Enter em clique no botão focado.
    expect(enterDefaultPrevented).toBe(true);
    expect(unlock).toHaveBeenCalledTimes(1);
  });

  it("Enter comum (sem crachá no buffer) segue sendo do teclado", async () => {
    await mount();

    const enter = new KeyboardEvent("keydown", {
      key: "Enter",
      bubbles: true,
      cancelable: true,
    });
    document.body.dispatchEvent(enter);

    expect(enter.defaultPrevented).toBe(false);
    expect(unlock).not.toHaveBeenCalled();
  });

  it("sequência que não tem cara de crachá é ignorada", async () => {
    await mount();

    scan("1234");

    expect(unlock).not.toHaveBeenCalled();
  });

  it("fica desligado durante a troca forçada de PIN", async () => {
    mustChange.value = true;
    await mount();

    scan(BADGE);

    // Lá há campos de texto de verdade; o Enter pertence ao formulário.
    expect(unlock).not.toHaveBeenCalled();
  });

  it("não deixa o token do crachá no DOM", async () => {
    await mount();

    scan(BADGE);

    expect(document.body.innerHTML).not.toContain(BADGE);
  });

  it("para de ouvir quando a tela sai (destravou)", async () => {
    const wrapper = await mount();
    wrapper.unmount();
    mounted = null;

    scan(BADGE);

    expect(unlock).not.toHaveBeenCalled();
  });

  it("a rajada do leitor não vaza os caracteres aos listeners de baixo", async () => {
    // O numpad do carrinho (e qualquer atalho global) ouve keydown na janela.
    // Um crachá com dígitos reescrevia quantidades enquanto identificava. Da
    // rajada, só a PRIMEIRA tecla pode vazar (indistinguível de um dedo); as
    // demais são consumidas pelo scanner.
    await mount();
    const leaked: string[] = [];
    const listener = (event: KeyboardEvent) => leaked.push(event.key);
    window.addEventListener("keydown", listener);
    try {
      scan(BADGE);
    } finally {
      window.removeEventListener("keydown", listener);
    }

    expect(unlock).toHaveBeenCalledWith({ badge: BADGE });
    expect(leaked).toEqual([BADGE[0]]);
  });
});

describe("OperatorLock — PIN pelo teclado físico", () => {
  beforeEach(() => {
    unlock.mockReset().mockResolvedValue(true);
    changePin.mockReset();
    mustChange.value = false;
    vi.stubGlobal("useSonner", { error: vi.fn(), success: vi.fn() });
  });

  afterEach(() => {
    mounted?.unmount();
    mounted = null;
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

  /** Digita como GENTE: intervalo acima da janela do leitor (o relógio é
   *  falseado, então nada de esperar de verdade). */
  function typeSlow(keys: string[]) {
    let clock = Date.now();
    const spy = vi.spyOn(Date, "now").mockImplementation(() => clock);
    for (const key of keys) {
      clock += 400;
      document.body.dispatchEvent(
        new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }),
      );
    }
    spy.mockRestore();
  }

  it("digitar o PIN e Enter destrava, sem tocar no mouse", async () => {
    const wrapper = await mount();
    // Escolhe a Bia na lista (o pad abre para ela).
    await wrapper.find("button").trigger("click");

    typeSlow(["1", "2", "3", "4", "Enter"]);

    expect(unlock).toHaveBeenCalledWith({ operatorId: 1, pin: "1234" });
  });

  it("Enter com PIN curto não submete nada", async () => {
    const wrapper = await mount();
    await wrapper.find("button").trigger("click");

    typeSlow(["1", "2", "Enter"]);

    expect(unlock).not.toHaveBeenCalled();
  });

  it("Backspace apaga o último dígito", async () => {
    const wrapper = await mount();
    await wrapper.find("button").trigger("click");

    typeSlow(["1", "2", "3", "9", "Backspace", "4", "Enter"]);

    expect(unlock).toHaveBeenCalledWith({ operatorId: 1, pin: "1234" });
  });
});
