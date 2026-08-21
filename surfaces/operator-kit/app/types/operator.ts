// Espelho TS da API de sessão do operador
// (shopman/backstage/api/operations.py: operator/session|eligible|unlock|lock).
// UMA identidade: quem prova PIN ou crachá VIRA a sessão, e é dela toda permissão.

export interface OperatorCard {
  id: number;
  username: string;
  name: string;
}

export interface OperatorSession {
  // De QUE BALCÃO esta tela é (`Terminal.ref`), ou "" quando o aparelho não é
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

export interface OperatorUnlockResponse {
  ok: boolean;
  operator: OperatorCard;
}
