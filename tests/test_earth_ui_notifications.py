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
        self.assertIn('class="brand"', text)
        self.assertIn('src="../assets/jalanlens-logo.png"', text)
        self.assertIn('<span>JalanLens</span>', text)
        self.assertNotIn('JalanLens Earth', text)
        self.assertNotIn('Earth Satellite', text)
        self.assertIn('id="viewModeSelect"', text)
        self.assertIn('<option value="earth">Earth View</option>', text)
        self.assertIn('<option value="street">Street View</option>', text)
        self.assertNotIn('id="earthBtn"', text)
        self.assertNotIn('id="streetBtn"', text)

    def test_street_only_controls_and_contrasting_dropdown_theme(self):
        text = self.html()
        css = (ROOT / "harvard.css").read_text()
        for required in [
            '.street-only-control',
            '.street-mode .street-only-control',
            'body[data-theme="light"]',
            'body[data-theme="dark"]',
            'id="themeToggleBtn"',
            '◐ System',
            '☀ Light',
            '☾ Dark',
            'document.documentElement.dataset.theme',
        ]:
            self.assertIn(required, text)
        self.assertRegex(text, r"select\s*\{[^}]*background:\s*var\(--control-bg\)", text)
        self.assertRegex(text, r"select option\s*\{[^}]*background:\s*var\(--option-bg\)", text)
        for required_css in [
            'html[data-theme="light"] body:has(#map)',
            'html[data-theme="dark"] body:has(#map)',
            'background-color: var(--control-bg)',
            'body:has(#map) #topbar button',
            'body:has(#map) #topbar .buttonlike',
            'color: var(--control-fg)',
            'background: var(--option-bg)',
            'color: var(--option-fg)',
        ]:
            self.assertIn(required_css, css)

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

    def test_scorecard_does_not_duplicate_street_part_length_metric(self):
        text = self.html()
        self.assertIn('m street part', text)
        self.assertNotIn('["Length", `${Math.round(m.length_m * 10) / 10} m`, "street-part distance"]', text)
        self.assertNotIn('street-part distance', text)

    def test_authority_score_card_flips_to_component_breakdown(self):
        text = self.html()
        for snippet in [
            'detail-flip-inner',
            'id="scoreFlipBtn"',
            'Score contributors',
            'id="scoreBreakdownList"',
            'function componentScoreRows',
            'setScoreCardFlipped(true)',
            'state.role === "authority"',
            'Clear width',
            'Tactile guidance',
            'component_scores: raw.component_scores',
        ]:
            self.assertIn(snippet, text)

    def test_synthetic_agent_count_removes_explanatory_suffix(self):
        text = self.html()
        self.assertIn('currently here</small>', text)
        self.assertNotIn('synthetic, not real-person tracking', text)

    def test_notification_schema_exists(self):
        sql = SCHEMA.read_text()
        self.assertIn('create table if not exists public.app_notifications', sql)
        self.assertIn('clear notification history', self.html().lower())
        self.assertIn('grant select, insert, update on public.app_notifications', sql)


if __name__ == "__main__":
    unittest.main()
