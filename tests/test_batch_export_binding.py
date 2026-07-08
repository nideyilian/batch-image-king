import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.layer_binding_manager import LayerBindingManager
from app.models.binding_group import BindingGroup
from app.utils.batch_export_precomputer import get_batch_precomputer_v2


def _touch_images(directory, prefix, count):
    """创建空图像文件，文件名形如 prefix_01.jpg。"""
    paths = []
    for index in range(1, count + 1):
        path = os.path.join(directory, f"{prefix}_{index:02d}.jpg")
        with open(path, "wb"):
            pass
        paths.append(path)
    return paths


def _image_layer(name, directory):
    """构造一个最小化的图像图层对象。"""
    return SimpleNamespace(
        name=name,
        visible=True,
        image_source=directory,
        is_folder=True,
        _is_folder=True,
        parent_group_id=None,
        type="layer",
    )


class BatchExportBindingTest(unittest.TestCase):
    def test_binding_mode_kept_when_groups_have_different_categories(self):
        """当多个绑定组拥有不同分类时，批量导出仍应进入绑定模式并为每个绑定组匹配文件。"""
        with tempfile.TemporaryDirectory() as dir_a, tempfile.TemporaryDirectory() as dir_b:
            _touch_images(dir_a, "apple", 2)
            _touch_images(dir_b, "banana", 2)

            layer_a = _image_layer("苹果图层", dir_a)
            layer_b = _image_layer("香蕉图层", dir_b)

            binding_manager = LayerBindingManager()
            binding_manager.global_enabled = True

            group_a = BindingGroup("group_a", "苹果组", binding_manager=binding_manager)
            group_a.add_layer(layer_a, 0)
            binding_manager.binding_groups[group_a.group_id] = group_a
            binding_manager.layer_to_group[id(layer_a)] = group_a.group_id

            group_b = BindingGroup("group_b", "香蕉组", binding_manager=binding_manager)
            group_b.add_layer(layer_b, 0)
            binding_manager.binding_groups[group_b.group_id] = group_b
            binding_manager.layer_to_group[id(layer_b)] = group_b.group_id

            document = SimpleNamespace(
                layers=[layer_a, layer_b],
                export_settings={},
                file_path="",
                binding_manager=binding_manager,
            )

            # 直接调用 Document 的分析方法需要 Document 实例，这里复用分析逻辑手动构造
            from app.models.document_export_analysis import DocumentExportAnalysis
            from app.utils.layer_tree import is_layer_group, is_effectively_visible

            class _DocLike(DocumentExportAnalysis):
                pass

            doc_like = _DocLike()
            doc_like.layers = document.layers
            doc_like.binding_manager = binding_manager
            analysis = doc_like._analyze_document_for_export()

            self.assertEqual(analysis["export_mode"], "binding")
            self.assertTrue(analysis["binding_enabled"])
            self.assertIn("apple", analysis["binding_categories"])
            self.assertIn("banana", analysis["binding_categories"])

            with tempfile.TemporaryDirectory() as out_dir:
                precomputer = get_batch_precomputer_v2(document, analysis)
                plan = precomputer.create_export_plan(
                    directory=out_dir,
                    count=4,
                    filename_template="image_{number:04d}",
                    file_format="png",
                    start_index=1,
                    avoid_duplicates=True,
                )

                self.assertGreater(plan.total_count, 0)
                for task in plan.tasks:
                    layer_states = task.combination.layer_states
                    self.assertIn(0, layer_states)
                    self.assertIn(1, layer_states)
                    self.assertIn("apple", os.path.basename(layer_states[0]).lower())
                    self.assertIn("banana", os.path.basename(layer_states[1]).lower())


if __name__ == "__main__":
    unittest.main()
