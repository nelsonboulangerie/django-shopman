// Presentation — as seções do Gestor. Puro: quem decide se o operador PODE ver Clientes
// ou Postos é o servidor; aqui só se monta a lista a partir da resposta.
//
// Dois andares (SUITE-UX §3, D de 13/11/2026): a OPERAÇÃO no rail (Pedidos, o quadro
// com Fila · Quadro · Tabela; Histórico; e, para quem cuida do catálogo, Catálogo e
// Canais) e um item só no pé, **Ajustes**, que abre a página com Clientes e Postos.
// Rotinas (abertura, rotina e fechamento) moram no PDV, perto do caixa. O ponto de canal desligado mora em Canais (ou em Ajustes, para quem não vê
// Canais).
//
// Barra inferior do celular (regra única do kit, `quickBarLayout`): as seções do chão
// (`GESTOR_FLOOR_SECTIONS`) vão para baixo; o resto, para a gaveta.
import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";

export interface GestorSectionsInput {
  // Rótulo de atenção de Canais ("1 desligado"); vazio quando está tudo normal.
  channelsAttention: string;
  // `true` só quando a antessala confirmou `shop.manage_customers` para quem está
  // operando. Desconhecido (carregando, erro) esconde: a aba não aparece para depois
  // levar a uma recusa.
  canManageCustomers: boolean;
  // `true` só quando a antessala confirmou `cashman.manage_operators`: Postos é o
  // cadastro de quem vincula dispositivos. Desconhecido esconde, como em Clientes.
  canManageWorkstations?: boolean;
  // `true` só quando a antessala confirmou `shop.manage_catalog`: Catálogo e Canais
  // são o cadastro de quem cuida do catálogo. Desconhecido esconde, como em Clientes
  // (beta 05/11, GES-08: o Caixa via os dois e, ao entrar, lia "Sem conexão").
  canManageCatalog?: boolean;
  // Quem só expede (SUITE-UX §15) entra no Gestor pela coluna Saída e não ganha o
  // resto: o rail fica só com a operação. Ausente conta como quem gerencia.
  expeditesOnly?: boolean;
  // Persona que cuida do catálogo: entra no mesmo app, mas não recebe Pedidos,
  // Saída, Histórico ou Clientes.
  catalogOnly?: boolean;
  // Contagens do quadro para os selos do rail (vazias fora do quadro).
  intakeCount?: number;
}

/** `?columns=expedition`: o quadro abre como balcão de saída (o mesmo parâmetro que o
 *  índice de estações da Cozinha usa). */
export const ORDERS_EXIT_POST = "/?columns=expedition";

/** As rotas que moram em Ajustes: estar numa delas acende o item Ajustes. */
export const SETTINGS_ROUTES = [
  "/history",
  "/catalog",
  "/customers",
  "/feeds",
  "/channels",
  "/workstations",
];

/** As telas da operação, no rail: não acendem Ajustes. */
const RAIL_ROUTES = ["/history", "/catalog", "/feeds", "/channels"];

function badge(count: number | undefined) {
  return count ? { badge: String(count) } : {};
}

export function gestorSections({
  channelsAttention,
  canManageCatalog = false,
  expeditesOnly = false,
  catalogOnly = false,
  intakeCount,
}: GestorSectionsInput): OperatorSection[] {
  if (catalogOnly) {
    return [
      {
        key: "catalog",
        label: "Catálogo",
        icon: "lucide:book-open",
        to: "/catalog",
        group: "Cadastro",
        quick: true,
      },
      {
        key: "feeds",
        label: "Canais",
        icon: "lucide:monitor-play",
        to: "/feeds",
        match: ["/channels"],
        attention: channelsAttention || undefined,
        group: "Cadastro",
        quick: true,
      },
    ];
  }
  // D (dono, 13/11/2026): o balcão de saída não é seção, é o mesmo quadro com Entrada
  // e Preparo recolhidas, e o posto lembra. "Pedidos" abre o quadro como o posto o
  // deixou; quem só expede entra direto na Saída. Canais sobe para o rail: desligar o
  // iFood no meio do movimento é operação, não ajuste, e o ponto de atenção mora nele.
  const operation: OperatorSection[] = [
    {
      key: "orders",
      label: "Pedidos",
      icon: "lucide:clipboard-list",
      to: expeditesOnly ? ORDERS_EXIT_POST : "/",
      group: "Operação",
      quick: true,
      ...badge(intakeCount),
    },
  ];
  if (expeditesOnly) return operation;
  return [
    ...operation,
    // Os pedidos que já saíram do quadro (concluídos, cancelados, devolvidos): a
    // "quarta coluna", a um toque para conferir (dono, 13/11/2026).
    {
      key: "history",
      label: "Histórico",
      icon: "lucide:history",
      to: "/history",
      group: "Operação",
    },
    // Catálogo é operação, não cadastro: a disponibilidade dos itens por canal muda
    // ao longo do dia (dono, 13/11/2026).
    ...(canManageCatalog
      ? [
          {
            key: "catalog",
            label: "Catálogo",
            icon: "lucide:book-open",
            to: "/catalog",
            group: "Operação",
          },
          {
            key: "feeds",
            label: "Canais",
            icon: "lucide:monitor-play",
            to: "/feeds",
            match: ["/channels"],
            attention: channelsAttention || undefined,
            group: "Operação",
          },
        ]
      : []),
    {
      key: "settings",
      label: "Ajustes",
      icon: "lucide:settings-2",
      to: "/settings",
      // Só as telas que moram em Ajustes: Histórico, Catálogo e Canais são do rail.
      match: SETTINGS_ROUTES.filter((route) => !RAIL_ROUTES.includes(route)),
      // Sem Canais no rail (quem não cuida do catálogo), o aviso de canal fica aqui.
      attention: canManageCatalog ? undefined : channelsAttention || undefined,
      foot: true,
      quick: true,
    },
  ];
}

export interface GestorSettingsEntry extends OperatorSection {
  /** O que mora ali, numa frase (a página de Ajustes lista, não esconde). */
  description: string;
}

/** O andar Ajustes: as seções que saíram do rail, cada uma a um toque. */
export function gestorSettingsSections({
  channelsAttention,
  canManageCustomers,
  canManageWorkstations = false,
  catalogOnly = false,
}: GestorSectionsInput): GestorSettingsEntry[] {
  if (catalogOnly) {
    return [
      {
        key: "catalog",
        label: "Catálogo",
        icon: "lucide:book-open",
        to: "/catalog",
        description: "Produtos, preços, coleções e disponibilidade",
      },
      {
        key: "feeds",
        label: "Canais",
        icon: "lucide:monitor-play",
        to: "/feeds",
        match: ["/channels"],
        attention: channelsAttention || undefined,
        description: "Loja online, iFood, WhatsApp e o catálogo de cada canal",
      },
    ];
  }
  return [
    // Histórico e Catálogo moram no rail (operação), não aqui.
    ...(canManageCustomers
      ? [
          {
            key: "customers",
            label: "Clientes",
            icon: "lucide:users",
            to: "/customers",
            description: "Cadastro, histórico e unificações",
          },
        ]
      : []),
    // Canais mora no rail (operação), não aqui.
    // Onde cada dispositivo fica (UX-POSTO1).
    ...(canManageWorkstations
      ? [
          {
            key: "workstations",
            label: "Postos",
            icon: "lucide:map-pin",
            to: "/workstations",
            description: "Onde cada dispositivo fica",
          },
        ]
      : []),
  ];
}

/** O nome de cada seção de Ajustes, para a frase "Sua conta não abre …". */
const SETTINGS_ROUTE_NAMES: Record<string, string> = {
  "/history": "o Histórico",
  "/catalog": "o Catálogo",
  "/customers": "os Clientes",
  "/feeds": "os Canais",
  "/channels": "os Canais",
  "/workstations": "os Postos",
};

function underRoute(path: string, route: string) {
  return path === route || path.startsWith(`${route}/`);
}

/**
 * A seção de Ajustes que a URL abre e o acesso NÃO inclui ("o Catálogo"), ou `""`.
 *
 * Quem chega pela URL direta numa seção que o andar Ajustes não lhe mostra recebia a
 * recusa do servidor (403) como "Sem conexão · Tentar de novo" e insistia achando que
 * a rede caiu (beta 05/11, GES-08). A lista de Ajustes já diz o que o acesso inclui:
 * fora dela, a tela diz "Sua conta não abre …" e não monta a página.
 */
export function deniedSettingsSection(
  path: string,
  allowed: readonly OperatorSection[],
): string {
  const route = Object.keys(SETTINGS_ROUTE_NAMES).find((r) => underRoute(path, r));
  if (!route) return "";
  // O item Ajustes acende para todas as telas dele, mas não é permissão de nenhuma.
  const ok = allowed.filter((section) => section.key !== "settings").some((section) =>
    [section.to, ...(section.match ?? [])].some(
      (to) => typeof to === "string" && underRoute(route, to.split("?")[0] ?? ""),
    ),
  );
  return ok ? "" : SETTINGS_ROUTE_NAMES[route] ?? "";
}

/** As seções do chão: andando pela loja (dono, 31/10/2026). */
export const GESTOR_FLOOR_SECTIONS: readonly string[] = ["orders", "history", "catalog", "feeds"];

/**
 * O trocador (modelo de navegação, 31/10/2026): a operação e o que mora em Ajustes, cada
 * seção com a sua forma, sem o item Ajustes (o trocador já mostra o que mora nele).
 * Chão: a operação (Pedidos, Histórico, Catálogo e Canais), que vai para a barra de baixo no celular,
 * ao alcance do polegar (`quick`; dono, 03/11/2026: "seção vai para baixo"). No topo da
 * tela fica só a subdivisão da seção (as colunas do quadro). Escritório: o resto.
 */
export function gestorSwitcherSections(
  sections: readonly OperatorSection[],
  settings: readonly OperatorSection[],
): OperatorSection[] {
  const seen = new Set<string>();
  return [...sections.filter((s) => s.key !== "settings"), ...settings]
    .filter((s) => (seen.has(s.key) ? false : (seen.add(s.key), true)))
    .map((s) =>
      GESTOR_FLOOR_SECTIONS.includes(s.key)
        ? { ...s, form: "floor" as const, quick: true }
        : { ...s, form: "office" as const, quick: undefined },
    );
}

/**
 * As respostas de permissão já chegaram (sucesso OU erro)? A grade de Ajustes só
 * desenha depois disso: antes, 3 cartões apareciam, os outros 3 entravam logo em
 * seguida, a grade deslocava e o toque caía no cartão errado (beta 05/11, GES-22).
 */
export function accessResolved(statuses: readonly string[]): boolean {
  return statuses.every((status) => status === "success" || status === "error");
}

/** Quantos cartões a grade de Ajustes reserva enquanto as permissões chegam. */
export const SETTINGS_SKELETON_CARDS = 6;

/**
 * A permissão de cada tela de Ajustes, com o nome dela para a recusa ("Sua conta não abre
 * o Catálogo"). A mesma régua dos endpoints que a tela lê (`required_permission` no
 * backstage). Quem chega pela barra de endereço sem a permissão vê a recusa no lugar da
 * página, e não "Sem conexão" com "Tentar de novo" e o servidor recebendo o mesmo 403 a
 * cada minuto (beta 05/11, CEN-05 e GES-17).
 */
const ROUTE_PERMISSIONS: ReadonlyArray<{ prefix: string; perm: string; what: string }> = [
  { prefix: "/catalog", perm: "shop.manage_catalog", what: "o Catálogo" },
  { prefix: "/feeds", perm: "shop.manage_catalog", what: "os Canais" },
  { prefix: "/channels", perm: "shop.manage_catalog", what: "os Canais" },
  { prefix: "/customers", perm: "shop.manage_customers", what: "os Clientes" },
  { prefix: "/history", perm: "shop.manage_orders", what: "o Histórico" },
  { prefix: "/workstations", perm: "cashman.manage_operators", what: "os Postos" },
];

export function gestorRoutePermission(path: string): { perm: string; what: string } | null {
  const hit = ROUTE_PERMISSIONS.find(
    (entry) => path === entry.prefix || path.startsWith(`${entry.prefix}/`),
  );
  return hit ? { perm: hit.perm, what: hit.what } : null;
}
