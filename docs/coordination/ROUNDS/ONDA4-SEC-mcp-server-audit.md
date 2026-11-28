# ONDA4-SEC: auditoria de dependências

Estado final: MERGED no #1967 em 2026-10-20 22:59:36 UTC.
Commit de merge: `486423dc2abcf6539ab0e6e5c6222f0b45cc7fbb`.
O dono autorizou a atualização de segurança no lock de production-nuxt.

A falha Supply chain marketing de #1957 foi lida no job 118893254167. O caminho é @eslint/config-inspector → @devframes/agentic → @modelcontextprotocol/server. Sete locks permitidos travavam server/core 2.0.0. Atualizados para a estável 2.3.1, já compatível com a faixa ^2.0.0. Status já estava corrigido. Nenhuma allowlist alterada.

Advisories oficiais GHSA-jm63-cq47-j5jp, GHSA-46jr-4wx8-v453 e GHSA-rvq5-wwqv-78pq exigem server >=2.3.0. Consulta GitHub API e registro npm realizada em 20/10/2026.

A auditoria também revelou vite 8.2.2 vulnerável no Hub. Atualizado para 8.3.4, versão já presente nos outros apps. launch-editor do Compras passa de 2.14.1 para 2.14.2. GHSA-r825-w8mm-5pxw exige launch-editor >=2.14.2 ou vite corrigido (8.3.3+).

Validação: gate npm audit passou nos oito consumidores MCP permitidos após correção do Hub, e no Compras; os logs /tmp/mcp-audit-*.log registram a rodada inicial, com Hub vermelho por vite, e o gate do Hub foi repetido com sucesso. Exceções temporárias preexistentes permanecem. check_surface_versions.py passou: 38 pacotes, 13 apps. npm ci --dry-run com Node 22/npm 10 passou nos oito locks alterados. O npm 11 removeu uma entrada cac de peer opcional do Hub; a entrada foi preservada e o npm ci validado. Sem mudança de UI, portanto capturas D1-D12 não se aplicam.

Production-nuxt atualizado para server/core 2.3.1 após autorização explícita do dono. A atualização de segurança permanece; a autorização excepcional vale apenas para o escopo desta tarefa. Nenhum manifest, configuração ou allowlist foi alterado temporariamente. Não há nada para reverter depois.
