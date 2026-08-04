"""
app/ui/components — 批图王 shadcn/ui 风格组件库

统一复用 app.ui.theme 的令牌与全局 QSS。所有界面新增控件应从本包取件，
禁止在业务文件写死样式或引入第三套硬编码样式。

组件清单：
    Button / button            按钮（变体 + 尺寸）
    Card / CardHeader / CardTitle / CardDescription / CardContent / CardFooter
    Input / Label / field / form_layout
    Tabs
    Select
    Checkbox / RadioButton / Slider / Switch（统一开关）
    Badge / Alert / Separator / ProgressBar
    Dialog / Sheet
    IconLabel / Icon / icon     主题色 SVG 图标（封装 IconManager）
    Heading / H1 / H2 / H3 / Text / Lead / Muted / Small / Code / Blockquote / Kbd
"""
from app.ui.components.button import Button, button, VARIANTS, SIZES
from app.ui.components.card import (
    Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter)
from app.ui.components.input import Input, Label, field, form_layout
from app.ui.components.tabs import Tabs
from app.ui.components.select import Select
from app.ui.components.controls import Checkbox, RadioButton, Slider, Switch
from app.ui.components.feedback import Badge, Alert, Separator, ProgressBar
from app.ui.components.dialog import Dialog, Sheet
from app.ui.components.icon import IconLabel, Icon, icon, ICON_COLORS
from app.ui.components.typography import (
    Heading, H1, H2, H3, Text, Lead, Muted, Small, Code, Blockquote, Kbd)

__all__ = [
    "Button", "button", "VARIANTS", "SIZES",
    "Card", "CardHeader", "CardTitle", "CardDescription", "CardContent", "CardFooter",
    "Input", "Label", "field", "form_layout",
    "Tabs", "Select",
    "Checkbox", "RadioButton", "Slider", "Switch",
    "Badge", "Alert", "Separator", "ProgressBar",
    "Dialog", "Sheet",
    "IconLabel", "Icon", "icon", "ICON_COLORS",
    "Heading", "H1", "H2", "H3", "Text", "Lead", "Muted", "Small",
    "Code", "Blockquote", "Kbd",
]
