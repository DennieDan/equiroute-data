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

    def test_earth_view_shows_harvard_road_name_labels_and_hides_green_route_lines(self):
        text = self.html()
        for snippet in [
            'id="roadNameLabels" aria-hidden="true"',
            'function coverageBoundsForRoadLabels',
            'function roadLabelCandidates',
            'class="road-label-inner"',
            'roadNameLabels.classList.toggle("visible", state.mode === "earth"',
            'Clementi Avenue 3',
            'Commonwealth Avenue West',
            'Clementi Bus Interchange',
            'lineOpacity: 0',
            'lineWidth: 0',
            'lineDasharray',
        ]:
            self.assertIn(snippet, text)
        css = text[text.index('#roadNameLabels'):text.index('.persona-card')]
        for snippet in [
            'background: rgba(243, 243, 241, 0.78)',
            'border-bottom: 4px solid var(--harvard-crimson)',
            'font-family: var(--harvard-serif)',
            'backdrop-filter: blur(8px)',
            'transform-origin: 50% 50%',
        ]:
            self.assertIn(snippet, css)

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

    def test_notifications_panel_uses_harvard_dropdown_design(self):
        text = self.html()
        css = (ROOT / "harvard.css").read_text()
        for snippet in [
            'id="notificationsPanel" class="hud"',
            'class="notification-head"',
            'class="notification-list"',
        ]:
            self.assertIn(snippet, text)
        notifications_css = css[css.index('/* Harvard notification menu: black/crimson dropdown chrome with readable paper rows. */'):]
        for snippet in [
            'body:has(#map) #notificationsPanel',
            'html[data-theme="light"] body:has(#map) #notificationsPanel',
            'html[data-theme="dark"] body:has(#map) #notificationsPanel',
            'background: #000000 !important;',
            'border-top: 5px solid var(--harvard-crimson)',
            'border-radius: 0 !important;',
            'body:has(#map) #notificationsPanel #clearNotificationsBtn',
            'border-bottom: 4px solid var(--harvard-crimson)',
            'body:has(#map) #notificationsPanel .notification-item',
            'border-left: 5px solid var(--harvard-crimson)',
            'background: #ffffff !important;',
            'color: #111111 !important;',
        ]:
            self.assertIn(snippet, notifications_css)
        self.assertNotIn('border-radius: 14px', notifications_css)
        self.assertNotIn('rgba(15, 23, 42', notifications_css)

    def test_theme_recolors_scorecard_text_and_metric_cards(self):
        css = (ROOT / "harvard.css").read_text()
        for snippet in [
            'body:has(#map) .score-card',
            'background: var(--panel-strong-bg)',
            'color: var(--txt)',
            'body:has(#map) .score-card small',
            'body:has(#map) #detailCard .metric span',
            'color: var(--muted)',
            'body:has(#map) #detailCard .score-flip',
            'body:has(#map) #detailCard .score-breakdown',
            'border-top: 4px solid var(--harvard-crimson)',
            'background: color-mix(in srgb, var(--harvard-crimson) 10%',
            'body:has(#map) #detailCard #scoreFlipBackBtn',
        ]:
            self.assertIn(snippet, css)
        scorecard_css = css[css.index('/* JalanLens score-card redesign */'):css.index('/* Mobile/APK Street View')]
        forbidden_scorecard_literals = [
            'body:has(#map) .score-card * {\n  color: #111111',
            'body:has(#map) #detailCard .metric b {\n  color: #111111',
            'body:has(#map) #detailCard .metric span {\n  color: #334155',
            'border-left: 5px solid #38bdf8',
            'border-top: 4px solid #38bdf8',
            'background: #e0f2fe !important;',
            'color: #075985 !important;',
        ]
        for literal in forbidden_scorecard_literals:
            self.assertNotIn(literal, scorecard_css)

    def test_score_number_has_no_inner_red_rule(self):
        css = (ROOT / "harvard.css").read_text()
        scorecard_css = css[css.index('/* JalanLens score-card redesign */'):css.index('/* Mobile/APK Street View')]
        self.assertIn('body:has(#map) #detailCard .score-flip', scorecard_css)
        self.assertIn('border-left: 5px solid var(--harvard-crimson)', scorecard_css)
        active_score_block = re.search(r'body:has\(#map\) #detailCard #activeScore \{(?P<body>.*?)\n\}', scorecard_css, re.S)
        self.assertIsNotNone(active_score_block)
        self.assertNotIn('border-left', active_score_block.group('body'))
        self.assertNotIn('background:', active_score_block.group('body'))

    def test_project_font_families_use_only_jalanlens_serif_and_sans(self):
        css = (ROOT / "harvard.css").read_text()
        self.assertIn('--harvard-serif', css)
        self.assertIn('--harvard-sans', css)
        self.assertIn('body,\nbody *', css)
        self.assertIn('font-family: var(--harvard-sans)', css)
        self.assertIn('h1, h1 *,', css)
        self.assertIn('.brand, .brand *', css)
        self.assertIn('font-family: var(--harvard-serif)', css)
        visible_pages = [
            ROOT / 'index.html',
            ROOT / 'about' / 'index.html',
            ROOT / 'login' / 'index.html',
            ROOT / 'profile' / 'index.html',
            ROOT / 'documentation' / 'index.html',
            ROOT / 'crowd-photos' / 'index.html',
            ROOT / 'street-intelligence' / 'index.html',
        ]
        joined = '\n'.join(p.read_text() for p in visible_pages) + '\n' + css
        forbidden = ['Inter,', 'Google Sans', 'Roboto', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI']
        for font in forbidden:
            self.assertNotIn(font, joined)

    def test_dark_display_uses_true_black_for_topbar_and_scorecards(self):
        css = (ROOT / "harvard.css").read_text()
        for snippet in [
            'Dark display setting: Abel wants top menu bars and score cards to be pure black',
            'html[data-theme="dark"] body:has(#map) #topbar',
            'html[data-theme="dark"] body:has(#map) #detailCard',
            'html[data-theme="dark"] body:has(#map) #detailCard .metric',
            'html[data-theme="dark"] body:has(#map) .score-card',
            'background: #000000 !important;',
            'background-color: #000000 !important;',
            'color: #ffffff !important;',
        ]:
            self.assertIn(snippet, css)
        dark_black_css = css[css.index('/* Dark display setting: Abel wants top menu bars and score cards to be pure black'):css.index('body:has(#map) .street-screen-nav')]
        for forbidden in [
            'background: var(--bg) !important;',
            'background: var(--panel-strong-bg) !important;',
            'background: rgba(15, 23, 42',
            'background-color: var(--control-bg)',
        ]:
            self.assertNotIn(forbidden, dark_black_css)

    def test_dashboard_view_and_footpath_dropdowns_are_black(self):
        css = (ROOT / "harvard.css").read_text()
        for snippet in [
            'body:has(#map) #topbar #viewModeSelect',
            'body:has(#map) #topbar #segmentSelect',
            'html[data-theme="light"] body:has(#map) #topbar #viewModeSelect',
            'html[data-theme="dark"] body:has(#map) #topbar #segmentSelect',
            'background-color: #000000 !important;',
            'color: #ffffff !important;',
            'border-left-color: var(--harvard-crimson) !important;',
        ]:
            self.assertIn(snippet, css)

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

    def test_score_card_drag_requires_left_click_hold_on_card(self):
        text = self.html()
        css = (ROOT / "harvard.css").read_text()
        for snippet in [
            'card.addEventListener("pointerdown"',
            'event.button !== 0',
            'event.buttons !== 1',
            'card.addEventListener("pointermove"',
            'card.setPointerCapture?.(event.pointerId)',
        ]:
            self.assertIn(snippet, text)
        self.assertIn('body:has(#map) #detailCard {', css)
        self.assertIn('cursor: grab !important;', css)
        self.assertIn('body:has(#map) #detailCard.dragging', css)
        self.assertIn('cursor: grabbing !important;', css)

    def test_score_card_drag_can_enter_screen_edges(self):
        text = self.html()
        for snippet in [
            'const edgeRecoveryPx = 56;',
            'const minLeft = Math.min(8, edgeRecoveryPx - rect.width);',
            'const maxLeft = Math.max(8, innerWidth - edgeRecoveryPx);',
            'const minTop = Math.min(8, edgeRecoveryPx - rect.height);',
            'const maxTop = Math.max(8, innerHeight - edgeRecoveryPx);',
        ]:
            self.assertIn(snippet, text)
        self.assertNotIn('innerWidth - rect.width - 8', text)
        self.assertNotIn('innerHeight - rect.height - 8', text)

    def test_synthetic_agent_count_removes_explanatory_suffix(self):
        text = self.html()
        self.assertIn('currently here</small>', text)
        self.assertNotIn('synthetic, not real-person tracking', text)

    def test_notification_schema_exists(self):
        sql = SCHEMA.read_text()
        html = self.html()
        self.assertIn('create table if not exists public.app_notifications', sql)
        self.assertIn('clear notification history', html.lower())
        self.assertIn('grant select, insert, update on public.app_notifications', sql)
        self.assertIn('async function supabaseInsertIgnoreDuplicate', html)
        self.assertIn('on_conflict=${encodeURIComponent(conflictColumn)}', html)
        self.assertIn('Prefer: "resolution=ignore-duplicates,return=minimal"', html)
        self.assertIn('await supabaseInsertIgnoreDuplicate("app_notifications"', html)


if __name__ == "__main__":
    unittest.main()
