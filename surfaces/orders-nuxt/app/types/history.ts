// Envelope da leitura do Histórico. O conteúdo é o contrato gerado da projection
// (`shopman/backstage/projections/order_history.py` → `generated/ordersContract.ts`).
import type { OrderHistoryProjection } from "~/generated/ordersContract";
import type { ReadMetadata } from "./readMetadata";

export type OrderHistoryResponse = ReadMetadata & { history: OrderHistoryProjection };
