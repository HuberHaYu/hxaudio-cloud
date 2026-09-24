# HXAudio Pro 云端预设

HXAudio Pro「云端」页面的**纯数据仓库**：只存预设文件和评分，全部是静态 JSON，由 App 通过 CDN 读取，**不需要任何服务器**。
所有展示与交互都在 App 内完成，仓库本身不提供任何页面。
仓库公开只是为了让 App 能免鉴权访问；写入权限只在维护者手里，所有生成物由 GitHub Actions 自动维护。

## 访问地址

把 `<用户名>` 换成你的 GitHub 用户名：

| 用途 | 地址 |
| --- | --- |
| 目录入口（jsDelivr，App 首选） | `https://cdn.jsdelivr.net/gh/<用户名>/hxaudio-cloud@main/api/v1/manifest.json` |
| 预设列表 + 评分 | `https://cdn.jsdelivr.net/gh/<用户名>/hxaudio-cloud@main/api/v1/index.json` |
| GitHub 原始地址（备用） | `https://raw.githubusercontent.com/<用户名>/hxaudio-cloud/main/api/v1/index.json` |

## 目录结构

```
presets/<id>/meta.json          标题、简介、标签、适用设备       ← 你只需要维护这里
presets/<id>/<id>.hx4           App 导出的配置文件
cloud.config.json               全局配置：目录名、公告、评分接口地址

ratings/<id>.json               每个预设的投票记录（匿名，自动写入）
api/v1/manifest.json            App 的入口：版本、公告、评分开关（自动生成）
api/v1/index.json               预设列表 + 曲线预览 + 评分汇总（自动生成）
.github/ISSUE_TEMPLATE/rating.yml  评分表单，下拉选项随预设自动更新

scripts/hxcloud.py              校验 / 构建 / 评分工具（零依赖）
.github/workflows/              自动构建目录、处理评分
relay/cloudflare-worker/        第二阶段：App 内评分的中转服务
docs/API.md                     App 对接协议
docs/SETUP.md                   GitHub 首次配置步骤
```

## 添加或更新预设

**命令行（推荐）**——直接用 App 导出的 `.hx4`，工具会自动去掉 `devices` 数组并生成 `meta.json`：

```bash
python3 scripts/hxcloud.py add ~/Downloads/我的调音.hx4 --id warm-vocal \
  --title "温暖人声" --subtitle "有线耳机 · 抒情" --tags "人声,温暖" --kinds WIRED_ANALOG,WIRED_USB
git add -A && git commit -m "新增预设 warm-vocal" && git push
```

只换曲线、保留介绍：`python3 scripts/hxcloud.py add 新版.hx4 --id warm-vocal --replace`。
`revision`、`created`、`updated` 全部自动推导——文件内容变化即 `revision + 1`。

**网页操作**——在 GitHub 上 *Add file → Create new file*，文件名输入 `presets/warm-vocal/meta.json`（输入 `/` 会自动建文件夹），
提交后进入该文件夹，*Add file → Upload files* 上传事先在电脑上改好名的 `warm-vocal.hx4`。
Actions 会自动校验并重建目录，失败时 Actions 页面显示红叉和具体原因。
注意：App 记住过多个设备时，导出文件里会带 `devices` 数组，网页上传会被拒绝——删掉该字段，或改用上面的命令行。

`meta.json` 字段：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `title` | ✓ | ≤ 24 字 |
| `author` | ✓ | ≤ 32 字 |
| `subtitle` | | ≤ 40 字，列表副标题 |
| `description` | | ≤ 600 字 |
| `tags` | | 最多 8 个，每个 ≤ 12 字 |
| `device_kinds` | | `SPEAKER` `WIRED_ANALOG` `WIRED_USB` `BLUETOOTH` `OTHER`，留空表示通用 |
| `featured` | | `true` 时 App 可置顶展示 |

预设 ID（文件夹名）只能用小写字母、数字、连字符，3–48 位，**发布后不要改**——评分和 App 的本地缓存都按它关联。

## 评分

- **现在就能用**：Issues → New issue →「⭐ 给预设评分」。机器人自动记票、回复并关闭 issue。每个 GitHub 账号对每个预设一票，重投覆盖。
- **维护者测试**：Actions →「评分（App 接口）」→ Run workflow，填预设 ID 和分数。
- **App 内评分（第二阶段）**：部署 `relay/cloudflare-worker`，把地址填进 `cloud.config.json` 的 `rating.submit_endpoint`。见 [docs/API.md](docs/API.md)。

内置的 18 条测试评分标记为 `via: seed`，正式上线前运行 `python3 scripts/hxcloud.py purge-seed` 后推送即可清除。

## 常用命令

```bash
python3 scripts/hxcloud.py validate          # 只校验
python3 scripts/hxcloud.py build             # 本地重建 api/v1（推送后 Actions 也会做）
python3 scripts/hxcloud.py rate studio-reference 5 --voter manual:me
python3 scripts/hxcloud.py purge-seed        # 清除测试评分
```
