# Gestor de pedidos: A (atual) × C (compacto)

Prévia. A = `origin/main` + `apply-conn-sim.mjs` (`?conn=live|calm|late|off`, aplicado igual
nos dois). C = A + `apply-compact.mjs` (âncoras que falham alto). `./run.sh` reproduz (mock
38920, A 4311, C 4312); `EVIDENCE=1 ./run.sh` refaz capturas e `evidence.json`.

## Medidas (cenário `normal`, topo do 1º cartão; cartões visíveis entre o topo e a barra inferior)

| | A | C (carga: faixa de atenção) | C (depois do Visto) |
|---|---|---|---|
| 320×568 | 190 px · 0,79 cartão | 182 px · 0,81 | 133 px · 0,93 |
| 375×667 | 190 px · 1,05 | 182 px · 1,07 | 133 px · 1,21 |
| alvos < 44 px no cabeçalho | 4 (☰, Visto, ⋯, sino: 32×32) | 0 | 0 |

Com o mesmo gesto (Visto) o A fica em 190 px: a linha "Filtros" e a de status são fixas.
Mesa (1440×900): A e C iguais (o C só muda abaixo do `md`).

## Três réguas → duas
A: <sm (barra do kit + linha "Filtros" + painel do kit), sm–md (barra do kit + chip
"Filtros" que abre o painel próprio da fila) e ≥md. C: <md é uma régua só (linha compacta,
um painel de filtros); ≥md intacto.

## Preservado
Abas Entrada/Preparo/Saída, cartões, Saída do próximo, barra de seleção, sinal do iFood,
aviso urgente, erro de leitura e de escrita (texto idêntico), mesmo painel de filtros
(Entrega/Retirada, canal, ordenar, ver como), as mesmas ações do ⋯, a busca da suíte.
Detalhe: voltar + código + estado + canal, ⋯ das ações e anterior/próximo.

## Melhorado
- Busca ativa visível: no A a 320 px, com o Visto na vaga do ícone, a busca desce para o
  ⋯ "Mais ações" (`operator-kit/app/presentation/pageHeader.ts:90`, revisado pela sessão-mãe) e o
  termo ativo não aparece em lugar nenhum (só a contagem da aba). No C: "Busca Maria.
  3 de 10 pedidos no quadro." + Limpar.
- Visto e Som bloqueado viram faixa explícita (uma linha, alvos 44 px) em vez de ícone
  de 32 px que tirava a busca do lugar.
- Sem conexão: chip no selo + faixa vermelha "Sem conexão. Última leitura às HH:MM.".

## Precisa de decisão
1. **Bloqueio (regra 7):** a barra inferior do Gestor não tem "Mais" (Pedidos, Saída,
   Ajustes; as demais seções são `where: rail`). Sem o ☰, o C perde no celular Histórico,
   Catálogo, Clientes, Canais e a troca de operador. Opções: "Mais" na barra, ou manter ☰.
2. Faixa de atenção custa 49 px enquanto há pedido novo (e na carga, até o 1º gesto,
   "Pedido novo. Som bloqueado."). Alternativa: Visto como botão na própria linha.
3. Leitura atrasada (`late`) fica só no chip do selo e no topo das Opções.
4. `?avisos=options`: o número de avisos (9+) some da tela.
5. "Ver como" abaixo do `lg` mostra só "Lista" (igual no A).

## Riscos a 320 px / pouca altura
Busca ativa + atenção + sem conexão empilham 3 faixas (topo do cartão até 270 px).
A busca do detalhe virou caixa com borda (destaque maior que o ⋯).

## O mock não cobre
Busca da suíte (o endpoint não responde: aparece "não respondeu"), SSE (204 → sempre
"a cada 30 s"), tempo real ao vivo, desconexão real (`navigator.onLine`), trilha do
anterior/próximo (carga direta não tem lista), Visto em outro dispositivo, permissões
de quem só expede, som de verdade. Horários "573h" vêm de fixtures antigas.

## Rodada desktop (`apply-desk.mjs` + `compact-kit/desk.css`)
A 1024 e 1280px, o A cortava o título ("Ped", "Pe") e a 1024px "Retirada" e o canal
saíam da linha dos recortes sem indício. No C: Urgência e Grade | Lista vão para o fim da
linha dos recortes (do `xl` para cima; abaixo seguem no ⋯, como no A), a linha quebra, e
a busca do centro é quem encolhe. Custo: a 1024px a busca fica em 119px ("Busc…" com o
atalho /). Alternativa a decidir: a maquininha virar ícone com número abaixo do `xl`.
