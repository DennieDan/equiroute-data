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
            'class="feedback-composer-line"',
            'id="feedbackSpeechBtn"',
            'aria-label="Speech to text"',
            'id="feedbackTranslationBox"',
            'id="feedbackTranslationText"',
            'class="mic-pulse"',
            'Add feedback or response…',
        ]:
            self.assertIn(snippet, html)
        self.assertRegex(html, r"#feedbackTranslationBox\s*\{[^}]*background:\s*#fef3c7")
        self.assertRegex(html, r"#feedbackTranslationBox\s*\{[^}]*color:\s*#1f2937")

    def test_feedback_js_uses_translation_fallback_and_speech_to_text_payload(self):
        js = self.js()
        for snippet in [
            'AGNES_BASE_URL',
            'agnes-2.5-flash',
            'translateFeedbackWithAgnes',
            'translateFeedbackWithPublicFallback',
            'localTranslationFallback',
            'transcribeAudioWithAgnes',
            'JALANLENS_USE_AGNES_SPEECH',
            'feedbackSpeechBtn',
            'english_translation',
            'original_language',
            'translation_provider: translation.provider || null',
            'translation_model: translation.model || null',
            'speech_transcript_original',
            'dedupeTranscriptText',
            'normalizeSpeechLanguage',
            'Detect English, Mandarin Chinese, Malay, Tamil, or Gujarati automatically',
            'speechRecognition = startBrowserSpeechRecognition(target);',
        ]:
            self.assertIn(snippet, js)
        self.assertNotIn('speechRecognition = startBrowserSpeechRecognition();', js)

    def test_reply_composer_has_speech_and_translation_preview(self):
        js = self.js()
        css = (ROOT / "harvard.css").read_text()
        for snippet in [
            'feedback-reply-speech',
            'Speech to text for reply',
            'feedback-reply-translation',
            'speechTargetForReply',
            'refreshReplyTranslationNow',
            'textarea?.dataset.inputModality || "typed"',
            'textarea?.dataset.detectedLanguage || ""',
        ]:
            self.assertIn(snippet, js)
        for snippet in [
            'feedback-reply-composer-line',
            'feedback-reply-speech svg',
            'feedback-reply-translation.visible',
        ]:
            self.assertIn(snippet, css)

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
