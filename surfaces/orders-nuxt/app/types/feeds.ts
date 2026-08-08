// TS mirror da projeção de Feeds (model Feed) (shopman/backstage/projections/feeds.py).

export interface FeedCollectionRef {
  ref: string;
  name: string;
  exists: boolean;
}

export interface FeedProjection {
  ref: string;
  name: string;
  kind: "menuboard" | "google" | "meta";
  kind_label: string;
  kind_icon: string;
  capability: "display" | "feed";
  is_active: boolean;
  output_path: string;
  collections: FeedCollectionRef[];
}

export interface CollectionOptionProjection {
  ref: string;
  name: string;
  product_count: number;
}

export interface FeedBoardProjection {
  feeds: FeedProjection[];
  all_collections: CollectionOptionProjection[];
}

export interface FeedBoardResponse {
  board: FeedBoardProjection;
}
