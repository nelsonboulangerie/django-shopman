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
const reportBadgeLost = vi.fn();
const mustChange = ref(false);
const lostBadgeError = ref("");

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
    reportBadgeLost,
    lostBadgeError,
    operator: ref(null),
    mustChange,
    busy: ref(false),
  }),
}));

/** Emula o leitor: teclas no elemento focado + Enter, como um HID de verdade.
 *  Sem espera entre teclas — é essa a velocidade do dispositivo. */
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

// ── Teclado de primeira, com o foco esquecido atrás da trava ─────────────────
//
// O achado do dono (03/10/2026): "quando a tela do PDV trava, na tela do PIN
// parece que nunca pega o número que digito logo de primeira; tenho que clicar
// na tela". O PDV trava por ociosidade com a busca de produto focada (ela nasce
// com `autofocus`). A captura tratava aquele campo como "do dono" e deixava os
// dígitos irem para a busca escondida. O teste monta a cena do balcão: um campo
// de busca focado na tela de baixo, a trava subindo por cima, e as teclas
// despachadas no elemento que o browser considera focado, sem clique nenhum.
describe("OperatorLock — teclado de primeira, sem clicar", () => {
  let search: HTMLInputElement;
  let reachedSearch: string[];

  beforeEach(() => {
    unlock.mockReset().mockResolvedValue(true);
    changePin.mockReset();
    mustChange.value = false;
    vi.stubGlobal("useSonner", { error: vi.fn(), success: vi.fn() });
    // A tela de baixo: a busca do PDV, focada, com o Enter que adiciona produto.
    search = document.createElement("input");
    search.type = "search";
    document.body.appendChild(search);
    reachedSearch = [];
    search.addEventListener("keydown", (event) => reachedSearch.push(event.key));
    search.focus();
  });

  afterEach(() => {
    mounted?.unmount();
    mounted = null;
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

  /** Teclas no elemento FOCADO, como o teclado de verdade (nada de clicar antes). */
  function press(keys: string[], gapMs = 400) {
    let clock = Date.now();
    const spy = vi.spyOn(Date, "now").mockImplementation(() => clock);
    const events: KeyboardEvent[] = [];
    for (const key of keys) {
      clock += gapMs;
      const target = (document.activeElement ?? document.body) as HTMLElement;
      const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
      target.dispatchEvent(event);
      events.push(event);
    }
    spy.mockRestore();
    return events;
  }

  const quiet = () => new Promise((resolve) => setTimeout(resolve, PICK_QUIET_MS + 40));

  it("a trava toma o foco da busca ao subir", async () => {
    await mount();

    const overlay = document.querySelector("[data-operator-lock]");
    expect(document.activeElement).toBe(overlay);
    expect(document.activeElement).not.toBe(search);
  });

  it("número do operador, PIN e Enter destravam sem tocar na tela", async () => {
    await mount();

    press(["1"]); // Bia é a primeira da lista
    await quiet();
    press(["1", "2", "3", "4", "Enter"]);

    expect(unlock).toHaveBeenCalledWith({ operatorId: 1, pin: "1234" });
    expect(reachedSearch).toEqual([]);
  });

  it("mesmo com o foco de volta na busca escondida, o PIN vai para a trava", async () => {
    // A rede de segurança da captura: Tab, um script da tela de baixo ou um
    // `autofocus` tardio devolvem o foco à busca. A tecla segue sendo da trava,
    // e nem o dígito nem o Enter (que lá adicionaria produto) chegam à busca.
    const wrapper = await mount();
    await wrapper.find("button").trigger("click"); // Bia
    search.focus();

    const events = press(["1", "2", "3", "9", "Backspace", "4", "Enter"]);

    expect(unlock).toHaveBeenCalledWith({ operatorId: 1, pin: "1234" });
    expect(reachedSearch).toEqual([]);
    // O default do dígito (escrever na busca) também é cancelado.
    expect(events.every((event) => event.defaultPrevented)).toBe(true);
  });

  it("Enter na busca escondida não vaza nem sem PIN pronto", async () => {
    await mount();
    search.focus();

    const [enter] = press(["Enter"]);

    expect(enter!.defaultPrevented).toBe(true);
    expect(reachedSearch).toEqual([]);
    expect(unlock).not.toHaveBeenCalled();
  });

  it("toma o foco de novo quando a janela volta a ter foco", async () => {
    await mount();
    search.focus(); // o foco escapou enquanto a janela estava em segundo plano

    window.dispatchEvent(new Event("focus"));

    expect(document.activeElement).toBe(document.querySelector("[data-operator-lock]"));
  });

  it("toma o foco de novo quando a aba volta a ficar visível", async () => {
    await mount();
    search.focus();

    document.dispatchEvent(new Event("visibilitychange"));

    expect(document.activeElement).toBe(document.querySelector("[data-operator-lock]"));
  });

  it("não rouba o foco de quem já está dentro da trava", async () => {
    const wrapper = await mount();
    const name = wrapper.find("button").element as HTMLButtonElement;
    name.focus();

    window.dispatchEvent(new Event("focus"));

    expect(document.activeElement).toBe(name);
  });

  it("o toque no pad continua valendo", async () => {
    const wrapper = await mount();
    await wrapper.find("button").trigger("click"); // Bia

    const digits = wrapper
      .findAll("button")
      .filter((b) => ["1", "2", "3", "4"].includes(b.text()));
    for (const button of digits) await button.trigger("click");
    await wrapper.find('button[aria-label="Confirmar"]').trigger("click");

    expect(unlock).toHaveBeenCalledWith({ operatorId: 1, pin: "1234" });
  });
});

// ── A outra metade do par ─────────────────────────────────────────────────
//
// ⚠️ Esta tela se confunde com a AUTORIZAÇÃO DO GERENTE do PDV, não com o
// login: as duas aparecem no meio do expediente, as duas são um teclado de PIN
// e as duas interrompem quem está atendendo. O teclado é o mesmo componente
// (`OperatorIdentify`) nas duas, então quem separa é o TEXTO — e ele só separa
// se as duas metades existirem. A metade de lá é "Você continua como <fulano>".

describe("OperatorLock — diz que a sessão TROCA", () => {
  beforeEach(() => {
    unlock.mockReset().mockResolvedValue(true);
    changePin.mockReset();
    mustChange.value = false;
    vi.stubGlobal("useSonner", { error: vi.fn(), success: vi.fn() });
  });
  afterEach(() => {
    mounted?.unmount();
    mounted = null;
  });

  it("anuncia que quem entra ASSUME o balcão", async () => {
    const wrapper = await mount();

    expect(wrapper.text()).toContain("Você assume o balcão.");
  });

  it("pergunta quem está OPERANDO, não quem autoriza", async () => {
    const wrapper = await mount();

    expect(wrapper.text()).toContain("Quem está operando?");
    expect(wrapper.text()).not.toContain("Quem autoriza?");
  });
});

// ── "Perdi meu crachá" ───────────────────────────────────────────────────────
//
// A saída de quem chega às 6h sem o crachá. Mora na trava porque é ali que a
// pessoa está: pré-login, sem sessão, olhando a lista de nomes. Provar o PIN é a
// autorização — o mesmo contrato da troca de PIN.
describe("OperatorLock — perdi meu crachá", () => {
  beforeEach(() => {
    unlock.mockReset().mockResolvedValue(true);
    changePin.mockReset();
    reportBadgeLost.mockReset().mockResolvedValue(true);
    mustChange.value = false;
    lostBadgeError.value = "";
    vi.stubGlobal("useSonner", { error: vi.fn(), success: vi.fn() });
  });

  afterEach(() => {
    mounted?.unmount();
    mounted = null;
    vi.unstubAllGlobals();
  });

  /** Escolhe alguém na lista — é o que faz o rodapé (e o pad) aparecerem. */
  async function pickSomeone(wrapper: Awaited<ReturnType<typeof mountSuspended>>) {
    const nome = wrapper.findAll("button").find((b) => b.text().includes("Bia Forno"));
    await nome!.trigger("click");
  }

  it("o botão é descobrível: texto legível, não menu escondido", async () => {
    const wrapper = await mount();
    await pickSomeone(wrapper);

    const botao = wrapper.findAll("button").find((b) => b.text().includes("Perdi meu crachá"));
    expect(botao).toBeDefined();
  });

  it("a tela diz o que acontece ANTES de pedir o PIN", async () => {
    const wrapper = await mount();
    await pickSomeone(wrapper);
    const botao = wrapper.findAll("button").find((b) => b.text().includes("Perdi meu crachá"));
    await botao!.trigger("click");

    const texto = wrapper.text();
    expect(texto).toContain("Seu crachá para de funcionar agora");
    expect(texto).toContain("Seu PIN continua valendo");
    expect(texto).toContain("Um gerente emite outro crachá");
  });

  it("o leitor de crachá fica desligado aqui — quem está nesta tela não tem o crachá", async () => {
    const wrapper = await mount();
    await pickSomeone(wrapper);
    await wrapper.findAll("button").find((b) => b.text().includes("Perdi meu crachá"))!.trigger("click");

    scan(BADGE);

    expect(unlock).not.toHaveBeenCalled();
  });

  it("invalida o crachá do operador escolhido, provando o PIN", async () => {
    const wrapper = await mount();
    await pickSomeone(wrapper);
    await wrapper.findAll("button").find((b) => b.text().includes("Perdi meu crachá"))!.trigger("click");

    // Dentro do modo: escolher-se de novo e digitar o PIN.
    await pickSomeone(wrapper);
    for (const d of "1234") {
      await wrapper.findAll("button").find((b) => b.text().trim() === d)!.trigger("click");
    }
    await wrapper.find('button[aria-label="Confirmar"]').trigger("click");

    expect(reportBadgeLost).toHaveBeenCalledWith({ operatorId: 1, pin: "1234" });
  });

  it("cancelar volta para a identificação sem invalidar nada", async () => {
    const wrapper = await mount();
    await pickSomeone(wrapper);
    await wrapper.findAll("button").find((b) => b.text().includes("Perdi meu crachá"))!.trigger("click");

    await wrapper.findAll("button").find((b) => b.text().trim() === "Cancelar")!.trigger("click");

    expect(reportBadgeLost).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("Identifique-se para operar");
  });
});
