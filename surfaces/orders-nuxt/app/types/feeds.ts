import type { ReadMetadata } from "./readMetadata";
// Generated from the canonical Channel display projections.
import type { FeedBoardProjection } from "../generated/ordersContract";
export type { FeedCollectionRef, FeedProjection, CollectionOptionProjection, FeedBoardProjection } from "../generated/ordersContract";

export interface FeedBoardResponse extends ReadMetadata {
  board: FeedBoardProjection;
}
