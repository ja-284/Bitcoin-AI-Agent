"""
Settings and API keys, read from environment variables.

Locally, these come from a `.env` file (see .env.example) loaded by python-dotenv.
In GitHub Actions, they come from the repo's encrypted Secrets instead — same variable
names, no code changes needed. Never hard-code a real key anywhere in this project.
"""

import os

from dotenv import load_dotenv

load_dotenv()

COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")  # optional: works without one, but rate limits are lower
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")  # Supabase Postgres connection string
HEARTBEAT_URL = os.getenv("HEARTBEAT_URL")  # optional: dead-man's-switch ping URL
