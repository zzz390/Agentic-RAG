"""将 BAAI/bge-small-zh-v1.5 下载到 models/bge-small-zh-v1.5，供本地向量化使用。"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODEL_ID = "BAAI/bge-small-zh-v1.5"
OUTPUT_DIR = PROJECT_ROOT / "models" / "bge-small-zh-v1.5"


def main() -> None:
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

    OUTPUT_DIR.parent.mkdir(parents=True, exist_ok=True)

    from sentence_transformers import SentenceTransformer

    print(f"Downloading {MODEL_ID} (HF_ENDPOINT={os.environ.get('HF_ENDPOINT')})...")
    model = SentenceTransformer(MODEL_ID)
    dim = model.get_sentence_embedding_dimension()
    model.save(str(OUTPUT_DIR))

    print(f"Saved to {OUTPUT_DIR}")
    print(f"Embedding dimension: {dim}")


if __name__ == "__main__":
    main()
