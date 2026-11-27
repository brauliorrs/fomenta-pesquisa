# Auditoria da etapa 2 — Bot Editais
**Data de referência:** 27/11/2026, 15h10 BRT  
**Repositório:** `brauliorrs/fomenta-pesquisa`  
**Natureza:** auditoria técnica de 100% dos registros do catálogo e confronto oficial dirigido; **não é homologação documental de todos os links**.  
**Regra vigente da etapa 2:** o bot verifica a vigência de `data_expiracao` atualizada; nenhuma homologação manual adicional é exigida para a checagem temporal. A triagem para publicação mantém os filtros contra resultados, notícias, páginas agregadoras, duplicidades, falta de prontidão e republicações indevidas.

## Parecer
**Conclusão: CONFORMIDADE PARCIAL; recomendar correção da recuperação de datas antes de considerar a qualidade dos dados satisfatória.**  
A regra de bloqueio temporal funciona conforme o escopo simplificado, mas não soluciona a ausência de data na maioria dos registros. A conclusão técnica da etapa 2 na issue #10 não comprova a homologação documental integral nem a recuperação automática de prazos.

## 1. Conferência de todos os registros atuais
Arquivos analisados em `main`: `data/editais.json`, `data/inventario_sem_prazo_etapa2.json`, `data/auditoria_prazos.json`, `data/holds_etapa2_20261127.json`, `data/confrontos_oficiais_etapa2.json`, `data/homologacoes_etapa2.json` e código da fila e do guard.

| Indicador | Quantidade | Observação |
|---|---:|---|
| Registros no catálogo | **237** | Conferência de IDs e prazos no catálogo |
| Sem `data_expiracao` | **208 (87,8%)** | Bloqueados para publicação pelo guard temporal |
| Com prazo futuro | **28** | Todos já com marca de publicação no feed; **0 inéditos aptos** entre esses registros |
| Com prazo decorrido (data sem hora) | **1** | Registro histórico publicado e não pronto |
| Sem prazo, com auditoria do mesmo link | **166** | Auditoria **automática**, não validação oficial |
| Sem prazo, sem consulta automática documentada | **42** | Lacuna de cobertura (20,2% dos 208) |
| Registros em HOLD do snapshot | **208/208** | HOLD provisório; não representa 208 revisões conclusivas |
| Aprovações no registro legado de homologações | **0** | A política de homologação não é mais o gate da regra simplificada |
| Publicados historicamente sem prazo atual | **2** | IPEA PROCIN 002/2026 e 003/2026, ambos não prontos; preservar histórico |

**Consistência estrutural:** o inventário contém exatamente os 208 IDs do catálogo sem prazo; o arquivo de HOLD cobre esses 208, sem lacunas. Para os 166 registros com auditoria automática, a URL registrada coincide com a URL atualmente catalogada. **Essa coincidência não garante que a URL seja o documento correto nem que a inscrição esteja aberta.**

### Classificação dos 208 sem prazo (snapshot de 09h35 BRT)
| Diagnóstico | Quantidade |
|---|---:|
| Falha de acesso ou formato | 69 |
| Prazo não extraído do link | 52 |
| Prazo de inscrição já decorrido | 43 |
| Não verificado | 27 |
| Bloqueio editorial a conferir | 13 |
| Inscrições encerradas confirmadas por errata | 1 |
| Página agregadora, não edital | 1 |
| Prazo de formulário oficial candidato à recuperação | 1 |
| Prazo encontrado aguardando revisão de fase/elegibilidade | 1 |
| **Total** | **208** |

**Concentração por fonte dos registros sem prazo:** FAPERN 39, FAPAC 28, CONFAP 27, IPEA 23, FACEPE 20 e FAPESQ 15. Essas seis fontes somam **152 dos 208**, recomendando investigação por extrator e origem, não apenas casos isolados.

## 2. Confrontos oficiais prioritários
| Registro / ID | Constatação e referência oficial | Tratamento correto |
|---|---|---|
| **FAPESB 019/2026 Ciência na Mesa 5** — `fundacao_de_amparo_a_pesquisa_do_estado__70bb5a90` | Errata 04 (29/10/2026), disponibilizada em https://www.fapesb.ba.gov.br/wp-content/uploads/2019/08/Errata_4_CNM_5.pdf : **preenchimento/conclusão do formulário até 16/12/2026 às 17h**, encaminhamento da proposta/documentos até **18/12/2026 às 23h59**. A página da chamada destina-se a ICTs do Estado da Bahia: https://www.fapesb.ba.gov.br/edital-no-0192026-ciencia-na-mesa-5-base-de-dados-e-sistemas-de-informacoes-para-tomada-de-decisao-em-soberania-alimentar-e-nutricional/ | **Falha de recuperação de dado**: catálogo segue sem data. Se vier a ser atualizado com provas completas de escopo, registrar o primeiro marco para **novas propostas**, 16/12 às 17h; não confundir com prazo de documentos. **Não publicar sem verificação editorial do tipo de chamada e público** |
| **EMBRAPII/Petrobras 02/2026 Economia Circular** — `empresa_brasileira_de_pesquisa_e_inovaca_d7e4e002` | A página oficial https://embrapii.org.br/chamadas-publicas/chamada-publica-n02-2026-para-projetos-de-alto-impacto-em-economia-circular/ confirma **pré-propostas entre 18/11/2026 e 08/01/2027 pelas Unidades EMBRAPII**; envolve consórcios, no mínimo duas Unidades EMBRAPII e empresa/startup. | **Falha de recuperação de dado**: catálogo segue sem data. Se aprovado para divulgação, informar a fase e a restrição de quem submete. Não apresentar como inscrição direta aberta a qualquer pesquisador |
| **FAPESB 018/2026** — `fundacao_de_amparo_a_pesquisa_do_estado__5bb9e677` | Confronto anterior na base oficial aponta encerramento em **08/10/2026, 17h**, mediante errata, com etapas administrativas posteriores | Manter encerrado/bloqueado; não confundir cronograma de resultados ou contratação com inscrições |
| **FAPEMIG SEDE 018/2026 HubMG GOV** — fora do catálogo | A base de confrontos registra divergência entre quadro-resumo antigo e cronograma retificado de várias fases | Manter histórico fora da fila até reconciliação da retificação e da fase |

**Escopo da verificação:** a Errata 04 FAPESB foi conferida diretamente; EMBRAPII pela página institucional com cronograma. Outros casos não foram revisados oficialmente nesta rodada. Os dois prazos reconhecidos nos confrontos já estavam no arquivo histórico, mas **não foram gravados em `data/editais.json`**. Nenhum registro foi promovido à publicação nesta auditoria.

## 3. Auditoria do fluxo de publicação
**Conformidades observadas**
1. `opportunity_gate` verifica status encerrado, fase pós-seleção, data de abertura futura, ausência/erro de prazo, vencimento e horário quando informado.
2. Na data de encerramento **sem hora confirmada**, a publicação é suspensa por precaução.
3. `PublicationQueueService` só inclui na Fila 1 os não publicados com `pronto_para_postagem` e `opportunity_gate` aprovados.
4. `publish_pending.py` repete o guard ao preparar a publicação de feed/story. Histórico e proteção de repostagem são mantidos.
5. Nenhum dos 208 sem prazo está marcado como pronto: a ausência da data não é contornada por um simples flag.

**Lacunas identificadas**
- **ALTA — recuperação incompleta:** `data_expiracao` permanece vazia em 208 registros; dois têm datas oficiais de candidatura documentadas em confrontos, mas não foram incorporados ao catálogo. Logo, a verificação temporal não corrige o dado ausente.
- **ALTA — erros de acesso em escala:** 69 registros diagnosticados com falha de acesso/formato e 52 com prazo não extraído, sujeitos a melhorias nos extratores e recuperação de PDFs. **Esses diagnósticos não demonstram ausência de prazo na origem**.
- **MÉDIA — cobertura:** 42 sem leitura automática documentada. O encerramento simplificado da etapa 2 deve ser descrito como **homologação do gate**, não auditoria documental encerrada.
- **MÉDIA — múltiplas fases:** uma data cronologicamente futura pode ser de resultado, contratação, recurso ou entrega secundária, não de **novas inscrições**. O gate não infere essa semântica a partir de uma data isolada.
- **MÉDIA — estado contraditório após prorrogação:** se o catálogo receber prazo novo, mas conservar status `encerrado`, o gate continuará bloqueando. O tratamento de prorrogação precisa revisar conjuntamente status, abertura e prazo.
- **BAIXA — ambiguidade documental:** `inventario_sem_prazo_etapa2.json` mantém `status_etapa=EM_ANDAMENTO` e `revisao_editorial_concluida=false`; isso reflete o escopo histórico mais amplo e **não contradiz** a homologação técnica simplificada, desde que a distinção seja mantida nos relatórios. `homologacoes_etapa2.json` e `stage2_publication_guard.py` permanecem como legado, fora do gate central.

## 4. Ações priorizadas, sem autorizar publicação
1. **P0** — corrigir a reconciliação entre data encontrada, fase oficial, errata e campo `data_expiracao`, inicialmente nos dois candidatos corroborados. Registrar a proveniência da data e manter revisão editorial do público e fase.
2. **P1** — executar recuperação de falhas de leitura por fonte (HTTP 403, PDF e documentos longos), priorizando as seis instituições responsáveis por 152 sem prazo.
3. **P1** — visitar os 42 registros não auditados e distingui-los de títulos que são notícias, resultados, eventos ou páginas de listagem.
4. **P1** — incluir teste de prorrogação que reavalie `status` e `data_expiracao` conjuntamente e teste da fase de inscrição vs resultado/contratação.
5. **P2** — reconciliar documentos de status histórico, removendo rótulos que possam sugerir que 208 revisões documentais foram homologadas.

## 5. Critério de conclusão da auditoria corretiva
O **gate temporal** foi homologado na etapa 2 simplificada. A correção da qualidade de dados terá aceite próprio apenas após: (a) rastreabilidade do documento oficial e da fase para datas recuperadas; (b) testes negativos contra publicação de resultados, inscrições encerradas e escopo inelegível; (c) métricas comparáveis por fonte; (d) ausência de publicação/repost não autorizado. **Não reabrir automaticamente a etapa 2 técnica nem declarar os 208 revisados individualmente.**

**Estado desta revisão:** auditoria de catálogo e código concluída; confrontos oficiais direcionados concluídos; recuperação massiva e saneamento documental **pendentes**; nenhuma publicação real acionada.
