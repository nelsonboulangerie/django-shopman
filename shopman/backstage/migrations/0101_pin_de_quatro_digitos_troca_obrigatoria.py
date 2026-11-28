"""Todo PIN que já existe passa a exigir troca no próximo uso (#3223).

O PIN da casa tem exatamente 4 dígitos (decisão do dono, 22/11/2026), e o teclado
envia sozinho no quarto dígito de quem tem a credencial de 4 fixos. O hash não
guarda o tamanho, então não há como saber quem já tem 4: toda credencial ativa
ganha a troca obrigatória (``must_change``). Quem tem PIN de 6 segue entrando
com o Confirmar, e a trava pede o PIN novo, de 4, antes de operar. Depois da troca
a credencial vira de 4 fixos (``services.operator.pin_digits``).

Credencial sem PIN (só crachá) não muda: não há PIN para trocar.
"""

from django.db import migrations


def force_pin_change(apps, schema_editor):
    PinCredential = apps.get_model("doorman", "PinCredential")
    PinCredential.objects.exclude(pin_hash="").update(must_change=True)


class Migration(migrations.Migration):
    dependencies = [
        ("backstage", "0100_refund_single_order_permission"),
        ("doorman", "0005_verificationcode_delivery_started_at"),
    ]

    operations = [
        # Sem volta: desfazer não devolveria a ninguém a certeza de que o PIN tem 4.
        migrations.RunPython(force_pin_change, migrations.RunPython.noop),
    ]
