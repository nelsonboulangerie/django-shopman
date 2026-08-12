"""Geometria de rolo declarada pelo terminal (spec §D3 — impressão do recibo).

O default de 80mm mora no print CSS do PDV. Este teste cobre o caminho de quem
declara OUTRA coisa, e principalmente o que acontece quando declara errado:
config ignorada em silêncio é o pior dos mundos, porque a loja acha que
configurou e o papel sai cortado sem ninguém entender por quê.
"""

from __future__ import annotations

from django.test import TestCase

from shopman.backstage.models.cash_register import POSTerminal
from shopman.backstage.services.pos_terminal import printer_geometry, runtime_profile


def _printer_health(terminal):
    profile = runtime_profile(terminal)
    return next(component for component in profile.components if component.key == "printer")


class PrinterGeometryTests(TestCase):
    def test_nao_declarado_deixa_o_css_mandar(self):
        geometry = printer_geometry({})
        self.assertFalse(geometry.declared)
        self.assertEqual((geometry.roll_width_mm, geometry.margin_mm), (0, 0))
        self.assertEqual(geometry.problem, "")

    def test_rolo_de_80mm_reserva_4mm_de_cada_lado(self):
        # 576 dots a 203dpi = 72,07mm impressos em 80mm de papel.
        geometry = printer_geometry({"roll_width_mm": 80})
        self.assertTrue(geometry.declared)
        self.assertEqual((geometry.roll_width_mm, geometry.margin_mm), (80, 4))

    def test_rolo_de_58mm_reserva_5mm_e_nao_4mm(self):
        # A área imprimível não é proporcional: 384 dots = 48,13mm em 58mm de
        # papel. Regra de três daria 2,9mm e imprimiria fora do alcance.
        geometry = printer_geometry({"roll_width_mm": 58})
        self.assertEqual((geometry.roll_width_mm, geometry.margin_mm), (58, 5))

    def test_modelo_fora_do_padrao_declara_a_largura_de_impressao(self):
        geometry = printer_geometry({"roll_width_mm": 76, "print_width_mm": 63})
        self.assertEqual((geometry.roll_width_mm, geometry.margin_mm), (76, 7))

    def test_margem_arredonda_para_cima(self):
        # Sobra de 9mm: 4,5 por lado. Arredondar para baixo invadiria a faixa
        # que o cabeçote não alcança.
        geometry = printer_geometry({"roll_width_mm": 80, "print_width_mm": 71})
        self.assertEqual(geometry.margin_mm, 5)

    def test_aceita_json_frouxo(self):
        for raw in (80, "80", 80.0, " 80 "):
            with self.subTest(raw=raw):
                self.assertEqual(printer_geometry({"roll_width_mm": raw}).roll_width_mm, 80)

    def test_rolo_fora_do_padrao_sem_largura_de_impressao_e_problema(self):
        geometry = printer_geometry({"roll_width_mm": 76})
        self.assertFalse(geometry.declared)
        self.assertIn("print_width_mm", geometry.problem)

    def test_declaracao_invalida_nao_cai_calada_para_o_default(self):
        for raw in ("oitenta", -80, 0, 5, 500, True, 80.5):
            with self.subTest(raw=raw):
                geometry = printer_geometry({"roll_width_mm": raw})
                self.assertFalse(geometry.declared)
                self.assertTrue(geometry.problem, "declaração inválida precisa reclamar")

    def test_largura_de_impressao_maior_que_o_rolo_e_problema(self):
        geometry = printer_geometry({"roll_width_mm": 80, "print_width_mm": 90})
        self.assertFalse(geometry.declared)
        self.assertIn("largura de impressão", geometry.problem)


class TerminalProfileGeometryTests(TestCase):
    def setUp(self):
        self.terminal = POSTerminal.objects.create(ref="pdv-geometria", label="PDV geometria")

    def _set_printer(self, config):
        self.terminal.metadata = {"hardware": {"printer": config}}
        self.terminal.save(update_fields=["metadata"])

    def test_terminal_sem_hardware_nao_declara_geometria(self):
        profile = runtime_profile(self.terminal)
        self.assertEqual(profile.printer.roll_width_mm, 0)
        self.assertEqual(_printer_health(self.terminal).status, "absent")

    def test_terminal_declara_o_rolo_e_o_perfil_carrega(self):
        self._set_printer({"adapter": "driver", "roll_width_mm": 58})
        profile = runtime_profile(self.terminal)
        self.assertEqual((profile.printer.roll_width_mm, profile.printer.margin_mm), (58, 5))
        self.assertEqual(_printer_health(self.terminal).status, "ready")

    def test_declaracao_invalida_acende_a_saude_da_impressora(self):
        self._set_printer({"adapter": "driver", "roll_width_mm": 999})
        health = _printer_health(self.terminal)
        self.assertEqual(health.status, "warning")
        self.assertIn("inválida", health.message)
        self.assertEqual(runtime_profile(self.terminal).status, "warning")

    def test_impressora_desligada_nao_vira_alerta_por_geometria(self):
        # Periférico desligado é escolha da loja, não defeito — mesmo que a
        # geometria que sobrou no JSON esteja quebrada.
        self._set_printer({"enabled": False, "roll_width_mm": 999})
        self.assertEqual(_printer_health(self.terminal).status, "absent")


class POSProjectionGeometryTests(TestCase):
    def test_projection_expoe_a_geometria_do_terminal(self):
        from shopman.backstage.projections.pos import build_pos

        terminal = POSTerminal.objects.create(
            ref="pdv-projection",
            label="PDV projection",
            metadata={"hardware": {"printer": {"adapter": "driver", "roll_width_mm": 58}}},
        )
        projection = build_pos(terminal=terminal)
        self.assertEqual(projection.terminal_roll_width_mm, 58)
        self.assertEqual(projection.terminal_roll_margin_mm, 5)

    def test_projection_manda_zero_quando_o_terminal_cala(self):
        from shopman.backstage.projections.pos import build_pos

        terminal = POSTerminal.objects.create(ref="pdv-mudo", label="PDV mudo")
        projection = build_pos(terminal=terminal)
        self.assertEqual(projection.terminal_roll_width_mm, 0)
        self.assertEqual(projection.terminal_roll_margin_mm, 0)
