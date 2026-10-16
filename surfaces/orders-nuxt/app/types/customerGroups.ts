import type {
  CustomerGroupAdvantageProjection,
  CustomerGroupFormOptionsProjection,
  CustomerGroupListProjection,
  CustomerGroupProjection,
} from "~/generated/ordersContract";
import type { ReadMetadata } from "./readMetadata";

export type CustomerGroupListResponse = ReadMetadata & { groups: CustomerGroupListProjection };
export type CustomerGroupDetailResponse = ReadMetadata & { group: CustomerGroupProjection };

/** Os tipos de vantagem que um grupo carrega. Um por linha, sem acumular. */
export const CUSTOMER_GROUP_ADVANTAGE_KINDS = [
  "free_shipping",
  "exclusive_collections",
  "exclusive_notifications",
] as const;
export type CustomerGroupAdvantageKind = (typeof CUSTOMER_GROUP_ADVANTAGE_KINDS)[number];

/**
 * Uma vantagem tipada indo para o servidor. `isActive` e `priority` valem para
 * todos os tipos; a configuração é do tipo, e chave ausente não é tocada: quem
 * escolhe as coleções é esta tela, e os avisos exclusivos são do Marketing.
 */
export interface CustomerGroupAdvantageInput {
  kind: CustomerGroupAdvantageKind;
  isActive: boolean;
  priority: number;
  minOrderQ?: string;
  collectionRefs?: string[];
}

export interface CustomerGroupMutationPayload {
  expectedRevision?: string;
  ref: string;
  name: string;
  description: string;
  listingRef: string;
  priority: number;
  isDefault: boolean;
  discountType: string;
  discountValue: string;
  channelRefs: string[];
  pickupOnly: boolean;
  discountKind: string;
  rounding: boolean;
  savingsMessage: string;
  advantages: CustomerGroupAdvantageInput[];
}

export type CustomerGroupMutationResponse = {
  ok?: boolean;
  outcome?: "applied" | "not_applied" | "unknown";
  group: CustomerGroupProjection;
  resource?: { kind: "customer-group"; ref: string };
};

export type {
  CustomerGroupAdvantageProjection,
  CustomerGroupFormOptionsProjection,
  CustomerGroupProjection,
};
