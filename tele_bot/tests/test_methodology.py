"""Tests for methodology module."""
from __future__ import annotations

import pytest

from src.bot.methodology import METHODOLOGIES, METHODOLOGY_BUTTONS

# Telegram message limit
MAX_MESSAGE_LENGTH = 4096


class TestMethodologies:
    def test_all_buttons_have_entries(self):
        for label, cb_data in METHODOLOGY_BUTTONS:
            key = cb_data.replace("method_", "", 1)
            assert key in METHODOLOGIES, f"Button '{label}' maps to missing key '{key}'"

    def test_all_entries_have_required_keys(self):
        required = {"title", "description", "metrics", "signals"}
        for key, entry in METHODOLOGIES.items():
            assert required.issubset(entry.keys()), f"Missing keys in '{key}': {required - entry.keys()}"

    def test_formatted_text_under_telegram_limit(self):
        for key, entry in METHODOLOGIES.items():
            text = (
                f"<b>{entry['title']}</b>\n\n"
                f"{entry['description']}\n\n"
                f"<b>── Metrics ──</b>\n{entry['metrics']}\n\n"
                f"<b>── Signals ──</b>\n{entry['signals']}"
            )
            assert len(text) < MAX_MESSAGE_LENGTH, (
                f"Methodology '{key}' text length {len(text)} exceeds {MAX_MESSAGE_LENGTH}"
            )

    def test_no_duplicate_callback_data(self):
        cb_data_set = [cb for _, cb in METHODOLOGY_BUTTONS]
        assert len(cb_data_set) == len(set(cb_data_set)), "Duplicate callback data"

    def test_button_count_matches_entries(self):
        assert len(METHODOLOGY_BUTTONS) == len(METHODOLOGIES)

    def test_entries_not_empty(self):
        for key, entry in METHODOLOGIES.items():
            assert entry["title"].strip(), f"Empty title in '{key}'"
            assert entry["description"].strip(), f"Empty description in '{key}'"
            assert entry["metrics"].strip(), f"Empty metrics in '{key}'"
            assert entry["signals"].strip(), f"Empty signals in '{key}'"

    def test_expected_keys_present(self):
        expected = {"technicals", "signals", "cars", "timezone", "pca_etf", "pca_fx"}
        assert expected == set(METHODOLOGIES.keys())
