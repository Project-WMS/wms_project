"""Kiểm thử chuẩn hóa cấu hình kết nối PostgreSQL."""
import os
import unittest
from unittest.mock import patch

from app.core.config import database_url


class DatabaseURLTests(unittest.TestCase):
    def test_postgresql_schemes_use_psycopg_three(self):
        for scheme in ("postgresql://", "postgres://", "postgresql+psycopg2://"):
            with self.subTest(scheme=scheme):
                with patch.dict(os.environ, {"DATABASE_URL": f"{scheme}user:pass@db.example:5432/wms"}, clear=True):
                    self.assertEqual(
                        database_url(),
                        "postgresql+psycopg://user:pass@db.example:5432/wms",
                    )

    def test_psycopg_scheme_is_preserved(self):
        url = "postgresql+psycopg://user:pass@db.example:5432/wms"
        with patch.dict(os.environ, {"DATABASE_URL": url}, clear=True):
            self.assertEqual(database_url(), url)

    def test_db_fields_build_psycopg_url(self):
        with patch.dict(
            os.environ,
            {
                "DB_USER": "user",
                "DB_PASSWORD": "pass",
                "DB_HOST": "db.example",
                "DB_PORT": "5432",
                "DB_NAME": "wms",
            },
            clear=True,
        ):
            self.assertEqual(
                database_url(),
                "postgresql+psycopg://user:pass@db.example:5432/wms",
            )


if __name__ == "__main__":
    unittest.main()
