"""Tests never send traces: set before backedcv.settings loads .env (which never overrides)."""

import os

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
