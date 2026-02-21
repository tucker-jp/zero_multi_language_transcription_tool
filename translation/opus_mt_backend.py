"""OPUS-MT translation backend via HuggingFace transformers."""

from __future__ import annotations

import torch
from transformers import MarianMTModel, MarianTokenizer

from translation.cache import TranslationCache


class OpusMTTranslator:
    """French → English translator using Helsinki-NLP/opus-mt-fr-en."""

    def __init__(
        self,
        model_name: str = "Helsinki-NLP/opus-mt-fr-en",
        cache_size: int = 1000,
    ):
        self._model_name = model_name
        self._model: MarianMTModel | None = None
        self._tokenizer: MarianTokenizer | None = None
        self._cache = TranslationCache(maxsize=cache_size)

    def load_model(self):
        self._tokenizer = MarianTokenizer.from_pretrained(self._model_name)
        self._model = MarianMTModel.from_pretrained(self._model_name)

    def is_loaded(self) -> bool:
        return self._model is not None

    def translate(self, text: str) -> str:
        """Translate French text to English. Uses cache for repeated lookups."""
        text = text.strip()
        if not text:
            return ""

        cached = self._cache.get(text)
        if cached is not None:
            return cached

        if self._model is None or self._tokenizer is None:
            raise RuntimeError("Translation model not loaded. Call load_model() first.")

        inputs = self._tokenizer(text, return_tensors="pt", padding=True)
        with torch.no_grad():
            translated = self._model.generate(**inputs)
        result = self._tokenizer.decode(translated[0], skip_special_tokens=True)

        self._cache.put(text, result)
        return result

    def translate_text(self, text: str, sentence: str = "") -> tuple[str, str]:
        """Translate a word or phrase and optionally its containing sentence.

        Returns (text_translation, sentence_translation).
        """
        text_trans = self.translate(text)
        sentence_trans = self.translate(sentence) if sentence else ""
        return text_trans, sentence_trans
