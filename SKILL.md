---
name: daily-collage
description: "把用户上传的日常照片做成手账杂志风拼贴图。先分析照片提取视觉关键词，再在 Pinterest 按关键词搜索背景纹理和单个物件元素，元素抠图成贴纸，以用户照片为最大主视觉，分三层（背景→整图元素→抠图贴纸+主体）合成拼贴成品，并按需求配合豆包自带可画 MCP 与浏览器完成设计查询、成品上传、Magic Layers 拆层、验证和导出。当用户说『帮我做张拼贴图』『把这张照片做成拼贴』『Pinterest 拼贴』『collage』『手账风拼贴』，或上传一张日常照片并要求做成拼贴/杂志风/贴纸风时使用。"
---

# Daily Collage — 日常照片拼贴工坊

把一张日常照片变成参考图风格的手账杂志拼贴。核心原则：**用户照片是绝对主视觉（放到最大），元素由照片的视觉关键词驱动，分三层和谐叠加。**

参考风格见 `assets/style-reference.png`。

## 工作流总览

```
需求澄清（提问+5个风格参考）→ 分析照片 → 提取关键词并展示
→ 分三类搜图（背景/整图/贴纸）→ 下载 → 贴纸层元素抠图
→ 主体贴纸化（最大）→ 三层布局合成 → 检查 PNG
→ 检查豆包可画 MCP 能力 → 上传成品（本地文件默认走网页）
→ Magic Layers（无对应 MCP 时走网页）→ 检查独立图层 → 交付 PNG 与设计链接
```

默认制作 PNG，并在生成后**默认继续** Canva Magic Layers 网页流程（不需要询问）。用户已有满意的拼贴成品时，直接进入 Step 9，不重复搜图或合成。只有用户明确说"不要 Canva"或"只要 PNG"时在 Step 8 停止。

## 执行环境

脚本路径相对于本 Skill 目录解析，命令中的路径全部加引号。Python 需要 Pillow；Vision 抠图需要 macOS 和可用的 PyObjC Vision/Quartz 桥接。先检查现有运行环境，不把某台机器的绝对路径写成用户必需条件。

本 Skill 优先适配豆包：可画连接器/MCP 做其已支持的设计操作，豆包浏览器补齐本地上传和 Magic Layers。进入可画阶段先读 [references/doubao-canva-mcp.md](references/doubao-canva-mcp.md)。使用当前会话实际工具清单与参数 schema，不要求用户安装另一套 MCP、申请开发者 API 或提供令牌。

网页操作使用豆包当前提供的浏览器/电脑工具。若有 `browser-use-automation-mac`，先读取它，再使用其文档化的 `mac_computer_use_tool`、`plane="bu"` 等接口；没有该技能时使用宿主实际提供的等价工具。需要登录接管时，只有宿主提供了 `interaction.request_action` 才按其 schema 调用。图片查看和文件交付优先使用豆包实际提供的 `Read`、`present_files` 或等价工具。其他宿主使用其自身可用工具，不把 Codex 工具名当成豆包依赖。


---

## Step 1 — 需求澄清（生成前必问）

在分析照片和搜图之前，先用 `interaction.ask` 向用户提出以下问题，一次性问完。这一步不是可选项——明确主题和元素方向能避免返工。

### 必问问题

**问题 1：这张拼贴画想表达什么主题或情绪？**
- 例如：旅行回忆、日常治愈、复古文艺、都市潮流、学术氛围、节日纪念、自我表达等
- 用户可以用一句话描述，也可以给几个关键词

**问题 2：希望加入哪些特定元素？**
- 可以是地点（如"大同古建筑""海边"）、物件（如"咖啡杯""书本""相机"）、氛围词（如"阳光感""怀旧"）
- 如果用户没有特定要求，说明会根据照片关键词自动选择

**问题 3：风格偏好（5 选 1，可补充说明）**

| 选项 | 风格名称 | 特点 | 典型元素 |
|---|---|---|---|
| A | 复古手账风 | 暖色调、做旧纸张、手写感、温柔怀旧 | 旧信纸、乐谱、干花、邮票、胶带 |
| B | 杂志拼贴风 | 大胆撞色、几何切割、潮流感、视觉冲击 | 潮流单品、英文剪报、色块、几何图形 |
| C | 自然治愈风 | 柔和色调、绿植阳光、棉麻质感、清新 | 树叶、花朵、阳光光斑、棉麻布、木纹 |
| D | 暗黑艺术风 | 深色背景、金属质感、神秘氛围、高级感 | 黑胶唱片、金属饰品、烟雾、复古钥匙 |
| E | 旅行记忆风 | 地标建筑、交通票据、地图、纪念品 | 古建筑、车票、明信片、指南针、钱币 |

### 执行要点

- 用 `interaction.ask` 一次性提出 3 个问题，风格题用选择题，前两题用自定义输入
- 用户回答后，结合照片内容和用户需求，在 Step 2 提取关键词时融入用户指定的主题和元素
- 如果用户跳过某个问题，用照片分析结果作为默认方向，并在关键词展示时说明
- 用户选择风格后，在搜图时优先匹配该风格的元素和背景

---

## Step 2 — 分析照片并提取关键词

先读取 [references/image-quality.md](references/image-quality.md)，确认原图路径和真实尺寸。视觉预览仅用于分析，合成必须直接读取上传附件原文件；禁止用预览截图、缩略图或 AI 重画版代替原图。

先用 `Read` 打开用户照片，结合 Step 1 中用户指定的主题、元素和风格偏好，从以下维度提取 **3-5 个视觉关键词**，用简洁的中文+英文展示给用户：

- **材质/质感**：丝绸、缎面、棉麻、皮革、透明、金属、木质……
- **环境元素**：绿树、阳光、光影、海水、砖墙、花窗、雪地、霓虹灯……
- **服装颜色**：酒红、米白、墨绿、藏蓝、鹅黄……
- **氛围**：复古、清新、暗黑、少女、学术、度假、都市……
- **物件**：咖啡杯、书本、耳机、花束、钥匙、相机……

展示格式示例：
> 从照片中提取的关键词：**绿树 / 阳光光影 / 酒红丝绸 / 中式花窗 / 米白棉麻**
> 基于这些关键词，我会去 Pinterest 找对应元素。

如果用户对关键词有修改意见，先调整再继续。否则直接进入下一步。

## Step 3 — 按关键词分三类搜图

读 `references/keyword-bank.md`，把关键词转成英文搜索词，分三类：

### A. 背景层（1 张，整图铺满，不抠图）
从 Pinterest 搜索一张和照片氛围匹配的大尺寸背景图，铺满整个画布做最底层。
- 关键词示例：`vintage paper texture`, `old wall texture`, `sunlight shadow texture`, `fabric texture`
- 选择标准：色调和照片协调、纹理不过于抢眼、尺寸够大
- 在布局 JSON 中用 `"background_image": "bg.jpg"` 指定，脚本会自动 cover 铺满

### B. 整图层（1-2 张，整图不抠图）
大尺寸纹理/纸张/乐谱，做中层铺垫。
- 关键词示例：`vintage paper texture`, `old sheet music`, `handwritten letter`, `newspaper texture`
- 特点：满版纹理，放在四角做底层元素

### C. 贴纸层（3-4 张，单个物件，需要抠图）
和照片关键词对应的单个物件，抠图后做成透明底贴纸。
- 关键词示例：`green leaf png`, `sunlight flare png`, `vintage key png`, `dried flower png`, `butterfly sticker`
- 特点：单品为主，背景简单，便于抠图

总共收集 **5-7 张**（1 背景 + 1-2 整图 + 3-4 贴纸）。

## Step 4 — Pinterest 搜索与下载

使用当前环境的浏览器工具浏览 Pinterest，不写爬虫。

1. 对英文关键词进行 URL 编码，打开 `https://www.pinterest.com/search/pins/?q=<编码后的关键词>`。
2. 查看实际图片，进入合适的 Pin 检查大图，选择与照片色调协调的素材。
3. 工具若支持文档化的页面 DOM 读取，可从该图的 `srcset` 选最大宽度候选；不要凭空改写 CDN 地址或把搜索缩略图冒充原图。若只有原生 UI，用图片保存或下载菜单。
4. 登录受阻时请用户完成登录；用户跳过后记录阻塞，不循环弹出同一请求。
5. 通过工具真实返回的下载路径找到文件，移动到本次 `collage_work/`。用 Pillow 检查能否打开、尺寸是否够用；HTML 错误页不能按图片交付。
6. 在工作目录保存 `sources.json`：每项记录关键词、Pin 页面地址、实际下载地址（若可见）、本地文件路径。不要记录 Cookie 或令牌。

## Step 5 — 贴纸层元素抠图

对 C 类（单个物件）元素，用 `scripts/make_sticker.py` 抠图并加白边：

```bash
python3 <skill_dir>/scripts/make_sticker.py \
  --input element_raw.jpg \
  --mode object \
  --output sticker_element.png \
  --border 8 \
  --shadow
```

**非人物元素的抠图**：脚本会尝试 macOS Vision 的通用前景分割（`VNGenerateForegroundInstanceMaskRequest`），失败则降级 rembg，再失败则用圆角相框模式。

A 类背景和 B 类整图元素**不抠图**，保留整图。抠图降级成圆角矩形时，必须告知并换素材或重做，不能把兜底结果当作透明物件贴纸。

## Step 6 — 主体贴纸化（放到最大）

```bash
python3 <skill_dir>/scripts/make_sticker.py \
  --input user_photo.jpg \
  --mode person \
  --output sticker_subject.png \
  --border 14 \
  --shadow
```

主体优先突出，但必须按抠图后可见区域的真实像素安排尺寸。目标宽度一般占画布 **55-70%**；像素不足时降低主体尺寸、缩小最终画布或换近景原图，不强制放大。

## Step 7 — 三层布局合成

### 6.1 分层原则

| 层级 | z 值 | 内容 | 说明 |
|---|---|---|---|
| 背景层 | 0 | Pinterest 背景图铺满 | 从 Pinterest 搜和照片氛围匹配的背景纹理（`background_image` 字段），cover 铺满；搜不到则纯色兜底 |
| 整图层 | 1-5 | B 类整图元素（纸张/乐谱） | 大尺寸，做底层铺垫，可部分超出画布 |
| 贴纸层 | 6-9 | C 类抠图元素（单个物件） | 中小尺寸，错落分布，和主体有互动 |
| 主体层 | 10 | 用户照片贴纸 | **最大**，居中，绝对焦点 |

### 6.2 布局要点

- **主体**：宽度 1200-1500px（2160 宽画布），居中略偏上，rotation ±2°
- **整图元素**：宽度 800-1100px，放在四角，rotation ±5-10°，部分被主体遮挡
- **贴纸元素**：宽度 240-500px，散落在主体周围和空隙处，rotation ±10-15°，有大有小
- **投影只加一次**：已通过 `make_sticker.py --shadow` 加过投影的 PNG 在布局中设 `shadow: false`，整图素材可设 `true`。
- 贴纸元素可以与主体边缘重叠并被主体遮挡（z<10），增加层次感

### 6.3 写布局 JSON 并合成

```json
{
  "canvas": {"width": 2160, "height": 2880},
  "background": "#F5F0E8",
  "background_image": "bg_paper.jpg",
  "elements": [
    {"path": "element_music.jpg", "x": 1700, "y": 600, "width": 760, "rotation": 7, "shadow": true, "z": 2},
    {"path": "sticker_flower.png", "x": 400, "y": 1960, "width": 520, "rotation": 8, "shadow": false, "z": 6},
    {"path": "sticker_key.png", "x": 1740, "y": 2000, "width": 400, "rotation": -12, "shadow": false, "z": 7},
    {"path": "sticker_subject.png", "x": 1080, "y": 1320, "width": 1440, "rotation": -2, "shadow": false, "z": 10}
  ]
}
```

`background_image` 会被脚本自动缩放铺满画布（cover 模式），作为最底层。`background` 是兜底色，未指定背景图时使用。指定的背景文件损坏或缺失时应修复路径，或明确移除该字段后再重跑。

```bash
python3 <skill_dir>/scripts/compose_collage.py \
  --config layout.json \
  --output collage_final.png
```

## Step 8 — 验证与交付

1. `Read` 成品检查：主体是否最大最突出（按可见人物而非透明 PNG 画幅判断）？元素抠图是否干净？三层是否有层次？色调是否协调？
2. 不满意则调整布局重跑，最多迭代 2-3 次。
3. 检查 `*.quality.json` 的原图尺寸、有效抠图尺寸和缩放倍率。脚本默认拒绝放大或缺失元素；先修复再重跑。完整验证流程见 `references/image-quality.md`。
4. 用宿主文件展示工具交付，文件名 `collage_<主题>.png`；然后**默认继续 Step 9** 上传 Canva Magic Layers，不需要询问用户。只有用户明确说"不要 Canva 版"或"只要 PNG"时才跳过。

---

## Step 9 — 上传 Canva Magic Layers（默认执行，不询问）

**这是默认步骤**：每次生成拼贴图后，必须上传到 Canva 并用 Magic Layers 拆层为可编辑设计，不需要询问用户是否需要。只有当用户明确说"不要 Canva 版"或"只要 PNG"时才跳过。

本地 PNG 是保真母版，Canva/AI 拆层结果另存为派生版本，不能覆盖本地母版，也不能宣称保留了原始像素。

先读取 [references/doubao-canva-mcp.md](references/doubao-canva-mcp.md)，根据当前连接器能力选择步骤。需要网页时再读 [references/canva-web.md](references/canva-web.md)。MCP 已支持的查询、读取、导出优先用 MCP；不支持的上传或 Magic Layers 自动衔接网页，不把缺少单个工具视为整条流程失败。用户只允许纯 MCP 时尊重该限制，说明缺失能力，不擅自使用网页。沿用用户已授权的站点、账号和成品。

交付必须区分：本地 PNG 完成、网页上传完成、Magic Layers 处理中、已验证独立图层。只有实际检查可编辑元素后才说拆层完成。若被登录、账号权益或功能入口阻塞，保留 PNG 与当前设计链接，说明具体卡点及恢复步骤。

## 关键约束

- **高清优先（强制）**：所有照片保持原始分辨率，禁止用 `sips -Z` 缩小到1600px；画布默认 **2160×2880**（2倍于1080×1440）；背景必须满足 cover 实际所需尺寸（同时检查宽高），不能用固定的“≥1000px宽”代替检查。
- **Pinterest 必须用当前可用的浏览器工具**，不要写爬虫，不要用 image_search 代替。
- **关键词必须先展示给用户**，这是流程的一部分，不是可选项。
- **主体优先突出**：在有效像素足够时占画布 55–70%；禁止为满足比例而无提示放大。
- **贴纸层元素必须抠图**：不能用矩形图直接贴在最上层。
- **元素图必须下载到本地**再合成。
- **macOS 优先用 Vision 抠图**：人物用 `VNGeneratePersonSegmentationRequest`，物件用 `VNGenerateForegroundInstanceMaskRequest`。remove.bg 可作为备选（需浏览器操作，可能遇到 hCaptcha 人机验证）。
- **不要在拼贴里加文字**，手写文字应由元素图自带。
- **工作目录**：中间文件放 `collage_work/`，成品放项目根目录。
- **Canva Magic Layers 是默认步骤**：生成 PNG 后必须上传 Canva 并拆层，不询问用户；只有用户明确说"不要 Canva"才跳过。本地 PNG 保留为保真母版，Canva 拆层为派生版本。
- **合成脚本已用 LANCZOS/BICUBIC 高质量插值**，不要改成默认插值。
