"""Tests for quant-specific hotword corrections."""

from pathlib import Path

import pytest

from voice_input_method.hotwords import HotwordManager
from voice_input_method.text_processing import apply_corrections


@pytest.fixture
def hm():
    return HotwordManager(Path(__file__).parent.parent / "hotwords.txt")


class TestQuantCorrections:
    def test_sharpe_correction(self, hm):
        text = "下普比率达到了1.5"
        result = apply_corrections(text, hm.corrections)
        assert "夏普比率" in result

    def test_factor_correction(self, hm):
        text = "多音子选股策略"
        result = apply_corrections(text, hm.corrections)
        assert "多因子" in result

    def test_alpha_correction(self, hm):
        text = "阿法因子的IC"
        result = apply_corrections(text, hm.corrections)
        assert "Alpha因子" in result

    def test_calmar_correction(self, hm):
        text = "kmer比率为2.3"
        result = apply_corrections(text, hm.corrections)
        assert "Calmar" in result

    def test_backtest_correction(self, hm):
        text = "回侧结果不错"
        result = apply_corrections(text, hm.corrections)
        assert "回测" in result

    def test_preserves_correct_terms(self, hm):
        text = "夏普比率和Calmar比率都很好"
        result = apply_corrections(text, hm.corrections)
        assert result == text

    def test_multiple_corrections_in_one_sentence(self, hm):
        text = "下普比率和kmer比率"
        result = apply_corrections(text, hm.corrections)
        assert "夏普" in result
        assert "Calmar" in result

    def test_hotwords_count(self, hm):
        assert len(hm._hotwords_list) >= 50

    def test_corrections_count(self, hm):
        assert len(hm.corrections) >= 20
