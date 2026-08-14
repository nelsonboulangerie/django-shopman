# Fechamento do dia e sobras (por lote)

Guia operacional e de sistema: **informe de não vendidos** às cegas e o destino
das sobras decidido pelo **LOTE** (validade + conformidade), sem posição
especial de véspera.

---

## Ideia central

1. **Listagem / canal** definem *o que pode ser ofertado*.
2. **Fechamento do dia** registra *quanto sobrou fisicamente* na loja, **sem depender** do fechamento automático de vendas no caixa (informe **às cegas** em relação ao ticket — ver abaixo).
3. **A sobra não se move.** O que decide o destino é o lote de cada quant:
   - lote **não conforme** → write-off imediato (`perda_nao_conformidade:<data>`);
   - lote **vencido** para a data do fechamento (ou produto do dia sem lote, `shelf_life_days == 0`) → write-off (`perda_vencido:<data>`);
   - lote **com validade** → **fica onde está**, como lote datado na própria vitrine. No dia seguinte, o gate de validade por canal (`expiry_margin_days`, `sells_nonconforming`) e o preço por lote (`percent_for_lot`) decidem o que cada canal oferece e por quanto.
4. Cada SKU fecha com uma **classificação**: `keep` (tudo fica), `expired` (tudo virou perda) ou `mixed` — o POS mostra "Fica / Parte vence / Vira perda".

---

## Informe “não vendidos” (às cegas)

- O operador informa, **SKU a SKU**, apenas a quantidade que **sobrou fisicamente**.
- A tela não exibe saldo disponível, destino, perda ou classificação interna. Isso evita viés na contagem.
- O sistema decide automaticamente o destino da sobra pelas regras de lote acima.
- Esse número **não é validado** contra somatório de vendas do PDV no mesmo passo: é uma **conferência física** (o que ainda está na loja ao fechar).
- **Por quê?** Porque na prática há diferenças (amostras, erro de caixa, furto, ajuste manual). A auditoria cruzada (produzido vs vendido vs informado) é **relatório**, não bloqueio automático do formulário.
- Se o informado for maior que o saldo conhecido, a movimentação física fica limitada ao saldo que o Stockman conhece, mas o snapshot registra `qty_reported`, `qty_applied` e `qty_discrepancy`. Divergência não é escondida.

Se no futuro o produto exigir **confirmação explícita** do tipo “revisei todas as linhas” antes de gravar, isso será um requisito de UX no assistente de fechamento — hoje o registro é o snapshot em `DayClosing`.

---

## Exemplo: sobraram 10 pães de forma

1. No fechamento, o operador informa **10** em “sobraram” para esse SKU.
2. O sistema olha os lotes desse saldo:
   - 3 unidades de um lote marcado não conforme → `perda_nao_conformidade:<data>`;
   - o produto tem `shelf_life_days == 1` e o lote de hoje vence amanhã → as 7 restantes **ficam** na vitrine como lote datado.
3. **No dia seguinte**: o canal remoto só oferece o lote se a margem de validade do canal permitir; o balcão vende com o desconto congelado no lote (`percent_for_lot`). O que vencer morre no próximo fechamento como `perda_vencido`.

---

## O que o código já faz

| Peça | Onde |
|------|------|
| Tela de fechamento | Antesala do PDV: `surfaces/pos-nuxt/app/pages/session/closing.vue` |
| API (GET/POST) | `shopman/backstage/api/operations.py` → `DayClosingView` (`/api/v1/backstage/closing/`) |
| Registro auditável | `DayClosing` (`date`, `closed_by`, `data` = snapshot por SKU com `qty_kept`, `qty_expired`, `qty_nonconforming`) |
| Write-off por lote | `shopman/backstage/services/closing.py::_write_off_lots` (WASTE com motivo auditável) |
| Classificação por SKU | `keep` / `expired` / `mixed` — derivada do snapshot, exibida no POS |

Permissão: `shop.add_dayclosing`.

---

## Roadmap / lacunas (produto)

- **Relatório** produzido vs vendido vs não vendido informado vs perda — base para auditoria sem substituir o informe às cegas.
- **Superfície operacional**: antesala do PDV (`pos.<zona>/session/closing`), consumindo `GET/POST /api/v1/backstage/closing/` (mesma projection `build_day_closing()` e mesmo service). A tela Admin/Unfold foi removida (ADMIN-ROLE-PLAN WP-ADM-3); `DayClosingAdmin` mantém auditoria e histórico readonly.

---

## Leitura relacionada

- [Stocking](stocking.md) — posições, quants, movimentos.
- [Lifecycle](lifecycle.md) — orquestração de pedidos (independente do fechamento físico).
- `docs/reference/data-schemas.md` — chaves em `Order.data` / sessão quando necessário cruzar com vendas.
