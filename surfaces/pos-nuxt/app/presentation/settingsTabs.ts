/**
 * As abas de PDV › Ajustes, na ordem da v4 (`salao-mesas4.html` pino 1). URL em
 * inglês (convenção das superfícies de operador); o rótulo é o da casa.
 */
export const POS_SETTINGS_TABS = [
  { key: "terminal", label: "Terminal", to: "/settings/terminal" },
  { key: "printers", label: "Impressoras", to: "/settings/printers" },
  { key: "card-machines", label: "Maquininhas", to: "/settings/card-machines" },
  { key: "seating", label: "Salão", to: "/settings/seating" },
  { key: "kitchen", label: "Envio à cozinha", to: "/settings/kitchen" },
  { key: "shortcuts", label: "Atalhos de venda", to: "/settings/shortcuts" },
] as const;

export type PosSettingsTabKey = (typeof POS_SETTINGS_TABS)[number]["key"];
