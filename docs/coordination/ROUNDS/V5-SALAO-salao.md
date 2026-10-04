# V5-SALAO: PDV › Ajustes › Salão

Frente da onda V4/V5 (04/10/2026). Branch `claude/v5-salao`. Prévia: `docs/plans/suite-ux-v2/v4/salao-mesas.jpg`
(fonte `docs/plans/suite-ux-v2/fontes/v4/salao-mesas4.html`). Fecha o item que o V4-PDV deixou de fora
("Ajustes › Salão: não entrou, e o que falta é dado").

## Decisão do dono
Construir Ajustes › Salão no PDV, igual à prévia. **Quem pode editar: o operador do PDV**
(`cashman.operate_pos`). **Toda mudança fica registrada**: quem, quando, o quê, antes e depois.

## O que entrou

**Modelo (`backstage.SeatingSpot`, migração `backstage.0083_seating_spot_plan`):** forma (`shape`:
redonda, quadrada, comprida, banqueta), posição na planta (`plan_x`, `plan_y`), giro (`rotation`, de 90
em 90), sigla na planta (`short_label`, "M1") e a versão anterior (`replaces`). A migração desenha o
lugar de balcão já cadastrado como banqueta. O seed põe a planta da Nelson (só em mesa sem posição:
rodar de novo não desfaz o desenho do operador).

**A regra de tempo (o B.I. não reescreve o passado):** o B.I. mede a lotação contando, em cada dia, as
mesas que existiam naquele dia e entram na capacidade oficial (`services/room.py::capacity_on`). Então:
- **desenho** (nome, sigla, área, forma, posição, giro) muda no lugar: o B.I. não lê;
- **medida** (lugares e "conta na capacidade oficial") muda por **versão**: a mesa de antes encerra ontem
  (`active_until`), a de hoje nasce hoje (`active_from`) com `replaces` apontando para a anterior. O
  "Existe desde" da tela atravessa as versões;
- mesa nascida hoje ainda não tem passado e muda no lugar até na medida;
- tirar do salão nunca apaga: encerra ontem.

**Registro:** o `LogEntry` do Admin (o mesmo histórico de `channel_switch` e `catalog_bindings`), uma
linha por mesa mudada, `change_message` JSON `{"action": "seating.spot.<add|change|version|remove>",
"ref", "before", "after", "replaces"?}`. O PDV mostra as últimas 30 em "… › Histórico do salão"; o Admin
mostra na história de cada mesa.

**API:** `GET/POST /api/v1/backstage/pos/seating/` (`api/seating.py`), permissão `cashman.operate_pos`.
Um salvar só: a planta inteira numa transação, com a revisão lida (outro dispositivo salvou no meio:
409 `seating_conflict`). Erro no dialeto `{detail, field, errors}` com o campo culpado
(`spots[2].seats`). Projeção `backstage/projections/seating.py`, registrada no `runtime-pos` de
`scripts/check_unfold_canonical.py`. Serviço `backstage/services/seating.py`.

**PDV (`surfaces/pos-nuxt`):** item **Ajustes** no pé do rail da suíte (e no fim da barra do polegar),
rota `/settings/seating`. Tela no visual v4 (camada `data-suite`, `OperatorPageHeader`, `OperatorSuiteRail`):
- computador: paleta (formas para arrastar ou tocar, áreas com contagem, "+ Área", legenda), planta em
  grade de 20px (áreas pelo contorno das mesas, cadeiras pelo número de lugares, extra tracejada, cantos e
  alça de girar, contorno de onde saiu e "arrastando M4"), painel da mesa (lugares, forma, área,
  capacidade, "Existe desde" com a regra, nota de comanda, nome e sigla, tirar do salão), rodapé com o total
  do B.I., a pílula das mudanças, Descartar e "Salvar salão (vale a partir de hoje; o passado não muda)";
- Desfazer/Refazer, zoom, "Encaixar na grade"; teclado: Ctrl S, Ctrl Z, Ctrl Shift Z, setas (Shift de 1 em
  1), Del, Esc; sair com mudança por salvar pergunta antes;
- tablet deitado: a paleta deita numa faixa acima da planta; tablet em pé: o painel desce para baixo da
  planta e só aparece com mesa escolhida;
- **celular: lista editável por área** (não a planta arrastável), o mesmo painel numa folha de baixo, total
  e Salvar presos acima da barra do polegar. A posição na planta se mexe no tablet ou no computador.

## Fora daqui (com nome e motivo)
- Abas Terminal, Impressoras, Maquininhas, Envio à cozinha e Atalhos de venda: não há cadastro delas no
  PDV. A linha de Ajustes mostra só o Salão (Terminal segue no pé do rail).
- "Vitrine e caixa" e "entrada" desenhadas na planta: decoração sem dado.
- "Mesa 4 tem comanda aberta agora": não há vínculo comanda e mesa (vetado no model, de propósito). A
  nota diz quantas comandas estão abertas e que mover mesa não mexe nelas.
- Pinça para zoom no tablet: zoom pelos botões.
- Tempo real (SSE) da planta: dois dispositivos editando ao mesmo tempo se protegem pela revisão (409), não
  por push.
