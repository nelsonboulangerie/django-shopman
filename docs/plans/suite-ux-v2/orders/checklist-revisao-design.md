# Checklist de revisão de design — superfícies de operador

A matriz visual é um **piso de geometria** (toque, overflow), não a régua. "Verde no
teste" não é "bom no olho". Antes de declarar pronto, revisar **no olho**, claro e
escuro, desktop (1440) e mobile (390), com **antes/depois** capturado.

1. **Linha de controles alinhada** — botões, busca, selects e chips na MESMA altura.
   Medir no DOM, não estimar. Um contrato de altura por linha (ex.: 44 no header).
2. **Hierarquia** — um título claro; UMA ação primária por cartão; o resto no ⋯/detalhe.
3. **Espaçamento** — nada encostado; "⋯" com respiro (≥12px); chips com gap consistente;
   divisor com margem e escondido quando a linha quebra no celular.
4. **Bordas/separadores** — visíveis o bastante para delimitar (WCAG 1.4.11: **3:1**
   não-texto). Se o token não puder mudar agora, **registrar** com o valor medido.
5. **Estados inconfundíveis** — ativo / inativo / disabled / bloqueado diferem por
   **cor + forma + ícone**, não só por matiz.
6. **Texto** — nada truncado, nada colado entre título e chamada; copy sem prolixidade
   nem erro de língua ("pedem **por** você").
7. **Densidade no celular** — o cartão não compete consigo mesmo; cortar o que não muda
   a decisão do operador.
8. **Contraste** — texto AA; não-texto 3:1; nos DOIS temas.
9. **Consistência** — o vocabulário visual do kit; nenhum wrapper com escala própria
   (ex.: alturas paralelas).
10. **Antes/depois** — capturar as duas versões e comparar lado a lado.
