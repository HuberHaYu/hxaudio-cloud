# 维护说明

本仓库的数据分为两类：人工维护的源文件，以及由工具生成、不应手动修改的文件。推送到 `main` 后，GitHub Actions 会自动完成校验、生成和 CDN 缓存刷新。

## 目录结构

| 路径 | 类型 | 内容 |
| --- | --- | --- |
| `presets/<id>/meta.json` | 人工维护 | 标题、说明、标签、适用设备 |
| `presets/<id>/<id>.hx4` | 人工维护 | 预设本体，由 App 导出 |
| `cloud.config.json` | 人工维护 | 目录名称、公告、GitHub 登录 Client ID、下载线路 |
| `ratings/<id>.json` | 自动写入 | 每个预设的匿名投票记录 |
| `api/v1/manifest.json` | 自动生成 | 目录入口：版本、公告、评分配置 |
| `api/v1/index.json` | 自动生成 | 预设列表、曲线预览、评分汇总 |
| `api/v1/manifest.sig` | 自动生成 | manifest 的签名，由 Actions 使用仓库 Secret 生成 |
| `keys/manifest-signing-public.pem` | 固定 | 验签公钥，与 App 内置的一致 |
| `README.md` 预设列表 | 自动生成 | `presets:start` 与 `presets:end` 标记之间的表格 |
| `.github/ISSUE_TEMPLATE/rating.yml` | 自动生成 | 评分表单，选项随预设同步 |
| `scripts/` | 工具 | `hxcloud.py`（校验、生成、评分）与 CI 辅助脚本 |
| `.github/workflows/` | 自动化 | 构建目录、处理评分 |

## 添加或更新预设

### 命令行

使用 App 导出的 `.hx4` 文件。工具会移除 `devices` 数组、按频率整理 PostEQ 控制点，并生成 `meta.json`：

```bash
python3 scripts/hxcloud.py add ~/Downloads/导出.hx4 --id warm-vocal \
  --title "温暖人声" --subtitle "有线耳机 · 抒情" --tags "人声,温暖" --kinds WIRED_ANALOG,WIRED_USB
git add -A && git commit -m "新增预设 warm-vocal" && git push
```

只替换曲线、保留说明文字：

```bash
python3 scripts/hxcloud.py add 新版.hx4 --id warm-vocal --replace
```

### 网页

1. *Add file → Create new file*，文件名填 `presets/warm-vocal/meta.json`（输入 `/` 会创建文件夹），写入元数据后提交
2. 进入该文件夹，*Add file → Upload files*，上传已重命名为 `warm-vocal.hx4` 的文件

App 保存过多个设备的调音时，导出文件会包含 `devices` 数组，网页上传的文件会因此校验失败。需要先删除该字段，或改用命令行导入。

### 规则

- 预设 ID 即文件夹名：小写字母、数字、连字符，3–48 个字符。发布后不应修改，评分与 App 本地缓存都以它为主键
- 每个预设文件夹只包含 `meta.json` 和 `<id>.hx4`
- `revision`、`created`、`updated` 由构建自动推导：文件内容每变化一次，`revision` 加 1
- 校验失败时，Actions 中「构建目录」会标红并列出具体原因，目录保持上一个有效版本

### `meta.json` 字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `title` | 是 | 不超过 24 个字符 |
| `author` | 是 | 不超过 32 个字符 |
| `subtitle` | 否 | 不超过 40 个字符，用作列表副标题 |
| `description` | 否 | 不超过 600 个字符 |
| `tags` | 否 | 最多 8 个，每个不超过 12 个字符 |
| `device_kinds` | 否 | `SPEAKER` `WIRED_ANALOG` `WIRED_USB` `BLUETOOTH` `OTHER`；为空表示通用 |
| `target_devices` | 否 | 适配机型，最多 20 个：`{"kind": "BLUETOOTH", "name": "WH-1000XM5", "aliases": ["WH1000XM5"]}` |
| `featured` | 否 | 为 `true` 时列为精选 |

### 适配机型

App 里的「适合当前设备」只列出标注了当前型号的预设：

- 手机外放：`kind` 为 `SPEAKER`，`name` 填手机市场名（如 `Xiaomi 15`），型号代码（如 `24129PN74C`）放进 `aliases`
- 蓝牙 / USB 耳机：`name` 填系统报告的产品名（如 `WH-1000XM5`）；4 个字符以上的名称也能匹配用户改过名的蓝牙耳机
- 3.5mm 耳机无法识别型号，不参与匹配
- 投稿邮件里会自动附带投稿人手机识别到的型号与输出设备名

可以在 HXCloud 中编辑，或命令行 `add` 时使用 `--model BLUETOOTH:WH-1000XM5,WH1000XM5`（可重复）。

## 评分

| 入口 | 触发方式 | 投票人标识 |
| --- | --- | --- |
| App | 云端页登录 GitHub 后在预设详情中评分 | GitHub 账号 |
| Issue 表单 | Issues →「⭐ 给预设评分」 | GitHub 账号 |
| 手动测试 | Actions →「评分（App 接口）」→ Run workflow | 触发者账号 |

每个账号对同一预设只保留最后一票。

### 开放 App 内评分（一次性设置）

App 通过一个 GitHub App 登录，它只有在本仓库提交 issue 的权限：

1. GitHub → Settings → Developer settings → GitHub Apps → **New GitHub App**
   - GitHub App name：任取一个未被占用的名字，例如 `HXAudio Pro Cloud`（授权页会显示它）
   - Homepage URL：`https://github.com/HuberHaYu/hxaudio-cloud`
   - Callback URL 留空；**不勾选** Expire user authorization tokens；**勾选 Enable Device Flow**
   - Webhook：取消勾选 Active
   - Permissions → Repository permissions → **Issues：Read and write**（其余保持 No access）
   - Where can this GitHub App be installed：**Any account**（其他用户才能授权登录）
2. 创建后，在应用页面左侧 **Install App** → 安装到 `HuberHaYu` → Only select repositories → `hxaudio-cloud`
3. 复制应用页面上的 **Client ID**（形如 `Iv23li…`，不是 App ID，也不需要 Client secret），在 HXCloud 的「目录设置」中填入并保存；或写入 `cloud.config.json` 的 `rating.github_client_id` 后推送

保存后 Actions 会把它写入签名后的 manifest，App 同步后即出现 GitHub 登录与评分。

仓库初始包含测试评分（`via: seed`），正式发布前应清除：

```bash
python3 scripts/hxcloud.py purge-seed && git add -A && git commit -m "清除测试评分" && git push
```

## 签名

GitHub Actions 每次生成 manifest 后都会自动签名（`scripts/sign_manifest.sh`），添加预设、修改配置、收到评分都不需要任何额外操作。

- 私钥保存在仓库 Secret `HXCLOUD_SIGNING_KEY`；本地备份在仓库目录之外，不应提交到任何仓库
- 公钥在 `keys/manifest-signing-public.pem`，与 App 内置的公钥是同一把
- 「构建目录」报错“没有签名私钥”时，说明 Secret 丢失：在 Settings → Secrets and variables → Actions 中用本地备份重新创建即可
- 更换密钥需要同时发布内置新公钥的 App，否则旧版 App 会拒绝新签名的数据

## 下载线路

`cloud.config.json` 的 `mirrors` 决定 App 使用哪些线路。某条线路失效时，把它的 `enabled` 改为 `false` 并推送；新增线路追加一项即可。App 在下一次成功同步后生效，不需要发布新版本。

## 公告

修改 `cloud.config.json` 中的 `notice` 并推送。内容会写入 `manifest.json`，由 App 在「云端」页面顶部显示；为空时不显示。

## 常用命令

```bash
python3 scripts/hxcloud.py validate      # 仅校验，不写文件
python3 scripts/hxcloud.py build         # 校验并重新生成全部生成物
python3 scripts/hxcloud.py build --check # 生成物不是最新时返回失败
python3 scripts/hxcloud.py rate studio-reference 5 --voter manual:me
python3 scripts/hxcloud.py purge-seed    # 清除测试评分
```

评分会持续产生新的提交，本地修改前先执行 `git pull`。
