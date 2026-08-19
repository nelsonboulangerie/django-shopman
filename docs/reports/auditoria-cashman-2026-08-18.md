# Auditoria profunda — Cashman

> Série "um app por vez", nº 1 · 2026-08-18 · Base: leitura integral do código (main, pós #215)
> Escopo lido: os ~1.700 loc do pacote, mais toda a fronteira — `shop/services/pos.py` (liquidação da venda, refund, PIN gerencial), `backstage/services/pos.py` (560 loc, tradução do balcão), `backstage/services/closing.py`, `backstage/services/financial_reconciliation.py`, projections (`cash_session`, `bi_cash`), admin, migração, seed, e os 38 testes do pacote + 16 do framework (`test_pos_cash_ledger`).

---

## Veredito em uma frase

O Cashman é o app onde a filosofia da casa está mais bem realizada — e é cercado por **três buracos que não são dele**: uma corrida entre lançar e fechar que o pacote permite, uma rede de segurança que o código *cita no presente* mas **não existe**, e um gêmeo legado ainda instalado no backstage. Nenhum dos três exige desconstruir; os três exigem ação antes do alpha.

---

## Parte I — O que está certo (e por quê importa registrar)

Registro primeiro porque o plano de ação não deve tocar nisso — e porque parte do que segue *vai além* das melhores práticas, não apenas as cumpre.

**1. O fechamento cego é estrutural, não comportamental.** `Shift` não tem coluna de dinheiro — não há número para a projection do terminal vazar, por construção. Esperado, contado e diferença são sempre provados por `Σ` do livro. Isso é superior ao padrão da indústria (que guarda `expected_q` em coluna e reza).

**2. Uma tabela de sinais, três camadas que a leem.** `SIGN_BY_KIND` alimenta a validação do service, o `CheckConstraint` do banco, e existe um teste (`test_sign_allows_e_a_mesma_tabela_do_check_constraint`) que **prova a paridade entre as duas**. O sinal mora no tipo; sangria positiva é impossível em três níveis. Elegância real: uma fonte, sem espelho.

**3. Estado dobrado do livro, não coluna.** Pedidos de troco não têm status: o estado é o `change_requested` mais o filho (`served`/`cancelled`) que aponta por `parent`, primeira resolução vale. Zero risco de coluna e livro divergirem — a doença que matou o modelo antigo.

**4. Segurança de balcão pensada por adversário, não por checklist.** Sangria exige PIN gerencial *sem limiar* (o docstring explica o golpe que isso fecha: sangria inventada abaixa o esperado e a contagem cega bate redonda). PIN via `doorman.PinCredential` (HMAC + lockout), permissão `cashman.adjust_shift` verificada, duas assinaturas na mesma linha. Motivo da saída exigido **no servidor** — com a justificativa escrita: *"um contrato que só a superfície cobra não é contrato"*. O `cash_shift_id` é resolvido pelo backstage, nunca aceito do browser. Suprimento não exige gerente — e o docstring prova por que não precisa (sobra não esconde desfalque). Isso é modelagem de ameaça de verdade.

**5. Fronteiras disciplinadas e testadas.** `test_boundaries` afirma que o domínio não importa nada da suite além de `get_user_model` — e o teste quebra se alguém importar. O `backstage/services/pos.py` é tradução pura (vocabulário sangria/suprimento ↔ cash_out/cash_in num dicionário único), nada lá grava `Entry` por conta própria, nada soma o livro no terminal. Admin de `Entry` é readonly com `has_add/change/delete` negados.

**6. Denominações de troco com fonte única projetada.** A lista `CHANGE_DENOMINATIONS` viaja para a tela via projection em vez de ser repetida em TypeScript — o comentário antecipa até a saída de circulação da moeda de R$ 0,25. Semântica e manutenção pensadas juntas.

**7. Honestidade documentada.** O limite da imutabilidade ("quem tem acesso ao banco edita; não prometa mais do que isto entrega") e o limite do SSE de troco ("prometer recado entregue seria mentira") estão escritos no próprio código. Docstrings registram o *porquê* e o defeito histórico que cada regra desfez (PR #178, o buraco da chave física). É o padrão de semântica que o resto da suite deveria perseguir.

---

## Parte II — Falhas e brechas (por severidade)

### F1 · CRÍTICA — Lançamento pode entrar depois da contagem, em turno fechado

`ledger.record()` valida `shift.is_open` **na instância recebida, sem lock e sem transação própria**; `close_shift()` tranca o `Shift` com `select_for_update`, mas `record()` nunca toca nessa linha — logo os dois não se serializam. Interleaving possível, e realista no fim do expediente:

1. Operador finaliza venda em dinheiro → `_settle_pos_sale` abre `transaction.atomic` com o `shift` buscado *antes* (por `_require_open_shift`, sem lock);
2. Gerente executa `close_blocking_shift` → COUNT gravado, turno fechado, commit;
3. A transação da venda insere o `SALE` — a checagem stale passou — e commita.

Resultado: dinheiro entra no livro **depois** da contagem, num turno CLOSED. `expected_before_count` passa a incluir a venda tardia, o `count.amount_q` (congelado como `contado − esperado no instante do fechamento`) fica órfão da sua premissa, e `counted()` devolve um valor que a gaveta nunca teve. **É exatamente a anomalia que o fechamento cego existe para tornar impossível.** Nenhuma camada impede: não há constraint ligando Entry a turno aberto (nem poderia trivialmente), e o teste que existe (`test_turno_fechado_tambem_recusa`) cobre só o caso sequencial.

O mesmo vale para sangria/suprimento/abertura de gaveta: `_open_shift_or_raise` busca sem lock e `_record` insere depois.

**Correção barata, sem redesign:** `record()` ganha `transaction.atomic()` próprio e re-lê o turno com `select_for_update` (ou ao menos `.only("status")` fresco *dentro* da transação) antes de criar o Entry. Custo: um SELECT FOR UPDATE por lançamento — irrelevante no volume de uma padaria, e alinha `record()` com a disciplina que `close_shift()` já tem. Teste de concorrência acompanhando (o Payman tem `test_concurrency.py`; o Cashman merece o seu).

### F2 · CRÍTICA — A rede de segurança citada no código não existe

Dois lugares afirmam, no presente do indicativo, que uma divergência será acusada:

- `_settle_pos_sale`, no `except` que **engole a exceção** da liquidação: *"Fica o erro; o cruzamento Payman × livro-caixa (WP-7) e a leitura Z do turno acusam a venda sem linha."*
- `financial_reconciliation.py:194`: *"O cruzamento com o livro-caixa é o check `cash_ledger_mismatch` (WP-7)."*

`grep -rn cash_ledger_mismatch` no repositório inteiro: **uma ocorrência — o próprio comentário.** O check não existe. O WP-7 do CASHMAN-PLAN está no roadmap, não no código. A `financial_reconciliation` diária cruza Orderman × Payman com rigor real (severidades, DayClosing, alerta) — mas **nunca abre o livro do Cashman**.

Consequência concreta: se `settle_terminal_tenders` falhar depois do commit da venda (o cenário do `except`), o dinheiro está na gaveta, **nem o Payman nem o livro têm a linha**, e o único acusador é a diferença na contagem cega — horas depois, misturada com o turno inteiro, indistinguível de troco errado. O design confiou o caso raro a um vigia que ainda não foi contratado.

**Ação:** implementar o WP-7 mínimo já — por turno fechado: `Σ SALE cash do livro` × `Σ settle(cash) capturado no Payman` (cruzando por `payment_ref`/`order_ref`, que **já existem** no Entry exatamente para isso), mais o inverso: intent cash capturado sem linha `sale`. São duas queries e um issue-code novo dentro da `financial_reconciliation` que já existe. Enquanto não entrar, os dois comentários devem virar futuro do indicativo — comentário que afirma guarda inexistente é a gambiarra mais perigosa que há, porque desarma quem lê.

### F3 · ALTA — O gêmeo legado ainda mora no backstage

`backstage/models/cash_register.py` mantém `POSTerminal`, `CashShift` e `CashMovement` — o modelo antigo, **com a coluna `difference_q`** (migração 0014 ainda a alterou), ou seja, o exato anti-padrão cuja morte é a tese fundadora do Cashman. Estão exportados em `models/__init__`, têm admin testado (`test_admin_cash_register.py`), o seed ainda os limpa ("somem no WP-5; até lá, limpar"), e `pos_intent.py` ainda descreve o fluxo como "Orderman/**CashShift** services".

Nada de vivo escreve neles — verifiquei — mas em pré-alpha, com sua doutrina explícita de não dever nada a legado, manter duas taxonomias de caixa instaladas é convite a: (a) alguém importar o modelo errado (o nome `CashShift` é *mais óbvio* que `Shift`); (b) migrações e testes carregando peso morto; (c) o `pos_intent` mentindo sobre a própria arquitetura. **O WP-5/WP-6 do plano (backfill + remoção) deveria ser antecipado: não há dado de produção para backfillar — o "ponto mais delicado" do plano evaporou.** Hoje é `makemigrations --empty` + delete; depois do go-live vira projeto.

### F4 · MÉDIA — Idempotência da venda por `exists()`, sem constraint, contra a doutrina da própria casa

`_record_sale` deduplica por `Entry.objects.filter(shift, kind=SALE, order_ref).exists()` antes de criar — TOCTOU clássico: dois submits simultâneos da mesma venda (retry de rede do PDV) podem gravar duas linhas `sale`, dobrando o dinheiro esperado do turno. O contraste é interessante: para unicidade de turno aberto, o próprio Cashman diz *"a unicidade é constraint do banco... a constraint decide"* — e aqui a mesma casa usa `exists()`. Idem `cod_settled` ("não repete" pelo mesmo padrão).

**Ação:** `UniqueConstraint` parcial `(shift, order_ref)` com `condition=Q(kind="sale") & ~Q(order_ref="")` (e o análogo para `cod_settled`), mantendo o `exists()` como fast-path de mensagem amigável. O banco decide; a mensagem continua sendo da casa — a fórmula que vocês já usam no `open_shift`.

### F5 · MÉDIA — Payload do pedido de troco só é validado na superfície

O `amount_q` do pedido de troco vive no `payload` JSON (correto — o lançamento tem efeito zero por construção), mas o **pacote** aceita qualquer payload: `record("change_requested", payload={"amount_q": -500})` passa. Quem valida (`>0`, denominações da lista canônica) é o `backstage/services/pos.py`. Isso viola o princípio que o próprio arquivo enuncia ao exigir motivo da sangria no servidor: *contrato que só a superfície cobra não é contrato*. O único escritor do livro (`record`) deveria validar o payload dos tipos que têm schema — ao menos `change_requested` (amount>0) e `receipt_result` (status ∈ enum). Hoje o schema mora em `docs/reference/data-schemas.md` como convenção; conveção não recusa nada.

### F6 · BAIXA — Sinais anunciados, ninguém escuta

`shift_opened`, `shift_closed`, `entry_recorded` são emitidos com disciplina (`on_commit`, testados) — e **nenhum receiver existe fora do pacote**. O anúncio de pedido de troco no SSE é chamado *diretamente* pelo backstage (`_announce_change_request`), não via sinal. Ou seja: a superfície de sinais é promessa sem cliente, e o acoplamento que ela existiria para evitar já aconteceu por outro caminho. Duas saídas coerentes: mover o emit de SSE para um receiver de `entry_recorded` (aí o backstage esquece de anunciar e o anúncio sai mesmo assim — mais robusto), ou registrar que os sinais são para o BI incremental futuro e aceitar o custo. O estado atual é o pior dos dois: infraestrutura viva sem uso e o uso real fora dela.

### F7 · BAIXA — A segunda assinatura é verificada num objeto e persistida por outro

`validate_manager_override` verifica username+PIN+permissão via `_verify_manager_pin` — que **retorna o User** — e o descarta; depois `_approver()` re-consulta o banco pelo mesmo username, exigindo apenas `is_active + is_staff` (sem re-checar `adjust_shift`). Funciona porque o dict é o mesmo na mesma request, mas é o padrão "validar A, persistir B": um refactor futuro que separe os dois momentos herda um buraco pronto. Correção de cinco linhas: o validador devolve o user autorizado e é *ele* que vai para `approved_by`.

### F8 · Pontos de verificação (não afirmo — checar)

- **Turno atravessando a virada do dia:** operador esquece o caixa aberto; `_cash_shift_summary(closing_date)` do fechamento do dia lida com turno ainda OPEN de ontem? Há alerta (omotenashi_qa tem `_day_closing_check`, não li o corpo)? Cenário banal de padaria.
- **`record_receipt_result`** tem o mesmo TOCTOU do F4 ("depois de printed não grava outro" via leitura + create), mas efeito zero em dinheiro — provavelmente aceitável; registrar como decisão, não como acidente.
- **QA físico:** gaveta/agente (`tools/pos-counter-agent`) e impressora térmica seguem sem teste em balcão real — fora do escopo de código, mas é o maior risco residual do app depois de F1–F3.

---

## Parte III — Desconstruir ou não?

Você autorizou demolição. Minha resposta, depois de ler tudo: **não demolir o pacote.** A arquitetura (custódia = estado, história = livro, sinal no tipo, estado dobrado) é a melhor da suite e está *mais* alinhada aos princípios da casa do que partes dos apps "maduros". O que merece demolição é o **entorno**:

1. **Demolir de fato:** o legado do F3 — agora, enquanto backfill é uma palavra sem objeto.
2. **Construir o que o código finge que existe:** WP-7 mínimo (F2) dentro da reconciliação diária que já está de pé.
3. **Fechar o pacote sobre si mesmo:** lock no `record()` (F1), constraints de idempotência (F4), validação de payload no único escritor (F5) — três mudanças pequenas que transformam garantias "de disciplina" em garantias "de construção", que é a assinatura do próprio app.
4. **Decidir o destino dos sinais** (F6) e o refactor de cinco linhas do aprovador (F7).

Estimativa honesta de esforço total: F1+F4+F5+F7 cabem numa PR focada com testes de concorrência; F2 em outra; F3 numa terceira de remoção pura. Nenhuma toca superfície Nuxt.

Próximo da série, quando você quiser: **Payman** — já levo daqui dois fios puxados (tenders mistos existem de verdade, o que reabre a semântica de `get_active_intent`; e a fronteira `settle_terminal_tenders` que o F2 expôs é dele também).
