// Canais que pedem atenção — espelho de shopman/backstage/projections/channel_attention.py.
// GET /api/v1/backstage/channels/attention/ → { attention }

export interface ChannelAttentionItem {
  ref: string;
  name: string;
  kind: "sale" | "display";
  state: "off" | "paused" | "diverges";
  line: string;
  focus_path: string;
}

export interface ChannelAttentionProjection {
  count: number;
  label: string;
  items: ChannelAttentionItem[];
  queue: ChannelAttentionItem[];
  can_open_channels: boolean;
}
