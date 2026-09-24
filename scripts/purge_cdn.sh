#!/usr/bin/env bash
# 让 jsDelivr 立即丢弃指定文件的分支缓存（否则最长会缓存 12 小时）。
# 用法：bash scripts/purge_cdn.sh <分支> [文件路径...]   manifest、签名与 index 总会被刷新。
set -uo pipefail
branch="$1"; shift
repo="${GITHUB_REPOSITORY:?需要 GITHUB_REPOSITORY}"
for path in api/v1/manifest.json api/v1/manifest.sig api/v1/index.json "$@"; do
  echo "$path"
done | sort -u | while read -r path; do
  [ -n "$path" ] || continue
  status=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 \
    "https://purge.jsdelivr.net/gh/${repo}@${branch}/${path}")
  echo "jsDelivr purge ${path} → ${status}"
done
