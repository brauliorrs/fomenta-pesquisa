"""Testes integrados negativos/positivos do registro editorial para feed/story."""
import unittest
from unittest.mock import patch, Mock
from datetime import datetime
from zoneinfo import ZoneInfo

from src.services.stage2_publication_guard import stage2_block_reason
from src.services.opportunity_guard import opportunity_gate
from src.publish_pending import eligible_for_publication, attempt_feed_batch_publication
from src.services.publication_queue_service import already_published


class Stage2PublicationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.edital = {
            'id': 'fapesb_019_teste', 'titulo': 'Edital pesquisa e inovacao',
            'status': 'aberto', 'link': 'https://oficial.example/edital',
            'data_expiracao': '2026-12-16T17:00:00-03:00',
            'pronto_para_postagem': True, 'instagram_asset': 'imagem.png',
        }
        self.now = datetime(2026, 11, 27, 12, tzinfo=ZoneInfo('America/Sao_Paulo'))
        self.homologado = {
            'id': self.edital['id'], 'decisao': 'HOMOLOGADO',
            'link_catalogado': self.edital['link'],
            'prazo_homologado': self.edital['data_expiracao'],
            'fase': 'inscricoes', 'responsavel': 'revisor',
            'homologado_em': '2026-11-27T12:00:00-03:00',
            'fontes_oficiais': ['https://oficial.example/documento.pdf'],
        }

    def test_registro_historico_hold_nao_substitui_verificacao_de_vigencia(self):
        with patch('src.services.stage2_publication_guard.stage2_ids', return_value=frozenset([self.edital['id']])), patch('src.services.stage2_publication_guard.stage2_approvals', return_value={}):
            self.assertNotEqual(stage2_block_reason(self.edital), '')
            # HOLD historico nao substitui a verificacao temporal do prazo.
            self.assertTrue(opportunity_gate(self.edital, now=self.now)[0])

    def test_homologacao_vinculada_ao_id_link_prazo_e_fase(self):
        with patch('src.services.stage2_publication_guard.stage2_ids', return_value=frozenset([self.edital['id']])), patch('src.services.stage2_publication_guard.stage2_approvals', return_value={self.edital['id']:self.homologado}):
            self.assertEqual(stage2_block_reason(self.edital), '')
            self.assertTrue(opportunity_gate(self.edital, now=self.now)[0])
            for field, bad in [('link','https://outra.example/'),('data_expiracao','2027-01-01')]:
                variant = dict(self.edital, **{field:bad})
                self.assertNotEqual(stage2_block_reason(variant), '')
            self.assertFalse(opportunity_gate(dict(self.edital, data_expiracao='2026-10-01'),now=self.now)[0])
            self.assertTrue(already_published(dict(self.edital, instagram_feed_publicado=True), set()))
            self.assertTrue(already_published(self.edital, {self.edital['id']}))

    def test_sem_politica_falha_fechado(self):
        with patch('src.services.stage2_publication_guard.stage2_ids', side_effect=FileNotFoundError()):
            self.assertNotEqual(stage2_block_reason(self.edital), '')
        with patch('src.services.stage2_publication_guard.stage2_ids', return_value=frozenset([self.edital['id']])),patch('src.services.stage2_publication_guard.stage2_approvals',side_effect=ValueError()):
            self.assertNotEqual(stage2_block_reason(self.edital), '')

    def test_novo_recuperado_precisa_de_registro_editorial(self):
        candidate=dict(self.edital,recuperacao_etapa2=True)
        with patch('src.services.stage2_publication_guard.stage2_ids',return_value=frozenset()),patch('src.services.stage2_publication_guard.stage2_approvals',return_value={}):
            self.assertNotEqual(stage2_block_reason(candidate),'')
