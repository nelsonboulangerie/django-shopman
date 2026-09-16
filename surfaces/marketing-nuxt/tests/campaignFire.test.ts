import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { fireAvailability } from "~/presentation/campaignFire";
import type { MarketingActionProjectionV2 } from "~/types/campaign";

function action(
  over: Partial<MarketingActionProjectionV2> = {},
): MarketingActionProjectionV2 {
  return {
    kind: "fire_campaign",
    resource_ref: "campaign:5",
    enabled: true,
    reason: "",
    ...over,
  } as MarketingActionProjectionV2;
}

describe("disparo manual — liberado ou com o porquê", () => {
  it("libera quando o servidor libera", () => {
    expect(fireAvailability({ pk: 5, is_active: true }, [action()])).toEqual({
      enabled: true,
      reason: "",
    });
  });

  it("pede para ligar a campanha antes de tudo", () => {
    expect(
      fireAvailability({ pk: 5, is_active: false }, [
        action({ enabled: false, reason: "campaign_inactive" }),
      ]).reason,
    ).toBe("Ligue a campanha antes de preparar um disparo.");
    // Campanha desligada sem ação nenhuma na lista: a frase é a mesma.
    expect(fireAvailability({ pk: 5, is_active: false }, []).reason).toBe(
      "Ligue a campanha antes de preparar um disparo.",
    );
  });

  it("explica a ausência do comando e a falta de permissão em frases distintas", () => {
    expect(fireAvailability({ pk: 5, is_active: true }, []).reason).toContain(
      "atualização de segurança",
    );
    expect(
      fireAvailability({ pk: 5, is_active: true }, [
        action({ enabled: false, reason: "missing_capability" }),
      ]).reason,
    ).toBe("Seu perfil não autoriza disparos manuais.");
  });

  it("nunca devolve botão morto sem frase", () => {
    const result = fireAvailability({ pk: 5, is_active: true }, [
      action({ enabled: false, reason: "algo_novo_do_servidor" }),
    ]);
    expect(result.enabled).toBe(false);
    expect(result.reason.length).toBeGreaterThan(0);
  });
});

describe("a lista de campanhas mostra o porquê por extenso", () => {
  // ⚠️ A razão morava só no `title` do botão desabilitado. O Firefox não mostra
  // tooltip em botão desabilitado; "Indisponível" ficava sem frase.
  it("põe a frase num parágrafo sob a linha, não num title", () => {
    const page = readFileSync(
      new URL("../app/pages/campaigns.vue", import.meta.url),
      "utf8",
    );

    expect(page).toContain('v-if="!fireState(rule).enabled"');
    expect(page).toContain("{{ fireState(rule).reason }}");
    expect(page).not.toMatch(/:title="[^"]*fireState\(rule\)\.reason/);
  });
});
