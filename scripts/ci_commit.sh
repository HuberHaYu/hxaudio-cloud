#!/usr/bin/env bash
# 仅供 GitHub Actions 使用：在最新的分支头上执行一条命令，把生成物提交并推送。
# 多个评分/构建同时运行时推送会冲突——此时基于新的分支头整条重做，最多 5 次。
# 投票按投票人覆盖写入，重做是幂等的，不会重复计票。
#
# 用法：bash scripts/ci_commit.sh "<提交信息>" <命令> [参数...]

main() {
  set -euo pipefail
  local message="$1"; shift
  local branch="${GITHUB_REF_NAME:-main}"

  git config user.name "github-actions[bot]"
  git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

  local attempt
  for attempt in 1 2 3 4 5; do
    git fetch --quiet origin "$branch"
    git reset --quiet --hard FETCH_HEAD
    "$@"
    bash scripts/sign_manifest.sh
    # 只暂存存在或仍被跟踪的路径：预设全部删除、还没有任何评分时 ratings/ 整个不存在，
    # 把它交给 git add 会报 “pathspec did not match” 并让整次构建失败。
    local path paths=()
    for path in api ratings .github/ISSUE_TEMPLATE README.md; do
      if [ -e "$path" ] || [ -n "$(git ls-files -- "$path")" ]; then
        paths+=("$path")
      fi
    done
    git add -A -- "${paths[@]}"
    if git diff --cached --quiet; then
      echo "没有需要提交的变化。"
      return 0
    fi
    git commit --quiet -m "$message"
    if git push --quiet origin "HEAD:$branch"; then
      echo "已推送：$(git rev-parse --short HEAD)"
      bash scripts/purge_cdn.sh "$branch" $(git diff --name-only HEAD~1 HEAD) || true
      return 0
    fi
    echo "推送冲突，第 $attempt 次重试…"
    sleep $((attempt * 2))
  done
  echo "::error::连续 5 次推送冲突，放弃。重新运行此工作流即可。"
  return 1
}

# 整个脚本先被解析成函数再执行：中途 git reset 改写本文件也不会影响正在运行的这一份。
main "$@"
