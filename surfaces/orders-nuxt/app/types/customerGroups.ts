import type {
  CustomerGroupFormOptionsProjection,
  CustomerGroupListProjection,
  CustomerGroupProjection,
} from "~/generated/ordersContract";
import type { ReadMetadata } from "./readMetadata";

export type CustomerGroupListResponse = ReadMetadata & { groups: CustomerGroupListProjection };
export type CustomerGroupDetailResponse = ReadMetadata & { group: CustomerGroupProjection };

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
}

export type CustomerGroupMutationResponse = {
  ok?: boolean;
  outcome?: "applied" | "not_applied" | "unknown";
  group: CustomerGroupProjection;
  resource?: { kind: "customer-group"; ref: string };
};

export type { CustomerGroupFormOptionsProjection, CustomerGroupProjection };
