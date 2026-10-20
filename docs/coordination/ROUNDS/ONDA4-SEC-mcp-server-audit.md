# ONDA4-SEC: auditoria de dependências

Estado: PR draft, aguardando decisão sobre production-nuxt, excluído pela ordem.

A falha Supply chain marketing de #1957 foi lida no job 118893254167. O caminho é @eslint/config-inspector → @devframes/agentic → @modelcontextprotocol/server. Sete locks permitidos travavam server/core 2.0.0. Atualizados para a estável 2.3.1, já compatível com a faixa ^2.0.0. Status já estava corrigido. Nenhuma allowlist alterada.

Advisories oficiais GHSA-jm63-cq47-j5jp, GHSA-46jr-4wx8-v453 e GHSA-rvq5-wwqv-78pq exigem server >=2.3.0. Consulta GitHub API e registro npm realizada em 20/10/2026.

A auditoria também revelou vite 8.2.2 vulnerável no Hub. Atualizado para 8.3.4, versão já presente nos outros apps. launch-editor do Compras passa de 2.14.1 para 2.14.2. GHSA-r825-w8mm-5pxw exige launch-editor >=2.14.2 ou vite corrigido (8.3.3+).

Validação: gate npm audit passou nos nove consumidores MCP após correção do Hub; os logs /tmp/mcp-audit-*.log registram a rodada inicial, com Hub vermelho por vite, e o gate do Hub foi repetido com sucesso. Exceções temporárias preexistentes permanecem. check_surface_versions.py passou: 38 pacotes, 13 apps. Sem mudança de UI, portanto capturas D1-D12 não se aplicam.

Decisão pendente: production-nuxt trava server/core 2.0.0 e está explicitamente fora da ordem. Seu lock não foi alterado nesta PR. Autorizar a mesma atualização transitiva nesse lock? A proteção de versões compartilhadas não enumera MCP e não acusa esta diferença.
