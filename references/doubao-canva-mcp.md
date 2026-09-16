# 豆包自带可画 MCP 适配

## 能力发现

使用豆包当前会话已经连接的可画 MCP，不安装替代连接器，不读取凭证文件。下表名称是发现线索，可能以 `mcp__canva__search_designs` 等形式出现；只调用当前真正可用的工具，参数以其 schema 为准，不能自行拼出工具名或猜参数。

| 能力 | 工具名线索 | 使用时机 |
|---|---|---|
| 搜索设计 | search-designs / search_designs | 用户指定已有设计名称、需要寻找续跑设计时 |
| 读取设计与页面 | get-design、get-design-pages、get-design-content | 已有 design_id 时读取标题、页面和访问权限 |
| 复制设计 | copy-design | 用户要基于某个已有设计制作副本时；不为连通性测试复制无关设计 |
| URL 资产上传 | upload-asset-from-url | 已有外部服务可取回的成品图片 URL 时 |
| 编辑事务 | start-editing-transaction、perform-editing-operations、commit-editing-transaction、cancel-editing-transaction | schema 明确支持所需操作、已取得真实 page_id/asset_id 等字段时 |
| 导出 | get-export-formats、export-design | 用户需要网页处理后的本地导出文件时 |

先检查工具清单。仅当有具体目标设计时做最小只读调用；不要无目的遍历用户全部设计。连接器不存在或授权失效不妨碍已授权网页流程，记录原因后继续网页，不反复要求连接。

## 路由

### 用户已有设计链接

从用户链接或断点取 design_id（结构不明确时用现有工具解析，不猜）。优先通过 MCP 读取；工具返回编辑 URL 时保存原值，然后用豆包浏览器打开同一设计。先确认图片是否已经上传、是否已拆层，不重复生成。

### 输入只有本地 PNG/JPEG

- 如果当前 MCP 明确提供本地文件上传，按实际 schema 使用；不要假设 `upload-asset-from-url` 接受本地路径、file:// 或 base64。
- 仅有 URL 上传工具时，默认按 `canva-web.md` 直接上传本地成品，并从网页取得设计链接。无需为使用 MCP 而人为创建图床或调用 FileBatchUpload。
- 用户已提供可用成品 URL 时才考虑 URL 上传。检查跟随重定向后的 GET 响应为成功图片且无需当前浏览器 Cookie；仍不能保证 Canva 服务器可达，以工具结果为准。失败一次后查看原因，改走本地网页上传，不重复提交同一失效链接。
- 取得 asset_id 只代表资产入库，不代表创建了设计或完成拆层。若没有可用的空白设计创建工具，在网页按图片比例创建；不要改用文生设计重画原图。优先在网页上传库选择已上传资产，避免再传一份。

### Magic Layers

当前工具没有明确声明图片拆层能力时，直接用豆包网页“编辑 → AI图层 / AI可编辑图层”。不向 `perform-editing-operations` 填入猜测的 `magic_layers` 操作，不用“调整图层”面板或 `insert_fill` 冒充拆层。

如果未来 MCP 明确支持 Magic Layers，核对输入、额度提示、异步状态和输出设计后使用真实 schema；仍按网页验证要求检查至少两个独立元素。用户明确指定走网页时优先遵循其选择。

## MCP 与网页交接

在 `collage_work/canva-state.json` 的原字段基础上可添加：

```json
{
  "mcp_status": "available",
  "route": "mcp_and_browser",
  "design_id": null,
  "asset_id": null,
  "transaction_id": null,
  "browser_url": null
}
```

这是本地进度字段，不是任何 MCP 的入参模板。ID 仅在工具实际返回或页面明确给出后填写。`mcp_status` 可为 available/unavailable/auth_required/error；`route` 按本次实际使用方式记录 mcp_and_browser/browser/mcp。

- MCP OAuth 登录与浏览器登录独立，豆包浏览器与 Chrome 也可能不同。网页打开同一设计无权限时保留链接，说明需要登录该设计所属账号；不要复制到不明账号来绕过权限。
- 页面和 MCP 的站点、设计 ID 必须一致；不能将 canva.com 设计 ID 直接用于 canva.cn。
- 使用编辑事务时，成功后提交再进入网页；出错则使用真实 transaction_id 取消草稿并读取确认。未确认事务结束时不在网页同时修改同一设计。提交超时先读取状态，避免重复执行。
- 网页拆层和保存完成后，MCP 如可读取同一设计，可辅助核对内容或按用户需求导出。MCP 暂时读不到网页设计时，保留网页结果与原始 PNG，不重复拆层，也不把 MCP 读取失败说成网页处理失败。
- 导出前查看支持格式；有异步任务就按工具说明等待并下载最终结果。浏览器和 MCP 都不能导出时，交付已有 PNG 与设计链接，说明未取得拆层后导出图。

## 完成判定

只有 `layers_verified` 才代表已验证拆层。MCP 搜索成功、上传成功、复制成功、事务提交成功均不能替代拆层验证。最终只描述本次实际使用了哪些能力；不得说“豆包 MCP 实测通过”，除非这次确实在豆包连接器中成功执行过。

适配依据：用户提供的豆包工具调用记录与 [Canva 官方 MCP 清单](https://www.canva.dev/docs/mcp/tools/)。这份 Skill 定义调用与交接规则，本身不会给连接器新增 API。
