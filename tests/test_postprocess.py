"""Tests for the postprocess module."""

import pytest

from voice_input_method.postprocess import (
    LLMPostProcessor,
    PostProcessPipeline,
    RulePostProcessor,
)


class TestRulePostProcessor:
    def setup_method(self):
        self.pp = RulePostProcessor()

    def test_removes_leading_fillers(self):
        assert self.pp.process("嗯，今天我们来讨论") == "今天我们来讨论"
        assert self.pp.process("那个，这个因子") == "这个因子"

    def test_removes_trailing_fillers(self):
        assert self.pp.process("结果很好嗯") == "结果很好"
        assert self.pp.process("这个呃") == "这个"

    def test_removes_mid_sentence_fillers(self):
        result = self.pp.process("这个因子嗯，表现不错")
        assert "嗯" not in result

    def test_deduplicates_punctuation(self):
        assert self.pp.process("好的。。") == "好的。"
        assert self.pp.process("什么？？") == "什么？"

    def test_removes_trailing_comma(self):
        assert self.pp.process("回测显示，") == "回测显示"

    def test_preserves_normal_text(self):
        text = "夏普比率达到1.5，年化收益超过20%"
        assert self.pp.process(text) == text

    def test_preserves_professional_terms(self):
        text = "Alpha因子的IC均值为0.05"
        assert self.pp.process(text) == text

    def test_empty_input(self):
        assert self.pp.process("") == ""

    def test_only_fillers(self):
        assert self.pp.process("嗯啊") == ""


class TestPostProcessPipeline:
    def test_rule_only_pipeline(self):
        pipeline = PostProcessPipeline(enable_llm=False)
        result = pipeline.process("嗯，今天讨论一下")
        assert result == "今天讨论一下"

    def test_pipeline_without_llm_model(self):
        pipeline = PostProcessPipeline(enable_llm=True, llm_model_path="")
        result = pipeline.process("测试文本")
        assert result == "测试文本"


class TestLLMPostProcessor:
    def test_prompt_template_format(self):
        pp = LLMPostProcessor(model_path="/fake/path")
        prompt = pp.PROMPT_TEMPLATE.format(text="测试")
        assert "测试" in prompt
        assert "严格保留专业术语" in prompt
