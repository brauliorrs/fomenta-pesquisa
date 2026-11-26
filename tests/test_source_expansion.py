import logging
import unittest

from src.models import SourceConfig
from src.services.source_expansion_service import SourceExpansionService
from src.sources.generic_discovery import GenericDiscoverySource


ROOT = 'https://instituto.gov.br'
SEED = ROOT + '/fomento'
LISTING = ROOT + '/editais-abertos'
EXTERNAL = 'https://nova-fundacao.org.br/editais'
SEED_HTML = (
    '<main><a href="/editais-abertos/">Editais abertos</a>'
    '<a href="https://nova-fundacao.org.br/editais">Editais</a>'
    '<a href="/editais/2026/edital-no-99">Edital nº 99/2026</a></main>'
)
LISTING_HTML = (
    '<main><ul>'
    '<li><a href="/editais/2026/edital-no-01">Edital nº 01/2026 - Pesquisa</a></li>'
    '<li><a href="/editais/2026/edital-no-02">Edital nº 02/2026 - Bolsas</a></li>'
    '</ul></main>'
)


def source():
    return {
        'nome': 'Instituto de Pesquisa', 'sigla': 'INST', 'uf': 'BR',
        'site_oficial': ROOT, 'pagina_editais': SEED, 'parser': 'generic',
        'tipo_coleta': 'html', 'ativo': True, 'selectors': {},
    }


def make_service(html_by_url):
    called = []
    def fetch(url):
        called.append(url)
        return html_by_url.get(url, '')
    return SourceExpansionService(logging.getLogger('test-expansion'), fetch), called


class TestSourceExpansion(unittest.TestCase):
    def test_primeira_descoberta_e_candidatura_sem_publicacao(self):
        service, called = make_service({SEED: SEED_HTML, LISTING: LISTING_HTML})
        active, candidates, report = service.scan(
            [source()], [], {}, '2026-11-25T08:00:00-03:00'
        )
        self.assertEqual(len(active), 1)
        self.assertEqual(len(candidates), 1, f'links={service.links_from_page(SEED_HTML, SEED)} normalized={service.clean_url('/editais-abertos/', SEED)} qualifies={service.is_listing_candidate('Editais abertos', LISTING)} called={called} state={report}')
        self.assertEqual(candidates[0]['pagina_editais_hint'], LISTING)
        self.assertEqual(candidates[0]['activation_mode'], 'review_when_viable')
        self.assertEqual(report['paginas'][LISTING]['validacoes'], 1)
        self.assertEqual(report['paginas'][EXTERNAL]['status'], 'externa_pendente_revisao')
        self.assertNotIn(EXTERNAL, called)

    def test_segundo_dia_valido_atualiza_fontes_ativas(self):
        service, _ = make_service({SEED: SEED_HTML, LISTING: LISTING_HTML})
        active1, candidates1, report1 = service.scan(
            [source()], [], {}, '2026-11-25T08:00:00-03:00'
        )
        active2, candidates2, report2 = service.scan(
            active1, candidates1, report1, '2026-11-26T08:00:00-03:00'
        )
        self.assertEqual(len(active2), 2)
        self.assertEqual(len(candidates2), 1)
        new_source = active2[1]
        self.assertEqual(new_source['pagina_editais'], LISTING)
        self.assertEqual(new_source['sigla_publicacao'], 'INST')
        self.assertEqual(new_source['parser'], 'generic_discovery')
        self.assertEqual(report2['paginas'][LISTING]['status'], 'integrada_auto')
        self.assertEqual(report2['sumario']['fontes_auto_integradas'], 1)

    def test_repeticao_no_mesmo_dia_nao_promove_fonte(self):
        service, _ = make_service({SEED: SEED_HTML, LISTING: LISTING_HTML})
        a, c, state = service.scan([source()], [], {}, '2026-11-25T08:00:00-03:00')
        a, c, state = service.scan(a, c, state, '2026-11-25T10:00:00-03:00')
        self.assertEqual(len(a), 1)
        self.assertEqual(state['paginas'][LISTING]['validacoes'], 1)
        self.assertEqual(state['paginas'][LISTING]['observacoes'], 1)

    def test_pagina_institucional_sem_chamadas_individuais_fica_pendente(self):
        html = '<main><a href="/editais-abertos">Editais abertos</a></main>'
        candidate_html = (
            '<ul><li><a href="/noticias/resultado">Resultados do edital</a></li>'
            '<li><a href="/noticias/premio">Finalistas do Prêmio Pesquisa</a></li></ul>'
        )
        service, _ = make_service({SEED: html, LISTING: candidate_html})
        a, c, state = service.scan([source()], [], {}, '2026-11-25T08:00:00-03:00')
        a, c, state = service.scan(a, c, state, '2026-11-26T08:00:00-03:00')
        self.assertEqual(len(a), 1)
        self.assertEqual(len(c), 0)
        self.assertEqual(state['paginas'][LISTING]['validacoes'], 0)

    def test_nao_tratar_edital_individual_como_pagina_coletora(self):
        svc, _ = make_service({})
        links = svc.links_from_page(SEED_HTML, SEED)
        self.assertNotIn(ROOT + '/editais/2026/edital-no-99',
                         [link for link, _ in links])

    def test_nao_seguir_links_para_rede_local_ou_perfis_com_credenciais(self):
        svc, _ = make_service({})
        self.assertEqual(svc.clean_url('http://127.0.0.1/admin', SEED), '')
        self.assertEqual(svc.clean_url('http://localhost:8080/editais', SEED), '')
        self.assertEqual(svc.clean_url('https://user:pass@evil.org/editais', SEED), '')

    def test_fonte_adicional_mantem_nome_editorial_original(self):
        cfg = SourceConfig(
            nome='Instituto de Pesquisa', sigla='EXP123', sigla_publicacao='INST',
            uf='BR', site_oficial=ROOT, pagina_editais=LISTING,
            tipo_coleta='html', parser='generic_discovery',
            selectors={'item': 'li a[href]'},
        )
        edital = GenericDiscoverySource(cfg).parse(LISTING_HTML)[0]
        self.assertEqual(edital['fonte'], 'INST')


if __name__ == '__main__':
    unittest.main()
