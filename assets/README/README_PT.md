<div align="center">

# PaperFlow

**Recomendação, leitura aprofundada e relatórios personalizados para artigos científicos.**

O PaperFlow transforma a descoberta diária de artigos em um fluxo de pesquisa em ciclo fechado: cria um perfil, ranqueia os artigos do dia, lê os mais úteis, coleta feedback e adapta as recomendações do dia seguinte.

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](https://www.python.org/downloads/)
[![Package](https://img.shields.io/badge/package-paperflow-2E7D32.svg)](https://github.com/OpenRaiser/PaperFlow/blob/main/pyproject.toml)
[![HF Dataset](https://img.shields.io/badge/HF%20Dataset-OpenRaiser%2FPaperFlow-FFD21E.svg)](https://huggingface.co/datasets/OpenRaiser/PaperFlow)
[![License: MIT](https://img.shields.io/badge/License-MIT-111111.svg)](https://github.com/OpenRaiser/PaperFlow/blob/main/LICENSE)

![Personalized Recommendation](https://img.shields.io/badge/personalized-recommendation-2E7D32.svg)
![Scientific Reading](https://img.shields.io/badge/scientific-reading-1565C0.svg)
![Daily Digest](https://img.shields.io/badge/daily-paper%20digest-F9A825.svg)
![Feedback Learning](https://img.shields.io/badge/feedback-learning-6A5ACD.svg)
![Interest Drift](https://img.shields.io/badge/interest-drift-00897B.svg)
![Feishu/Lark](https://img.shields.io/badge/Feishu%2FLark-bot-00A1E9.svg)

**Idioma**:
[English](https://github.com/OpenRaiser/PaperFlow#readme) ·
[简体中文](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_CN.md) ·
[日本語](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_JA.md) ·
[Español](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_ES.md) ·
[Français](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_FR.md) ·
[Português](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_PT.md) ·
[한국어](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_KO.md)

[Início rápido](#início-rápido) | [Prévia desktop](#prévia-desktop) | [GUI local](#gui-local) |
[Prévia da GUI](https://openraiser.github.io/PaperFlow/deployments/desktop/static/index.html?demo=1) |
[Uso da CLI](#uso-da-cli) |
[Loop de feedback](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feedback-loop.md) |
[Bot Feishu/Lark](#bot-feishulark) |
[PaperFlow-Bench](#paperflow-bench) | [Reproduzir](https://github.com/OpenRaiser/PaperFlow/blob/main/experiments/REPRODUCE.md)

<img src="https://github.com/user-attachments/assets/fd31a62b-00a4-4210-82cb-1ffd080de254" alt="Banner PaperFlow para leitura científica personalizada" width="100%">

</div>

---

## Versão atual

A primeira versão pública inclui **CLI + GUI local no navegador + bot opcional para Feishu/Lark**. Você pode rodar o PaperFlow pelo terminal, abrir uma GUI local para seleção interativa de artigos ou manter o webhook Feishu/Lark ativo para envios programados.

| Item | Descrição |
| --- | --- |
| Entrada | Perfis de pesquisa, artigos, PDFs, páginas pessoais, Google Scholar |
| Saída | Digests diários, relatórios de leitura, relatórios semanais de perfil |
| Runtime | CLI Python local, GUI local, SQLite, webhook Feishu/Lark opcional + ngrok |
| Benchmark | PaperFlow-Bench no HuggingFace com scripts públicos de avaliação |

## Prévia desktop

O PaperFlow traz uma GUI desktop offline-first. Ela usa o mesmo estado SQLite local e os mesmos workflows backend da CLI, portanto não é um mock estático: pulls de artigos, feedback, relatórios, Wiki e configurações passam pelo backend local.

<div align="center">
  <img src="https://github.com/user-attachments/assets/c852c134-5ddb-478e-8a13-3fa313dcd812" alt="Demo do fluxo desktop offline do PaperFlow" width="92%">
</div>

<br>

<details>
<summary>Ver capturas desktop</summary>

| Fluxo diário de artigos | Grafo Wiki de conhecimento |
| --- | --- |
| <img src="https://github.com/user-attachments/assets/018aa646-41fa-4967-b4d4-6d6a54df51cf" alt="Fluxo diário de recomendações do PaperFlow"> | <img src="https://github.com/user-attachments/assets/305279b3-1350-4169-887c-99c0cac29a15" alt="Grafo Wiki do PaperFlow"> |
| Pulls por data, filtros de fonte, métricas, ações e estado backend. | Relações backend entre artigos, temas, métodos, perfil e citações. |

| Q&A Wiki com citações | Configurações locais |
| --- | --- |
| <img src="https://github.com/user-attachments/assets/6685dd75-e2e2-45d1-b440-1ca5325eca1d" alt="Q&A Wiki local com citações"> | <img src="https://github.com/user-attachments/assets/a629cc1e-e26e-4878-9eb3-97565153b711" alt="Configurações locais do PaperFlow"> |
| Respostas em streaming com marcadores clicáveis e cartões de fonte. | Chaves de provider, caminhos, fontes, acesso a conferências e exportação. |

</details>

### Estrutura do produto

<img src="https://github.com/user-attachments/assets/60ff5a52-5d09-46c2-be0d-1933c19515b6" alt="Diagrama da estrutura do produto PaperFlow" width="100%">

O ciclo desktop é local por padrão: perfil, pushes, feedback, relatórios e nós Wiki ficam em disco, exceto quando providers externos ou exportação Feishu/Lark são ativados explicitamente.

## Por que PaperFlow

Recomendação científica não é um ranking único. Pesquisadores fazem uma pergunta dinâmica: **o que devo ler hoje e como o sistema deve se adaptar amanhã?**

| Alertas tradicionais | PaperFlow |
| --- | --- |
| Palavras-chave ou perfil estático | Perfil estruturado atualizado por feedback |
| Mesmo feed todos os dias | Pools por data e orçamento diário de digest |
| Apenas recomendação | Recomendação + relatório + loop de feedback |
| Sem deriva explícita | Modelagem de deriva de interesse curta e longa |
| Difícil reproduzir longitudinalmente | Episódios e avaliador públicos do PaperFlow-Bench |

## Recursos principais

| Recurso | O que faz |
| --- | --- |
| Inicialização de perfil | Cria perfis acadêmicos a partir de texto, PDFs, páginas ou Google Scholar |
| Recomendação diária | Busca arXiv, OpenReview e periódicos, ranqueando um digest personalizado |
| Relatórios de leitura | Gera relatórios personalizados a partir de metadados e PDFs |
| Aprendizado por feedback | Atualiza o mesmo perfil via CLI, GUI, Feishu/Lark e feedback natural |
| Wiki local de pesquisa | Ingestão de pushes, relatórios, citações, feedback e sinais de perfil em grafo local |
| Q&A Wiki citado | Responde com evidência local, citações clicáveis e referências explícitas `@` |
| GUI offline | UI local para pulls, feedback, relatórios, grafo Wiki, Q&A e configurações |
| Adaptação à deriva | Acompanha mudanças de interesse em janelas curtas e longas |
| Bot Feishu/Lark | Envia pushes e relatórios; processa feedback de chat e PDFs |
| Benchmark | Baixa, prediz e avalia submissões PaperFlow-Bench |

## Início rápido

O fluxo diário tem cinco etapas. As etapas 1-3 rodam uma vez; 4-5 viram a rotina.

```bash
# 1. Instalar
git clone https://github.com/OpenRaiser/PaperFlow.git
cd PaperFlow
pip install -e ".[all]"          # instalação completa; `pip install -e .` para CLI mínima

# 2. Configurar providers
cp .env.example .env
# edite .env: PAPERFLOW_LLM_PROVIDER e, em produção, um backend de embeddings

# 3. Inicializar runtime + criar perfil (OBRIGATÓRIO)
paperflow init
paperflow doctor
paperflow profile \
  --user-id user_alice \
  --natural-language "I work on LLM agents for scientific discovery, \
literature mining, and automated paper reading."

# 4. Push diário
paperflow daily --user-id user_alice

# 5. Ler artigos selecionados
paperflow read 1 3 7 --user-id user_alice

# Opcional: usar a GUI local
paperflow gui
```

> **A etapa 3 é obrigatória.** `paperflow daily / read / feedback` leem o perfil criado por `paperflow profile`. Sem perfil, não há sinal de personalização nem push para leitura.

### Smoke test offline

```bash
paperflow demo
```

O demo usa providers mock/hash determinísticos e não requer API keys nem rede.

## Configurar providers

```bash
cp .env.example .env
```

As variáveis `PAPERFLOW_*` são a superfície canônica de configuração. Embeddings no-download servem para testes rápidos, mas qualidade real pede um backend semântico.

### Opção A: produção recomendada

```env
PAPERFLOW_LLM_PROVIDER=openai
PAPERFLOW_LLM_MODEL=gpt-4o-mini

PAPERFLOW_EMBED_PROVIDER=openai
PAPERFLOW_EMBED_MODEL=text-embedding-3-small

OPENAI_API_KEY=sk-...
# OPENAI_BASE_URL=https://your-openai-compatible-gateway/v1
```

`OPENAI_BASE_URL` suporta OpenAI, DashScope, Azure OpenAI, vLLM e serviços compatíveis. Se credenciais faltarem, PaperFlow volta para mock/hash quando possível.

### Opção B: teste sem download

```env
PAPERFLOW_LLM_PROVIDER=mock
PAPERFLOW_EMBED_PROVIDER=hash
```

Rápido e determinístico, mas não mede similaridade semântica real.

### Opção C: embeddings locais de alta qualidade

```env
PAPERFLOW_EMBED_PROVIDER=sentence_transformers
PAPERFLOW_EMBED_MODEL=BAAI/bge-m3
PAPERFLOW_EMBED_DIMENSIONS=1024
```

Não precisa de API key de embedding, mas baixa pesos na primeira execução.

```bash
paperflow doctor
```

Dados runtime ficam em `data/` e são ignorados pelo Git.

## Inicializar perfil de usuário

PaperFlow mantém **um perfil por `user_id`**. Crie um antes do primeiro `daily`.

```bash
# (a) Descrição natural
paperflow profile \
  --user-id user_alice \
  --natural-language "I work on LLM agents for scientific discovery, \
literature mining, and automated paper reading."

# (b) Artigos próprios ou relevantes
paperflow profile --user-id user_alice --pdf /path/to/my-paper.pdf

# (c) Google Scholar público
paperflow profile \
  --user-id user_alice \
  --scholar-url "https://scholar.google.com/citations?user=..."

# (d) Página pessoal ou de laboratório
paperflow profile \
  --user-id user_alice \
  --homepage-url "https://example.edu/~alice"
```

Chamadas repetidas mesclam sinais por padrão. Use `--reset-existing` apenas para reconstruir.

```bash
python scripts/show_profile.py user_alice
```

## GUI local

```bash
paperflow gui
```

Prévia sem instalação: [PaperFlow GUI Preview](https://openraiser.github.io/PaperFlow/deployments/desktop/static/index.html?demo=1).

A GUI usa o mesmo SQLite da CLI:

- selecionar perfil e ver resumo de direções
- puxar artigos de hoje ou de uma data anterior
- manter pulls longos como tarefa backend com polling
- marcar leitura profunda, não interessado ou ver depois
- enviar feedback e atualizar perfil/Wiki
- gerar ou reabrir relatórios
- inspecionar grafo Wiki e buscar nós locais
- perguntar ao Wiki com referências clicáveis
- configurar providers, fontes, armazenamento e exportação

```bash
paperflow gui --port 8766
paperflow gui --host 0.0.0.0 --no-browser
```

Detalhes: [deployments/desktop/README.md](https://github.com/OpenRaiser/PaperFlow/blob/main/deployments/desktop/README.md).

## Uso da CLI

```bash
paperflow --help
```

| Comando | Finalidade |
| --- | --- |
| `paperflow init` | Criar diretórios runtime e tabelas SQLite |
| `paperflow doctor` | Verificar dependências, credenciais e caminhos |
| `paperflow demo` | Rodar demo offline |
| `paperflow profile` | Criar/atualizar perfil |
| `paperflow daily` | Gerar push diário personalizado |
| `paperflow read` | Gerar relatório de leitura |
| `paperflow wiki` | Listar, buscar e inspecionar Wiki local |
| `paperflow feedback` | Registrar feedback de push anterior |
| `paperflow gui` | Iniciar GUI local |
| `paperflow eval` | Avaliar PaperFlow-Bench |

```bash
paperflow daily \
  --user-id user_role1 \
  --days 1 \
  --output data/daily_push.txt \
  --dry-run

paperflow read 1 3 7 --user-id user_role1 --no-feishu
paperflow read 1 3 7 --user-id user_role1 --push-id push_20260401_090000 --no-feishu
```

Wiki local:

```bash
paperflow wiki backfill --user-id user_role1
paperflow wiki topics --user-id user_role1
paperflow wiki stats --user-id user_role1
paperflow wiki search "graph rag" --user-id user_role1
paperflow wiki ask "What have I read about graph RAG?" --user-id user_role1
```

Exportação para Obsidian:

```env
PAPERFLOW_PDF_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026
PAPERFLOW_READING_REPORTS_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026
PAPERFLOW_MONTHLY_REPORT_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026
PAPERFLOW_TOPIC_INDEX_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026
PAPERFLOW_STORAGE_ROLE_SUBDIR=true
PAPERFLOW_STORAGE_CATEGORY_SUBDIR=true
PAPERFLOW_STORAGE_MONTHLY_SUBDIR=true
```

```bash
paperflow wiki monthly --user-id user_role1
```

Exportação Feishu/Lark: [docs/feishu-doc-export.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-doc-export.md).

```bash
paperflow read 1 --user-id user_role1
paperflow read 1 --user-id user_role1 --folder-id <feishu_folder_token>
```

Feedback:

```bash
paperflow feedback \
  --user-id user_role1 \
  --push-id push_20260401_090000 \
  --reply "1, 3"
```

O feedback da CLI, GUI e Feishu/Lark vai para o mesmo SQLite. Ver [docs/feedback-loop.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feedback-loop.md).

## Bot Feishu/Lark

Opcional para pushes e relatórios programados. Para apenas exportar documentos, veja [docs/feishu-doc-export.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-doc-export.md).

```env
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_VERIFICATION_TOKEN=
FEISHU_USER_ID=

NGROK_AUTHTOKEN=
NGROK_DOMAIN=
```

```bash
python deployments/feishu/webhook-server/start-with-ngrok.py
```

Cole a Request URL no Feishu/Lark e habilite `im.message.receive_v1`.

| Job | Agenda padrão |
| --- | --- |
| Push diário | 09:00, Asia/Shanghai |
| Relatório semanal | Segunda 10:00, Asia/Shanghai |

```powershell
Get-Content data/webhook_stderr.log -Wait
```

```text
profile
daily push
weekly report
1 3
read 1
```

Guia: [docs/feishu-webhook-setup.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-webhook-setup.md).

## PaperFlow-Bench

Dataset: [OpenRaiser/PaperFlow](https://huggingface.co/datasets/OpenRaiser/PaperFlow).

```bash
python experiments/benchmark/fetch_benchmark.py \
  --output-dir data/PaperFlow-Bench

python experiments/benchmark/make_benchmark_submission.py \
  --benchmark-dir data/PaperFlow-Bench \
  --output data/PaperFlow-Bench/example_predictions.jsonl

paperflow eval \
  --benchmark-dir data/PaperFlow-Bench \
  --predictions data/PaperFlow-Bench/example_predictions.jsonl \
  --output data/PaperFlow-Bench/example_metrics.json
```

- [docs/benchmark.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/benchmark.md)
- [experiments/REPRODUCE.md](https://github.com/OpenRaiser/PaperFlow/blob/main/experiments/REPRODUCE.md)

## Workflow

```text
research profile
      |
      v
daily candidate pool  ->  scoring + drift adjustment  ->  paper digest
      |                                                       |
      v                                                       v
arXiv / OpenReview / journals                         reading reports
                                                              |
                                                              v
                                                     feedback + profile update
                                                              |
                                                              v
                                                     tomorrow's recommendation
```

## Estrutura do repositório

```text
PaperFlow/
  paperflow/                 CLI e abstração de provider
  agents/                    Agentes de workflow
  skills/                    Helpers de fetching, parsing, perfil e armazenamento
  deployments/desktop/       GUI local opcional
  deployments/feishu/        Bot Feishu/Lark opcional
  experiments/               Benchmark e reprodução
  scripts/                   Utilidades operacionais
  config/                    Fontes, scoring e direções
  docs/                      Documentação
  tests/                     Testes unitários e integração
```

## Checks de desenvolvimento

```bash
pytest tests -q
pytest experiments/tests -q
```

## Documentação

- [docs/README.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/README.md)
- [docs/quickstart.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/quickstart.md)
- [docs/configuration.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/configuration.md)
- [docs/feedback-loop.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feedback-loop.md)
- [deployments/desktop/README.md](https://github.com/OpenRaiser/PaperFlow/blob/main/deployments/desktop/README.md)
- [PaperFlow GUI Preview](https://openraiser.github.io/PaperFlow/deployments/desktop/static/index.html?demo=1)
- [docs/feishu-doc-export.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-doc-export.md)
- [docs/feishu-webhook-setup.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-webhook-setup.md)

## Citação

```bibtex
@article{wang2026paperflow,
  title={PaperFlow: Profiling, Recommending, and Adapting Across Daily Paper Streams},
  author={Wang, Fuqiang and Tan, Song and Guo, Zheng and Fu, Jiaohao and Xu, Xinglong and Yu, Bihui and Dong, Jie and Sun, Zheng and Li, Siyuan and Wei, Jingxuan and others},
  journal={arXiv preprint arXiv:2606.07454},
  year={2026}
}
```

A citação formal será atualizada após a publicação do paper.

## Licença

PaperFlow é publicado sob licença MIT. Ver [LICENSE](https://github.com/OpenRaiser/PaperFlow/blob/main/LICENSE).
