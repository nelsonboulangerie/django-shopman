// A loja no iFood — espelho de shopman/backstage/projections/ifood_store.py.
// GET /api/v1/backstage/ifood/store/ · ligar/desligar é o toggle do card (feeds/switch).

export interface IFoodStoreProjection {
  enabled: boolean;
  governs: boolean;
  /** Canal iFood desligado no Gestor (toggle "Ativo" do card). */
  channel_off: boolean;
  /** Quem vê pode abrir a aba Canais (onde mora o toggle). */
  can_open_channels: boolean;
  shop_open: boolean;
  shop_message: string;
  ifood_available: boolean | null;
  ifood_status_label: string;
  ifood_checked_at_display: string;
  ifood_problems: string[];
  diverges: boolean;
}
