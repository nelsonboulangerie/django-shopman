/** Os números do topo do Painel, contados na grandeza certa.
 *
 * ⚠️ O ledger conta `DeliveryTarget`, e um alvo de WhatsApp é uma PESSOA enquanto um
 * alvo de Instagram, Facebook ou Google é uma POSTAGEM. Somar os dois num número só
 * produzia "12 entregas confirmadas hoje" que tanto podia ser doze pessoas quanto nove
 * pessoas e três murais — e é o primeiro número que o gestor lê de manhã, o que ele usa
 * para decidir se disparou demais.
 *
 * Onde o número é uma boa notícia, ele aparece separado em dois cartões, cada um com o
 * nome da sua grandeza. Onde o número é um problema a resolver — sem confirmação,
 * falhas, incertos — ele fica junto, porque dois alarmes em cartões distintos escondem
 * o menor; aí a linha de baixo diz de quê é o total.
 */
import { formatCount } from "~/presentation/campaign";

export interface GrandezaSplit {
  total: number;
  /** "37 pessoas · 1 postagem" — vazio quando o total é zero e não há o que detalhar. */
  breakdown: string;
}

function plural(count: number, one: string, many: string): string {
  return `${formatCount(count)} ${count === 1 ? one : many}`;
}

export function splitByGrandeza(input: {
  people: number;
  posts: number;
}): GrandezaSplit {
  const people = Math.max(0, Math.trunc(input.people || 0));
  const posts = Math.max(0, Math.trunc(input.posts || 0));
  const total = people + posts;
  if (total === 0) return { total: 0, breakdown: "" };
  // Com uma grandeza só, repetir a conta embaixo do número é ruído: o cartão já diz
  // tudo quando "3" e "3 pessoas" são a mesma informação.
  if (posts === 0) return { total, breakdown: plural(people, "pessoa", "pessoas") };
  if (people === 0) return { total, breakdown: plural(posts, "postagem", "postagens") };
  return {
    total,
    breakdown: `${plural(people, "pessoa", "pessoas")} · ${plural(posts, "postagem", "postagens")}`,
  };
}
