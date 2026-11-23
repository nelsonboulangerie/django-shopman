# Continuidade Comercial Omnicanal — Laudo Adversarial e Plano Complementar

> **Data:** 2026-11-23. **Status:** PROPOSTA PARA REVISÃO POR TERCEIRO AGENTE — SOMENTE LEITURA, SEM AUTORIZAÇÃO DE IMPLEMENTAÇÃO.  
> **Objeto:** continuidade de identidade, necessidade/intenção, contexto, sessão comercial, pedido, pagamento e relacionamento entre canais do Django Shopman.  
> **Documento irmão (preservado e não substituído):** [Storefront Excellence — plano mestre de experiência, A/B e continuidade](../plans/STOREFRONT-EXCELENCIA-AB-CONTINUIDADE-OMNICANAL-2026-11-23.md).  
> **Escopo editorial:** este relatório EXPANDE e, onde houver justificativa, QUALIFICA hipóteses do primeiro relatório. Não altera o original nem documentos pré-existentes. Ao divergir, explicita a divergência e exige arbitragem do terceiro agente.  
> **Importante:** `Omniman` **não existe** e não é pressuposto da solução. Não criar app, domínio, modelo, endpoint ou feature flag por mera simetria de nomes.  
> **Limite de evidência:** leitura estática de trechos do `main` em 23/11/2026; não houve execução integral de WhatsApp, provedor de pagamento, testes multi-dispositivo ou homologação humana. Qualquer capacidade não demonstrada em ponta a ponta permanece **a validar**.

## 0. Resumo executivo e correção de foco

A investigação começou perguntando: **como uma pessoa começa em um canal e continua em outro?** É necessário ampliar a pergunta:

> **Como o Shopman permite que uma pessoa alcance seu objetivo comercial no canal que escolheu — inclusive 100% dentro da conversa com a Nice — e, caso decida mudar de canal, retome a mesma jornada sem perder contexto, autorização, escolhas, pagamentos ou compromissos?**

**Princípio central:** continuidade omnicanal **não significa** obrigar toda jornada a cruzar canais, nem obrigar toda conversa a terminar no site. A opção de trocar de canal deve ser conveniência, não exigência arquitetural.

A **jornada integral pela Nice/WhatsApp é requisito de primeira classe**, cobrindo informações e dúvidas, descoberta e recomendações adequadas, formação e revisão da sacola, retirada/entrega, confirmação expressa dos termos, registro do pedido, solicitação e acompanhamento de pagamento, status de preparo/entrega, alterações/cancelamentos elegíveis, resolução de problemas, retorno humano e pós-venda. Abrir o app do banco para efetuar Pix ou eventualmente um checkout hospedado seguro **não equivale a obrigar o cliente a navegar no Storefront**; porém a necessidade de mudar de aplicativo e o retorno ao diálogo são partes da experiência a comprovar.

**Tese de arquitetura preferida (hipótese, não decisão encerrada):**
- **Guestman**: identidade, contatos verificados, vínculos externos, preferências e relacionamento.
- **Orderman**: sessão comercial mutável, carrinho/itens, revisão, pedido e integridade do commit.
- **Conversação/Nice**: mensagens, turnos, episódios, intenções/necessidades, contexto de diálogo e posse da interação; consumir serviços de comércio, não tornar-se livro de pedidos.
- **Orquestrador Shopman/adaptadores**: passagem autorizada, descoberta, reconciliação entre contextos e canais; nenhum novo proprietário de preço, reserva ou pagamento.
- **Framework de Comércio Conversacional**: núcleo agnóstico, sem import de Django, Guestman, Storefront ou WhatsApp; artefatos e decisões portáveis. A Nice é um adaptador, não o framework.
- **Storefront e demais superfícies**: apresentação e comandos autorizados; não duplificar estado comercial.

**Não propor de início uma “sacola universal” nem uma entidade persistente “Intenção Comercial”** sem verificar se `Orderman.Session`, `Conversation`/episódios e serviços já compõem o comportamento. Um contrato fino de continuidade por referências pode ser suficiente.

## 1. Relação entre os dois relatórios: complementaridade, não substituição

| Primeiro relatório — continua canônico para | Este relatório — aprofundamento indispensável |
| --- | --- |
| Storefront Excellence e diretrizes de UX/A11y | Continuidade de relações, compromissos e intenções entre canais |
| A/B permanente, baseline A, candidata B e aprovação | Não usar A/B de UI para alterar política/efeitos comerciais da Nice |
| Copy Profiles, isolamento de variante, Projections | Contexto compartilhado com fatos/projeções válidos, sem copies falsas |
| Preservação do design existente | Jornada Nice-only que **não possui layout web** como requisito |
| Experimentos, coortes, releases e rollback | Episódios, identidade, autenticação, handoff e concorrência multicanal |
| Investigação H1–H4 sobre Guestman/Orderman | Prova por jornadas reais e matriz de responsabilidades/autoridade |
| Testes A/B da UI | Testes conversacionais E2E, incluindo Pix, cartão e pós-venda |

**Qualificação importante:** o primeiro relatório usa por vezes “transferência de sacola” como solução preferencial preliminar. Este segundo relatório estabelece que **retomada, espelhamento read-only, transferência reconciliada e sessão compartilhada** são alternativas diferentes. A escolha depende das regras do canal, titularidade, hold e revisão; nenhuma é aprovada apenas por ser mais simples de explicar.

## 2. Evidência estática encontrada no código vivo

### 2.1 Guestman já resolve aspectos importantes de identidade

- `packages/guestman/shopman/guestman/services/identity.py`: `ensure_contact_point` e `ensure_external_identity` com trava de titularidade e colisão de vínculos externos; PHONE/WHATSAPP compartilham família de identificação. **Reconhecimento ≠ autorização irrestrita para ler conta/pedido.**
- `shopman/storefront/identity.py`: resolução da identidade autenticada via middleware Doorman; diferencia `device` e `number` em certas jornadas e vincula rascunhos de checkout a um contexto opaco.
- `shopman/storefront/api/auth.py` e `docs/guides/whatsapp-access-link.md`: login/retorno WhatsApp, acesso via link e concessões; examinar escopo, força da identidade, expiração e roteamento antes de reutilizar.

**A validar:** como identidade externa de conversa se associa a Customer após autenticação em outro canal; revogação, retificação, exclusão LGPD e telefone reciclado; se há reivindicação automática insegura de dados antigos.

### 2.2 Orderman já mantém transação pré-pedido e pedido

- `packages/orderman/shopman/orderman/models/session.py`: `Session` é unidade mutável pré-commit; a identidade da sessão inclui `session_key` **e `channel_ref`**; o modelo registra origem e proprietário quando aplicável.
- `shopman/shop/services/sessions.py`: `create_session`, `modify_session`, `commit_session`, `assign_phone_handle`, `assign_customer` e `move_session_lines`. Esta última usa um único `channel_ref` para origem/destino; **não é evidência de transferência segura entre canais de venda diferentes**.
- `shopman/storefront/cart.py`: `CartService` liga sessão web ao cliente identificado e reprecifica conforme grupo; carrinho web normalmente se encontra via sessão do navegador.
- `shopman/shop/services/cart.py`: mutações delegadas a Orderman/Stockman, reservas e regras de data/canal.

**A validar:** passagem de itens, cupons, reservas, datas, preferências e pagamentos entre canais com políticas possivelmente divergentes. Evitar copiar preços/holds “verbatim” de canal a canal sem autorização de domínio.

### 2.3 A Nice já tem memória e ferramentas comerciais reais

- `shopman/shop/models/concierge.py`: `Conversation` registra `phone`, `customer_ref`, `channel_ref`, `session_key` de Orderman, `quote`, `summary`, `last_order_ref`, `turn_fence`, estado de handoff; `ConversationBinding` liga uma conversa lógica a transportes e inclui `identity_assurance`.
- `shopman/storefront/concierge/service.py`: ingresso, identidade, `attach_binding`, `identify`, posse/turno, handoff e `assert_turn_authority`.
- `shopman/storefront/concierge/tools.py`: `search_storefront`, `view_cart`, `set_item`, `list_fulfillment_slots`, `set_fulfillment`, `review_order`, `place_order`, `order_status`, mais ferramentas a inventariar integralmente.
- `place_order` exige revisão/orçamento vigente e confirmação posterior compatível, protege contra replay com `remote_mutations`, usa checkout canônico e retorna referência, estado e instrução de pagamento; `order_status` consulta pedido do cliente e consome `build_order_conversation` e `build_order_tracking`, reaproveitando promises/Actions.
- `shopman/storefront/concierge/cancellation.py`: autossserviço de cancelamento condicionado a elegibilidade e confirmação expressa; fora das condições, encaminhamento a equipe.
- `shopman/storefront/concierge/intents.py`: reconhece questões de catálogo, pedido/status, reclamação, cancelamento e necessidade de pessoa.

**Cuidado crítico:** em `_placed_result`, a Nice já pode enviar Pix copia-e-cola como resposta adicional e produz um `tracking_url` no Storefront; `order_status` devolve `payment_url`, `tracking_url`, `requires_payment_gate` e Actions. Isso prova que há um caminho conversacional de pedido/consulta, **mas não prova uma jornada totalmente resolvida sem abrir o Storefront em todos os estados de pagamento, correção, recuperação e pós-venda**.

### 2.4 Framework e planos existentes

- `docs/decisions/adr-049-comercio-conversacional-pacote-puro.md`: pacote agnóstico e adaptador no orquestrador; negócio continua dono de pedidos e efeitos.
- `docs/plans/COMERCIO-CONVERSACIONAL-FRAMEWORK-PLANO.md`: contratos, efeitos, compromissos, evidências, testes.
- `docs/plans/COMERCIO-CONVERSACIONAL-ADAPTADOR-NICE-PLANO.md`: implementação Nice em ondas N1–N9, com dependências e limitações; **plano histórico/estado a reconferir**, não presumir tudo entregue.
- `docs/plans/CONCIERGE-PLANO-DE-ACAO.md`, `docs/guides/whatsapp-concierge.md`, `docs/guides/whatsapp-access-link.md`: contratos de operação, integrações e UX conversacional.

**Critério de evidência:** distinguir implementado no `main`, coberto em testes, comprovado em pilha local e comprovado com provedor real. Um método existir não certifica experiência completa.

## 3. A jornada 100% Nice é obrigatória — não fallback

### J0 — Informações sem compra

Cliente inicia e termina no WhatsApp: pergunta horário, endereço, disponibilidade de um produto, conservação, alergênicos, preços, retirada/entrega ou dúvidas sobre a casa. A Nice responde com fatos/projeções verificados e validade adequada, pergunta somente o indispensável e conclui o assunto ali. Não exige cadastro, sacola, formulário ou visita ao site para informações públicas.

**Portões:** identidade proporcional; não inferir ausência de alergênico; preço/estoque/prazo têm fonte; se dúvida exige confirmação humana, criar caso e retorno com dono e prazo, não simplesmente “vou verificar”.

### J1 — Pedido completo na conversa (caso nuclear)

1. **Descoberta:** “Quero duas baguettes e croissants para amanhã”. Nice reconhece produtos/quantidades e esclarece ambiguidade sem inventar SKU.
2. **Disponibilidade:** consulta produto, preço e promessa; diferencia estoque pronto, produção futura, indisponibilidade e encomenda; não promete o que não pode cumprir.
3. **Sacola:** cria/edita sessão Orderman pelo canal conversacional; mostra resumo progressivo e oferece correção.
4. **Recebimento:** coleta retirada ou entrega, data, slot, endereço e taxa/mínimo quando pertinentes; pode reutilizar endereço salvo somente com autorização/identidade adequada.
5. **Pagamento:** pergunta forma elegível do canal. Não selecionar Pix silenciosamente se mais de uma forma for possível; seleção explícita ou preferência expressamente registrada e transparente.
6. **Revisão dos termos:** mostra itens, quantidades, preços, descontos, taxa, total, data, janela, forma de pagamento e condição de aceite da padaria; oferta tem token/versão, prazo e vínculo com a conversa.
7. **Confirmação:** usuário confirma **a revisão vigente** com gesto inequívoco. Mensagem ambígua, atrasada, encaminhada ou sobre orçamento antigo não gera pedido; repetir a confirmação é idempotente.
8. **Pedido registrado:** responde “recebido/aguardando aceite” conforme estado real; não chama recebido de aceito nem aceito de pago; transmite número e próximos passos **na própria conversa**.
9. **Cobrança:** quando o pagamento se torna exigível, entrega instrução segura por mensagem, preferencialmente Pix copia-e-cola em WhatsApp e alternativa acessível; cartão pode requerer checkout de gateway externo, **sem obrigar navegação no Storefront**.
10. **Confirmação financeira:** status não depende de “já paguei” dito pelo cliente; reconcilia webhook/ledger e informa se pago, pendente, expirado ou inconclusivo sem duplicar cobrança.
11. **Produção e entrega/retirada:** comunica estados reais com promessas e prazos; cliente pergunta “já está pronto?” e recebe a informação atual; não exigir acompanhamento web.
12. **Conclusão/pós-venda:** confirmação de retirada/entrega quando pertinente, recibo/nota conforme regras, satisfação, dúvidas, reclamação e resolução pelo mesmo canal com humano quando necessário.

**Condição de aceite J1:** teste ponta a ponta completo sem uma única passagem obrigatória pelo Storefront. Abrir banco para autorizar Pix ou gateway seguro para cartão pode ocorrer; deve haver retorno claro à Nice e estado de pagamento conciliado. Nenhuma funcionalidade essencial é ocultada atrás do site. Se a política regulatória, do gateway ou de segurança impedir uma etapa integral no WhatsApp, registrar a exceção exata e a alternativa mínima segura — não alegar “WhatsApp 100%” incondicionalmente.

### J2 — Pedido Nice-only com mudança de ideia

Cliente muda quantidade, data, endereço, entrega/retirada ou meio de pagamento após uma cotação. O sistema invalida orçamento/aceite anterior, recalcula pelo domínio, reapresenta mudanças materiais e solicita nova confirmação. Após commit, alterações seguem autoridade e regras de edição/cancelamento, nunca alteram silenciosamente termos já aceitos.

### J3 — Pedido Nice-only com falhas, atraso e concorrência

Cliente manda a confirmação duas vezes; perde conexão após enviar; recebe mensagem de pagamento muito tarde; pagamento confirma depois do vencimento; pedido é recusado pela casa; desconto/estoque muda enquanto conversa. Nice reconcilia por idempotência, mostra estado real, exige nova revisão quando necessário e oferece alternativa ou humano sem forçar abertura da loja web.

### J4 — Atendimento Nice-only sobre pedido anterior

“Cadê meu pedido?”, “Paguei e não recebi”, “Quero cancelar”, “Troque a retirada”, “Quero nota fiscal”, “Vou retirar atrasado”, “Tenho uma reclamação”. Nice localiza pedido **do titular autorizado**, explica o que pode fazer, executa ações tipadas somente quando elegíveis, passa para equipe com contexto e prazo quando necessário, e retoma conversa após resposta. Não abrir site como resposta-padrão para problemas que têm porta conversacional autorizada.

### J5 — Cliente recorrente Nice-only

Cliente retorna em outro dia; Nice reconhece vínculo verificado, lembra preferência declarada e histórico elegível, não supõe que uma conversa nova retoma a mesma intenção; oferece recompra **somente após revisar disponibilidade e preços novos**, com consentimento para novo commit.

## 4. Jornadas que cruzam canais (não substituem J0–J5)

### J6 — Nice → Storefront

Cliente iniciou sacola no WhatsApp e **escolheu** continuar no Storefront para visualizar fotos ou revisar melhor. O Shopman emite transferência/retomada com escopo/TTL/revogação; autenticação adequada; resolve sessão de origem por autoridade. No destino, oferece itens/quantidades/contexto, **reconcilia** preço, reserva, disponibilidade, slot, desconto e pagamento segundo regras do canal web, mostrando diferenças antes de qualquer efeito. Nice conserva episódio e sabe que cliente mudou de canal, sem afirmar pedido já confirmado.

### J7 — Storefront → Nice

Cliente montou carrinho no site e pede ajuda via WhatsApp. Identidade e posse precisam ser demonstradas; Nice recebe apenas contexto necessário, preserva itens e escolhas e responde dúvidas. Se cliente optar por comprar na conversa, a sessão de destino é reconciliada sob regras conversacionais. Nada de “copiar carrinho” com preços antigos ou assumir que o número WhatsApp é o dono do navegador.

### J8 — Conversa → atendimento humano → Nice (mesmo canal)

O cliente pergunta algo complexo ou apresenta reclamação; a equipe assume o atendimento com contexto correto, status de posse claro e sem respostas simultâneas da Nice. Quando devolvido, a Nice retoma o episódio e não reaplica comandos anteriores. **Isso também é continuidade**, mesmo sem mudança de canal.

### J9 — Vários canais em paralelo

Cliente mantém o Storefront e WhatsApp abertos e altera a sacola nos dois. Regras explícitas para “uma sessão autoritativa”, revisão otimista/controle de concorrência, conflitos e bloqueios; uma confirmação antiga da Nice não pode finalizar uma sacola modificada no site. Evitar replicar mutable state em dois destinos sem sincronização e autoridade.

### J10 — Anônimo → identificado / dois assuntos simultâneos

Visitante consulta site sem login e conversa por WhatsApp; posterior vínculo deve exigir comprovação proporcional e não revelar informação de outra pessoa. Um cliente pode simultaneamente comprar amanhã e reclamar de pedido passado; **mesmo Customer não significa mesmo Episode nem mesmo Cart**. Identidades recicladas, compartilhamento de aparelho e mensagens encaminhadas exigem tratamento adversarial.

### J11 — Outros canais

Telefone atendido por funcionário, PDV/retirada, atendimento presencial, integrações de marketplace e novos transportes: identificar quais contratos suportam continuidade por leitura e quais permitem escrita; **não assumir** que todos compartilham a mesma modalidade de preço, estoque, política ou permissão. Priorizar interfaces existentes e transferências autorizadas.

## 5. Transições e autoridade: contrato a ser provado

A passagem entre canais deve, conceitualmente, executar:

1. `identify`: obter sujeito e **nível de garantia**; distinguir número conhecido, aparelho autenticado e vínculo externo.
2. `locate`: encontrar somente sessões/episódios/pedidos que o sujeito pode acessar — sem escolher automaticamente um assunto ambíguo.
3. `authorize`: verificar escopo, expiração, revogação, identidade e titularidade no **momento do efeito**, não só quando gerou link.
4. `inspect`: ler snapshot com versões, fonte e validade dos fatos.
5. `propose_resume`: apresentar **o que** será retomado e **qual a consequência** da passagem; nenhuma cópia oculta de PII.
6. `reconcile`: solicitar ao domínio do destino cálculo das diferenças de regras/hold/preços. Não reutilizar preço ou reserva de outro canal automaticamente.
7. `confirm`: confirmar somente mudanças materiais ou efeitos que exigem autorização; nada de pedido automático no ato de abrir link.
8. `apply_once`: mutação idempotente, lock/revisão, um executor, resultado recuperável.
9. `observe`: atualização do canal de origem e eventuais compromissos, sem duplicar notificações ou criar dois donos do mesmo efeito.

**Essas operações são nomes conceituais, não endpoints prescritos.** O terceiro agente deve mapear nomes reais e suprimir etapas já realizadas pelo contrato existente.

**Regra de segurança:** ligação de Customer, ConversationBinding, browser session, Orderman.Session e Order é por referência autorizada, jamais por simples comparação de telefone ou por URL contendo identificador de sacola bruto. Um link capaz de conceder acesso tem natureza de credencial bearer e exige escopo e proteção apropriados.

## 6. Projections e contrato de experiência

Os dois relatórios concordam: **não duplicar verdade comercial**. A interface conversa e a visual recebem dados/projeções canônicos com adaptações de apresentação.

- Tempo de produção, data/slot, preço, taxa, disponibilidade, cancelabilidade, confirmação e pagamento devem compartilhar fonte semântica; copies podem diferir conforme canal/contexto e perfil, mas não o estado real.
- `Action` apropriada ao estado e autoridade; uma Action que existe no Storefront **não** implica que Nice possa executá-la sem nova autorização/permissão.
- Contrato conversacional deve representar `known`/`unknown`, `valid_until`, fatos de negócio, compromissos e recibos; não usar resposta gerada por LLM como sistema de registro.
- Expansões de Projection devem ser compatíveis com A/B do Storefront e com o adaptador Nice; mudanças de schema seguem expand–contract com testes pelos consumidores.
- Evitar “versionar regra comercial por canal de UI”: regras de canal existentes permanecem no orquestrador/config canônica.
- Enviar link de acompanhamento é **opcional**; consultar e responder sobre o pedido **dentro da conversa** é obrigatório para J1/J4.
- Pix e cartão: diferenciar pedido recebido, aceito, pagamento solicitado, instrução entregue, pagamento confirmado, falha/expiração, estorno; resposta pós-pagamento deve ser lastreada em fonte autoritativa, não em inferência.

## 7. Teste adversarial da jornada Nice-only: a matriz de aceitação

| ID | Experimento | Prova exigida |
| --- | --- | --- |
| N01 | Pergunta pública sem cadastro | Resposta útil sem exigir site/login |
| N02 | Produto ambíguo ou esgotado | Esclarecimento/alternativa, sem SKU inventado |
| N03 | Encomenda de amanhã e prontidão de fornada | Data/slot e promessa compatíveis com domínio |
| N04 | Carrinho com alterações sucessivas | Revisão atual, totais corretos, hold íntegro |
| N05 | Retirada vs entrega, cobertura e taxa | Política do canal validada e copy clara |
| N06 | Endereço do cadastro | Só com titularidade e nível de garantia apropriados |
| N07 | Seleção de Pix ou cartão | Escolha inequívoca, sem default indevido |
| N08 | Revisão e “sim” antigo | Rejeição de confirmação defasada, pedido único |
| N09 | Confirmação repetida/rede perdida | Idempotência, recuperação sem segundo pedido |
| N10 | Pix ainda sem QR/código por aceite pendente | Mensagem verdadeira; cobrança chega após autorização operacional |
| N11 | Pix copia-e-cola e retorno do banco | Pagamento e status resolvidos sem Storefront obrigatório |
| N12 | Cartão | Gateway seguro se necessário, retorno conversacional e status correto |
| N13 | Pix pago após timeout/cancelamento | Sem “pago” falso; reconciliação adequada e tratativa de dinheiro |
| N14 | Pedido aceito, preparo, pronto, entrega | Consulta conversacional com estado/prazo correto |
| N15 | Cancelamento permitido e não permitido | Porta elegível, confirmação, humano nos demais casos |
| N16 | Reclamação e resolução com equipe | Contexto e dono/prazo preservados, sem sumiço de caso |
| N17 | Recompra de cliente recorrente | Novo preço/disponibilidade, revisão e autorização próprias |
| N18 | Troca de prestador/transport binding | Transcrição e sessão lógica não duplicadas |
| N19 | Handoff humano concorrente com Nice | Posse única; comando atrasado revogado |
| N20 | Cliente solicita tudo via WhatsApp | Nenhuma etapa essencial impõe Storefront |
| N21 | Falha de provedor WhatsApp/janela 24h | Resposta/canal alternativo permitido e estado preservado |
| N22 | Conta excluída, contato reciclado, vínculo revogado | Não recupera dados/sessão indevidamente |
| N23 | Mudança de canal durante orçamento | Reconciliar; token do outro canal não aprova novos termos |
| N24 | Múltiplos assuntos em paralelo | Episódios e pedidos não se misturam |
| N25 | Notificação duplicada/evento fora de ordem | Uma consequência operacional, atualizações monotônicas |

Para cada caso: registrar commit, ambiente, seed, identidade/nível, canal, horário, estado antes/depois, mensagens realmente exibidas, Action/receipt, efeitos, evidência do gateway, regressão e limitações. Testar texto real no WhatsApp/ManyChat quando o provedor estiver disponível; harness/fakes não certificam entrega efetiva e UX no aparelho real.

## 8. Continuidade cruzada: matriz de testes

| ID | Cenário | Critério |
| --- | --- | --- |
| C01 | Nice → Storefront com sacola | Itens retomados com diferenças explícitas; sem reserva duplicada |
| C02 | Storefront → Nice com sacola | Identidade provada, contexto mínimo, sem vazamento |
| C03 | Troca de canal com pagamento iniciado | Não cria nova cobrança/segundo pedido |
| C04 | Identidade só por número e link encaminhado | Informações protegidas, exigência de prova proporcional |
| C05 | Sessões de dois clientes no mesmo navegador | Nenhum dado de cliente anterior recuperado |
| C06 | Atualização paralela web e chat | Detecção de revisão/conflito, sem last-writer-wins silencioso |
| C07 | Preço/promo/estoque muda entre canais | Requote obrigatório com diferenças e aprovação |
| C08 | Handoff humano e retorno da Nice | Sem diálogo concorrente/dupla execução |
| C09 | Cliente não quer trocar de canal | Jornada completa no canal original |
| C10 | Cancelamento, devolução e suporte posteriores | Uma verdade de pedidos e pagamentos em todos os canais |

## 9. Análise de alternativas de domínio — não decidir por nomenclatura

| Alternativa | Vantagem | Risco | Prova antes de decidir |
| --- | --- | --- | --- |
| **Guestman ampliado** | Já é micro-CRM e dono de identidade/contatos | Virar dono de carrinho, intenção ou workflow transacional indevidamente | Enumerar operações de CRM vs coordenação comercial, avaliar coesão |
| **Orderman + Guestman + composição no Shopman** | Preserva autoridades e reduz novas entidades | Orquestrador pode virar aglomerado de regras ad hoc | Um único serviço fino, contratos explícitos, testes cross-domain |
| **Capacidade fina de continuidade** | Reutilizável por qualquer canal e persona | Abstração decorativa, segunda autoridade, estado desnecessário | Demonstrar cenário impossível com serviços existentes |
| **Novo domínio independente** | Isolamento quando responsabilidade emergente for genuína | Duplica modelos, migrations e fluxo; custo alto | Só com evidência de coesão/vida própria e duas integrações reais; ADR |
| **“Omniman”** | Nome possível no futuro | **Não existe hoje** | Não propor como dependência nem como arquitetura assumida |

**Pergunta que decide:** há um estado durável de intenção/episódio comercial **não representável sem ambiguidade** por Session, Conversation/Episode, Guestman e Orderman? Se sim: qual a invariável exclusiva, ciclo de vida, privacidade, eventos e dono? Se não: manter referências/contratos sem criar tabela.

Uma sessão de Orderman representa comércio pré-commit; a Conversation representa interação; Guestman, pessoa. A ligação entre essas unidades pode exigir um *link* com expiração, estado e recibo — não necessariamente um novo aggregate de negócio.

## 10. Frontes de risco (ameaças que a solução deve enfrentar)

1. **Confusão identidade vs titularidade:** telefone WhatsApp, browser cookie e Customer podem divergir; usar prova no efeito.
2. **Conflito de sessões e holds:** “transferir” entre canais não equivale a mover linhas dentro do mesmo canal; quem libera reservas antigas?
3. **Oferta comercial divergente:** web e WhatsApp podem ter preços, regras, meios e timing de pagamento diferentes; toda reconciliação mostra diferenças.
4. **Confirmação defasada:** confirmação de texto anterior não autoriza orçamento novo.
5. **Recibo e rede:** confirmação sem retorno exige reconcile, não retry que duplique comando.
6. **Pagamento externo:** ausência de link web não exime de UX segura de Pix/cartão, checkout do gateway, webhook e conciliação.
7. **Janelas e consentimento WhatsApp:** mensagem proativa depende de política do provedor e consentimento; não prometer notificações irrestritas.
8. **Contexto excessivo:** não enviar dados pessoais completos para IA ou outro canal sem necessidade/autoridade.
9. **Projections velhas:** prazo/estoque/status no início do diálogo podem caducar; reconsultar e validar no momento decisivo.
10. **Duas fontes de compromisso:** Nice e Storefront não podem escrever “promessa” contraditória com pedido/operador.
11. **Handoff humano:** posse precisa sobreviver a mensagens atrasadas, worker concorrente e mudanças entre canais.
12. **Experimentos:** A/B do Storefront não pode afetar segurança/contrato do canal Nice; experimentação de política conversacional tem rigor próprio.

## 11. Plano proposto para o terceiro agente — primeiro análise, depois execução autorizada

### Fase R0 — Inventário de autoridade e contratos (somente leitura)

Ler ambos os relatórios, revalidar `main` atual, os WPs/ADRs e todos os serviços de identidade, sessões, checkout, conversa, pagamento, status, acesso, cases e notificações. Montar tabela **dono / modelo / comandos / leitura / eventos / privacidade / consumidores**, com `path:line` e status entregue/testado/não demonstrado. Não repetir como gap aquilo que já foi corrigido desde a leitura.

### Fase R1 — Prova integral da Nice-only (prioridade máxima)

Executar a matriz N01–N25 em harness isolado, além de pelo menos uma validação controlada com provedor real para os pontos que exigem WhatsApp e pagamento. Mapear todo salto obrigatório ao Storefront e distinguir: (a) conveniência opcional; (b) gateway bancário/externo necessário; (c) dependência funcional inadequada da UI web. Entregar laudo de bloqueios com gravidade e causas.

**Por que começa aqui:** não faz sentido criar ponte para Storefront se a Nice ainda não conclui corretamente uma compra em seu próprio canal. A completude nativa e a segurança do pagamento são pré-requisitos da continuidade.

### Fase R2 — Modelo de continuidade (leitura + prova de desenho)

Montar diagramas de sequência J6/J7/J8/J9/J10; identificar quais serviços reais bastam; definir autorização, sessão/episódio, política do canal de destino, idempotência, revisão/concorrência, expiração e reversão. Preferir referência + reconciliação, evitando novos modelos até prova contrária.

### Fase R3 — Confronto adversarial das alternativas

Apresentar H1–H4, custos de migração, complexidade, fronteira com Framework e WPs ativos. Selecionar menor proposta coerente, que satisfaça J0–J11, N01–N25 e C01–C10. Acessibilidade e clareza devem existir também na linguagem da Nice; link não é solução universal.

### Fase R4 — Plano implementável e separação por PRs

Somente depois de arbitrar arquitetura: backlog de WPs coesos, testes antes de implementação, contratos, rollout e rollback, migrations se inevitáveis, consumidores e precedência. **Nenhuma escrita é autorizada pelo presente relatório.** Alterações de domínio/criação de app e mudanças L3 do Storefront dependem de aprovação explícita.

### Fase R5 — Execução futura autorizada e homologação

A versão definitiva deve demonstrar: Nice-only, Storefront-only, transferências bidirecionais, múltiplos canais, retorno humano, pagamentos e pós-venda; compatibilidade com Storefront A/B e Projections; zero duplicação e segurança de identidade. Reportar resultados por cenário, com evidência e limitações.

## 12. Critérios de sucesso (gates não negociáveis)

- **Nice-first/Nice-only:** o cliente pode esclarecer, pedir, revisar, confirmar, receber cobrança, acompanhar e obter suporte **sem Storefront obrigatório**.
- **Opt-in de troca:** mudar de canal é decisão voluntária ou contingência justificada, e nunca apaga contexto silenciosamente.
- **Uma verdade transacional:** pedido/estoque/pagamento pertencem a seus domínios, com confirmação e recibos únicos.
- **Uma identidade autorizada:** nenhuma sacola, histórico ou dado de outro titular é exposto por atalho de WhatsApp, link ou cookie.
- **Um compromisso verdadeiro:** informação e prazos seguem Projections e a validade do estado; erros não viram promessas falsas.
- **Reversibilidade:** transferência, cancelamento, retomada e rollback são recuperáveis; efeito já executado não é desfeito só porque a UI voltou.
- **Sem regressão da A:** evolução não quebra Storefront, Admin, Nice, POS nem outros consumidores ativos.
- **Sem abstração especulativa:** novo domínio só se lacuna e melhor coesão forem provadas no código e nos testes.
- **Observabilidade:** correlação de episódio, conversa, Customer, sessão, pedido e efeito por IDs opacos, preservando privacidade.

## 13. Perguntas obrigatórias para resposta explícita do terceiro agente

1. Hoje é possível finalizar **J1 sem Storefront** para Pix? E para cartão? Onde estão os bloqueios exatos?
2. Em que estados a Nice entrega `tracking_url` ou `payment_url` como necessidade, não conveniência? Qual alternativa conversacional?
3. Quem recebe e comunica webhook de pagamento e aceite/recusa da loja ao cliente WhatsApp? Quais janelas e recibos?
4. Como o cliente Nice-only corrige data, quantidade, endereço e meio de pagamento **antes** do pedido e **depois** do commit? O que exige operador?
5. Existe posse de uma intenção pré-pedido independente de `Conversation` e `Session`? Precisamos mesmo de nova entidade?
6. O Guestman deve apenas comprovar/vincular identidade e preferências, ou também guardar ponte de continuidade? Justifique sua fronteira.
7. Como conservar reservas e preços ao cruzar `channel_ref` sem violar regras? Transferir, reprecificar, espelhar ou recriar sob autorização?
8. Como impedir atuação simultânea da Nice, do cliente web e da equipe sobre a mesma sessão ou compromisso?
9. Como preservar A/B, Copy Profiles e Projections para que um experimento de UI não contamine a Nice?
10. Quais gates, scripts E2E e cenários com provedores reais faltam? Quais já existem no `main`?
11. Há motivos comprovados para um novo domínio? Se sim, por que o orquestrador atual e Guestman/Orderman não bastam?
12. Quais conclusões do primeiro relatório ficam **inalteradas**, quais são **qualificadas** e quais precisam de **substituição fundamentada** na proposta final, sem reescrever o original?

## 14. Instrução de handoff: entregar os DOIS relatórios ao terceiro agente

O terceiro agente deve ler **ambos os arquivos integralmente**, junto aos contratos atuais, e produzir uma análise final unificada que não apague evidências históricas nem trate hipóteses como implementação concluída.

**Ordem de leitura recomendada:**
1. `docs/plans/STOREFRONT-EXCELENCIA-AB-CONTINUIDADE-OMNICANAL-2026-11-23.md` — baseline, A/B, copies, Projections, excelência e preservação visual.
2. **Este arquivo** — completude da Nice-only, continuidade multicanal, autoridades, segurança e cenários de prova.
3. ADR-043/release, ADR-049, planos em andamento de Storefront e Concierge, código vivo e evidências E2E.
4. Laudo do terceiro agente: **conclusões, contradições, fronteiras, contratos, backlog e proposta de implementação, com gates**.

**Critério de arbitragem:** quando este relatório qualifica o primeiro, explicitar a razão e a evidência. Se o `main` tiver mudado, prevalece o comportamento atual demonstrado. Não modificar os dois relatórios-fonte. Nenhuma execução de código ou rollout deve ser presumida autorizada apenas pela leitura.

## 15. Encerramento

> **Omnicanalidade bem-sucedida é liberdade de escolher um canal, não obrigação de usar todos.**  
> A Nice deve conseguir realizar uma venda e acompanhar sua conclusão no próprio diálogo. O Storefront deve realizar o mesmo percurso em sua interface. A passagem entre ambos deve preservar identidade, contexto, escolhas e compromissos, com reconciliação comercial explícita onde necessário. **O negócio continua com uma única verdade.**
