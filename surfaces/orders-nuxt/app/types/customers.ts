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

export type CustomerListResponse = ReadMetadata & {
  list: CustomerListProjection;
};
export type CustomerDetailResponse = ReadMetadata & {
  customer: CustomerDetailProjection;
};
export type MergePreviewResponse = ReadMetadata & {
  preview: MergePreviewProjection;
};
export type MergeAuditListResponse = ReadMetadata & {
  merges: MergeAuditListProjection;
};
export type MergeResponse = {
  ok: boolean;
  source_ref: string;
  target_ref: string;
  audit_id: string;
};

export interface CustomerMutationPayload {
  expectedRevision?: string;
  firstName?: string;
  lastName?: string;
  customerType?: string;
  document?: string;
  birthday?: string;
  email?: string;
  phone?: string;
  priceTierRef?: string;
  tags?: string[];
  notes?: string;
  houseAccount?: boolean;
  houseAccountLimit?: string;
  fiscalCpfNaNota?: boolean;
  fiscalEmailReceipt?: boolean;
}

export type CustomerMutationResponse = {
  customer: CustomerDetailProjection;
  ok?: boolean;
  outcome?: "applied" | "not_applied" | "unknown";
  resource?: { kind: "customer" | "customer-address"; ref: string };
};

export interface CustomerAddressMutationPayload {
  expectedRevision?: string;
  label?: string;
  labelCustom?: string;
  formattedAddress?: string;
  route?: string;
  streetNumber?: string;
  complement?: string;
  neighborhood?: string;
  city?: string;
  stateCode?: string;
  postalCode?: string;
  deliveryInstructions?: string;
  isDefault?: boolean;
}

export type CustomerAddressMutationResponse = CustomerMutationResponse;
