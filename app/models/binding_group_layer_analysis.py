#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BindingGroup 子 mixin 2: 图层接入/移除/信号 + 文字图层分析 + 关键词提取

从原 binding_group.py 拆分。涵盖：
- 图层 add/remove + signal 接入
- 文字图层分析 (_analyze_text_layer_content)
- 图像图层分析 (_analyze_layer_files)
- 关键词提取 (_extract_keywords_from_text)
- 文件名核心名 (_extract_core_name / _is_meaningful_filename_category / _extract_categories_for_filename)
- 状态一致性 (_capture_layer_state / _is_state_consistent)
- 工具: _is_text_layer / _build_text_virtual_path / _is_stop_word / _calculate_similarity / _extract_product_categories_from_text
"""

import os
import re
import time
import logging
from typing import Set, List

from app.utils.print_utils import safe_print as _safe_print
from app.utils.text_layer_virtual_path import (
    build_text_layer_virtual_path,
)

logger = logging.getLogger(__name__)

# 统一使用编码安全输出，避免GBK控制台因emoji日志中断流程
print = _safe_print

# 顶层环境开关（与原文件保持一致）
_BINDING_VERBOSE = os.environ.get("BTPW_BINDING_VERBOSE", "0") == "1"


class BindingGroupLayerAnalysis:
    """图层接入 + 文字/图像图层分析 + 关键词提取（拆分自 BindingGroup）。"""

    def add_layer(self, layer, layer_index: int):
        """添加图层到绑定组"""
        if layer not in self.layers:
            self.layers.append(layer)
            self._analyze_layer_files(layer, layer_index)
            try:
                # 仅文字图层需要监听文案变化；避免普通图层误触发文字分析
                if self._is_text_layer(layer) and hasattr(layer, 'text_changed') and hasattr(layer.text_changed, 'connect'):
                    # 使用lambda包装，确保能传递图层引用
                    text_slot = lambda: self._on_text_layer_changed(layer)
                    layer.text_changed.connect(text_slot)
                    # 记录连接，便于定向断开
                    lid = id(layer)
                    self._signal_connections.setdefault(lid, {})["text_changed"] = text_slot
                    print(f"[绑定组] 成功连接文字图层 '{layer.name}' 的 text_changed 信号")
                if self._is_text_layer(layer) and hasattr(layer, 'changed') and hasattr(layer.changed, 'connect'):
                    changed_slot = lambda: self._on_text_layer_changed(layer)
                    layer.changed.connect(changed_slot)
                    lid = id(layer)
                    self._signal_connections.setdefault(lid, {})["changed"] = changed_slot
                    print(f"[绑定组] 成功连接文字图层 '{layer.name}' 的 changed 信号")
            except Exception as e:
                print(f"[绑定组] 连接文字图层信号失败: {e}")

    def remove_layer(self, layer):
        """从绑定组移除图层"""
        if layer in self.layers:
            self.layers.remove(layer)
            try:
                # 🔧 修复：断开连接时需要处理lambda包装的情况
                if hasattr(layer, 'text_changed') and hasattr(layer.text_changed, 'disconnect'):
                    lid = id(layer)
                    slot = self._signal_connections.get(lid, {}).get("text_changed")
                    if slot:
                        try:
                            layer.text_changed.disconnect(slot)
                        except Exception:
                            # 回退：若定向断开失败，则断开全部，避免泄漏
                            layer.text_changed.disconnect()
                    print(f"[绑定组] 成功断开文字图层 '{layer.name}' 的 text_changed 信号")
                if hasattr(layer, 'changed') and hasattr(layer.changed, 'disconnect'):
                    lid = id(layer)
                    slot = self._signal_connections.get(lid, {}).get("changed")
                    if slot:
                        try:
                            layer.changed.disconnect(slot)
                        except Exception:
                            layer.changed.disconnect()
                    print(f"[绑定组] 成功断开文字图层 '{layer.name}' 的 changed 信号")
                # 清理信号记录
                self._signal_connections.pop(id(layer), None)
            except Exception as e:
                print(f"[绑定组] 断开文字图层信号失败: {e}")
            self._rebuild_file_categories()

    def _on_text_layer_changed(self, sender=None):
        """文字图层内容变化时的处理函数 - 修复版本，直接接收发送者"""
        print(f"[绑定组] 文字图层内容发生变化，开始重建分类...")

        # 🔧 根本修复：现在sender直接通过参数传递，不再依赖inspect
        if sender:
            if not self._is_text_layer(sender):
                # 忽略非文字图层，避免误进入文字解析逻辑
                return
            print(f"[绑定组] 检测到变化的文字图层: '{sender.name}', 当前文字: '{getattr(sender, 'current_text', '')}'")
            # 🔧 新增：重新分析这个特定的文字图层
            for i, layer in enumerate(self.layers):
                if layer is sender:
                    print(f"[绑定组] 重新分析变化的文字图层: '{sender.name}' (索引: {i})")
                    self._analyze_text_layer_content(layer, i)
                    break

        # 🔧 改进：只重建受影响的分类，而不是全部重建
        # 先保存当前状态
        old_categories = set(self.file_categories.keys())

        # 如果找到了发送者，我们已经单独分析了它，现在更新整体分类
        if sender:
            print(f"[绑定组] 基于变化的文字图层更新分类...")
        else:
            # 如果没找到发送者，回退到完全重建
            print(f"[绑定组] 未检测到具体变化的文字图层，执行完全重建...")
            self._rebuild_file_categories()

        new_categories = set(self.file_categories.keys())
        print(f"[绑定组] 分类更新完成")
        print(f"[绑定组] 原分类数量: {len(old_categories)}, 新分类数量: {len(new_categories)}")

        # 检测新增和移除的分类
        added_categories = new_categories - old_categories
        removed_categories = old_categories - new_categories

        if added_categories:
            print(f"[绑定组] 检测到新增分类: {list(added_categories)}")
        if removed_categories:
            print(f"[绑定组] 检测到移除分类: {list(removed_categories)}")

        # 如果有变化，通知绑定管理器
        if added_categories or removed_categories:
            print(f"[绑定组] 分类发生变化，将通知相关组件更新...")

    def _is_text_layer(self, layer) -> bool:
        """检查图层是否为文字图层"""
        return hasattr(layer, 'get_text_lines') and callable(getattr(layer, 'get_text_lines', None))

    def _build_text_virtual_path(self, layer_name: str, text_value) -> str:
        """统一构建文字图层虚拟路径，确保文本内容始终使用URL编码。"""
        return build_text_layer_virtual_path(layer_name, text_value)

    def _is_stop_word(self, word: str) -> bool:
        """判断是否为停用词（通用修饰词，不应作为分类依据）"""
        stop_words = {
            '热卖', '爆款', '新品', '推荐', '限时', '优惠', '特价', '打折',
            '大牌', '好物', '精选', '超值', '划算', '实惠', '便宜', '低价',
            '疯抢', '疯降', '直降', '立减', '满减', '买赠', '秒杀', '抢购',
            '正品', '品质', '高端', '时尚', '潮流', '经典', '必备', '实用',
            '家用', '日常', '生活', '必备品', '必需品', '单品', '同款'
        }
        return word.strip() in stop_words

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """🔧 新增：计算两个文本的相似度"""
        """用于模糊匹配文字内容和文件名"""
        try:
            # 简单的相似度计算：共同字符比例
            set1 = set(text1.lower())
            set2 = set(text2.lower())

            if not set1 or not set2:
                return 0.0

            intersection = len(set1.intersection(set2))
            union = len(set1.union(set2))

            jaccard_similarity = intersection / union if union > 0 else 0.0

            # 额外的长度相似度惩罚
            length_ratio = min(len(text1), len(text2)) / max(len(text1), len(text2)) if max(len(text1), len(text2)) > 0 else 0.0

            return jaccard_similarity * length_ratio

        except Exception:
            return 0.0

    def _extract_product_categories_from_text(self, text: str) -> Set[str]:
        from app.utils.product_category_extractor import extract_product_categories_from_text
        return extract_product_categories_from_text(text)

    def _is_meaningful_filename_category(self, token: str) -> bool:
        """判断文件名提取的分类是否有语义，避免噪声分类导致随机匹配。"""
        if not token:
            return False

        value = str(token).strip()
        if not value:
            return False

        value_lower = value.lower()

        # 纯数字或过短 token 没有分类意义
        if value_lower.isdigit() or len(value_lower) < 2:
            return False

        # 常见噪声前缀/后缀，不应作为绑定分类
        generic_noise = {
            'img', 'image', 'photo', 'pic', 'picture', 'export', 'output', 'out',
            'test', 'tmp', 'temp', 'new', 'old', 'final', 'copy', 'result',
            'item', 'product', 'shop', 'scene', 'bg', 'banner'
        }
        if value_lower in generic_noise:
            return False

        # 与文字分类共用停用词，避免营销词把分类池污染成“全匹配”
        if self._is_stop_word(value):
            return False

        return True

    def _extract_categories_for_filename(self, filename_without_ext: str) -> Set[str]:
        """从文件名提取分类集合（用于目录索引缓存）。"""
        categories_to_add = set()
        core_name = self._extract_core_name(filename_without_ext)
        if core_name and self._is_meaningful_filename_category(core_name):
            categories_to_add.add(core_name)

        clean_filename = re.sub(r'\d+', '', filename_without_ext)
        clean_filename = re.sub(r'[_\-\s]+$', '', clean_filename)

        chinese_keywords = re.findall(r'[\u4e00-\u9fa5]{2,}', clean_filename)
        for kw in chinese_keywords:
            if self._is_meaningful_filename_category(kw):
                categories_to_add.add(kw)

        english_keywords = re.findall(r'[a-zA-Z]{2,}', clean_filename)
        for kw in english_keywords:
            normalized_kw = kw.lower().strip()
            if self._is_meaningful_filename_category(normalized_kw):
                categories_to_add.add(normalized_kw)

        # 完整文件名仅在“有语义”时才纳入，避免 img_001 这类噪声分类污染
        if clean_filename and self._is_meaningful_filename_category(clean_filename):
            categories_to_add.add(clean_filename)

        return {c for c in categories_to_add if isinstance(c, str) and c.strip()}

    def _extract_core_name(self, filename: str) -> str:
        base = os.path.splitext(os.path.basename(str(filename)))[0]
        base = str(base).strip()
        base = re.sub(r'[\s_\-]*[\(\[\{]\s*\d+\s*[\)\]\}]\s*$', '', base)
        for pattern in [
            r'(?:[\s_\-]*(?:副本|拷贝|复制|copy|Copy|COPY))\s*$',
            r'(?:[\s_\-]*(?:副本|拷贝|复制)\s*\d*)\s*$'
        ]:
            base = re.sub(pattern, '', base, flags=re.IGNORECASE)
        for pattern in [
            r'(?:[\s_\-]*(?:v|ver|版本|version)\s*[\d\.]+)\s*$',
            r'(?:[\s_\-]*v\s*\d+\.\d+)\s*$'
        ]:
            base = re.sub(pattern, '', base, flags=re.IGNORECASE)
        base = re.sub(r'(?:[\s_\-\.]*\d+)+\s*$', '', base)
        tokens = re.split(r'[\s_\-]+', base)
        tokens = [t.strip() for t in tokens if t and not t.strip().isdigit()]
        # 扩展通用前缀列表，包含常见的文件名前缀
        generic = {'rt', 'img', 'image', 'photo', 'pic', 'export', 'expo', 'exp', 'test', 'tmp', 'temp', 'output', 'out', 'final', 'new', 'old', '品牌', '分类', '商品', 'item', 'product', 'shop'}

        def chinese_len(s: str) -> int:
            return len(re.findall(r'[\u4e00-\u9fa5]', s))
        preferred = [t for t in tokens if chinese_len(t) >= 2]
        if preferred:
            # 按中文长度排序，选择中文最多的，如果长度相同选择更具体的词
            preferred.sort(key=lambda x: (chinese_len(x), len(x)), reverse=True)
            core = preferred[0]
        else:
            candidates = [t for t in tokens if t.lower() not in generic]
            if candidates:
                candidates.sort(key=lambda x: len(x), reverse=True)
                core = candidates[0]
            else:
                # 如果过滤后没有候选，选择最长的token
                if tokens:
                    tokens.sort(key=lambda x: len(x), reverse=True)
                    core = tokens[0]
                else:
                    core = base
        core = re.sub(r'[\s_\-\.]+$', '', core).strip()
        return core if core else os.path.splitext(os.path.basename(str(filename)))[0]

    def _capture_layer_state(self, layer):
        """🔧 新增：捕获图层状态的快照"""
        """用于验证状态一致性"""
        try:
            return {
                'current_text': getattr(layer, 'current_text', ''),
                'text_lines': layer.get_text_lines() if hasattr(layer, 'get_text_lines') else [],
                'layer_id': id(layer),
                'timestamp': time.time()  # 真实时间戳
            }
        except Exception as e:
            print(f"[绑定组] 捕获图层状态失败: {e}")
            return {'error': str(e)}

    def _is_state_consistent(self, old_state, new_state):
        """🔧 新增：验证图层状态是否一致"""
        """防止在分析过程中状态发生变化"""
        try:
            if 'error' in old_state or 'error' in new_state:
                return False

            # 比较关键状态字段
            return (old_state.get('current_text') == new_state.get('current_text') and
                    old_state.get('layer_id') == new_state.get('layer_id'))
        except Exception as e:
            print(f"[绑定组] 状态一致性检查失败: {e}")
            return False

    def _extract_keywords_from_text(self, text: str) -> set:
        """从文字中提取关键词作为分类 - 修复版本，增强跨分类关联"""
        keywords = set()

        text = str(text).strip()
        if len(text) < 2:
            return keywords

        # 🔧 增强：标准化产品分类词典 - 包含更多分类和跨分类关联
        standard_categories = {
            # 美妆护肤
            '口红', '唇膏', '唇彩', '唇釉', '口红套装',
            '面膜', '面贴膜', '睡眠面膜', '清洁面膜',
            '防晒', '防晒霜', '防晒喷雾', '防晒乳',
            '香水', '淡香水', '古龙水', '香氛',
            '面霜', '日霜', '晚霜', '乳液', '润肤霜',
            '精华', '精华液', '精华露', '肌底液',
            '洁面', '洗面奶', '洁面乳', '洁面泡沫',
            '眼霜', '眼精华', '眼膜',
            '粉底', '粉底液', '粉底霜', '气垫', 'BB霜', 'CC霜',
            '眼影', '眼线', '睫毛膏', '眉笔',

            # 数码电器
            '手机', '智能手机', 'iPhone', '华为手机', '小米手机', 'OPPO手机', 'vivo手机',
            '蓝牙音箱', '音箱', '音响', '无线音箱', '便携音箱',
            '耳机', '蓝牙耳机', '无线耳机', '降噪耳机',
            '充电宝', '移动电源', '充电器', '数据线',
            '智能手表', '手环', '运动手表',
            '平板电脑', 'iPad', '安卓平板',
            '笔记本电脑', '笔记本', 'MacBook',
            '相机', '数码相机', '单反', '微单',

            # 服装鞋包
            '连衣裙', '裙子', '长裙', '短裙', '半身裙', 'A字裙',
            'T恤', '短袖', '长袖', '卫衣', '毛衣', '针织衫',
            '牛仔裤', '休闲裤', '运动裤', '打底裤',
            '外套', '夹克', '风衣', '大衣', '羽绒服',
            '运动鞋', '板鞋', '帆布鞋', '皮鞋', '高跟鞋',
            '包包', '手提包', '单肩包', '双肩包', '钱包',

            # 家居生活 - 增强抽纸相关分类
            '抽纸', '纸巾', '面巾纸', '卫生纸', '餐巾纸', '手帕纸', '卷纸',
            '洗衣液', '洗衣粉', '洗衣皂', '洗衣凝珠',
            '洗发水', '护发素', '沐浴露', '香皂',
            '牙膏', '牙刷', '漱口水',
            '毛巾', '浴巾', '洗脸巾',
            '被子', '床单', '枕头', '被套', '枕套',

            # 食品饮料
            '零食', '坚果', '饼干', '巧克力', '糖果',
            '茶叶', '绿茶', '红茶', '乌龙茶', '普洱茶',
            '咖啡', '速溶咖啡', '咖啡豆', '咖啡粉',
            '蜂蜜', '果酱', '花生酱',

            # 母婴用品
            '奶粉', '婴儿奶粉', '儿童奶粉',
            '纸尿裤', '尿不湿', '拉拉裤',
            '奶瓶', '奶嘴', '婴儿餐具',
            '婴儿服装', '连体衣', '爬服',

            # 平台/品牌相关
            '快手', '抖音', '淘宝', '直播', '网红', '达人', '李佳琦', '薇娅',
            '热卖', '爆款', '新品', '推荐', '限时', '优惠', '特价', '打折',
            '维达', '清风', '心相印', '洁柔',  # 纸巾品牌

            # 修饰词
            '春夏', '秋冬', '春季', '夏季', '秋季', '冬季',
            '清新', '保湿', '美白', '抗衰老', '抗皱', '紧致', '修复'
        }

        # 🔧 新增：跨分类关联词典
        cross_category_mapping = {
            '半身裙': ['女装', '服装', '时尚', '搭配', '裙子'],
            '抽纸': ['家居', '日用品', '清洁', '生活用纸', '纸巾'],
            '纸巾': ['抽纸', '面巾纸', '卫生纸', '生活用纸'],
            '快手热卖': ['直播', '网红', '爆款', '抖音'],
            '维达': ['抽纸', '纸巾', '品牌', '生活用纸'],
        }

        # 🔍 第一步：检查标准分类是否在文本中
        for category in standard_categories:
            if category in text:
                keywords.add(category)

        # 🔧 第二步：智能跨分类匹配
        # 如果找到了主要分类，添加其关联词
        for main_category, related_words in cross_category_mapping.items():
            if main_category in text:
                # 添加关联词到关键词集合
                keywords.update(related_words)
                print(f"[智能匹配] 找到主分类 '{main_category}'，添加关联词: {related_words}")

        # 🔍 第三步：智能提取产品词（如果没有找到标准分类）
        if not keywords:
            # 提取2-6个字符的核心词
            import re

            # 移除标点符号和特殊字符
            clean_text = re.sub(r'[，。！？；：、\s]', '', text)

            # 尝试提取可能的产品词
            if len(clean_text) >= 2:
                # 提取连续的中文词组
                chinese_words = re.findall(r'[\u4e00-\u9fa5]{2,6}', clean_text)

                for word in chinese_words:
                    # 🔧 修复：使用统一的停用词检测函数，避免通用修饰词被当作关键词
                    if not self._is_stop_word(word):
                        # 如果这个词看起来像是产品词（不是纯动词/形容词）
                        if len(word) >= 2 and len(word) <= 6:
                            keywords.add(word)

                # 🔧 新增：提取英文关键词（与普通图层分析逻辑保持一致）
                english_words = re.findall(r'[a-zA-Z]{2,}', text)
                for word in english_words:
                    # 统一转换为小写进行停用词检查，但保留原词作为分类（如果需要区分大小写）
                    # 或者为了匹配更容易，可以添加小写版本
                    if not self._is_stop_word(word.lower()):
                        keywords.add(word)
                        # 同时添加小写版本以增加匹配概率
                        keywords.add(word.lower())

            # 如果还是找不到，使用原始文本作为后备
            if not keywords and len(text) >= 2:
                keywords.add(text.strip())

        # 🔧 第四步：上下文感知增强
        # 检查是否出现在电商平台上下文中
        ecommerce_contexts = ['快手', '抖音', '淘宝', '直播', '热卖', '爆款']
        has_ecommerce_context = any(ctx in text for ctx in ecommerce_contexts)

        if has_ecommerce_context and keywords:
            # 如果在电商上下文中，增强产品词的权重
            print(f"[上下文感知] 检测到电商上下文，增强产品词权重: {keywords}")

        return keywords

    def _analyze_layer_files(self, layer, layer_index: int):
        """分析图层文件并分类 - 修复版本，支持文件限制和文字图层特殊处理"""

        # 🔧 新增：检查是否为文字图层
        if self._is_text_layer(layer):
            self._analyze_text_layer_content(layer, layer_index)
            return

        # 原有逻辑：处理普通图像图层
        if not layer.image_source or not os.path.isdir(layer.image_source):
            print(f"[绑定组] 图层 '{layer.name}' (索引{layer_index}) 跳过分析: 无图像源或源不是文件夹")
            return

        # 🔧 关键修复：检查是否有绑定管理器的文件限制
        restricted_files = None
        if hasattr(self, '_binding_manager') and self._binding_manager:
            restricted_files = self._binding_manager.get_layer_file_restrictions(layer)
            if restricted_files:
                print(f"[绑定组] 图层 '{layer.name}' 应用文件限制: {len(restricted_files)} 个文件")

        try:
            indexed_entries = self._get_folder_category_entries_cached(layer.image_source)
            if restricted_files:
                allowed_files = {
                    os.path.normcase(os.path.normpath(os.path.abspath(p)))
                    for p in restricted_files if isinstance(p, str)
                }
                indexed_entries = [
                    item for item in indexed_entries
                    if isinstance(item, dict) and os.path.normcase(
                        os.path.normpath(os.path.abspath(str(item.get('path', ''))))
                    ) in allowed_files
                ]
                print(f"[绑定组] 图层 '{layer.name}' 使用文件限制: {len(indexed_entries)} 个文件")
            else:
                print(f"[绑定组] 图层 '{layer.name}' 扫描文件夹: {len(indexed_entries)} 个文件")

            for item in indexed_entries:
                if not isinstance(item, dict):
                    continue
                file_path = item.get('path')
                categories_to_add = item.get('categories', [])
                if not isinstance(file_path, str) or not file_path:
                    continue
                if not isinstance(categories_to_add, list):
                    categories_to_add = []
                for category in categories_to_add:
                    if not isinstance(category, str) or not category.strip():
                        continue
                    if category not in self.file_categories:
                        self.file_categories[category] = {}

                    if layer_index not in self.file_categories[category]:
                        self.file_categories[category][layer_index] = []

                    if file_path not in self.file_categories[category][layer_index]:
                        self.file_categories[category][layer_index].append(file_path)

                if _BINDING_VERBOSE:
                    filename = os.path.basename(file_path)
                    print(f"  文件: {filename} -> 分类: {list(categories_to_add)}")

        except Exception as e:
            print(f"分析图层文件时出错: {e}")

    def _analyze_text_layer_content(self, layer, layer_index: int):
        """分析文字图层的内容并分类 - 文字图层特殊处理 - 修复状态同步问题"""
        try:
            if not self._is_text_layer(layer):
                return
            # 🔧 修复：增加状态一致性验证
            layer_state_snapshot = self._capture_layer_state(layer)

            # 获取文字图层的所有文字内容
            text_lines = layer.get_text_lines()
            if not text_lines:
                text_lines = []

            # 获取当前显示的文字 - 增加验证
            current_text = getattr(layer, 'current_text', '')
            if not isinstance(current_text, str):
                current_text = str(current_text) if current_text is not None else ''

            if not current_text and text_lines:
                current_text = text_lines[0] if text_lines else ''

            print(f"[绑定组] 分析文字图层 '{layer.name}': 当前文字='{current_text}', 所有文字={text_lines}")

            # 🔧 关键修复：为每个独特的文字内容创建分类
            # 而不仅仅是基于当前文字
            unique_categories = set()

            # 🔧 重要改进：确保当前编辑的文字始终参与分类
            # 即使它不在原始的 text_lines 中
            all_texts = text_lines.copy() if text_lines else []
            if current_text and current_text.strip():
                # 如果当前文字是全新的内容，将其添加到分析集合
                if current_text not in all_texts:
                    all_texts.append(current_text)
                    print(f"[绑定组] 添加新编辑的文字到分析集合: '{current_text}'")

            # 🔧 新增：为当前文字创建专门的分类，确保实时性
            if current_text and current_text.strip():
                # 提取当前文字的关键词
                current_keywords = self._extract_keywords_from_text(current_text)
                unique_categories.update(current_keywords)
                # 同时添加完整文字作为分类
                unique_categories.add(current_text.strip())

            # 🔧 修复：增强文字内容验证，避免空值和异常
            for text_content in all_texts:
                if not text_content or not str(text_content).strip():
                    continue

                # 验证文字内容有效性
                text_str = str(text_content).strip()
                if len(text_str) == 0:
                    continue

                # 提取关键词作为分类（如"口红"、"面膜"、"抖音"等）
                words = self._extract_keywords_from_text(text_str)
                unique_categories.update(words)
                # 同时将每一行完整文案作为分类，支持相同文案精确绑定
                unique_categories.add(text_str)

            # 确保至少有一个分类
            if not unique_categories and current_text:
                unique_categories.add(current_text.strip())
            elif not unique_categories:
                unique_categories.add("空文字")

            print(f"[绑定组] 文字图层 '{layer.name}' 提取到分类: {unique_categories}")

            # 🔧 修复：增加状态一致性检查
            current_state = self._capture_layer_state(layer)
            if not self._is_state_consistent(layer_state_snapshot, current_state):
                print(f"[绑定组] 警告：图层 '{layer.name}' 状态在分析过程中发生变化，可能需要重新分析")
                # 可以选择重新分析或记录状态变化

            # 为每个分类创建条目
            for category_name in unique_categories:
                # 如果分类不存在，创建它
                if category_name not in self.file_categories:
                    self.file_categories[category_name] = {}

                # 为该图层索引创建文件列表（文字图层用虚拟文件路径表示）
                if layer_index not in self.file_categories[category_name]:
                    self.file_categories[category_name][layer_index] = []

                # 🔧 关键：为匹配这个分类的文字内容创建虚拟文件路径
                for text_content in all_texts:
                    text_stripped = str(text_content).strip()
                    if not text_stripped:
                        continue

                    # 🔧 修复：更严格的匹配检查，避免宽松匹配导致的错误绑定
                    should_match = False

                    # 1. 精确匹配（最高优先级）
                    if text_stripped == str(category_name).strip():
                        should_match = True

                    # 2. 分类名在文字内容中（仅当分类名是有效产品词时）
                    elif category_name and str(category_name).lower() in text_stripped.lower():
                        # 检查分类名是否为有效产品词，而不是通用修饰词
                        category_str = str(category_name).strip()
                        if len(category_str) >= 2 and not self._is_stop_word(category_str):
                            should_match = True

                    if should_match:
                        virtual_file_path = self._build_text_virtual_path(layer.name, text_stripped)
                        if virtual_file_path not in self.file_categories[category_name][layer_index]:
                            self.file_categories[category_name][layer_index].append(virtual_file_path)

                # 🔧 新增：特别处理当前文字，确保它始终可用
                if current_text and current_text.strip():
                    current_stripped = current_text.strip()
                    # 检查当前文字是否与这个分类匹配
                    current_should_match = False
                    if category_name and str(category_name).lower() in current_stripped.lower():
                        current_should_match = True
                    elif current_stripped.lower() in str(category_name).lower():
                        current_should_match = True
                    elif current_stripped.lower() == str(category_name).strip().lower():
                        current_should_match = True

                    if current_should_match:
                        current_virtual_path = self._build_text_virtual_path(layer.name, current_stripped)
                        if current_virtual_path not in self.file_categories[category_name][layer_index]:
                            self.file_categories[category_name][layer_index].append(current_virtual_path)
                            print(f"[绑定组] 为分类 '{category_name}' 添加当前文字虚拟路径: {current_virtual_path}")

            print(f"[绑定组] 文字图层 '{layer.name}' 分类完成: 创建了 {len(unique_categories)} 个分类")

        except Exception as e:
            print(f"[绑定组] 分析文字图层内容时出错: {e}")
            import traceback
            traceback.print_exc()
