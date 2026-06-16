<div align="center">

# PaperFlow

**Recommandation, lecture approfondie et rapports personnalisés pour les articles scientifiques.**

PaperFlow transforme la veille quotidienne en boucle de recherche fermée : construire un profil, classer les articles du jour, lire les plus utiles, collecter du feedback et adapter les recommandations du lendemain.

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

**Langue**:
[English](https://github.com/OpenRaiser/PaperFlow#readme) ·
[简体中文](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_CN.md) ·
[日本語](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_JA.md) ·
[Español](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_ES.md) ·
[Français](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_FR.md) ·
[Português](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_PT.md) ·
[한국어](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_KO.md)

[Démarrage rapide](#démarrage-rapide) | [Aperçu desktop](#aperçu-desktop) | [GUI locale](#gui-locale) |
[Aperçu GUI](https://openraiser.github.io/PaperFlow/deployments/desktop/static/index.html?demo=1) |
[CLI](#utilisation-cli) |
[Boucle de feedback](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feedback-loop.md) |
[Bot Feishu/Lark](#bot-feishulark) |
[PaperFlow-Bench](#paperflow-bench) | [Reproduire](https://github.com/OpenRaiser/PaperFlow/blob/main/experiments/REPRODUCE.md)

<img src="https://github.com/user-attachments/assets/fd31a62b-00a4-4210-82cb-1ffd080de254" alt="Bannière PaperFlow pour la lecture scientifique personnalisée" width="100%">

</div>

---

## Version actuelle

Cette première version publique est une version **CLI + GUI locale dans le navigateur + bot Feishu/Lark optionnel**. PaperFlow peut fonctionner entièrement depuis le terminal, via une GUI locale pour la sélection interactive, ou avec un serveur webhook Feishu/Lark pour les envois planifiés.

| Élément | Description |
| --- | --- |
| Entrées | Profils de recherche, articles, PDFs, pages personnelles, profils Google Scholar |
| Sorties | Digests quotidiens, rapports de lecture, rapports hebdomadaires de profil |
| Runtime | CLI Python locale, GUI locale, SQLite, webhook Feishu/Lark optionnel + ngrok |
| Benchmark | PaperFlow-Bench sur HuggingFace avec scripts d’évaluation publics |

## Aperçu desktop

PaperFlow fournit une GUI desktop offline-first. Elle utilise le même état SQLite local et les mêmes workflows backend que la CLI : extraction d’articles, feedback, rapports, mises à jour du Wiki et paramètres passent par le backend local.

<div align="center">
  <img src="https://github.com/user-attachments/assets/c852c134-5ddb-478e-8a13-3fa313dcd812" alt="Démo du workflow desktop offline de PaperFlow" width="92%">
</div>

<br>

<details>
<summary>Voir les captures desktop</summary>

| Flux quotidien d’articles | Graphe Wiki de connaissance |
| --- | --- |
| <img src="https://github.com/user-attachments/assets/018aa646-41fa-4967-b4d4-6d6a54df51cf" alt="Flux quotidien de recommandations PaperFlow"> | <img src="https://github.com/user-attachments/assets/305279b3-1350-4169-887c-99c0cac29a15" alt="Graphe Wiki PaperFlow"> |
| Pulls datés, filtres de sources, métriques de candidats, actions et état backend. | Relations backend entre articles, thèmes, méthodes, profil et citations. |

| Q&A Wiki cité | Paramètres locaux |
| --- | --- |
| <img src="https://github.com/user-attachments/assets/6685dd75-e2e2-45d1-b440-1ca5325eca1d" alt="Q&A Wiki local cité"> | <img src="https://github.com/user-attachments/assets/a629cc1e-e26e-4878-9eb3-97565153b711" alt="Paramètres locaux PaperFlow"> |
| Réponses en streaming avec marqueurs de référence cliquables et cartes de sources. | Clés provider, chemins de stockage, sources, accès conférence et export. |

</details>

### Cadre produit

<img src="https://github.com/user-attachments/assets/60ff5a52-5d09-46c2-be0d-1933c19515b6" alt="Diagramme du cadre produit PaperFlow" width="100%">

La boucle desktop est locale par défaut : profil, pushes, feedback, rapports et nœuds Wiki restent sur disque sauf activation explicite de providers externes ou de l’export Feishu/Lark.

## Pourquoi PaperFlow

La recommandation d’articles n’est pas un classement ponctuel. Un chercheur demande plutôt : **que lire aujourd’hui, et comment le système doit-il s’adapter demain ?**

| Alertes classiques | PaperFlow |
| --- | --- |
| Matching statique par mots-clés ou profil | Profil structuré mis à jour par feedback |
| Même flux chaque jour | Pools datés et budget de digest quotidien |
| Recommandation seulement | Recommandation + rapport + feedback |
| Pas de dérive explicite | Modélisation court/long terme de la dérive d’intérêt |
| Reproduction longitudinale difficile | Épisodes et évaluateur publics PaperFlow-Bench |

## Fonctionnalités principales

| Fonctionnalité | Rôle |
| --- | --- |
| Initialisation du profil | Construit un profil depuis texte, PDFs, pages web ou Google Scholar |
| Recommandation quotidienne | Récupère arXiv, OpenReview et revues puis classe un digest personnalisé |
| Rapports de lecture | Génère des rapports personnalisés depuis les métadonnées et PDFs |
| Apprentissage par feedback | Met à jour le même profil depuis CLI, GUI, Feishu/Lark et feedback naturel |
| Wiki local de recherche | Ingestion des pushes, rapports, citations, feedback et signaux de profil dans un graphe local |
| Q&A Wiki cité | Répond avec preuves locales, citations cliquables et références explicites `@` |
| GUI offline | Interface locale pour pulls, feedback, rapports, graphe Wiki, Q&A et paramètres |
| Adaptation à la dérive | Suit les mouvements d’intérêt court et long terme |
| Bot Feishu/Lark | Envoie pushes et rapports; traite feedback chat et demandes PDF |
| Outils benchmark | Téléchargement, prédiction et évaluation PaperFlow-Bench |

## Démarrage rapide

Le flux quotidien a cinq étapes. Les étapes 1-3 ne se font qu’une fois; 4-5 deviennent la routine.

```bash
# 1. Installer
git clone https://github.com/OpenRaiser/PaperFlow.git
cd PaperFlow
pip install -e ".[all]"          # installation complète; `pip install -e .` pour la CLI minimale

# 2. Configurer les providers
cp .env.example .env
# éditer .env: PAPERFLOW_LLM_PROVIDER et, en production, un backend d'embeddings

# 3. Initialiser le runtime + créer un profil (OBLIGATOIRE)
paperflow init
paperflow doctor
paperflow profile \
  --user-id user_alice \
  --natural-language "I work on LLM agents for scientific discovery, \
literature mining, and automated paper reading."

# 4. Push quotidien
paperflow daily --user-id user_alice

# 5. Lire les articles sélectionnés
paperflow read 1 3 7 --user-id user_alice

# Optionnel: utiliser la GUI locale
paperflow gui
```

> **L’étape 3 est obligatoire.** `paperflow daily / read / feedback` lisent le profil créé par `paperflow profile`. Sans profil, il n’y a pas de signal de personnalisation ni de push à lire.

### Test offline sans clés API

```bash
paperflow demo
```

Le demo utilise des providers mock/hash déterministes et ne nécessite ni clé API ni réseau.

## Configurer les providers

```bash
cp .env.example .env
```

Les variables `PAPERFLOW_*` sont la surface de configuration canonique. Les embeddings no-download suffisent pour les tests rapides, mais la qualité réelle demande un backend sémantique.

### Option A : production recommandée

```env
PAPERFLOW_LLM_PROVIDER=openai
PAPERFLOW_LLM_MODEL=gpt-4o-mini

PAPERFLOW_EMBED_PROVIDER=openai
PAPERFLOW_EMBED_MODEL=text-embedding-3-small

OPENAI_API_KEY=sk-...
# OPENAI_BASE_URL=https://your-openai-compatible-gateway/v1
```

`OPENAI_BASE_URL` prend en charge OpenAI, DashScope, Azure OpenAI, vLLM et services compatibles. Sans identifiants valides, PaperFlow revient à mock/hash quand c’est possible.

### Option B : smoke test sans téléchargement

```env
PAPERFLOW_LLM_PROVIDER=mock
PAPERFLOW_EMBED_PROVIDER=hash
```

Rapide et déterministe, mais pas adapté à l’évaluation de la qualité de recommandation.

### Option C : embeddings locaux de qualité

```env
PAPERFLOW_EMBED_PROVIDER=sentence_transformers
PAPERFLOW_EMBED_MODEL=BAAI/bge-m3
PAPERFLOW_EMBED_DIMENSIONS=1024
```

Ne nécessite pas de clé API embedding, mais télécharge les poids au premier lancement.

```bash
paperflow doctor
```

Les données runtime sont stockées sous `data/` et ignorées par Git.

## Initialiser un profil utilisateur

PaperFlow conserve **un profil par `user_id`**. Crée au moins un profil avant le premier `daily`.

```bash
# (a) Description naturelle
paperflow profile \
  --user-id user_alice \
  --natural-language "I work on LLM agents for scientific discovery, \
literature mining, and automated paper reading."

# (b) Articles écrits ou importants
paperflow profile --user-id user_alice --pdf /path/to/my-paper.pdf

# (c) Google Scholar public
paperflow profile \
  --user-id user_alice \
  --scholar-url "https://scholar.google.com/citations?user=..."

# (d) Page personnelle ou de laboratoire
paperflow profile \
  --user-id user_alice \
  --homepage-url "https://example.edu/~alice"
```

Les appels répétés fusionnent les signaux. Utilise `--reset-existing` seulement pour reconstruire.

```bash
python scripts/show_profile.py user_alice
```

## GUI locale

```bash
paperflow gui
```

Aperçu sans installation : [PaperFlow GUI Preview](https://openraiser.github.io/PaperFlow/deployments/desktop/static/index.html?demo=1).

La GUI partage la même base SQLite que la CLI :

- choisir un profil et voir les directions dérivées
- tirer les articles du jour ou d’une date antérieure
- conserver les pulls longs en tâche backend avec polling
- marquer lecture approfondie, pas intéressé ou plus tard
- soumettre feedback et mettre à jour profil/Wiki
- générer ou rouvrir les rapports
- inspecter le graphe Wiki et rechercher des nœuds locaux
- poser des questions au Wiki avec références cliquables
- configurer providers, sources, stockage et export

```bash
paperflow gui --port 8766
paperflow gui --host 0.0.0.0 --no-browser
```

Notes détaillées : [deployments/desktop/README.md](https://github.com/OpenRaiser/PaperFlow/blob/main/deployments/desktop/README.md).

## Utilisation CLI

```bash
paperflow --help
```

| Commande | But |
| --- | --- |
| `paperflow init` | Créer les dossiers runtime et tables SQLite |
| `paperflow doctor` | Vérifier dépendances, credentials et chemins |
| `paperflow demo` | Lancer un demo offline |
| `paperflow profile` | Créer/mettre à jour un profil |
| `paperflow daily` | Générer un push quotidien personnalisé |
| `paperflow read` | Générer un rapport de lecture |
| `paperflow wiki` | Lister, chercher et inspecter le Wiki local |
| `paperflow feedback` | Enregistrer le feedback d’un push |
| `paperflow gui` | Démarrer la GUI locale |
| `paperflow eval` | Évaluer PaperFlow-Bench |

```bash
paperflow daily \
  --user-id user_role1 \
  --days 1 \
  --output data/daily_push.txt \
  --dry-run

paperflow read 1 3 7 --user-id user_role1 --no-feishu
paperflow read 1 3 7 --user-id user_role1 --push-id push_20260401_090000 --no-feishu
```

Wiki local :

```bash
paperflow wiki backfill --user-id user_role1
paperflow wiki topics --user-id user_role1
paperflow wiki stats --user-id user_role1
paperflow wiki search "graph rag" --user-id user_role1
paperflow wiki ask "What have I read about graph RAG?" --user-id user_role1
```

Export Obsidian :

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

Export Feishu/Lark : [docs/feishu-doc-export.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-doc-export.md).

```bash
paperflow read 1 --user-id user_role1
paperflow read 1 --user-id user_role1 --folder-id <feishu_folder_token>
```

Feedback :

```bash
paperflow feedback \
  --user-id user_role1 \
  --push-id push_20260401_090000 \
  --reply "1, 3"
```

Le feedback CLI, GUI et Feishu/Lark va dans la même base SQLite. Voir [docs/feedback-loop.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feedback-loop.md).

## Bot Feishu/Lark

Optionnel pour recevoir pushes et rapports programmés. Pour seulement exporter des documents, voir [docs/feishu-doc-export.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-doc-export.md).

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

Colle la Request URL dans Feishu/Lark et active `im.message.receive_v1`.

| Job | Horaire par défaut |
| --- | --- |
| Push quotidien | 09:00, Asia/Shanghai |
| Rapport hebdomadaire | Lundi 10:00, Asia/Shanghai |

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

Guide : [docs/feishu-webhook-setup.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-webhook-setup.md).

## PaperFlow-Bench

Dataset : [OpenRaiser/PaperFlow](https://huggingface.co/datasets/OpenRaiser/PaperFlow).

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

## Structure du dépôt

```text
PaperFlow/
  paperflow/                 CLI et abstraction provider
  agents/                    Agents de workflow
  skills/                    Helpers fetching, parsing, profil et stockage
  deployments/desktop/       GUI locale optionnelle
  deployments/feishu/        Bot Feishu/Lark optionnel
  experiments/               Benchmark et reproduction
  scripts/                   Outils opérationnels
  config/                    Sources, scoring et directions
  docs/                      Documentation
  tests/                     Tests unitaires et intégration
```

## Checks de développement

```bash
pytest tests -q
pytest experiments/tests -q
```

## Documentation

- [docs/README.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/README.md)
- [docs/quickstart.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/quickstart.md)
- [docs/configuration.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/configuration.md)
- [docs/feedback-loop.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feedback-loop.md)
- [deployments/desktop/README.md](https://github.com/OpenRaiser/PaperFlow/blob/main/deployments/desktop/README.md)
- [PaperFlow GUI Preview](https://openraiser.github.io/PaperFlow/deployments/desktop/static/index.html?demo=1)
- [docs/feishu-doc-export.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-doc-export.md)
- [docs/feishu-webhook-setup.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-webhook-setup.md)

## Citation

```bibtex
@article{wang2026paperflow,
  title={PaperFlow: Profiling, Recommending, and Adapting Across Daily Paper Streams},
  author={Wang, Fuqiang and Tan, Song and Guo, Zheng and Fu, Jiaohao and Xu, Xinglong and Yu, Bihui and Dong, Jie and Sun, Zheng and Li, Siyuan and Wei, Jingxuan and others},
  journal={arXiv preprint arXiv:2606.07454},
  year={2026}
}
```

La citation formelle sera mise à jour après publication.

## Licence

PaperFlow est publié sous licence MIT. Voir [LICENSE](https://github.com/OpenRaiser/PaperFlow/blob/main/LICENSE).
