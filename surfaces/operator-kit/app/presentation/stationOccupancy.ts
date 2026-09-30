// A ocupação de um balcão, dita a quem vai iniciar um dispositivo nele.
//
// Vários dispositivos no mesmo terminal é postura decidida (D-007): dividem a
// gaveta e o turno de caixa. A tela não recusa, mas também não deixa isso ser
// descoberto por acidente.
import type { StationTerminal } from "../types/operator";

/** Segunda linha da opção: o `ref` que desempata, e o que já está no balcão. */
export function stationTerminalHint(terminal: StationTerminal): string {
  const parts = [terminal.ref];
  const devices = terminal.active_devices ?? 0;
  if (devices === 1) parts.push("1 dispositivo já usa este balcão");
  else if (devices > 1) parts.push(`${devices} dispositivos já usam este balcão`);
  if (terminal.has_open_shift) parts.push("caixa aberto");
  return parts.join(" · ");
}
