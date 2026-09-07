import os
from functools import lru_cache

import lmstudio as lms
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = os.getenv("LM_MODEL", "qwen/qwen3-4b-2507")

@lru_cache(maxsize=None)
def get_model(model_key: str | None = None) -> lms.LLM:
    """Return a cached handle to the LM Studio model, loading it on first use."""
    return lms.llm(model_key or DEFAULT_MODEL)
