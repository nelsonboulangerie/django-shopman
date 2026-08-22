// Espelho TS da API de sessão do operador
// (shopman/backstage/api/operations.py: operator/session|eligible|unlock|lock).
// UMA identidade: quem prova PIN ou crachá VIRA a sessão, e é dela toda permissão.

export interface OperatorCard {
  id: number;
  username: string;
  name: string;
}

export interface OperatorSession {
  // De QUE BALCÃO esta tela é (`Terminal.ref`), ou "" quando o dispositivo não é
  // uma estação reconhecida. Substituiu `device_user`: não há mais conta de
  // máquina para nomear, e o que a tela precisa saber é de onde ela fala.
  station: string;
  operator: OperatorCard | null;
  locked: boolean;
  // O operador recebeu um PIN temporário (reset do gerente) e precisa trocá-lo
  // antes de operar. O shell força a troca quando true.
  pin_must_change: boolean;
}

export type OperatorSessionResponse = OperatorSession;

export interface OperatorEligibleResponse {
  operators: OperatorCard[];
}

/** Um terminal que este dispositivo pode assumir (o `Terminal.ref` e o rótulo). */
export interface StationTerminal {
  ref: string;
  label: string;
}

/** O que a tela de provisionamento precisa: que estação este dispositivo é hoje
 *  (`""` quando nenhuma), e as opções. */
export interface StationProvisionState {
  station: string;
  terminals: StationTerminal[];
}

export interface OperatorUnlockResponse {
  ok: boolean;
  operator: OperatorCard;
}
