# CHANGELOG

Formato inspirado em Keep a Changelog; versionamento semântico.

## [0.3.1] — 2026-11-10

### Alterado
- Novo painel público (`web/index.html`): frase-resumo do estado dos reservatórios, tanques com marcas de atenção e escassez do mês, gráfico com faixas coloridas (normal/atenção/escassez) e seletor de período, comparação com o mesmo dia em anos anteriores e El Niño explicado em escala simples.
- Página anterior passou a ser `web/tecnico.html` (detalhes técnicos).
- `aqua publicar` gera `data/painel.json` compacto e copia todas as páginas de `web/`.

### Corrigido
- Carga SAR aceita a medição anterior mais próxima (comportamento da API a partir de 2010), que interrompia a carga em 2011.

## [0.3.0] — 2026-11-10

### Adicionado
- Fonte **ANA · SAR, Distrito Federal** (`ingestion/ana_sar.py`): API `restportal` usada pelo portal do SAR, identificada e verificada com o workflow `Diagnosticar fontes`. `retornaMedicoes` (data em MM/dd/yyyy; devolve a próxima medição disponível quando o dia não tem) e `retornaGrafico` (últimos 5 anos por reservatório, volume em hm³).
- Série versionada `data/series/sar_df_diario.csv` (cota, volume, capacidade, % SAR) desde 1990, com `sar_df_dias_consultados.txt` para cargas retomáveis.
- Workflows `carga-historica.yml` e `diagnosticar-fontes.yml`; `scripts/diagnosticar_fontes.py`.
- `conversao_adasa.py`: Santa Maria usa o % do SAR (igual à ADASA em 5 datas, ≤ 0,12 p.p.); Descoberto convertido para a base ADASA (linear, 6 pontos de calibração, resíduo ≤ 0,26 p.p.) e recalculado pela cota com a curva atual, porque o SAR usa curvas cota-volume diferentes por época. Valores do Descoberto marcados como **estimados**.
- Página: valor SAR e estimativa ADASA lado a lado; série SAR original no gráfico.

### Corrigido
- Pipeline diário passa a versionar `data/series` e compartilha o grupo de concorrência `dados` com a carga histórica.

## [0.2.0] — 2026-11-10

### Adicionado
- `aqua publicar`: orquestrador que coleta, processa, calcula indicadores e gera `site/` com `index.html` e `data/*.json` (enos, volume, telemetria, indicadores, status).
- Leitor de planilhas de volume útil (`ingestion/volume_arquivo.py`), CSV e XLSX, com as mesmas regras da página.
- Cliente da API ANA HidroWebService (`ingestion/ana_hidrowebservice.py`), ativado por secrets `ANA_IDENTIFICADOR`/`ANA_SENHA`.
- Página do pipeline (`web/index.html`): carrega os dados publicados, mostra a situação de cada fonte automática, aceita arquivos e cai para demonstração sintética marcada quando não há dados.
- Workflows `ci.yml` (pytest em SQLite e PostGIS) e `pipeline-diario.yml` (coleta diária, versionamento de brutos, deploy no GitHub Pages).
- 13 testes novos (51 no total).

### Alterado
- `preservar_bruto` passou a ser idempotente por SHA-256: conteúdo repetido não gera nova cópia (evita commits diários sem mudança).
- `data/raw/` agora é versionado no Git (fonte de verdade da proveniência).

## [0.1.0] — 2026-11-10

### Adicionado
- Estrutura do pacote `aqua_foresight`, `pyproject.toml`, CLI `aqua` (`init-db`, `ingest-enos`, `enquadrar`).
- Modelos SQLAlchemy: `fonte_dado`, `ingestao`, `indice_enos`, `reservatorio`, `serie_observada`, `norma_juridica`, `limiar_estado_hidrologico`, `registro_auditoria`.
- Adaptador NOAA/CPC (RONI, ONI) com preservação de bruto, SHA-256, vintages e valores provisórios.
- Classificação de fases ENOS (critério CPC).
- Base normativa Res. ADASA nº 56/2025 (Tabela 1 completa e art. 2º).
- Motor de enquadramento indicativo com distinção observado/projetado e bloqueios.
- API FastAPI com 7 endpoints e OpenAPI.
- Dockerfile, docker-compose com PostGIS, Makefile, `.env.example`.
- 38 testes; suporte a `AQUA_TEST_DATABASE_URL` para rodar contra PostgreSQL.

### Corrigido
- `norma_juridica.status_verificacao` ampliado para `VARCHAR(64)` e código de status encurtado (falhava em PostgreSQL).
- Modelo de entrada do `POST /enquadramento` movido para o nível do módulo (FastAPI não resolvia a anotação adiada e tratava o corpo como query).
