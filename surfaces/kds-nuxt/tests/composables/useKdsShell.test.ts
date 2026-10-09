import { beforeEach, describe, expect, it, vi } from "vitest";
import { reactive } from "vue";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { sectionDescription } from "../../../operator-kit/app/presentation/suiteChrome";
import { useKdsBoardState, useKdsSections, useKdsStation } from "~/composables/useKdsShell";

// A navegação da Cozinha são as estações da casa, pelo nome (dono, 09/10/2026): cada uma
// leva à sua bancada, a Saída leva ao Gestor, e não existe item "Preparo".
//
// E a barra inferior na CARGA DIRETA do quadro (`/bancada` aberto pela barra de endereço,
// não por navegação interna): o servidor desenha a barra antes de o quadro ter dados e
// sem o localStorage; a hidratação do cliente tem de ver a MESMA barra, porque o Vue
// corrige o texto que difere mas não os atributos (#1563).

const env = installNuxtGlobals();
const route = reactive<{ path: string; name: string; params: Record<string, string> }>({
  path: "/",
  name: "index",
  params: {},
});
vi.stubGlobal("useRoute", () => route);

const EXIT = "https://gestor.example/?columns=expedition";

function goTo(path: string) {
  route.path = path;
  if (path === "/") {
    route.name = "index";
    route.params = {};
  } else {
    route.name = "ref";
    route.params = { ref: path.slice(1) };
  }
}

function bar() {
  const { bar: sections, current } = useKdsSections();
  return {
    links: () => sections.value.filter((s) => s.to).map((s) => [s.key, s.to]),
    current: () => current.value,
  };
}

beforeEach(() => {
  env.reset();
  env.runtimeConfig.public = { djangoBaseUrl: "", ordersUrl: "https://gestor.example/" };
  env.fetchData.value = {
    instances: [
      { ref: "cafes", name: "Cafés", type: "prep", type_display: "Preparo", active_count: 2 },
      { ref: "bancada", name: "Bancada", type: "prep", type_display: "Preparo", active_count: 7 },
      { ref: "encomendas", name: "Encomendas", type: "picking", type_display: "Separação", active_count: 0 },
      { ref: "saida", name: "Saída", type: "expedition", type_display: "Saída", active_count: 3 },
    ],
  };
});

describe("itens da Cozinha: as estações reais", () => {
  it("cada estação pelo nome, levando à sua bancada; Saída leva ao Gestor; sem Preparo", () => {
    goTo("/cafes");
    const { rail: sections } = useKdsSections();
    expect(sections.value.filter((s) => s.to).map((s) => [s.label, s.to])).toEqual([
      ["Cafés", "/cafes"],
      ["Bancada", "/bancada"],
      ["Encomendas", "/encomendas"],
      ["Saída", EXIT],
      ["Painel de retirada", "/pickup"],
    ]);
    expect(sections.value.some((s) => s.label === "Preparo")).toBe(false);
  });

  it("a estação de Saída do cadastro não vira bancada: é o item Saída, com o selo dela", () => {
    goTo("/cafes");
    const { rail: sections } = useKdsSections();
    expect(sections.value.some((s) => s.to === "/saida")).toBe(false);
    expect(sections.value.find((s) => s.key === "exit")?.badge).toBe("3");
  });

  it("sem a URL do Gestor, a estação de Saída segue acessível como bancada", () => {
    env.runtimeConfig.public = { djangoBaseUrl: "", ordersUrl: "" };
    goTo("/cafes");
    const { rail: sections } = useKdsSections();
    expect(sections.value.some((s) => s.key === "exit")).toBe(false);
    expect(sections.value.find((s) => s.to === "/saida")?.label).toBe("Saída");
  });

  it("a estação aberta é o item atual; a descrição é \"Estação · N pendências\"", () => {
    goTo("/bancada");
    const { rail: sections, current } = useKdsSections();
    const open = sections.value.find((s) => s.key === current.value)!;
    expect(open.to).toBe("/bancada");
    expect(sectionDescription(open)).toBe("Bancada · 7 pendências");
  });

  it("na tela de escolher a estação, nenhum item é o atual", () => {
    goTo("/");
    const nav = bar();
    expect(nav.current()).toBe("");
  });
});

describe("barra da Cozinha na carga direta do quadro", () => {
  it("o servidor (memória vazia) já desenha a estação da rota à frente, marcada como atual", () => {
    goTo("/bancada");
    const nav = bar();
    expect(nav.links()).toEqual([
      ["station:bancada", "/bancada"],
      ["station:cafes", "/cafes"],
      ["station:encomendas", "/encomendas"],
      ["exit", EXIT],
    ]);
    expect(nav.current()).toBe("station:bancada");
  });

  it("o que o quadro grava depois de montar não muda nenhum href nem o item atual", () => {
    goTo("/bancada");
    const nav = bar();
    const served = { links: nav.links(), current: nav.current() };

    // O quadro, já montado no cliente, conta ao shell a estação e os pedidos.
    useKdsStation().remember("bancada", "Bancada");
    const board = useKdsBoardState();
    board.value = { ...board.value, onBoard: true, total: 7, stationRef: "bancada", stationName: "Bancada" };

    expect(nav.links()).toEqual(served.links);
    expect(nav.current()).toBe(served.current);
  });

  it("a memória de OUTRA estação (localStorage) não desvia a barra do quadro aberto", () => {
    useKdsStation().remember("encomendas", "Encomendas");
    goTo("/bancada");
    const nav = bar();
    expect(nav.links()[0]).toEqual(["station:bancada", "/bancada"]);
    expect(nav.current()).toBe("station:bancada");
  });

  it("fora do quadro, a estação deste dispositivo vai à frente (depois de montar)", () => {
    useKdsStation().remember("encomendas", "Encomendas");
    goTo("/");
    const nav = bar();
    expect(nav.links()[0]).toEqual(["station:encomendas", "/encomendas"]);
    expect(nav.current()).toBe("");
  });

  it("o selo da estação é o do quadro só quando o quadro é o da rota", () => {
    goTo("/bancada");
    const board = useKdsBoardState();
    board.value = { ...board.value, onBoard: true, total: 3, stationRef: "cafes" };
    const { bar: sections } = useKdsSections();
    expect(sections.value.find((s) => s.key === "station:bancada")?.badge).toBe("7");
    expect(sections.value.find((s) => s.key === "station:cafes")?.badge).toBe("2");
  });
});
