# 创建"视图"菜单
view_menu = self.addMenu("视图")
toggle_sources_action = QAction("显示/隐藏源面板", self)
toggle_sources_action.setShortcut("Ctrl+S")
toggle_sources_action.triggered.connect(self.main_window.toggle_sources_panel)
view_menu.addAction(toggle_sources_action)

# 创建"工具"菜单
tools_menu = self.addMenu("工具")

# 创建"帮助"菜单 