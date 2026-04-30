"""Shared pytest fixtures and test environment setup."""

import os

# Force an isolated in-memory database for tests.
# Must be set before guidloc modules are imported anywhere.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["APP_ENV"] = "test"
os.environ["APP_DEBUG"] = "false"
