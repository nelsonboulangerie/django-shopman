// POSTOS de trabalho: o espelho tipado das CHAVES de
// `shopman/backstage/workstation_vocabulary.py`. Só chaves, nunca texto: os rótulos
// dos tipos e a copy da tela chegam pela projection (`operator/station/`), para que
// renomear um posto seja mudar uma linha no backend. O dono ainda está decidindo
// nomes ("Expedição" ou "Saída"), e duas fontes de texto divergiriam no primeiro
// rename.
//
// O teste `workstation.test.ts` confere estas listas contra o arquivo Python.

export const WORKSTATION_KINDS = [
  "cash_desk",
  "service",
  "dispatch",
  "kitchen_station",
  "production_room",
  "office",
] as const;

export type WorkstationKind = (typeof WORKSTATION_KINDS)[number];

export const WORKSTATION_COPY_KEYS = [
  "setup_title",
  "setup_lead",
  "setup_choice_label",
  "setup_confirm",
  "setup_confirm_shared",
  "setup_busy",
  "setup_dismiss",
  "setup_error",
  "setup_empty",
  "context_prefix",
  "release",
  "cash_desk_hint",
  "devices_one",
  "devices_many",
  "open_shift_hint",
  "shared_cash_desk",
  "unknown",
  "not_a_workstation",
  "manage_title",
  "manage_lead",
  "manage_new",
  "manage_name_label",
  "manage_kind_label",
  "manage_create",
  "manage_rename",
  "manage_save",
  "manage_deactivate",
  "manage_deactivate_warning",
  "manage_keep_active",
  "manage_activate",
  "manage_inactive",
  "manage_cash_desk_note",
  "manage_devices_none",
  "manage_device_last_used",
  "manage_device_never_used",
  "manage_error",
] as const;

export type WorkstationCopyKey = (typeof WORKSTATION_COPY_KEYS)[number];
export type WorkstationCopy = Record<WorkstationCopyKey, string>;

/** Ícone por tipo: identidade visual, não texto (o texto vem do servidor). */
export const WORKSTATION_KIND_ICON: Record<WorkstationKind, string> = {
  cash_desk: "lucide:wallet",
  service: "lucide:hand-platter",
  dispatch: "lucide:package-check",
  kitchen_station: "lucide:chef-hat",
  production_room: "lucide:wheat",
  office: "lucide:briefcase",
};

export function workstationKindIcon(kind: string): string {
  return WORKSTATION_KIND_ICON[kind as WorkstationKind] ?? "lucide:map-pin";
}

export interface WorkstationRadioOption {
  value: string;
  label: string;
  hint: string;
}

/** As opções do seletor: o nome do posto, e na segunda linha o tipo e a ocupação. */
export function workstationRadioOptions(
  options: { ref: string; label: string; kind_label: string; hint: string }[],
): WorkstationRadioOption[] {
  return options.map((option) => ({
    value: option.ref,
    label: option.label,
    hint: [option.kind_label, option.hint].filter(Boolean).join(" · "),
  }));
}

/**
 * Oferecer vincular este dispositivo a um posto? Só com alguém identificado e destravado
 * (quem vincula precisa estar ali), num dispositivo que ainda não é posto, e enquanto a
 * oferta não foi dispensada. É oferta, não parede: "usar sem vincular" é resposta certa no
 * notebook pessoal do gestor.
 */
export function shouldOfferStationSetup(input: {
  canIdentify: boolean;
  locked: boolean;
  stationRef: string;
  dismissed: boolean;
}): boolean {
  return input.canIdentify && !input.locked && !input.stationRef && !input.dismissed;
}
