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


/** Um aviso de acesso aponta para o log; os demais, para a tela do assunto. */
export function isSignIn(n: Pick<UserNotification, "category">): boolean {
  return n.category === "sign_in";
}

/**
 * A ordem da caixa pessoal (beta 05/11, CEN-01): o que pede gesto da operação (o lote na
 * Qualidade) vem antes dos acessos, e não depois de 28 deles. Os acessos continuam na
 * MESMA lista (realce, nunca silo): o suspeito aparece inteiro, um por um; os de rotina,
 * quando passam de `groupFrom`, viram UMA linha que se abre ali mesmo ("5 acessos seus
 * sem nada fora do comum"). Nada some: só deixa de empurrar o resto para baixo.
 */
export interface InboxLayout {
  /** Avisos da operação e da casa, na ordem do servidor (mais novo primeiro). */
  operation: UserNotification[];
  /** Acessos mostrados um por um: os destacados, ou todos se forem poucos. */
  signIns: UserNotification[];
  /** Acessos de rotina agrupados numa linha só (vazio quando são poucos). */
  routine: UserNotification[];
}

export function inboxLayout(items: readonly UserNotification[], groupFrom = 3): InboxLayout {
  const operation = items.filter((item) => !isSignIn(item));
  const access = items.filter(isSignIn);
  const routine = access.filter((item) => !isHighlighted(item));
  if (routine.length < groupFrom) return { operation, signIns: access, routine: [] };
  return { operation, signIns: access.filter(isHighlighted), routine };
}

/** A linha dos acessos de rotina agrupados. */
export function routineSignInsLabel(count: number): string {
  return count === 1
    ? "1 acesso seu sem nada fora do comum"
    : `${count} acessos seus sem nada fora do comum`;
}

/** "Não fui eu" só existe sobre um acesso que aconteceu (o servidor diz `is_actionable`). */
export function canReportNotMe(n: Pick<UserNotification, "category" | "is_actionable">): boolean {
  return isSignIn(n) && n.is_actionable;
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
