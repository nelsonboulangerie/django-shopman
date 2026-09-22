import type { ReadMetadata } from "./readMetadata";
// Generated from the canonical Channel display projections.
import type { FeedBoardProjection } from "../generated/ordersContract";
export type {
  CatalogChannelProjection,
  ChannelPeriodOption,
  ChannelSwitchProjection,
  CollectionOptionProjection,
  FeedBoardProjection,
  FeedCollectionRef,
  FeedProjection,
  ManagerOptionProjection,
} from "../generated/ordersContract";

export interface FeedBoardResponse extends ReadMetadata {
  board: FeedBoardProjection;
}
