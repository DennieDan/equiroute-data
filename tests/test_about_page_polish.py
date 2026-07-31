from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ABOUT = ROOT / "about" / "index.html"


class AboutPagePolishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = ABOUT.read_text()

    def test_hero_intro_text_flies_in_fluidly(self):
        for snippet in [
            "@keyframes aboutFlyIn",
            "animation: aboutFlyIn 0.9s cubic-bezier(.16, 1, .3, 1) forwards",
            ".hero .eyebrow",
            ".hero h1",
            ".hero > p",
            "prefers-reduced-motion: reduce",
        ]:
            self.assertIn(snippet, self.html)

    def test_abel_photo_uses_real_attached_image(self):
        self.assertIn('src="../assets/team/abel.jpg"', self.html)
        self.assertIn('class="abel-photo"', self.html)
        self.assertIn('Abel standing on a wood-panelled staircase', self.html)
        self.assertNotIn('Portrait placeholder for Abel', self.html)
        self.assertGreater((ROOT / "assets" / "team" / "abel.jpg").stat().st_size, 10000)


if __name__ == "__main__":
    unittest.main()
