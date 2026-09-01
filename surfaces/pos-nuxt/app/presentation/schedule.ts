// QUANDO — "é para hoje ou para outro dia?".
//
// Terceira pergunta da barra de contexto, irmã de Cliente e Recebimento. Morava
// dentro do formulário de ENTREGA, e por isso a retirada agendada não existia: a
// casa recebe encomenda por telefone para retirar na quinta, e o operador não
// tinha onde escrever isso. *Quando* é fato do PEDIDO; só *onde* e *quanto* são
// fatos da entrega.
//
// Aqui só mora o formato. A oferta de datas e a compatibilidade das janelas vêm
// prontas do servidor (`/pos/schedule/`) — a tela não decide o que a casa pode
// prometer.

/** Uma janela de meia hora, já anotada pelo servidor para este carrinho. */
export interface ScheduleWindow {
  ref: string;
  label: string;
  /** Cabe no preparo dos itens deste pedido. */
  enabled?: boolean;
  /** Por que não cabe, em português de balcão. */
  reason?: string;
}

const DIAS = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];

/**
 * "2026-09-10" → `Date` no fuso LOCAL.
 *
 * `new Date("2026-09-10")` lê a string como UTC e, a oeste de Greenwich, devolve
 * o dia ANTERIOR — a quinta vira quarta na etiqueta do botão. Partir a string à
 * mão é o que mantém a data que o servidor mandou sendo a data que a tela diz.
 */
export function parseLocalDate(iso: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec((iso || "").trim());
  if (!match) return null;
  const [, y, m, d] = match;
  const date = new Date(Number(y), Number(m) - 1, Number(d));
  return Number.isNaN(date.getTime()) ? null : date;
}

/** "10/09" — a data curta que cabe num botão de barra. */
export function shortDate(iso: string): string {
  const date = parseLocalDate(iso);
  if (!date) return "";
  const dd = String(date.getDate()).padStart(2, "0");
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  return `${dd}/${mm}`;
}

/**
 * Como a data se chama para quem está no balcão.
 *
 * "Hoje" e "Amanhã" por nome, porque é assim que o operador fala com o cliente
 * ao telefone. De depois de amanhã em diante, o dia da semana entra junto: "qui,
 * 10/09" responde a pergunta que o cliente realmente faz ("que dia da semana?")
 * sem obrigar ninguém a contar no calendário.
 */
export function dateLabel(iso: string, today: string): string {
  if (!iso) return "";
  if (iso === today) return "Hoje";
  const date = parseLocalDate(iso);
  const todayDate = parseLocalDate(today);
  if (date && todayDate) {
    const dias = Math.round((date.getTime() - todayDate.getTime()) / 86_400_000);
    if (dias === 1) return "Amanhã";
  }
  const dia = date ? DIAS[date.getDay()] : "";
  const curta = shortDate(iso);
  return dia ? `${dia}, ${curta}` : curta;
}

/**
 * O rótulo do botão na barra de contexto.
 *
 * "Para hoje" é o estado padrão e ele é uma AFIRMAÇÃO, não um campo vazio: a
 * esmagadora maioria das vendas é para agora, e a barra tem que dizer isso sem
 * parecer que falta preencher alguma coisa. Só quando há combinado é que o
 * botão passa a carregá-lo.
 */
export function scheduleLabel(
  deliveryDate: string,
  windowLabel: string,
  today: string,
): string {
  const agendado = Boolean(deliveryDate) && deliveryDate !== today;
  if (!agendado) return windowLabel ? `Hoje, ${windowLabel}` : "Para hoje";
  const dia = dateLabel(deliveryDate, today);
  return windowLabel ? `${dia}, ${windowLabel}` : dia;
}

/** O pedido é para outro dia? Muda o ícone e o realce do botão. */
export function isScheduled(deliveryDate: string, today: string): boolean {
  return Boolean(deliveryDate) && deliveryDate !== today;
}

/** O rótulo de uma janela pelo ref, ou o próprio ref quando ela sumiu da grade. */
export function windowLabel(windows: ScheduleWindow[], ref: string): string {
  if (!ref) return "";
  return windows.find((w) => w.ref === ref)?.label || ref;
}

/**
 * O rótulo do chip QUANDO a escolha virou impossível sozinha.
 *
 * O chip mostrava "qui, 10/09, 09:00 às 09:30" com toda a calma depois de o
 * operador lançar a baguete que empurra o pedido para as 12h. Ele só descobria
 * num 422 seco no Finalizar — e o cliente já tinha ouvido o horário. O aviso
 * precisa estar onde ele olha de relance, não só dentro do diálogo que ele
 * fechou.
 */
export function scheduleChipTone(
  windows: ScheduleWindow[],
  ref: string,
): "ok" | "conflict" {
  return selectedWindowConflict(windows, ref) ? "conflict" : "ok";
}

/**
 * A janela escolhida ainda cabe?
 *
 * O operador escolhe "09:00 às 09:30" e SÓ DEPOIS lança a baguete de tradição.
 * A escolha vira impossível sem ninguém tocar nela, e a tela precisa perceber
 * isso na hora — o servidor recusa no fim, mas descobrir na tela de pagamento é
 * tarde: o cliente já ouviu o horário.
 *
 * Janela desconhecida da grade NÃO é tratada como inválida: o dia pode ter
 * mudado de expediente, e "a grade não tem" é assunto de oferta, não de
 * promessa quebrada (a mesma calibração que o servidor faz em
 * `fulfillment_window.validate`).
 */
export function selectedWindowConflict(
  windows: ScheduleWindow[],
  ref: string,
): string {
  if (!ref) return "";
  const found = windows.find((w) => w.ref === ref);
  if (!found || found.enabled !== false) return "";
  return found.reason || "Este horário não cabe no preparo deste pedido.";
}

/**
 * A frase única do topo do diálogo quando algo do carrinho segura o pedido.
 *
 * Dita uma vez, no lugar de repetir o mesmo motivo em dez janelas apagadas.
 */
export function readinessNote(bottleneckName: string, readyAt: string): string {
  if (!bottleneckName || !readyAt) return "";
  return `${bottleneckName} sai às ${readyAt}. Antes disso não dá para prometer.`;
}
