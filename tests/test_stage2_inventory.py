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

    def test_fapesb_erratas_confirmam_prazo_e_fase_sem_publicar(self):
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        manual = json.loads((root / 'data/confrontos_oficiais_etapa2.json').read_text(encoding='utf-8'))
        encerrado = manual['registros']['fundacao_de_amparo_a_pesquisa_do_estado__5bb9e677']
        aberto = manual['registros']['fundacao_de_amparo_a_pesquisa_do_estado__70bb5a90']
        self.assertEqual(encerrado['prazo_formulario'], '2026-10-08T17:00:00-03:00')
        self.assertEqual(encerrado['fase'], 'inscricoes_encerradas')
        self.assertEqual(aberto['prazo_formulario'], '2026-12-16T17:00:00-03:00')
        self.assertEqual(aberto['prazo_documentos'], '2026-12-18T23:59:00-03:00')
        self.assertNotEqual(aberto['prazo_formulario'], aberto['prazo_documentos'])
        self.assertTrue(all(
            any(url.lower().endswith('.pdf') for url in row['fontes_oficiais'])
            for row in (encerrado, aberto)
        ))
        rows = [entry(key) for key in (
            'fundacao_de_amparo_a_pesquisa_do_estado__5bb9e677',
            'fundacao_de_amparo_a_pesquisa_do_estado__70bb5a90',
        )]
        inventario = build_stage2_inventory(rows, {}, manual, '2026-11-27T09:00:00-03:00')
        self.assertEqual(inventario['sumario']['confrontos_oficiais_no_catalogo'], 2)
        self.assertTrue(all(not x['publicacao_autorizada'] for x in inventario['registros']))
        self.assertEqual(
            {x['status'] for x in inventario['registros']},
            {'inscricoes_encerradas_confirmadas_por_errata',
             'prazo_de_formulario_comprovado_candidato_a_recuperacao'},
        )

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
