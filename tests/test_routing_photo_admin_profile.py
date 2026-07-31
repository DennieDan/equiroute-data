import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "street-intelligence" / "index.html"
SCHEMA = ROOT / "supabase" / "schema.sql"
PROFILE = ROOT / "profile" / "index.html"


class RoutingPhotoAdminProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.platform = PLATFORM.read_text()
        cls.schema = SCHEMA.read_text().lower()
        cls.profile = PROFILE.read_text()

    def test_platform_uses_relevant_extensionless_route_name(self):
        self.assertIn("Street Intelligence", self.platform)
        self.assertIn("street-intelligence/", self.platform)
        self.assertNotIn("earth_accessibility.html", self.platform)
        self.assertNotIn("Earth Accessibility", self.platform)

    def test_toasts_have_real_fadeout_and_photo_prompt_is_toast_only(self):
        self.assertIn("toast.fade-out", self.platform)
        self.assertIn("toastOut", self.platform)
        self.assertIn("showPhotoUploadToast", self.platform)
        self.assertIn("Settings → Photo crowdsourcing", self.platform)
        self.assertIn("persist: false", self.platform)
        self.assertNotIn('id="photoUploadPanel"', self.platform)

    def test_settings_has_photo_crowdsourcing_and_account_management(self):
        self.assertIn("Photo crowdsourcing", self.platform)
        self.assertIn("CV first review", self.platform)
        self.assertIn("human-in-the-loop approval", self.platform)
        self.assertIn("photoProgressRail", self.platform)
        self.assertIn("Account management", self.platform)
        self.assertIn("managedUsersTable", self.platform)
        self.assertIn("employee_id", self.platform)
        self.assertIn("department", self.platform)
        self.assertIn("platform_purpose", self.platform)

    def test_schema_has_company_admin_and_photo_review_fields(self):
        for token in [
            "company_external_id",
            "managed_by_user_external_id",
            "employee_id",
            "full_name",
            "department",
            "position_title",
            "salutation",
            "platform_purpose",
            "photo_review_jobs",
            "review_stage",
            "human_review_status",
        ]:
            self.assertIn(token, self.schema)

    def test_profile_contrast_and_extensionless_back_link(self):
        self.assertIn("profile-page", self.profile)
        self.assertIn("--profile-card", self.profile)
        self.assertIn("color:#f8fafc", self.profile.replace(" ", ""))
        self.assertNotIn('href="earth_accessibility.html"', self.profile)
        self.assertIn('href="../street-intelligence/"', self.profile)


if __name__ == "__main__":
    unittest.main()
