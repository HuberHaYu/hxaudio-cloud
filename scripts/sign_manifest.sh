#!/usr/bin/env bash
# 为 api/v1/manifest.json 生成 ECDSA P-256 / SHA-256 签名，写入 api/v1/manifest.sig（Base64 DER）。
#
# manifest 里记录了 index.json 的 SHA-256，index.json 又记录了每个 .hx4 的 SHA-256，
# 所以这一个签名覆盖了整个目录。App 只信任能用内置公钥验签的数据，任何线路改动内容都会被识别。
#
# 私钥只从环境变量 HXCLOUD_SIGNING_KEY（GitHub Actions Secret）读取，从不落盘到仓库。
# 现有签名仍然有效时不重签：ECDSA 签名每次都不同，重签会产生无意义的提交。
set -euo pipefail
cd "$(dirname "$0")/.."

manifest=api/v1/manifest.json
signature=api/v1/manifest.sig
public_key=keys/manifest-signing-public.pem

verify() {
  [ -s "$signature" ] || return 1
  local der status
  der=$(mktemp)
  if ! base64 -d < "$signature" > "$der" 2>/dev/null; then rm -f "$der"; return 1; fi
  openssl dgst -sha256 -verify "$public_key" -signature "$der" "$manifest" > /dev/null 2>&1 && status=0 || status=1
  rm -f "$der"
  return $status
}

if verify; then
  echo "manifest 签名有效。"
  exit 0
fi

if [ -z "${HXCLOUD_SIGNING_KEY:-}" ]; then
  echo "::error::manifest 已变化，但没有签名私钥（仓库 Secret：HXCLOUD_SIGNING_KEY）。App 会拒绝未签名的数据。"
  exit 1
fi

key=$(mktemp)
der=$(mktemp)
trap 'rm -f "$key" "$der"' EXIT
chmod 600 "$key"
printf '%s\n' "$HXCLOUD_SIGNING_KEY" > "$key"
openssl dgst -sha256 -sign "$key" -out "$der" "$manifest"
base64 < "$der" | tr -d '\n' > "$signature"
echo >> "$signature"

if ! verify; then
  echo "::error::签名后校验失败：Secret 中的私钥与 keys/manifest-signing-public.pem 不是一对。"
  exit 1
fi
echo "已重新签名 manifest。"
