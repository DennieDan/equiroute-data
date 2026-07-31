import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "street-intelligence" / "index.html"
SCHEMA = ROOT / "supabase" / "schema.sql"


class EarthUiControlsNotificationTests(unittest.TestCase):
    def html(self):
        return HTML.read_text()

    def test_topbar_uses_clean_labels_and_single_view_dropdown(self):
        text = self.html()
        self.assertIn('<div class="brand">JalanLens</div>', text)
        self.assertNotIn('JalanLens Earth', text)
        self.assertNotIn('Earth Satellite', text)
        self.assertIn('<select id="viewModeSelect"', text)
        self.assertIn('<option value="earth">Earth View</option>', text)
        self.assertIn('<option value="street">Street View</option>', text)
        self.assertNotIn('id="earthBtn"', text)
        self.assertNotIn('id="streetBtn"', text)

    def test_street_only_controls_and_contrasting_dropdown_theme(self):
        text = self.html()
        for required in [
            '.street-only-control',
            '.street-mode .street-only-control',
            'body[data-theme="light"]',
            'body[data-theme="dark"]',
            'id="themeToggleBtn"',
            '◐',
        ]:
            self.assertIn(required, text)
        self.assertRegex(text, r"select\s*\{[^}]*background:\s*var\(--control-bg\)", text)
        self.assertRegex(text, r"select option\s*\{[^}]*background:\s*var\(--option-bg\)", text)

    def test_status_is_toast_notification_not_persistent_5m_segment_box(self):
        text = self.html()
        self.assertNotIn('5 m segments', text)
        self.assertNotIn('id="status">Loading Clementi digital twin', text)
        self.assertIn('id="toastStack"', text)
        self.assertIn('id="notificationsPanel"', text)
        self.assertIn('id="notificationBellBtn"', text)
        self.assertIn('Clear notification history', text)
        self.assertIn('createNotification(', text)
        self.assertIn('street parts', text)

    def test_notification_schema_exists(self):
        sql = SCHEMA.read_text()
        self.assertIn('create table if not exists public.app_notifications', sql)
        self.assertIn('clear notification history', self.html().lower())
        self.assertIn('grant select, insert, update on public.app_notifications', sql)


if __name__ == "__main__":
    unittest.main()
