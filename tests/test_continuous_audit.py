import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from src.services.continuous_audit import run_continuous_audit, safe_source_url

NOW = datetime(2026,11,27,14,tzinfo=ZoneInfo('America/Sao_Paulo'))


class ContinuousAuditTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path=Path(temp.name)
        self.snapshot=path/'auditoria_continua.json'
        self.events=path/'auditoria_eventos.jsonl'

    def run_audit(self,items,history=None,**kwargs):
        return run_continuous_audit(items,history or [],NOW,'America/Sao_Paulo',
                                    self.snapshot,self.events,**kwargs)

    def test_snapshot_e_eventos_nao_repetidos(self):
        item={'id':'a','titulo':'Chamada de pesquisa','fonte':'FAP',
              'link':'https://example.org/editais?token=secreto',
              'data_expiracao':'2026-12-15','pronto_para_postagem':True}
        first=self.run_audit([item])
        self.assertEqual(first['sumario']['alteracoes_nesta_execucao'],1)
        self.assertEqual(first['registros'][0]['url_fonte'],'https://example.org/editais')
        self.assertNotIn('secreto',self.events.read_text())
        second=self.run_audit([item])
        self.assertEqual(second['sumario']['alteracoes_nesta_execucao'],0)
        self.assertEqual(len(self.events.read_text().splitlines()),1)
        item['data_expiracao']='2026-12-20'
        third=self.run_audit([item])
        self.assertEqual(third['sumario']['alteracoes_nesta_execucao'],1)
        self.assertEqual(len(self.events.read_text().splitlines()),2)

    def test_sem_prazo_e_hold_sao_identificados_sem_liberar(self):
        obj={'id':'s','titulo':'Chamada de pesquisa','fonte':'FAP',
             'link':'', 'data_expiracao':None,'pronto_para_postagem':False}
        report=self.run_audit([obj])
        self.assertEqual(report['registros'][0]['decisao'],'HOLD_nao_pronto')
        self.assertIn('sem_prazo',report['sumario']['anomalias_por_tipo'])
        self.assertIn('sem_url_fonte_valida',report['sumario']['anomalias_por_tipo'])

    def test_historico_feed_e_falhas_e_sobreposicao(self):
        obj={'id':'x','titulo':'Chamada pesquisa','fonte':'FAP',
             'link':'https://example.org/','data_expiracao':'2026-10-01',
             'pronto_para_postagem':False}
        history=[{'edital_id':'x','status':'success','feed_media_id':'123'},
                 {'edital_id':'x','status':'failed','mensagem':'erro remoto'}]
        report=self.run_audit([obj],history,queue1_ids={'x'},queue2_ids={'x'})
        self.assertEqual(report['registros'][0]['decisao'],'monitoramento_publicado')
        self.assertEqual(report['sumario']['falhas_de_publicacao_no_historico'],1)
        self.assertEqual(report['sumario']['sobreposicoes_filas'],['x'])

    def test_remocao_do_catalogo_preserva_trilha(self):
        self.run_audit([{'id':'a','titulo':'Chamada','fonte':'FAP',
                         'data_expiracao':None}])
        result=self.run_audit([])
        self.assertEqual(result['sumario']['alteracoes_nesta_execucao'],1)
        self.assertEqual(json.loads(self.events.read_text().splitlines()[-1])['tipo'],
                         'removido_do_catalogo')

    def test_url_credenciais_e_query_removidos(self):
        self.assertEqual(safe_source_url('https://user:senha@example.org/x?a=token'),
                         'https://example.org/x')
