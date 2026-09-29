import type { ReadMetadata } from "./readMetadata";
// Gerado da projeção canônica `shopman/backstage/projections/channel_health.py`.
import type { ChannelHealthBoardProjection } from "../generated/ordersContract";
export type { ChannelHealthItem, ChannelHealthLink, ChannelHealthProjection, ChannelHealthBoardProjection } from "../generated/ordersContract";

export interface ChannelHealthResponse extends ReadMetadata {
  health: ChannelHealthBoardProjection;
}
