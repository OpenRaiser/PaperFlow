<div align="center">

# PaperFlow

**科学論文のための動的な個人化推薦、精読、レポート生成システム。**

PaperFlow は、毎日の論文発見を閉ループの研究ワークフローに変えます。研究プロフィールを作成し、その日の論文をランキングし、有用な論文を精読し、フィードバックを集め、翌日の推薦をさらに適応させます。

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

**言語**:
[English](https://github.com/OpenRaiser/PaperFlow#readme) ·
[简体中文](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_CN.md) ·
[日本語](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_JA.md) ·
[Español](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_ES.md) ·
[Français](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_FR.md) ·
[Português](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_PT.md) ·
[한국어](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_KO.md)

[クイックスタート](#クイックスタート) | [デスクトッププレビュー](#デスクトッププレビュー) | [ローカル GUI](#ローカル-gui) |
[GUI プレビュー](https://openraiser.github.io/PaperFlow/deployments/desktop/static/index.html?demo=1) |
[CLI の使い方](#cli-の使い方) |
[フィードバックループ](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feedback-loop.md) |
[Feishu/Lark Bot](#feishulark-bot) |
[PaperFlow-Bench](#paperflow-bench) | [再現](https://github.com/OpenRaiser/PaperFlow/blob/main/experiments/REPRODUCE.md)

<img src="https://github.com/user-attachments/assets/fd31a62b-00a4-4210-82cb-1ffd080de254" alt="PaperFlow personalized scientific reading banner" width="100%">

</div>

---

## 現在のリリース

最初の公開リリースは **CLI + ローカルブラウザ GUI + 任意の Feishu/Lark Bot** です。PaperFlow はターミナルだけで実行でき、対話的な論文選択にはローカル GUI を開けます。定期配信が必要な場合は Feishu/Lark webhook サーバーを動かし続けます。

| 項目 | 内容 |
| --- | --- |
| 入力 | 研究プロフィール、論文、PDF、ホームページ、Google Scholar ページ |
| 出力 | 毎日の論文 digest、精読レポート、週次プロフィールレポート |
| Runtime | ローカル Python CLI、ローカルブラウザ GUI、SQLite、任意の Feishu/Lark webhook + ngrok |
| Benchmark | HuggingFace の PaperFlow-Bench と公開評価スクリプト |

## デスクトッププレビュー

PaperFlow には offline-first のデスクトップブラウザ GUI があります。CLI と同じ SQLite 状態とバックエンドワークフローを使うため、静的 mock ではありません。論文取得、フィードバック、精読レポート、Wiki グラフ更新、設定はすべてローカルバックエンドを通ります。

<div align="center">
  <img src="https://github.com/user-attachments/assets/c852c134-5ddb-478e-8a13-3fa313dcd812" alt="PaperFlow offline desktop workflow demo" width="92%">
</div>

<br>

<details>
<summary>デスクトップスクリーンショットを見る</summary>

| 毎日の論文ストリーム | Knowledge Wiki グラフ |
| --- | --- |
| <img src="https://github.com/user-attachments/assets/018aa646-41fa-4967-b4d4-6d6a54df51cf" alt="PaperFlow daily paper recommendation stream"> | <img src="https://github.com/user-attachments/assets/305279b3-1350-4169-887c-99c0cac29a15" alt="PaperFlow knowledge Wiki graph"> |
| 日付指定の pull、ソースフィルタ、候補メトリクス、論文アクション、バックエンドタスク状態。 | バックエンド由来の論文、トピック、手法、プロフィール、引用関係。 |

| 引用付き Wiki Q&A | ローカル設定 |
| --- | --- |
| <img src="https://github.com/user-attachments/assets/6685dd75-e2e2-45d1-b440-1ca5325eca1d" alt="PaperFlow cited local Wiki question answering"> | <img src="https://github.com/user-attachments/assets/a629cc1e-e26e-4878-9eb3-97565153b711" alt="PaperFlow local settings and source configuration"> |
| クリック可能な引用マーカーとソースカードを備えたストリーミング回答。 | Provider キー、保存先、論文ソース、会議アクセス、エクスポート設定。 |

</details>

### プロダクトフレームワーク

<img src="https://github.com/user-attachments/assets/60ff5a52-5d09-46c2-be0d-1933c19515b6" alt="PaperFlow product framework diagram" width="100%">

デスクトップのループはローカル優先です。プロフィール状態、論文 push、フィードバック、精読レポート、Wiki ノードは、外部 provider や Feishu/Lark export を明示的に有効化しない限りディスク上に残ります。

## なぜ PaperFlow か

科学論文推薦は一度きりのランキングではありません。研究者が本当に知りたいのは **今日何を読むべきか、そして明日システムはどう適応すべきか** です。

| 従来の論文アラート | PaperFlow |
| --- | --- |
| 静的キーワードまたはプロフィール照合 | フィードバックで更新される構造化プロフィール |
| 毎日同じ feed | 日付別候補プールと digest 予算 |
| 推薦のみ | 推薦 + 精読レポート + フィードバックループ |
| 明示的な drift 処理なし | 短期・長期の興味 drift をモデル化 |
| 長期再現が難しい | PaperFlow-Bench の公開 episodes と評価器 |

## 主な機能

| 機能 | 内容 |
| --- | --- |
| プロフィール初期化 | テキスト、PDF、ホームページ、Google Scholar から研究プロフィールを作成 |
| 毎日推薦 | arXiv、OpenReview、ジャーナル論文を取得し、個人化 digest をランキング |
| 精読レポート | メタデータと PDF 内容から個人化された論文レポートを生成 |
| フィードバック学習 | CLI、GUI、Feishu/Lark、選択、スキップ、既読、自然言語から同じプロフィールを更新 |
| ローカル研究 Wiki | push、レポート、引用、フィードバック、プロフィール信号を検索可能なローカルグラフへ保存 |
| 引用付き Wiki Q&A | 必要に応じてローカル証拠で回答し、クリック可能な引用と `@` 参照をサポート |
| オフライン GUI | pull、feedback、レポート閲覧、Wiki グラフ、Q&A、設定のローカル UI |
| Drift 適応 | 日単位で短期・長期の興味変化を追跡 |
| Feishu/Lark Bot | 毎日 push と週報を送り、チャット feedback と PDF 要求を処理 |
| Benchmark ツール | PaperFlow-Bench のダウンロード、予測、評価 |

## クイックスタート

日常フローは 5 ステップです。1-3 は初回のみ、4-5 が日常操作です。

```bash
# 1. インストール
git clone https://github.com/OpenRaiser/PaperFlow.git
cd PaperFlow
pip install -e ".[all]"          # フルインストール。最小 CLI は `pip install -e .`

# 2. provider を設定
cp .env.example .env
# .env を編集し PAPERFLOW_LLM_PROVIDER と、本番用 embedding backend を設定

# 3. runtime 初期化 + ユーザープロフィール作成（必須）
paperflow init
paperflow doctor
paperflow profile \
  --user-id user_alice \
  --natural-language "I work on LLM agents for scientific discovery, \
literature mining, and automated paper reading."

# 4. 毎日 push
paperflow daily --user-id user_alice

# 5. 選択した論文を読む
paperflow read 1 3 7 --user-id user_alice

# 任意: ローカル GUI を使う
paperflow gui
```

> **ステップ 3 は必須です。** `paperflow daily / read / feedback` は `paperflow profile` が作成したプロフィールを読みます。これを省略すると個人化信号がなく、`paperflow read` も読む push を持てません。

### オフライン smoke test

```bash
paperflow demo
```

Demo は決定的な mock/hash provider を使うため、API key もネットワークも不要です。

## Provider 設定

```bash
cp .env.example .env
```

`PAPERFLOW_*` 変数が標準設定です。初期状態は高速確認用の no-download embedding ですが、実際の推薦品質には semantic embedding backend が必要です。

### Option A: 推奨本番設定

```env
PAPERFLOW_LLM_PROVIDER=openai
PAPERFLOW_LLM_MODEL=gpt-4o-mini

PAPERFLOW_EMBED_PROVIDER=openai
PAPERFLOW_EMBED_MODEL=text-embedding-3-small

OPENAI_API_KEY=sk-...
# OPENAI_BASE_URL=https://your-openai-compatible-gateway/v1
```

`OPENAI_BASE_URL` により OpenAI、DashScope、Azure OpenAI、vLLM などの OpenAI 互換 gateway を利用できます。認証情報がない場合は、可能な箇所で mock/hash provider に fallback します。

### Option B: ダウンロードなしテスト

```env
PAPERFLOW_LLM_PROVIDER=mock
PAPERFLOW_EMBED_PROVIDER=hash
```

高速で決定的ですが、hash ベクトルは実際の意味的類似度を表しません。

### Option C: 高品質ローカル embedding

```env
PAPERFLOW_EMBED_PROVIDER=sentence_transformers
PAPERFLOW_EMBED_MODEL=BAAI/bge-m3
PAPERFLOW_EMBED_DIMENSIONS=1024
```

embedding API key は不要ですが、初回にモデル重みをダウンロードします。

```bash
paperflow doctor
```

runtime データは `data/` に保存され、Git からは無視されます。

## ユーザープロフィール初期化

PaperFlow は **`user_id` ごとに 1 つのプロフィール** を保持します。最初の `daily` の前に必ず 1 つ作成してください。

```bash
# (a) 自然言語の自己説明
paperflow profile \
  --user-id user_alice \
  --natural-language "I work on LLM agents for scientific discovery, \
literature mining, and automated paper reading."

# (b) 自分の論文または関心論文
paperflow profile --user-id user_alice --pdf /path/to/my-paper.pdf

# (c) Google Scholar プロフィール
paperflow profile \
  --user-id user_alice \
  --scholar-url "https://scholar.google.com/citations?user=..."

# (d) 個人または研究室ホームページ
paperflow profile \
  --user-id user_alice \
  --homepage-url "https://example.edu/~alice"
```

`paperflow profile` は既存プロフィールに信号をマージします。最初から作り直す場合だけ `--reset-existing` を使います。

```bash
python scripts/show_profile.py user_alice
```

## ローカル GUI

```bash
paperflow gui
```

インストールなしのプレビュー: [PaperFlow GUI Preview](https://openraiser.github.io/PaperFlow/deployments/desktop/static/index.html?demo=1).

GUI は CLI と同じ SQLite を使い、実際の毎日フローを対象にしています。

- ユーザープロフィールを選び、方向サマリーを見る
- 今日または過去日付の論文を pull
- 長時間 pull を backend task として保持し UI が状態を poll
- 精読、不感兴趣、後で読むをマーク
- feedback を送信しプロフィール/Wiki を更新
- 精読レポートを生成または再表示
- Wiki グラフを閲覧しローカル知識ノードを検索
- 引用付きでローカル Wiki に質問
- providers、ソース、保存先、export を設定

```bash
paperflow gui --port 8766
paperflow gui --host 0.0.0.0 --no-browser
```

詳細: [deployments/desktop/README.md](https://github.com/OpenRaiser/PaperFlow/blob/main/deployments/desktop/README.md).

## CLI の使い方

```bash
paperflow --help
```

| コマンド | 目的 |
| --- | --- |
| `paperflow init` | runtime ディレクトリと SQLite テーブルを作成 |
| `paperflow doctor` | 依存関係、認証情報、パスを確認 |
| `paperflow demo` | オフライン provider demo を実行 |
| `paperflow profile` | テキスト、PDF、Scholar、ホームページからプロフィール作成/更新 |
| `paperflow daily` | 毎日の個人化 paper push を生成 |
| `paperflow read` | 精読レポートを生成 |
| `paperflow wiki` | ローカル Wiki を一覧・検索・確認 |
| `paperflow feedback` | 過去 push への feedback を記録 |
| `paperflow gui` | ローカル GUI を起動 |
| `paperflow eval` | PaperFlow-Bench 予測を評価 |

```bash
paperflow daily \
  --user-id user_role1 \
  --days 1 \
  --output data/daily_push.txt \
  --dry-run

paperflow read 1 3 7 --user-id user_role1 --no-feishu
paperflow read 1 3 7 --user-id user_role1 --push-id push_20260401_090000 --no-feishu
```

ローカル Wiki:

```bash
paperflow wiki backfill --user-id user_role1
paperflow wiki topics --user-id user_role1
paperflow wiki stats --user-id user_role1
paperflow wiki search "graph rag" --user-id user_role1
paperflow wiki ask "What have I read about graph RAG?" --user-id user_role1
```

Obsidian export:

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

Feishu/Lark 文書 export: [docs/feishu-doc-export.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-doc-export.md).

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

CLI、GUI、Feishu/Lark の feedback は同じ SQLite に保存され、同じプロフィールを更新します。詳細: [docs/feedback-loop.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feedback-loop.md).

## Feishu/Lark Bot

PaperFlow を定期 push と週報付きの chat bot として使うための任意機能です。文書 export だけなら [docs/feishu-doc-export.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-doc-export.md) を使います。

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

出力された Request URL を Feishu/Lark に貼り、`im.message.receive_v1` を有効化します。

| Job | デフォルト schedule |
| --- | --- |
| Daily paper push | 09:00, Asia/Shanghai |
| Weekly report | Monday 10:00, Asia/Shanghai |

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

ガイド: [docs/feishu-webhook-setup.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-webhook-setup.md).

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

## リポジトリ構成

```text
PaperFlow/
  paperflow/                 CLI と provider 抽象
  agents/                    コア workflow agents
  skills/                    fetching、parsing、profile、storage helpers
  deployments/desktop/       任意のローカルブラウザ GUI
  deployments/feishu/        任意の Feishu/Lark bot
  experiments/               Benchmark と再現スクリプト
  scripts/                   運用ユーティリティ
  config/                    ソース、scoring、方向設定
  docs/                      ドキュメント
  tests/                     unit / integration tests
```

## 開発チェック

```bash
pytest tests -q
pytest experiments/tests -q
```

## ドキュメント

- [docs/README.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/README.md)
- [docs/quickstart.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/quickstart.md)
- [docs/configuration.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/configuration.md)
- [docs/feedback-loop.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feedback-loop.md)
- [deployments/desktop/README.md](https://github.com/OpenRaiser/PaperFlow/blob/main/deployments/desktop/README.md)
- [PaperFlow GUI Preview](https://openraiser.github.io/PaperFlow/deployments/desktop/static/index.html?demo=1)
- [docs/feishu-doc-export.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-doc-export.md)
- [docs/feishu-webhook-setup.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-webhook-setup.md)

## 引用

```bibtex
@article{wang2026paperflow,
  title={PaperFlow: Profiling, Recommending, and Adapting Across Daily Paper Streams},
  author={Wang, Fuqiang and Tan, Song and Guo, Zheng and Fu, Jiaohao and Xu, Xinglong and Yu, Bihui and Dong, Jie and Sun, Zheng and Li, Siyuan and Wei, Jingxuan and others},
  journal={arXiv preprint arXiv:2606.07454},
  year={2026}
}
```

正式な引用情報は論文公開後に更新されます。

## License

PaperFlow は MIT License で公開されています。[LICENSE](https://github.com/OpenRaiser/PaperFlow/blob/main/LICENSE) を参照してください。
