import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from src.services.opportunity_guard import (
    NOT_OPPORTUNITY,
    COLLECTION_PAGE,
    UNKNOWN_CLOSING_TIME,
    is_listing_page,
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

    def test_fapesq_lista_com_prazo_atribuido_nao_pode_publicar(self):
        item = edital('EDITAIS LANÇADOS E/OU COM PRAZO DE SUBMISSÃO DE PROPOSTAS ABERTO',
                      due='2026-11-26')
        item['status'] = 'prorrogado'
        item['pronto_para_postagem'] = True
        item['link'] = 'https://fapesq.rpp.br/noticias/editais-com-prazo-de-submissao-de-propostas-aberto'
        allowed, reason, definitive = opportunity_gate(item, NOW)
        self.assertEqual((allowed, reason, definitive), (False, COLLECTION_PAGE, True))

    def test_titulos_e_urls_de_listagens_sao_filtrados(self):
        for title in ('Editais lançados e/ou com prazo',
                      'Editais com inscrições abertas',
                      'Lista de chamadas de pesquisa',
                      'Oportunidades disponíveis'):
            with self.subTest(title=title):
                self.assertTrue(is_listing_page(title))
        self.assertTrue(is_listing_page('Atualização', 
            'https://fapesq.rpp.br/noticias/editais-com-prazo-de-submissao-de-propostas-aberto'))
        self.assertFalse(is_listing_page('EDITAL Nº 72/2026 - Seleção de equipes',
            'https://fapesq.rpp.br/editais/2026/edital-no-72-2026'))

    def test_fapesq_coletor_nao_publica_pagina_agrupadora(self):
        from src.models import SourceConfig
        from src.sources.fapesq import FAPESQSource
        cfg = SourceConfig(
            nome='FAPESQ', sigla='FAPESQ', uf='PB', site_oficial='https://fapesq.rpp.br',
            pagina_editais='https://fapesq.rpp.br/noticias', tipo_coleta='html')
        raw = (
            '<main>'
            '<article><a href="/noticias/editais-com-prazo-de-submissao-de-propostas-aberto">'
            'EDITAIS LANÇADOS E/OU COM PRAZO DE SUBMISSÃO DE PROPOSTAS ABERTO</a></article>'
            '<article><a href="/editais/2026/edital-no-72-2026">'
            'EDITAL Nº 72/2026 - Seleção de equipes</a></article>'
            '</main>'
        )
        items = FAPESQSource(cfg).parse(raw)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['titulo'], 'EDITAL Nº 72/2026 - Seleção de equipes')

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

    def test_data_atualizada_e_verificada_novamente(self):
        item = edital(due='2026-11-15')
        self.assertFalse(opportunity_gate(item, NOW)[0])
        item['data_expiracao'] = '2026-11-28'
        self.assertTrue(opportunity_gate(item, NOW)[0])
        item['data_expiracao'] = '2026-11-16'
        self.assertFalse(opportunity_gate(item, NOW)[0])

    def test_data_atualizada_nao_dispensa_filtros_editoriais(self):
        item = edital('Divulgados os finalistas do premio', due='2026-12-10')
        self.assertFalse(opportunity_gate(item, NOW)[0])
        item = edital(due='data invalida')
        self.assertFalse(opportunity_gate(item, NOW)[0])

    def test_novo_prazo_em_registro_etapa2_nao_exige_homologacao_manual(self):
        item = edital(due='2026-12-10', id='edital_recuperado',
                      recuperacao_etapa2=True,
                      homologacao_editorial_etapa2=False)
        self.assertTrue(opportunity_gate(item, NOW)[0])

    def test_prazo_recuperado_bloqueia_feed_mesmo_com_data_futura(self):
        item = edital(due='2026-12-16T17:00:00-03:00',
                      bloqueio_recuperacao_prazo=True,
                      pronto_para_postagem=True)
        allowed, reason, definitive = opportunity_gate(item, NOW)
        self.assertFalse(allowed)
        self.assertIn('revisao editorial', reason)
        self.assertFalse(definitive)
        item['bloqueio_recuperacao_prazo'] = False
        self.assertTrue(opportunity_gate(item, NOW)[0])

    def test_modelo_preserva_bloqueio_entre_sincronizacoes(self):
        from src.models import Edital
        from src.services.dedup_service import DedupService
        fields = dict(id='x', titulo='Chamada de pesquisa', orgao='FAP',
                      fonte='FAP', uf='BR', categoria='pesquisa', link='https://fap.org/a',
                      resumo='Chamada com prazo oficial', publico_alvo='ICTs',
                      data_abertura='2026-11-01', data_expiracao='2026-12-16',
                      data_ultima_coleta='2026-11-27T10:00:00-03:00',
                      bloqueio_recuperacao_prazo=True,
                      prazo_fase_recuperada='formulario_proposta',
                      prazo_fonte_documental='https://fap.org/errata.pdf')
        original=Edital(**fields).to_dict()
        incoming=Edital(**dict(fields, data_ultima_coleta='2026-11-27T11:00:00-03:00',
                               bloqueio_recuperacao_prazo=False,
                               prazo_fase_recuperada='', prazo_fonte_documental=''))
        merged,_=DedupService().merge(DedupService().index_existing([original]),[incoming])
        self.assertTrue(merged[0].bloqueio_recuperacao_prazo)
        self.assertEqual(merged[0].prazo_fase_recuperada,'formulario_proposta')
        self.assertFalse(opportunity_gate(merged[0].to_dict(), NOW)[0])

    def test_reconciliacao_documentada_nao_publica_e_nao_confunde_fases(self):
        from src.services.recovered_deadlines import (
            read_documented_deadlines, reconcile_documented_deadlines,
        )
        from src.main import classify_posting_readiness, mark_expired
        from src.models import Edital
        rows = [
            {'id':'fundacao_de_amparo_a_pesquisa_do_estado__70bb5a90',
             'link':'https://www.fapesb.ba.gov.br/edital-no-0192026-ciencia-na-mesa-5-base-de-dados-e-sistemas-de-informacoes-para-tomada-de-decisao-em-soberania-alimentar-e-nutricional/',
             'titulo':'Edital FAPESB 019/2026 Ciência na Mesa',
             'orgao':'FAPESB','fonte':'FAPESB','uf':'BA','categoria':'pesquisa',
             'resumo':'Edital para financiamento de pesquisa','publico_alvo':'Pesquisadores',
             'status':'encerrado','data_abertura':None,'data_expiracao':None,
             'data_ultima_coleta':'2026-11-27T10:00:00-03:00'},
            {'id':'empresa_brasileira_de_pesquisa_e_inovaca_d7e4e002',
             'link':'https://embrapii.org.br/chamadas-publicas/chamada-publica-n02-2026-para-projetos-de-alto-impacto-em-economia-circular/',
             'titulo':'Chamada Petrobras Economia Circular',
             'orgao':'EMBRAPII','fonte':'EMBRAPII','uf':'BR','categoria':'inovacao',
             'resumo':'Projetos de desenvolvimento e inovação','publico_alvo':'Empresas',
             'status':'novo','data_abertura':None,'data_expiracao':None,
             'data_ultima_coleta':'2026-11-27T10:00:00-03:00'},
        ]
        report = reconcile_documented_deadlines(rows, read_documented_deadlines())
        self.assertEqual(report['aplicados'],2)
        fapesb,embrapii=rows
        self.assertEqual(fapesb['data_expiracao'],'2026-12-16T17:00:00-03:00')
        self.assertEqual(fapesb['prazo_documentacao_adicional'],'2026-12-18T23:59:00-03:00')
        self.assertEqual(fapesb['status'],'atualizado')
        self.assertEqual(embrapii['data_expiracao'],'2027-01-08')
        self.assertEqual(embrapii['prazo_documentacao_adicional'],'2027-03-05')
        self.assertTrue(all(row['bloqueio_recuperacao_prazo'] for row in rows))
        for row in rows:
            self.assertFalse(opportunity_gate(row,NOW)[0])
            self.assertFalse(classify_posting_readiness(row)[0])
            self.assertFalse(Edital(**row).pronto_para_postagem)
        mark_expired(rows,'2026-11-27')
        self.assertFalse(any(row['pronto_para_postagem'] for row in rows))

    def test_reconciliacao_falha_fechada_em_url_mudada_e_fase_ambigua(self):
        import copy
        from src.services.recovered_deadlines import (
            read_documented_deadlines,reconcile_documented_deadlines,
        )
        registry=read_documented_deadlines()
        key='fundacao_de_amparo_a_pesquisa_do_estado__70bb5a90'
        item={'id':key,'link':'https://fapesb.ba.gov.br/arquivo-diferente','data_expiracao':None}
        result=reconcile_documented_deadlines([item],registry)
        self.assertEqual(result['links_divergentes'],1)
        self.assertIsNone(item['data_expiracao'])
        item['link']=registry['registros'][key]['link_catalogado']
        bad=copy.deepcopy(registry)
        bad['registros'][key]['fase']=''
        self.assertEqual(reconcile_documented_deadlines([item],bad)['invalidos'],1)
        self.assertIsNone(item['data_expiracao'])
        bad=copy.deepcopy(registry)
        bad['registros'][key]['prazo_inscricao']='2027-05-11'
        bad['registros'][key]['prazo_secundario']=''
        # A ausência de fase para data secundária não pode ser reaproveitada.
        bad['registros'][key]['prazo_secundario_fase']=''
        self.assertEqual(reconcile_documented_deadlines([item],bad)['aplicados'],1)
        self.assertFalse(opportunity_gate(item,NOW)[0])

    def test_catalogo_dois_prazos_recuperados_continuam_em_hold(self):
        import json
        from pathlib import Path
        from src.publish_pending import eligible_for_publication
        catalog = json.loads((Path(__file__).resolve().parents[1] /
                              'data/editais.json').read_text(encoding='utf-8'))
        by_id = {x['id']: x for x in catalog}
        cases = {
            'fundacao_de_amparo_a_pesquisa_do_estado__70bb5a90':
                ('2026-12-16T17:00:00-03:00','conclusao_formulario_online_de_proposta'),
            'empresa_brasileira_de_pesquisa_e_inovaca_d7e4e002':
                ('2027-01-08','submissao_pre_propostas_por_unidades_embrapii'),
        }
        for key,(deadline,phase) in cases.items():
            row=by_id[key]
            self.assertEqual(row['data_expiracao'],deadline)
            self.assertEqual(row['prazo_fase_recuperada'],phase)
            self.assertTrue(row['prazo_fonte_documental'].startswith('https://'))
            self.assertTrue(row['bloqueio_recuperacao_prazo'])
            self.assertFalse(row['pronto_para_postagem'])
            self.assertFalse(eligible_for_publication(row))
        self.assertEqual(sum(not x.get('data_expiracao') for x in catalog),206)


if __name__ == '__main__':
    unittest.main()
