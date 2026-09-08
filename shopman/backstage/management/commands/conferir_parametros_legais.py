"""Põe lado a lado o que o sistema ASSUME e o que a norma DIZ.

Quem tem a responsabilidade de cumprir a lei é o gestor, não o repositório. Este
comando existe para que a conferência seja um trabalho de minutos: ele mostra,
para cada parâmetro, de qual norma veio, o que o sistema assume hoje, quando
alguém conferiu pela última vez, e **o endereço para ler a norma**.

    python manage.py conferir_parametros_legais
    python manage.py conferir_parametros_legais --vencidos
    python manage.py conferir_parametros_legais --alertar

⚠️ **Ele não decide se a norma mudou.** Não existe fonte pública consultável que
responda isso para as normas que nos interessam — medido em 08/09/2026:

- o SRU do **LexML** (que modela revogação) está atrás de verificação anti-bot
  do Senado e não responde a chamada de servidor;
- o **dados abertos do Senado** responde JSON e serve para LEI FEDERAL (a
  10.674/2003 está lá), mas **não cobre RDC da ANVISA** — e três dos nossos
  quatro parâmetros são RDC.

Então a conferência é humana, e o papel do sistema é **não deixar ninguém
esquecer** e reduzir o trabalho ao clique. Automatizar a detecção de
substituição fica como passo seguinte, provavelmente com auxílio de IA lendo a
página da norma — está escrito no plano, não prometido aqui.
"""

from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand

from shopman.shop.legal_parameters import (
    JANELA_DE_REVISAO_DIAS,
    PARAMETROS,
    vencidos,
)


class Command(BaseCommand):
    help = "Confronta os parâmetros do sistema com as normas de onde vieram."

    def add_arguments(self, parser):
        parser.add_argument("--vencidos", action="store_true", help="Só os que passaram do prazo.")
        parser.add_argument(
            "--alertar", action="store_true",
            help="Cria OperatorAlert para o gestor quando houver vencido.",
        )

    def handle(self, *args, **opts):
        hoje = date.today()
        alvo = vencidos(hoje) if opts["vencidos"] else list(PARAMETROS)

        if not alvo:
            self.stdout.write(self.style.SUCCESS("Nenhum parâmetro vencido."))
            self.stdout.write(
                f"Todos conferidos há menos de {JANELA_DE_REVISAO_DIAS} dias. "
                "Rode sem `--vencidos` para ver a lista inteira."
            )
            return

        for p in alvo:
            idade = (hoje - p.conferido_em).days
            venceu = p.vencido_em(hoje)
            marca = self.style.ERROR("VENCIDO") if venceu else self.style.SUCCESS("em dia")

            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING(f"{p.chave}  [{marca}]"))
            self.stdout.write(f"  norma ......... {p.norma}")
            self.stdout.write(f"  o sistema usa . {p.valor}")
            self.stdout.write(f"  conferido ..... {p.conferido_em} por {p.conferido_por} ({idade} dias)")
            if p.fonte:
                self.stdout.write(f"  ler em ........ {p.fonte}")
            if p.urn:
                self.stdout.write(f"  urn ........... {p.urn}")
            if p.nota:
                for linha in _quebra(p.nota, 74):
                    self.stdout.write(f"  nota .......... {linha}" if linha == _quebra(p.nota, 74)[0]
                                      else f"                 {linha}")

        velhos = [p for p in alvo if p.vencido_em(hoje)]
        self.stdout.write("")
        if velhos:
            self.stdout.write(self.style.ERROR(f"{len(velhos)} parâmetro(s) precisam de conferência."))
            self.stdout.write(
                "Ao conferir: leia a norma, confirme (ou corrija) o valor e atualize "
                "`conferido_em`/`conferido_por` em `shopman/shop/legal_parameters.py`.\n"
                "⚠️ Mexer só na data sem ler é o defeito que esta rotina existe para impedir."
            )
            if opts["alertar"]:
                self._alertar(velhos)
        else:
            self.stdout.write(self.style.SUCCESS("Todos em dia."))

    def _alertar(self, velhos):
        """O lembrete tem de chegar a QUEM responde pela lei, não só ao CI.

        Teste vermelho é visto por quem programa. A obrigação é do gestor — então
        o vencimento vira alerta na superfície dele.
        """
        # ⚠️ Este comando mora no BACKSTAGE, e não é detalhe de arrumação: o
        # `shop` NÃO pode importar o `backstage` (regra de dependência do
        # CLAUDE.md, cobrada por `test_import_boundaries`). Quem lê os parâmetros
        # é o shop; quem ALERTA o gestor é o backstage — então o comando fica do
        # lado que pode enxergar os dois.
        from shopman.backstage.models import OperatorAlert
        from shopman.backstage.services.alerts import create_alert

        # ⚠️ Um alerta por vez, não um por dia. O worker roda a cada ciclo; sem
        # esta guarda o gestor receberia a mesma cobrança todo dia até conferir,
        # e alerta que se repete é alerta que se aprende a ignorar.
        ja_aberto = OperatorAlert.objects.filter(
            type="legal_parameter_stale", acknowledged=False
        ).exists()
        if ja_aberto:
            self.stdout.write("  (já há alerta aberto para o gestor; não repito)")
            return

        chaves = ", ".join(p.chave for p in velhos)
        create_alert(
            type="legal_parameter_stale",
            severity="warning",
            message=(
                f"{len(velhos)} parâmetro(s) baseados em lei sem conferência há mais de "
                f"{JANELA_DE_REVISAO_DIAS} dias: {chaves}. "
                "A legislação muda; parâmetro velho faz o sistema ensinar a errar. "
                "Rode `manage.py conferir_parametros_legais` para ver a norma e o link."
            ),
        )
        self.stdout.write(self.style.WARNING("  alerta criado para o gestor."))


def _quebra(texto: str, largura: int) -> list[str]:
    palavras, linhas, atual = texto.split(), [], ""
    for w in palavras:
        if len(atual) + len(w) + 1 > largura:
            linhas.append(atual)
            atual = w
        else:
            atual = f"{atual} {w}".strip()
    if atual:
        linhas.append(atual)
    return linhas or [""]
