# agent/llm_config.py
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def get_llm_model() -> str:
    return os.getenv("OPENAI_MODEL", "lapa-function-calling")


def get_fix_model() -> str:
    return os.getenv("OPENAI_FIX_MODEL", get_llm_model())
