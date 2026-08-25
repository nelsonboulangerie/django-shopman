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
import { PICK_QUIET_MS } from "../../app/composables/useIdentityCapture";

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

  it("a rajada do leitor não vaza NENHUM caractere aos listeners de baixo", async () => {
    // O numpad do carrinho (e qualquer atalho global) ouve keydown na janela.
    // Um crachá com dígitos reescrevia quantidades enquanto identificava. A tela
    // de identificação é modal: toda tecla que a captura aceita é consumida —
    // nem a primeira vaza.
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
    expect(leaked).toEqual([]);
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

  /** Digita com o relógio falseado, num intervalo fixo entre as teclas —
   *  serve para gente lenta (400ms) e para o digitador ágil (60-110ms). */
  function typeAt(gapMs: number, keys: string[]) {
    let clock = Date.now();
    const spy = vi.spyOn(Date, "now").mockImplementation(() => clock);
    for (const key of keys) {
      clock += gapMs;
      document.body.dispatchEvent(
        new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }),
      );
    }
    spy.mockRestore();
  }
  const typeSlow = (keys: string[]) => typeAt(400, keys);

  it("digitar o PIN e Enter destrava, sem tocar no mouse", async () => {
    const wrapper = await mount();
    // Escolhe a Bia na lista (o pad abre para ela).
    await wrapper.find("button").trigger("click");

    typeSlow(["1", "2", "3", "4", "Enter"]);

    expect(unlock).toHaveBeenCalledWith({ operatorId: 1, pin: "1234" });
  });

  it("digitador RÁPIDO (60-110ms entre teclas) não perde dígito nenhum", async () => {
    // O achado do balcão: digitar o PIN "um pouquinho mais rápido" engolia
    // dígitos, porque a cadência de um dedo ágil caía na janela que separava
    // leitor de gente. A decisão agora é no Enter — dedo nunca é máquina.
    for (const gapMs of [60, 80, 110]) {
      unlock.mockClear();
      const wrapper = await mount();
      await wrapper.find("button").trigger("click");

      typeAt(gapMs, ["1", "2", "3", "4", "Enter"]);

      expect(unlock, `cadência de ${gapMs}ms`).toHaveBeenCalledWith({
        operatorId: 1,
        pin: "1234",
      });
      wrapper.unmount();
      mounted = null;
      document.body.innerHTML = "";
    }
  });

  it("rajada de crachá NO MEIO da digitação do PIN destrava pelo crachá", async () => {
    const wrapper = await mount();
    await wrapper.find("button").trigger("click");

    typeAt(80, ["1", "2"]); // a pessoa começou o PIN…
    scan(BADGE); // …e passou o crachá no leitor no meio do caminho

    expect(unlock).toHaveBeenCalledWith({ badge: BADGE });
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

  /** O silêncio que a escolha por número espera (`PICK_QUIET_MS` + folga). É
   *  tempo de relógio de verdade: o que se está provando aqui é justamente que
   *  a decisão espera o mundo, não que um timer foi agendado. */
  const quiet = () => new Promise((resolve) => setTimeout(resolve, PICK_QUIET_MS + 40));

  it("o número ao lado do nome escolhe a pessoa, sem mouse", async () => {
    // A lista era o único passo da identificação que ainda pedia ponteiro: PIN e
    // crachá são teclado puro, e para dizer QUEM era preciso mirar num alvo.
    await mount();

    typeSlow(["2"]); // Davi Sousa é o segundo
    await quiet();
    typeSlow(["1", "2", "3", "4", "Enter"]);

    expect(unlock).toHaveBeenCalledWith({ operatorId: 2, pin: "1234" });
  });

  it("número fora da lista não escolhe ninguém", async () => {
    const wrapper = await mount();

    typeSlow(["7"]); // só há duas pessoas
    await quiet();

    // Sem escolha não há pad, e o Enter não tem o que submeter.
    expect(wrapper.find('button[aria-label="Confirmar"]').exists()).toBe(false);
    typeSlow(["1", "2", "3", "4", "Enter"]);
    expect(unlock).not.toHaveBeenCalled();
  });

  it("crachá que começa com dígito destrava pelo crachá, e não escolhe ninguém no caminho", async () => {
    // O token é hexadecimal: mais da metade dos crachás começa com um dígito,
    // que é exatamente a tecla que agora escolhe gente. A rajada cancela a
    // escolha (a segunda tecla chega em milissegundos) e o token vence inteiro.
    // Se isto quebrar, metade dos crachás da casa abre o pad de um operador
    // aleatório em vez de destravar.
    await mount();

    scan("1a2b3c4d5e6f");
    await quiet();

    expect(unlock).toHaveBeenCalledWith({ badge: "1a2b3c4d5e6f" });
    expect(unlock).toHaveBeenCalledTimes(1);
  });

  it("tocar os botões do pad em sequência rápida registra todos os dígitos", async () => {
    // Clique entra no MESMO buffer que o teclado, direto — sem depender de foco
    // e sem desabilitar durante verificação (só o CONFIRMAR trava com busy).
    const wrapper = await mount();
    await wrapper.find("button").trigger("click"); // Bia

    const digits = wrapper
      .findAll("button")
      .filter((b) => ["1", "2", "3", "4"].includes(b.text()));
    for (const button of digits) await button.trigger("click");
    const confirm = wrapper.find('button[aria-label="Confirmar"]');
    await confirm.trigger("click");

    expect(unlock).toHaveBeenCalledWith({ operatorId: 1, pin: "1234" });
  });
});
