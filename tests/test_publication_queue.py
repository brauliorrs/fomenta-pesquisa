import tempfile
import unittest
from pathlib import Path

from src.services.publication_queue_service import (
    PublicationQueueService, already_published, published_feed_ids,
)
from src.services.storage_service import StorageService


def call(edital_id, deadline='2099-12-31', **extra):
    return {
        'id': edital_id, 'titulo': f'Edital de pesquisa {edital_id}',
        'resumo': 'Chamada com inscricoes para pesquisadores',
        'status': 'novo', 'data_expiracao': deadline,
        'pronto_para_postagem': True,
        'score_editorial': 90, 'fonte': 'FAP',
        **extra,
    }


class PublicationQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.storage = StorageService()
        self.path1 = root / 'fila_publicacao.json'
        self.path2 = root / 'fila_ja_publicados.json'
        self.service = PublicationQueueService(self.storage, self.path1, self.path2)

    def export(self, editais, history=None):
        self.service.export(editais, '2026-11-25T20:00:00-03:00', history or [])
        return (self.storage.read_json(self.path1, {}),
                self.storage.read_json(self.path2, {}))

    def test_fila_um_apenas_ineditos_em_ordem_de_prazo(self):
        f1, f2 = self.export([
            call('a', '2099-12-30'),
            call('b', '2099-12-28'),
            call('c', '2099-12-29', instagram_feed_publicado=True),
        ])
        self.assertEqual([x['id'] for x in f1['itens']], ['b', 'a'])
        self.assertEqual([x['id'] for x in f2['itens']], ['c'])
        self.assertEqual((f1['total_prontos'], f1['total_ineditos'],
                          f1['total_ja_publicados']), (2, 2, 1))
        self.assertEqual(f2['total_ja_publicados'], 1)
        self.assertEqual(f1['itens'][0]['posicao_fila'], 1)
        self.assertEqual(f1['itens'][0]['validacao_inscricoes'],
                         'triagem_automatica_sem_homologacao_do_prazo_oficial')

    def test_historico_de_feed_sobrepoe_flag_desatualizado(self):
        history = [{'edital_id': 'antigo', 'status': 'success',
                    'feed_media_id': '178123', 'publication_kind': 'feed_carousel'}]
        f1, f2 = self.export([call('antigo', instagram_feed_publicado=False)], history)
        self.assertEqual(f1['total_prontos'], 0)
        self.assertEqual(f2['total_ja_publicados'], 1)
        self.assertTrue(f2['itens'][0]['instagram_feed_publicado'])

    def test_stories_nao_sao_registrados_como_primeiro_feed(self):
        rows = [{'edital_id': 'x', 'status': 'success',
                 'story_media_id': '999', 'feed_media_id': ''},
                {'edital_id': 'y', 'status': 'failed', 'feed_media_id': '123'}]
        self.assertEqual(published_feed_ids(rows), set())
        f1, f2 = self.export([call('x'), call('y')], rows)
        self.assertEqual(f1['total_prontos'], 2)
        self.assertEqual(f2['total_ja_publicados'], 0)

    def test_duplicidade_na_fila_evitada_por_classe(self):
        f1, f2 = self.export([
            call('a', instagram_feed_media_id='17999'),
            call('b'),
        ])
        ids1 = {x['id'] for x in f1['itens']}
        ids2 = {x['id'] for x in f2['itens']}
        self.assertFalse(ids1 & ids2)
        self.assertEqual(ids1 | ids2, {'a', 'b'})

    def test_bloqueados_nao_entram_em_nenhuma_fila(self):
        f1, f2 = self.export([
            call('sem_prazo', deadline=None),
            call('listagem', titulo='Editais abertos de pesquisa'),
            call('nao_pronto', pronto_para_postagem=False),
            call('publicado', instagram_feed_publicado=True),
        ])
        self.assertEqual(f1['total_prontos'], 0)
        self.assertEqual(f2['total_ja_publicados'], 1)
        self.assertEqual(f2['itens'][0]['id'], 'publicado')

    def test_publicado_vencido_permanece_no_monitoramento(self):
        f1, f2 = self.export([
            call('antigo', deadline='2020-01-01', instagram_feed_publicado=True,
                 pronto_para_postagem=False, status='encerrado'),
            call('vigente'),
        ])
        self.assertEqual([x['id'] for x in f1['itens']], ['vigente'])
        self.assertEqual([x['id'] for x in f2['itens']], ['antigo'])
        self.assertEqual(f2['total_encerrados_monitorados'], 1)

    def test_id_duplicado_nunca_reaparece_como_inedito(self):
        f1, f2 = self.export([
            call('repetido'), call('repetido', instagram_feed_media_id='17899'),
            call('novo'), call('sem_data', deadline=None),
        ])
        self.assertEqual([x['id'] for x in f1['itens']], ['novo'])
        self.assertEqual([x['id'] for x in f2['itens']], ['repetido'])
        self.assertEqual(f1['total_registros_catalogo_distintos'], 3)
        self.assertEqual(f1['total_bloqueados_ou_sem_prazo'], 1)

    def test_feed_historico_vencido_nao_reaparece_em_ineditos(self):
        history = [{'edital_id': 'hist', 'status': 'success',
                    'feed_media_id': '178123', 'publication_kind': 'feed_carousel'}]
        f1, f2 = self.export([
            call('hist', deadline='2020-01-01', pronto_para_postagem=False),
        ], history)
        self.assertEqual(f1['total_ineditos'], 0)
        self.assertEqual(f2['total_ja_publicados'], 1)

    def test_prioridade_instante_real_e_fuso(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime(2026, 11, 27, 10, tzinfo=ZoneInfo('America/Sao_Paulo'))
        items = [
            call('segundo', deadline='2026-11-29T10:00:00-03:00'),
            call('primeiro', deadline='2026-11-29T09:00:00-03:00'),
            call('primeiro_mesmo_instante', deadline='2026-11-29T12:00:00+00:00'),
            call('sem_hora', deadline='2026-11-29'),
        ]
        ranked = sorted(items, key=lambda x: self.service._sort_key(x, now))
        self.assertEqual([x['id'] for x in ranked],
                         ['primeiro', 'primeiro_mesmo_instante', 'segundo', 'sem_hora'])

    def test_prorrogacao_reordena_sem_persistir_risco_antigo(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime(2026, 11, 27, 10, tzinfo=ZoneInfo('America/Sao_Paulo'))
        a = call('prorrogado', deadline='2026-11-28')
        b = call('normal', deadline='2026-11-30')
        self.assertEqual(sorted([a,b],key=lambda x:self.service._sort_key(x,now))[0]['id'],'prorrogado')
        a['data_expiracao']='2026-12-10'
        self.assertEqual(sorted([a,b],key=lambda x:self.service._sort_key(x,now))[0]['id'],'normal')

    def test_riscos_iminente_sem_hora_e_vencido(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime(2026, 11, 27, 10, tzinfo=ZoneInfo('America/Sao_Paulo'))
        risk=self.service._risk_label
        self.assertEqual(risk('2026-11-27T15:00:00-03:00',now),'iminente_24h')
        self.assertEqual(risk('2026-11-27',now),'vence_hoje_horario_desconhecido')
        self.assertEqual(risk('2026-11-26',now),'vencido')
        self.assertEqual(risk(None,now),'prazo_desconhecido')
        self.assertEqual(risk('2026-11-28',now),'vence_amanha')

    def test_previsao_exportada_alerta_15_para_10(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from unittest.mock import patch
        now = datetime(2026, 11, 27, 14, tzinfo=ZoneInfo('America/Sao_Paulo'))
        entries = [call(f'novo_{i}', deadline='2026-11-28') for i in range(15)]
        from types import SimpleNamespace
        fake_settings=SimpleNamespace(
            timezone='America/Sao_Paulo', instagram_max_new_publications_per_day=10,
        )
        with patch('src.services.publication_queue_service.now_in_timezone', return_value=now), patch(
            'src.services.publication_queue_service.settings', fake_settings,
        ):
            f1, f2 = self.export(entries)
        preview = f1['previsao_capacidade']
        self.assertEqual(f1['total_ineditos'], 15)
        self.assertEqual(preview['capacidade_restante_hoje'],10)
        self.assertEqual(preview['em_risco_antes_do_vencimento'],5)
        self.assertTrue(preview['alerta_gargalo'])
        self.assertEqual(f2['previsao_capacidade']['em_risco_antes_do_vencimento'],5)

    def test_capacidade_com_feed_ja_publicado_hoje(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from src.services.stage5_capacity import forecast_capacity
        now=datetime(2026,11,27,14,tzinfo=ZoneInfo('America/Sao_Paulo'))
        hist=[{'edital_id':'ja_publicado','status':'success',
               'feed_media_id':'feed_123',
               'data_publicacao':'2026-11-27T09:00:00-03:00'}]
        item=[{'id':f'novo_{i}','data_expiracao':'2026-11-28'} for i in range(15)]
        result=forecast_capacity(item,hist,now,10)
        self.assertEqual(result['capacidade_restante_hoje'],0)
        self.assertEqual(result['em_risco_antes_do_vencimento'],15)

    def test_previsao_diferencia_story_e_prorrogacao(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from src.services.stage5_capacity import forecast_capacity
        now=datetime(2026,11,27,14,tzinfo=ZoneInfo('America/Sao_Paulo'))
        story=[{'edital_id':'story','status':'success',
                'story_media_id':'story123','feed_media_id':'',
                'data_publicacao':'2026-11-27T09:00:00-03:00'}]
        edital={'id':'novo','data_expiracao':'2026-11-27T15:00:00-03:00'}
        self.assertEqual(forecast_capacity([edital],story,now,10)['previstos_no_horizonte'],1)
        edital['data_expiracao']='2026-11-27T12:00:00-03:00'
        self.assertEqual(forecast_capacity([edital],story,now,10)['previstos_no_horizonte'],0)
        edital['data_expiracao']='2026-12-04'
        self.assertEqual(forecast_capacity([edital],story,now,10)['previstos_no_horizonte'],1)


if __name__ == '__main__':
    unittest.main()
