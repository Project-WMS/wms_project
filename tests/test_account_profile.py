import unittest

from fastapi import HTTPException
from pydantic import ValidationError

from app.modules.accounts import service
from app.modules.accounts.schemas import UpdateMyProfileRequest


class FakeResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class FakeDatabase:
    def __init__(self, row):
        self.row = row
        self.statement = ""
        self.params = {}
        self.commits = 0

    def execute(self, statement, params):
        self.statement = str(statement)
        self.params = params
        return FakeResult(self.row)

    def commit(self):
        self.commits += 1


class AccountProfileTests(unittest.TestCase):
    def test_update_changes_only_authenticated_users_display_name(self):
        db = FakeDatabase({
            "id": 17,
            "username": "worker17",
            "full_name": "Nguyễn Văn B",
            "role": "worker",
            "approval_status": "approved",
            "is_active": True,
            "created_at": None,
        })

        result = service.update_my_profile(db, 17, "  Nguyễn Văn B  ")

        self.assertEqual(db.params, {"full_name": "Nguyễn Văn B", "id": 17})
        self.assertIn("WHERE id = :id AND approval_status = 'approved' AND is_active = TRUE", db.statement)
        self.assertNotIn("role =", db.statement)
        self.assertEqual(result["user"]["role"], "worker")
        self.assertEqual(db.commits, 1)

    def test_profile_update_rejects_blank_names_without_writing(self):
        db = FakeDatabase(None)

        with self.assertRaises(HTTPException) as raised:
            service.update_my_profile(db, 17, "   ")

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(db.commits, 0)
        self.assertEqual(db.statement, "")

    def test_profile_update_reports_inactive_or_missing_account(self):
        db = FakeDatabase(None)

        with self.assertRaises(HTTPException) as raised:
            service.update_my_profile(db, 17, "Nguyễn Văn B")

        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(db.commits, 0)

    def test_profile_request_rejects_role_or_status_changes(self):
        with self.assertRaises(ValidationError):
            UpdateMyProfileRequest.model_validate({
                "full_name": "Nguyễn Văn B",
                "role": "admin",
                "is_active": True,
            })


if __name__ == "__main__":
    unittest.main()
