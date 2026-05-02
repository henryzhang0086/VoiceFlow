"""Text post-processing pipeline: rule-based cleanup + optional LLM refinement.

The pipeline runs after ASR transcription and hotword correction:
  ASR text → hotword corrections → postprocess (this module) → paste

Rule-based processing is always available (zero latency cost).
LLM refinement is optional and adds ~1-3s latency on CPU.
"""

from __future__ import annotations

import re
from typing import Protocol


class TextPostProcessor(Protocol):
    def process(self, text: str) -> str: ...


class RulePostProcessor:
    """Zero-latency rule-based post-processing."""

    _FILLERS = re.compile(r"(?<![说道到])(?:嗯|啊|呃){1,3}(?=[，。、；]|$)")
    _REPEATED_PUNCT = re.compile(r"([，。！？、；：])\1+")
    _LEADING_FILLER = re.compile(r"^(?:嗯|啊|呃|那个|就是)[，、]?\s*")

    def process(self, text: str) -> str:
        text = self._LEADING_FILLER.sub("", text)
        text = self._FILLERS.sub("", text)
        text = self._REPEATED_PUNCT.sub(r"\1", text)
        text = re.sub(r"，$", "", text)
        return text.strip()


class LLMPostProcessor:
    """LLM-based post-processing via llama-cpp-python.

    Removes filler words, fixes grammar, adds punctuation.
    Preserves professional terms and numbers strictly.
    """

    PROMPT_TEMPLATE = """你是中文语音转写后处理助手。任务：
1. 去除口头禅（嗯、啊、那个、就是说、然后呢）
2. 修正明显语法错误，但不改变原意
3. 添加或修正标点符号
4. 严格保留专业术语和数字（如 Sharpe、因子、3.5、Factor54、LightGBM）
5. 不要展开缩写，不要补充用户没说的内容

原文：{text}
修正后："""

    def __init__(self, model_path: str, n_ctx: int = 512, n_threads: int = 4):
        self._model_path = model_path
        self._n_ctx = n_ctx
        self._n_threads = n_threads
        self._llm = None

    def load(self) -> None:
        from llama_cpp import Llama
        self._llm = Llama(
            model_path=self._model_path,
            n_ctx=self._n_ctx,
            n_threads=self._n_threads,
            verbose=False,
        )

    def process(self, text: str) -> str:
        if not self._llm or not text.strip():
            return text

        prompt = self.PROMPT_TEMPLATE.format(text=text)
        output = self._llm(
            prompt,
            max_tokens=len(text) * 3,
            temperature=0.1,
            stop=["\n\n", "原文：", "修正后："],
        )

        result = output["choices"][0]["text"].strip()
        if not result or len(result) < len(text) * 0.3:
            return text
        return result


class PostProcessPipeline:
    """Chains rule-based and optional LLM processing."""

    def __init__(self, enable_llm: bool = False, llm_model_path: str = ""):
        self._rule = RulePostProcessor()
        self._llm: LLMPostProcessor | None = None

        if enable_llm and llm_model_path:
            self._llm = LLMPostProcessor(llm_model_path)
            self._llm.load()

    def process(self, text: str) -> str:
        text = self._rule.process(text)
        if self._llm:
            text = self._llm.process(text)
        return text
