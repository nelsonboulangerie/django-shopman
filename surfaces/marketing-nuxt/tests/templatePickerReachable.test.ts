import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// ⚠️ Este arquivo nasceu de um defeito de projeto: o seletor do template aprovado do
// WhatsApp vivia SÓ dentro do aviso de alcance do painel — e o aviso só aparece quando
// alguma campanha ativa usa WhatsApp E falta template. A config ficava invisível quando não
// havia campanha ativa, e invisível DE NOVO depois de configurada.
//
// A correção final não foi dar um botão ao painel: foi dar **casa** à configuração. Ela mora
// em `/platforms`, e o painel volta a ser só decisão.
function read(path: string): string {
  return readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
}

describe("a configuração de plataforma tem casa", () => {
  it("o seletor de template vive na tela de Plataformas", () => {
    const page = read("../app/pages/platforms.vue");
    expect(page).toContain("onChooseTemplate");
    expect(page).toContain("Teste seguro do WhatsApp");
    expect(page).not.toContain("test-recipient");
    expect(page).toContain("testTargets");
    expect(page).toContain("Verificado em");
    expect(page).toContain("UiVerificationCodeInput");
    expect(page).toContain("waTemplate.commandAvailable");
    expect(page).not.toContain("{{ option.ns }}");
  });

  it("o painel NÃO configura plataforma — só decide", () => {
    const board = read("../app/pages/index.vue");
    expect(board).not.toContain("onChooseTemplate");
    expect(board).not.toContain("Teste seguro do WhatsApp");
    expect(board).not.toContain("useWhatsAppTemplate");
  });

  it("o aviso do painel aponta a casa em vez de configurar", () => {
    expect(read("../app/pages/index.vue")).toContain("/platforms");
  });

  it("o teste preserva idempotência no BFF e não serializa destinatário livre", () => {
    const composable = read("../app/composables/useWhatsAppTemplate.ts");
    expect(composable).toContain('"Idempotency-Key"');
    expect(composable).toContain("target_ref: targetRef");
    expect(composable).not.toContain("body: { recipient");
  });

  it("a aprovação envia versão, consequência explícita e reaproveita a mesma key", () => {
    const composable = read("../app/composables/useCampaignBoard.ts");
    const command = read("../app/composables/useMarketingDecisionCommand.ts");
    const detail = read("../app/pages/announcements/[id].vue");
    expect(composable).toContain("base_version");
    expect(composable).toContain("publish_mode");
    expect(command).toContain('"Idempotency-Key"');
    expect(command).toContain("confirmation_token");
    expect(detail).toContain("buildApprovalCommand");
    expect(detail).toContain("useMarketingDecisionCommand");
    expect(detail).toContain("approvalKeys");
  });

  it("edições de campanha e modelo carregam a versão lida e atualizam antes do rebase", () => {
    const campaigns = read("../app/composables/useCampaigns.ts");
    const templates = read("../app/composables/useAnnouncementTemplates.ts");
    for (const source of [campaigns, templates]) {
      expect(source).toContain("base_updated_at");
      expect(source).toContain("httpError(err).status === 409");
      expect(source).toContain("await refresh()");
    }
  });
});
