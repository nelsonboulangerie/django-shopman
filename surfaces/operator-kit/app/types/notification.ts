// A caixa pessoal — espelho do contrato de `backstage/api/notifications.py`.

export interface UserNotification {
  pk: number;
  category: "campaign" | "production" | "order" | "sign_in" | "system";
  title: string;
  message: string;
  action_url: string;
  action_data: Record<string, unknown>;
  is_actionable: boolean;
  is_read: boolean;
  created_at: string;
  created_at_display: string;
}

export interface NotificationListResponse {
  notifications: UserNotification[];
  unread_count: number;
  actionable_count: number;
}

// Os acessos da PRÓPRIA conta — `backstage/api/sign_ins.py`.
export interface SignInEntry {
  pk: number;
  method: string;
  method_display: string;
  outcome: string;
  outcome_display: string;
  station_ref: string;
  station_display: string;
  ip_address: string;
  created_at: string;
  created_at_display: string;
  anomalies: string[];
  anomaly_labels: string[];
  highlight: boolean;
}

export interface SignInListResponse {
  sign_ins: SignInEntry[];
  highlighted_count: number;
}
