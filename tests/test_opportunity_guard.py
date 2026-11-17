import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from src.services.opportunity_guard import (
    NOT_OPPORTUNITY,
    UNKNOWN_CLOSING_TIME,
    opportunity_gate,
)


NOW = datetime(2026, 11, 16, 21, 11, tzinfo=ZoneInfo('America/Sao_Paulo'))


def edital(title='Chamada para submissao de projetos', due='2026-11-20', **extra):
    return {
        'titulo': title, 'resumo': 'Submissoes abertas para pesquisadores',
        'status': 'novo', 'data_abertura': '2026-11-01',
        'data_expiracao': due, **extra,
    }


class TestOpportunityGuard(unittest.TestCase):
    def test_finalistas_premio_bloqueio_definitivo(self):
        allowed, reason, definitive = opportunity_gate(
            edital('Divulgados os finalistas da 5ª edição do Prêmio CONFAP', '2026-11-30'), NOW)
        self.assertFalse(allowed)
        self.assertEqual(reason, NOT_OPPORTUNITY)
        self.assertTrue(definitive)

    def test_resultados_e_homologacoes_sao_bloqueados(self):
        for title in ('Resultado final de bolsa', 'Homologação dos selecionados',
                      'Lista de aprovados no processo seletivo', 'Vencedores da chamada'):
            with self.subTest(title=title):
                self.assertFalse(opportunity_gate(edital(title), NOW)[0])

    def test_premiacao_com_inscricoes_abertas_tambem_nao_entra(self):
        self.assertFalse(opportunity_gate(edital('Prêmio de inovação: inscrições abertas'), NOW)[0])

    def test_oportunidade_vigente_e_publicavel(self):
        self.assertTrue(opportunity_gate(edital(), NOW)[0])

    def test_sem_hora_oficial_bloqueia_publicacao_no_dia_final(self):
        self.assertEqual(opportunity_gate(edital(due='2026-11-16'), NOW),
                         (False, UNKNOWN_CLOSING_TIME, False))

    def test_encerramento_com_fuso_exato(self):
        self.assertFalse(opportunity_gate(edital(due='2026-11-16T15:00:00+01:00'), NOW)[0])
        self.assertTrue(opportunity_gate(edital(due='2026-11-16T23:30:00-03:00'), NOW)[0])

    def test_inscricoes_futuras_nao_sao_publicadas(self):
        self.assertFalse(opportunity_gate(edital(data_abertura='2026-11-18'), NOW)[0])

    def test_sem_prazo_exige_verificacao(self):
        allowed, _, definitive = opportunity_gate(edital(due=None), NOW)
        self.assertFalse(allowed)
        self.assertFalse(definitive)

    def test_texto_de_pesquisa_com_resultados_esperados_e_valido(self):
        self.assertTrue(opportunity_gate(
            edital(resumo='A proposta deve indicar os resultados esperados'), NOW)[0])

    def test_prazo_encerrado_explicito_no_resumo_e_bloqueado(self):
        self.assertFalse(opportunity_gate(
            edital(resumo='Inscrições encerradas às 12h'), NOW)[0])


if __name__ == '__main__':
    unittest.main()
