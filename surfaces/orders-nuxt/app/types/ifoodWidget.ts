// O widget oficial do iFood — espelho de IFoodWidgetProjection
// (shopman/backstage/projections/ifood_store.py). GET /api/v1/backstage/ifood/widget/.

export interface IFoodWidgetProjection {
  /** Vazio = desligado: o Gestor não carrega nada do iFood no navegador. */
  widget_id: string;
  merchant_ids: string[];
}
