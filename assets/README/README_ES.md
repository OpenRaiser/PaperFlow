<div align="center">

# PaperFlow

**Recomendación, lectura profunda e informes personalizados para artículos científicos.**

PaperFlow convierte la búsqueda diaria de papers en un flujo de investigación cerrado: construye un perfil, ordena los papers del día, lee en profundidad los más útiles, recoge feedback y adapta las recomendaciones de mañana.

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

[Inicio rápido](#inicio-rápido) | [Vista de escritorio](#vista-de-escritorio) | [GUI local](#gui-local) |
[Vista previa GUI](https://openraiser.github.io/PaperFlow/deployments/desktop/static/index.html?demo=1) |
[Uso CLI](#uso-cli) |
[Bucle de feedback](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feedback-loop.md) |
[Bot Feishu/Lark](#bot-feishulark) |
[PaperFlow-Bench](#paperflow-bench) | [Reproducir](https://github.com/OpenRaiser/PaperFlow/blob/main/experiments/REPRODUCE.md)

<img src="https://github.com/user-attachments/assets/fd31a62b-00a4-4210-82cb-1ffd080de254" alt="Banner de lectura científica personalizada de PaperFlow" width="100%">

</div>

---

## Versión actual

La primera versión pública incluye **CLI + GUI local en navegador + bot opcional para Feishu/Lark**. Puedes ejecutar PaperFlow desde la terminal, abrir una GUI local para seleccionar papers de forma interactiva o mantener activo el servidor webhook de Feishu/Lark para envíos programados.

| Elemento | Descripción |
| --- | --- |
| Entrada | Perfiles de investigación, papers, PDFs, páginas personales, Google Scholar |
| Salida | Resúmenes diarios, informes de lectura, informes semanales de perfil |
| Runtime | CLI Python local, GUI local, SQLite, webhook opcional Feishu/Lark + ngrok |
| Benchmark | PaperFlow-Bench en HuggingFace con scripts públicos de evaluación |

## Vista de escritorio

PaperFlow incluye una GUI de escritorio offline-first. Usa el mismo estado SQLite local y los mismos flujos backend que la CLI, por lo que no es un mock estático: extracción de papers, feedback, informes, grafo Wiki y configuración pasan por el backend local.

<div align="center">
  <img src="https://github.com/user-attachments/assets/c852c134-5ddb-478e-8a13-3fa313dcd812" alt="Demo del flujo de escritorio offline de PaperFlow" width="92%">
</div>

<br>

<details>
<summary>Ver capturas de escritorio</summary>

| Flujo diario de papers | Grafo Wiki de conocimiento |
| --- | --- |
| <img src="https://github.com/user-attachments/assets/018aa646-41fa-4967-b4d4-6d6a54df51cf" alt="Flujo diario de recomendaciones de PaperFlow"> | <img src="https://github.com/user-attachments/assets/305279b3-1350-4169-887c-99c0cac29a15" alt="Grafo Wiki de PaperFlow"> |
| Extracción por fecha, filtros de fuente, métricas de candidatos, acciones de paper y estado de tareas backend. | Relaciones generadas por backend entre papers, temas, métodos, perfil y citas. |

| Q&A Wiki con citas | Configuración local |
| --- | --- |
| <img src="https://github.com/user-attachments/assets/6685dd75-e2e2-45d1-b440-1ca5325eca1d" alt="Q&A local con citas en PaperFlow"> | <img src="https://github.com/user-attachments/assets/a629cc1e-e26e-4878-9eb3-97565153b711" alt="Configuración local y fuentes de PaperFlow"> |
| Respuestas en streaming con marcadores de referencia clicables y tarjetas de fuente. | Claves de provider, rutas de almacenamiento, fuentes, acceso a conferencias y exportación. |

</details>

### Marco de producto

<img src="https://github.com/user-attachments/assets/60ff5a52-5d09-46c2-be0d-1933c19515b6" alt="Diagrama del marco de producto de PaperFlow" width="100%">

El ciclo de escritorio es local por defecto: perfil, pushes, feedback, informes y nodos Wiki permanecen en disco salvo que actives providers externos o exportación Feishu/Lark.

## Por qué PaperFlow

La recomendación de papers no es un ranking único. Un investigador real pregunta algo cambiante: **qué debo leer hoy y cómo debe adaptarse el sistema mañana?**

| Alertas tradicionales | PaperFlow |
| --- | --- |
| Coincidencia estática por palabras clave o perfil | Perfil estructurado que se actualiza con feedback |
| El mismo feed cada día | Pools por fecha y presupuesto diario de digest |
| Solo recomendación | Recomendación + informe de lectura + feedback |
| Sin manejo explícito de deriva | Modelado de deriva de interés a corto y largo plazo |
| Difícil de reproducir en el tiempo | Episodios y evaluador públicos de PaperFlow-Bench |

## Capacidades principales

| Capacidad | Qué hace |
| --- | --- |
| Arranque de perfil | Construye perfiles académicos desde texto, PDFs, páginas web o Google Scholar |
| Recomendación diaria | Recupera papers de arXiv, OpenReview y revistas, y genera un digest personalizado |
| Informes de lectura | Genera informes personalizados a partir de metadatos y PDF |
| Aprendizaje por feedback | Actualiza el mismo perfil desde CLI, GUI, Feishu/Lark, selección, salto, lectura y feedback natural |
| Wiki local de investigación | Ingresa pushes, informes, citas, feedback y señales de perfil en un grafo local consultable |
| Q&A Wiki con citas | Responde con evidencia local cuando hace falta retrieval; soporta citas clicables y referencias `@` |
| GUI offline | UI local para pulls diarios, feedback, informes, grafo Wiki, Q&A y ajustes |
| Adaptación a deriva | Sigue cambios de interés entre ventanas cortas y largas |
| Bot Feishu/Lark | Envía pushes diarios y semanales; procesa feedback de chat y solicitudes PDF |
| Herramientas benchmark | Empaqueta, descarga, predice y evalúa envíos de PaperFlow-Bench |

## Inicio rápido

El flujo diario tiene cinco pasos. Los pasos 1-3 se ejecutan una vez; los pasos 4-5 son la rutina diaria.

```bash
# 1. Instalar
git clone https://github.com/OpenRaiser/PaperFlow.git
cd PaperFlow
pip install -e ".[all]"          # instalación completa; `pip install -e .` para CLI mínima

# 2. Configurar providers
cp .env.example .env
# edita .env: PAPERFLOW_LLM_PROVIDER y, en producción, un backend de embeddings

# 3. Inicializar runtime + crear perfil de usuario (OBLIGATORIO)
paperflow init
paperflow doctor
paperflow profile \
  --user-id user_alice \
  --natural-language "I work on LLM agents for scientific discovery, \
literature mining, and automated paper reading."

# 4. Push diario
paperflow daily --user-id user_alice

# 5. Leer papers seleccionados
paperflow read 1 3 7 --user-id user_alice

# Opcional: usar la GUI local
paperflow gui
```

> **El paso 3 es obligatorio.** `paperflow daily / read / feedback` leen el perfil creado por `paperflow profile`. Sin perfil no hay señal de personalización y `paperflow read` no tiene un push desde el cual leer.

### Smoke test offline

```bash
paperflow demo
```

El demo usa providers mock/hash deterministas; no requiere API keys ni red. Úsalo para validar la instalación antes de configurar providers reales.

## Configurar providers

```bash
cp .env.example .env
```

Las variables `PAPERFLOW_*` son la superficie canónica de configuración. La instalación nueva usa embeddings no-download para pruebas rápidas, pero la calidad real requiere un backend semántico.

### Opción A: producción recomendada

```env
PAPERFLOW_LLM_PROVIDER=openai
PAPERFLOW_LLM_MODEL=gpt-4o-mini

PAPERFLOW_EMBED_PROVIDER=openai
PAPERFLOW_EMBED_MODEL=text-embedding-3-small

OPENAI_API_KEY=sk-...
# OPENAI_BASE_URL=https://your-openai-compatible-gateway/v1
```

`OPENAI_BASE_URL` permite gateways compatibles con OpenAI, como OpenAI, DashScope, Azure OpenAI, vLLM y servicios similares. Si faltan credenciales, PaperFlow vuelve a mock/hash cuando es posible.

### Opción B: smoke test sin descargas

```env
PAPERFLOW_LLM_PROVIDER=mock
PAPERFLOW_EMBED_PROVIDER=hash
```

Es rápido y determinista, pero los vectores hash no capturan similitud semántica real.

### Opción C: embeddings locales de alta calidad

```env
PAPERFLOW_EMBED_PROVIDER=sentence_transformers
PAPERFLOW_EMBED_MODEL=BAAI/bge-m3
PAPERFLOW_EMBED_DIMENSIONS=1024
```

No necesita API key de embeddings, pero la primera ejecución descarga pesos. `BAAI/bge-m3` pesa alrededor de 2.3GB.

Después de cambiar providers:

```bash
paperflow doctor
```

Los datos runtime viven en `data/` y Git los ignora.

## Inicializar un perfil de usuario

PaperFlow mantiene **un perfil por `user_id`**. Debes crear al menos uno antes del primer `daily`.

```bash
# (a) Autodescripción
paperflow profile \
  --user-id user_alice \
  --natural-language "I work on LLM agents for scientific discovery, \
literature mining, and automated paper reading."

# (b) Papers propios o relevantes
paperflow profile --user-id user_alice --pdf /path/to/my-paper.pdf

# (c) Google Scholar público
paperflow profile \
  --user-id user_alice \
  --scholar-url "https://scholar.google.com/citations?user=..."

# (d) Página personal o de laboratorio
paperflow profile \
  --user-id user_alice \
  --homepage-url "https://example.edu/~alice"
```

Las llamadas repetidas a `paperflow profile` fusionan señales por defecto. Usa `--reset-existing` solo para reconstruir desde cero.

```bash
python scripts/show_profile.py user_alice
```

## GUI local

```bash
paperflow gui
```

Vista previa sin instalación: [PaperFlow GUI Preview](https://openraiser.github.io/PaperFlow/deployments/desktop/static/index.html?demo=1).

La GUI usa la misma base SQLite local que la CLI y cubre el flujo real:

- seleccionar perfil y ver resumen de direcciones
- extraer papers de hoy o de una fecha anterior
- mantener pulls largos como tareas backend con polling de estado
- marcar papers como lectura profunda, no interesado o ver luego
- enviar feedback y actualizar perfil/Wiki
- generar o reabrir informes
- inspeccionar el grafo Wiki y buscar nodos locales
- hacer preguntas al Wiki con referencias clicables
- configurar providers, fuentes, almacenamiento y exportación

La GUI no ejecuta schedules de fondo; eso sigue en `deployments/feishu/`.

```bash
paperflow gui --port 8766
paperflow gui --host 0.0.0.0 --no-browser
```

Más detalles: [deployments/desktop/README.md](https://github.com/OpenRaiser/PaperFlow/blob/main/deployments/desktop/README.md).

## Uso CLI

```bash
paperflow --help
```

| Comando | Propósito |
| --- | --- |
| `paperflow init` | Crear directorios runtime y tablas SQLite |
| `paperflow doctor` | Revisar dependencias, credenciales y rutas |
| `paperflow demo` | Ejecutar demo offline |
| `paperflow profile` | Crear o actualizar perfil desde texto, PDFs, Scholar o web |
| `paperflow daily` | Generar push diario personalizado |
| `paperflow read` | Generar informe de lectura |
| `paperflow wiki` | Listar, buscar e inspeccionar el Wiki local |
| `paperflow feedback` | Registrar feedback de un push anterior |
| `paperflow gui` | Iniciar la GUI local |
| `paperflow eval` | Evaluar predicciones de PaperFlow-Bench |

```bash
paperflow daily \
  --user-id user_role1 \
  --days 1 \
  --output data/daily_push.txt \
  --dry-run

paperflow read 1 3 7 --user-id user_role1 --no-feishu
paperflow read 1 3 7 --user-id user_role1 --push-id push_20260401_090000 --no-feishu
```

El Wiki local recibe pushes, informes, feedback y deriva de perfil:

```bash
paperflow wiki backfill --user-id user_role1
paperflow wiki topics --user-id user_role1
paperflow wiki stats --user-id user_role1
paperflow wiki search "graph rag" --user-id user_role1
paperflow wiki ask "What have I read about graph RAG?" --user-id user_role1
```

Exportación a Obsidian:

```env
PAPERFLOW_PDF_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026
PAPERFLOW_READING_REPORTS_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026
PAPERFLOW_MONTHLY_REPORT_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026
PAPERFLOW_TOPIC_INDEX_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026
PAPERFLOW_STORAGE_ROLE_SUBDIR=true
PAPERFLOW_STORAGE_CATEGORY_SUBDIR=true
PAPERFLOW_STORAGE_MONTHLY_SUBDIR=true
```

Las exportaciones locales se separan por role por defecto. Para una estructura plana heredada, desactiva `PAPERFLOW_STORAGE_ROLE_SUBDIR` o `PAPERFLOW_STORAGE_CATEGORY_SUBDIR`.

```bash
paperflow wiki monthly --user-id user_role1
```

Exportación Feishu/Lark de informes: [docs/feishu-doc-export.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-doc-export.md).

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

El feedback de CLI, GUI y Feishu/Lark se guarda en la misma SQLite y actualiza el mismo perfil. Ver [docs/feedback-loop.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feedback-loop.md).

## Bot Feishu/Lark

La integración Feishu/Lark es opcional para usar PaperFlow como bot con pushes y reportes programados. Para solo exportar documentos, usa [docs/feishu-doc-export.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-doc-export.md).

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

Pega la Request URL en la página de suscripción de eventos de Feishu/Lark y habilita `im.message.receive_v1`.

| Tarea | Horario por defecto |
| --- | --- |
| Push diario | 09:00, Asia/Shanghai |
| Informe semanal | Lunes 10:00, Asia/Shanghai |

```powershell
Get-Content data/webhook_stderr.log -Wait
```

Comandos de chat:

```text
profile
daily push
weekly report
1 3
read 1
```

Guía: [docs/feishu-webhook-setup.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-webhook-setup.md).

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

Más detalles:

- [docs/benchmark.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/benchmark.md)
- [experiments/REPRODUCE.md](https://github.com/OpenRaiser/PaperFlow/blob/main/experiments/REPRODUCE.md)

## Flujo de trabajo

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

## Estructura del repositorio

```text
PaperFlow/
  paperflow/                 CLI y abstracción de providers
  agents/                    Agentes principales de workflow
  skills/                    Helpers de fetching, parsing, perfil y almacenamiento
  deployments/desktop/       GUI local opcional
  deployments/feishu/        Bot Feishu/Lark opcional
  experiments/               Benchmark y scripts de reproducción
  scripts/                   Utilidades operativas
  config/                    Fuentes, scoring y direcciones
  docs/                      Documentación
  tests/                     Tests unitarios e integración
```

## Checks de desarrollo

```bash
pytest tests -q
pytest experiments/tests -q
```

GitHub Actions ejecuta la suite principal; `experiments/tests/` valida benchmark y reproducción.

## Documentación

- [docs/README.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/README.md)
- [docs/quickstart.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/quickstart.md)
- [docs/configuration.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/configuration.md)
- [docs/feedback-loop.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feedback-loop.md)
- [deployments/desktop/README.md](https://github.com/OpenRaiser/PaperFlow/blob/main/deployments/desktop/README.md)
- [PaperFlow GUI Preview](https://openraiser.github.io/PaperFlow/deployments/desktop/static/index.html?demo=1)
- [docs/feishu-doc-export.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-doc-export.md)
- [docs/feishu-webhook-setup.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-webhook-setup.md)

## Cita

```bibtex
@article{wang2026paperflow,
  title={PaperFlow: Profiling, Recommending, and Adapting Across Daily Paper Streams},
  author={Wang, Fuqiang and Tan, Song and Guo, Zheng and Fu, Jiaohao and Xu, Xinglong and Yu, Bihui and Dong, Jie and Sun, Zheng and Li, Siyuan and Wei, Jingxuan and others},
  journal={arXiv preprint arXiv:2606.07454},
  year={2026}
}
```

La cita formal se actualizará cuando se publique el paper.

## Licencia

PaperFlow se publica bajo licencia MIT. Ver [LICENSE](https://github.com/OpenRaiser/PaperFlow/blob/main/LICENSE).
