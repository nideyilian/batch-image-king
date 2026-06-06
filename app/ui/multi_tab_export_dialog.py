from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QCheckBox, QDialogButtonBox, QListWidget,
                              QListWidgetItem, QMessageBox, QProgressDialog, QLineEdit,
                              QGroupBox, QSpinBox, QFormLayout, QApplication)
from PySide6.QtCore import Qt, Signal, QThreadPool, QRunnable, QObject, Slot, QMutex, QTimer, QMetaObject, Q_ARG
import os
import time
import concurrent.futures
import gc
import logging

# 导入参数模板
from app.ui.export_params_template import ExportParamsTemplate, ExportParamsDialog
from app.ui.batch_export_dialog import BatchExportDialog

# 定义信号对象用于线程通信
class ExportWorkerSignals(QObject):
    """工作线程信号"""
    finished = Signal(int, bool, str)  # (标签页索引, 是否成功, 错误信息)
    progress = Signal(int, int)  # (标签页索引, 进度百分比)

# 定义工作线程
class ExportWorker(QRunnable):
    """导出工作线程"""

    def __init__(self, document, tab_index, tab_name, export_request=None):
        super().__init__()
        self.document = document
        self.tab_index = tab_index
        self.tab_name = tab_name
        self.export_request = export_request or {}
        self.signals = ExportWorkerSignals()
        self._mutex = QMutex()  # 添加线程安全保护
        self._is_cancelled = False

    def run(self):
        """执行导出任务"""
        try:
            # 检查是否已取消
            self._mutex.lock()
            if self._is_cancelled:
                self._mutex.unlock()
                return
            self._mutex.unlock()

            if not self.export_request:
                self.signals.finished.emit(self.tab_index, False, "导出参数无效")
                return

            def check_canceled():
                self._mutex.lock()
                cancelled = bool(self._is_cancelled)
                self._mutex.unlock()
                return cancelled or bool(getattr(self.document, '_export_canceled', False))

            success = BatchExportDialog.execute_export_request(
                self.document,
                self.export_request,
                cancel_callback=check_canceled
            )

            # 清理内存
            if hasattr(self.document, '_optimize_memory'):
                self.document._optimize_memory()

            # 发送完成信号
            self.signals.finished.emit(self.tab_index, success, "")

        except Exception as e:
            error_msg = str(e)
            # 使用日志记录错误
            try:
                logger = logging.getLogger('批图王')
                logger.error(f"导出标签页 '{self.tab_name}' 时出错: {error_msg}", exc_info=True)
            except:
                pass
            safe_print(f"导出标签页 '{self.tab_name}' 时出错: {error_msg}")
            self.signals.finished.emit(self.tab_index, False, error_msg)
        finally:
            # 确保资源清理
            try:
                # 强制垃圾回收
                gc.collect()
            except:
                pass

    def cancel(self):
        """取消导出任务"""
        self._mutex.lock()
        self._is_cancelled = True
        self._mutex.unlock()
        try:
            if hasattr(self.document, '_export_canceled'):
                self.document._export_canceled = True
            if hasattr(self.document, 'cancel_export'):
                self.document.cancel_export()
        except Exception:
            pass


class MultiTabExportDialog(QDialog):
    """多标签页批量导出对话框"""

    def __init__(self, document_manager, parent=None):
        super().__init__(parent)

        self.document_manager = document_manager
        # 避免覆盖 QObject.parent() 方法：使用独立字段保存宿主窗口引用
        self._host_parent = parent
        self.selected_tabs = []  # 存储被选中的标签页索引
        self.all_tabs_data = []  # 存储所有标签页数据
        self.export_params = None  # 导出参数模板
        self._export_started = False

        # 多线程处理相关
        self.thread_pool = QThreadPool.globalInstance()
        self.max_threads = min(QThreadPool.globalInstance().maxThreadCount(), 4)  # 默认最大线程数为4或系统最大值
        self.running_exports = {}  # 正在运行的导出任务
        self.export_results = {}   # 导出结果
        self.mutex = QMutex()      # 互斥锁保护共享数据

        self.setWindowTitle("多标签页批量导出")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        self.setup_ui()

    def _resolve_progress_parent(self):
        """获取进度弹窗父对象，兼容 parent 属性被覆盖的历史代码。"""
        parent_widget = self.parentWidget()
        if parent_widget is not None:
            return parent_widget
        if self._host_parent is not None:
            return self._host_parent
        return self

    def setup_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)

        # 说明标签
        description = QLabel("请选择要参与批量导出的标签页：")
        description.setStyleSheet("font-weight: bold;")
        layout.addWidget(description)

        # 搜索框
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入关键词筛选标签页")
        self.search_input.textChanged.connect(self.filter_tabs)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)

        # 标签页列表
        self.tab_list = QListWidget()
        self.update_tab_list()
        layout.addWidget(self.tab_list)

        # 全选/取消全选按钮
        select_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(self.select_all)
        self.deselect_all_btn = QPushButton("取消全选")
        self.deselect_all_btn.clicked.connect(self.deselect_all)

        select_layout.addWidget(self.select_all_btn)
        select_layout.addWidget(self.deselect_all_btn)
        layout.addLayout(select_layout)

        # 导出参数设置组
        params_group = QGroupBox("批量导出设置")
        params_layout = QVBoxLayout()

        # 批量参数选项
        batch_params_layout = QHBoxLayout()
        self.use_batch_params_check = QCheckBox("使用统一导出参数")
        self.use_batch_params_check.setToolTip("启用后将对所有选中标签页应用相同的导出参数")
        self.edit_params_btn = QPushButton("编辑参数")
        self.edit_params_btn.clicked.connect(self.edit_export_params)
        batch_params_layout.addWidget(self.use_batch_params_check)
        batch_params_layout.addWidget(self.edit_params_btn)
        params_layout.addLayout(batch_params_layout)

        # 线程设置
        thread_layout = QFormLayout()
        self.thread_count_spin = QSpinBox()
        self.thread_count_spin.setRange(1, QThreadPool.globalInstance().maxThreadCount())
        self.thread_count_spin.setValue(self.max_threads)
        self.thread_count_spin.valueChanged.connect(self.update_thread_count)
        thread_layout.addRow("并行导出线程数:", self.thread_count_spin)
        params_layout.addLayout(thread_layout)

        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        # 对话框按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.on_accept)
        button_box.rejected.connect(self.reject)

        # 设置按钮中文文本
        button_box.button(QDialogButtonBox.Ok).setText("确定")
        button_box.button(QDialogButtonBox.Cancel).setText("取消")

        layout.addWidget(button_box)

    def _notify_non_blocking(self, message, timeout_ms=7000):
        """非阻塞提示：优先状态栏，不弹阻塞对话框"""
        try:
            root = self.window()
            if root is not None and hasattr(root, 'statusBar'):
                status_bar = root.statusBar()
                if status_bar is not None:
                    status_bar.showMessage(str(message), int(timeout_ms))
        except Exception:
            pass
        try:
            safe_print(str(message))
        except Exception:
            pass

    def _build_tab_export_request(self, document, output_dir=None):
        """Build a plain export request on the GUI thread before handing work to QRunnable."""
        dialog = None
        try:
            dialog = BatchExportDialog(document, self)
            if getattr(self, 'use_batch_params', False):
                dialog.apply_export_params(self.export_params)
            if output_dir:
                dialog.directory = output_dir
                if hasattr(dialog, 'path_edit'):
                    dialog.path_edit.setText(output_dir)
            request, error_message = dialog.build_export_request()
            return request, error_message
        except Exception as e:
            return None, str(e)
        finally:
            try:
                if dialog is not None:
                    dialog.deleteLater()
            except Exception:
                pass

    def update_tab_list(self):
        """更新标签页列表"""
        self.tab_list.clear()
        self.all_tabs_data = []

        # 获取所有标签页
        for i in range(self.document_manager.get_document_count()):
            document = self.document_manager.get_document(i)
            if document:
                # 构建标签页描述文本
                tab_name = self.document_manager.get_document_name(i)

                # 获取画布尺寸信息
                canvas_info = ""
                if hasattr(document, 'canvas_width') and hasattr(document, 'canvas_height'):
                    canvas_info = f"{document.canvas_width}x{document.canvas_height}"

                # 获取图层数量信息
                layers_count = 0
                if hasattr(document, 'layers'):
                    layers_count = len(document.layers)

                # 完整描述: "标签名 (宽x高, n个图层)"
                checkbox_text = tab_name
                if canvas_info or layers_count > 0:
                    checkbox_text += f" ({canvas_info}, {layers_count}个图层)"

                # 保存标签页数据
                self.all_tabs_data.append({
                    'index': i,
                    'name': tab_name,
                    'display_text': checkbox_text
                })

                # 创建列表项
                self.add_tab_item(i, checkbox_text)

    def add_tab_item(self, tab_index, display_text):
        """添加标签页项到列表"""
        item = QListWidgetItem()
        self.tab_list.addItem(item)

        # 创建复选框
        checkbox = QCheckBox(display_text)
        checkbox.setChecked(True)  # 默认选中

        # 设置项目小部件
        self.tab_list.setItemWidget(item, checkbox)

    def filter_tabs(self, keyword):
        """根据关键词筛选标签页"""
        self.tab_list.clear()

        keyword = keyword.lower()
        for tab_data in self.all_tabs_data:
            # 如果关键词为空或者关键词在标签页名称中，则显示
            if not keyword or keyword in tab_data['name'].lower() or keyword in tab_data['display_text'].lower():
                self.add_tab_item(tab_data['index'], tab_data['display_text'])

    def select_all(self):
        """选择所有标签页"""
        for i in range(self.tab_list.count()):
            item = self.tab_list.item(i)
            checkbox = self.tab_list.itemWidget(item)
            if checkbox:
                checkbox.setChecked(True)

    def deselect_all(self):
        """取消选择所有标签页"""
        for i in range(self.tab_list.count()):
            item = self.tab_list.item(i)
            checkbox = self.tab_list.itemWidget(item)
            if checkbox:
                checkbox.setChecked(False)

    def get_selected_tabs(self):
        """获取选中的标签页索引列表"""
        selected_tabs = []

        # 首先创建一个显示项目索引到标签页索引的映射
        visible_tabs = {}
        for i in range(self.tab_list.count()):
            item = self.tab_list.item(i)
            checkbox = self.tab_list.itemWidget(item)
            if checkbox:
                # 在所有标签数据中查找匹配的显示文本
                for tab_data in self.all_tabs_data:
                    if tab_data['display_text'] == checkbox.text():
                        visible_tabs[i] = tab_data['index']
                        break

        # 然后收集所有勾选的标签页索引
        for i in range(self.tab_list.count()):
            item = self.tab_list.item(i)
            checkbox = self.tab_list.itemWidget(item)
            if checkbox and checkbox.isChecked() and i in visible_tabs:
                original_index = visible_tabs[i]
                selected_tabs.append(original_index)

        return selected_tabs

    def edit_export_params(self):
        """编辑批量导出参数"""
        dialog = ExportParamsDialog(self, self.export_params)
        if dialog.exec() == QDialog.Accepted:
            self.export_params = dialog.template
            self.use_batch_params_check.setChecked(True)
            QMessageBox.information(self, "参数已设置", f"已设置批量导出参数: {self.export_params.name}")

    def update_thread_count(self, value):
        """更新线程数量"""
        self.max_threads = value

    def on_accept(self):
        """点击确定按钮时的处理"""
        self.selected_tabs = self.get_selected_tabs()

        # 检查是否有选择标签页
        if not self.selected_tabs:
            QMessageBox.warning(self, "警告", "请至少选择一个标签页进行导出！")
            return

        if self._export_started:
            return

        self._export_started = True
        self.start_export()
        # 保留对象但隐藏配置窗口，避免干扰其他文档操作
        self.hide()

    def start_export(self):
        """开始导出所有选中的标签页"""
        if not self.selected_tabs:
            return

        # 创建导出进度对话框
        progress_parent = self._resolve_progress_parent()
        self.progress_dialog = QProgressDialog("正在批量导出多个标签页...", "取消", 0, len(self.selected_tabs), progress_parent)
        self.progress_dialog.setWindowTitle("多标签页导出进度")
        self.progress_dialog.setWindowModality(Qt.NonModal)
        self.progress_dialog.setModal(False)
        self.progress_dialog.setWindowFlag(Qt.WindowStaysOnTopHint, False)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setMinimumWidth(450)
        self.progress_dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        self.progress_dialog.show()

        # 保存当前活动标签页索引，以便导出后恢复
        self.current_tab = self.document_manager.active_document_index

        # 记录导出结果
        self.export_results = {
            'total': len(self.selected_tabs),
            'success': 0,
            'failed': [],
            'completed': 0
        }

        # 记录开始时间
        self.start_time = time.time()

        # 检查是否使用批量参数
        self.use_batch_params = self.use_batch_params_check.isChecked() and self.export_params is not None

        # 创建统一的输出目录（可选）
        base_output_dir = None
        if self.use_batch_params and self.export_params and hasattr(self.export_params, 'output_directory') and self.export_params.output_directory:
            # 使用参数中的输出目录，每个标签页创建子目录
            base_output_dir = self.export_params.output_directory
            if not os.path.exists(base_output_dir):
                try:
                    os.makedirs(base_output_dir)
                except Exception as e:
                    self._notify_non_blocking(f"创建目录失败：{str(e)}", 10000)
                    self.progress_dialog.close()
                    return

        # 如果是多线程模式
        if self.max_threads > 1:
            try:
                # 显示多线程导出信息
                self.progress_dialog.setLabelText(f"正在使用 {self.max_threads} 个线程并行导出 {len(self.selected_tabs)} 个标签页...")

                # 创建线程池
                self.thread_pool.setMaxThreadCount(self.max_threads)
                self.running_exports = {}

                # 添加导出完成的回调函数
                def on_export_finished(tab_index, success, error_msg):
                    # 使用QMetaObject.invokeMethod确保UI更新在主线程中进行
                    QMetaObject.invokeMethod(self, "_handle_export_finished",
                                           Qt.QueuedConnection,
                                           Q_ARG(int, tab_index),
                                           Q_ARG(bool, success),
                                           Q_ARG(str, error_msg))

                # 提交导出任务到线程池
                batch_size = max(1, len(self.selected_tabs) // self.max_threads)  # 每个工作线程至少处理1个任务
                for tab_index in self.selected_tabs:
                    document = self.document_manager.get_document(tab_index)
                    tab_name = self.document_manager.get_document_name(tab_index)

                    if document:
                        # 为每个标签页准备输出目录
                        output_dir = None
                        if base_output_dir:
                            # 创建以标签页名称命名的子目录
                            safe_tab_name = "".join(c for c in tab_name if c.isalnum() or c in ".-_ ")
                            output_dir = os.path.join(base_output_dir, safe_tab_name)
                            try:
                                if not os.path.exists(output_dir):
                                    os.makedirs(output_dir)
                            except Exception as e:
                                safe_print(f"为标签页 '{tab_name}' 创建目录失败: {str(e)}")
                                output_dir = base_output_dir  # 回退到基础目录

                        request, error_message = self._build_tab_export_request(document, output_dir)
                        if not request:
                            QTimer.singleShot(
                                0,
                                lambda idx=tab_index, err=error_message or "导出参数无效": self._handle_export_finished(idx, False, err)
                            )
                            continue

                        # 创建工作线程
                        worker = ExportWorker(document, tab_index, tab_name, request)
                        worker.signals.finished.connect(on_export_finished)
                        self.running_exports[tab_index] = worker

                        # 优化：设置导出任务优先级，更均匀地分配任务
                        self.thread_pool.start(worker, self.max_threads - (tab_index % self.max_threads))

                # 检查进度的定时器，代替循环+sleep
                self.check_timer = QTimer(self)
                self.check_timer.timeout.connect(self.check_export_progress)
                self.check_timer.start(500)  # 每500毫秒检查一次

                # 连接取消按钮
                self.progress_dialog.canceled.connect(self.cancel_export)

            except Exception as e:
                # 处理启动导出时的异常
                error_msg = f"启动多线程导出时出错: {str(e)}"
                try:
                    logger = logging.getLogger('批图王')
                    logger.error(error_msg, exc_info=True)
                except:
                    pass
                safe_print(error_msg)
                self._notify_non_blocking(error_msg, 10000)
                if hasattr(self, 'progress_dialog'):
                    self.progress_dialog.close()
                self._export_started = False
        else:
            # 单线程模式，逐个导出
            self.current_export_index = 0

            # 准备输出目录
            if base_output_dir:
                self.base_output_dir = base_output_dir
            self.process_next_tab()

    @Slot(int, bool, str)
    def _handle_export_finished(self, tab_index, success, error_msg):
        """在主线程中处理导出完成事件"""
        try:
            self.mutex.lock()
            try:
                self.running_exports.pop(tab_index, None)
            except Exception:
                pass
            self.export_results['completed'] += 1

            if success:
                self.export_results['success'] += 1
            else:
                tab_name = next((tab['name'] for tab in self.all_tabs_data if tab['index'] == tab_index), f"标签页 {tab_index}")
                self.export_results['failed'].append(f"{tab_name} (错误: {error_msg})")

            # 更新进度对话框
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                self.progress_dialog.setValue(self.export_results['completed'])
                self.update_progress_text()

            # 如果所有任务完成，恢复原标签页并显示结果
            if self.export_results['completed'] >= len(self.selected_tabs):
                QTimer.singleShot(100, self.export_finished)  # 延迟执行，确保UI更新完成

            self.mutex.unlock()
        except Exception as e:
            self.mutex.unlock()
            safe_print(f"处理导出完成事件时出错: {e}")

    def check_export_progress(self):
        """定时检查导出进度"""
        # 如果用户取消，停止所有任务
        if hasattr(self, 'progress_dialog') and self.progress_dialog and self.progress_dialog.wasCanceled():
            self.cancel_export()
            return

        # 每次更新进度文本
        self.update_progress_text()

    def update_progress_text(self):
        """更新进度对话框文本"""
        if self.export_results['completed'] > 0:
            elapsed_time = time.time() - self.start_time
            avg_time_per_tab = elapsed_time / self.export_results['completed']
            remaining_tabs = len(self.selected_tabs) - self.export_results['completed']
            estimated_time_left = avg_time_per_tab * remaining_tabs

            # 格式化时间
            if estimated_time_left < 60:
                time_str = f"{estimated_time_left:.1f}秒"
            elif estimated_time_left < 3600:
                time_str = f"{estimated_time_left / 60:.1f}分钟"
            else:
                time_str = f"{estimated_time_left / 3600:.1f}小时"

            if self.max_threads > 1:
                progress_text = (f"正在并行导出 {len(self.selected_tabs)} 个标签页 (使用 {self.max_threads} 个线程)\n"
                              f"已完成: {self.export_results['success']}/{self.export_results['completed']} 个标签页\n"
                              f"预计剩余时间: {time_str}")
            else:
                # 单线程模式
                current_tab_index = self.selected_tabs[self.current_export_index] if self.current_export_index < len(self.selected_tabs) else -1
                if current_tab_index >= 0:
                    tab_name = self.document_manager.get_document_name(current_tab_index)
                    progress_text = (f"正在导出标签页 {tab_name} ({self.export_results['completed']+1}/{len(self.selected_tabs)})\n"
                                  f"已完成: {self.export_results['success']}/{self.export_results['completed']} 个标签页\n"
                                  f"预计剩余时间: {time_str}")
                else:
                    progress_text = f"已完成: {self.export_results['success']}/{self.export_results['completed']} 个标签页"

            self.progress_dialog.setLabelText(progress_text)

    def process_next_tab(self):
        """处理下一个标签页 (单线程模式)"""
        # 如果用户取消或已处理完所有标签页，则结束流程
        if self.progress_dialog.wasCanceled() or self.current_export_index >= len(self.selected_tabs):
            self.export_finished()
            return

        # 获取当前要处理的标签页索引
        tab_index = self.selected_tabs[self.current_export_index]
        tab_name = self.document_manager.get_document_name(tab_index)

        # 更新进度对话框
        self.progress_dialog.setValue(self.export_results['completed'])
        self.update_progress_text()

        # 处理逻辑移动到单独的方法，以便通过QTimer调用避免UI阻塞
        QTimer.singleShot(50, lambda: self._process_tab(tab_index, tab_name))

    def _process_tab(self, tab_index, tab_name):
        """真正的标签页处理逻辑，通过QTimer延迟调用"""
        try:
            # 激活要导出的标签页
            document = self.document_manager.get_document(tab_index)
            if document:
                # 切换到该标签页
                self.document_manager.set_active_document(tab_index)

                # 打开并执行该标签页的批量导出
                if hasattr(self._host_parent, 'tab_widget'):
                    self._host_parent.tab_widget.setCurrentIndex(tab_index)

                # 准备输出目录
                output_dir = None
                if hasattr(self, 'base_output_dir'):
                    # 创建以标签页名称命名的子目录
                    safe_tab_name = "".join(c for c in tab_name if c.isalnum() or c in ".-_ ")
                    output_dir = os.path.join(self.base_output_dir, safe_tab_name)
                    try:
                        if not os.path.exists(output_dir):
                            os.makedirs(output_dir)
                    except Exception as e:
                        safe_print(f"为标签页 '{tab_name}' 创建目录失败: {str(e)}")
                        output_dir = self.base_output_dir  # 回退到基础目录

                request, error_message = self._build_tab_export_request(document, output_dir)
                if not request:
                    QTimer.singleShot(0, lambda err=error_message or "导出参数无效": self._handle_export_error(tab_name, err))
                    return

                QApplication.processEvents()

                worker = ExportWorker(document, tab_index, tab_name, request)

                def on_finished(finished_tab_index, success, error_msg):
                    try:
                        self.running_exports.pop(finished_tab_index, None)
                    except Exception:
                        pass
                    if success:
                        self._handle_export_result(True, tab_name)
                    else:
                        self._handle_export_error(tab_name, error_msg or "导出失败")

                worker.signals.finished.connect(on_finished)
                self.running_exports[tab_index] = worker
                self.thread_pool.start(worker)

                # 不立即处理下一个，等待当前导出完成
                return
        except Exception as e:
            # 记录错误信息
            error_msg = str(e)
            safe_print(f"导出标签页 '{tab_name}' 时出错: {error_msg}")

            # 使用QTimer在主线程中显示错误消息
            QTimer.singleShot(0, lambda err=error_msg: self._handle_export_error(tab_name, err))

    def _handle_export_result(self, result, tab_name):
        """处理导出结果（在主线程中调用）"""
        # 更新结果状态
        if result:
            self.export_results['success'] += 1
        else:
            self.export_results['failed'].append(tab_name)

        # 更新完成数量
        self.export_results['completed'] += 1

        # 移到下一个标签页
        self.current_export_index += 1

        # 处理下一个
        QTimer.singleShot(100, self.process_next_tab)

    def _handle_export_error(self, tab_name, error_msg):
        """处理导出错误（在主线程中调用）"""
        self.export_results['failed'].append(f"{tab_name} (错误: {error_msg})")
        self._notify_non_blocking(
            f"标签页“{tab_name}”导出失败：{error_msg}（已继续其他标签页）",
            9000
        )

        # 更新完成数量
        self.export_results['completed'] += 1

        # 移到下一个标签页
        self.current_export_index += 1

        # 处理下一个
        QTimer.singleShot(100, self.process_next_tab)

    def cancel_export(self):
        """取消导出操作"""
        # 防止重复取消
        if hasattr(self, '_canceling') and self._canceling:
            return

        self._canceling = True

        try:
            # 停止定时器
            if hasattr(self, 'check_timer') and self.check_timer.isActive():
                self.check_timer.stop()

            # 取消所有正在运行的工作线程
            if hasattr(self, 'running_exports'):
                for worker in self.running_exports.values():
                    if hasattr(worker, 'cancel'):
                        worker.cancel()

            # 清空线程池中的任务
            if self.max_threads > 1:
                self.thread_pool.clear()
                # 等待当前任务完成
                self.thread_pool.waitForDone(3000)  # 最多等待3秒

            # 强制内存清理
            gc.collect()

            # 只显示一次取消消息
            if not hasattr(self, '_cancel_message_shown'):
                self._cancel_message_shown = True
                self._notify_non_blocking("多标签导出已取消", 5000)

            # 恢复原标签页
            self.restore_original_tab()

            # 关闭进度对话框
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                self.progress_dialog.close()
            # 取消后关闭该文档的多标签导出窗口实例
            self.close()

        except Exception as e:
            safe_print(f"取消导出时出错: {str(e)}")
            # 确保进度对话框关闭
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                self.progress_dialog.close()
        finally:
            # 重置取消标志
            self._canceling = False
            self._export_started = False

    def export_finished(self):
        """所有导出任务完成"""
        try:
            # 停止定时器
            if hasattr(self, 'check_timer') and self.check_timer.isActive():
                self.check_timer.stop()

            # 强制内存清理
            gc.collect()

            # 恢复原来的标签页
            self.restore_original_tab()

            # 计算总耗时
            total_time = time.time() - self.start_time if hasattr(self, 'start_time') else 0
            if total_time < 60:
                time_display = f"{total_time:.1f}秒"
            elif total_time < 3600:
                time_display = f"{total_time / 60:.1f}分钟"
            else:
                time_display = f"{total_time / 3600:.1f}小时"

            # 关闭进度对话框
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                self.progress_dialog.close()

            # 显示导出结果摘要
            if self.export_results.get('failed', []):
                error_message = "以下标签页导出失败:\n- " + "\n- ".join(self.export_results['failed'])
                self._notify_non_blocking(
                    f"多标签导出部分完成：成功 {self.export_results.get('success', 0)}/{len(self.selected_tabs)}，"
                    f"耗时 {time_display}。失败详情见日志。",
                    10000
                )
                safe_print(error_message)
            else:
                self._notify_non_blocking(
                    f"多标签导出完成：共 {self.export_results.get('success', 0)} 个标签页，耗时 {time_display}",
                    9000
                )
            # 导出完成后关闭该实例，主窗口会清理映射
            self.close()
        except Exception as e:
            # 处理导出完成时的异常
            error_msg = f"完成导出时出错: {str(e)}"
            try:
                logger = logging.getLogger('批图王')
                logger.error(error_msg, exc_info=True)
            except:
                pass
            safe_print(error_msg)
        finally:
            self._export_started = False
            if 'error_msg' in locals() and error_msg:
                self._notify_non_blocking(error_msg, 10000)

    def restore_original_tab(self):
        """恢复原来的标签页"""
        try:
            if hasattr(self, 'current_tab') and 0 <= self.current_tab < self.document_manager.get_document_count():
                self.document_manager.set_active_document(self.current_tab)
                if hasattr(self._host_parent, 'tab_widget'):
                    self._host_parent.tab_widget.setCurrentIndex(self.current_tab)
        except Exception as e:
            safe_print(f"恢复原标签页时出错: {str(e)}")


def safe_print(message: str):
    """安全的打印函数，避免编码问题"""
    try:
        print(message)
    except (UnicodeEncodeError, OSError):
        try:
            # 尝试使用ASCII编码
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            print(f"[DEBUG] {ascii_message}")
        except:
            # 最后的备选方案
            print("[DEBUG] Message encoding failed")
