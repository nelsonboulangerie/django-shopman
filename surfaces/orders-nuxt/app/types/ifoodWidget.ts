// O widget oficial do iFood — espelho de IFoodWidgetProjection
// (shopman/backstage/projections/ifood_store.py). GET /api/v1/backstage/ifood/widget/.

export interface IFoodWidgetProjection {
  /** Vazio = desligado: o Gestor não carrega nada do iFood no navegador. */
  widget_id: string;
  merchant_ids: string[];
  /** Há pedido iFood aberto e ainda não entregue: o botão do iFood aparece. */
  has_order_in_progress: boolean;
}
