// Espelho TS da API de sessão do operador
// (shopman/backstage/api/operations.py: operator/session|eligible|unlock|lock).
// UMA identidade: quem prova PIN ou crachá VIRA a sessão, e é dela toda permissão.
import type { WorkstationCopy, WorkstationKind } from "../presentation/workstation";

export interface OperatorCard {
  id: number;
  username: string;
  name: string;
}

export interface OperatorSession {
  // De QUE POSTO esta tela é (`Workstation.ref`; no Caixa, o mesmo `Terminal.ref`),
  // ou "" quando o dispositivo não é uma estação reconhecida. Substituiu `device_user`: não há mais conta de
  // máquina para nomear, e o que a tela precisa saber é de onde ela fala.
  station: string;
  // O posto que a estação nomeia, com o contexto para o rail ("Posto Expedição").
  workstation?: WorkstationCard | null;
  operator: OperatorCard | null;
  locked: boolean;
  // O operador recebeu um PIN temporário (reset do gerente) e precisa trocá-lo
  // antes de operar. O shell força a troca quando true.
  pin_must_change: boolean;
  // Resposta somente para a capability solicitada pela superfície. Evita montar
  // o app para um operador identificado, porém sem acesso.
  authorized: boolean;
}

export type OperatorSessionResponse = OperatorSession;

export interface OperatorEligibleResponse {
  operators: OperatorCard[];
}

/** Um terminal que este dispositivo pode assumir (o `Terminal.ref` e o rótulo). */
/** O posto como a tela o mostra (rail, cabeçalho). Rótulos vêm do servidor
 *  (`workstation_vocabulary.py`), nunca de literal no front. */
export interface WorkstationCard {
  ref: string;
  label: string;
  kind: WorkstationKind;
  kind_label: string;
  /** Só o posto Caixa tem gaveta e turno. */
  has_cash_desk: boolean;
  /** "Posto Expedição": o contexto que o rail mostra. */
  context_label: string;
}

/** Uma opção da tela de vincular: o posto e o que já está nele. */
export interface WorkstationOption extends WorkstationCard {
  /** Dispositivos com confiança válida neste posto. No Caixa, dividem a gaveta e o
   *  turno (D-007): a tela mostra, não recusa. */
  active_devices: number;
  has_open_shift: boolean;
  /** Segunda linha da opção, já montada pelo servidor. */
  hint: string;
}

export interface WorkstationKindOption {
  kind: WorkstationKind;
  label: string;
}

/** O que a tela de vincular precisa: o posto deste dispositivo hoje (`""` quando
 *  nenhum), os postos que ESTE app oferece e a copy da fonte única. */
export interface StationProvisionState {
  station: string;
  workstation: WorkstationCard | null;
  kinds: WorkstationKindOption[];
  workstations: WorkstationOption[];
  copy: WorkstationCopy;
}

/** Um dispositivo vinculado a um posto (cadastro de Postos). */
export interface WorkstationDevice {
  id: string;
  label: string;
  ip_address: string;
  created_at: string | null;
  last_used_at: string | null;
}

/** Uma linha do cadastro de Postos: o posto, se está ativo e os dispositivos dele. */
export interface WorkstationManageRow extends WorkstationCard {
  is_active: boolean;
  devices: WorkstationDevice[];
}

/** `GET /api/v1/backstage/workstations/`: o cadastro inteiro, os tipos e a copy. */
export interface WorkstationManageState {
  station?: string;
  workstations: WorkstationManageRow[];
  kinds: WorkstationKindOption[];
  copy: WorkstationCopy;
}

export interface OperatorUnlockResponse {
  ok: boolean;
  operator: OperatorCard;
}
