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

/**
 * A persona do B.I. que a antessala devolve (`surface_role`): `cash_auditor` audita
 * o caixa (o Dono), `reader` lê o resto (o Gerente). Desconhecida (a sessão ainda não
 * chegou), nada some: esconder o Caixa do Dono enquanto carrega seria pior.
 */
export type BiSurfaceRole = "cash_auditor" | "reader" | null | undefined;

/**
 * As seções com a janela de análise (`period=…&from=…`) na query de cada link. Quem
 * não audita o caixa não vê a seção Caixa: ela só sabia dizer "tentar de novo" a um
 * 403 que nunca vai passar (beta 05/11, ge:BI-07), e ocupava uma das quatro vagas da
 * barra de baixo do Gerente.
 */
export function biSections(windowQuery: string, role: BiSurfaceRole = null): OperatorSection[] {
  const visible = BI_SECTIONS.filter((section) => !(section.key === "cash" && role === "reader"));
  if (!windowQuery) return [...visible];
  return visible.map((section) => ({
    ...section,
    to: `${section.to}?${windowQuery}`,
  }));
}
