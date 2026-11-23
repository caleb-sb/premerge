"""Shared test case that builds the fixture once and isolates git config."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tests.fixture import isolated_env, make_fixture


class FixtureCase(unittest.TestCase):
    """setUpClass builds a fresh fixture in `cls.work`; subclasses must not mutate it persistently."""

    work: Path

    @classmethod
    def setUpClass(cls):
        cls._env = {k: os.environ.get(k) for k in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM")}
        env = isolated_env()
        os.environ["GIT_CONFIG_GLOBAL"], os.environ["GIT_CONFIG_NOSYSTEM"] = env["GIT_CONFIG_GLOBAL"], "1"
        cls._tmp = tempfile.TemporaryDirectory()
        cls.work = make_fixture(Path(cls._tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()
        for k, v in cls._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
