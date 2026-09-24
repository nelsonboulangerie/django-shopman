import { describe, expect, it } from "vitest";

import { activeSectionKey, type OperatorSection } from "../app/presentation/appBar";

// As listas reais dos quatro apps que escreviam a barra à mão. O teste existe porque a
// cadeia de `route.path.startsWith(...)` estava repetida nos quatro, sem teste em
// nenhum — e porque comparação de caminho já quebrou nesta casa com a barra final.
const GESTOR: OperatorSection[] = [
  { key: "orders", label: "Pedidos", icon: "lucide:clipboard-list", to: "/" },
  { key: "catalog", label: "Catálogo", icon: "lucide:book-open", to: "/catalog" },
  { key: "feeds", label: "Canais", icon: "lucide:monitor-play", to: "/feeds", match: ["/channels"] },
];

const MARKETING: OperatorSection[] = [
  { key: "board", label: "Painel", icon: "lucide:megaphone", to: "/" },
  { key: "campaigns", label: "Campanhas", icon: "lucide:sliders-horizontal", to: "/campaigns", match: ["/templates"] },
  { key: "platforms", label: "Plataformas", icon: "lucide:share-2", to: "/platforms" },
];

describe("activeSectionKey", () => {
  it("a raiz não é prefixo de ninguém", () => {
    // Se fosse, `/` venceria todas as rotas e a barra acenderia sempre a primeira aba.
    expect(activeSectionKey("/", GESTOR)).toBe("orders");
    expect(activeSectionKey("/catalog", GESTOR)).toBe("catalog");
    expect(activeSectionKey("/feeds", GESTOR)).toBe("feeds");
  });

  it("a barra final não muda a seção", () => {
    // `/display` × `/display/` já derrubou a trava de senha da parede em 10/09/2026:
    // a mesma tela, dois resultados. A normalização aqui é uma só.
    expect(activeSectionKey("/catalog/", GESTOR)).toBe("catalog");
    expect(activeSectionKey("//", GESTOR)).toBe("orders");
  });

  it("rota filha fica na seção da mãe", () => {
    expect(activeSectionKey("/catalog/PAO-001", GESTOR)).toBe("catalog");
    expect(activeSectionKey("/campaigns/nova", MARKETING)).toBe("campaigns");
  });

  it("`match` traz para a seção as rotas que pertencem a ela", () => {
    // Canais e /channels/<ref> são a mesma seção; modelos são vista de Campanhas.
    expect(activeSectionKey("/channels/ifood", GESTOR)).toBe("feeds");
    expect(activeSectionKey("/templates", MARKETING)).toBe("campaigns");
    expect(activeSectionKey("/templates/boas-vindas", MARKETING)).toBe("campaigns");
  });

  it("query e âncora não entram na conta", () => {
    expect(activeSectionKey("/catalog?view=table", GESTOR)).toBe("catalog");
    expect(activeSectionKey("/feeds#topo", GESTOR)).toBe("feeds");
  });

  it("vence o prefixo mais longo", () => {
    const sections: OperatorSection[] = [
      { key: "base", label: "Base", icon: "i", to: "/estoque" },
      { key: "fina", label: "Fina", icon: "i", to: "/estoque/contagem" },
    ];
    expect(activeSectionKey("/estoque/contagem/3", sections)).toBe("fina");
    expect(activeSectionKey("/estoque/outra", sections)).toBe("base");
  });

  it("rota desconhecida cai na seção raiz, nunca em nenhuma", () => {
    // "Nenhuma aba acesa" é a tela dizendo que o operador está em lugar nenhum.
    expect(activeSectionKey("/rota-que-ninguem-conhece", GESTOR)).toBe("orders");
    expect(activeSectionKey("/sumiu", MARKETING)).toBe("board");
  });

  it("sem seção raiz, cai na primeira da lista", () => {
    const sections: OperatorSection[] = [
      { key: "a", label: "A", icon: "i", to: "/a" },
      { key: "b", label: "B", icon: "i", to: "/b" },
    ];
    expect(activeSectionKey("/z", sections)).toBe("a");
  });
});
