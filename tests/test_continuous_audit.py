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

    def test_documento_falha_e_recuperacao_geram_alertas_sem_autorizacao(self):
        import json
        row={'id':'a','titulo':'Chamada de pesquisa', 'fonte':'FACEPE',
             'link':'https://example.org/edital.pdf',
             'data_expiracao':'2026-11-29', 'pronto_para_postagem':True}
        evidence={'registros':{'a':{'link_cadastrado':row['link'],
                   'classificacao':'falha_http_403',
                   'verificado_em':'2026-11-27T10:00:00-03:00'}}}
        audit=self.snapshot.parent/'auditoria_prazos.json'
        audit.write_text(json.dumps(evidence),encoding='utf-8')
        first=self.run_audit([row])
        self.assertEqual(first['sumario']['auditados_documentalmente'],1)
        self.assertEqual(first['sumario']['novos_desde_ultimo_snapshot'],1)
        self.assertIn('falha_acesso_documento',first['sumario']['anomalias_por_tipo'])
        self.assertEqual(first['sumario']['risco_de_expiracao_em_ate_3_dias'],1)
        second=self.run_audit([row])
        self.assertEqual(second['sumario']['anomalias_persistentes_desde_ultimo_snapshot'],1)
        audit.write_text(json.dumps({'registros':{'a':{
            'link_cadastrado':row['link'],'classificacao':'prazo_corroborrado',
            'verificado_em':'2026-11-27T14:00:00-03:00'}}}),encoding='utf-8')
        third=self.run_audit([row])
        self.assertEqual(third['sumario']['falhas_recuperadas_desde_ultimo_snapshot'],1)
        self.assertEqual(third['sumario']['ids_recuperados'],['a'])

    def test_novo_link_invalida_auditoria_antiga(self):
        import json
        row={'id':'b','titulo':'Chamada','fonte':'FAP',
             'link':'https://example.org/edital-novo','data_expiracao':None}
        (self.snapshot.parent/'auditoria_prazos.json').write_text(
            json.dumps({'registros':{'b':{'link_cadastrado':'https://example.org/antigo',
                'classificacao':'prazo_corroborrado'}}}),encoding='utf-8')
        report=self.run_audit([row])
        self.assertIn('link_alterado_auditoria_obsoleta',
                      report['sumario']['anomalias_por_tipo'])
        self.assertEqual(report['sumario']['auditados_documentalmente'],0)

    def test_url_credenciais_e_query_removidos(self):
        self.assertEqual(safe_source_url('https://user:senha@example.org/x?a=token'),
                         'https://example.org/x')
