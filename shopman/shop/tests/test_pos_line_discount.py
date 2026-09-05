"""Per-line manual discount (POS numpad "Desc"): pricing, intent and gate.

Operator policy (decided 2026-05-30):
- promo vs manual on the same line → "maior desconto ganha" (best wins).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from shopman.backstage.projections import pos as pos_projection
from shopman.shop.modifiers import DiscountModifier
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import PosIntentError, parse_pos_sale_intent


class TestCalcManual:
    def test_percent_of_unit_price(self) -> None:
        # 10% of R$ 13,00 (1300) = 130
        assert DiscountModifier._calc_manual({"value": 10}, 1300) == 130

    def test_clamped_to_unit_price(self) -> None:
        assert DiscountModifier._calc_manual({"value": 200}, 1300) == 1300

    def test_zero_or_invalid_is_no_discount(self) -> None:
        assert DiscountModifier._calc_manual({"value": 0}, 1300) == 0
        assert DiscountModifier._calc_manual({"value": "abc"}, 1300) == 0
        assert DiscountModifier._calc_manual({}, 1300) == 0


class TestIntentPreservesLineDiscount:
    def test_discount_survives_parsing(self) -> None:
        intent = parse_pos_sale_intent(
            {
                "items": [
                    {"sku": "BAGUETE", "qty": 2, "unit_price_q": 1300,
                     "discount": {"value": 15, "reason": "fidelidade"}},
                ],
            },
            for_commit=True,
        )
        item = intent.payload["items"][0]
        assert item["discount"] == {"type": "percent", "value": 15.0, "reason": "fidelidade"}

    def test_percent_clamped_to_100(self) -> None:
        intent = parse_pos_sale_intent(
            {"items": [{"sku": "X", "qty": 1, "unit_price_q": 1000, "discount": {"value": 250}}]},
            for_commit=True,
        )
        assert intent.payload["items"][0]["discount"]["value"] == 100.0

    def test_no_discount_when_absent_or_zero(self) -> None:
        intent = parse_pos_sale_intent(
            {"items": [{"sku": "X", "qty": 1, "unit_price_q": 1000, "discount": {"value": 0}}]},
            for_commit=True,
        )
        assert "discount" not in intent.payload["items"][0]


class TestIntentPreservesLineIdentity:
    """O `line_id` é a identidade da linha, e ela nasce no cliente.

    Este parser copia campo a campo: o que ele não nomeia morre na porta. Sem o
    `line_id` aqui, o servidor regerava a identidade a cada save — duas linhas do
    mesmo SKU trocavam de dono e a comanda re-disparava para a cozinha no
    fechamento.
    """

    def test_line_id_survives_parsing(self) -> None:
        intent = parse_pos_sale_intent(
            {"items": [
                {"line_id": "L-AAA", "sku": "CHA", "qty": 1, "unit_price_q": 1400},
                {"line_id": "L-BBB", "sku": "CHA", "qty": 1, "unit_price_q": 1400},
            ]},
            for_commit=True,
        )
        assert [i["line_id"] for i in intent.payload["items"]] == ["L-AAA", "L-BBB"]

    def test_sem_line_id_o_kernel_gera(self) -> None:
        intent = parse_pos_sale_intent(
            {"items": [{"sku": "CHA", "qty": 1, "unit_price_q": 1400}]}, for_commit=True
        )
        assert "line_id" not in intent.payload["items"][0]

    def test_duas_linhas_com_a_mesma_identidade_sao_recusadas(self) -> None:
        """Repetido não é ambíguo: uma das duas SOME.

        O `_persist_items` do kernel indexa por `line_id` — duas linhas com o
        mesmo id viram uma só, sem erro, e o item comido não é cobrado nem feito.
        """
        with pytest.raises(PosIntentError) as exc:
            parse_pos_sale_intent(
                {"items": [
                    {"line_id": "L-AAA", "sku": "CHA", "qty": 1, "unit_price_q": 1400},
                    {"line_id": "L-AAA", "sku": "CAFE", "qty": 1, "unit_price_q": 900},
                ]},
                for_commit=True,
            )
        assert exc.value.code == "duplicate_line_id"


class TestPayloadDiscountHelpers:
    def test_line_discounts_sum_per_unit_times_qty(self) -> None:
        payload = {"items": [
            {"sku": "A", "qty": 2, "unit_price_q": 1300, "discount": {"value": 10}},  # 130 * 2
            {"sku": "B", "qty": 1, "unit_price_q": 800},                               # no discount
        ]}
        assert pos_service._payload_line_discounts_q(payload) == 260

@pytest.mark.django_db
class TestBuildSessionOpsStampsDiscount:
    def test_stamps_manual_discount_meta_with_approved_by(self) -> None:
        payload = {
            "items": [{"sku": "BAGUETE", "name": "Baguete", "qty": 1, "unit_price_q": 1300,
                       "discount": {"type": "percent", "value": 10, "reason": "cortesia"}}],
        }
        ops = pos_service.build_session_ops(payload, operator_username="op", approved_by="gerente")
        add_line = next(op for op in ops if op["op"] == "add_line" and op["sku"] == "BAGUETE")
        assert add_line["meta"]["manual_discount"]["value"] == 10
        assert add_line["meta"]["manual_discount"]["reason"] == "cortesia"
        assert add_line["meta"]["manual_discount"]["approved_by"] == "gerente"

    def test_o_corpo_sozinho_nao_assina_nada(self) -> None:
        """⚠️ Era assim que a Joyce aprovava um desconto que nunca viu.

        O validador retorna cedo quando nada exige desafio, mas a construção lia
        ``manager_approval.username`` do corpo INCONDICIONALMENTE. Um payload montado à
        mão — ou uma tela com o campo do gerente preenchido e o PIN limpo — gravava a
        assinatura dela no pedido. Como o nome do corpo coincide com o verificado
        quando HÁ desafio, o defeito era invisível nos testes.
        """
        payload = {
            "items": [{"sku": "BAGUETE", "name": "Baguete", "qty": 1, "unit_price_q": 1300,
                       "discount": {"type": "percent", "value": 10, "reason": "cortesia"}}],
            "manager_approval": {"username": "joyce", "pin": ""},
        }
        ops = pos_service.build_session_ops(payload, operator_username="op")
        add_line = next(op for op in ops if op["op"] == "add_line" and op["sku"] == "BAGUETE")
        assert "approved_by" not in add_line["meta"]["manual_discount"]

    def test_no_meta_discount_without_line_discount(self) -> None:
        payload = {"items": [{"sku": "BAGUETE", "name": "Baguete", "qty": 1, "unit_price_q": 1300}]}
        ops = pos_service.build_session_ops(payload, operator_username="op")
        add_line = next(op for op in ops if op["op"] == "add_line" and op["sku"] == "BAGUETE")
        assert "manual_discount" not in (add_line.get("meta") or {})


@pytest.mark.django_db
class TestManagerApprovalGate:
    def test_plain_line_discount_below_threshold_passes(self) -> None:
        # Default threshold is 0 (no approval); a plain line discount does not gate.
        payload = {
            "items": [{"sku": "BAGUETE", "qty": 1, "unit_price_q": 1300, "discount": {"value": 10}}],
        }
        # Must not raise.
        pos_service.validate_manager_approval(payload, operator_username="op")


@pytest.mark.django_db
class TestTabPayloadRestore:
    def test_line_discount_surfaced_for_restore(self) -> None:
        item = {"sku": "X", "meta": {"manual_discount": {"value": 10, "reason": "cortesia"}}}
        assert pos_projection._tab_payload_line_discount(item) == {
            "value": 10,
            "reason": "cortesia",
            "type": "percent",
        }

    def test_restore_devolve_o_formato_em_reais(self) -> None:
        # Sem o `type` de volta, uma comanda salva com R$ 2,00 de cortesia voltava
        # do banco como 2% — o campo estava gravado, e era a projection que o
        # deixava para trás.
        item = {
            "sku": "X",
            "meta": {"manual_discount": {"value": 2.0, "reason": "qualidade", "type": "fixed"}},
        }
        assert pos_projection._tab_payload_line_discount(item) == {
            "value": 2.0,
            "reason": "qualidade",
            "type": "fixed",
        }

    def test_no_discount_returns_none(self) -> None:
        assert pos_projection._tab_payload_line_discount({"sku": "X", "meta": {}}) is None

    def test_display_price_uses_pre_discount_when_manual_applied(self) -> None:
        # After the modifier ran, unit_price_q is discounted; the reload restores the
        # base price from session.pricing (NOT from the item's modifiers_applied,
        # which is stripped on save) so the descriptor is not double-applied (B1-3).
        item = {
            "line_id": "L-1",
            "sku": "X",
            "unit_price_q": 1170,  # 1300 - 10%
            "meta": {"manual_discount": {"value": 10, "reason": "cortesia"}},
        }
        originals = {"L-1": 1300}
        assert pos_projection._tab_line_display_price_q(item, originals) == 1300

    def test_duas_linhas_do_mesmo_sku_restauram_precos_proprios(self) -> None:
        """A cortesia dada numa linha não vaza para a outra do mesmo produto.

        Enquanto o registro de desconto era chaveado por SKU, o da segunda linha
        sobrescrevia o da primeira: a linha SEM desconto voltava do banco com o
        preço pré-desconto da outra, e a com desconto voltava sem.
        """
        cortesia = {
            "line_id": "L-1", "sku": "X", "unit_price_q": 1170,
            "meta": {"manual_discount": {"value": 10, "reason": "cortesia"}},
        }
        cheia = {"line_id": "L-2", "sku": "X", "unit_price_q": 1300, "meta": {}}
        originals = {"L-1": 1300}
        assert pos_projection._tab_line_display_price_q(cortesia, originals) == 1300
        assert pos_projection._tab_line_display_price_q(cheia, originals) == 1300

    def test_display_price_falls_back_when_no_pricing_record(self) -> None:
        # No surviving pricing record → fall back to the stored (baked) unit price
        # rather than guessing; the descriptor path only triggers with an original.
        item = {"line_id": "L-1", "sku": "X", "unit_price_q": 1170, "meta": {"manual_discount": {"value": 10}}}
        assert pos_projection._tab_line_display_price_q(item, {}) == 1170

    def test_display_price_falls_back_to_unit_price(self) -> None:
        item = {"sku": "X", "unit_price_q": 1300, "meta": {}}
        assert pos_projection._tab_line_display_price_q(item, {}) == 1300

    def test_manual_originals_map_from_session_pricing(self) -> None:
        # The surviving source: session.pricing["discount"]["items"]. Only manual
        # records with an original price map; promotion/coupon records are ignored
        # (their baked price is repriced on commit, not restored here). A chave é
        # a LINHA: duas linhas do mesmo SKU têm descontos independentes.
        session = SimpleNamespace(pricing={"discount": {"items": [
            {"line_id": "L-1", "sku": "X", "type": "manual", "original_price_q": 1300, "discount_q": 1170, "qty": 1},
            {"line_id": "L-2", "sku": "Y", "type": "promotion", "original_price_q": 900, "discount_q": 90, "qty": 1},
            {"line_id": "", "sku": "", "type": "coupon", "original_price_q": 0, "discount_q": 500, "qty": 1},
        ]}})
        assert pos_projection._manual_discount_originals(session) == {"L-1": 1300}

    def test_manual_originals_map_empty_without_pricing(self) -> None:
        assert pos_projection._manual_discount_originals(SimpleNamespace(pricing=None)) == {}


@pytest.mark.django_db
class TestManualDiscountWithoutPromotions:
    """A cortesia do operador não pode depender de haver campanha no ar.

    ⚠️ O defeito, medido com número: numa padaria sem promoção ativa — o caso
    comum —, 50% de cortesia num item de R$ 12,00 fechava a venda cobrando
    R$ 12,00. O `DiscountModifier` saía cedo quando não havia promoção nem
    cupom, e o laço que avalia o desconto manual vinha DEPOIS dessa saída. O
    desconto ficava gravado na linha (`meta.manual_discount`), a tela o exibia,
    e o caixa cobrava integral. Cortesia prometida ao cliente e não dada.
    """

    class _Session:
        """O mínimo de sessão que o modifier toca: itens, data, pricing e a
        escrita de volta."""

        def __init__(self, item):
            self.items = [item]
            self.data: dict = {}
            self.pricing: dict = {}

        def update_items(self, items):
            self.items = items

    def _session(self, *, discount):
        item = {"sku": "PAO", "qty": 1, "unit_price_q": 1200, "line_total_q": 1200, "meta": {"_list_q": 1200}}
        if discount:
            item["meta"]["manual_discount"] = discount
        return self._Session(item)

    def _apply(self, session):
        DiscountModifier().apply(channel=SimpleNamespace(ref="pdv"), session=session, ctx={})
        return session.items[0]

    def test_a_cortesia_vale_sem_promocao_nenhuma_no_ar(self) -> None:
        linha = self._apply(self._session(discount={"value": 50, "reason": "cortesia", "type": "percent"}))
        assert linha["unit_price_q"] == 600
        assert linha["line_total_q"] == 600

    def test_em_reais_tambem(self) -> None:
        linha = self._apply(self._session(discount={"value": 2.0, "reason": "qualidade", "type": "fixed"}))
        assert linha["unit_price_q"] == 1000

    def test_cortesia_sozinha_nao_paga_a_consulta_da_promocao(self, monkeypatch) -> None:
        # A busca de coleções por SKU serve só ao casamento de promoção/cupom.
        # Sem campanha no ar, a comanda com cortesia não pode pagar essa ida ao
        # banco — e o reprice roda a cada toque no carrinho.
        from shopman.shop.projections import catalog_context

        chamadas = []
        monkeypatch.setattr(
            catalog_context, "collection_refs_by_sku",
            lambda skus: chamadas.append(skus) or {},
        )
        self._apply(self._session(discount={"value": 50, "reason": "cortesia", "type": "percent"}))
        assert chamadas == []

    def test_sem_desconto_nenhum_a_saida_antecipada_continua_limpando(self) -> None:
        # A saída existe para não deixar pricing velho de pé; ela só não pode
        # atropelar o manual.
        session = self._session(discount=None)
        session.pricing = {"discount": {"items": [{"sku": "VELHO"}]}, "coupon": {"code": "X"}}
        self._apply(session)
        assert "discount" not in session.pricing
        assert "coupon" not in session.pricing


class TestReversePriorPricingIsPerLine:
    """Reverter o desconto de UMA linha não pode apagar o registro da irmã.

    ⚠️ `_apply_flat_best_wins` (funcionário, happy hour) e o desconto de lote
    chamam `_reverse_prior_pricing` e NÃO reescrevem o bloco de desconto depois.
    Com o filtro por `(sku, type)`, duas linhas do mesmo produto com cortesia e
    um desconto flat vencendo só uma apagavam os dois registros. A linha que
    manteve a cortesia ficava com ela no preço e sem `original_price_q` na
    transparência — e é dele que a projection tira o preço de lista. Sem ele, a
    tela devolvia o preço JÁ descontado como lista, e a gravação seguinte
    aplicava a cortesia por cima. Composto a cada reprice.
    """

    def _pricing(self):
        return {
            "discount": {
                "items": [
                    {"line_id": "L-1", "sku": "PAO", "type": "manual", "original_price_q": 1200,
                     "discount_q": 120, "qty": 1},
                    {"line_id": "L-2", "sku": "PAO", "type": "manual", "original_price_q": 1200,
                     "discount_q": 120, "qty": 1},
                ],
                "total_discount_q": 240,
            }
        }

    def test_a_irma_do_mesmo_sku_mantem_o_registro(self) -> None:
        from shopman.shop.modifiers import _reverse_prior_pricing

        pricing = self._pricing()
        linha = {"line_id": "L-2", "sku": "PAO", "qty": 1,
                 "meta": {"_disc": {"type": "manual", "amount_q": 120, "label": "cortesia"}}}
        _reverse_prior_pricing(pricing, linha)

        restantes = pricing["discount"]["items"]
        assert [d["line_id"] for d in restantes] == ["L-1"]
        assert pricing["discount"]["total_discount_q"] == 120

    def test_registro_sem_line_id_ainda_e_alcancado_pelo_sku(self) -> None:
        # Order-level e registros de outra origem não têm identidade de linha; o
        # SKU segue sendo a chave deles.
        from shopman.shop.modifiers import _reverse_prior_pricing

        pricing = {"discount": {"items": [
            {"sku": "PAO", "type": "manual", "discount_q": 120, "qty": 1},
        ], "total_discount_q": 120}}
        linha = {"sku": "PAO", "qty": 1,
                 "meta": {"_disc": {"type": "manual", "amount_q": 120, "label": "cortesia"}}}
        _reverse_prior_pricing(pricing, linha)

        assert pricing["discount"]["items"] == []


@pytest.mark.django_db
class TestManualDiscountThroughTheRealChain:
    """A comanda sai mais barata — dirigindo o kernel, não um dublê.

    A classe acima prova a decisão dentro do modifier; esta prova o RESULTADO
    que o operador vê, atravessando `ModifyService.modify_session` com produto,
    canal e sessão de verdade. Os casos de arbitragem só existem aqui: eles
    precisam de promoção no banco para disputar a linha.

    Casos 2 a 5 vieram da sessão irmã que investigou o mesmo defeito em paralelo
    (worktree eloquent-grothendieck-1945b1) — adaptados, porque nesta árvore os
    registros de desconto carregam `line_id`.
    """

    SKU = "CORTESIA-SKU"

    @pytest.fixture(autouse=True)
    def _catalogo(self):
        from django.core.cache import cache
        from shopman.offerman.models import Product

        from shopman.shop.models import Channel

        cache.clear()
        Channel.objects.get_or_create(ref="pdv", defaults={"name": "PDV", "is_active": True})
        Product.objects.create(
            sku=self.SKU, name="Pão da cortesia", base_price_q=1000,
            is_published=True, is_sellable=True,
        )
        yield
        cache.clear()

    def _lancar(self, *, discount: dict | None = None, qty: int = 1):
        from shopman.orderman.ids import generate_session_key
        from shopman.orderman.models import Session
        from shopman.orderman.services.modify import ModifyService

        key = generate_session_key()
        Session.objects.create(
            session_key=key, channel_ref="pdv", state="open",
            pricing_policy="fixed", edit_policy="open",
            data={"origin_channel": "pdv"},
        )
        linha = {"op": "add_line", "sku": self.SKU, "qty": qty, "unit_price_q": 1000}
        if discount is not None:
            linha["meta"] = {"manual_discount": discount}
        session = ModifyService.modify_session(session_key=key, channel_ref="pdv", ops=[linha])
        return session, next(i for i in session.items if i.get("sku") == self.SKU)

    def _promocao(self, **overrides):
        """Uma promoção qualquer, ativa — a muleta que mascarava o defeito."""
        from datetime import timedelta

        from django.utils import timezone

        from shopman.shop.models import Promotion

        agora = timezone.now()
        campos = {
            "ref": "promo-de-fundo", "name": "Promo de fundo",
            "type": Promotion.PERCENT, "value": 5, "is_active": True,
            "skus": ["OUTRO-SKU"],  # não alcança a linha sob teste
            "valid_from": agora - timedelta(days=1),
            "valid_until": agora + timedelta(days=1),
        }
        campos.update(overrides)
        return Promotion.objects.create(**campos)

    def test_cada_unidade_da_linha_e_descontada(self) -> None:
        # qty > 1 é onde um rateio errado aparece: o unitário pode estar certo e
        # o total da linha não.
        _, item = self._lancar(discount={"type": "percent", "value": 10}, qty=3)
        assert item["unit_price_q"] == 900
        assert item["line_total_q"] == 2700

    def test_a_promocao_de_fundo_nao_muda_mais_o_resultado(self) -> None:
        """O sintoma exato, em forma de asserção.

        A promoção está escopada em OUTRO SKU: ela não toca esta linha, e sua
        única influência era impedir a saída antecipada. Antes do conserto, os
        dois lados divergiam — 1000 sem ela, 900 com ela. Ligar uma promoção
        "consertava" o desconto, e ela vencer à meia-noite quebrava de novo.
        """
        _, sem_promo = self._lancar(discount={"type": "percent", "value": 10})
        self._promocao()
        _, com_promo = self._lancar(discount={"type": "percent", "value": 10})
        assert sem_promo["unit_price_q"] == com_promo["unit_price_q"] == 900

    def test_a_promocao_maior_vence_a_cortesia(self) -> None:
        self._promocao(value=30, skus=[self.SKU])
        _, item = self._lancar(discount={"type": "percent", "value": 10})
        assert item["unit_price_q"] == 700  # os 30% da promo, não os 10% do manual

    def test_a_cortesia_maior_vence_a_promocao_sem_compor(self) -> None:
        # ⚠️ 600, e NÃO 570. Os 40% valem sobre a ETIQUETA; 570 seria o manual
        # aplicado sobre os 950 que a promoção já tinha deixado — composição, que
        # é a dívida que a auditoria de stacking fechou. Este teste passa dos dois
        # lados do conserto de propósito: ele não prova o conserto, ele guarda
        # contra o conserto passar do ponto.
        self._promocao(value=5, skus=[self.SKU])
        _, item = self._lancar(discount={"type": "percent", "value": 40})
        assert item["unit_price_q"] == 600

    def test_cortesia_zerada_nao_reabre_o_portao(self) -> None:
        # `value: 0` é "sem desconto" (o intent nem grava). Não pode custar o
        # caminho longo nem deixar um `pricing["discount"]` vazio para trás.
        session, item = self._lancar(discount={"type": "percent", "value": 0})
        assert item["unit_price_q"] == 1000
        assert "discount" not in (session.pricing or {})

    def test_o_registro_diz_de_QUE_LINHA_e(self) -> None:
        # É deste registro que a projection tira o preço de lista para reabrir a
        # comanda; com ele chaveado por SKU, duas linhas do mesmo produto se
        # confundiam. Ver `TestReversePriorPricingIsPerLine`.
        session, item = self._lancar(discount={"type": "percent", "value": 10, "reason": "cortesia"})
        registro = session.pricing["discount"]["items"][0]
        assert registro["line_id"] == item["line_id"]
        assert registro["original_price_q"] == 1000
        assert pos_projection._manual_discount_originals(session) == {item["line_id"]: 1000}
