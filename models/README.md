# Local Models

Put large local model snapshots in this folder.

Recommended layout:

```text
models/
  Qwen3-Embedding-8B/
```

This directory is ignored by git except for this file and `.gitkeep`, so large model weights will not be pushed to GitHub.

To use a downloaded local embedding model, set these values in `.env`:

```env
EMBEDDING_PROVIDER=local
LOCAL_EMBEDDING_MODEL_PATH=./models/Qwen3-Embedding-8B
LOCAL_EMBEDDING_TRUST_REMOTE_CODE=true
```

If `LOCAL_EMBEDDING_MODEL_PATH` exists, the code will use that local directory first.

If you prefer a hosted API instead of local weights, use:

```env
EMBEDDING_PROVIDER=hf_api
HF_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B
HF_INFERENCE_PROVIDER=auto
HF_API_TIMEOUT=60
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx
```
