// As seções do B.I. na casca canônica da suíte (`OperatorSuiteShell`: rail e barra do
// celular). Ícones da prévia `bi-sobra4.html`: cada leitura tem o seu, e o da Produção
// é o chapéu (a sobra e a falta são a pergunta nº 1 do dono sobre o forno).
import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";

export const BI_SECTIONS: readonly OperatorSection[] = [
  { key: "production", label: "Produção", icon: "lucide:chef-hat", to: "/" },
  { key: "sales", label: "Vendas", icon: "lucide:banknote", to: "/sales" },
  { key: "cash", label: "Caixa", icon: "lucide:wallet", to: "/cash" },
  { key: "customers", label: "Clientes", icon: "lucide:users", to: "/customers" },
  { key: "profiles", label: "Perfis", icon: "lucide:id-card", to: "/profiles" },
  { key: "explore", label: "Explorar", icon: "lucide:telescope", to: "/explore" },
  // As outras olham o que aconteceu; esta projeta.
  { key: "forecast", label: "Projeção", icon: "lucide:trending-up", to: "/forecast" },
  // Última: a IA propõe cenários sobre os agregados; o gestor decide.
  { key: "scenarios", label: "Cenários", icon: "lucide:flask-conical", to: "/scenarios" },
];

/** As seções com a janela de análise (`period=…&from=…`) na query de cada link. */
export function biSections(windowQuery: string): OperatorSection[] {
  if (!windowQuery) return [...BI_SECTIONS];
  return BI_SECTIONS.map((section) => ({ ...section, to: `${section.to}?${windowQuery}` }));
}
