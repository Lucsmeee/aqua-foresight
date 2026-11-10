# Aqua Foresight

Plataforma GovTech de **apoio à decisão** para risco de escassez hídrica, com piloto no Distrito Federal (reservatórios **Descoberto** e **Santa Maria**), ENOS/El Niño como eixo de pesquisa e regras jurídicas auditáveis.

> **Status: v0.4.0.** Pipeline ponta a ponta (coleta → processamento → armazenamento → análise → indicadores → página) com execução diária no GitHub Actions. Nada aqui é previsão validada. Nenhum componente emite ato administrativo, declara estado hidrológico oficial ou notifica terceiros. Toda saída é indicativa e exige revisão humana (Especificação v2.0, §2.2 e §7).

## Como funciona no GitHub

```
GitHub Actions (todo dia 06:41 BRT, ou ao enviar planilha)
  ├─ baixa RONI do NOAA/CPC ............ público, sem chave
  ├─ atualiza série SAR/ANA do DF ...... cota e volume de Descoberto e Santa Maria (API do portal SAR)
  ├─ lê data/manual/volume/*.csv|xlsx .. planilhas adicionais (ex.: série oficial da ADASA)
  ├─ consulta API ANA HidroWebService .. só se houver secrets ANA_IDENTIFICADOR/ANA_SENHA
  ├─ valida, guarda brutos com SHA-256 em data/raw (commit só quando o conteúdo muda)
  ├─ calcula fases ENOS e enquadramento pela Res. ADASA 56/2025
  └─ publica site/ no GitHub Pages: index.html + data/*.json
```

### Ativar (uma vez)

1. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
2. **Actions → Pipeline diário → Run workflow** para a primeira execução.
3. Opcional, API da ANA: peça acesso por e-mail a `hidro@ana.gov.br` com o assunto `<seu CPF> - Solicitação de acesso à API HidroWebService para consumo de dados`. Com a senha, crie em **Settings → Secrets and variables → Actions** os secrets `ANA_IDENTIFICADOR` (CPF) e `ANA_SENHA`.

### Enviar dados de volume

Coloque CSV ou XLSX em `data/manual/volume/` (Add file → Upload files). O envio dispara o pipeline. Detalhes em [`data/manual/volume/README.md`](data/manual/volume/README.md).

## O que já funciona

| Componente | Situação |
|---|---|
| Esquema de banco (SQLite dev / PostgreSQL 16 testado) | ✅ 8 tabelas, proveniência e versões |
| Adaptador NOAA/CPC RONI e ONI | ✅ código e testes; download real roda no GitHub Actions |
| Série diária SAR/ANA do DF desde 1990 (`data/series/`) | ✅ carga histórica e atualização diária |
| Conversão do Descoberto para a base ADASA | ⚠️ estimativa calibrada em 6 datas (erro ≤ 0,26 p.p.); confirmar com série oficial |
| Leitor de planilhas de volume útil (SAR/ANA, ADASA) | ✅ CSV e XLSX, validação com motivos de rejeição |
| Cliente API ANA HidroWebService (telemetria) | ✅ código e testes com servidor simulado; ⚠️ não testado com credencial real; traz **cota**, não volume útil |
| Fases ENOS (critério CPC: ±0,5 °C por ≥5 estações) | ✅ |
| Base normativa Res. ADASA 56/2025, Tabela 1 completa | ✅ conferida em 2 fontes oficiais; ⚠️ revisão jurídica e vigência pendentes (D-05) |
| Motor de enquadramento indicativo | ✅ |
| Comparação DF × Júcar (`web/comparacao.html`) | ✅ MITECO (reservas semanais desde 1988) e CHJ (índice de escassez mensal) |
| Painel público (`web/index.html`) | ✅ resumo em linguagem simples, reservatórios, histórico com faixas de estado, mesmo dia em outros anos, El Niño |
| Página técnica (`web/tecnico.html`) | ✅ etapas do pipeline, proveniência, envio de arquivos, auditoria |
| API FastAPI e CLI `aqua` | ✅ |
| CI (pytest em SQLite e PostgreSQL/PostGIS) | ✅ |
| Modelos preditivos A × B | ⏳ |

## Rodar localmente

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                                   # 63 testes

aqua publicar --saida site               # pipeline completo; abra site/index.html com um servidor local
python -m http.server -d site 8000       # http://localhost:8000

aqua init-db
aqua ingest-enos --indicador RONI        # ou --arquivo ~/Downloads/RONI.ascii.txt
aqua enquadrar descoberto 28.4 --natureza observado --data-referencia 2026-11-10 --data-dado 2026-11-09
uvicorn aqua_foresight.api.main:app_factory --factory --reload   # http://localhost:8000/docs
```

Com PostgreSQL/PostGIS: `cp .env.example .env && docker compose up -d --build`.

## Estrutura

```
src/aqua_foresight/
  ingestion/   provenance.py, noaa_cpc.py, volume_arquivo.py, ana_hidrowebservice.py
  enso/        fases ENOS
  legal/       Res. ADASA 56/2025, motor de enquadramento
  db/          modelos e sessão
  api/         FastAPI
  publicar.py  orquestrador da execução agendada
  cli.py       comando `aqua`
web/index.html             painel público
web/tecnico.html           detalhes técnicos do pipeline
data/raw/                  brutos versionados (proveniência)
data/manual/volume/        planilhas de volume útil
.github/workflows/         ci.yml, pipeline-diario.yml
docs/ARCHITECTURE.md       arquitetura, dados, integrações, ENOS, jurídico
```

## Documentos de continuidade

`ROADMAP.md` · `PROGRESS.md` · `CHANGELOG.md` · `NEXT_STEPS.md` · `docs/ARCHITECTURE.md`.

## Regras do projeto

Fontes oficiais primeiro; nunca inventar dados, normas, endpoints ou resultados; dado sintético sempre marcado; observação ≠ projeção ≠ simulação; IA nunca decide ato administrativo.
