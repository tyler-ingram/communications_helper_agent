import os
import lmstudio as lms
from dotenv import load_dotenv
from contextlib import asynccontextmanager
load_dotenv()

DEFAULT_MODEL = os.getenv("LM_MODEL", "qwen/qwen3-4b-2507")

@asynccontextmanager
async def get_model(model_key: str | None = None):
    async with lms.AsyncClient() as client:
        model = await client.llm.model(model_key or DEFAULT_MODEL, 
            config={
            "contextLength": 128000,
        })
        yield model