# Evidência de QA visual do Admin — contrato v3

Execução local em 12 de setembro de 2026 na branch
`codex/concierge-transport-bindings-20260912`. O código e o harness validados
formam o SHA `4a11724125509ad37d7d849aa8bcbb5e55ad535a`; a seed visual foi executada
durante sua preparação sobre a mesma árvore de trabalho.

## Escopo e isolamento

O harness usa somente dados sintéticos e exige explicitamente um PostgreSQL
isolado em `CONCIERGE_BROWSER_DATABASE_URL`. Nesta execução, o cluster local
ficou em `/tmp/shopman-concierge-browser-v3-pg`, porta `56541`, banco
`concierge_browser_v3`, e foi encerrado ao final. Redis, credenciais externas e
chamadas de rede a provedores não foram usados.

A seed v3 criou uma conversa lógica em atendimento humano e dois vínculos
ativos:

- `manychat / whatsapp`, sujeito `synthetic-browser-wa`, garantia
  `configured_transport`;
- `tiktok / direct_message`, sujeito `synthetic-browser-tiktok`, garantia
  `transport_subject`.

Ela também criou uma entrada com garantia `at_least_once` e duas respostas,
cada uma com seu `OutboundAttempt`: uma em estado `unknown` e outra em
`accepted`. Os adapters sintéticos não implementam handoff nem acessam rede.

## Execução

O servidor foi executado separadamente com o gate de retorno desativado e
ativado. Em cada modo, `browser_admin.py` autenticou um superusuário e um
usuário com apenas `shop.view_conversation`, primeiro em viewport 1440 × 1000
e depois em 390 × 844.

| Modo | Usuário | Ação “Devolver ao concierge” | Edição | Bindings e estados | Console |
| --- | --- | --- | --- | --- | --- |
| contido | `synthetic-admin` | ausente | indisponível | legíveis em 1440 e 390 | sem erros |
| contido | `synthetic-viewer` | ausente | indisponível | legíveis em 1440 e 390 | sem erros |
| retorno habilitado | `synthetic-admin` | presente | indisponível | legíveis em 1440 e 390 | sem erros |
| retorno habilitado | `synthetic-viewer` | ausente | indisponível | legíveis em 1440 e 390 | sem erros |

O modo de retorno habilitado também acionou a action com o adapter opaco. Como
o adapter não suporta handoff, o Admin manteve a conversa com a equipe e
mostrou “Não aplicada; atendimento humano preservado”. Nenhum retorno a um
provedor real foi tentado.

As asserções verificaram a ausência de controles de gravação, o inline de
bindings somente leitura, os dois canais, as garantias de identidade, os
estados de saída `unknown` e `accepted`, a disponibilidade da action conforme
gate e permissão, e ausência de corte nos textos operacionais principais. A
inspeção das capturas confirmou a composição do Admin em desktop e mobile.

Resultados estruturados:

- [`browser-v3-contained.json`](../browser-v3-contained.json)
- [`browser-v3-return-enabled.json`](../browser-v3-return-enabled.json)
- [`browser-v3-seed.txt`](../browser-v3-seed.txt)
- [`SHA256SUMS`](SHA256SUMS), com os hashes dos resultados e das capturas

Capturas:

- `contained-synthetic-admin-desktop-1440.png`
- `contained-synthetic-admin-mobile-390.png`
- `contained-synthetic-viewer-desktop-1440.png`
- `contained-synthetic-viewer-mobile-390.png`
- `return-enabled-synthetic-admin-desktop-1440.png`
- `return-enabled-synthetic-admin-mobile-390.png`
- `return-enabled-synthetic-viewer-desktop-1440.png`
- `return-enabled-synthetic-viewer-mobile-390.png`

## Achado e correção

A primeira inspeção mostrou que o inline tabular cortava as colunas finais dos
bindings em 1440 px. O inline foi convertido para o componente empilhado do
Unfold e a execução foi repetida nas duas larguras e nos dois perfis. Também
foi explicitado o resultado `not_applied` durante handoff como “Não aplicada;
atendimento humano preservado”. Os JSONs e PNGs deste diretório são da
execução posterior a essas correções.

## Verificações automatizadas

- testes focados de Admin: `14 passed`;
- `make admin`: verificador canônico do Unfold aprovado e `268 passed`;
- Ruff check e format nos dois scripts, no Admin e na regressão: aprovados;
- `git diff --check`: aprovado.

Esta evidência conclui a implementação e a QA local isolada desta superfície.
Ela não comprova homologação com ManyChat ou TikTok, piloto, envio real,
ativação de canal nem rollout. Nenhuma dessas etapas foi executada.
