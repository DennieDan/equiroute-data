import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "street-intelligence" / "index.html"
SCHEMA = ROOT / "supabase" / "schema.sql"
PROFILE = ROOT / "profile" / "index.html"
CROWD_PHOTOS = ROOT / "crowd-photos" / "index.html"
CROWD_PHOTOS_APP = ROOT / "crowd-photos" / "app.js"
RLS = ROOT / "supabase" / "rls.sql"


class RoutingPhotoAdminProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.platform = PLATFORM.read_text()
        cls.schema = SCHEMA.read_text().lower()
        cls.profile = PROFILE.read_text()
        cls.crowd_photos = CROWD_PHOTOS.read_text()
        cls.crowd_photos_app = CROWD_PHOTOS_APP.read_text()
        cls.rls = RLS.read_text().lower()

    def test_platform_uses_relevant_extensionless_route_name(self):
        self.assertIn("Street Intelligence", self.platform)
        self.assertIn("street-intelligence/", self.platform)
        self.assertNotIn("earth_accessibility.html", self.platform)
        self.assertNotIn("Earth Accessibility", self.platform)

    def test_toasts_have_real_fadeout_and_photo_prompt_is_toast_only(self):
        self.assertIn("toast.fade-out", self.platform)
        self.assertIn("toastOut", self.platform)
        self.assertIn("showPhotoUploadToast", self.platform)
        self.assertIn("dedicated Photo crowdsourcing page", self.platform)
        self.assertIn("persist: false", self.platform)
        self.assertNotIn('id="photoUploadPanel"', self.platform)

    def test_settings_has_photo_crowdsourcing_and_account_management(self):
        self.assertIn("Photo crowdsourcing", self.platform)
        self.assertIn("Open dedicated page", self.platform)
        self.assertNotIn('id="photoProgressRail"', self.platform)
        self.assertNotIn('id="photoUploadBtn"', self.platform)
        self.assertNotIn('id="photoUploadInput"', self.platform)
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
            "photo_review_comments",
            "reviewer_external_id",
            "review_comment",
            "reviewed_at",
            "review_photo_submission",
        ]:
            self.assertIn(token, self.schema)

    def test_photo_crowdsourcing_has_complete_four_step_workflow(self):
        for token in [
            'data-step="upload"',
            'data-step="cv"',
            'data-step="staff"',
            'data-step="approved"',
            'id="mySubmissions"',
            'id="reviewQueue"',
            'id="reviewDetail"',
            'id="approvedGallery"',
            'id="activationModal"',
            'id="currentPhotoPreview"',
            'id="newPhotoPreview"',
            'id="confirmActivationBtn"',
        ]:
            self.assertIn(token, self.crowd_photos)
        for token in [
            "../data/street_view_registry.json",
            "analyzePhoto",
            'validation_status: "needs_review"',
            "loadReviewQueue",
            'decideReview("approved")',
            'decideReview("rejected")',
            'rpc("review_photo_submission"',
            'rpc("activate_approved_photo"',
            "openActivationModal",
            "Confirm replacement",
            "footpathGroups",
            "footpath-toggle",
            "street-part-toggle",
            "street_parts!street_photos_street_part_id_fkey!inner",
            "streets!street_parts_street_id_fkey",
        ]:
            self.assertIn(token, self.crowd_photos_app)
        self.assertIn("Approve photo", self.crowd_photos_app)
        self.assertNotIn("Approve and make active", self.crowd_photos_app)

    def test_pending_upload_policy_and_atomic_review_activation(self):
        self.assertIn("public insert pending crowd photos", self.rls)
        self.assertIn("validation_status = 'needs_review'", self.rls)
        self.assertIn("is_active = false", self.rls)
        self.assertIn("validation_status = 'accepted',\n      is_active = false", self.schema)
        self.assertIn("photo_activation_events", self.schema)
        self.assertIn("activate_approved_photo", self.schema)
        self.assertIn("previous_photo_id", self.schema)
        self.assertIn("authority_confirmed_active_replacement", self.schema)
        self.assertIn("active_photo_id = v_photo.id", self.schema)

    def test_profile_contrast_and_extensionless_back_link(self):
        self.assertIn("profile-page", self.profile)
        self.assertIn("--profile-card", self.profile)
        self.assertIn("color:#f8fafc", self.profile.replace(" ", ""))
        self.assertNotIn('href="earth_accessibility.html"', self.profile)
        self.assertIn('href="../street-intelligence/"', self.profile)


if __name__ == "__main__":
    unittest.main()
