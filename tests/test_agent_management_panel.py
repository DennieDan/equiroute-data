from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "street-intelligence" / "index.html"
THEME = ROOT / "harvard.css"


class AgentManagementPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.platform = PLATFORM.read_text()
        cls.theme = THEME.read_text()

    def test_settings_launches_persistent_agent_management_panel(self):
        for token in [
            'id="agentManagementSettingsSection"',
            'id="openAgentManagementBtn"',
            'id="agentManagementPanel"',
            'aria-label="Agent simulation management"',
            'function openAgentManagementPanel',
            'openAgentManagementPanel("overview")',
        ]:
            self.assertIn(token, self.platform)
        self.assertIn("position: fixed", self.platform)
        self.assertIn("agent-panel-resize", self.platform)
        self.assertNotIn('role="dialog"', self.platform)

    def test_panel_has_monitoring_sections_and_map_coordination(self):
        for token in [
            'data-agent-tab="overview"',
            'data-agent-tab="personas"',
            'data-agent-tab="agents"',
            'data-agent-tab="events"',
            'data-agent-tab="run"',
            'id="agentPersonaFilter"',
            'id="agentEventSeverityFilter"',
            "function locateAgent",
            "function locateAgentEvent",
            "function applyAgentMapFilter",
            'id="clearAgentMapFilterBtn"',
        ]:
            self.assertIn(token, self.platform)

    def test_configuration_is_explicitly_draft_only(self):
        for token in [
            "jalanlens_agent_simulation_draft",
            "Next-run configuration",
            "Save run draft",
            "Save persona draft",
            "do not alter the running snapshot yet",
            "will not pause, restart or change the live snapshot",
        ]:
            self.assertIn(token, self.platform)

    def test_panel_is_authority_only_collapsible_resizable_and_responsive(self):
        for token in [
            'class="hud authority-only"',
            'id="agentPanelCollapseBtn"',
            'id="agentPanelCloseBtn"',
            "toggleAgentManagementCollapse",
            "AGENT_PANEL_WIDTH_STORAGE_KEY",
            "agentManagementPanel.style.width",
            "@media (max-width: 800px)",
            "closeAgentManagementPanel();",
        ]:
            self.assertIn(token, self.platform)

    def test_dark_result_rows_force_all_text_to_pure_white(self):
        for selector in [
            "#agentManagementPanel .agent-distribution-row *",
            "#agentManagementPanel .agent-persona-row *",
            "#agentManagementPanel .agent-row *",
            "#agentManagementPanel .agent-event-row *",
        ]:
            self.assertIn(selector, self.theme)
        self.assertIn("color: #ffffff !important;", self.theme)
        self.assertIn('id="agentManagementTextOverride"', self.platform)
        self.assertIn(
            'href="../harvard.css?v=20260731-agent-white-1"', self.platform
        )
        override = self.platform[self.platform.index('id="agentManagementTextOverride"') :]
        self.assertIn("#agentManagementPanel .agent-row *", override)
        self.assertIn("color: #ffffff !important;", override)


if __name__ == "__main__":
    unittest.main()
