/**
 * Diretório GERADO, que nenhum guardrail lê: dependências e build.
 *
 * Por prefixo, não por nome exato: o e2e do PDV gera `.nuxt-e2e-<porta>` e
 * `.output-e2e-<porta>` (porta no nome para execuções concorrentes), e os guardrails
 * que só pulavam `.nuxt`/`.output` exatos liam o bundle compilado: falso vermelho em
 * quem rodou o e2e na própria máquina (#3640, achado pelo `make preflight`).
 * Um lugar só, para a próxima pasta gerada não precisar ser lembrada em 16 testes.
 */
export function isGeneratedDir(entry: string): boolean {
  return entry === "node_modules" || /^\.(nuxt|output)(-|$)/.test(entry);
}
