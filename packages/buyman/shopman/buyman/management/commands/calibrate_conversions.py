"""Lista as equivalências aproximadas que ninguém pesou, e grava a pesagem.

Usage::

    python manage.py calibrate_conversions                      # o que falta
    python manage.py calibrate_conversions --weigh OVOS:ovos=0.058 --apply

**Por que existe.** A ADR-024 separa três tipos de conversão, e o terceiro — a
equivalência **aproximada** — é o único que carrega incerteza: "1 ovo ≈ 50 g",
"1 limão ≈ 100 g", "1 folha de louro ≈ ?". O ``kind`` diz que a incerteza
existe; ele não diz **quanto** dela.

E isso tem consequência: até 24/09/2026 o ovo a 50 g e o limão a 100 g estavam no
banco exatamente como estaria um número que a casa tivesse pesado. Ninguém sabia
quais vieram de estimativa, e portanto ninguém sabia **qual calibrar primeiro**.
A procedência da salsicha estava escrita — em comentário do ``seed``, onde tela
nenhuma lê.

**O gesto que ele pediu.** Pesar dez folhas, dividir por dez, e o número entra
com carimbo de *pesado na casa*. A partir daí ele para de aparecer nesta lista,
e quem vier depois sabe que aquele fator não é chute de internet.

**O que este comando NÃO faz.** Não inventa fator, não converte nada e não toca
em conversão **convencionada**: "1 saco = 25 kg" é contrato do fornecedor, não
equivalência física — calibrar ali seria duvidar da nota.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Mostra as equivalências aproximadas por calibrar, e grava a pesagem da casa."

    def add_arguments(self, parser):
        parser.add_argument(
            "--weigh",
            action="append",
            default=[],
            metavar="SKU:rótulo=fator",
            help=(
                "A pesagem da casa, na unidade-base do insumo. "
                "Ex.: --weigh OVOS:ovos=0.058 (58 g por ovo). Repetível."
            ),
        )
        parser.add_argument(
            "--apply", action="store_true",
            help="Grava. Sem isto o comando só relata o que faria.",
        )

    def handle(self, *args, **options):
        from shopman.buyman.models import MaterialConversion

        pesagens = [self._ler(p) for p in options["weigh"]]
        apply = options["apply"]

        if pesagens:
            self._gravar(pesagens, apply=apply)

        pendentes = [
            c for c in MaterialConversion.objects.filter(is_active=True)
            .select_related("material").order_by("material__sku", "label")
            if c.needs_calibration
        ]
        self._relatorio(pendentes)

    def _ler(self, texto: str) -> tuple[str, str, Decimal]:
        try:
            alvo, fator = texto.rsplit("=", 1)
            sku, rotulo = alvo.split(":", 1)
            valor = Decimal(fator.strip())
        except (ValueError, InvalidOperation) as erro:
            raise CommandError(
                f"'{texto}' não tem a forma SKU:rótulo=fator (ex.: OVOS:ovos=0.058)."
            ) from erro
        if valor <= 0:
            raise CommandError(f"'{texto}': o fator precisa ser maior que zero.")
        return sku.strip(), rotulo.strip(), valor

    def _gravar(self, pesagens, *, apply: bool) -> None:
        from shopman.buyman.models import MaterialConversion

        with transaction.atomic():
            for sku, rotulo, fator in pesagens:
                conversao = MaterialConversion.objects.filter(
                    material__sku=sku, label=rotulo, is_active=True
                ).first()
                if conversao is None:
                    raise CommandError(
                        f"{sku}:{rotulo} não existe. Este comando calibra o que já está "
                        "cadastrado — criar equivalência é outro gesto, e ele declara o "
                        "rótulo que a bancada usa."
                    )
                if conversao.kind != MaterialConversion.Kind.APPROXIMATE:
                    raise CommandError(
                        f"{sku}:{rotulo} é convencionada, não aproximada. "
                        f"'{rotulo}' vem do contrato do fornecedor — calibrar ali seria "
                        "duvidar da nota, e o conserto é outro: corrigir a embalagem."
                    )
                antes = conversao.to_base_factor
                conversao.to_base_factor = fator
                conversao.source = MaterialConversion.Source.HOUSE_SCALE
                if apply:
                    conversao.save(update_fields=["to_base_factor", "source", "updated_at"])
                variacao = (fator - antes) / antes * 100 if antes else Decimal("0")
                self.stdout.write(self.style.SUCCESS(
                    f"  {'pesado' if apply else 'pesaria'}: {sku}:{rotulo} "
                    f"{antes} → {fator}  ({variacao:+.1f}%)"
                ))
            if not apply:
                transaction.set_rollback(True)

    def _relatorio(self, pendentes) -> None:
        out = self.stdout
        if not pendentes:
            out.write(self.style.SUCCESS(
                "\nNenhuma equivalência por calibrar: toda aproximação ativa diz de onde veio."
            ))
            return

        out.write(self.style.WARNING(
            f"\n{len(pendentes)} equivalência(s) aproximada(s) que ninguém pesou:"
        ))
        for c in pendentes:
            origem = "sem procedência declarada" if not c.source else c.get_source_display()
            out.write(
                f"  {c.material.sku:<26} 1 {c.label:<12} ≈ {c.to_base_factor} "
                f"{c.material.unit}   ({origem})"
            )
        out.write(
            "\nPara calibrar: pese DEZ e divida por dez — a média de dez folhas erra menos que\n"
            "a de uma, e é o que o fator representa. Depois:\n"
            f"  python manage.py calibrate_conversions --weigh {pendentes[0].material.sku}:"
            f"{pendentes[0].label}=<fator> --apply\n"
            "\nO fator entra carimbado como pesado na casa, sai desta lista, e quem vier depois\n"
            "sabe que ele não é chute."
        )
