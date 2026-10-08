// A barra de seções do app — a parte PURA: que seção está ativa, dada a rota.
//
// ## Por que isto virou peça da layer
//
// Quatro apps escreviam a mesma barra à mão (Gestor, B.I., Marketing, Compras), e a
// medição de 22/09/2026 mostrou que "a mesma" já não era a mesma:
//
// - altura da aba: `min-h-control` (44px) no Gestor, `h-11` no Marketing, **`h-8`** no
//   B.I. e no Compras — metade do alvo de toque que o token `--spacing-control` define
//   para a casa inteira, e o dobro da chance de errar o toque com a mão ocupada;
// - a aba ativa só era trazida para dentro da área visível no Marketing. Nos outros,
//   numa tela estreita, a seção em que o operador estava podia ficar fora da barra —
//   ele lia a barra e concluía que estava em outra seção (o bug está documentado em
//   `CampaignTopBar.vue`, que o corrigiu sozinho);
// - a tecla de atalho só era ENSINADA na própria aba na Produção;
// - `chipClass(active)` estava duplicado byte a byte entre B.I. e Compras.
//
// O que um app resolveu melhor passa a valer para todos — que é a única forma de a
// suíte parecer uma suíte. O desenho, o alvo de toque, o `aria-current` e a revelação
// da aba ativa moram no `OperatorAppBar`; a lista de seções continua de cada app.
//
// ## Por que a rota ativa é uma função pura
//
// A cadeia de `route.path.startsWith(...)` estava repetida nos quatro, e nenhuma tinha
// teste. Pior: comparação de caminho por igualdade já quebrou nesta casa com a BARRA
// FINAL — `/display` e `/display/` são a mesma tela e eram dois resultados diferentes.
// Aqui a normalização é uma só, e tem teste.

export interface OperatorSection {
  /** Identidade da seção. É o que o app compara e o que o teste nomeia. */
  key: string;
  label: string;
  /**
   * Rótulo curto para a barra do polegar no celular, quando o nome não cabe em 1/5 da
   * tela (ex.: a Produção, "Plano" para Planejamento, como nas prévias v4). O rail e o
   * nome acessível seguem com `label`. Ausente = `label`.
   */
  shortLabel?: string;
  /** Ícone lucide (`lucide:*`). */
  icon: string;
  /** Rota da seção. Sem ela, a aba vira botão e a barra emite `select`. */
  to?: string;
  /** Outras rotas que PERTENCEM a esta seção (ex.: `/channels/` dentro de Canais). */
  match?: string[];
  /** Aviso curto ao lado do rótulo ("1 desligado"). Ausente = estado normal, sem ruído. */
  attention?: string;
  /**
   * A cor do sinal no rail da suíte (ponto ou número): `success`, `warning` (padrão) ou
   * `error`. A cor nunca fala sozinha: o que ela quer dizer está em `attention` ou no
   * número.
   */
  tone?: "success" | "warning" | "error";
  /** Tecla que leva a esta seção. Ensinada na própria aba, onde a mão está. */
  shortcut?: string;
  /**
   * Contagem curta no selo do item (rail da suíte e barra do polegar), ex.: pedidos
   * na fila. Ausente ou vazia = sem selo; zero não é selo. O número é visual: quem
   * monta a seção diz o que ele conta em `badgeLabel`.
   */
  badge?: string;
  /** O que o selo conta, por extenso, para leitor de tela ("10 pedidos na fila"). */
  badgeLabel?: string;
  /**
   * Rótulo do grupo (rail da suíte, prévia v4: "Operação"). Sai uma vez, acima da
   * primeira seção do grupo. A barra do polegar ignora.
   */
  group?: string;
  /**
   * Mora no pé do rail, separada da operação (v4: "Ajustes não divide barra com a
   * operação"). Na barra do polegar entra no fim, como as outras.
   */
  foot?: boolean;
  /**
   * Onde a seção aparece (V6-KIT). Omitido: no rail e na barra do polegar. `rail`: só no
   * rail (ex.: a Tela do cliente do PDV, que abre no segundo monitor e não cabe no
   * bolso). `bar`: só na barra de baixo (ex.: o Fim do dia do PDV no tablet em pé).
   */
  where?: "rail" | "bar";
  /** Um traço acima desta seção no rail (v4 `salao-mesas4.html`: Caixa · traço · Ajustes). */
  divider?: boolean;
}

/** `/pedidos/` e `/pedidos` são a mesma tela. Uma normalização só, com teste. */
function normalize(path: string): string {
  const clean = (path || "/").split("?")[0]!.split("#")[0]!;
  if (clean.length > 1 && clean.endsWith("/")) return clean.slice(0, -1);
  return clean || "/";
}

function matches(path: string, prefix: string): boolean {
  const target = normalize(prefix);
  // A raiz não é prefixo de ninguém: se fosse, ela venceria todas as rotas do app.
  if (target === "/") return path === "/";
  return path === target || path.startsWith(`${target}/`);
}

/**
 * Qual seção está ativa nesta rota.
 *
 * Vence o prefixo MAIS LONGO que casa — é o que faz `/campaigns/novo` ficar em
 * Campanhas mesmo com uma seção `/` na lista. Sem nenhum casamento, devolve a seção
 * raiz (`to === "/"`), e na falta dela a primeira da lista: a barra nunca fica sem
 * nenhuma aba marcada, porque "nenhuma acesa" é a tela dizendo que o operador está
 * em lugar nenhum.
 */
export function activeSectionKey(path: string, sections: readonly OperatorSection[]): string {
  const current = normalize(path);
  let winner: { key: string; length: number } | null = null;

  for (const section of sections) {
    for (const candidate of [section.to, ...(section.match || [])]) {
      if (!candidate || !matches(current, candidate)) continue;
      const length = normalize(candidate).length;
      if (!winner || length > winner.length) winner = { key: section.key, length };
    }
  }

  if (winner) return winner.key;
  return sections.find((section) => section.to && normalize(section.to) === "/")?.key
    || sections[0]?.key
    || "";
}
