# ROADMAP — Aqua Foresight

Gate de cada fase = critério verificável. Prioridades P0/P1/P2 conforme Especificação v2.0 §11.1.

| Fase | Conteúdo | Gate de conclusão | Status |
|---|---|---|---|
| **1 · Infraestrutura** | Repositório, config, banco, Docker, testes | Suíte verde em SQLite **e** PostgreSQL; `docker compose up` sobe API + PostGIS; migrações Alembic | 🟡 Parcial — CI pronto; falta Alembic e build Docker verificado |
| **2 · Pipeline de dados** | Adaptadores oficiais, ingestão, ETL, qualidade | RONI real ingerido; série de volume útil dos 2 reservatórios com proveniência; indicador de frescor por fonte | 🟡 Em andamento — CPC automático, planilhas de volume, cliente ANA; falta série histórica |
| **3 · Inteligência climática** | Séries ENOS, defasagens, correlações, visualizações | Relatório reproduzível de associação ENOS × variáveis locais por estação e lag | ⏳ |
| **4 · Machine Learning** | Baselines, XGBoost, (LSTM se justificado), A × B, 30/60/90 d, incerteza | Avaliação fora da amostra rolling-origin com métricas por horizonte e comparação A × B | ⏳ |
| **5 · Inteligência jurídica** | Base normativa, enquadramento, competências, minutas, auditoria | Matriz validada por assessoria jurídica (D-05); minuta gerada só como rascunho com trilha | 🟡 Iniciada — Res. ADASA 56/2025 + motor indicativo |
| **6 · Plataforma web** | Dashboard, Mapa, Observatório ENOS, Compliance, Simulador, Auditoria | RF-01 a RF-09 com testes de aceitação §13.1 | 🟡 Página do pipeline publicada no GitHub Pages |
| **7 · Integração e validação** | Integração front/back, segurança, MVP, Brasil–Espanha | Avaliação do MVP e estudo comparativo (Segura ou Júcar, D-02) | ⏳ |

## Ordem imediata (P0)

1. RONI real no banco (rodar `aqua ingest-enos` com rede, ou `--arquivo`).
2. Adaptador de volume útil diário dos reservatórios (fonte oficial a confirmar: ADASA ou ANA).
3. Alembic + build Docker verificado.
4. Endpoint `/situacao/{reservatorio}`: última observação válida + frescor + enquadramento indicativo (base do RF-01).
5. Baseline de persistência/sazonal para volume útil (início da Fase 4, sem ENOS).

## Decisões pendentes (Especificação §14)

D-01 fonte operacional dos reservatórios · D-02 bacia espanhola · D-03 dados de consumo · D-04 conceito de evento de risco e política de alerta (inclui o parâmetro provisório de defasagem de 7 dias) · D-05 validação jurídica · D-06 metas após baseline · D-07 uso público e segurança.
