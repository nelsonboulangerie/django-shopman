import { beforeEach, describe, expect, it, vi } from "vitest";
import { reactive } from "vue";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useKdsBoardState, useKdsSections, useKdsStation } from "~/composables/useKdsShell";

// A barra do polegar na CARGA DIRETA do quadro (`/bancada` aberto pela barra de endereço,
// não por navegação interna). O servidor desenha a barra antes de o quadro ter dados e
// sem o localStorage; a hidratação do cliente tem de ver a MESMA barra, porque o Vue
// corrige o texto que difere mas não os atributos. Quando a barra dependia da memória da
// estação, o servidor mandava "Saída · Estações" e o cliente montava "Preparo · Saída":
// o "Preparo" ficava com o `href` da Saída e a "Saída" com o `/` marcado como atual.

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
  const { sections, current } = useKdsSections("bar");
  return {
    links: () => sections.value.filter((s) => s.to).map((s) => [s.key, s.to]),
    current: () => current.value,
  };
}

beforeEach(() => {
  env.reset();
  env.runtimeConfig.public = { djangoBaseUrl: "", ordersUrl: "https://gestor.example/" };
  env.fetchData.value = {
    instances: [{ ref: "bancada", name: "Bancada", type: "prep", type_display: "Preparo", active_count: 7 }],
  };
});

describe("barra da Cozinha na carga direta do quadro", () => {
  it("o servidor (memória vazia) já desenha Preparo na estação da rota, marcado como atual", () => {
    goTo("/bancada");
    const nav = bar();
    expect(nav.links()).toEqual([
      ["prep", "/bancada"],
      ["exit", EXIT],
      ["stations", "/"],
    ]);
    expect(nav.current()).toBe("prep");
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

  it("a memória de OUTRA estação (localStorage) não desvia o Preparo do quadro aberto", () => {
    useKdsStation().remember("forno", "Forno");
    goTo("/bancada");
    const nav = bar();
    expect(nav.links()[0]).toEqual(["prep", "/bancada"]);
    expect(nav.current()).toBe("prep");
  });

  it("fora do quadro, o Preparo é a última estação aberta e o atual é Estações", () => {
    useKdsStation().remember("forno", "Forno");
    goTo("/");
    const nav = bar();
    expect(nav.links()).toEqual([
      ["prep", "/forno"],
      ["exit", EXIT],
      ["stations", "/"],
    ]);
    expect(nav.current()).toBe("stations");
  });

  it("o selo do Preparo é o do quadro só quando o quadro é o da rota", () => {
    goTo("/bancada");
    const board = useKdsBoardState();
    board.value = { ...board.value, onBoard: true, total: 3, stationRef: "forno" };
    const { sections } = useKdsSections("bar");
    expect(sections.value.find((s) => s.key === "prep")?.badge).toBe("7");
  });
});
