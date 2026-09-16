# Triagem do brief PDV — 10/09/2026

Base: branch atualizada sobre origin/main antes da implementação. Escopo restrito ao PDV; nenhum rename/migração de controles entre apps.

## Classificação antes da alteração visual

| Achado | Classe | Tratamento |
|---|---|---|
| Motivo do desconto: texto xs em campo h-11 (`PosCartPanel`) | Acidental | text-sm e px-3, conforme receita de campo do PDV. |
| Acerto de fiado: select h-10 (`session/index`) | Acidental | h-11, como os campos da mesma tela. |
| Cards rounded-lg em session/index, closing, report e PosCashReadingCard | Acidental | rounded-md, conforme escala já declarada; não alterar pills/QR. |
| Títulos de tela com leading-tight/tracking-tight (exceto display) | Acidental | Retirar os overrides, mantendo tamanho/peso. |
| Rótulos de campos comuns text-sm em PosTabPickerDialog e motivo de desconto no pagamento | Acidental | text-xs, conforme escala de label; controles mantêm sua própria tipografia. |
| Valores de estorno e comprovante sem tabular-nums | Acidental | Adicionar tabular-nums. |
| Disabled opacity-40 no teclado de pagamento | Acidental | opacity-50, conforme UiButton; preservar geometria das teclas. |
| text-amber-* em avisos | Acidental | Migrar para text-warning após conferir contraste do token; não substituir cores sem garantir legibilidade. |
| Teclado h-11/text-xl, pills rounded-full | Proposital | Geometria compacta de operação e agrupamento contextual; comentário no call site. |
| Recibo branco/preto, 11px/12px de impressão, QR branco/rounded-2xl | Proposital | Papel térmico e leitura óptica; comentário no call site. |
| Tipografia grande do display | Proposital | Leitura à distância; preservada. |
| PosDrawerLockDialog: botão /25 | Proposital | O comentário existente explicita discrição para acesso de emergência; preservar e não contradizer por varredura. |
| Altura global h-9/h-11, fundo e receita única de foco | Decisão do dono | Pergunta enviada antes de alterar primitivos; aguardando resposta. Recomendação: h-11 em campos, h-9 em inline, bg-card, foco como UiInput. |

A decisão global pendente não bloqueia os bugs funcionais nem correções locais que já têm regra escrita. Não se presume aprovação pelo silêncio.

## Contraste do aviso — decisão compartilhada pendente

Medição sRGB: warning claro atual `#c2701c` tem 3,48:1 sobre `#fcf6f1` e 3,73:1 sobre branco. O dark `#e09a4a` tem 7,47:1 sobre `#221610`. Migrar diretamente textos âmbar mais escuros para o token atual reduziria legibilidade. Recomendação enviada ao dono: corrigir o token claro uma vez para `#965411` (5,88:1 sobre branco; 4,86:1 sobre muted) e então migrar os avisos do PDV. Até a resposta, ambos preservados. Não criar um warning paralelo no app.

## Resultado desta etapa

- Cadastro: reabertura busca por ref sem reaplicar defaults; CPF da nota acompanha a comanda; lookup atrasado não recoloca cliente removido. Oferta de cadastro usa a mesma regra na tela e no intent, inclusive quando o lookup está indisponível.
- Fiscal: portão antigo removido do serviço, intent, interface e contrato. Teste fecha CPF + taxa e comprova endereço/CPF recebidos pelo adapter via directive.
- Atalhos do modal Dividir conta incluídos; Tela do Cliente informa limitação à mesma máquina/navegador e avisa quando window.open retorna bloqueio.
- Correções acidentais de geometria/tipografia aplicadas; exceções propositais preservadas e comentadas. Cores e padrões globais aguardam escolhas do dono.
- Validação: 869 testes pos-nuxt; 170 testes shopman/shop/tests/test_pos_*.py, um arquivo por invocação, PostgreSQL/Redis isolados; typecheck e Ruff passaram. Sessão local conferida visualmente nos dois temas. Nenhuma chamada real à SEFAZ ou hardware.
- Mudanças desta etapa ainda não publicadas.

## Escolhas posteriores do dono

Aprovados: campos de 44px, fundo `bg-background` com maior contraste, halo forte de 3px e proposta recomendada para warning (`#965411` claro; dark preservado). A aprovação é transversal aos apps e não precisa ser solicitada novamente. A implementação compartilhada deve ser conciliada com a frente de Produção; o texto de decisões pendentes acima descreve a triagem original. A revisão de pagamento na entrega está documentada em `PDV-PAGAMENTO-ENTREGA-2026-09-11.md`.

## Fechamento visual — 11/09/2026

Escolhas implementadas: o PR #599 já entregou 44px, bg-background e foco de
3px/50% nos primitivos dos seis apps operadores e no UiNativeSelect compartilhado.
Conferidos nesta branch, sem duplicar componentes. Avisos do PDV agora usam o
token canônico; warning claro consolidado em #965411 conforme a proposta aceita,
dark #e09a4a preservado. A pendência visual mencionada acima está encerrada.
