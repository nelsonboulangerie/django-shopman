/**
 * O contexto que o PDV manda junto do chamado.
 * Refs, nunca PII: o servidor já sabe quem abriu.
 */
export interface PosSupportContextInput {
  route: string;
  station?: string;
  terminal?: string;
}

export function posSupportContext(input: PosSupportContextInput): Record<string, unknown> {
  const context: Record<string, unknown> = { app: "pos", route: input.route };
  if (input.station) context.workstation_ref = input.station;
  if (input.terminal) context.terminal_ref = input.terminal;
  return context;
}
