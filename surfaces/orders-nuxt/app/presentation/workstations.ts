// Presentation: o cadastro de Postos do Gestor. Puro. As palavras vêm do servidor
// (`copy`, fonte única em `workstation_vocabulary.py`); aqui só se monta a frase.
import type {
  WorkstationDevice,
  WorkstationKindOption,
  WorkstationManageRow,
} from "../../../operator-kit/app/types/operator";
import type { WorkstationCopy } from "../../../operator-kit/app/presentation/workstation";

const WHEN = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "America/Sao_Paulo",
});

/** "Usado por último em 03/10, 14:20" ou "Ainda não usado". */
export function deviceUsageLine(device: WorkstationDevice, copy: Partial<WorkstationCopy>): string {
  if (!device.last_used_at) return copy.manage_device_never_used ?? "";
  const when = WHEN.format(new Date(device.last_used_at));
  return (copy.manage_device_last_used ?? "{when}").replace("{when}", when);
}

/** O nome do dispositivo, com o IP quando ele ajuda a dizer qual é. */
export function deviceName(device: WorkstationDevice): string {
  return [device.label, device.ip_address].filter(Boolean).join(" · ");
}

/** "2 dispositivos", "1 dispositivo", ou a frase de nenhum. */
export function devicesSummary(row: WorkstationManageRow, copy: Partial<WorkstationCopy>): string {
  const n = row.devices.length;
  if (n === 0) return copy.manage_devices_none ?? "";
  if (n === 1) return copy.devices_one ?? "";
  return (copy.devices_many ?? "{n}").replace("{n}", String(n));
}

/** Os tipos que o cadastro pode criar: o Caixa nasce com o caixa, não aqui. */
export function creatableKinds(kinds: WorkstationKindOption[]): WorkstationKindOption[] {
  return kinds.filter((kind) => kind.kind !== "cash_desk");
}

/** Os tipos para que um posto pode mudar: Caixa só para quem tem caixa. */
export function editableKinds(kinds: WorkstationKindOption[], row: WorkstationManageRow): WorkstationKindOption[] {
  return row.has_cash_desk ? kinds : creatableKinds(kinds);
}
