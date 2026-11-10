# PROGRESS — histórico de entregas

## Execução 1 — 10/11/2026 · v0.1.0

**Fase:** 1 (Infraestrutura) com fatias verticais das Fases 2 e 5.

**Ponto de partida:** projeto continha apenas a Especificação v2.0; nenhum código, repositório ou registro anterior.

**Entregue**
- Pacote Python `aqua_foresight` (pyproject, config por variáveis `AQUA_*`, CLI `aqua`).
- Esquema com 8 tabelas: proveniência por ingestão (vintage), natureza do dado, base normativa, auditoria.
- Adaptador NOAA/CPC RONI/ONI: download ou arquivo local, bruto preservado com SHA-256, validação de formato/continuidade/faixa, deduplicação por checksum, vintages, marcação de valores provisórios.
- Classificador de fases ENOS pelo critério CPC, com sinalização de episódio em curso não confirmado.
- Res. ADASA 56/2025, Tabela 1 completa, conferida em duas fontes oficiais (ADASA SEI 178925819 e DODF nº 157 de 21/08/2025).
- Motor de enquadramento indicativo com bloqueios, ressalvas e auditoria.
- API FastAPI: `/health`, `/fontes`, `/enos/{RONI|ONI}`, `/normas`, `/limiares/{reservatorio}`, `POST /enquadramento`, `/auditoria`.
- Dockerfile, docker-compose (PostGIS 16-3.4), Makefile, `.env.example`.
- Documentação: README, ROADMAP, NEXT_STEPS, CHANGELOG, docs/ARCHITECTURE.md (diagrama Mermaid, dicionário, integrações, ENOS, jurídico).

**Validação**
- 38 testes pytest: 38/38 em SQLite e 38/38 em PostgreSQL 16.15 local.
- O teste em PostgreSQL revelou um campo `VARCHAR(48)` estourado que o SQLite aceitava — corrigido.
- Execução ponta a ponta (CLI + uvicorn + PostgreSQL): base normativa carregada, enquadramento auditado, tentativa real de download do CPC registrada como `falha` (`ProxyError: 403`), conector marcado `falha`, `/enos/RONI` retorna 404 em vez de dado falso.

**Limitações**
- Nenhum dado real ingerido ainda (rede do ambiente bloqueia cpc.ncep.noaa.gov).
- Build Docker não executado (sem daemon no ambiente).
- Vigência e texto integral da Res. ADASA 56/2025 sem revisão jurídica humana.
- Sem Alembic; sem séries locais; sem modelos.

## Execução 1b — 10/11/2026 · v0.2.0

**Pedido:** pipeline funcionando em HTML com dados reais e conexão a APIs; subir o projeto para o GitHub do usuário.

**Entregue**
- Pipeline no navegador (6 etapas) publicado como artefato e incorporado ao repositório em `web/index.html`.
- Orquestrador `aqua publicar` + workflow diário no GitHub Actions: baixa o RONI (público), lê planilhas de volume versionadas, consulta a API da ANA se houver credencial, versiona brutos novos e publica no GitHub Pages.
- Leitor de CSV/XLSX de volume útil e cliente da API ANA HidroWebService.
- CI com pytest em SQLite e PostgreSQL/PostGIS.

**Pesquisa de fontes**
- RONI: arquivo público sem chave (CPC).
- ANA HidroWebService: API oficial com credencial pedida por e-mail (hidro@ana.gov.br); autenticação por cabeçalhos Identificador/Senha, token de 60 min; série telemétrica traz cota, vazão e chuva, não volume útil.
- SAR/ANA: módulo DF exporta a tabela do dia em CSV; sem API documentada; o manual v1.1 não inclui o DF na área de dados históricos.

**Validação**
- 51/51 testes em SQLite e PostgreSQL 16.15; 15 testes Node do núcleo JS da página.
- Simulação da execução agendada com download simulado: 3 fontes com status correto; página servida por HTTP carregou os JSON publicados sem erros.

**Limitações**
- Download real do CPC e workflow ainda não executados no GitHub (primeira execução após o push).
- Cliente ANA não testado com credencial real; códigos de estação a confirmar; cota sem curva cota-volume.
- Série histórica de volume útil do DF ainda sem fonte automatizável.

## Execução 1c — 10/11/2026 · v0.3.0

**Pedido:** buscar todos os dados e versionar para gerar os gráficos.

**Entregue**
- Repositório no GitHub (Lucsmeee/aqua-foresight) com CI verde (SQLite e PostGIS) e RONI real versionado pelo robô.
- Workflow de diagnóstico de fontes, usado para localizar a API não documentada do SAR/ANA (restportal) a partir do código do portal.
- Adaptador SAR/ANA e carga histórica diária desde 1990 em `data/series/sar_df_diario.csv`.
- Conversão do Descoberto para a base ADASA (calibrada em 6 datas, erro ≤ 0,26 p.p.) e recálculo pela cota; Santa Maria validado como igual à ADASA.
- Página com dados reais: cartões de situação, gráfico com limiares mensais, seletor de período e lacunas visíveis.

**Achados**
- API do SAR lê a data como MM/dd/yyyy e devolve a próxima medição disponível; dados esparsos antes dos anos 2000.
- SIRH/ADASA inacessível a partir do GitHub Actions.
- Curva cota-volume do Descoberto no SAR mudou entre épocas.

**Validação**: 63 testes; publicação local com dados reais e página renderizada sem erros.

## Execução 1d — 10/11/2026 · v0.3.1 / v0.4.0

**Pedidos:** painel mais convidativo e fácil de entender; comparação com a Espanha para a analogia jurídica e hidrológica.

**Decisão D-02:** bacia espanhola = **Júcar** (Confederación Hidrográfica del Júcar), escolhida pelo usuário.

**Entregue**
- Painel em linguagem simples (`web/index.html`): frase-resumo, tanques com as linhas de limite, gráfico com faixas coloridas, "mesmo dia em outros anos", termômetro do ENOS. Página técnica movida para `web/tecnico.html`.
- Fontes espanholas reais:
  - MITECO, Boletín Hidrológico (`BD-Embalses.zip`, base Access): reserva semanal por reservatório desde 1988 → `data/series/es_jucar_semanal.csv` (demarcação e sistema Alarcón + Contreras + Tous).
  - CHJ, informe mensal do Plan Especial de Sequía: Índice de Estado de Escasez (IEE) por unidade territorial e global → `data/series/es_jucar_pes_mensal.csv`, com conferências internas das tabelas.
- Página `web/comparacao.html`: hoje lado a lado em escala comum (Normal/Atenção/Crítico), volumes DF × Júcar, IEE mensal com faixas e quadro das regras (autoridade, norma, indicador, níveis, seca × escassez, declaração formal).
- Workflow `carga-espanha.yml`; etapa Espanha no pipeline diário.

**Achados**
- Variação média dentro do ano: Descoberto ≈ 41 p.p.; sistema Alarcón–Contreras–Tous ≈ 17 p.p. (reserva plurianual).
- Brasil/DF: uma variável (volume %), limiares mês a mês na própria resolução; Vermelho já declara escassez. Espanha/Júcar: índice composto 0–1, faixas fixas, exige persistência, separa seca (natural) de escassez (gestão); situação excepcional declarada por ato do Presidente da CHJ (art. 27 Lei 10/2001).
- CHJ só publica o informe mais recente em endereço fixo; o MITECO grafa "Tous - La Ribera".

**Validação**: 67 testes; site gerado com dados reais e renderizado no navegador sem erros.

**Limitações**
- Equivalência de faixas é didática, não jurídica: os sistemas medem coisas diferentes.
- Série mensal do IEE começa nos informes de 08/2026 e 10/2026; anteriores dependem de arquivo da CHJ.
- Texto da Orden TED/601/2026 e do PES do Júcar sem revisão jurídica humana.
