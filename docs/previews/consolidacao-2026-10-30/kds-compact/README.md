# Cozinha/KDS: modo compacto (C) contra o atual (A) e a prévia anterior (B)

Somente prévia. Nada em `surfaces/`, Core, backend ou kit do produto. Sem merge nem deploy.

- **A**: `origin/main` `6fcef1c5` intacto. Só recebe `apply-conn-sim.mjs`, que força a
  entrada do indicador de conexão por `?conn=live|calm|late|off`. O mesmo ajuste vai em B e C.
- **B**: a prévia anterior (PR #2048, `kds-native/`), com os três aplicadores dela sem
  mudança: dismiss no canto, ⋮ do pedido na linha de contexto, fila a 320px, contorno de
  Agora, Filtro|Busca|Opções, aviso de Desfazer.
- **C**: B mais `apply-compact.mjs` e as peças de `../compact-kit/`.

Reprodução: `bash docs/previews/consolidacao-2026-10-30/kds-compact/run.sh`. Usa as portas
38898 (mock), 4291 (A), 4292 (B) e 4293 (C). Evidência: `node capture.mjs <node_modules> captures`.

## O que C muda (só no celular, abaixo de 768px)

1. **Uma linha no lugar de três.** Antes eram ☰ + título + lupa + ⋯ + sino, depois a linha
   "Atualiza sozinho a cada 15 s", depois a régua de ferramentas de B. Agora:
   selo da Cozinha (44px, leva à Central) com chip de conexão | Filtro · Busca · ⋮ | Avisos.
2. **Sem título e sem seletor de estação no topo.** A estação é a vaga ativa da barra
   inferior. O nome segue no `<h1>` acessível e no nome do grupo de ferramentas.
3. **Chip de conexão no canto do selo.** Cada estado tem forma e glifo: ✓ ao vivo,
   ↻ periódico, relógio para leitura atrasada, × sem conexão. O nome acessível do selo
   diz o estado e a hora da última leitura. A cadência ("Atualiza sozinho a cada 15 s.
   Lida às 12:14.") passa a ser a primeira linha das Opções. Sem conexão continua
   explícito no conteúdo, com a faixa "Sem conexão" que já existia.
4. **Avisos.** Por padrão é controle próprio, com o alvo levado a 44px (o sino do kit
   mede 32×32 hoje, inclusive em A). A variante `?avisos=options` põe Avisos dentro das
   Opções e abre a mesma caixa do kit ancorada no ⋮.
5. **Sem ☰.** A gaveta completa abre pelo "Mais", que a Cozinha sempre tem.
6. **Busca e filtro ativos.** Uma faixa logo abaixo da linha mostra "Busca 0138. 2 de 8
   na estação" com Limpar. O cabeçalho não rola, então a faixa nunca sai de vista.
7. **Desktop.** O título deixa de ser seletor de estação e vira texto, porque a lateral
   já lista as estações. As ferramentas ficam na linha principal, o modo "header" de B.
   O indicador de conexão (OperatorLiveStatus), a barra da estação e a hora ficam como
   estão.

Variante opcional `?aviso=denso`: o aviso da tela ocupa uma linha, com texto, Visto e
fechar. A descrição fica no DOM para o leitor de tela. Cor e ícone não mudam.

## Medidas (Playwright headless, tema escuro, aviso "8 pedidos novos" tocando)

Topo do rótulo "Agora" do card em foco e espaço entre ele e o botão Pronto:

| Viewport | A topo | B topo | C topo | A útil | B útil | C útil |
|---|---|---|---|---|---|---|
| 320×740 | 329 | 377 | 299 | 282 | 236 | 314 |
| 320×568 | 329 | 377 | 299 | 110 | 64 | 142 |
| 375×667 | 309 | 337 | 259 | 229 | 203 | 281 |
| 390×844 | 309 | 337 | 259 | 406 | 380 | 458 |
| 1440×900 | 359 | 417 | 359 | 150 | 150 | 150 |

Com `?aviso=denso`, medido no navegador a 320×568: o aviso tem 56px e o topo fica em
**153** (C sem a variante: 299). O card em foco aparece inteiro, com os itens.

No modo C a 320px, os alvos medem: selo 44×44, filtro 44×44, busca 114×44, ⋮ 44×44 e
Avisos 44×44. Não há rolagem horizontal em nenhum dos cinco tamanhos.

## Preservado

Ficaram iguais:
- TicketCard, fila, itens, notas, alergias, urgências, Mudou/cancelamento;
- Iniciar, Pronto e Desfazer com a janela nativa;
- a trava de armar, o histórico, os ajustes de som e tamanho, e a barra inferior com as
  posições fixas.

Também ficou tudo o que B já fazia, inclusive o contorno claro de Agora e o aviso
"Pronto pendente… ao sair, a confirmação será enviada e o Desfazer termina".

## Achados adversariais

- **Pouca altura:** a 320×568 o aviso de pedido novo (cerca de 175px com "e mais 1
  aviso") é o que mais rouba espaço, mais que o cabeçalho. Sem a variante densa, o card
  em foco mostra só o código. Fica para decisão.
- **Toque atrasado no Desfazer (existe em A, no produto):** quando a janela termina, o
  foco passa ao próximo pedido e o mesmo botão vira "Pronto <próximo>" já armado. A trava
  `KDS_ARM_DELAY_MS` (`[ref].vue:416-429`) só cobre Iniciar→Pronto do mesmo pedido.
  Aconteceu nesta revisão: um toque em "Desfazer 0131" marcou o 0138. A prévia não muda
  isso. Fica para decisão.
- **Avisos dentro das Opções** esconde a contagem de não lidos, porque o ⋮ não tem número.
  Só serve se o ⋮ ganhar a contagem; por isso o padrão de C é o controle próprio.
- **Desktop:** em B e C, o Filtro do grupo e os recortes "Todos/Entrega/Atrasados" da
  toolbar fazem o mesmo papel. Fica para decisão: tirar um dos dois na mesa.

## Fora da comprovação

O mock não serve Avisos ("Não foi possível atualizar os avisos" aparece nas três
variantes) nem a busca da suíte. Também ficaram de fora:
- SSE real, som em segundo plano, push e PWA instalado;
- troca real de app pela Central e login/trava;
- teclado virtual real.

A Central e os outros apps são destinos simulados.
