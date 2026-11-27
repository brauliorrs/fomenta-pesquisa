import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from src.services.stage6_urgent_exception import select_urgent_exception, feed_batches_today

NOW=datetime(2026,11,27,14,tzinfo=ZoneInfo('America/Sao_Paulo'))
HISTORY=[{'edital_id':'old','status':'success','feed_media_id':'carrossel_a',
          'data_publicacao':'2026-11-27T10:00:00-03:00'}]
APPROVAL={'versao':1,'data':'2026-11-27','autorizada':True,
          'responsavel':'editor','justificativa':'Risco documentado de perda de prazo nesta data.',
          'ids_autorizados':['a']}
CANDIDATE={'id':'a','titulo':'Chamada de projetos científicos', 'status':'novo',
           'data_expiracao':'2026-11-28', 'pronto_para_postagem':True}

class Stage6UrgentTests(unittest.TestCase):
    def check(self, **changes):
        opts=dict(eligible_unpublished=[CANDIDATE],history=HISTORY,
                  now=NOW,daily_limit=10,enabled=True,policy=APPROVAL)
        opts.update(changes)
        return select_urgent_exception(**opts)

    def test_sem_autorizacao_nao_publica(self):
        self.assertEqual(self.check(enabled=False)[0],[])
        self.assertEqual(self.check(policy=dict(APPROVAL,autorizada=False))[0],[])
        self.assertEqual(self.check(policy=dict(APPROVAL,justificativa='curta'))[0],[])
        self.assertEqual(self.check(policy=dict(APPROVAL,data='2026-11-28'))[0],[])

    def test_um_carrossel_ja_publicado_exigido(self):
        self.assertEqual(len(self.check()[0]),1)
        self.assertEqual(self.check(history=[])[0],[])
        self.assertEqual(self.check(history=HISTORY+[
            dict(HISTORY[0],feed_media_id='carrossel_b')])[0],[])

    def test_mesma_midia_varios_itens_conta_uma_publicacao(self):
        self.assertEqual(feed_batches_today(HISTORY+[
            dict(HISTORY[0],edital_id='outro')],NOW),1)

    def test_prazo_vencido_ou_longo_nao_gera_excecao(self):
        self.assertEqual(self.check(eligible_unpublished=[
            dict(CANDIDATE,data_expiracao='2026-11-26')])[0],[])
        self.assertEqual(self.check(eligible_unpublished=[
            dict(CANDIDATE,data_expiracao='2026-12-05')])[0],[])

    def test_urgencia_precisa_e_limite_fuso(self):
        self.assertEqual(len(self.check(eligible_unpublished=[
            dict(CANDIDATE,data_expiracao='2026-11-27T20:00:00-03:00')])[0]),1)
        self.assertEqual(self.check(eligible_unpublished=[
            dict(CANDIDATE,data_expiracao='2026-11-27T14:00:00-03:00')])[0],[])

    def test_sem_repost_ou_mais_dez_itens(self):
        self.assertEqual(self.check(history=HISTORY+[
            dict(HISTORY[0],edital_id='a')])[0],[])
        entries=[dict(CANDIDATE,id=str(i)) for i in range(11)]
        self.assertEqual(self.check(eligible_unpublished=entries,policy=dict(
            APPROVAL,ids_autorizados=[str(i) for i in range(11)]))[0],[])

    def test_limite_zero_e_registro_fora_da_fila_bloqueados(self):
        self.assertEqual(self.check(daily_limit=0)[0],[])
        self.assertEqual(self.check(eligible_unpublished=[])[0],[])


if __name__=='__main__':
    unittest.main()
