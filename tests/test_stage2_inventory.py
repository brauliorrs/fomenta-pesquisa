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

    def test_hold_editorial_explica_a_exclusao_por_registro(self):
        item = entry(
            'seminario', bloqueio_editorial_definitivo=True,
            motivo_bloqueio_postagem='Prazo final nao identificado.',
            pendencias_editoriais=[
                'Prazo final nao identificado.',
                'Titulo com perfil de noticia lateral ou institucional.',
            ],
        )
        resultado = build_stage2_inventory(
            [item], {}, {}, '2026-11-27T09:00:00-03:00',
        )
        rec = resultado['registros'][0]
        self.assertEqual(rec['status'], 'bloqueio_editorial_a_conferir')
        self.assertIn('Titulo com perfil de noticia lateral', rec['motivo'])
        self.assertEqual(len(rec['pendencias_editoriais_de_origem']), 2)
        self.assertFalse(rec['publicacao_autorizada'])

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

    def test_recuperacao_com_data_atualizada_respeita_vigencia(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from src.services.opportunity_guard import opportunity_gate
        now = datetime(2026, 11, 27, 12, 0, tzinfo=ZoneInfo('America/Sao_Paulo'))
        candidato = {
            'id': 'recuperado', 'titulo': 'Edital válido', 'status': 'aberto',
            'recuperacao_etapa2': True,
            'homologacao_editorial_etapa2': False,
            'data_expiracao': '2026-12-16T17:00:00-03:00',
        }
        self.assertTrue(opportunity_gate(candidato, now=now)[0])
        candidato['data_expiracao'] = '2026-10-08T17:00:00-03:00'
        self.assertFalse(opportunity_gate(candidato, now=now)[0])
        candidato['data_expiracao'] = None
        self.assertFalse(opportunity_gate(candidato, now=now)[0])

    def test_resumo_p1_distingue_exclusao_editorial_de_link_nao_visitado(self):
        from src.services.p1_operational_report import build_p1_operational_report
        records = [
            {'id':'a','fonte':'FAP','link':'https://fap.org.br/a',
             'data_expiracao':None},
            {'id':'b','fonte':'FAP','link':'https://fap.org.br/b',
             'data_expiracao':None},
            {'id':'premio','fonte':'CAPES','link':'https://capes.gov.br/premio',
             'data_expiracao':None},
        ]
        previous={'registros':{'a':{'link_cadastrado':records[0]['link'],
                         'classificacao':'falha_http_503'}}}
        current={'generated_at':'2026-11-27T16:00:00-03:00',
                 'registros':{'a':{'link_cadastrado':records[0]['link'],
                           'classificacao':'sem_evidencia_de_inscricao'}}}
        inventory={'registros':[
            {'id':'a','fonte':'FAP','status':'nao_extraido_do_link',
             'auditoria_automatica_executada':True},
            {'id':'b','fonte':'FAP','status':'nao_verificado',
             'auditoria_automatica_executada':False},
            {'id':'premio','fonte':'CAPES',
             'status':'bloqueio_editorial_a_conferir',
             'auditoria_automatica_executada':False}
        ], 'sumario':{'status_por_categoria':{'nao_extraido_do_link':1}}}
        report=build_p1_operational_report(records,previous,current,inventory)
        self.assertEqual(report['elegiveis_para_visita'],2)
        self.assertEqual(report['visitados_elegiveis'],1)
        self.assertEqual(report['pendentes_de_visita_elegiveis'],1)
        self.assertEqual(report['ids_pendentes_visita'],['b'])
        self.assertEqual(report['falhas_de_acesso_recuperadas_nesta_execucao'],1)
        self.assertEqual(report['excluidos_da_visita_por_filtro_editorial'],{
            'bloqueio_editorial_a_conferir':1})


if __name__ == '__main__':
    unittest.main()
