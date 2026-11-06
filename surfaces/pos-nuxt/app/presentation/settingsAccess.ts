// PDV › Ajustes: quem grava o quê, e como a tela diz isso.
//
// Decisão do dono (05/11/2026, beta test): maquininha, impressora e Salão são
// equipamento e planta da casa, e só o Gerente e o Dono os gravam. A Caixa abre as
// três abas para conferir, sem gravar. O servidor manda a permissão na leitura
// (`can_manage_setup` nos Ajustes, `can_edit` no Salão) e recusa a gravação de quem
// não a tem; a tela só não oferece o que vai ser recusado.

import type { OperatorScreenAlert } from "../../../operator-kit/app/presentation/screenState";


/** O aviso das abas de equipamento para quem só confere. */
export const SETUP_READ_ONLY_NOTE = "Só o gerente muda maquininha, impressora e Salão. Aqui você confere o que está gravado.";

/**
 * O aviso de quem só confere, no lugar único dos avisos de tela (`alerts` do
 * `OperatorPageHeader`): fecha no X e volta ao remontar a tela, enquanto a causa
 * durar. Um `NuxtAlert` solto no topo não fechava e roubava a tela do celular.
 */
export function setupReadOnlyAlerts(canEdit: boolean): OperatorScreenAlert[] {
  if (canEdit) return [];
  return [{ id: "setup-read-only", title: SETUP_READ_ONLY_NOTE, color: "info", icon: "i-lucide-lock" }];
}

/** A tela grava? Só com a permissão dita pelo servidor; leitura sem ela não grava. */
export function canEditSetup(flag: boolean | undefined | null): boolean {
  return flag === true;
}

type Station = NonNullable<{ station?: { ready: boolean; reason: string } }["station"]> | null | undefined;

/**
 * A linha sob o nome do terminal em Ajustes › Terminal. "Este dispositivo" só
 * quando o dispositivo está vinculado ao posto: sem vínculo, o terminal mostrado é
 * o primeiro da loja, e chamá-lo de "este dispositivo" mentia (beta 05/11, CEN-06).
 */
export function terminalDeviceLine(station: Station): string {
  if (!station || station.ready) return "Este dispositivo";
  if (station.reason === "inactive") return "Terminal da loja (o posto deste dispositivo está desativado)";
  if (station.reason === "ambiguous") return "Terminal da loja (este dispositivo está em mais de um posto)";
  return "Terminal da loja (este dispositivo não está vinculado)";
}

