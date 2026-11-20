# #2827: o rodapé do assistente da encomenda a 375 px

Capturas do PDV de verdade (Django semeado e PDV compilado), com a Caixa (Fran) entrando
com PIN, a 375 px (celular) e 1280 px (balcão). `antes/` é o branch do #2828 (a base
deste PR); `depois/` é este PR. A cliente é a Maria Santos, a encomenda é para amanhã.

| Arquivo | O que mostra |
|---|---|
| `01-data-e-horario` | etapa 2, o rótulo mais longo ("Data e horário"), com Voltar e Continuar |
| `02-retirada-escolhida` | etapa 3, Retirada escolhida, com Voltar e "Montar encomenda" (a captura 03 do #2778) |

A mais representativa: `antes/375/02-retirada-escolhida.png` contra
`depois/375/02-retirada-escolhida.png`.

## A auditoria (`auditoria.txt`)

A 375 px, etapa 3, **antes**: a etapa em 3 linhas, "3 de 3" partido em 2 linhas, folga
até "Montar encomenda" de -0,5 px (encostado). **Depois**: a etapa numa linha própria,
1 linha, "3 de 3" inteiro, folga vertical de 13 px até Voltar e até o botão, Voltar e o
botão a 81 px um do outro, nada fora da tela, transbordo lateral 0.

A 1280 px, as duas etapas: posições, folgas e contraste iguais no antes e no depois (a
etapa numa linha só, entre Voltar e o botão).

Contraste nos dois tamanhos e nas duas fases: a etapa 6,09:1, Voltar 4,62:1, o botão
4,95:1.
