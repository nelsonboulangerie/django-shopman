# Interface compacta do PDV — 10/09/2026

Candidata sobre origin/main `d525c248d`, branch `codex/pdv-ui-release-20260910`.
Recorte da interface aprovada no estudo E–C compacta: linhas com quantidade × nome,
preço unitário e total; detalhes em acordeão contínuo; numpad permanente e modos à
direita; seleção em lote pela linha inteira; Qtd/Obs desabilitados para lote;
navegação Alt+I e ajuda central de atalhos. Navegação/seleção recolhem ações gerais,
conservando o total. Concluir restaura o rodapé. Pagamento indica F4.
Cabeçalho do atendimento quebra linha no tablet para evitar sobreposição.

Sem backend, migrations, seed ou configuração de deploy alterados. Autoria é
metadado opcional: só aparece quando fornecida pelo servidor. Este recorte não
acrescenta esses metadados nem muda sincronização entre terminais.

## Validação local

- Typecheck e ESLint dos arquivos alterados passaram.
- Vitest: 48 arquivos, 845 testes passaram, incluindo 39 de carrinho.
- Build de produção e três E2E Chromium de login/offline passaram. O mock agora
  responde 403 para sessão sem estação/usuário, em vez de simular sessão com `{}`.
- Lint global: quatro erros preexistentes em PosDisplayPublisher, session/index e
  dois testes não alterados, além de 25 avisos em pages/index.
- Tela completa com Django/PostgreSQL/Redis locais: última execução após ajuste
  do cabeçalho passou em 23,88s, pedido sintético PDV-260910-B95.
- Jornada: abrir comanda, dois produtos, quantidade por teclado, seleção em lote,
  desconto de 1%, observação, envio à cozinha e fechamento em dinheiro exato.
  Banco confirmou um pedido e uma entrada SALE de 2475 centavos.
- Capturas conferidas em 1366×1000 e 1024×768.

Artefatos locais não versionados em `.artifacts/pdv-20260910-a1/`: test_full_ui.py,
full-ui.cjs, logs e capturas. Adaptadores de teste, sem pagamentos externos. O
ensaio aborta SSE e usa polling; não comprova SSE, concorrência entre terminais,
impressora, gaveta ou gateway físico. Sem venda de teste no ambiente online.

## Caminho de publicação

PR com checks obrigatórios, merge normal e Deploy Images no main. O app existente
shopman-alpha atende pdv.boulangerie.com.br; não foi identificado outro ambiente
separado. Não aplicar spec nem resemear dados. Este relatório registra a candidata;
a conclusão do deploy exige verificar a implantação ativa correspondente.

O gate compartilhado identificou tamanhos avulsos no carrinho. Textos auxiliares
foram alinhados a text-xs e o total a text-xl; 220 testes do operator-kit passaram
após a correção, sem exceção adicionada à regra tipográfica.

## Conclusão de seleção após ação

Envio e cancelamento de envio em lote agora informam o resultado ao carrinho.
Só o sucesso conclui o modo e restaura o rodapé. Erro ou ausência de ação mantém
os itens marcados para nova tentativa; envio duplicado durante espera é bloqueado.
Desconto pelo numpad mantém seleção enquanto o operador digita o valor.
847 testes do PDV passaram, incluindo sucesso, falha e repetição das duas ações.
Ensaio completo atualizado: falha HTTP 503 simulada preservou seleção; nova
 tentativa com Django real concluiu a seleção e devolveu Pagamento. Fechamento
confirmado no banco em R$ 24,75, pedido PDV-260910-P32 (35,65s).

## Ajuste visual de cabeçalho e atalhos

Cabeçalho agora mostra apenas X itens com tipografia do título anterior; Selecionar
 e Concluir usam pills. A altura acompanha o cabeçalho de contexto por ResizeObserver,
com divisórias confirmadas em y=97px no tablet. A folga acima das ações da linha
ativa diminuiu 6px. OperatorKbd centraliza as indicações dos apps operacionais,
com variante inversa para botões sólidos; atalhos e semântica preservados.
847 testes e typecheck do PDV, 220 testes do kit e typecheck/8 testes de Produção
passaram. Ensaio completo passou com pedido sintético PDV-260910-R58 (38,32s).
