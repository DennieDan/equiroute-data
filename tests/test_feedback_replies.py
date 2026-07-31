from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "street-intelligence" / "index.html"
JS = ROOT / "feedback-form.js"
SCHEMA = ROOT / "supabase" / "schema.sql"
RLS = ROOT / "supabase" / "rls.sql"


class FeedbackRepliesTests(unittest.TestCase):
    def test_feedback_replies_schema_and_rls(self):
        schema = SCHEMA.read_text()
        rls = RLS.read_text()
        for snippet in [
            "create table if not exists public.feedback_replies",
            "parent_source text not null check (parent_source in ('public','agent_simulation'))",
            "parent_thread_id uuid null references public.feedback_threads",
            "parent_agent_thread_id uuid null references public.agent_feedback_threads",
            "author_role text not null check (author_role in ('public','authority','agent','system'))",
            "feedback_replies_public_parent_idx",
            "feedback_replies_agent_parent_idx",
        ]:
            self.assertIn(snippet, schema)
        for snippet in [
            "alter table public.feedback_replies enable row level security",
            "public read feedback replies",
            "public insert feedback replies",
        ]:
            self.assertIn(snippet, rls)

    def test_feedback_ui_renders_role_replies_and_filters(self):
        html = HTML.read_text()
        js = JS.read_text()
        for snippet in [
            'option value="authority">Authority',
            'feedback-reply ${escapeHtml(role)}',
            'Reply as authority',
            'feedback-reply-open',
            'feedback_replies',
            'author_role',
            'parent_agent_thread_id',
            'feedback-refresh',
            'function bindHistoryControls',
            'loadHistory({ manual: true })',
        ]:
            self.assertIn(snippet, js + html)


if __name__ == "__main__":
    unittest.main()
