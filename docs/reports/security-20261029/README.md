# Segurança das superfícies: 29/10/2026

A afirmação histórica de zero alertas da issue #574 não descreve o estado atual. A consulta paginada preservada em `dependabot-before.json` encontrou 96 ocorrências em 12 locks. São ocorrências por manifesto/advisory, não 96 falhas independentes.

| Pacote | Ocorrências antes | Versão anterior | Versão resolvida | Alcance encontrado |
|---|---:|---|---|---|
| seroval | 24 | 1.6.9 | 1.7.5 | Serialização usada por `@nuxt/vite-builder` |
| @vitest/mocker | 24 | 4.1.11 | 4.1.12 | Ferramenta de testes/dev server |
| fast-uri | 12 | 3.1.8 | 3.1.9 | Transitivo do validador Ajv |
| serialize-javascript | 12 | 7.1.0 | 7.1.4 | Serialização do plugin Terser no build |
| node-forge | 12 | 1.4.0 | 1.4.2 | TLS/certificados em listhen, via CLI Nuxt |
| deepmerge | 12 | 4.3.1 | 4.3.1 | Plugin de resolução Rollup no build |

Vitest e seus componentes ficam em 4.1.12 em todos os apps; não há migração para Vitest 5. Seroval 1.7.5 e serialize-javascript 7.1.4 são versões estáveis dentro das faixas transitivas já permitidas. Chai e tinyrainbow também foram resolvidos dentro das faixas da família Vitest. O check de versões confirma faixas e locks uniformes.

## node-forge: a informação de ausência de patch envelheceu

O advisory antigo ainda retorna `first_patched_version=null`, mas o [CHANGELOG oficial da versão 1.4.2](https://github.com/digitalbazaar/forge/blob/v1.4.2/CHANGELOG.md) confirma a correção da CVE-2026-85393 em 1.4.1 e a compatibilidade de entrada Buffer restaurada em 1.4.2. Ambas foram publicadas em 27/10. O patch elimina a necessidade da exceção GHSA-86w9-cpqp-85rv, removida da allowlist.

## Risco residual explícito: deepmerge

O [advisory GHSA-gcqx-w48m-w2h4](https://github.com/advisories/GHSA-gcqx-w48m-w2h4) continua sem versão corrigida; o registro npm ainda publica 4.3.1 como estável mais recente em 29/10. A falha é envenenamento do protótipo do objeto retornado quando a entrada é controlada pelo atacante.

No código instalado de `@rollup/plugin-node-resolve/dist/es/index.js`, há uma única chamada de `deepMerge`: `deepFreeze(deepMerge({}, defaults))`, usando constantes do próprio plugin. Não há entrada de pedido HTTP nessa chamada. Não encontramos importação direta desses pacotes nos diretórios `app` ou `server` das superfícies. Isso limita o alcance comprovado desta cadeia; não demonstra ausência universal de exploração em qualquer consumidor.

As imagens em `surfaces/Dockerfile.surface` e `surfaces/Dockerfile.operator-group` copiam somente o resultado `.output` para o runtime e iniciam o servidor Nitro diretamente. A classificação `runtime` de Dependabot reflete dependências Nuxt declaradas em produção; por si só não prova que o pacote entre no artefato final. A inspeção do build da loja está registrada na validação abaixo.

O gate high+ continua ativo; não adicionamos dispensa para deepmerge nem escondemos o alerta low. Reavaliar até **15/11/2026**, ou antes se sair patch do deepmerge/plugin Rollup. O próximo passo é atualizar o transitivo quando houver fix estável compatível.

## Validação

- `python3 scripts/check_surface_versions.py`: passou, 38 pacotes compartilhados, faixas e locks alinhados.
- `npm ci` com Node 22.23.1/npm 10.9.8: passou no operator-kit e na loja.
- Locks resolvidos com npm 11.17.0/Node 22: npm 10 falhou internamente em Arborist (`edgesOut`) ao tentar resolver peers opcionais Vitest; a instalação reproduzível por npm 10 foi conferida depois.
- `audit-after-summary.json`: auditoria dos 12 apps sem moderate/high/critical. Único advisory folha residual é deepmerge low; o total npm inclui seus dependentes e não deve ser confundido com falhas independentes.
- Gate high+ do kit passou sem precisar de exceção.
- Suíte operator-kit: 176 arquivos e 1.897 testes passaram, saída final do Vitest com exit code 0.
- Build da loja passou (41,9 s, exit code 0). Busca textual por `deepmerge`, `node-forge`, `seroval`, `serialize-javascript` e `fast-uri` em `.output/server` não encontrou referências; a checagem é limitada ao artefato local da loja, não a todas as imagens.

A fila da PR executa os demais gates de cada app. Nenhuma aprovação de major congelada foi inferida desta atualização de patches.
