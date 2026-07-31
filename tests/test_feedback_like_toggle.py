from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "feedback-form.js"
RLS = ROOT / "supabase" / "rls.sql"
SCHEMA = ROOT / "supabase" / "schema.sql"


class FeedbackLikeToggleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text()

    def test_heart_click_toggles_like_and_unlike_locally(self):
        for snippet in [
            "const nextLiked = !wasLiked",
            "liked.delete(threadId)",
            "button.classList.toggle(\"liked\", nextLiked)",
            "button.textContent = `${nextLiked ? \"♥\" : \"♡\"} ${next}`",
            "Math.max(0, current + (nextLiked ? 1 : -1))",
        ]:
            self.assertIn(snippet, self.js)

    def test_unlike_removes_existing_vote_from_supabase_when_possible(self):
        for snippet in [
            'method: "DELETE"',
            'feedback_votes?thread_id=eq.${encodeURIComponent(threadId)}',
            'user_id=eq.${encodeURIComponent(voterId())}',
            'button.classList.contains("liked")',
            'fetchUserVoteThreadIds(publicRowsRaw)',
            'Prefer: "resolution=ignore-duplicates,return=minimal"',
        ]:
            self.assertIn(snippet, self.js)

    def test_rls_allows_public_demo_vote_delete(self):
        rls = RLS.read_text()
        schema = SCHEMA.read_text()
        self.assertIn('grant select, insert, delete on public.feedback_votes to anon, authenticated', schema)
        self.assertIn('grant select, insert, delete on public.feedback_votes to anon, authenticated', rls)
        self.assertIn('create policy "public delete own feedback votes"', rls)
        self.assertIn('for delete using (true)', rls)


if __name__ == "__main__":
    unittest.main()
