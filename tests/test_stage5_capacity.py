import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from src.services.stage5_capacity import forecast_capacity


NOW = datetime(2026,11,27,14,0,tzinfo=ZoneInfo('America/Sao_Paulo'))


def items(total, deadline):
    return [{'id':str(i), 'data_expiracao':deadline} for i in range(total)]


class Stage5CapacityTests(unittest.TestCase):
    def test_15_para_10_antes_do_prazo_dispara_alerta_5(self):
        result=forecast_capacity(items(15,'2026-11-28'),[],NOW,10)
        self.assertEqual(result['capacidade_restante_hoje'],10)
        self.assertEqual(result['previstos_no_horizonte'],10)
        self.assertEqual(result['em_risco_antes_do_vencimento'],5)
        self.assertTrue(result['alerta_gargalo'])
        self.assertTrue(all(p['data_prevista']=='2026-11-27' for p in result['previsoes']))

    def test_15_com_prazo_mais_longo_cabem_em_dois_dias(self):
        result=forecast_capacity(items(15,'2026-12-02'),[],NOW,10)
        self.assertEqual(result['previstos_no_horizonte'],15)
        self.assertFalse(result['alerta_gargalo'])
        self.assertEqual([p['data_prevista'] for p in result['previsoes']].count('2026-11-28'),5)

    def test_carrossel_publicado_hoje_elimina_vagas_do_dia(self):
        history=[{'edital_id':str(i),'status':'success','feed_media_id':'abc',
                  'data_publicacao':'2026-11-27T09:00:00-03:00'} for i in range(4)]
        result=forecast_capacity(items(15,'2026-11-28'),history,NOW,10)
        self.assertEqual(result['capacidade_restante_hoje'],0)
        self.assertEqual(result['publicacoes_feed_hoje'],4)
        self.assertEqual(result['em_risco_antes_do_vencimento'],15)

    def test_story_ou_falha_nao_ocupam_capacidade_de_feed(self):
        rows=[{'edital_id':'a','status':'success','story_media_id':'123','feed_media_id':'',
               'mensagem':'Story publicado','data_publicacao':'2026-11-27T10:00:00-03:00'},
              {'edital_id':'b','status':'failed','feed_media_id':'999',
               'data_publicacao':'2026-11-27T10:00:00-03:00'}]
        result=forecast_capacity(items(2,'2026-11-28'),rows,NOW,10)
        self.assertEqual(result['capacidade_restante_hoje'],10)

    def test_hora_fuso_e_prorrogacao(self):
        one=items(1,'2026-11-27T17:00:00-03:00')
        self.assertEqual(forecast_capacity(one,[],NOW,10)['em_risco_antes_do_vencimento'],0)
        one[0]['data_expiracao']='2026-11-27T16:00:00+00:00'
        self.assertEqual(forecast_capacity(one,[],NOW,10)['em_risco_antes_do_vencimento'],1)
        one[0]['data_expiracao']='2026-12-05'
        self.assertEqual(forecast_capacity(one,[],NOW,10)['previstos_no_horizonte'],1)

    def test_sem_capacidade_nao_finge_publicacao(self):
        result=forecast_capacity(items(2,'2026-12-01'),[],NOW,0)
        self.assertEqual(result['previstos_no_horizonte'],0)
        self.assertEqual(result['em_risco_antes_do_vencimento'],2)


if __name__=='__main__':
    unittest.main()
