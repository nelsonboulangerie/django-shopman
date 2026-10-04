// Presentation — as seções do Gestor. Puro: quem decide se o operador PODE ver Clientes
// ou Postos é o servidor; aqui só se monta a lista a partir da resposta.
//
// Dois andares (SUITE-UX §3, prévia v4 `gestor-fila4.html`, UX-KIT-V2): a OPERAÇÃO no
// rail (Pedidos, com as três colunas, e Saída, o posto do passe) e um item só no pé,
// **Ajustes**, que abre a página com Histórico, Catálogo, Clientes, Canais e Postos.
// Ajustes não divide barra com a operação; o ponto avisa pendência (canal desligado)
// sem pesar na fila. Toda seção continua a um toque de Ajustes.
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
  // Quem só expede (SUITE-UX §15) entra no Gestor pela coluna Saída e não ganha o
  // resto: o rail fica só com a operação. Ausente conta como quem gerencia.
  expeditesOnly?: boolean;
  // Contagens do quadro para os selos do rail (vazias fora do quadro).
  intakeCount?: number;
  exitCount?: number;
}

/** `?columns=all` / `?columns=expedition`: o quadro abre com as três colunas ou como posto
 *  Saída (o mesmo parâmetro que o índice de estações da Cozinha usa). */
export const ORDERS_ALL_COLUMNS = "/?columns=all";
export const ORDERS_EXIT_POST = "/?columns=expedition";

/** As rotas que moram em Ajustes: estar numa delas acende o item Ajustes. */
export const SETTINGS_ROUTES = ["/history", "/catalog", "/customers", "/feeds", "/channels", "/workstations"];

function badge(count: number | undefined, noun: [string, string]) {
  if (!count) return {};
  return { badge: String(count), badgeLabel: `${count} ${count === 1 ? noun[0] : noun[1]}` };
}

export function gestorSections({
  channelsAttention,
  expeditesOnly = false,
  intakeCount,
  exitCount,
}: GestorSectionsInput): OperatorSection[] {
  const operation: OperatorSection[] = [
    { key: "orders", label: "Pedidos", icon: "lucide:clipboard-list", to: ORDERS_ALL_COLUMNS, group: "Operação", ...badge(intakeCount, ["pedido novo", "pedidos novos"]) },
    // O posto do passe: o mesmo quadro com Entrada e Preparo recolhidas (SUITE-UX §16).
    { key: "exit", label: "Saída", icon: "lucide:package-check", to: ORDERS_EXIT_POST, group: "Operação", ...badge(exitCount, ["pedido na Saída", "pedidos na Saída"]) },
  ];
  if (expeditesOnly) return operation;
  return [
    ...operation,
    {
      key: "settings",
      label: "Ajustes",
      icon: "lucide:settings-2",
      to: "/settings",
      match: SETTINGS_ROUTES,
      attention: channelsAttention || undefined,
      foot: true,
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
}: GestorSectionsInput): GestorSettingsEntry[] {
  return [
    // Os pedidos que já saíram do quadro: concluídos, cancelados e devolvidos.
    { key: "history", label: "Histórico", icon: "lucide:history", to: "/history", description: "Pedidos concluídos, cancelados e devolvidos" },
    { key: "catalog", label: "Catálogo", icon: "lucide:book-open", to: "/catalog", description: "Produtos, preços, coleções e disponibilidade" },
    ...(canManageCustomers
      ? [{ key: "customers", label: "Clientes", icon: "lucide:users", to: "/customers", description: "Cadastro, histórico e unificações" }]
      : []),
    {
      key: "feeds",
      label: "Canais",
      icon: "lucide:monitor-play",
      to: "/feeds",
      match: ["/channels"],
      attention: channelsAttention || undefined,
      description: "Loja online, iFood, WhatsApp e o catálogo de cada canal",
    },
    // Onde cada dispositivo fica (UX-POSTO1).
    ...(canManageWorkstations
      ? [{ key: "workstations", label: "Postos", icon: "lucide:map-pin", to: "/workstations", description: "Onde cada dispositivo fica" }]
      : []),
  ];
}
