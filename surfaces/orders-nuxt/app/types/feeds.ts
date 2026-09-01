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
  rotate_seconds: number; // menuboard: cadência da troca de páginas (0 = sem rotação)
  items_per_page: number; // menuboard: teto de itens por tela (0 = tudo numa página)
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
