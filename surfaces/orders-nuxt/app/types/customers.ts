// Envelopes das leituras de Clientes. O conteúdo é o contrato gerado das projections
// (`shopman/backstage/projections/customers.py` → `generated/ordersContract.ts`);
// aqui só a casca de cada endpoint.
import type {
  CustomerDetailProjection,
  CustomerListProjection,
  MergeAuditListProjection,
  MergePreviewProjection,
} from "~/generated/ordersContract";
import type { ReadMetadata } from "./readMetadata";

export type CustomerListResponse = ReadMetadata & { list: CustomerListProjection };
export type CustomerDetailResponse = ReadMetadata & { customer: CustomerDetailProjection };
export type MergePreviewResponse = ReadMetadata & { preview: MergePreviewProjection };
export type MergeAuditListResponse = ReadMetadata & { merges: MergeAuditListProjection };
export type MergeResponse = { ok: boolean; source_ref: string; target_ref: string; audit_id: string };
