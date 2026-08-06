const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");
const lucide = require("lucide");

const root = path.resolve(__dirname, "..", "..");
const productImage = fs.readFileSync(path.join(root, "app", "qml", "assets", "watch-product.jpg")).toString("base64");

function escapeAttribute(value) {
  return String(value).replaceAll("&", "&amp;").replaceAll('"', "&quot;");
}

function icon(name, size = 16) {
  const nodes = lucide[name];
  if (!nodes) throw new Error(`Unknown Lucide icon: ${name}`);
  const body = nodes.map(([tag, attributes]) => {
    const attrs = Object.entries(attributes)
      .map(([key, value]) => `${key.replace(/[A-Z]/g, match => `-${match.toLowerCase()}`)}="${escapeAttribute(value)}"`)
      .join(" ");
    return `<${tag} ${attrs}></${tag}>`;
  }).join("");
  return `<svg class="icon" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
}

const variants = [
  {
    slug: "production-console",
    code: "A",
    name: "生产控制台",
    note: "高密度 · 低干扰 · 批量任务优先",
    accent: "#3bd5aa",
    accentStrong: "#67e6c1",
    accentInk: "#06271f",
    bg: "#0d1011",
    bar: "#111516",
    panel: "#151a1c",
    panelAlt: "#1a2022",
    control: "#20272a",
    hover: "#293235",
    border: "#2b3437",
    borderStrong: "#3b474a",
    text: "#f3f6f5",
    muted: "#aab5b1",
    quiet: "#6f7c78",
    radius: "4px",
    density: "compact",
    rail: "48px",
    layers: "276px",
    inspector: "342px"
  },
  {
    slug: "fluent-workspace",
    code: "B",
    name: "Fluent 工作区",
    note: "Windows 熟悉感 · 层级柔和 · 组件更宽松",
    accent: "#5ba7ff",
    accentStrong: "#80bcff",
    accentInk: "#07192b",
    bg: "#111318",
    bar: "#171a20",
    panel: "#1b1f26",
    panelAlt: "#21262e",
    control: "#272d36",
    hover: "#303843",
    border: "#343b46",
    borderStrong: "#485261",
    text: "#f5f7fa",
    muted: "#bbc3ce",
    quiet: "#7e8997",
    radius: "7px",
    density: "relaxed",
    rail: "52px",
    layers: "292px",
    inspector: "356px"
  },
  {
    slug: "creator-studio",
    code: "C",
    name: "创作工作室",
    note: "画布主导 · 控件留白 · 视觉表达更强",
    accent: "#ff7968",
    accentStrong: "#ff9c8d",
    accentInk: "#2d0906",
    bg: "#101011",
    bar: "#171718",
    panel: "#1c1c1f",
    panelAlt: "#232328",
    control: "#29292f",
    hover: "#34343b",
    border: "#37373e",
    borderStrong: "#50505a",
    text: "#f7f5f4",
    muted: "#c0bcba",
    quiet: "#847f7d",
    radius: "5px",
    density: "studio",
    rail: "56px",
    layers: "252px",
    inspector: "330px"
  }
];

function controlIcon(iconName, label, extra = "") {
  return `<button class="icon-button ${extra}" aria-label="${label}">${icon(iconName)}<span class="tooltip">${label}</span></button>`;
}

function navItem(iconName, label, active = false) {
  return `<button class="nav-item ${active ? "active" : ""}">${icon(iconName, 15)}<span>${label}</span></button>`;
}

function field(label, value, suffix = "") {
  return `<div class="field-row"><span class="field-label">${label}</span><div class="field"><span>${value}</span>${suffix ? `<small>${suffix}</small>` : ""}</div></div>`;
}

function section(title, summary, content, open = true) {
  return `<section class="property-section ${open ? "open" : ""}"><header><strong>${title}</strong><span>${summary}</span>${icon("ChevronDown", 14)}</header><div class="section-body">${content}</div></section>`;
}

function html(v) {
  const denseClass = `density-${v.density}`;
  const layers = [
    { icon: "Type", title: "限量腕表", meta: "文字 · 1 条候选", active: false },
    { icon: "Type", title: "陨石黑 · 2026", meta: "文字 · 3 条候选", active: true },
    { icon: "Image", title: "产品底图", meta: "图片 · 单图", active: false }
  ];
  const layerRows = layers.map((layer, index) => `
    <div class="layer-row ${layer.active ? "active" : ""}">
      <button class="visibility">${icon("Eye", 14)}</button>
      <div class="thumb ${layer.icon === "Type" ? "text-thumb" : ""}">${icon(layer.icon, 17)}</div>
      <div class="layer-copy"><strong>${layer.title}</strong><span>${layer.meta}</span></div>
      <button class="lock">${icon(index === 1 ? "LockKeyhole" : "LockOpen", 14)}</button>
    </div>`).join("");

  const inspector = [
    section("基本属性", "354 × 94", `
      ${field("名称", "陨石黑 · 2026")}
      <div class="split-fields">${field("位置", "68", "X")}${field("", "1040", "Y")}</div>
      <div class="split-fields">${field("尺寸", "354", "W")}${field("", "94", "H")}</div>
    `),
    section("文字内容", "1 条候选", `
      <div class="textarea">限量腕表</div>
      <div class="segmented"><button class="selected">按行随机</button><button>整段排版</button></div>
      <div class="micro-row"><span>候选文案</span><strong>1 条</strong><button>${icon("Shuffle", 13)} 重新抽取</button></div>
    `),
    section("字体", "86 px", `
      <div class="select-field"><span>Microsoft YaHei</span>${icon("ChevronsUpDown", 14)}</div>
      <div class="type-row"><div class="field"><span>86</span><small>px</small></div><button class="type-toggle active">B</button><button class="type-toggle"><em>I</em></button></div>
    `),
    section("排版", "左对齐 · 横排", `
      <div class="segmented three"><button class="selected">左</button><button>中</button><button>右</button></div>
      <div class="switch-row"><span>横向排版</span><span class="switch on"><i></i></span></div>
      <div class="slider-row"><span>行距</span><div class="slider"><i style="width:62%"></i><b style="left:62%"></b></div><strong>130%</strong></div>
    `),
    section("外观与效果", "填充 · 描边 · 阴影", `
      <div class="swatch-row"><span class="swatch light"></span><span>文字填充</span><strong>#F2F4F3</strong></div>
      <div class="switch-row"><span>描边</span><span class="switch"><i></i></span></div>
    `, false)
  ].join("");

  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>
    :root {
      --accent:${v.accent}; --accent-strong:${v.accentStrong}; --accent-ink:${v.accentInk};
      --bg:${v.bg}; --bar:${v.bar}; --panel:${v.panel}; --panel-alt:${v.panelAlt};
      --control:${v.control}; --hover:${v.hover}; --border:${v.border}; --border-strong:${v.borderStrong};
      --text:${v.text}; --muted:${v.muted}; --quiet:${v.quiet}; --radius:${v.radius};
      --rail:${v.rail}; --layers:${v.layers}; --inspector:${v.inspector};
    }
    * { box-sizing:border-box; }
    html,body { margin:0; width:100%; height:100%; overflow:hidden; background:var(--bg); color:var(--text); font-family:"Microsoft YaHei UI","Segoe UI",sans-serif; letter-spacing:0; }
    button { border:0; font:inherit; color:inherit; cursor:default; }
    .icon { display:block; flex:0 0 auto; }
    .app { width:1600px; height:960px; display:grid; grid-template-rows:42px 54px 36px 1fr 28px; background:var(--bg); }
    .titlebar,.commandbar,.tabs,.statusbar { background:var(--bar); border-bottom:1px solid var(--border); }
    .titlebar { display:flex; align-items:center; padding:0 13px; gap:24px; }
    .brand { display:flex; align-items:center; gap:9px; min-width:160px; font-weight:700; }
    .brand-mark { width:22px; height:22px; position:relative; }
    .brand-mark::before,.brand-mark::after { content:""; position:absolute; border-radius:2px; transform:rotate(7deg); }
    .brand-mark::before { inset:3px 2px 0 0; background:var(--accent); }
    .brand-mark::after { width:10px; height:10px; right:0; top:0; background:#f0c45b; border:2px solid var(--bar); }
    .menus { display:flex; height:100%; align-items:center; gap:2px; }
    .menus button { height:28px; padding:0 11px; background:transparent; color:var(--muted); font-size:12px; border-radius:var(--radius); }
    .window-title { margin-left:auto; display:flex; align-items:center; gap:10px; color:var(--quiet); font-size:11px; }
    .direction-pill { color:var(--accent); border:1px solid color-mix(in srgb,var(--accent) 36%,var(--border)); padding:4px 9px; border-radius:999px; background:color-mix(in srgb,var(--accent) 9%,transparent); }
    .commandbar { display:flex; align-items:center; padding:0 12px; gap:7px; }
    .command-group { display:flex; align-items:center; gap:3px; padding-right:8px; margin-right:2px; border-right:1px solid var(--border); }
    .icon-button { width:32px; height:32px; display:grid; place-items:center; background:transparent; color:var(--muted); border-radius:var(--radius); position:relative; }
    .icon-button.active { color:var(--accent); background:color-mix(in srgb,var(--accent) 12%,transparent); outline:1px solid color-mix(in srgb,var(--accent) 30%,transparent); }
    .icon-button:hover { background:var(--hover); }
    .icon-button .tooltip { display:none; }
    .command-button { height:34px; display:flex; align-items:center; gap:8px; padding:0 12px; background:var(--panel-alt); border:1px solid var(--border-strong); border-radius:var(--radius); font-size:12px; font-weight:600; }
    .command-button.primary { background:var(--accent); color:var(--accent-ink); border-color:var(--accent); margin-left:6px; }
    .command-spacer { flex:1; }
    .alignment { display:flex; align-items:center; height:34px; padding:0 5px; gap:1px; background:var(--panel); border:1px solid var(--border); border-radius:var(--radius); }
    .alignment .icon-button { width:29px; height:28px; }
    .tabs { display:flex; align-items:end; padding-left:48px; background:var(--bg); }
    .tab { height:35px; min-width:170px; padding:0 11px; display:flex; align-items:center; gap:8px; background:var(--panel); border-right:1px solid var(--border); border-top:2px solid var(--accent); font-size:11px; font-weight:600; }
    .tab .close { margin-left:auto; color:var(--quiet); }
    .add-tab { margin-left:auto; width:36px; height:34px; display:grid; place-items:center; color:var(--muted); }
    .workspace { min-height:0; display:grid; grid-template-columns:var(--rail) var(--layers) 1fr var(--inspector); }
    .toolrail { background:var(--bar); border-right:1px solid var(--border); display:flex; flex-direction:column; align-items:center; padding:10px 0; gap:6px; }
    .toolrail .icon-button { width:36px; height:36px; }
    .toolrail .spacer { flex:1; }
    .palette { width:30px; height:30px; position:relative; margin-bottom:6px; }
    .palette i { position:absolute; width:18px; height:18px; border:2px solid var(--bar); border-radius:2px; }
    .palette i:first-child { left:1px; top:1px; background:var(--accent); }
    .palette i:last-child { right:1px; bottom:1px; background:#ecebe7; }
    .layers-panel,.inspector { background:var(--panel); min-height:0; border-right:1px solid var(--border); }
    .panel-header { height:50px; padding:0 12px; display:flex; align-items:center; border-bottom:1px solid var(--border); }
    .panel-header strong { font-size:12px; }
    .panel-header span { margin-left:7px; color:var(--quiet); font-size:10px; }
    .panel-header button { margin-left:auto; width:28px; height:28px; display:grid; place-items:center; background:transparent; color:var(--muted); }
    .layer-list { padding:4px 0; }
    .layer-row { height:58px; display:grid; grid-template-columns:25px 38px 1fr 28px; align-items:center; gap:5px; padding:0 8px; border-left:2px solid transparent; }
    .layer-row.active { background:color-mix(in srgb,var(--accent) 10%,var(--panel)); border-left-color:var(--accent); }
    .visibility,.lock { display:grid; place-items:center; background:transparent; color:var(--quiet); padding:0; }
    .thumb { width:34px; height:34px; display:grid; place-items:center; background:var(--control); border:1px solid var(--border-strong); color:var(--muted); border-radius:var(--radius); }
    .text-thumb { color:var(--accent); background:color-mix(in srgb,var(--accent) 7%,var(--control)); }
    .layer-copy { min-width:0; display:flex; flex-direction:column; gap:4px; }
    .layer-copy strong { overflow:hidden; white-space:nowrap; text-overflow:ellipsis; font-size:11px; font-weight:600; }
    .layer-copy span { color:var(--quiet); font-size:9px; }
    .layers-footer { position:absolute; bottom:28px; left:var(--rail); width:var(--layers); height:42px; display:flex; align-items:center; padding:0 8px; gap:2px; background:var(--bar); border-top:1px solid var(--border); border-right:1px solid var(--border); }
    .layers-footer .icon-button { width:29px; height:29px; }
    .layers-footer .footer-spacer { flex:1; }
    .canvas-workspace { position:relative; overflow:hidden; background-color:#0b0e0f; background-image:radial-gradient(circle at 1px 1px,var(--border) 1px,transparent 1.1px); background-size:18px 18px; }
    .ruler-top { position:absolute; z-index:2; left:30px; right:0; top:0; height:22px; background:var(--bar); border-bottom:1px solid var(--border); color:var(--quiet); font:9px Consolas,monospace; display:flex; justify-content:space-around; align-items:center; }
    .ruler-left { position:absolute; z-index:2; top:22px; bottom:0; left:0; width:30px; background:var(--bar); border-right:1px solid var(--border); color:var(--quiet); font:9px Consolas,monospace; display:flex; flex-direction:column; justify-content:space-around; align-items:center; }
    .ruler-left span { transform:rotate(-90deg); }
    .canvas-stage { position:absolute; left:50%; top:51%; transform:translate(-50%,-50%); width:680px; height:760px; background:#ddd; box-shadow:0 16px 40px #0008; overflow:hidden; }
    .canvas-stage img { width:100%; height:100%; object-fit:cover; filter:saturate(.72) contrast(1.02); }
    .canvas-stage::after { content:""; position:absolute; inset:0; border:1px solid #ffffff33; pointer-events:none; }
    .canvas-badge { position:absolute; z-index:4; top:28px; left:50%; transform:translateX(-50%); background:#202728e8; color:#cbd4d1; padding:5px 11px; border-radius:999px; font:10px Consolas,monospace; box-shadow:0 3px 12px #0006; }
    .canvas-badge i { display:inline-block; width:5px; height:5px; border-radius:50%; background:var(--accent); margin-right:7px; }
    .canvas-tools { position:absolute; z-index:4; right:12px; top:31px; display:flex; padding:3px; gap:2px; background:#101516ec; border:1px solid #364143; border-radius:var(--radius); box-shadow:0 6px 18px #0006; }
    .canvas-tools .icon-button { width:31px; height:31px; color:var(--accent); }
    .selection-box { position:absolute; z-index:3; left:145px; bottom:14px; width:310px; height:76px; border:2px solid var(--accent); }
    .selection-box::before,.selection-box::after { content:""; position:absolute; width:7px; height:7px; background:#effffb; border:2px solid var(--accent); }
    .selection-box::before { left:-5px; top:-5px; }.selection-box::after { right:-5px; bottom:-5px; }
    .selection-text { position:absolute; left:8px; bottom:-14px; color:white; font-size:58px; line-height:1; font-weight:800; white-space:nowrap; }
    .inspector { border-right:0; border-left:1px solid var(--border); overflow:hidden; }
    .inspector-head { height:68px; padding:10px 12px 8px; border-bottom:1px solid var(--border); }
    .inspector-title { display:flex; align-items:center; gap:8px; }
    .inspector-title strong { font-size:13px; }.inspector-title button { margin-left:auto; background:transparent; color:var(--muted); }
    .inspector-meta { color:var(--quiet); font-size:9px; margin-top:4px; }
    .inspector-tabs { height:42px; display:grid; grid-template-columns:1fr 1fr; border-bottom:1px solid var(--border); }
    .inspector-tabs button { background:transparent; color:var(--quiet); font-size:11px; border-bottom:2px solid transparent; }
    .inspector-tabs button.active { color:var(--text); border-bottom-color:var(--accent); }
    .property-scroll { height:calc(100% - 110px); overflow:hidden; }
    .property-section { border-bottom:1px solid var(--border); }
    .property-section header { height:42px; display:flex; align-items:center; gap:8px; padding:0 12px; }
    .property-section header strong { font-size:11px; }.property-section header span { margin-left:auto; color:var(--quiet); font-size:9px; }.property-section header .icon { color:var(--quiet); }
    .property-section:not(.open) header .icon { transform:rotate(-90deg); }
    .property-section:not(.open) .section-body { display:none; }
    .section-body { padding:0 12px 12px; display:flex; flex-direction:column; gap:8px; }
    .field-row { min-height:30px; display:grid; grid-template-columns:52px 1fr; align-items:center; gap:8px; }
    .field-label { color:var(--quiet); font-size:10px; }
    .field,.select-field,.textarea { background:var(--control); border:1px solid var(--border-strong); border-radius:var(--radius); color:var(--text); }
    .field { height:30px; padding:0 8px; display:flex; align-items:center; min-width:0; font-size:10px; }
    .field small { margin-left:auto; color:var(--quiet); font-size:8px; }
    .split-fields { display:grid; grid-template-columns:1fr 1fr; gap:6px; }.split-fields .field-row { grid-template-columns:52px 1fr; }.split-fields .field-row + .field-row { grid-template-columns:0 1fr; gap:0; }
    .textarea { height:68px; padding:9px; font-size:10px; }
    .segmented { display:grid; grid-template-columns:1fr 1fr; gap:3px; padding:3px; background:var(--control); border:1px solid var(--border); border-radius:var(--radius); }
    .segmented.three { grid-template-columns:repeat(3,1fr); }
    .segmented button { height:26px; color:var(--muted); background:transparent; border-radius:calc(var(--radius) - 2px); font-size:9px; }
    .segmented button.selected { color:var(--accent); background:color-mix(in srgb,var(--accent) 12%,var(--panel)); outline:1px solid color-mix(in srgb,var(--accent) 56%,transparent); }
    .micro-row,.switch-row,.swatch-row,.slider-row,.type-row { display:flex; align-items:center; gap:8px; min-height:28px; font-size:9px; color:var(--muted); }
    .micro-row strong { color:var(--text); }.micro-row button { margin-left:auto; height:26px; display:flex; gap:5px; align-items:center; background:var(--control); border:1px solid var(--border); border-radius:var(--radius); color:var(--muted); font-size:9px; }
    .select-field { height:31px; display:flex; align-items:center; justify-content:space-between; padding:0 9px; font-size:10px; }
    .type-row .field { flex:1; }.type-toggle { width:31px; height:31px; background:transparent; color:var(--muted); border-radius:var(--radius); font-weight:700; }.type-toggle.active { color:var(--accent); background:color-mix(in srgb,var(--accent) 10%,transparent); }
    .switch-row .switch { margin-left:auto; width:34px; height:19px; border-radius:10px; background:var(--control); border:1px solid var(--border-strong); position:relative; }.switch i { position:absolute; width:13px; height:13px; border-radius:50%; left:2px; top:2px; background:var(--quiet); }.switch.on { background:var(--accent); border-color:var(--accent); }.switch.on i { left:17px; background:var(--accent-ink); }
    .slider-row .slider { flex:1; height:3px; background:var(--border-strong); position:relative; }.slider i { display:block; height:100%; background:var(--accent); }.slider b { position:absolute; top:50%; transform:translate(-50%,-50%); width:10px; height:10px; border-radius:50%; background:var(--accent); box-shadow:0 0 0 2px var(--panel); }.slider-row strong { font-size:9px; color:var(--muted); }
    .swatch { width:21px; height:21px; border-radius:3px; border:1px solid var(--border-strong); }.swatch.light { background:#f2f4f3; }.swatch-row strong { margin-left:auto; font-size:9px; }
    .statusbar { border-top:1px solid var(--border); border-bottom:0; display:flex; align-items:center; padding:0 12px; gap:14px; color:var(--quiet); font-size:9px; }
    .statusbar .ready { color:var(--muted); display:flex; align-items:center; gap:6px; }.statusbar .ready i { width:5px; height:5px; border-radius:50%; background:var(--accent); }.statusbar .zoom { margin-left:auto; display:flex; align-items:center; gap:8px; }.statusbar .zoom-line { width:92px; height:3px; background:var(--border-strong); position:relative; }.statusbar .zoom-line::after { content:""; width:10px; height:10px; border-radius:50%; position:absolute; right:22px; top:-4px; background:var(--accent); }
    .density-relaxed .app { grid-template-rows:44px 58px 38px 1fr 30px; }.density-relaxed .layer-row { height:62px; }.density-relaxed .property-section header { height:44px; }.density-relaxed .canvas-stage { width:650px; height:744px; }.density-relaxed .titlebar,.density-relaxed .commandbar { background:linear-gradient(180deg,color-mix(in srgb,var(--bar) 96%,white),var(--bar)); }
    .density-studio .workspace { grid-template-columns:var(--rail) var(--layers) 1fr var(--inspector); }.density-studio .canvas-stage { width:720px; height:770px; }.density-studio .commandbar { padding-left:16px; }.density-studio .layers-panel,.density-studio .inspector { background:color-mix(in srgb,var(--panel) 92%,transparent); }.density-studio .panel-header { height:56px; }.density-studio .layer-row { height:64px; }.density-studio .selection-box { border-color:#6de1d4; }.density-studio .selection-box::before,.density-studio .selection-box::after { border-color:#6de1d4; }.density-studio .canvas-tools .icon-button { color:#6de1d4; }
  </style></head><body class="${denseClass}"><main class="app">
    <header class="titlebar">
      <div class="brand"><span class="brand-mark"></span><span>批图王</span></div>
      <nav class="menus">${navItem("FileText", "文件")}${navItem("SlidersHorizontal", "编辑")}${navItem("Layers3", "图层")}${navItem("Frame", "画布")}${navItem("Eye", "视图")}</nav>
      <div class="window-title"><span class="direction-pill">方案 ${v.code} · ${v.name}</span><span>${v.note}</span>${icon("Settings", 15)}</div>
    </header>
    <div class="commandbar">
      <div class="command-group">${controlIcon("FilePlus2", "新建项目")}${controlIcon("FolderOpen", "打开项目")}${controlIcon("Save", "保存")}</div>
      <div class="command-group">${controlIcon("Undo2", "撤销")}${controlIcon("Redo2", "重做")}</div>
      <button class="command-button">${icon("ImagePlus", 15)}<span>新建图层</span></button>
      <div class="command-group">${controlIcon("Type", "添加文字")}${controlIcon("FolderInput", "添加素材文件夹")}${controlIcon("Box", "添加异形图层")}</div>
      <div class="alignment">${controlIcon("AlignStartVertical", "左对齐")}${controlIcon("AlignCenterVertical", "水平居中")}${controlIcon("AlignEndVertical", "右对齐")}${controlIcon("AlignStartHorizontal", "顶对齐")}${controlIcon("AlignCenterHorizontal", "垂直居中")}${controlIcon("AlignEndHorizontal", "底对齐")}</div>
      <div class="command-spacer"></div>
      ${controlIcon("Search", "预览")}${controlIcon("ListChecks", "任务记录")}
      <button class="command-button primary">${icon("SendToBack", 15)}<span>批量导出</span></button>
    </div>
    <div class="tabs"><div class="tab">${icon("FileImage", 14)}<span>未命名-1.cmp</span><span class="close">${icon("X", 13)}</span></div><button class="add-tab">${icon("Plus", 16)}</button></div>
    <div class="workspace">
      <aside class="toolrail">${controlIcon("MousePointer2", "选择工具", "active")}${controlIcon("Move", "移动工具")}${controlIcon("Type", "文字工具")}${controlIcon("Shapes", "形状工具")}<div class="spacer"></div><div class="palette"><i></i><i></i></div>${controlIcon("PanelLeftClose", "收起图层")}</aside>
      <aside class="layers-panel"><div class="panel-header"><strong>图层</strong><span>3 个</span><button>${icon("Plus", 16)}</button></div><div class="layer-list">${layerRows}</div></aside>
      <section class="canvas-workspace">
        <div class="ruler-top"><span>0</span><span>200</span><span>400</span><span>600</span><span>800</span><span>1000</span></div>
        <div class="ruler-left"><span>0</span><span>300</span><span>600</span><span>900</span><span>1200</span></div>
        <div class="canvas-stage"><img src="data:image/jpeg;base64,${productImage}"><div class="canvas-badge"><i></i>1080 × 1350 px · RGBA</div><div class="canvas-tools">${controlIcon("MousePointer2", "选择", "active")}${controlIcon("Tag", "绑定")}${controlIcon("FolderOpen", "替换素材")}${controlIcon("RefreshCw", "随机预览", "active")}</div><div class="selection-box"><div class="selection-text">限量腕表</div></div></div>
      </section>
      <aside class="inspector"><div class="inspector-head"><div class="inspector-title"><strong>限量腕表</strong><button>${icon("Ellipsis", 16)}</button></div><div class="inspector-meta">文字图层 · #2 · 已选择</div></div><div class="inspector-tabs"><button class="active">基本参数</button><button>更多参数</button></div><div class="property-scroll">${inspector}</div></aside>
    </div>
    <div class="layers-footer">${controlIcon("Plus", "新建空图层")}${controlIcon("Copy", "复制图层")}${controlIcon("Group", "创建组")}<div class="footer-spacer"></div>${controlIcon("ChevronUp", "上移")}${controlIcon("ChevronDown", "下移")}${controlIcon("Trash2", "删除")}</div>
    <footer class="statusbar"><span class="ready"><i></i>预览完成 · 296 ms</span><span>RGBA / sRGB IEC61966-2.1</span><span>X 68 · Y 1040</span><span class="zoom">${icon("ZoomOut", 13)}<i class="zoom-line"></i>${icon("ZoomIn", 13)}<strong>100%</strong></span></footer>
  </main></body></html>`;
}

async function render() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"
  });
  const page = await browser.newPage({ viewport: { width: 1600, height: 960 }, deviceScaleFactor: 1 });
  for (const variant of variants) {
    await page.setContent(html(variant), { waitUntil: "load" });
    await page.screenshot({ path: path.join(__dirname, `qml-direction-${variant.slug}.png`), fullPage: false });
  }
  await browser.close();
}

render().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
