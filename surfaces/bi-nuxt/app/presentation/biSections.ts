// As seções do B.I. na casca canônica da suíte (`OperatorSuiteShell`: rail e barra do
// celular). Ícones da prévia `bi-sobra4.html`: cada leitura tem o seu, e o da Produção
// é o chapéu (a sobra e a falta são a pergunta nº 1 do dono sobre o forno).
//
// O modelo de navegação (dono, 31/10/2026) dá a cada seção a forma da tela, que nunca
// vira palavra na tela. O B.I. é leitura de gestor, mas o dono olha os números pelo
// celular, e é o uso no celular que decide:
//   · chão (a olhada do dia, no celular): Produção (sobrou ou faltou), Vendas, Caixa
//     (fechou certo?) e Projeção (o que esperar e o troco para separar). No celular são
//     a barra de baixo, as quatro (dono, 03/11/2026: "as seções principais vão para a
//     barra de baixo, em TODOS os apps");
//   · escritório (a leitura de tendência, com tempo, no computador): Clientes, Entregas,
//     Perfis, Explorar e Cenários.
// A ordem é a de sempre (barra lateral e Alt+1 a Alt+9, dadas pelo kit por posição):
// mudar a forma não renumera tecla.
import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";

export const BI_SECTIONS: readonly OperatorSection[] = [
  { key: "production", label: "Produção", icon: "lucide:chef-hat", to: "/", form: "floor", quick: true },
  { key: "sales", label: "Vendas", icon: "lucide:banknote", to: "/sales", form: "floor", quick: true },
  { key: "cash", label: "Caixa", icon: "lucide:wallet", to: "/cash", form: "floor", quick: true },
  {
    key: "customers",
    label: "Clientes",
    icon: "lucide:users",
    to: "/customers",
    form: "office",
  },
  // O custo da TaOn (corridas da casa) ao lado do frete que os clientes pagaram.
  { key: "delivery", label: "Entregas", icon: "lucide:bike", to: "/delivery", form: "office" },
  { key: "profiles", label: "Perfis", icon: "lucide:id-card", to: "/profiles", form: "office" },
  {
    key: "explore",
    label: "Explorar",
    icon: "lucide:telescope",
    to: "/explore",
    form: "office",
  },
  // As outras olham o que aconteceu; esta projeta.
  {
    key: "forecast",
    label: "Projeção",
    icon: "lucide:trending-up",
    to: "/forecast",
    form: "floor",
    quick: true,
  },
  // Última: a IA propõe cenários sobre os agregados; o gestor decide.
  {
    key: "scenarios",
    label: "Cenários",
    icon: "lucide:flask-conical",
    to: "/scenarios",
    form: "office",
  },
];

/** As seções com a janela de análise (`period=…&from=…`) na query de cada link. */
export function biSections(windowQuery: string): OperatorSection[] {
  if (!windowQuery) return [...BI_SECTIONS];
  return BI_SECTIONS.map((section) => ({
    ...section,
    to: `${section.to}?${windowQuery}`,
  }));
}
