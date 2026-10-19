// Presentation — pôr e tirar clientes de um grupo comercial, em lote. Transforms puros:
// o rótulo do botão que diz o resultado e o aviso do que o servidor fez. Sem rede.
//
// O cliente pode estar em vários grupos (vale a melhor vantagem por tipo). Pôr num
// grupo não tira dos outros; tirar devolve ao grupo padrão quem ficaria sem nenhum.

import type {
  CustomerGroupMembersOperation,
  CustomerGroupMembersResponse,
} from "~/types/customerGroups";

export const GROUP_MEMBER_OPERATIONS: { value: CustomerGroupMembersOperation; label: string }[] = [
  { value: "add", label: "Adicionar ao grupo" },
  { value: "remove", label: "Tirar do grupo" },
];

function customers(count: number): string {
  return count === 1 ? "1 cliente" : `${count} clientes`;
}

/**
 * O botão diz o resultado: "Adicionar 3 clientes ao grupo Equipe". Sem grupo
 * escolhido, o verbo e a quantidade bastam.
 */
export function groupMembersActionLabel(
  operation: CustomerGroupMembersOperation,
  count: number,
  groupName = "",
): string {
  // Nada marcado ainda: o botão diz o gesto, sem um "0" que não é quantidade.
  const who = count > 0 ? customers(count) : "clientes";
  if (operation === "add") return groupName ? `Adicionar ${who} ao grupo ${groupName}` : `Adicionar ${who}`;
  return groupName ? `Tirar ${who} do grupo ${groupName}` : `Tirar ${who}`;
}

/** A frase sob a escolha: o que acontece com os outros grupos de cada cliente. */
export function groupMembersHint(operation: CustomerGroupMembersOperation): string {
  return operation === "add"
    ? "Os outros grupos de cada cliente continuam."
    : "Quem ficar sem nenhum grupo volta para o grupo padrão.";
}

/**
 * O aviso depois do gesto, só com o que aconteceu. Ex.: "3 clientes entraram no
 * grupo Equipe. 1 já estava nele." Repetir o gesto diz que nada mudou.
 */
export function groupMembersResultMessage(response: CustomerGroupMembersResponse): string {
  const group = response.group.name;
  const changed = response.applied.length;
  const parts: string[] = [];
  if (response.operation === "add") {
    if (changed) parts.push(changed === 1 ? `1 cliente entrou no grupo ${group}.` : `${changed} clientes entraram no grupo ${group}.`);
    if (response.unchanged.length) {
      parts.push(response.unchanged.length === 1 ? "1 já estava nele." : `${response.unchanged.length} já estavam nele.`);
    }
  } else {
    if (changed) parts.push(changed === 1 ? `1 cliente saiu do grupo ${group}.` : `${changed} clientes saíram do grupo ${group}.`);
    const moved = response.moved_to_default.length;
    if (moved && response.default_group) {
      const target = response.default_group.name;
      parts.push(
        moved === 1
          ? `1 não tinha outro grupo e voltou para ${target}.`
          : `${moved} não tinham outro grupo e voltaram para ${target}.`,
      );
    }
    if (response.unchanged.length) {
      parts.push(response.unchanged.length === 1 ? "1 não estava nele." : `${response.unchanged.length} não estavam nele.`);
    }
    const only = response.skipped.filter((item) => item.reason === "only_group").length;
    if (only) {
      parts.push(
        only === 1
          ? `1 continua em ${group}, porque é o único grupo dele.`
          : `${only} continuam em ${group}, porque é o único grupo deles.`,
      );
    }
  }
  const gone = response.skipped.filter((item) => item.reason === "not_found_or_inactive").length;
  if (gone) {
    parts.push(
      gone === 1
        ? "1 cadastro ficou de fora: foi unificado ou desativado."
        : `${gone} cadastros ficaram de fora: foram unificados ou desativados.`,
    );
  }
  if (!changed && !parts.length) return `Nada mudou no grupo ${group}.`;
  if (!changed) return `Nada mudou no grupo ${group}. ${parts.join(" ")}`;
  return parts.join(" ");
}

/** Os grupos do cliente numa linha da lista: o primário primeiro, como o servidor manda. */
export function customerGroupsLabel(groups: readonly { name: string }[]): string {
  return groups.map((group) => group.name).join(", ");
}

/** Quem da busca já está no grupo: aparece marcado e travado, sem precisar adivinhar. */
export function isAlreadyMember(groups: readonly { ref: string }[], groupRef: string): boolean {
  return groups.some((group) => group.ref === groupRef);
}
