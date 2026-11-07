# Peças compartilhadas do modo compacto (prévia)

`OperatorCompactSeal.vue`: o selo do app que leva à Central, com o chip de conexão.
`OperatorCompactBar.vue`: a linha única do celular. `apply-kit.mjs` copia as duas para o
operator-kit de uma cópia temporária, sem alterar nenhum componente existente.

Pendências conhecidas, achadas nas prévias:
- O ⋮ usa `NuxtDropdownMenu` e não escreve o motivo de uma ação desabilitada, que o
  `OperatorMoreMenu` escreve ("Impressora não configurada…"). O PDV contornou no aplicador
  dele. Se o compacto for adiante, o ⋮ deve reusar o `OperatorMoreMenu`.
- O chip não tem tom para leitura sob demanda (Compras).
- O sino do kit mede 32×32. Aqui ele é levado a 44px por um invólucro.
