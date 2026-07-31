from __future__ import annotations

import unittest

from src.config import Settings
from src.models import Edital
from src.services.instagram_service import InstagramService
from src.services.render_service import RenderService


def build_edital(**overrides: object) -> Edital:
    payload: dict[str, object] = {
        "id": "facepe_global_pe",
        "titulo": "22/2026 -",
        "orgao": "Fundacao de Amparo a Ciencia e Tecnologia do Estado de Pernambuco",
        "fonte": "FACEPE",
        "uf": "PE",
        "categoria": "pesquisa",
        "link": "https://www.facepe.br/2026.07.15-Global-PE-Espanha-Ajustado.pdf",
        "resumo": "22/2026.",
        "publico_alvo": "Pesquisadores",
        "data_abertura": "2026-07-02",
        "data_expiracao": "2026-09-24",
        "data_ultima_coleta": "2026-07-31T00:00:00-03:00",
    }
    payload.update(overrides)
    return Edital(**payload)


class InstagramLayoutTests(unittest.TestCase):
    def test_facepe_link_title_removes_filename_markers(self) -> None:
        fields = RenderService().build_card_fields(build_edital())

        self.assertEqual(fields["card_title"], "Global PE Espanha")
        self.assertTrue(fields["card_summary"].startswith("Voltado a pesquisadores."))
        self.assertIn("Prazo final em 24/09/2026.", fields["card_summary"])

    def test_long_unbroken_title_stays_inside_card_width(self) -> None:
        service = InstagramService(Settings())
        max_width = service.FEED_WIDTH - 168
        lines, font = service._fit_title_layout(
            "Global-PE-Espanha-Ajustado-Sem-Espacos-Para-Testar",
            max_width=max_width,
            max_lines=4,
        )

        self.assertLessEqual(len(lines), 4)
        self.assertTrue(all(service._text_width(line, font) <= max_width for line in lines))


if __name__ == "__main__":
    unittest.main()
