from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "street-intelligence" / "index.html"
JS = ROOT / "feedback-form.js"
SCHEMA = ROOT / "supabase" / "schema.sql"


class MultilingualFeedbackTests(unittest.TestCase):
    def html(self):
        return HTML.read_text()

    def js(self):
        return JS.read_text()

    def sql(self):
        return SCHEMA.read_text()

    def test_feedback_ui_exposes_multilingual_translation_and_speech_controls(self):
        html = self.html()
        for snippet in [
            'id="feedbackLanguageHint"',
            'id="feedbackSpeechBtn"',
            'id="feedbackTranslationBox"',
            'id="feedbackTranslationText"',
            'Traditional Chinese, Simplified Chinese, Malay, Tamil, Bengali, and Gujarati',
            'class="mic-pulse"',
        ]:
            self.assertIn(snippet, html)
        self.assertRegex(html, r"#feedbackTranslationBox\s*\{[^}]*background:\s*#fef3c7")
        self.assertRegex(html, r"#feedbackTranslationBox\s*\{[^}]*color:\s*#1f2937")

    def test_feedback_js_uses_agnes_for_translation_and_speech_to_text_payload(self):
        js = self.js()
        for snippet in [
            'AGNES_BASE_URL',
            'agnes-2.5-flash',
            'translateFeedbackWithAgnes',
            'transcribeAudioWithAgnes',
            'feedbackSpeechBtn',
            'english_translation',
            'original_language',
            'translation_provider: "agnes"',
            'translation_model: AGNES_TRANSLATION_MODEL',
            'speech_transcript_original',
        ]:
            self.assertIn(snippet, js)

    def test_feedback_schema_stores_original_language_translation_and_transcript(self):
        sql = self.sql()
        for snippet in [
            'add column if not exists original_language text',
            'add column if not exists english_translation text',
            'add column if not exists translation_provider text',
            'add column if not exists translation_model text',
            'add column if not exists speech_transcript_original text',
            'add column if not exists input_modality text',
            'feedback_threads_translation_idx',
        ]:
            self.assertIn(snippet, sql)


if __name__ == "__main__":
    unittest.main()
