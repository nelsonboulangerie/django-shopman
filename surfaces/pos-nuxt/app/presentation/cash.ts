// Presentation — cash drawer shaping (spec §2.6, blind count).
//
// Pure transforms for the POS cash panel: the movement-kind labels, the
// opened-at formatting, and the terminal-occupied gate. The shift's full
// reconciliation report (expected vs counted, variance) lives in the backoffice
// (Unfold), NOT here — the POS never reveals the expected drawer, so the
// operator counts blind and the system computes the variance server-side.

import type {
  POSCashManagementCapability,
  POSCashRuntimeProjection,
  POSChangeDenomination,
  POSChangeRequestProjection,
} from "~/types/pos";

/**
 * O rótulo que o operador lê. O REF continua `sangria`/`suprimento` — é o
 * identificador do domínio, viaja na API e está no banco.
 *
 * "Sangria" é vocabulário de PDV brasileiro: quem trabalha em varejo sabe, quem
 * lê a filipeta dias depois não. Entrada/Saída não precisa ser aprendido, e a
 * conferência do caixa é feita justamente por quem não estava no balcão.
 */
const MOVEMENT_LABELS: Record<string, string> = {
  sangria: "Saída de caixa",
  suprimento: "Entrada de caixa",
};

export function movementLabel(kind: string): string {
  return MOVEMENT_LABELS[kind] || kind;
}

/**
 * Os motivos que viram botão, por tipo de movimento — vindos do SERVIDOR.
 *
 * O motivo é obrigatório na saída e quem cobra é o servidor. Exigir DIGITAÇÃO
 * no meio da fila é como se obriga o balcão a escrever "sangria" no campo e
 * seguir a vida: a exigência sobrevive e a informação morre. Com opções para
 * tocar, ele responde a única pergunta que a trilha precisa depois: **para onde
 * foi**.
 *
 * ⚠️ A ENTRADA vem com lista vazia, e isso é deliberado: "entrada de caixa" já
 * é a resposta inteira, e um campo com uma opção só ensina o balcão a preencher
 * qualquer coisa para passar.
 *
 * ⚠️ "Troco" NÃO é motivo de saída, e a ausência é deliberada — há teste que
 * trava, no servidor. Trocar uma nota não muda o dinheiro que existe na gaveta:
 * saem R$ 50, entram 5×R$ 10, o total é o mesmo. Lançar como saída derruba o
 * esperado por um dinheiro que nunca saiu, e o turno fecha com falta fantasma.
 * Quem precisa de troco PEDE troco, que é outro fluxo e é net zero.
 */
export function movementReasons(
  cashManagement: POSCashManagementCapability | null | undefined,
  kind: string,
): readonly string[] {
  return cashManagement?.movement_reasons?.[kind] || [];
}

/**
 * Se o movimento pode ser registrado.
 *
 * A tela reprova ANTES para o operador não convocar o gerente e só então
 * descobrir que faltava um campo. O servidor reprova de novo, e é lá que a
 * regra vale: contrato que só a superfície cobra não é contrato.
 *
 * O motivo é exigido só na SAÍDA. Na entrada não há o que perguntar.
 */
export function canRegisterMovement(kind: string, amount: string, reason: string): boolean {
  // Movimento de zero não move nada: o valor precisa ser legível E positivo.
  // Antes bastava "não vazio", e um "1,2,3" colado virava "0" no servidor.
  const amountQ = amountToQ(amount);
  if (!kind || amountQ === null || amountQ <= 0) return false;
  return kind === "sangria" ? Boolean(reason.trim()) : true;
}

/**
 * Abertura e fechamento exigem um valor EXPLÍCITO e legível — zero incluso.
 *
 * Zero é resposta de verdade nas duas pontas: abrir sem fundo de troco e
 * fechar uma gaveta esvaziada acontecem. O que não pode é campo vazio virar
 * "0" calado (era o defeito do fechar caixa): vazio não é contagem, é
 * pergunta sem resposta.
 */
export function canSubmitCashAmount(raw: string): boolean {
  return amountToQ(raw) !== null;
}

/**
 * A mensagem inline de valor ilegível — "" quando não há o que acusar.
 *
 * Vazio não acusa nada: o CTA desarmado já diz que falta responder, e gritar
 * antes de a pessoa digitar é validação que atrapalha. A mensagem só aparece
 * quando existe texto e ele não é um valor.
 */
export function amountInputError(raw: string): string {
  if (!String(raw ?? "").trim()) return "";
  return amountToQ(raw) === null ? "Valor ilegível. Use números, como 25,00." : "";
}

/**
 * Format the shift opening timestamp for the panel header (pt-BR, short). Falls
 * back to the raw string if it is not a parseable date, and to an em dash when
 * absent.
 */
export function formatOpenedAt(raw: string | null | undefined): string {
  if (!raw) return "—";
  const date = new Date(raw);
  return Number.isNaN(date.getTime())
    ? raw
    : date.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

/**
 * Whether selling requires an open cash shift — the sale screen redirects to
 * the session lobby (`/session`) when there is none. Contract-driven via the
 * checkout capability (absent flag = required, the safe default).
 */
export function requiresOpenShiftForSale(
  cashManagement: POSCashManagementCapability | null | undefined,
): boolean {
  return cashManagement?.requires_open_shift_for_sale !== false;
}

// ── Pedido de troco ────────────────────────────────────────────────────────
//
// Quando falta troco, o operador saía do balcão com dinheiro até o cofre: parte
// do trajeto tem câmera, parte não, e a falta só apareceria no fechamento. Aqui
// ele PEDE, alguém traz, e a troca acontece no balcão entre duas pessoas.
//
// ⚠️ Trocar dinheiro é NET ZERO — saem R$ 50, entram 5×R$ 10. Nada nesta seção
// fala de valor esperado, movimento ou fechamento, e não pode passar a falar:
// somar um pedido ao caixa inventaria uma diferença que não existe.

/**
 * As cédulas e moedas que o balcão pode pedir — vindas do SERVIDOR.
 *
 * Repetir os números aqui seria assinar uma divergência para o dia em que uma
 * moeda saísse de circulação: o pedido passaria a falar de um dinheiro que não
 * existe, e ninguém descobriria pela tela.
 */
export function changeDenominations(
  cashManagement: POSCashManagementCapability | null | undefined,
): readonly POSChangeDenomination[] {
  return cashManagement?.change_denominations || [];
}

/**
 * O valor é sempre exigido, e é EXATO.
 *
 * Antes havia um pedido "aproximado" ao lado de "moedas" e "notas pequenas":
 * quem ia buscar o troco lia "moedas", tinha de adivinhar quanto, e voltava com
 * o que achou. Um número pedido de verdade é o que faz a viagem valer.
 *
 * As denominações NÃO são exigidas: "me traz R$ 100" é um pedido completo, e
 * travar a fila por um refino que o gerente resolve com o que tem no cofre
 * seria trocar a fila por nada.
 */
export function canRequestChange(amount: string): boolean {
  return Boolean(amount.trim()) && parseAmountToQ(amount) > 0;
}

/** "120,50" / "120.50" / "120" → centavos. Ilegível vira 0, e o CTA não arma. */
export function parseAmountToQ(raw: string): number {
  return amountToQ(raw) ?? 0;
}

/**
 * "120,50" / "120.50" / "120" → centavos; `null` quando NÃO é um valor.
 *
 * O `null` existe porque "0" e "ilegível" são respostas diferentes: no
 * fechamento, zero é uma contagem (gaveta esvaziada) e ilegível é falta de
 * resposta. `parseAmountToQ` esmaga os dois em 0 — serve ao pedido de troco,
 * que só aceita valor positivo, e não serve à contagem.
 */
export function amountToQ(raw: string): number | null {
  const limpo = String(raw ?? "").trim().replace(/\s/g, "").replace(",", ".");
  if (!/^\d+(\.\d{1,2})?$/.test(limpo)) return null;
  return Math.round(Number(limpo) * 100);
}

/** Centavos → o texto que um campo de valor aceita de volta: 12050 → "120,50". */
export function formatAmountInput(q: number): string {
  return (Math.max(0, Math.round(q)) / 100).toFixed(2).replace(".", ",");
}

/**
 * Soma do contador de denominações: quantidade × cédula/moeda, em centavos.
 *
 * As chaves são o `q` da denominação; os valores, a quantidade digitada.
 * Quantidade ilegível ou vazia conta como zero — o contador é AJUDA para
 * quem conta nota por nota, nunca um segundo lugar onde a contagem trava.
 */
export function denominationCountTotalQ(counts: Record<number | string, string>): number {
  let total = 0;
  for (const [q, qty] of Object.entries(counts)) {
    const n = Number.parseInt(String(qty ?? "").trim(), 10);
    if (Number.isFinite(n) && n > 0) total += Number(q) * n;
  }
  return total;
}

/** Como a denominação se lê num resumo de uma linha: "R$ 20", "0,50". */
export function denominationLabel(
  cashManagement: POSCashManagementCapability | null | undefined,
  q: number,
): string {
  return changeDenominations(cashManagement).find((d) => d.q === q)?.label || String(q);
}

/**
 * A linha que o gerente lê antes de sair para buscar: quanto, e em quê.
 *
 * Sem denominação escolhida, o resumo é só o valor — e isso é um pedido
 * inteiro, não um pedido pela metade.
 */
export function changeRequestSummary(
  request: POSChangeRequestProjection,
  cashManagement?: POSCashManagementCapability | null,
): string {
  const valor = request.amount_display || "";
  const partes = (request.denominations || []).map((q) => denominationLabel(cashManagement, q));
  if (!partes.length) return valor;
  return valor ? `${valor} · em ${partes.join(", ")}` : `em ${partes.join(", ")}`;
}

/** Format the request timestamp for the pending list (pt-BR, hour and minute). */
export function formatRequestedAt(raw: string | null | undefined): string {
  if (!raw) return "";
  const date = new Date(raw);
  return Number.isNaN(date.getTime())
    ? raw
    : date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/** The lobby's single screen state — drives which card the antesala shows. */
export function sessionScreenState(
  runtime: POSCashRuntimeProjection,
  hasOpenShift: boolean,
): "open" | "closed" {
  // Havia um terceiro estado, `occupied`: a gaveta tinha turno de OUTRA pessoa e
  // quem chegava ficava preso sem vender. Ele morreu com a custódia da gaveta —
  // o turno do terminal é o turno de quem está nele, e o balcão se reveza sem
  // fechar nada. `runtime` fica na assinatura porque a antessala ainda deriva
  // dela o resto da tela.
  void runtime;
  return hasOpenShift ? "open" : "closed";
}

// ── Antesala do turno aberto: pendências e tiles ──────────────────────────
//
// Com o turno aberto a antesala respondia tudo de uma vez: dois formulários
// grandes abertos o turno inteiro, e as ações raras misturadas com as
// pendências que precisam de gente. O que vai aqui é a ORGANIZAÇÃO dessa
// tela: quantas coisas pedem uma pessoa agora, e quais ações viram tile. As
// funções são puras para a página só desenhar.

/**
 * Quantas coisas na antesala precisam de uma pessoa AGORA: devoluções em
 * dinheiro, pedidos de troco pendentes e contas na casa com saldo. É o número
 * do cabeçalho "Precisa de você" — e zero é o que decide se o bloco existe.
 */
export function attentionCount(input: {
  pendingCashRefunds: readonly unknown[];
  pendingChangeRequests: readonly unknown[];
  accountBalances: readonly unknown[];
}): number {
  return input.pendingCashRefunds.length
    + input.pendingChangeRequests.length
    + input.accountBalances.length;
}

export interface SessionActionTile {
  /** Identidade do tile (e do diálogo que ele abre). Movimento leva o tipo: `movement:sangria`. */
  key: string;
  action: "request_change" | "movement" | "open_drawer" | "close_shift";
  /** Só para `movement`: o tipo pré-escolhido ao abrir o diálogo. */
  kind?: string;
  icon: string;
  label: string;
  description: string;
  disabled: boolean;
  tone: "default" | "destructive";
}

// O tile de movimento fala pelo TIPO. O rótulo continua o de `movementLabel`
// (Entrada/Saída de caixa), pela mesma razão de sempre: quem confere dias
// depois não precisa saber o que é sangria. A descrição diz o gesto e, na
// saída, avisa do PIN antes de o gerente ser chamado.
const MOVEMENT_TILES: Record<string, { icon: string; description: string }> = {
  sangria: { icon: "lucide:banknote-arrow-down", description: "Tirar dinheiro da gaveta · PIN do gerente" },
  suprimento: { icon: "lucide:banknote-arrow-up", description: "Colocar dinheiro na gaveta" },
};

/**
 * Os tiles da seção "Gaveta", na ordem em que o balcão os usa: pedir troco,
 * os movimentos que a capability oferece, abrir a gaveta e fechar o caixa.
 *
 * ⚠️ Sem caminho de software a gaveta NÃO some: o tile fica desabilitado e a
 * descrição diz por quê. Sumir calado fez o dono procurar um botão que nunca
 * ia aparecer, achando que o PDV estava quebrado.
 */
export function sessionActionTiles(input: {
  movementKinds: readonly string[];
  canOpenDrawer: boolean;
  drawerUnavailableReason: string;
}): SessionActionTile[] {
  const tiles: SessionActionTile[] = [
    {
      key: "request_change",
      action: "request_change",
      icon: "lucide:coins",
      label: "Pedir troco",
      description: "O troco vem até o balcão",
      disabled: false,
      tone: "default",
    },
  ];
  for (const kind of input.movementKinds) {
    const tile = MOVEMENT_TILES[kind];
    tiles.push({
      key: `movement:${kind}`,
      action: "movement",
      kind,
      icon: tile?.icon || "lucide:banknote",
      label: movementLabel(kind),
      description: tile?.description || "",
      disabled: false,
      tone: "default",
    });
  }
  tiles.push(
    {
      key: "open_drawer",
      action: "open_drawer",
      icon: "lucide:archive",
      label: "Abrir gaveta",
      description: input.canOpenDrawer ? "Sem venda, com motivo registrado" : input.drawerUnavailableReason,
      disabled: !input.canOpenDrawer,
      tone: "default",
    },
    {
      key: "close_shift",
      action: "close_shift",
      icon: "lucide:lock",
      label: "Fechar caixa",
      description: "Contagem cega · encerra o turno",
      disabled: false,
      // Destrutivo no ÍCONE, não no tile inteiro: é a ação que encerra, e a
      // tela precisa dizer isso sem pintar um quadrado de vermelho na frente
      // do operador o turno todo.
      tone: "destructive",
    },
  );
  return tiles;
}

export interface SessionNavTile {
  key: "cash_report" | "day_closing";
  icon: string;
  label: string;
  description: string;
}

/**
 * Os tiles de "Fim do expediente" — só para quem pode. O relatório é de quem
 * AUDITA (`can_audit_cash`), o fechamento do dia de quem a API deixou entrar
 * (`dayClosing` nulo = 401/403 na sondagem). Lista vazia = seção não existe.
 */
export function endOfDayTiles(input: {
  canAuditCash: boolean;
  dayClosing: { already_closed: boolean; today_display: string; existing_closing_display: string } | null;
}): SessionNavTile[] {
  const tiles: SessionNavTile[] = [];
  if (input.canAuditCash) {
    tiles.push({
      key: "cash_report",
      icon: "lucide:receipt-text",
      label: "Relatório de caixa",
      description: "Leitura X do turno aberto, leituras Z dos turnos fechados e o histórico do dia.",
    });
  }
  if (input.dayClosing) {
    tiles.push({
      key: "day_closing",
      icon: "lucide:clipboard-check",
      label: input.dayClosing.already_closed ? "Ver fechamento" : "Fazer o fechamento",
      description: input.dayClosing.already_closed
        ? input.dayClosing.existing_closing_display
        : `${input.dayClosing.today_display} · contagem cega de sobras e perdas.`,
    });
  }
  return tiles;
}
