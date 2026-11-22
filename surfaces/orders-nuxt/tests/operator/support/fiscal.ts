import { existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { controlDir } from "./clock";

// A nota simulada da pilha (#2585, shopman/shop/adapters/fiscal_simulated.py): toda
// emissão autoriza, a não ser que `fiscal.json` da pasta de controle peça a recusa das
// próximas. É o que a SEFAZ faria numa recusa de verdade: o motivo vai para o Gestor, e o
// "Reprocessar NFC-e" emite de novo.

/** A SEFAZ recusa as próximas `times` emissões com este motivo. */
export function sefazRejectsNext(message: string, times = 1): void {
  if (!controlDir) throw new Error("OPERATOR_CONTROL_DIR não declarada: a pilha não tem a nota simulada.");
  writeFileSync(join(controlDir, "fiscal.json"), JSON.stringify({ deny_next: times, error_message: message }), "utf8");
}

/** Volta a autorizar tudo. Chamar no fim de toda jornada que roteirizou recusa. */
export function sefazAuthorizesAll(): void {
  if (controlDir) rmSync(join(controlDir, "fiscal.json"), { force: true });
}

/** O que a SEFAZ simulada guardou da nota do pedido (ou `null`, sem nota): o documento
 *  do destinatário e se foi entrega. É o que a nota declarou, e a tela não mostra. */
export function simulatedNote(ref: string): { status: string; customer_tax_id: string; delivery: boolean } | null {
  const path = join(controlDir, "fiscal-notes", `${ref.replace(/[^A-Za-z0-9_-]/g, "_")}.json`);
  return existsSync(path) ? JSON.parse(readFileSync(path, "utf8")) : null;
}
