import type { POSTerminalComponentProjection } from "~/types/pos";

/**
 * Saúde do terminal com a resposta que só ESTA página alcança.
 *
 * O servidor projeta o que ele sabe (config declarada), mas o agente do balcão
 * vive na loopback da estação — de lá, o Django não enxerga nada. A sonda do
 * `/health` acontece aqui no navegador, e este módulo promove o resultado às
 * linhas do card: a Impressora e a Gaveta que o servidor marcou como "ready"/
 * "na estação" viram verdes ou vermelhas de verdade, e uma linha "Agente do
 * balcão" diz o estado do cano por onde tudo passa.
 *
 * Puro de propósito: recebe dados, devolve linhas. A sonda (fetch + intervalo)
 * mora em `useAgentHealth`; a cor e o popover moram no componente.
 */

/** O que a sonda respondeu. `ok: null` = agente configurado, sonda ainda no ar. */
export interface AgentProbe {
  ok: boolean | null;
  message: string;
}

export interface TerminalHealthRow {
  key: string;
  label: string;
  status: string;
  message: string;
}

/** O estado honesto quando o agente caiu: diz O QUE acontece com os recibos. */
export const AGENT_OFFLINE_MESSAGE = "Agente offline. Recibos sairão pelo diálogo do navegador.";

/**
 * Linhas do card, com a sonda promovida por cima da projeção do servidor.
 *
 * `probe === null` = terminal sem agente configurado (gaveta de chave, impressão
 * pelo navegador): as linhas do servidor passam intactas e não existe linha de
 * agente — ausência não é defeito.
 */
export function terminalHealthRows(
  components: POSTerminalComponentProjection[],
  fiscal: { status: string; label: string; message: string },
  probe: AgentProbe | null,
): TerminalHealthRow[] {
  const rows: TerminalHealthRow[] = [];

  if (probe !== null) {
    rows.push({
      key: "agent",
      label: "Agente do balcão",
      status: probe.ok === null ? "deferred" : probe.ok ? "ready" : "error",
      message: probe.ok === null ? "sondando a estação" : probe.ok ? probe.message : AGENT_OFFLINE_MESSAGE,
    });
  }

  for (const component of components) {
    rows.push(promoteProbe(component, probe));
  }

  rows.push({
    key: "fiscal",
    label: "Fiscal",
    status: fiscal.status,
    message: fiscal.message || fiscal.label,
  });

  return rows;
}

/**
 * A sonda só sobrescreve o que ela realmente mede: o caminho até a impressora
 * (e a gaveta pendurada nela) passa pelo agente. Um `warning` de configuração
 * do servidor fica de pé — agente saudável não conserta rolo mal declarado.
 * A impressora `absent` também é promovida quando HÁ agente: um terminal com
 * agente tem caminho de impressão por definição, declarado ou não em metadata.
 */
function promoteProbe(
  component: POSTerminalComponentProjection,
  probe: AgentProbe | null,
): TerminalHealthRow {
  const row = {
    key: component.key,
    label: component.label,
    status: component.status,
    message: component.message,
  };
  if (probe === null || probe.ok === null) return row;
  const promotable
    = (component.key === "printer" && ["ready", "absent", "deferred"].includes(component.status))
      || (component.key === "cash_drawer" && component.status === "deferred");
  if (!promotable) return row;
  if (probe.ok) {
    return { ...row, status: "ready", message: probe.message || "agente respondendo" };
  }
  return { ...row, status: "error", message: "sem caminho até a estação (agente offline)" };
}

/**
 * O badge geral segue as linhas JÁ promovidas — mesmo critério do servidor
 * (`TerminalRuntimeProfile.status`): erro > atenção > pronto; `absent` e
 * `deferred` não acendem nada. A linha fiscal fica de fora, como sempre ficou:
 * ela tem badge próprio no checkout.
 */
export function terminalOverallStatus(rows: TerminalHealthRow[]): "ready" | "warning" | "error" {
  const relevant = rows.filter((row) => row.key !== "fiscal");
  if (relevant.some((row) => row.status === "error")) return "error";
  if (relevant.some((row) => row.status === "warning")) return "warning";
  return "ready";
}
