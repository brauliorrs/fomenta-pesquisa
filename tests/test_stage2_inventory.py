import unittest

from src.services.stage2_inventory import build_stage2_inventory


def entry(id, source='FAP', url='https://fap.example/editais/a', **changes):
    return {'id': id, 'titulo': id, 'fonte': source, 'link': url,
            'data_expiracao': None, 'bloqueio_editorial_definitivo': False, **changes}


class Stage2InventoryTests(unittest.TestCase):
    def test_preserva_todos_os_sem_prazo_e_fora_do_catalogo(self):
        rows = [entry('a'), entry('b'), entry('c', url=''), entry('d', url='https://fap.example/editais')]
        audit = {'registros': {'a': {
            'classificacao': 'sem_evidencia_de_inscricao',
            'link_cadastrado': 'https://fap.example/editais/a',
            'verificado_em': '2026-11-27T09:00:00-03:00',
        }}}
        manual = {'registros': {
            'b': {'decisao': 'prazo_localizado_verificacao', 'prazo_candidato': '2027-01-08',
                  'fundamento': 'Fonte oficial', 'fontes_oficiais': ['https://oficial.example/']},
            'z': {'titulo': 'Antigo', 'fundamento': 'Fora do catalogo'},
        }}
        result = build_stage2_inventory(rows, audit, manual, '2026-11-27T09:00:00-03:00')
        self.assertEqual(result['sumario']['sem_prazo_atuais'], 4)
        self.assertEqual(result['sumario']['com_auditoria_de_link'], 1)
        self.assertEqual(result['sumario']['casos_historicos_fora_do_catalogo'], 1)
        states = {x['id']: x['status'] for x in result['registros']}
        self.assertEqual(states['a'], 'nao_extraido_do_link')
        self.assertEqual(states['b'], 'prazo_localizado_verificacao')
        self.assertEqual(states['c'], 'link_ausente')
        self.assertEqual(states['d'], 'pagina_agregadora_nao_e_edital')
        self.assertTrue(all(not x['publicacao_autorizada'] for x in result['registros']))

    def test_link_alterado_invalida_prova_antiga(self):
        item = entry('a', url='https://fap.example/novo')
        audit = {'registros': {'a': {'link_cadastrado': 'https://fap.example/antigo',
                                    'classificacao': 'possivel_recuperacao',
                                    'datas_identificadas': ['2027-01-09']}}}
        result = build_stage2_inventory([item], audit, {}, '2026-11-27T09:00:00-03:00')
        self.assertEqual(result['registros'][0]['status'], 'link_alterado_requer_nova_auditoria')
        self.assertFalse(result['registros'][0]['auditoria_automatica_executada'])

    def test_nenhum_aviso_sem_data_equivale_ausencia_comprovada(self):
        result = build_stage2_inventory(
            [entry('a')],
            {'registros': {'a': {'classificacao': 'sem_evidencia_de_inscricao',
                                 'link_cadastrado': 'https://fap.example/editais/a'}}},
            {}, '2026-11-27T09:00:00-03:00')
        self.assertEqual(result['registros'][0]['status'], 'nao_extraido_do_link')
        self.assertNotIn('ausencia_real', str(result['registros'][0]))

    def test_prazo_passado_nao_reabre_nem_autoriza_postagem(self):
        result = build_stage2_inventory(
            [entry('a')],
            {'registros': {'a': {'classificacao': 'prazo_de_inscricao_ja_decorrido',
                                 'link_cadastrado': 'https://fap.example/editais/a',
                                 'datas_identificadas': ['2026-08-09']}}},
            {}, '2026-11-27T09:00:00-03:00')
        row = result['registros'][0]
        self.assertEqual(row['status'], 'prazo_de_inscricao_encerrado')
        self.assertFalse(row['publicacao_autorizada'])


if __name__ == '__main__':
    unittest.main()
