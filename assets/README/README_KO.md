<div align="center">

# PaperFlow

**과학 논문을 위한 동적 개인화 추천, 정독, 리포트 생성 시스템.**

PaperFlow는 매일의 논문 탐색을 닫힌 루프 연구 워크플로로 바꿉니다. 사용자 프로필을 만들고, 오늘의 논문을 정렬하고, 유용한 논문을 정독하고, 피드백을 수집해 내일의 추천에 다시 반영합니다.

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

**언어**:
[English](https://github.com/OpenRaiser/PaperFlow#readme) ·
[简体中文](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_CN.md) ·
[日本語](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_JA.md) ·
[Español](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_ES.md) ·
[Français](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_FR.md) ·
[Português](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_PT.md) ·
[한국어](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_KO.md)

[빠른 시작](#빠른-시작) | [데스크톱 미리보기](#데스크톱-미리보기) | [로컬 GUI](#로컬-gui) |
[GUI 미리보기](https://openraiser.github.io/PaperFlow/deployments/desktop/static/index.html?demo=1) |
[CLI 사용법](#cli-사용법) |
[피드백 루프](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feedback-loop.md) |
[Feishu/Lark Bot](#feishulark-bot) |
[PaperFlow-Bench](#paperflow-bench) | [재현](https://github.com/OpenRaiser/PaperFlow/blob/main/experiments/REPRODUCE.md)

<img src="https://github.com/user-attachments/assets/fd31a62b-00a4-4210-82cb-1ffd080de254" alt="PaperFlow personalized scientific reading banner" width="100%">

</div>

---

## 현재 릴리스

첫 공개 릴리스는 **CLI + 로컬 브라우저 GUI + 선택적 Feishu/Lark Bot** 버전입니다. PaperFlow는 터미널에서 완전히 실행할 수 있고, 논문 선택을 위해 로컬 GUI를 열 수 있으며, 예약 발송이 필요하면 Feishu/Lark webhook 서버를 유지할 수 있습니다.

| 항목 | 설명 |
| --- | --- |
| 입력 | 연구 프로필, 논문, PDF, 홈페이지, Google Scholar 페이지 |
| 출력 | 일일 논문 digest, 정독 리포트, 주간 프로필 리포트 |
| Runtime | 로컬 Python CLI, 로컬 브라우저 GUI, SQLite, 선택적 Feishu/Lark webhook + ngrok |
| Benchmark | HuggingFace의 PaperFlow-Bench 및 공개 평가 스크립트 |

## 데스크톱 미리보기

PaperFlow는 offline-first 데스크톱 브라우저 GUI를 제공합니다. CLI와 같은 로컬 SQLite 상태 및 백엔드 워크플로를 사용하므로 정적 mock이 아닙니다. 논문 pull, 피드백, 정독 리포트, Wiki 그래프 업데이트, 설정이 모두 로컬 백엔드를 거칩니다.

<div align="center">
  <img src="https://github.com/user-attachments/assets/c852c134-5ddb-478e-8a13-3fa313dcd812" alt="PaperFlow offline desktop workflow demo" width="92%">
</div>

<br>

<details>
<summary>데스크톱 스크린샷 보기</summary>

| 일일 논문 스트림 | 지식 Wiki 그래프 |
| --- | --- |
| <img src="https://github.com/user-attachments/assets/018aa646-41fa-4967-b4d4-6d6a54df51cf" alt="PaperFlow daily paper recommendation stream"> | <img src="https://github.com/user-attachments/assets/305279b3-1350-4169-887c-99c0cac29a15" alt="PaperFlow knowledge Wiki graph"> |
| 날짜 기반 pull, 소스 필터, 후보 지표, 논문 액션, 백엔드 작업 상태. | 백엔드에서 만든 논문, 주제, 방법, 프로필, 인용 관계. |

| 인용 포함 Wiki Q&A | 로컬 설정 |
| --- | --- |
| <img src="https://github.com/user-attachments/assets/6685dd75-e2e2-45d1-b440-1ca5325eca1d" alt="PaperFlow cited local Wiki question answering"> | <img src="https://github.com/user-attachments/assets/a629cc1e-e26e-4878-9eb3-97565153b711" alt="PaperFlow local settings and source configuration"> |
| 클릭 가능한 참고문헌 마커와 소스 카드가 있는 스트리밍 답변. | Provider key, 저장 경로, 논문 소스, 학회 접근, export 설정. |

</details>

### 제품 프레임워크

<img src="https://github.com/user-attachments/assets/60ff5a52-5d09-46c2-be0d-1933c19515b6" alt="PaperFlow product framework diagram" width="100%">

데스크톱 루프는 기본적으로 로컬입니다. 프로필 상태, 논문 push, 피드백, 정독 리포트, Wiki 노드는 외부 provider나 Feishu/Lark export를 명시적으로 켜지 않는 한 디스크에 남습니다.

## 왜 PaperFlow인가

과학 논문 추천은 한 번의 랭킹 문제가 아닙니다. 연구자가 실제로 묻는 것은 **오늘 무엇을 읽고, 내일 시스템이 어떻게 적응해야 하는가** 입니다.

| 기존 논문 알림 | PaperFlow |
| --- | --- |
| 정적 키워드 또는 프로필 매칭 | 피드백으로 업데이트되는 구조화 프로필 |
| 매일 같은 feed | 날짜별 후보 풀과 일일 digest 예산 |
| 추천만 제공 | 추천 + 정독 리포트 + 피드백 루프 |
| 명시적 drift 처리 없음 | 단기/장기 관심 drift 모델링 |
| 장기 재현이 어려움 | 공개 PaperFlow-Bench episode 및 evaluator |

## 핵심 기능

| 기능 | 역할 |
| --- | --- |
| 프로필 부트스트랩 | 텍스트, PDF, 홈페이지, Google Scholar에서 연구 프로필 생성 |
| 일일 추천 | arXiv, OpenReview, 저널 논문을 가져와 개인화 digest 생성 |
| 정독 리포트 | 메타데이터와 PDF 내용으로 개인화 논문 리포트 생성 |
| 피드백 학습 | CLI, GUI, Feishu/Lark, 선택, 스킵, 읽음, 자연어 피드백으로 같은 프로필 업데이트 |
| 로컬 연구 Wiki | push, 리포트, 인용, 피드백, 프로필 신호를 검색 가능한 로컬 그래프로 저장 |
| 인용 포함 Wiki Q&A | 필요 시 로컬 증거로 답하고, 클릭 가능한 인용 및 `@` 명시 참조 지원 |
| 오프라인 GUI | pull, feedback, 리포트, Wiki 그래프, Q&A, 설정을 위한 로컬 UI |
| Drift 적응 | 짧은 기간과 긴 기간의 관심 변화를 추적 |
| Feishu/Lark Bot | 일일 push와 주간 리포트 발송, 채팅 피드백과 PDF 요청 처리 |
| Benchmark 도구 | PaperFlow-Bench 다운로드, 예측, 평가 |

## 빠른 시작

일일 흐름은 5단계입니다. 1-3단계는 한 번만 실행하고, 4-5단계가 일상 루틴입니다.

```bash
# 1. 설치
git clone https://github.com/OpenRaiser/PaperFlow.git
cd PaperFlow
pip install -e ".[all]"          # 전체 설치; 최소 CLI는 `pip install -e .`

# 2. provider 설정
cp .env.example .env
# .env에서 PAPERFLOW_LLM_PROVIDER와, 운영 환경의 embedding backend를 설정

# 3. runtime 초기화 + 사용자 프로필 생성(필수)
paperflow init
paperflow doctor
paperflow profile \
  --user-id user_alice \
  --natural-language "I work on LLM agents for scientific discovery, \
literature mining, and automated paper reading."

# 4. 일일 push
paperflow daily --user-id user_alice

# 5. 선택 논문 정독
paperflow read 1 3 7 --user-id user_alice

# 선택: 로컬 GUI 사용
paperflow gui
```

> **3단계는 필수입니다.** `paperflow daily / read / feedback`은 `paperflow profile`이 만든 프로필을 읽습니다. 프로필이 없으면 개인화 점수 신호가 없고, `paperflow read`도 읽을 push가 없습니다.

### 오프라인 smoke test

```bash
paperflow demo
```

Demo는 결정적인 mock/hash provider를 사용하므로 API key나 네트워크가 필요 없습니다.

## Provider 설정

```bash
cp .env.example .env
```

`PAPERFLOW_*` 변수는 표준 설정 표면입니다. 새 설치는 빠른 확인을 위해 no-download embedding을 사용하지만, 실제 추천 품질에는 semantic embedding backend가 필요합니다.

### 옵션 A: 권장 운영 설정

```env
PAPERFLOW_LLM_PROVIDER=openai
PAPERFLOW_LLM_MODEL=gpt-4o-mini

PAPERFLOW_EMBED_PROVIDER=openai
PAPERFLOW_EMBED_MODEL=text-embedding-3-small

OPENAI_API_KEY=sk-...
# OPENAI_BASE_URL=https://your-openai-compatible-gateway/v1
```

`OPENAI_BASE_URL`로 OpenAI, DashScope, Azure OpenAI, vLLM 등 OpenAI 호환 gateway를 사용할 수 있습니다. 자격 증명이 없으면 가능한 곳에서 mock/hash provider로 fallback합니다.

### 옵션 B: 다운로드 없는 테스트

```env
PAPERFLOW_LLM_PROVIDER=mock
PAPERFLOW_EMBED_PROVIDER=hash
```

빠르고 결정적이지만 hash vector는 실제 의미 유사도를 담지 않습니다.

### 옵션 C: 고품질 로컬 embedding

```env
PAPERFLOW_EMBED_PROVIDER=sentence_transformers
PAPERFLOW_EMBED_MODEL=BAAI/bge-m3
PAPERFLOW_EMBED_DIMENSIONS=1024
```

embedding API key는 필요 없지만 첫 실행에서 모델 weight를 다운로드합니다.

```bash
paperflow doctor
```

runtime 데이터는 `data/`에 저장되며 Git에서 무시됩니다.

## 사용자 프로필 초기화

PaperFlow는 **`user_id`마다 하나의 프로필** 을 유지합니다. 첫 `daily` 전에 최소 하나를 만들어야 합니다.

```bash
# (a) 자연어 자기소개
paperflow profile \
  --user-id user_alice \
  --natural-language "I work on LLM agents for scientific discovery, \
literature mining, and automated paper reading."

# (b) 본인이 썼거나 관심 있는 논문
paperflow profile --user-id user_alice --pdf /path/to/my-paper.pdf

# (c) Google Scholar 공개 페이지
paperflow profile \
  --user-id user_alice \
  --scholar-url "https://scholar.google.com/citations?user=..."

# (d) 개인 또는 연구실 홈페이지
paperflow profile \
  --user-id user_alice \
  --homepage-url "https://example.edu/~alice"
```

반복 실행 시 신호는 기본적으로 병합됩니다. 처음부터 다시 만들 때만 `--reset-existing`를 사용하세요.

```bash
python scripts/show_profile.py user_alice
```

## 로컬 GUI

```bash
paperflow gui
```

설치 없이 미리보기: [PaperFlow GUI Preview](https://openraiser.github.io/PaperFlow/deployments/desktop/static/index.html?demo=1).

GUI는 CLI와 같은 로컬 SQLite를 사용합니다.

- 사용자 프로필 선택 및 방향 요약 확인
- 오늘 또는 과거 날짜의 논문 pull
- 긴 pull을 backend task로 유지하고 UI에서 상태 polling
- 정독, 관심 없음, 나중에 보기 표시
- 피드백 제출 및 프로필/Wiki 업데이트
- 정독 리포트 생성 또는 다시 열기
- Wiki 그래프 탐색 및 로컬 지식 노드 검색
- 클릭 가능한 참고문헌과 함께 로컬 Wiki 질문
- provider, source, 저장, export 설정

```bash
paperflow gui --port 8766
paperflow gui --host 0.0.0.0 --no-browser
```

상세 문서: [deployments/desktop/README.md](https://github.com/OpenRaiser/PaperFlow/blob/main/deployments/desktop/README.md).

## CLI 사용법

```bash
paperflow --help
```

| 명령 | 목적 |
| --- | --- |
| `paperflow init` | runtime 디렉터리와 SQLite 테이블 생성 |
| `paperflow doctor` | 의존성, 자격 증명, 경로 확인 |
| `paperflow demo` | 오프라인 provider demo 실행 |
| `paperflow profile` | 텍스트, PDF, Scholar, 홈페이지에서 프로필 생성/수정 |
| `paperflow daily` | 일일 개인화 논문 push 생성 |
| `paperflow read` | 정독 리포트 생성 |
| `paperflow wiki` | 로컬 Wiki 조회, 검색, 확인 |
| `paperflow feedback` | 이전 push에 대한 feedback 기록 |
| `paperflow gui` | 로컬 GUI 시작 |
| `paperflow eval` | PaperFlow-Bench 예측 평가 |

```bash
paperflow daily \
  --user-id user_role1 \
  --days 1 \
  --output data/daily_push.txt \
  --dry-run

paperflow read 1 3 7 --user-id user_role1 --no-feishu
paperflow read 1 3 7 --user-id user_role1 --push-id push_20260401_090000 --no-feishu
```

로컬 Wiki:

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

Feishu/Lark 문서 export: [docs/feishu-doc-export.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-doc-export.md).

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

CLI, GUI, Feishu/Lark feedback은 같은 SQLite에 저장되고 같은 프로필을 업데이트합니다. 자세한 내용: [docs/feedback-loop.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feedback-loop.md).

## Feishu/Lark Bot

예약 push와 주간 리포트를 위한 선택 기능입니다. 문서 export만 필요하면 [docs/feishu-doc-export.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-doc-export.md)를 사용하세요.

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

출력되는 Request URL을 Feishu/Lark 이벤트 구독 페이지에 넣고 `im.message.receive_v1`을 활성화합니다.

| Job | 기본 스케줄 |
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

가이드: [docs/feishu-webhook-setup.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-webhook-setup.md).

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

## 저장소 구조

```text
PaperFlow/
  paperflow/                 CLI 및 provider 추상화
  agents/                    핵심 workflow agents
  skills/                    fetching, parsing, profile, storage helpers
  deployments/desktop/       선택적 로컬 브라우저 GUI
  deployments/feishu/        선택적 Feishu/Lark bot
  experiments/               Benchmark 및 재현 스크립트
  scripts/                   운영 유틸리티
  config/                    소스, scoring, direction 설정
  docs/                      문서
  tests/                     unit / integration tests
```

## 개발 체크

```bash
pytest tests -q
pytest experiments/tests -q
```

## 문서

- [docs/README.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/README.md)
- [docs/quickstart.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/quickstart.md)
- [docs/configuration.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/configuration.md)
- [docs/feedback-loop.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feedback-loop.md)
- [deployments/desktop/README.md](https://github.com/OpenRaiser/PaperFlow/blob/main/deployments/desktop/README.md)
- [PaperFlow GUI Preview](https://openraiser.github.io/PaperFlow/deployments/desktop/static/index.html?demo=1)
- [docs/feishu-doc-export.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-doc-export.md)
- [docs/feishu-webhook-setup.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-webhook-setup.md)

## 인용

```bibtex
@article{wang2026paperflow,
  title={PaperFlow: Profiling, Recommending, and Adapting Across Daily Paper Streams},
  author={Wang, Fuqiang and Tan, Song and Guo, Zheng and Fu, Jiaohao and Xu, Xinglong and Yu, Bihui and Dong, Jie and Sun, Zheng and Li, Siyuan and Wei, Jingxuan and others},
  journal={arXiv preprint arXiv:2606.07454},
  year={2026}
}
```

정식 인용 정보는 논문 출판 후 업데이트됩니다.

## License

PaperFlow는 MIT License로 배포됩니다. [LICENSE](https://github.com/OpenRaiser/PaperFlow/blob/main/LICENSE)를 참고하세요.
