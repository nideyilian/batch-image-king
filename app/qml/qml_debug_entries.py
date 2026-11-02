"""调试入口与初始文档准备的拆分（从 qml_main.main 抽出）。

这些函数只服务 ``--screenshot`` 验收与人工核查，生产路径不会进入。
抽出的目的：让 ``qml_main.main()`` 只剩「装配 → 加载 → 进事件循环」三段，
而不是被 40 多个调试分支淹没（拆分前 668 行 / ~134 分支，拆后 302 行 / ~37 分支）。

约定：**不读闭包**，所有依赖（args / workspace / window / debug）显式传参。
这样单独阅读任一函数时，不需要回看 main() 的上下文。
"""

from __future__ import annotations

from pathlib import Path


def _demo_requested(args) -> bool:
    """这批参数都要求一份"有内容的" demo 文档，而不是空画布。"""
    return bool(
        args.demo
        or args.demo_effects
        or args.demo_tabs
        or args.demo_shaped
        or args.show_advanced_properties
        or args.cycle_inspector_tabs
        or args.show_random_transform
        or args.show_text_typography
        or args.show_text_appearance
        or args.show_text_effects
        or args.show_crop_tools
        or args.show_vector_path
        or args.show_multi_select
        or args.show_grouped_layers
    )


def wants_initial_document(args) -> bool:
    """是否需要预先准备一份初始文档。

    判断依据是「调用方想看到具体内容」：显式打开、demo、空白画布、选中某图层，
    或任何一个面板类验收入口 —— 它们都要求文档已存在，否则截图里是空画布，
    验收没有意义。

    注意：默认启动（不带任何参数）返回 **False** —— 那种情况首页是预设工作台，
    不是一张白纸。这个语义被 tests/test_qml_debug_entries.py 锁住。
    """
    return bool(
        args.open_path
        or _demo_requested(args)
        or args.blank
        or args.select_layer is not None
        or args.duplicate_selected
        or args.show_batch_export
        or args.show_batch_advanced
        or args.show_batch_unique
        or args.show_multi_tab_export
        or args.show_effects
        or args.show_close_confirm
        or args.show_text_layer_dialog
        or args.show_shaped_layer_dialog
        or args.show_guides
        or args.show_canvas_presets
        or args.show_project_presets
        or args.show_data_relations
        or args.show_size_match
    )


def prepare_initial_document(args, workspace, qml_dir: Path) -> None:
    """建初始文档并按 demo 参数铺好夹具（图层 / 效果 / 引导线等）。

    只改文档状态、不碰窗口与 QML 对象，因此在 ``engine.load()`` 之前调用是安全的。
    """
    # ---- 文档本体 ----
    if args.open_path:
        workspace.openDocument(str(args.open_path.expanduser().resolve()))
    elif _demo_requested(args) and not args.blank:
        workspace.createDemoDocument(str(qml_dir / "assets" / "watch-product.jpg"))
    elif wants_initial_document(args):
        workspace.newDocument(1080, 1350)

    # ---- 选中哪个图层 ----
    # 顺序有意义：显式 --select-layer 优先，其余按面板需求挑默认图层。
    # text_* 系列都选 1 号（文字图层），crop/vector/multi_select 选 0 号（图片图层）。
    if args.select_layer is not None:
        workspace.selectLayer(args.select_layer)
    elif args.show_random_transform:
        workspace.selectLayer(0)
    elif args.show_text_typography:
        workspace.selectLayer(1)
    elif args.show_text_appearance:
        workspace.selectLayer(1)
    elif args.show_text_effects:
        workspace.selectLayer(1)
    elif args.show_crop_tools or args.show_vector_path or args.show_multi_select or args.show_grouped_layers:
        workspace.selectLayer(0)

    # ---- 各面板需要的图层效果 ----
    if args.demo_effects:
        workspace.setSelectedStrokeEnabled(True)
        workspace.setSelectedStrokeWidth(8)
        workspace.setSelectedStrokeColor("#46D7AD")
        workspace.setSelectedCornerRadius(48)
        workspace.setSelectedGradientOverlayEnabled(True)
        workspace.setSelectedGradientOverlayColor(0, "#173B32")
        workspace.setSelectedGradientOverlayColor(1, "#46D7AD")
        workspace.setSelectedGradientOverlayOpacity(38)
        workspace.setSelectedGradientOverlayAngle(45.0)
    if args.duplicate_selected:
        workspace.duplicateSelectedLayer()
    if args.demo_shaped:
        workspace.addShapedLayer(str(qml_dir / "assets" / "watch-product.jpg"), "hexagon")
        workspace.setSelectedPolygonRotation(18.0)
        workspace.setSelectedPolygonCornerRadius(24)
    if args.show_random_transform:
        layer = workspace.document.layers[workspace.selectedLayerIndex]
        layer.aspect_ratio_locked = True
        layer.random_position_enabled = True
        layer.random_position_range = 24
        layer.random_scale_enabled = True
        layer.random_scale_min = 0.85
        layer.random_scale_max = 1.15
        layer.random_rotation_enabled = True
        layer.random_rotation_range = 8.0
        layer.generate_random_transform_params()
        workspace.selectionChanged.emit()
    if args.show_text_typography:
        workspace.setSelectedTextFontFamily("Microsoft YaHei")
        workspace.setSelectedTextFontSize(72)
        workspace.setSelectedTextBold(True)
        workspace.setSelectedTextAlignment("center")
        workspace.setSelectedTextLineSpacingPercent(130)
        workspace.setSelectedTextLetterSpacing(2)
        workspace.setSelectedTextBoxPadding(18)
    if args.show_text_appearance:
        workspace.setSelectedTextBindingEnabled(False)
        workspace.setSelectedTextFillMode("gradient")
        workspace.setSelectedTextGradientType("linear")
        workspace.setSelectedTextGradientDirection("diagonal_lr")
        workspace.setSelectedTextGradientColor(0, "#F7BD63")
        workspace.setSelectedTextGradientColor(1, "#46D7AD")
        workspace.setSelectedTextColorRange(0, 2, "#F1786D")
        workspace.setSelectedTextBackgroundEnabled(True)
        workspace.setSelectedTextBackgroundColor("#101715CC")
        workspace.setSelectedTextBackgroundPadding(14)
        workspace.setSelectedStrokeEnabled(True)
        workspace.setSelectedStrokeWidth(3)
        workspace.setSelectedStrokeColor("#F2F4F3")
    if args.show_text_effects:
        workspace.setSelectedTextBindingEnabled(False)
        workspace.setSelectedTextFillMode("solid")
        workspace.setSelectedTextColor("#F7BD63")
        workspace.setSelectedTextBackgroundEnabled(False)
        workspace.setSelectedStrokeEnabled(True)
        workspace.setSelectedStrokeWidth(2)
        workspace.setSelectedStrokeColor("#F2F4F3")
        workspace.setSelectedTextShadowEnabled(True)
        workspace.setSelectedTextShadowOffset(12, 10)
        workspace.setSelectedTextShadowBlur(9)
        workspace.setSelectedTextShadowColor("#101715B8")
        workspace.setSelectedTextGlowEnabled(True)
        workspace.setSelectedTextGlowStrength(7)
        workspace.setSelectedTextGlowRadius(14)
        workspace.setSelectedTextGlowColor("#F7BD63")
        workspace.copySelectedLayerStyle()
    if args.show_crop_tools:
        workspace.startCropEdit()
        workspace.updateCropRect(0.12, 0.1, 0.88, 0.9)
    if args.show_vector_path:
        workspace.convertSelectedToVectorPath()
        workspace.selectVectorNode(1)
        workspace.setSelectedVectorNodeType("smooth")
    if args.show_multi_select:
        workspace.document.select_layers([0, 1, 2], primary_index=0)
        workspace.layerModel.reset_from_document()
        workspace.selectionChanged.emit()
    if args.show_grouped_layers:
        workspace.document.select_layers([0, 1], primary_index=0)
        workspace.groupSelectedLayers()
    if args.show_guides:
        workspace.addGuide("vertical", workspace.canvasWidth * 0.25)
        workspace.addGuide("vertical", workspace.canvasWidth * 0.75)
        workspace.addGuide("horizontal", workspace.canvasHeight * 0.33)
        workspace.addGuide("horizontal", workspace.canvasHeight * 0.67)


def apply_window_geometry(window, args, debug) -> None:
    """按命令行参数设置窗口尺寸与主题。

    截图模式下**不读写**持久化的窗口几何，否则验收图会被上一次的尺寸顶掉。
    """
    from PySide6.QtCore import Q_ARG, QMetaObject

    window.setProperty("screenshotMode", bool(args.screenshot))
    if args.screenshot:
        window.setProperty("width", max(1180, args.width or 1600))
        window.setProperty("height", max(720, args.height or 960))
    else:
        if args.width:
            window.setProperty("width", max(1180, args.width))
        if args.height:
            window.setProperty("height", max(720, args.height))
    if args.theme:
        if not QMetaObject.invokeMethod(
            window, "setThemeMode", Q_ARG("QVariant", args.theme)
        ):
            debug(f"theme could not be applied: {args.theme}")


def _open_inspector_sections(args, window, workspace, debug) -> None:
    """把 Inspector 的某个分区滚到可见 / 切到指定 Tab（属性页验收）。"""
    from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QTimer

    if args.show_effects:
        window.setProperty("inspectorTab", 0)

    if args.show_random_transform:
        window.setProperty("inspectorTab", 1)

    if args.show_advanced_properties:
        def reveal_advanced_properties() -> None:
            if workspace.selectedSupportsClone:
                workspace.setSelectedCloneEnabled(True)
                workspace.setSelectedCloneFillEnabled(True)
            if not QMetaObject.invokeMethod(window, "revealAdvancedProperties"):
                debug("advanced properties section could not be revealed")

        QTimer.singleShot(120, reveal_advanced_properties)

    if args.cycle_inspector_tabs:
        def show_more_parameters() -> None:
            QMetaObject.invokeMethod(
                window, "selectInspectorTab", Q_ARG("QVariant", 1)
            )

        def return_to_basic_parameters() -> None:
            QMetaObject.invokeMethod(
                window, "selectInspectorTab", Q_ARG("QVariant", 0)
            )

        QTimer.singleShot(120, show_more_parameters)
        QTimer.singleShot(420, return_to_basic_parameters)

    if args.show_random_transform:
        def reveal_random_transform() -> None:
            scroll_view = window.findChild(QObject, "inspectorScroll")
            flickable = scroll_view.property("contentItem") if scroll_view is not None else None
            debug(f"random transform scroller: view={scroll_view}, content={flickable}")
            if flickable is not None:
                content_height = float(scroll_view.property("contentHeight") or 0)
                viewport_height = float(flickable.property("height") or 0)
                debug(f"random transform scroll metrics: content={content_height}, viewport={viewport_height}")
                flickable.setProperty("contentY", max(0, content_height - viewport_height))

        QTimer.singleShot(900, reveal_random_transform)

    if args.show_text_typography:
        def reveal_text_typography() -> None:
            if not QMetaObject.invokeMethod(window, "revealTextTypography"):
                debug("text typography section could not be revealed")

        QTimer.singleShot(120, reveal_text_typography)

    if args.show_text_appearance:
        def reveal_text_appearance() -> None:
            if not QMetaObject.invokeMethod(window, "revealTextAppearance"):
                debug("text appearance section could not be revealed")

        QTimer.singleShot(120, reveal_text_appearance)

    if args.show_text_effects:
        def reveal_text_effects() -> None:
            if not QMetaObject.invokeMethod(window, "revealTextEffects"):
                debug("text effects section could not be revealed")

        QTimer.singleShot(120, reveal_text_effects)


def _open_side_drawers(args, window, debug) -> None:
    """打开右侧抽屉类面板（批量导出 / 配色 / 多标签导出 / 画布预设）。"""
    from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QTimer

    if args.show_batch_export or args.show_batch_advanced or args.show_batch_unique:
        def open_batch_export() -> None:
            drawer = window.findChild(QObject, "batchExportDrawer")
            if drawer is None or not QMetaObject.invokeMethod(drawer, "open"):
                debug("batch export drawer could not be opened")
                return
            if args.show_batch_advanced:
                advanced_dialog = window.findChild(QObject, "batchExportAdvancedDialog")
                if advanced_dialog is None or not QMetaObject.invokeMethod(advanced_dialog, "open"):
                    debug("batch export advanced dialog could not be opened")
            elif args.show_batch_unique:
                def open_unique_layer_selector() -> None:
                    if not QMetaObject.invokeMethod(drawer, "showUniqueLayerSelector"):
                        debug("batch export unique layer selector could not be opened")

                QTimer.singleShot(260, open_unique_layer_selector)

        QTimer.singleShot(80, open_batch_export)

    if args.show_color_picker:
        def open_color_picker() -> None:
            dialog = window.findChild(QObject, "effectColorDialog")
            if dialog is None or not QMetaObject.invokeMethod(
                dialog,
                "openFor",
                Q_ARG("QVariant", "textFill"),
                Q_ARG("QVariant", "#46D7AD"),
                Q_ARG("QVariant", 0),
                Q_ARG("QVariant", 0),
                Q_ARG("QVariant", 0),
            ):
                debug("color picker could not be opened")

        QTimer.singleShot(80, open_color_picker)

    if args.show_multi_tab_export:
        def open_multi_tab_export() -> None:
            drawer = window.findChild(QObject, "multiTabExportDrawer")
            if drawer is None or not QMetaObject.invokeMethod(drawer, "open"):
                debug("multi-tab export drawer could not be opened")

        QTimer.singleShot(80, open_multi_tab_export)

    if args.show_canvas_presets:
        def open_canvas_presets() -> None:
            drawer = window.findChild(QObject, "canvasPresetDrawer")
            if drawer is None or not QMetaObject.invokeMethod(drawer, "open"):
                debug("canvas preset drawer could not be opened")

        QTimer.singleShot(80, open_canvas_presets)


def open_preset_workbench(args, window, debug) -> None:
    """把预设工作台作为首页打开（普通双击启动时的默认行为）。

    触发条件（任一）：
      - ``--open-presets`` / ``--show-project-presets``：显式要求
      - 「没给任何文档相关参数」：即普通双击启动。此时工作台就是首页，
        而不是一张空白画布 —— 用户是奔着"用预设出图"来的，不是来开白纸的。

    反面条件：给了 --open / --demo / --blank / --select-layer 等，
    说明调用方明确想直接看编辑器（调试、自动化、关联文件打开），不能被抢。
    """
    from PySide6.QtCore import QObject, QMetaObject, QTimer

    should_open = bool(args.open_presets or args.show_project_presets) or not (
        wants_initial_document(args) or args.open_path
    )
    if not should_open:
        return

    def open_project_presets() -> None:
        # 预设中心已升级为整页工作台：探测入口改为切到工作台视图，
        # 不再打开已被取代的右侧抽屉。
        if not QMetaObject.invokeMethod(window, "openProjectPresetDrawer"):
            # QML 根对象的普通 function 在部分版本下不暴露给 QMetaObject，
            # 兜底直接写属性切换工作台。
            try:
                window.setProperty("presetWorkbenchVisible", True)
            except Exception:
                debug("preset workbench could not be opened")

    QTimer.singleShot(80, open_project_presets)

    if args.select_preset is not None:
        def select_preset_card() -> None:
            workbench = window.findChild(QObject, "presetWorkbench")
            if workbench is None:
                debug("preset workbench item not found")
                return
            workbench.setProperty("selectPresetIndex", int(args.select_preset))

        QTimer.singleShot(400, select_preset_card)


def open_debug_dialogs(args, window, workspace, workspace_sessions, debug) -> None:
    """打开 ``--show-*`` 对应的对话框（数据关联 / 新建画布 / 改名 / 图层 …）。"""
    from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QTimer

    if args.show_data_relations or args.show_size_match:
        def open_data_relations() -> None:
            drawer = window.findChild(QObject, "dataRelationsDrawer")
            if drawer is None:
                debug("data relations drawer could not be found")
                return
            drawer.setProperty("activeTab", 1 if args.show_size_match else 0)
            if not QMetaObject.invokeMethod(drawer, "open"):
                debug("data relations drawer could not be opened")

        QTimer.singleShot(80, open_data_relations)

    if args.show_new_canvas:
        def open_new_canvas() -> None:
            dialog = window.findChild(QObject, "newCanvasDialog")
            if dialog is None or not QMetaObject.invokeMethod(dialog, "open"):
                debug("new canvas dialog could not be opened")

        QTimer.singleShot(80, open_new_canvas)

    if args.show_resize_canvas:
        def open_resize_canvas() -> None:
            dialog = window.findChild(QObject, "resizeCanvasDialog")
            if dialog is None or not QMetaObject.invokeMethod(dialog, "openForDocument"):
                debug("resize canvas dialog could not be opened")

        QTimer.singleShot(80, open_resize_canvas)

    if args.show_rename_document:
        def open_rename_document() -> None:
            dialog = window.findChild(QObject, "renameDocumentDialog")
            if dialog is None or not QMetaObject.invokeMethod(
                dialog,
                "openForDocument",
                Q_ARG("QVariant", int(workspace_sessions.activeIndex)),
            ):
                debug("rename document dialog could not be opened")

        QTimer.singleShot(80, open_rename_document)

    if args.show_text_layer_dialog:
        def open_text_layer_dialog() -> None:
            dialog = window.findChild(QObject, "textLayerDialog")
            if dialog is None or not QMetaObject.invokeMethod(dialog, "openFresh"):
                debug("text layer dialog could not be opened")

        QTimer.singleShot(80, open_text_layer_dialog)

    if args.show_shaped_layer_dialog:
        def open_shaped_layer_dialog() -> None:
            dialog = window.findChild(QObject, "shapedLayerDialog")
            if dialog is None or not QMetaObject.invokeMethod(dialog, "openFresh"):
                debug("shaped layer dialog could not be opened")

        QTimer.singleShot(80, open_shaped_layer_dialog)

    if args.show_close_confirm:
        def open_close_confirmation() -> None:
            workspace.document.is_modified = True
            workspace.documentInfoChanged.emit()
            workspace_sessions.requestClose(workspace_sessions.activeIndex)

        QTimer.singleShot(80, open_close_confirmation)


def open_debug_overlays(args, window, workspace, workspace_sessions, debug) -> None:
    """按 ``--show-*`` 参数打开抽屉 / 工作台 / 对话框，用于截图验收。

    只做调度，实现在上面四个子函数里。
    """
    _open_inspector_sections(args, window, workspace, debug)
    _open_side_drawers(args, window, debug)
    open_preset_workbench(args, window, debug)
    open_debug_dialogs(args, window, workspace, workspace_sessions, debug)

def panels_need_window_grab(args) -> bool:
    """这些面板是独立浮层/抽屉，``captureRoot`` 抓不到，必须整窗抓图。

    截图验收时必须等它们真正展开后再抓，否则拿到的是空画布；
    也正因为它们是浮层（不在 captureRoot 子树里），只能用 grabWindow。
    """
    return bool(
        args.show_batch_export
        or args.show_batch_advanced
        or args.show_batch_unique
        or args.show_color_picker
        or args.show_multi_tab_export
        or args.show_new_canvas
        or args.show_resize_canvas
        or args.show_rename_document
        or args.show_text_layer_dialog
        or args.show_shaped_layer_dialog
        or args.show_close_confirm
        or args.show_canvas_presets
        or args.show_project_presets
        or args.show_data_relations
        or args.show_size_match
    )

def launcher_source_text() -> str:
    """启动器全部源码（qml_main + 本模块）。

    供"源码里必须存在某个标记"型测试使用：这些测试关心的是"启动器有没有这个
    能力"，而不是"这个能力写在哪个文件"。拆分后代码会在两个文件间移动，
    测试若只读 qml_main.py 就会因为搬家而误报失败（2026-11-02 实际发生过 4 起）。
    """
    here = Path(__file__).resolve().parent
    parts = []
    for name in ("qml_main.py", "qml_debug_entries.py"):
        path = here / name
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)
