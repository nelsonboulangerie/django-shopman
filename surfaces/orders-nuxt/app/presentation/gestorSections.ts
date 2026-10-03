// Presentation — as seções da barra do Gestor. Puro: quem decide se o operador PODE
// ver Clientes é o servidor; aqui só se monta a lista a partir da resposta.
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
  // resto: a barra fica só com Pedidos. Ausente conta como quem gerencia.
  expeditesOnly?: boolean;
}

export function gestorSections({
  channelsAttention,
  canManageCustomers,
  canManageWorkstations = false,
  expeditesOnly = false,
}: GestorSectionsInput): OperatorSection[] {
  if (expeditesOnly) return [{ key: "orders", label: "Pedidos", icon: "lucide:clipboard-list", to: "/" }];
  return [
    { key: "orders", label: "Pedidos", icon: "lucide:clipboard-list", to: "/" },
    // Os pedidos que já saíram do quadro: concluídos, cancelados e devolvidos.
    { key: "history", label: "Histórico", icon: "lucide:history", to: "/history" },
    { key: "catalog", label: "Catálogo", icon: "lucide:book-open", to: "/catalog" },
    ...(canManageCustomers
      ? [{ key: "customers", label: "Clientes", icon: "lucide:users", to: "/customers" }]
      : []),
    {
      key: "feeds",
      label: "Canais",
      icon: "lucide:monitor-play",
      to: "/feeds",
      // `/channels/<ref>` é a mesma seção: quem abre um canal não saiu de Canais.
      match: ["/channels"],
      attention: channelsAttention || undefined,
    },
    // Onde cada dispositivo fica (UX-POSTO1). O rótulo da aba é o mesmo `manage_title`
    // da copy do servidor; aqui ele precisa existir antes de qualquer leitura.
    ...(canManageWorkstations
      ? [{ key: "workstations", label: "Postos", icon: "lucide:map-pin", to: "/workstations" }]
      : []),
  ];
}
