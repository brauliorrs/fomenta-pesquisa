import logging
import unittest
from types import SimpleNamespace
from unittest.mock import patch


from src.services.deadline_audit_service import DeadlineAuditService
from src.services.scraper_service import ScraperService
from src.services.normalize_service import NormalizeService
from src.services.render_service import RenderService
from src.services.deadline_evidence import (
    assess_deadline, extract_registration_deadlines, parse_date_token,
)


def item(id, due=None, ready=False):
    return {
        'id': id, 'titulo': f'Edital {id}/2026 de fomento',
        'fonte': 'FAP', 'link': f'https://fap.org.br/editais/{id}',
        'data_expiracao': due, 'pronto_para_postagem': ready,
        'status': 'novo', 'bloqueio_editorial_definitivo': False,
    }


class EvidenceTests(unittest.TestCase):
    def test_data_do_evento_e_resultado_nao_sao_inscricao(self):
        raw = ('Feira de ciencia: realizada em 26/11/2026.\n'
               'Resultado e divulgado em 27/11/2026.\n'
               'Prazo de contratacao dos aprovados: 30/11/2026.')
        self.assertEqual(extract_registration_deadlines(raw), [])

    def test_uso_da_ultima_data_da_pagina_nao_e_aceito(self):
        raw = ('Inscricoes de 01/11/2026 ate 18/11/2026\n'
               'Resultado: 25/11/2026\n'
               'Contratacao: 30/11/2026.')
        self.assertEqual(
            [x['data'] for x in extract_registration_deadlines(raw)],
            ['2026-11-18'],
        )

    def test_prazo_apos_rotulo_na_linha_seguinte(self):
        raw = 'Data-limite para submissao de propostas\n03/12/2026'
        self.assertEqual(
            [x['data'] for x in extract_registration_deadlines(raw)],
            ['2026-12-03'],
        )

    def test_documento_em_ingles_com_retificacao_tem_duas_datas(self):
        raw = ('Deadline for submission of full proposals: '
               'November 19, 2026 December 3, 2026')
        self.assertEqual(
            [x['data'] for x in extract_registration_deadlines(raw)],
            ['2026-11-19', '2026-12-03'],
        )
        row = assess_deadline(item('a', '2026-12-03'), raw,
                              '2026-11-26T09:00:00-03:00', 'https://fap.org.br')
        self.assertEqual(row['classificacao'], 'multiplos_prazos_revisao')

    def test_nao_inferir_ano_ausente(self):
        self.assertEqual(extract_registration_deadlines(
            'Inscricoes abertas ate 23 de marco.'), [])

    def test_candidato_recuperacao_nao_autoriza_publicar(self):
        record = assess_deadline(
            item('test'), 'Inscricoes ate 14 de dezembro de 2026',
            '2026-11-26T09:00:00-03:00', 'https://fap.org.br/editais/test',
        )
        self.assertEqual(record['classificacao'], 'possivel_recuperacao')
        self.assertEqual(record['datas_identificadas'], ['2026-12-14'])
        self.assertFalse(record['publicacao_autorizada_pela_auditoria'])

    def test_divergencia_independente_de_data_futura(self):
        record = assess_deadline(
            item('test', '2027-12-31'),
            'Inscricoes abertas ate 23 de marco de 2026',
            '2026-11-26T09:00:00-03:00', 'https://fap.org.br',
        )
        self.assertEqual(record['classificacao'], 'prazo_de_inscricao_ja_decorrido')

    def test_prazo_cadastrado_corroborado_so_com_contexto(self):
        record = assess_deadline(
            item('test', '2026-12-14'),
            'Data-limite para submissao de propostas: 14/12/2026',
            '2026-11-26T09:00:00-03:00', 'https://fap.org.br',
        )
        self.assertEqual(record['classificacao'], 'prazo_corroborado_por_trecho')

    def test_pdf_ou_html_nao_visitam_servidores_locais(self):
        audit = DeadlineAuditService(logging.getLogger('test'))
        for bad in ('http://127.0.0.1/admin', 'http://localhost/editais',
                    'https://user:password@site.com/editais',
                    'http://10.2.3.4/', 'file:///etc/passwd'):
            with self.subTest(url=bad):
                self.assertFalse(audit.safe_url(bad))

    def test_sweep_rotativo_todos_os_sem_prazo(self):
        called = []
        def fetch(url):
            called.append(url)
            return 'Inscricoes ate 14/12/2026', url, ''
        audit = DeadlineAuditService(logging.getLogger('test'), fetch)
        audit.MAX_READY = 2
        audit.MAX_MISSING = 3
        records = [item(f'{x:02d}') for x in range(7)]
        state = {}
        for i in range(3):
            state = audit.run(records, state, f'2026-11-{26+i:02d}T09:00:00-03:00')
        self.assertEqual(len(state['registros']), 7)
        self.assertEqual(len(set(called)), 7)
        self.assertEqual(state['sumario']['sem_prazo_elegiveis_para_auditoria'], 7)

    def test_auditoria_nao_altera_os_editais_originais(self):
        edital = item('a', None)
        original = edital.copy()
        audit = DeadlineAuditService(
            logging.getLogger('test'),
            lambda url: ('Inscricoes ate 14/12/2026', url, ''),
        )
        audit.run([edital], {}, '2026-11-26T09:00:00-03:00')
        self.assertEqual(edital, original)


    def test_integracao_scraper_nao_adota_ultima_data_da_pagina(self):
        service = ScraperService(
            logging.getLogger('test-scraper'), NormalizeService(), RenderService(),
        )
        response = SimpleNamespace(
            url='https://fap.org.br/noticias/feira',
            headers={'content-type': 'text/html'},
            text='<main><p>Feira cientifica em 26/11/2026.</p>'
                 '<p>Prazo da contratacao: 30/11/2026.</p></main>',
        )
        with patch.object(service, '_request', return_value=response):
            edital = service._enrich_item(
                {'link': response.url, 'fonte': 'FAP', 'titulo': 'Feira cientifica'},
                '2026-11-26T09:00:00-03:00',
            )
        self.assertIsNone(edital.get('data_expiracao'))
        self.assertIsNone(edital.get('data_abertura'))

    def test_integracao_scraper_recupera_prazo_com_evidencia(self):
        service = ScraperService(
            logging.getLogger('test-scraper'), NormalizeService(), RenderService(),
        )
        response = SimpleNamespace(
            url='https://fap.org.br/editais/14',
            headers={'content-type': 'text/html'},
            text='<main><p>As inscricoes para a chamada estao abertas '
                 'ate 14/12/2026.</p><p>Resultado em 20/12/2026</p></main>',
        )
        with patch.object(service, '_request', return_value=response):
            edital = service._enrich_item(
                {'link': response.url, 'fonte': 'FAP', 'titulo': 'Chamada de pesquisa'},
                '2026-11-26T09:00:00-03:00',
            )
        self.assertEqual(edital['data_expiracao'], '2026-12-14')


if __name__ == '__main__':
    unittest.main()
