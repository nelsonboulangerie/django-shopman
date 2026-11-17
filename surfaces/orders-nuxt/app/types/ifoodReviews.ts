// Avaliações do iFood: espelho de shopman/backstage/projections/ifood_reviews.py.
// GET /api/v1/backstage/ifood/reviews/ · /summary/ · /<id>/ · POST /<id>/reply/

export interface IFoodReviewReply {
  text: string;
  author: string;
  author_label: string;
  created_at: string;
  created_at_display: string;
}

export interface IFoodReviewQuestion {
  title: string;
  kind: string;
  answers: string[];
}

export interface IFoodReview {
  id: string;
  status: string;
  status_label: string;
  visibility: string;
  visibility_label: string;
  version: string;
  score: number | null;
  score_display: string;
  previous_score: number | null;
  score_changed: boolean;
  comment: string;
  customer_name: string;
  created_at: string;
  created_at_display: string;
  order_id: string;
  order_short_id: string;
  order_created_at_display: string;
  replies: IFoodReviewReply[];
  questions: IFoodReviewQuestion[];
  survey_id: string;
  can_reply: boolean;
}

export interface IFoodReviewList {
  enabled: boolean;
  policy_url: string;
  page: number;
  page_size: number;
  total: number | null;
  page_count: number | null;
  reviews: IFoodReview[];
  reply_min_chars: number;
  reply_max_chars: number;
  ifood_max_page_size: number;
}

export interface IFoodReviewSummary {
  score: number | null;
  score_display: string;
  total_reviews: number | null;
  valid_reviews: number | null;
}

/** Recusa do iFood repassada pela API do Gestor. */
export interface IFoodReviewError {
  detail?: string;
  ifood_status?: number;
  ifood_message?: string;
}
