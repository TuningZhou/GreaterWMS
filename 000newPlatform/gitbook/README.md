# DMXSmart 帮助中心 · GitBook 项目

本目录包含从 [help.dmxsmart.com](https://help.dmxsmart.com/) 同步的 WMS、TMS、打单系统和 Y2 使用手册，可直接通过 GitBook 的 Git Sync 导入并发布。

## 目录说明

- `docs/`：GitBook 实际发布内容。
  - `README.md`：帮助中心首页。
  - `SUMMARY.md`：完整侧边栏导航。
  - `.gitbook.yaml`：空间内容配置。
  - `wms/`、`tms/`、`printer/`、`y2/`：四套手册的 Markdown 页面。
  - `.gitbook/assets/`：本地化的图片与附件，按 URL 哈希去重。
- `gitbook-docs.yaml`：GitBook 站点与 `docs/` 目录的映射配置。
- `scripts/sync_help_center.py`：页面、侧边栏、图片和链接同步脚本。
- `sync-report.json`：最近一次同步的页面清单、资源清单和校验结果。

`README.md`、`SUMMARY.md` 以及各级分类中的 `README.md` 是生成的导航页；其余 Markdown 页面与源站页面一一对应，文件末尾保留源页面地址注释。

## 更新帮助中心

在 PowerShell 中执行：

```powershell
cd 'd:\000 Download Area\000 xCode\GreaterWMS\000newPlatform\gitbook'
python -m pip install -r requirements.txt
python scripts/sync_help_center.py
```

脚本会重新读取源站 sitemap 和侧边栏，下载新增或变化的资源，重写内部链接，并校验页面覆盖、导航和本地资源。资源使用 SHA-256 和文件大小判断是否变化；重复执行会更新 `docs/` 中由脚本生成的内容，并清理上一轮生成但源站已删除的页面和资源。

资源主机白名单包含帮助中心及其当前图片 CDN。若未来增加其他可信 CDN，可通过环境变量 `HELP_CENTER_ALLOWED_ASSET_HOSTS` 追加，多个主机用英文逗号分隔。

仅检查本地项目、不访问网络：

```powershell
python scripts/sync_help_center.py --verify-only
```

## 本地预览

在项目根目录执行：

```powershell
npm run preview
```

然后访问 <http://localhost:4000/>。修改 `docs/` 下的 Markdown 后，本地预览会自动重新加载。

本地预览使用根目录 `book.json` 和已弃用的 GitBook 3.2.3 渲染器，主要用于检查正文、侧边栏、链接和图片；它的界面与当前 GitBook 云端并不完全一致。由于旧渲染器无法在 Node 16 及以上版本正常安装，预览命令通过 `npx` 临时使用 Node 10，仅用于本地测试，不参与线上发布。

如需生成静态 HTML 检查产物，可执行 `npm run preview:build`，输出目录为 `_preview/`。

## 一键发布到 GitBook

1. 将本项目推送到 GitHub 或 GitLab。如果只把 `gitbook` 目录作为独立仓库，直接推送该目录；如果推送整个 GreaterWMS 仓库，请保留 `000newPlatform/gitbook/` 路径。
2. 在 GitBook 中创建站点，选择 **Sync with Git**，安装 GitHub Sync 或 GitLab Sync。
3. 选择仓库和分支。整个 GreaterWMS 仓库的 **Project directory** 填写 `000newPlatform/gitbook`；独立仓库则留空。
4. 同步方向选择 **GitHub/GitLab → GitBook**。GitBook 会根据根目录的 `gitbook-docs.yaml` 将 `docs/` 导入“帮助中心”空间。
5. 在 GitBook 中预览后点击 **Publish**。后续提交并合并到同步分支即可更新线上文档。

图片已经下载到本地，发布时不依赖原站图床。脚本不会登录 GitBook，也不会代替执行账号授权和最终发布。

## 技术说明

源站使用 Docusaurus，因此本项目在本地将其 HTML 正文转换为 GitBook Markdown。发布配置采用 GitBook 当前的 Git Sync 标准：`gitbook-docs.yaml`、`.gitbook.yaml` 和 `SUMMARY.md`。`GitbookIO/gitbook` 中的旧版 CLI 已弃用，不需要安装旧 CLI 即可完成托管发布。
