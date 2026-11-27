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


    def test_recurso_administrativo_nao_conta_como_prazo_de_inscricao(self):
        raw = (
            '10.5 Prazo para recurso referente às propostas inelegíveis '
            'Até 2 (dois) dias úteis após a divulgação de elegibilidade; '
            '10.6 Divulgação final das propostas elegíveis '
            'A partir de 01 de dezembro de 2026;'
        )
        self.assertEqual(extract_registration_deadlines(raw), [])
        row = assess_deadline(
            item('fappr', '2026-11-30'), raw,
            '2026-11-26T19:00:00-03:00', 'https://fappr.pr.gov.br/cp20.pdf'
        )
        self.assertEqual(row['classificacao'], 'sem_evidencia_de_inscricao')

    def test_rodizio_sem_prazo_amostra_fontes_diversas(self):
        sampled_sources = []
        def fetch(url):
            sampled_sources.append(url.split('/')[-2])
            return '', url, ''
        audit = DeadlineAuditService(logging.getLogger('test'), fetch)
        audit.MAX_MISSING = 3
        registros = []
        for fonte in ('A', 'B', 'C'):
            for x in range(5):
                item_x = item(f'{fonte.lower()}-{x}')
                item_x['fonte'] = fonte
                item_x['link'] = f'https://fap.org.br/{fonte}/{x}'
                registros.append(item_x)
        report = audit.run(registros, {}, '2026-11-26T19:00:00-03:00')
        self.assertEqual(set(sampled_sources), {'A', 'B', 'C'})
        self.assertEqual(report['sumario']['fontes_distintas_sem_prazo_consultadas'], 3)

    def test_prazo_divergente_reavaliado_no_mesmo_dia(self):
        count = []
        def fetch(url):
            count.append(url)
            return ('Prazo de recurso referente às propostas elegíveis '
                    '01/12/2026', url, '')
        audit = DeadlineAuditService(logging.getLogger('test'), fetch)
        edital = item('fappr', '2026-11-30', True)
        old = {'registros': {
            'fappr': {
                'classificacao': 'prazo_divergente',
                'verificado_em': '2026-11-26T19:00:00-03:00',
            }
        }}
        report = audit.run([edital], old, '2026-11-26T19:15:00-03:00')
        self.assertEqual(len(count), 1)
        self.assertEqual(report['registros']['fappr']['classificacao'],
                         'sem_evidencia_de_inscricao')


    def test_inicio_do_prazo_nao_e_fim_da_submissao(self):
        texto = (
            'Início do prazo para submissão de propostas 13/07/2026\n'
            'Término do prazo para submissão de propostas (até às 17h) 09/11/2026'
        )
        self.assertEqual(
            [e['data'] for e in extract_registration_deadlines(texto)],
            ['2026-11-09'],
        )

    def test_avaliacao_de_inscricoes_nao_gera_prazo(self):
        texto = (
            'Encerramento das inscrições 20 de outubro de 2025\n'
            'Avaliação das inscrições pelo comitê de seleção 21 a 28 de outubro de 2025'
        )
        self.assertEqual(
            [e['data'] for e in extract_registration_deadlines(texto)],
            ['2025-10-20'],
        )

    def test_multiplas_datas_todas_passadas_nao_sao_ativas(self):
        texto = (
            'Prazo final de inscrições até 25 de janeiro de 2024\n'
            'Prazo final para submissão de propostas completas 4 de abril de 2024'
        )
        row = assess_deadline(
            item('serrapilheira'), texto, '2026-11-27T09:00:00-03:00',
            'https://serrapilheira.org/chamada',
        )
        self.assertEqual(row['classificacao'], 'prazo_de_inscricao_ja_decorrido')
        self.assertFalse(row['publicacao_autorizada_pela_auditoria'])

    def test_prio_dos_registros_que_ainda_nao_foram_visitados(self):
        vistos = []
        def fetch(url):
            vistos.append(url.split('/')[-1])
            return '', url, ''
        audit = DeadlineAuditService(logging.getLogger('test'), fetch)
        audit.MAX_MISSING = 2
        rows = [item(f'e{i}') for i in range(5)]
        prior = {'registros': {
            'e0': {'classificacao':'sem_evidencia_de_inscricao',
                   'link_cadastrado': rows[0]['link']},
            'e1': {'classificacao':'sem_evidencia_de_inscricao',
                   'link_cadastrado': rows[1]['link']},
        }}
        report = audit.run(rows, prior, '2026-11-27T09:00:00-03:00')
        self.assertEqual(len(vistos), 2)
        self.assertTrue(set(vistos).isdisjoint({'e0', 'e1'}))
        self.assertEqual(report['sumario']['consultados_nesta_execucao'], 2)

    def test_intervalo_explicito_ipea_tem_um_prazo_final(self):
        texto = 'Prazo de inscrição: 06/10/2026 a 19/10/2026'
        evidencias = extract_registration_deadlines(texto)
        self.assertEqual([x['data'] for x in evidencias], ['2026-10-19'])
        registro = assess_deadline(
            item('ipea'), texto, '2026-11-26T19:00:00-03:00',
            'https://ipea.gov.br/chamada-032',
        )
        self.assertEqual(registro['classificacao'], 'prazo_de_inscricao_ja_decorrido')

    def test_caso_ambiguo_sem_prazo_reavaliado_fora_do_rodizio(self):
        vistos = []
        def fetch(url):
            vistos.append(url)
            return 'Prazo de inscricao: 06/10/2026 a 19/10/2026', url, ''
        audit = DeadlineAuditService(logging.getLogger('test'), fetch)
        audit.MAX_MISSING = 1
        lista = [item('a'), item('b'), item('c')]
        old = {
            'cursor_sem_prazo': 0,
            'registros': {
                'c': {'classificacao': 'multiplos_prazos_revisao',
                      'verificado_em': '2026-11-26T19:00:00-03:00'},
            },
        }
        result = audit.run(lista, old, '2026-11-26T19:26:00-03:00')
        self.assertEqual(result['sumario']['revisoes_ambiguas_nesta_execucao'], 1)
        self.assertEqual(result['registros']['c']['classificacao'], 'prazo_de_inscricao_ja_decorrido')
        self.assertEqual(len(vistos), 2)

    def test_fapern_nao_adota_resultado_da_noticia_como_inscricao(self):
        from src.sources.fapern import FAPERNSource
        summary='Aberta chamada para projetos científicos'
        content=('Evento em 10/11/2026.\nPrazo de inscrição até 18/12/2026\n'
                 'Resultado final 20/01/2027. Contratação em 18/02/2027.')
        self.assertEqual(FAPERNSource._extract_deadline(None,summary,content,'2026-11-01'),
                         '2026-12-18')
        only_results=('Divulgação do resultado em 20/01/2027.\n'
                      'Prazo de contratação em 18/02/2027.')
        self.assertIsNone(FAPERNSource._extract_deadline(None,summary,only_results,'2026-11-01'))

    def test_fapesq_prazo_explicitado_e_datas_de_resultado(self):
        from src.sources.fapesq import FAPESQSource
        texto=('Lançamento do edital em 14/11/2026.\n'
               'Prazo para submissão de propostas até 19/12/2026.\n'
               'Resultado em 21/01/2027.')
        self.assertEqual(FAPESQSource._extract_deadline(None,texto),'2026-12-19')
        self.assertIsNone(FAPESQSource._extract_deadline(None,
            'Resultado de projetos em 21/01/2027. Contratação em 15/02/2027.'))

    def test_fapac_nao_trata_capa_jpg_como_edital(self):
        from src.models import SourceConfig
        from src.sources.fapac import FAPACSource
        cfg=SourceConfig(nome='FAPAC', sigla='FAPAC', uf='AC',
            site_oficial='https://fapac.ac.gov.br',
            pagina_editais='https://fapac.ac.gov.br/editais',
            tipo_coleta='html')
        html=('<main><a href="/wp-content/uploads/2026/05/EDITAL-PDPG-01.2026-pdf-724x1024.jpg">'
              'Edital PDPG 01/2026</a>'
              '<a href="/wp-content/uploads/2026/05/EDITAL-02-2026.pdf">'
              'Edital 02/2026 de pesquisa</a></main>')
        items=FAPACSource(cfg).parse(html)
        self.assertEqual(len(items),1)
        self.assertTrue(items[0]['link'].endswith('.pdf'))

    def test_auditor_falha_http_503_tem_um_retry_seguro(self):
        from unittest.mock import Mock
        service=DeadlineAuditService(logging.getLogger('retry-test'))
        fail=Mock()
        fail.status_code=503
        success=Mock()
        success.status_code=200
        success.content=b'<html><main>Inscricoes ate 14/12/2026</main></html>'
        success.text=success.content.decode()
        success.headers={'content-type':'text/html'}
        success.raise_for_status.return_value=None
        with patch('src.services.deadline_audit_service.requests.get',
                   side_effect=[fail,success]) as get:
            content, retrieved, error=service._fetch_text('https://fap.org.br/edital')
        self.assertEqual(error,'')
        self.assertIn('14/12/2026',content)
        self.assertEqual(get.call_count,2)

    def test_auditor_timeout_e_imagem_falham_sem_liberacao(self):
        from unittest.mock import Mock
        from requests import Timeout
        service=DeadlineAuditService(logging.getLogger('failure-test'))
        with patch('src.services.deadline_audit_service.requests.get',
                   side_effect=[Timeout('temporario'),Timeout('persistente')]) as get:
            raw,url,error=service._fetch_text('https://fap.org.br/edital')
        self.assertEqual(error,'timeout_http')
        self.assertEqual(get.call_count,2)
        response=Mock()
        response.status_code=200
        response.headers={'content-type':'image/jpeg'}
        response.content=b'jpeg'
        response.raise_for_status.return_value=None
        with patch('src.services.deadline_audit_service.requests.get',return_value=response):
            raw,url,error=service._fetch_text('https://fap.org.br/capa.jpg')
        self.assertEqual(error,'imagem_nao_e_documento_textual')

    def test_resumo_por_fonte_reconhece_recuperacao_transitoria(self):
        state={'registros':{'id':{'id':'id','fonte':'FAP',
                                 'link_cadastrado':'https://fap.org.br/editais/id',
                                 'classificacao':'falha_http_503'}}}
        service=DeadlineAuditService(logging.getLogger('recover-test'),
            lambda url:('Inscricoes ate 14/12/2026',url,''))
        now='2026-11-27T09:00:00-03:00'
        report=service.run([item('id')],state,now)
        self.assertEqual(report['sumario']['falhas_de_acesso_recuperadas_na_execucao'],1)
        self.assertEqual(report['sumario']['novos_candidatos_a_recuperacao'],1)
        self.assertFalse(report['registros']['id']['publicacao_autorizada_pela_auditoria'])


if __name__ == '__main__':
    unittest.main()
