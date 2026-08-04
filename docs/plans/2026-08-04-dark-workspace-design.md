# 深色工作台组件系统设计

## 目标

将 `awesome-shadcn-ui` 中适合桌面图像编辑器的组件模式映射为 PySide6 原生组件，统一批图王现有窗口、面板和反馈状态。运行时继续使用深色工作台，不在本阶段提供皮肤切换入口，但主题基础设施必须允许后续注册新皮肤而无需修改业务窗口。

## 技术边界

- 不引入 React、Tailwind、WebView 或浏览器运行时。
- 不改变文档模型、渲染、导出、批量导出和持久化逻辑。
- 优先复用 Qt 原生可访问性、键盘导航、菜单、对话框和布局能力。
- 业务界面不得依赖具体十六进制界面色，只依赖语义令牌和组件属性。
- 图片内容色、用户选择色、渐变值和导出参数不是界面主题色，不纳入禁止范围。

## 分层架构

### 1. 主题注册层

`app/ui/theme/tokens.py` 继续提供 `Theme` 兼容接口，并新增皮肤注册、校验、枚举和切换能力。默认皮肤为 `dark`。现有 `Theme.mode()`、`set_mode()` 保留为兼容别名，新的业务代码使用 `skin()`、`set_skin()` 和 `register_skin()`。

每套皮肤至少提供 background、foreground、card、popover、primary、secondary、muted、accent、destructive、border、input、ring、hover、success、warning、info 等语义色。间距、圆角、字号、控件高度和动效时间继续作为跨皮肤结构令牌。

### 2. 全局语义适配层

`app/ui/theme/provider.py` 生成全局 QSS，并通过应用级事件过滤器处理历史窗口：

- 对未声明语义的普通按钮应用一致的次级样式。
- 对默认确认按钮、取消按钮和破坏性按钮设置对应 variant。
- 对进度条、分组框、标签页和工具按钮补齐 role/variant。
- 尊重业务代码已经设置的动态属性，不覆盖显式语义。
- 在控件首次显示时执行，避免要求每个旧弹窗立即重写。

`CursorDarkTheme` 保留为应用启动兼容入口，内部安装语义适配器并应用默认深色皮肤。

### 3. 公共组件层

组件按职责拆分，保持薄封装和 Qt 原生信号：

- 操作：Button、IconButton、ButtonGroup、Toggle、ToggleGroup、SegmentedControl、Tooltip、Kbd。
- 表单：Input、Textarea、NumberInput、Select、ComboBox、MultiSelect、Checkbox、RadioGroup、Switch、Slider、Field、InputGroup、ColorSwatch。
- 布局：Card、Collapsible、Accordion、Tabs、ScrollArea、Resizable、Sidebar、Separator、AspectRatio。
- 弹层：Dialog、AlertDialog、Sheet、Popover、DropdownMenu、ContextMenu、CommandPalette。
- 反馈与数据：Alert、Toast、Badge、Progress、Spinner、Skeleton、EmptyState、Table、FileDropZone。

网页专属或当前没有明确用途的 Avatar、Calendar、Carousel、Breadcrumb、Pagination、OTP、Marquee、NavigationMenu 不进入运行时组件库。

## 迁移策略

第一步通过全局语义适配覆盖所有历史界面；第二步把高频入口改为显式组件，包括主窗口工具栏、画布对话框、添加图层、图层效果、预设和批量导出；第三步在后续维护中按触达原则迁移低频窗口。兼容层在业务调用全部迁移前不删除。

## 状态与交互

所有交互组件必须覆盖 normal、hover、pressed、focus、disabled；输入类额外覆盖 invalid 和 read-only；异步流程覆盖 idle、loading、success、error、cancelled；数据容器覆盖 loading、empty、error 和 populated。

键盘焦点必须可见。图标按钮必须有 tooltip 或 accessibleName。确认按钮使用 default，普通取消操作使用 outline/secondary，删除或覆盖使用 destructive。Toast 用于非阻塞结果，Alert 用于需要留在当前上下文中的状态，AlertDialog 只用于不可逆确认。

## 验收

- 默认启动仍为深色工作台。
- 新增皮肤只需注册语义令牌并重新应用主题。
- 现有业务窗口无需全部重写即可获得统一基础样式。
- 公共组件可独立构造，动态属性和关键信号可测试。
- Showcase 覆盖所有新增组件类别。
- 全量 pytest 通过，主程序可启动，组件截图无空白、溢出或重叠。
