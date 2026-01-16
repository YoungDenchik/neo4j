from __future__ import annotations

import os
from openai import OpenAI

from dotenv import load_dotenv

load_dotenv()


def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    if not base_url:
        raise RuntimeError("OPENAI_BASE_URL is not set")

    return OpenAI(
        api_key=api_key,
        base_url=base_url,
    )
