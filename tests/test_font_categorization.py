# -*- coding: utf-8 -*-
"""文字图层字体分类与中文名映射测试（纯逻辑，标记为 unit）。"""

import os

import pytest

from app.models.text_layer import TextLayer


@pytest.mark.unit
class TestFontCategorization:
    """字体分类与中文名映射的纯逻辑测试。

    依赖本机已安装字体；不存在的字体名断言会自动跳过，
    只对稳定存在于 Windows 默认字体集中的字体做断言。
    """

    def setup_method(self):
        self.layer = TextLayer()
        self.cn_names = self.layer.get_font_cn_names()
        self.categories = self.layer.get_categorized_fonts()
        self.all_fonts = self.layer.get_system_fonts()

    def test_system_fonts_non_empty(self):
        assert isinstance(self.all_fonts, list)
        assert len(self.all_fonts) > 0
        assert all(isinstance(f, str) and f.strip() for f in self.all_fonts)
        # 去重
        assert len(self.all_fonts) == len(set(self.all_fonts))

    @pytest.mark.skipif(os.name != "nt", reason="Windows 默认字体检查")
    def test_windows_cn_names(self):
        expect = {
            "Microsoft YaHei": "微软雅黑",
            "SimSun": "宋体",
            "SimHei": "黑体",
            "KaiTi": "楷体",
            "FangSong": "仿宋",
        }
        for en, zh in expect.items():
            if en in self.all_fonts:
                assert self.cn_names.get(en) == zh, f"{en} 中文名应为 {zh}"

    @pytest.mark.skipif(os.name != "nt", reason="Windows 默认字体检查")
    def test_windows_categories(self):
        if "Microsoft YaHei" in self.all_fonts:
            assert "Microsoft YaHei" in self.categories["chinese"]
        if "Arial" in self.all_fonts:
            assert "Arial" in self.categories["english"]

    def test_chinese_and_english_cover_all(self):
        combined = set(self.categories["chinese"]) | set(self.categories["english"])
        assert set(self.all_fonts) == combined

    def test_chinese_english_disjoint(self):
        overlap = set(self.categories["chinese"]) & set(self.categories["english"])
        assert not overlap

    def test_cn_names_keys_are_font_names(self):
        for key in self.cn_names:
            assert key in self.all_fonts
            assert self.cn_names[key]

    def test_cn_names_value_contains_cjk(self):
        # 中文名必须包含 CJK 字符，避免无意义映射
        import re

        cjk_re = re.compile(r"[\u4e00-\u9fff]")
        for key, zh in self.cn_names.items():
            if zh != key:
                assert cjk_re.search(zh), f"{key} -> {zh} 缺少中文字符"
