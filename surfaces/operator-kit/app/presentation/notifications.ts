// Leitura pura da caixa pessoal. Sem fetch, sem Vue — só as decisões de tela,
// que é o que vale a pena travar com teste.
import type { SignInEntry, UserNotification } from "../types/notification";

/** O contador do sino. Acima de 9 vira "9+": o número exato não muda decisão. */
export function badgeCount(unread: number): string {
  if (unread <= 0) return "";
  return unread > 9 ? "9+" : String(unread);
}

/**
 * Este aviso merece realce?
 *
 * ⚠️ Realce, nunca silo. Todo acesso vira aviso e todos moram na MESMA lista —
 * o olho é que para no que é anômalo. Separar os suspeitos numa aba própria
 * esconderia o resto, que é o oposto do que o dono pediu.
 */
export function isHighlighted(n: Pick<UserNotification, "action_data">): boolean {
  return Boolean((n.action_data as { highlight?: boolean } | null)?.highlight);
}

/** Os códigos de anomalia que o backend já traduziu, prontos para a linha. */
export function anomalyLabels(n: Pick<UserNotification, "action_data">): string[] {
  const raw = (n.action_data as { anomalies?: unknown } | null)?.anomalies;
  return Array.isArray(raw) ? raw.map(String) : [];
}

/** Um aviso de acesso aponta para o log; os demais, para a tela do assunto. */
export function isSignIn(n: Pick<UserNotification, "category">): boolean {
  return n.category === "sign_in";
}

/** Resumo de uma linha de acesso, para a lista dentro do painel. */
export function signInSummary(entry: SignInEntry): string {
  const partes = [entry.method_display, entry.station_display];
  if (entry.outcome !== "success") partes.unshift(entry.outcome_display);
  return partes.join(" · ");
}

/** Quantos avisos ainda não lidos, defensivo contra resposta truncada. */
export function unreadOf(list: { unread_count?: number } | null): number {
  return Math.max(0, Number(list?.unread_count ?? 0));
}
