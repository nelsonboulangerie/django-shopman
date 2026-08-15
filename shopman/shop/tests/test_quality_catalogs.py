"""Catálogos de qualidade — a política que o core não conhece (ADR-017 §6).

O que estes testes protegem não é o CRUD: é a fronteira. O grau é o único eixo
de preço; o defeito é o único eixo de veto; e o percentual que o lote carrega é
um retrato, não um ponteiro para esta tabela.
"""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from shopman.shop.models import QualityDefect, QualityGrade

pytestmark = pytest.mark.django_db


class TestSeed:
    def test_a_escala_nasce_com_quatro_graus_ordenados(self):
        refs = list(QualityGrade.objects.order_by("-rank").values_list("ref", flat=True))
        assert refs == ["excellent", "standard", "fair", "minimal"]

    def test_o_padrao_e_standard(self):
        assert QualityGrade.objects.get(is_default=True).ref == "standard"

    def test_so_os_dois_de_baixo_descontam(self):
        by_ref = {g.ref: g.markdown_percent for g in QualityGrade.objects.all()}
        assert by_ref == {"excellent": 0, "standard": 0, "fair": 20, "minimal": 50}

    def test_o_catalogo_de_defeitos_e_um_2x2_mais_tres(self):
        refs = set(QualityDefect.objects.values_list("ref", flat=True))
        assert {"underproofed", "overproofed", "underbaked", "overbaked"} <= refs
        assert len(refs) == 7

    def test_todo_defeito_tem_sintoma(self):
        """Sem a dica, escolher pela causa vira adivinhação."""
        assert not QualityDefect.objects.filter(hint="").exists()

    def test_o_sintoma_abre_linha_com_maiuscula(self):
        """A dica é a segunda linha do botão de QC: abre linha, então sentence case
        (regra de copy). Confere que a 0018 reescreveu o que a 0013 semeou."""
        hints = dict(QualityDefect.objects.values_list("ref", "hint"))
        assert hints["underproofed"] == "Pequeno, denso, rasgou"
        assert all(hint[:1] == hint[:1].upper() for hint in hints.values())


class TestVeto:
    def test_so_contaminacao_veta(self):
        """Cosmético vende com desconto. Veto é só segurança alimentar."""
        vetoed = list(
            QualityDefect.objects.filter(forces_discard=True).values_list("ref", flat=True)
        )
        assert vetoed == ["contaminated"]

    def test_marcas_de_forno_nao_vetam(self):
        """Tentar limpar às vezes danifica: a decisão é de quem tem o pão na mão."""
        assert not QualityDefect.objects.get(ref="scorch_marks").forces_discard

    def test_defeito_com_veto_nao_pode_ser_desativado_por_descuido(self):
        defect = QualityDefect.objects.get(ref="contaminated")
        defect.is_active = False
        with pytest.raises(ValidationError):
            defect.full_clean()

    def test_defeito_nao_tem_percentual(self):
        """A ausência é o contrato: um eixo só para preço."""
        assert not hasattr(QualityDefect(), "markdown_percent")


class TestInvariantes:
    def test_dois_padroes_nao_convivem(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            QualityGrade.objects.create(
                ref="other", label="Outro", rank=99, is_default=True
            )

    def test_rank_e_unico(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            QualityGrade.objects.create(ref="other", label="Outro", rank=30)

    def test_percentual_acima_de_cem_e_recusado(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            QualityGrade.objects.create(
                ref="absurd", label="Absurdo", rank=5, markdown_percent=101
            )

    def test_rank_ordena_sem_depender_de_tupla_literal(self):
        """A hierarquia mora aqui agora — não mais duplicada em código."""
        grades = list(QualityGrade.objects.all())
        assert grades[0].ref == "excellent"
        assert grades[-1].ref == "minimal"
        assert all(
            grades[i].rank > grades[i + 1].rank for i in range(len(grades) - 1)
        )


class TestRotuloMudaCodigoFica:
    def test_trocar_rotulo_nao_toca_no_codigo(self):
        grade = QualityGrade.objects.get(ref="fair")
        grade.label = "Aceitável"
        grade.save()

        grade.refresh_from_db()
        assert grade.ref == "fair"
        assert grade.label == "Aceitável"

    def test_nada_em_qualitygrade_aponta_para_lote(self):
        """O lote carrega o número que recebeu; esta tabela é só a origem dele."""
        assert not any(
            f.is_relation for f in QualityGrade._meta.get_fields() if f.concrete
        )
