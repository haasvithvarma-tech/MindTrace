"""
tests/test_m6_5.py — Automated tests for workflow-specific AI configuration and direct API integration.
"""

import unittest
import os
from unittest.mock import patch, MagicMock
import ai_service

class Milestone65WorkflowTests(unittest.TestCase):

    def setUp(self):
        self.saved_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved_env)

    @patch("ai_service.urllib.request.urlopen")
    def test_01_textbook_analysis_selects_gemini_flash(self, mock_urlopen):
        os.environ["GEMINI_API_KEY"] = "mock-gemini-key"
        os.environ["TEXTBOOK_AI_PROVIDER"] = "gemini"
        os.environ["TEXTBOOK_AI_MODEL"] = "gemini-3.8-flash"

        mock_context_manager = MagicMock()
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"candidates": [{"content": {"parts": [{"text": "{\\"textbook_title\\": \\"Math Grade 7\\", \\"page_number\\": 5, \\"concepts\\": [{\\"name\\": \\"Integers\\"}], \\"summary\\": \\"Summary text\\", \\"prerequisites\\": []}"}]}}]}'
        mock_context_manager.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_context_manager

        analysis = ai_service.analyze_textbook_content("Math Grade 7", 5, "Integers.")
        self.assertEqual(analysis["source"], "ai_generated")
        self.assertEqual(analysis["provider"], "gemini")
        self.assertEqual(analysis["model"], "gemini-3.8-flash")

    @patch("ai_service.urllib.request.urlopen")
    def test_02_diagnostic_generation_selects_gemini_flash_lite(self, mock_urlopen):
        os.environ["GEMINI_API_KEY"] = "mock-gemini-key"
        os.environ["DIAGNOSTIC_AI_PROVIDER"] = "gemini"
        os.environ["DIAGNOSTIC_AI_MODEL"] = "gemini-3.5-flash-lite"

        mock_context_manager = MagicMock()
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"candidates": [{"content": {"parts": [{"text": "{\\"questions\\": [{\\"question_text\\": \\"What is 2+2?\\", \\"option_a\\": \\"4\\", \\"option_b\\": \\"3\\", \\"option_c\\": \\"5\\", \\"option_d\\": \\"6\\", \\"correct_option\\": \\"a\\"}]}"}]}}]}'
        mock_context_manager.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_context_manager

        questions = ai_service.generate_diagnostic_questions("Addition", "Basic math")
        self.assertTrue(len(questions) > 0)
        self.assertEqual(questions[0]["source"], "ai_generated")
        self.assertEqual(questions[0]["provider"], "gemini")
        self.assertEqual(questions[0]["model"], "gemini-3.5-flash-lite")

    @patch("ai_service.urllib.request.urlopen")
    def test_03_simultaneous_different_providers_and_models(self, mock_urlopen):
        os.environ["GEMINI_API_KEY"] = "mock-gemini-key"
        os.environ["GROQ_API_KEY"] = "mock-groq-key"

        os.environ["TEXTBOOK_AI_PROVIDER"] = "gemini"
        os.environ["TEXTBOOK_AI_MODEL"] = "gemini-3.8-flash"

        os.environ["DIAGNOSTIC_AI_PROVIDER"] = "groq"
        os.environ["DIAGNOSTIC_AI_MODEL"] = "qwen/qwen3.8-27b"

        def side_effect(req, timeout=12):
            url = req.get_full_url() if hasattr(req, "get_full_url") else str(req)
            ctx = MagicMock()
            res = MagicMock()
            if "generativelanguage.googleapis.com" in url:
                res.read.return_value = b'{"candidates": [{"content": {"parts": [{"text": "{\\"textbook_title\\": \\"Math\\", \\"page_number\\": 1, \\"concepts\\": [{\\"name\\": \\"Numbers\\"}], \\"summary\\": \\"Summary\\", \\"prerequisites\\": []}"}]}}]}'
            else:
                res.read.return_value = b'{"choices": [{"message": {"content": "{\\"questions\\": [{\\"question_text\\": \\"Q1?\\", \\"option_a\\": \\"A\\", \\"option_b\\": \\"B\\", \\"option_c\\": \\"C\\", \\"option_d\\": \\"D\\", \\"correct_option\\": \\"a\\"}]}"}}]}}'
            ctx.__enter__.return_value = res
            return ctx

        mock_urlopen.side_effect = side_effect

        analysis = ai_service.analyze_textbook_content("Math", 1, "Numbers.")
        questions = ai_service.generate_diagnostic_questions("Numbers", "Count")

        self.assertEqual(analysis["provider"], "gemini")
        self.assertEqual(analysis["model"], "gemini-3.8-flash")
        self.assertEqual(questions[0]["provider"], "groq")
        self.assertEqual(questions[0]["model"], "qwen/qwen3.8-27b")

    def test_04_legacy_global_configuration_fallback(self):
        os.environ.pop("TEXTBOOK_AI_PROVIDER", None)
        os.environ.pop("TEXTBOOK_AI_MODEL", None)
        os.environ["AI_PROVIDER"] = "groq"
        os.environ["GROQ_MODEL"] = "qwen/qwen3.8-27b"

        provider, model = ai_service._resolve_workflow_config("textbook", "gemini", "gemini-3.8-flash")
        self.assertEqual(provider, "groq")
        self.assertEqual(model, "qwen/qwen3.8-27b")

    def test_05_incompatible_provider_model_raises_error(self):
        os.environ["TEXTBOOK_AI_PROVIDER"] = "groq"
        os.environ["TEXTBOOK_AI_MODEL"] = "gemini-3.8-flash" # Mismatched: Gemini model requested on Groq provider

        with self.assertRaises(ValueError):
            ai_service._resolve_workflow_config("textbook", "groq", "qwen/qwen3.8-27b")


if __name__ == "__main__":
    unittest.main()
