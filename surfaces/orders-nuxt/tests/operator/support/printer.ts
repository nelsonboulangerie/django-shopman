import { createHash } from "node:crypto";
import { expect, request } from "@playwright/test";
import { stack } from "./stack";

// A impressora simulada do balcão (#3124): faz o que o agente de impressão faz, e nada
// além. Com a credencial do relay (a mesma que o pareamento real emite, pelo comando
// `issue_print_agent_credential`; passo declarado do README), ela busca o próximo
// trabalho no servidor, confere que os bytes são os que o servidor assinou e responde
// "spooled", como o agente faz depois de entregar o papel ao spooler. Ela não cria
// trabalho nem muda estado de pedido: quem imprime é o gesto da pessoa no Gestor.

export const printerBearer = (process.env.OPERATOR_PRINT_AGENT_BEARER || "").trim();

export type PrintedPaper = { jobRef: string; kind: string; text: string };

/** Busca o próximo trabalho do relay, confere o hash, confirma e devolve o papel. */
export async function printerTakesTheNextJob(timeout = 60_000): Promise<PrintedPaper> {
  const api = await request.newContext({
    baseURL: stack.django,
    extraHTTPHeaders: { Authorization: `Bearer ${printerBearer}` },
  });
  try {
    let job: Record<string, unknown> | null = null;
    await expect(async () => {
      const response = await api.post("/api/v1/backstage/print-agent/jobs/claim/", { data: { agent_id: "impressora-simulada" } });
      expect(response.status(), "a impressora não achou trabalho na fila").toBe(200);
      job = (await response.json()).job;
    }).toPass({ timeout, intervals: [1_000] });
    const claimed = job as unknown as {
      job_ref: string;
      kind: string;
      payload_b64: string;
      payload_sha256: string;
      lease_token: string;
    };
    const payload = Buffer.from(claimed.payload_b64, "base64");
    const sha256 = createHash("sha256").update(payload).digest("hex");
    expect(sha256, "os bytes do trabalho não são os que o servidor assinou").toBe(claimed.payload_sha256);
    const ack = await api.post(`/api/v1/backstage/print-agent/jobs/${claimed.job_ref}/ack/`, {
      data: {
        status: "spooled",
        // O agente real manda o número do trabalho no spooler do sistema.
        spooler_job_id: `simulada-${claimed.job_ref}`,
        payload_sha256: sha256,
        lease_token: claimed.lease_token,
        agent_id: "impressora-simulada",
      },
    });
    expect(ack.status(), await ack.text()).toBe(200);
    // ESC/POS: o texto vai em página de código de um byte; latin1 lê as letras ASCII.
    return { jobRef: claimed.job_ref, kind: claimed.kind, text: payload.toString("latin1") };
  } finally {
    await api.dispose();
  }
}
