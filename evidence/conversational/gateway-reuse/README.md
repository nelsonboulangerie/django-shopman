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

É necessário conferir o **Body real do External Request** e o seletor que fornece a identidade da mensagem. O Body histórico documentado tinha somente subscriber/text/nome. Não inventar que existe um campo sistêmico `Message ID`, nem preencher o exemplo com um identificador fixo. Mesmo evento em retry precisa manter ID/payload; duas mensagens legítimas iguais precisam ter IDs distintos.

Depois dessa prova, adaptar o Body e eventual tratamento do ACK **no mesmo flow**, conservar coorte/roteamento e preparar a ativação controlada da versão 2. A vinculação de identidade e o retorno humano têm flags próprias; não habilitar todas as capacidades indiscriminadamente. Conversas legadas não ganham autoridade de conta/evento por backfill de transcrição.

`spec-drift.txt` registra por que o spec inteiro não pode ser aplicado agora: sete envs novas da frente Marketing existem no app vivo e não nesta base do arquivo. Substituir o spec as removeria. Nenhuma delas foi apagada ou alterada; a adaptação Concierge permanece local. O release precisa reconciliar esse drift com o trabalho da outra frente, além de ter seu alvo autorizado. Não alterar o script de drift para esconder essas diferenças.

**Estado:** compatibilidade local testada e configuração preparada; flow existente identificado; Body/identidade real pendentes. Não declarar que o candidato novo já atende pelo WhatsApp. O teste antigo permanece como estava.
