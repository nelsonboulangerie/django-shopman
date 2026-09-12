# Reutilização do portão ManyChat existente — 11/09/2026

Pedido: adaptar o candidato ao teste que já existe, preservando o portão original. Base desta adaptação: `dd5a23b0e6d8751d39a3d615a5d77e4a01acc674`; código WP00–WP10 validado em `97aaad216`.

## Fatos conferidos

- Histórico: commit `d777be1cc` introduziu o gatilho `#c` em 04/09. O webhook candidato já preserva esse prefixo e a rota `/api/webhooks/manychat/conversation/`.
- Consulta somente leitura ao app `shopman-nelson` mostrou o switch legado ligado, dois subjects e dois telefones legados na lista, credenciais configuradas e o mesmo `process_directives --watch`. Conta/versão v2 ainda não constavam como envs.
- GET autenticado `https://api.manychat.com/fb/page/getInfo` confirmou a conta `764222643620409`, Nelson Boulangerie.
- GET `.../page/getFlows` confirmou **Concierge (piloto)**, `ns=content20260904134021_491685`. O catálogo retorna `ns`, `name` e `folder_id`; não retorna o Body publicado dos nós.
- GET `.../page/getCustomFields` confirmou `concierge_handoff` do tipo texto. Não apareceu campo personalizado de evento/mensagem; isso não prova ausência de campo sistêmico.
- A inspeção usou credencial já presente no processo, somente como autenticação à própria API ManyChat. Nenhum token foi impresso ou copiado para testes. Nenhum envio, custom-field write, publicação, migração ou deploy foi feito. O console remoto foi encerrado.

Metadados não sensíveis e limites estão em `inspection.json`. As consultas seguem a [API oficial ManyChat](https://api.manychat.com/swagger?urls.primaryName=Profile+API). O controle do Chrome não tinha permissão nesta sessão; o navegador integrado chegou à tela de login sem sessão autenticada. Portanto, os nós do editor não foram inspecionados.

## Adaptação entregue no worktree

1. O guia canônico `docs/guides/whatsapp-concierge.md` passa a documentar o flow real, `#c`, mesma URL e `X-Api-Key` com o fallback de chave já existente. Corrige orientações antigas de ACK 202, lista vazia aberta, dedupe por minuto e leitura da última mensagem via getInfo.
2. A fixture única `evidence/conversational/flows/manychat-conversation-v2.json` usa o mesmo header e corpo mínimo, com `#c` e `event_id`. Continua sendo fixture local, não export nativo nem publicação.
3. O spec alpha declara a conta conferida e `CONCIERGE_CONTRACT_VERSION=0`. Esse valor contém o candidato enquanto a origem do ID do evento não estiver comprovada. Todas as envs preexistentes, convidados, segredos, hosts, rotas e componentes foram preservados exatamente (`spec-check.json`).
4. Quatro regressões exercitam o endpoint real com credenciais sintéticas: ingresso pelo `#c` e chave compartilhada, replay, texto igual em duas mensagens distintas e mensagem sem ID sem efeito. Não foi criado webhook, fila ou sender alternativo.

## Validação local

`tests.txt`: **49 passed, 31,16s**, zero skips/warnings, PostgreSQL 16.14 e Redis 7.2.5 privados nas portas 56429/56430. Inclui os quatro testes novos, contratos de ingresso/webhook e a vertical com compra/recuperação canônicas. Modelo e fornecedor são fakes.

```bash
DATABASE_URL=postgres://concierge_test@127.0.0.1:56429/concierge_gate \
REDIS_URL=redis://127.0.0.1:56430/12 \
PYTHONDONTWRITEBYTECODE=1 \
/Users/pablovalentini/Dev/Claude/django-shopman/.venv/bin/python \
evidence/conversational/run.py \
shopman/storefront/tests/test_concierge_existing_gateway.py \
shopman/storefront/tests/test_concierge_ingress_contract.py \
shopman/storefront/tests/test_concierge_webhook.py \
shopman/storefront/tests/test_concierge_runtime_vertical.py --reuse-db -rs
```

O cluster original 56419 não estava ativo; a tentativa inicial do agente falhou no setup antes de executar testes. Houve também 4 passed em SQLite (14,34s), não usados como prova de concorrência. O novo cluster inicialmente encontrou limite de tamanho do caminho de socket no macOS; um diretório curto exclusivo resolveu o startup. O gate PostgreSQL final acima executou integralmente.

## O que falta para conectar a versão nova

O operador confirmou o Body real: `subscriber_id`, `text`, `first_name`, `last_name`, sem event ID, e o URL `https://api.boulangerie.com.br/api/webhooks/manychat/conversation/`. IDs pessoais e código de acesso do exemplo não foram copiados para fixtures. O seletor/origem de uma identidade estável continua sem prova; não inventar um campo `Message ID`.

C01 permite leitura/handoff sem identidade de evento. A compatibilidade local acrescenta opt-in `CONCIERGE_LEGACY_READ_HANDOFF_ENABLED`, desligado por padrão, usando as mesmas tabelas e Directive. `legacy_read_only` é o ACK200; sem flag, permanece `event_id_required`. O turno legado é determinístico: catálogo público pelo reader/renderer canônico ou orientação/handoff. Não chama modelo/getInfo nem mutantes, revisão, AccessLink, consentimento ou consulta de pedido com reconciliação. Batch misto é conservadoramente somente leitura. Confirmação legada jamais vira prova posterior.

Antes: quatro campos → candidato recusa falta de ID. Depois, somente com opt-in autorizado: quatro campos → recibo local explicitamente não verificado → consulta pública ou atendimento, com contexto e próxima ação. Compra automatizada continua dependente de identidade estável. PK local não é event ID; retries podem repetir leituras/respostas. Recibos legados não atualizam last_inbound_at. Sem janela previamente comprovada, a saída é contida como not_applied/window_closed. A fixture que exercita envio sem rede fornece uma janela sintética previamente verificada; isso não é instrução de setar timestamp no ambiente real. Fornecedor/janela/roteamento humano seguem pendentes de homologação. Nenhum teste local comprova ganho humano ou entrega real.

Sem nova migração: a constraint existente permite external_id vazio; não há backfill/replay de legado. Rollback funcional: desligar o opt-in, que contém admissão, execução, saída preparada e retry explícito. Entradas legadas não consumidas ficam preservadas e excluídas do agendamento enquanto a flag está desligada, sem loop nem bloquear novos eventos v2. Preservar Message/Directive/receipts; não apagar transcrição nem reprocessá-la com autoridade v2. Rollback de código ao candidato anterior mantém o gate geral em 0 até avaliação; não rodar worker anterior com opt-in ativo.

`spec-drift.txt` registra por que o spec inteiro não pode ser aplicado agora: sete envs novas da frente Marketing existem no app vivo e não nesta base do arquivo. Substituir o spec as removeria. Nenhuma delas foi apagada ou alterada; a adaptação Concierge permanece local. O release precisa reconciliar esse drift com o trabalho da outra frente, além de ter seu alvo autorizado. Não alterar o script de drift para esconder essas diferenças.

**Estado:** compatibilidade local testada e configuração preparada; flow existente identificado; Body e URL confirmados; identidade estável, homologação e ativação pendentes. Não declarar que o candidato novo já atende pelo WhatsApp. O teste antigo permanece como estava.

## Verificação da compatibilidade legada

Código: `2583e3744c7b2f4f4330db1a5f5a6b9a11f84c08`, branch exclusiva `codex/conversational-excellence-implementation-20260911`; base desta fatia `ae4dec40b`. Quinze casos novos (`test_concierge_legacy_gateway.py`) abrangem endpoint de quatro campos, catálogo real, #menu sem AccessLink, compra contida, handoff, revogação em intake/claim/output/recovery, batch misto, chamada interna após reload, confirmação posterior, timeout desconhecido e janela não renovada por retry.

- `legacy-tests.txt`: primeiro checkpoint 58 passed/3,65s.
- `legacy-integration.txt`: seleção de `legacy-selection.json`, **419 passed/39,94s**, zero skips/warnings. PostgreSQL privado 56429, Redis 56430; modelo e fornecedor fakes, sem credenciais externas. Rodou antes do ajuste final que evita contar leitura normal como falha consecutiva.
- `legacy-final-targeted.txt`: **96 passed/5,31s**, zero skips/warnings, após esse ajuste (novo teste confirma contador zero), com engine, ingresso, capacidades e todos os casos legados. Esse é o código do SHA acima.
- `legacy-ruff.txt` e `git diff --check`: aprovados. Não houve alteração de schema; não é necessário novo migration/rollback de banco nesta fatia.

Na retomada local, a primeira tentativa de iniciar este cluster sem repetir `-p/-k` tentou a porta padrão ocupada e falhou antes dos testes; nenhum processo existente foi interrompido. Reinício correto com portas/socket exclusivos passou. Os serviços privados foram encerrados ao final (`legacy-shutdown.txt`). Testes de fornecedor, janela real, publicação e medição humana não executados; não são substituídos pelos fakes.
