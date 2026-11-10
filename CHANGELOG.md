# CHANGELOG

Formato inspirado em Keep a Changelog; versionamento semântico.

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
