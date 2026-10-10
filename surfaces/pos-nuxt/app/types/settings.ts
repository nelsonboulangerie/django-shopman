// Contrato da leitura `/api/v1/backstage/pos/settings/` (`services/pos_settings.build_settings`).

export interface PosPrinterSetting {
  terminal_ref: string;
  label: string;
  location: string;
  roll_width_mm: number | null;
  cut_mode: string;
  /** Estações sem tela que imprimem nesta impressora. */
  stations: string[];
}

export interface PosCardMachineSetting {
  ref: string;
  label: string;
  identification: string;
  active: boolean;
  /** O pedido com que a maquininha está agora ("" = no balcão). */
  with_order: string;
}

export interface PosKitchenStationSetting {
  ref: string;
  name: string;
  type: string;
  type_label: string;
  collections: string[];
  print_terminal: string;
  auto_fire: boolean;
}

export interface PosSettingsResponse {
  terminal_ref: string;
  terminal_label: string;
  printers: PosPrinterSetting[];
  roll_widths: number[];
  cut_modes: Array<{ value: string; label: string }>;
  card_machines: PosCardMachineSetting[];
  kitchen_stations: PosKitchenStationSetting[];
  shortcuts: {
    favorite_collection_refs: string[];
    collections: Array<{ ref: string; name: string }>;
  };
}
