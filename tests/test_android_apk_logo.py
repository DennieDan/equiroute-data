from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "android-app" / "app" / "src" / "main" / "res"


class AndroidApkLogoTests(unittest.TestCase):
    def test_launcher_icon_uses_project_logo_png_resources(self):
        manifest = (ROOT / "android-app" / "app" / "src" / "main" / "AndroidManifest.xml").read_text()
        self.assertIn('android:icon="@mipmap/ic_launcher"', manifest)
        for density in ["mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"]:
            icon = RES / f"mipmap-{density}" / "ic_launcher.png"
            self.assertTrue(icon.exists(), f"missing {icon}")
            self.assertGreater(icon.stat().st_size, 1000)
        foreground = RES / "drawable" / "ic_launcher_foreground.png"
        self.assertTrue(foreground.exists())
        self.assertGreater(foreground.stat().st_size, 1000)
        legacy_vector = RES / "mipmap-hdpi" / "ic_launcher.xml"
        self.assertFalse(legacy_vector.exists(), "legacy generated vector icon should not override project logo")

    def test_adaptive_icon_wraps_project_logo_foreground(self):
        adaptive = (RES / "mipmap-anydpi-v26" / "ic_launcher.xml").read_text()
        self.assertIn('@drawable/ic_launcher_background', adaptive)
        self.assertIn('@drawable/ic_launcher_foreground', adaptive)
        old_foreground_xml = RES / "drawable" / "ic_launcher_foreground.xml"
        self.assertFalse(old_foreground_xml.exists(), "old abstract vector foreground should be replaced by project logo png")


if __name__ == "__main__":
    unittest.main()
