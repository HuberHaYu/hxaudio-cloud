# GitHub 首次配置

整个过程约 10 分钟，只需要做一次。

## 1. 建空仓库

打开 <https://github.com/new>：

- Repository name：`hxaudio-cloud`（换名字的话，App 里的基础地址要跟着改）
- 选 **Public**
- **不要**勾选 Add a README / .gitignore / license——保持空仓库
- Create repository

## 2. 上传

### 方式 A：命令行（推荐，最不容易漏文件）

```bash
cd ~/Downloads && unzip hxaudio-cloud.zip && cd hxaudio-cloud
git init -b main
git add -A
git commit -m "初始化云端预设仓库"
git remote add origin https://github.com/<用户名>/hxaudio-cloud.git
git push -u origin main
```

推送时要求输入密码的话，GitHub 不接受账号密码，要填 **Personal access token**：
Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token，
勾选 `repo` 和 **`workflow`**（没有 `workflow` 权限会推不上 `.github/workflows/`），把生成的令牌当密码粘贴进去。

不想碰令牌也可以用 [GitHub Desktop](https://desktop.github.com)：File → Add local repository 选解压出的文件夹 → Publish repository，取消勾选 “Keep this code private”。

### 方式 B：网页拖拽

在空仓库页面点 “uploading an existing file”，把解压后文件夹里的**所有内容**拖进去。
macOS 访达默认隐藏 `.github`、`.gitattributes` 等以点开头的文件，先按 `⌘ + Shift + .` 显示出来再一起拖。
上传后确认仓库里有 `.github/workflows/` 三个文件，否则自动化不会运行。

## 3. 仓库设置

进入仓库 **Settings**：

1. **Actions → General**
   - Actions permissions：任意一档都可以，工作流不依赖任何外部 action；最严格的 “Allow HuberHaYu actions and reusable workflows” 也能正常运行
   - Workflow permissions：默认只读即可，三个工作流都显式声明了自己需要的写权限。
     如果之后 Actions 日志里 `git push` 报 403，再把这里改成 **Read and write permissions**
   - Approval for running fork pull request workflows：选 **Require approval for all external contributors**，
     别人提交的 PR 需要你点批准才会运行
2. **General → Features**：保留 **Issues**（评分测试要用），Wikis、Projects 可以关掉
3. **不要**给 `main` 开启“必须通过 PR 合并”的分支保护——Actions 需要直接向 `main` 提交生成物
4. （可选）**Issues → Labels → New label** 建一个 `rating` 标签，评分 issue 会自动带上它

公开仓库只有你（和你邀请的协作者）能推送，其他人最多提 issue 或 PR。

## 4. 验证

1. **Actions** 页 → 左侧「构建目录」→ Run workflow → main → 运行。
   应在半分钟内变绿，日志显示“没有需要提交的变化”（压缩包里已经带好了生成物）
2. 浏览器打开以下地址，都应该返回含 3 个预设的 JSON：
   - `https://cdn.jsdelivr.net/gh/<用户名>/hxaudio-cloud@main/api/v1/index.json`
   - `https://raw.githubusercontent.com/<用户名>/hxaudio-cloud/main/api/v1/index.json`
   - `https://cdn.jsdelivr.net/gh/<用户名>/hxaudio-cloud@main/presets/studio-reference/studio-reference.hx4`
3. 测试评分写入（二选一）：
   - **Issues → New issue →「⭐ 给预设评分」**，选预设和分数提交。约 1 分钟后机器人回复并关闭 issue，
     `index.json` 里该预设的 `rating.count` +1
   - **Actions →「评分（App 接口）」→ Run workflow**，填 `studio-reference` 和分数。
     这条链路与将来 App 内评分完全相同，只是入口换成了手动触发
4. 刷新第 2 步的地址确认票数变化（raw 地址自身有约 5 分钟缓存，jsDelivr 会被 Actions 主动刷新）

## 5. 日常维护

- 新增/更新预设：见 docs/MAINTAINING.md，推送后自动校验、重建、刷新 CDN
- 发公告：改 `cloud.config.json` 的 `notice` 并推送
- 正式上线前清除测试评分：`python3 scripts/hxcloud.py purge-seed`，然后提交推送
- 本地修改前先 `git pull`——评分会不断产生新提交

## 6. 第二阶段：App 内评分

App 不能内置 GitHub 令牌，所以需要一个中转服务。部署步骤见 `relay/cloudflare-worker/README.md`，
部署后把地址填进 `cloud.config.json` 的 `rating.submit_endpoint` 并推送，
manifest 更新后 App 就会开放评分提交。在这之前 App 可以只展示评分。
