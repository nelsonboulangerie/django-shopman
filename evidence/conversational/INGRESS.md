# WP01 / WP08 — ingresso e sync de identidade

Artefato local v2: `flows/manychat-conversation-v2.json`. É fixture de contrato revisável, não export nativo nem flow homologado/publicado. G01/G02/G03/G04/G07 continuam pendentes. Nenhum Default Reply ou conta externa foi modificado.

C01 verifica chave antes de ler identidade, falha fechado inclusive DEBUG e permite chave anterior explícita (`api_key_previous`) durante janela administrada. Não se cria HMAC para External Request. Conta (`account_id`) e canal (`transport_channel`) vêm da configuração; divergência no body é recusada. `channel_ref` comercial permanece responsabilidade da configuração de serviço. Limites: body 32 KiB, texto 16k, profundidade 8, evento 4096 caracteres, IP 1200/min, conta 1200/min e subject por conta/canal 60/min. Esses tetos locais são contenção inicial, não SLO/capacidade homologada G06.

Envelope normalizado conserva ID integral, hash SHA256 do payload JSON canônico, subject, conta, transporte, timestamp informado, recebimento local, tipo, correlação e método de autenticação. A assinatura/chave nunca é persistida. ACK 200 serve ao mapeamento proposto do flow; registra somente recebimento/trabalho. Conflito é 409. Nenhum getInfo/identify/IA roda no ACK; texto ausente não é substituído pela última mensagem do perfil.

H04: chamada síncrona era estruturalmente demonstrada no código auditado; regressão usa stub que falha se chamado. Isso demonstra ausência de rede no ACK local; não mede latência ManyChat.

H07: `data.id` usado como nonce descartava futuras atualizações do assinante e nonce gravado antes do sync impedia retry após erro. Agora só `event_id` explícito deduplica, na mesma transação do sync. Sem event_id, reaplicação do estado de assinante é idempotente e não promete identidade de evento. JSON não objeto retorna 400. `false` textual revoga em vez de conceder por `bool('false')`; tipos ambíguos não mudam consentimento. Conservado ProcessedEvent, HMAC específico do sync e fonte canônica CommunicationConsent. Uso real/formato de eventos nesta conta continua G02; nenhuma ampliação de força de identidade ou consentimento.

J05/J07: retry conserva identidade em vez de exigir nova fala ou gerar intenção; J12: opt-out textual deixa de ser convertido em opt-in. São propriedades de testes sintéticos; A/U/R/M/T, entendimento humano e entrega remota ainda não medidos.

Validação local em 11/09/2026, base `1138c95eee0862630330328cf3bfe2f0b6424796` + working tree candidato: 78 passed, 0 skips, 12.39s; log `ingress-tests.txt`. Comando:

```sh
DATABASE_URL=postgresql://concierge_test@localhost:56419/concierge_ingress REDIS_URL=redis://localhost:56420/2 PYTHONDONTWRITEBYTECODE=1 /Users/pablovalentini/Dev/Claude/django-shopman/.venv/bin/python evidence/conversational/run.py shopman/storefront/tests/test_concierge_ingress_contract.py shopman/storefront/tests/test_concierge_webhook.py packages/guestman/shopman/guestman/tests/test_manychat.py packages/guestman/shopman/guestman/tests/test_manychat_ingress_regressions.py packages/guestman/shopman/guestman/tests/test_manychat_consent_sync.py -rs
```

SHA256 da fixture de flow: `4a4f3bd53851c74e22145d119359776afc47d5bbf7edc0667f04d2fa4812065d`. Tentativas anteriores: 22 passed (H07/consent); integração inicial 4 failed/29 passed enquanto service/account estava em edição concorrente; segunda 1 failed/75 passed por fixture CONFIG_OFF sem versão; corrigidas e rerun 78 passed. Sem esconder falhas iniciais.

Limites preservados de Guestman: ProcessedEvent não tem fingerprint do payload, portanto apenas ingresso conversacional C01 detecta conflito de conteúdo. Sync de consentimento mantém comportamento já testado de log/continuação quando seu writer falha; reconciliação dessa situação exige observabilidade/política do owner. Nenhuma migração de Core foi inventada para estender o escopo. A autenticação HMAC do sync continua separada do ingresso conversacional; eventos reais e vínculo de conta de sync seguem homologação G02/G04.

## WP08 — capacidades e segundo transporte sintético

`transport.py` fornece `ChannelCapabilities`, `ConversationAdapter`, `adapter_for`, `send_for`, `response_allowed`, `handoff_for` e `identity_for`. O serviço de conversa consome esses helpers para claim, tools, janela, saída, handoff e enriquecimento. Conta/provider/canal persistidos precisam corresponder à configuração v2 ativa: mudar a conta não dá acesso ao contexto anterior. Alterar o adapter exige configuração explícita; não existe ativação automática de IG/Messenger.

ManyChatAdapter usa o envio transacional existente, texto até 4000 caracteres, janela de 24 horas e campo de handoff. Não declara receipt de entrega, botões/postback/mídia ou identidade estável de evento homologados. `OpaqueAdapter` fica exclusivamente em `tests/support`: subject não numérico, sem telefone, botões, handoff remoto ou receipt; janela sintética de 30 minutos. O mesmo núcleo aceita entrada/turno/resposta, preserva consumo, contém saída e impede consulta de recibo sem identidade em ambos.

Bloco essencial maior que a capacidade retorna `not_applied/essential_block_too_large`, preservando texto integral e alertando pelo serviço. Não corta Pix/CTA/prazo nem finge envio. Adaptação semântica para formatos mais curtos permanece necessária se a copy exceder o limite; o teste não demonstra homologação de renderização no aparelho.

Enriquecimento exige `identity_link_enabled` explícito (default fechado G04), escopo correto e adapter que o suporte. ManyChat usa somente o subject no resolver do fornecedor; telefone/nome alegados pelo body não promovem vínculo. Fake sempre retorna ausência de identidade e navegar continua possível. Nenhuma credencial universal ou nova fonte de consentimento foi criada.

Validação C08 + C01 integrada: **41 passed, 0 skips, 17.24s**, PostgreSQL/Redis isolados acima; log `capabilities-tests.txt`. Executado com o mesmo runner e env, módulos `test_concierge_capabilities.py` + `test_concierge_ingress_contract.py`. C08 contém 10 cenários parametrizados nos dois adapters. Primeiro ensaio 16 passed; ampliação 18 passed/2 failed porque teste esperava exceção interna em vez de erro público `authority_unavailable`; oráculo corrigido mantendo prova de lookup não chamado. Ruff dos três arquivos C08 e diff check aprovados. Nenhum resultado comprova entrega real, UX no aparelho, export de flow ou autorização de identidade.

## Revisão adversarial C03/C04/C08

`test_concierge_adversarial_integration.py` cobre três defeitos demonstrados por fault injection: bloco Pix saía após resumo rejeitado/unknown; prepared de claim expirado era descartado pelo fence atualizado; receipt de resultado rejeitado precisava conservar seu erro original. A revisão também acrescentou prova de identidade alterada exatamente antes da execução idempotente, lookup de status contido por troca de conta, recuperação explícita ordenada sem retry unknown e revisão em vários blocos só oferecida após o último primário aceito.

Correções dos owners: dependência por Message existente, recuperação de prepared com contexto/fence verificáveis, guard de leitura, comparação de identidade sob lock e replay do resultado rejeitado. Retry explícito exige gate `output_retry_enabled`, não aplicação comprovada, contexto ainda válido e predecessor aceito. O teste de race verifica que a injeção realmente ocorreu, evitando verde por erro anterior.

Também foi encontrado e corrigido pelo owner tools um erro de serialização Decimal no snapshot de revisão; o teste passou a exigir review válido antes de testar race. Evidência inicial foi 3 failed no lote de saída, seguida por 27 passed após os primeiros ajustes. Ampliação seguinte 30 passed/2 failed revelou fixture de retry sem identidade de entrada e o Decimal real; ambos foram corrigidos antes do novo ensaio. Não tratar essas falhas como skips nem como comprovação de fornecedor.

A divisão semântica de `transport.semantic_blocks` conserva cada linha inteira e todos os caracteres entre blocos; linha essencial maior que capacidade continua recusada integralmente. Núcleo liga `depends_on` em todos os blocos e associa prova de revisão/disclosure ao último bloco primário, conservando Pix extra indivisível. Handoff explícito agora grava/envia um ACK determinístico depois de conter o bot; não exige IA nem afirma disponibilidade imediata da equipe.

Resultado final dessa revisão: **34 passed, 0 skips, 13.58s**, log `adversarial-tests.txt`; comando com mesmo env/runner acima, módulos `test_concierge_adversarial_integration.py` + `test_concierge_capabilities.py`. São 10 regressões adversariais e 24 casos de capacidades (12 cenários nos dois adapters). Ruff dos arquivos desta fatia e diff check aprovados.

## Corpus hostil e barreiras PostgreSQL — complemento da tabela 8.2

Na revisão posterior ao congelamento anterior, o corpus foi finalmente executado: a hipótese de URL em nome tornou-se defeito reproduzido. `boundary-races-before.txt` preserva **5 failed / 2 passed**: nome de produto com newline criava linha de total/pagamento/instrução, URL externa em nome tornava-se ação textual, e `message` de tool result substituía fatos de catálogo. A reprodução inclui Product no banco → catálogo/listing/estoque canônicos → `browse_menu` → renderer, além de entradas diretas de corpus.

Correção autorizada limitada à apresentação: nomes citados em uma linha; controles e URLs em campos textuais neutralizados; fatos estruturados prevalecem sobre `message`. Não há blacklist de preços ou frases nem mudança no produto/preço armazenado. URLs estruturadas de Action, acompanhamento e AccessLink permanecem intactas; Pix extra não passa por sanitização de prosa. Log de falha de handoff passou a código sem subject/traceback que possa ecoar PII.

`test_concierge_boundary_races.py` adiciona duas barreiras com PostgreSQL, transações e PIDs de conexões comprovadamente distintos: revogação de Conversation (CLOSED + fence) antes do lock de saída impede chamada ao provider; handoff antes do lock de tool impede Session/Order. A primeira é revogação de autoridade conversacional, **não** teste de revogação de consentimento marketing. Provider permanece fake; locks e writers locais são reais.

Validação complementar: **81 passed, 0 skips, 29.07s**; log `boundary-races-tests.txt`, módulos `test_concierge_boundary_races.py`, `test_concierge_authority.py`, `test_concierge_engine.py`. Mesmo runner, `DATABASE_URL=postgresql://concierge_test@localhost:56419/concierge_ingress`, `REDIS_URL=redis://localhost:56420/7`; sem credenciais reais. Ruff e diff check aprovados. Serviços isolados permaneceram ativos para validação integrada do owner.
