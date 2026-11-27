import json
import unittest
from pathlib import Path
from unittest.mock import patch

from src.services.published_editorial_guard import (
    POLICY_PATH, published_repost_block_reason, read_published_decisions,
)
from src.publish_pending import eligible_for_publication, ready_editais
from src.services.publication_queue_service import PublicationQueueService


class PublishedEditorialGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with POLICY_PATH.open(encoding='utf-8-sig') as f:
            cls.data = json.load(f)
        cls.catalog = json.loads(
            (Path(__file__).resolve().parents[1] / 'data/editais.json').read_text(encoding='utf-8-sig')
        )
        cls.by_id = {str(x.get('id')): x for x in cls.catalog}
        historical = json.loads(
            (Path(__file__).resolve().parents[1] / 'data/auditoria_publicados_etapa1_20261126.json')
            .read_text(encoding='utf-8-sig')
        )
        cls.historical_by_id = {row['id']: row for row in historical['itens']}

    @classmethod
    def protected_item(cls, edital_id):
        # O bot remove registros vencidos do catálogo ativo. A proteção
        # editorial, porém, deve continuar válida para IDs históricos.
        item = cls.by_id.get(edital_id)
        if item is None:
            evidence = cls.historical_by_id[edital_id]
            item = {'id': edital_id, 'titulo': evidence['titulo']}
        item = dict(item)
        # Evita um falso positivo: o bloqueio precisa funcionar mesmo se
        # alguém reintroduzir um registro histórico com prazo futuro.
        item.update(
            status='novo', data_abertura='2026-11-01',
            data_expiracao='2099-12-31', pronto_para_postagem=True,
        )
        return item

    def test_29_decisions_and_no_approval(self):
        rows = self.data['registros']
        self.assertEqual(len(rows), 29)
        self.assertTrue(all(not x['liberar_repostagem'] for x in rows.values()))
        self.assertTrue(all(x['motivo'] and x['fonte'] for x in rows.values()))
        self.assertTrue(set(rows).issubset(self.historical_by_id))
        self.assertTrue(set(self.by_id).intersection(rows))
        self.assertTrue(all(
            self.historical_by_id[key]['publicado_feed'] for key in rows
        ))

    def test_reposts_blocked_for_every_historical_item(self):
        rows = self.data['registros']
        for edital_id in rows:
            with self.subTest(edital_id=edital_id):
                edital = self.protected_item(edital_id)
                self.assertTrue(published_repost_block_reason(edital))
                self.assertFalse(eligible_for_publication(edital))
        self.assertFalse(set(rows).intersection({
            x['id'] for x in ready_editais([self.protected_item(edital_id) for edital_id in rows])
        }))

    def test_unlisted_valid_new_opportunity_not_blocked(self):
        item = {
            'id': 'a-new-unique-test-case',
            'titulo': 'Chamada para projetos de pesquisa',
            'resumo': 'Submissao aberta para pesquisadores',
            'status': 'novo',
            'data_abertura': '2026-11-01',
            'data_expiracao': '2099-12-31',
            'pronto_para_postagem': True,
        }
        self.assertEqual(published_repost_block_reason(item), '')
        self.assertTrue(eligible_for_publication(item))

    def test_monitoring_retains_published_with_explicit_hold(self):
        service = PublicationQueueService(None, Path('/tmp/unused-queue.json'))
        item = self.protected_item(next(iter(self.data['registros'])))
        rendered = service._to_queue_item(item, 1, True)
        self.assertTrue(rendered['instagram_feed_publicado'])
        self.assertTrue(rendered['repostagem_bloqueada'])
        self.assertEqual(rendered['validacao_inscricoes'], 'HOLD_editorial_repostagem_suspensa')

    def test_policy_malformed_fails_closed(self):
        with patch('src.services.published_editorial_guard.read_published_decisions', side_effect=ValueError('malformed')):
            with self.assertRaises(ValueError):
                published_repost_block_reason({'id': 'anything'})


if __name__ == '__main__':
    unittest.main()
