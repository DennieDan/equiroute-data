from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "feedback-form.js"


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
        ]:
            self.assertIn(snippet, self.js)


if __name__ == "__main__":
    unittest.main()
