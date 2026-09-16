# C04/C05 — corridas comerciais PostgreSQL

Revalidação adicional sobre candidato `ff1c9bee331e931250c10cd4a9de0c118f6dbf4e`. Testes novos em `shopman/storefront/tests/test_concierge_commercial_races.py`, com `transaction=True`, duas conexões independentes, barreiras/Event e **consulta `pg_blocking_pids` comprovando que o concorrente aguarda um lock real**. Cada worker fecha suas próprias conexões. Nenhum provider externo real; callback de pagamento inerte. PostgreSQL/Redis isolados `127.0.0.1:56419` e `127.0.0.1:56420/8`.

## Defeito confirmado e correção

O ensaio `transfer_and_site_edit...` reproduziu uma unidade reservada na origem **já abandonada**, embora a edição retornasse `already_abandoned` e a transferência tivesse concluído com duas unidades no destino. `cart.update_qty` reconciliava Stockman antes de bloquear/validar Session, em commits separados; o concorrente criava o delta de uma unidade e depois falhava na escrita da sessão. Isso é perda de disponibilidade por reserva órfã, não duplicação de Order. Evidência negativa preservada em `commercial-races-before.txt`: **2 passed, 1 failed**.

Correção no escritor canônico `shopman/shop/services/cart.py`: `add_item`, `update_qty` e `remove_item` passam a usar uma transação local conjunta e lock da Session antes de qualquer reserva/reconciliação. Sessão encerrada é recusada primeiro. Falha na escrita reverte também os holds. A mesma janela estrutural existia em add/remove; os ensaios pós-correção cobrem ambos. Ordem de locks mantida Session → Stockman; nenhuma política de preço, estoque ou atendimento alterada, nenhuma fila nova.

## Provas pós-correção

| Disputa | Oráculo |
|---|---|
| modify/commit | checkout segura lock após comparar total; modify aguarda no PostgreSQL e recebe `already_committed`; Order único com qty2/total180; Session committed, receipt commit único e holds totais2 |
| confirm/edit | edit mantém qty3/holds3 ainda não commitados; confirmação aguarda lock; depois do commit da edição, revisão antiga recebe `revision_conflict` persistido/replayável; nenhum Order; Session/holds preservam3 |
| transfer/site-update | transferência mantém origem abandonada e destino preparado dentro da mesma transação; update aguarda; após commit, recebe `already_abandoned`; origem holds0, destino qty2/slot-12/holds2, receipt transferência único |
| transfer/site-add | mesmo oráculo, sem reserva delta órfã após recusa |
| transfer/site-remove | mesmo oráculo, sem liberar indevidamente a reserva do destino |
| falha local após reconcile | fault injection na escrita Session para add/update/remove; mesma Session, mesmas linhas, mesmos IDs/quantidades dos holds; nenhum Order |

- `commercial-races-tests.txt`: **5 passed**, sem warning/skip (cinco disputas após correção).
- `commercial-races-consumers-tests.txt`: **55 passed**, sem skips; inclui oito testes acima e consumidores API cart_hardening, projections_cart, cart_context_pricing, concurrent_checkout e checkout_error_paths. Um warning de teardown: teste existente ConcurrentPaymentCaptureTests deixou quatro conexões usando o banco de teste. Não foi encerrado serviço nem ocultado warning.
- Ruff dos arquivos alterados: passou.
- Não somar os dois lotes como testes distintos: existe sobreposição. O master posterior consolida a prova do candidato.

Escopo da prova: interleavings descritos, transações/locks/recibos/reservas e conservação local. Não certifica arbitrariamente todos os interleavings, entrega ManyChat, ganho humano, homologação ou piloto. Nenhum serviço de teste foi parado e nenhuma produção foi alterada.
