/**
 * HXAudio Pro 评分中转（Cloudflare Worker）—— 第二阶段才需要部署。
 *
 *   App ──POST /v1/ratings──▶ 本 Worker ──repository_dispatch──▶ GitHub Actions 记票 ──▶ index.json
 *
 * GitHub 令牌只保存在 Worker 的 secret 里，App 内不含任何密钥。
 * install_id 经 HMAC(VOTER_SALT) 匿名化后才进入公开仓库，无法反推出设备。
 */
const SCORE_MIN = 1;
const SCORE_MAX = 5;
const PRESET_ID = /^[a-z0-9][a-z0-9-]{1,46}[a-z0-9]$/;
const INSTALL_ID = /^[A-Za-z0-9_-]{16,128}$/;
const VOTE_COOLDOWN_S = 60; // 同一设备对同一预设的最短重投间隔（KV 的 TTL 下限就是 60 秒）
const IP_LIMIT_PER_HOUR = 30;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/v1/health") return reply({ ok: true });
    if (url.pathname !== "/v1/ratings") return reply({ ok: false, error: "not_found" }, 404);
    if (request.method !== "POST") return reply({ ok: false, error: "method_not_allowed" }, 405);
    if (!env.GITHUB_TOKEN || !env.VOTER_SALT || !env.GITHUB_REPO) {
      return reply({ ok: false, error: "relay_misconfigured" }, 500);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return reply({ ok: false, error: "bad_json" }, 400);
    }
    const presetId = typeof body?.preset_id === "string" ? body.preset_id : "";
    const score = body?.score;
    const installId = typeof body?.install_id === "string" ? body.install_id : "";
    if (!PRESET_ID.test(presetId)) return reply({ ok: false, error: "invalid_preset" }, 400);
    if (!Number.isInteger(score) || score < SCORE_MIN || score > SCORE_MAX) {
      return reply({ ok: false, error: "invalid_score" }, 400);
    }
    if (!INSTALL_ID.test(installId)) return reply({ ok: false, error: "invalid_install_id" }, 400);

    const index = await loadIndex(env);
    if (!index) return reply({ ok: false, error: "catalog_unavailable" }, 503);
    if (!index.presets?.some((p) => p.id === presetId)) {
      return reply({ ok: false, error: "unknown_preset" }, 404);
    }

    const voter = "app:" + (await hmac(env.VOTER_SALT, installId));
    if (env.RATING_KV) {
      const ip = request.headers.get("CF-Connecting-IP") || "unknown";
      const retryAfter = await rateLimited(env.RATING_KV, ip, voter, presetId);
      if (retryAfter) return reply({ ok: false, error: "rate_limited", retry_after: retryAfter }, 429);
    }

    const response = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "hxaudio-rating-relay",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        event_type: "submit-rating",
        client_payload: {
          preset_id: presetId,
          score,
          voter,
          app_version: String(body.app_version ?? "").slice(0, 32),
        },
      }),
    });
    if (response.status !== 204) {
      console.log("repository_dispatch failed", response.status, await response.text());
      return reply({ ok: false, error: "upstream_failed" }, 502);
    }
    return reply({ ok: true, status: "queued" }, 202);
  },
};

async function loadIndex(env) {
  const url = env.INDEX_URL || `https://raw.githubusercontent.com/${env.GITHUB_REPO}/main/api/v1/index.json`;
  try {
    const response = await fetch(url, { cf: { cacheTtl: 300, cacheEverything: true } });
    return response.ok ? await response.json() : null;
  } catch {
    return null;
  }
}

/** KV 是最终一致的，这里是“软”限流：挡住连点和脚本刷票，不追求绝对精确。 */
async function rateLimited(kv, ip, voter, presetId) {
  const voteKey = `v:${voter}:${presetId}`;
  if (await kv.get(voteKey)) return VOTE_COOLDOWN_S;
  const hour = Math.floor(Date.now() / 3_600_000);
  const ipKey = `ip:${ip}:${hour}`;
  const used = Number((await kv.get(ipKey)) || 0);
  if (used >= IP_LIMIT_PER_HOUR) return 3600 - Math.floor((Date.now() / 1000) % 3600);
  await Promise.all([
    kv.put(voteKey, "1", { expirationTtl: VOTE_COOLDOWN_S }),
    kv.put(ipKey, String(used + 1), { expirationTtl: 3600 }),
  ]);
  return 0;
}

async function hmac(secret, text) {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const signature = new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(text)));
  const base64 = btoa(String.fromCharCode(...signature));
  return base64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "").slice(0, 32);
}

function reply(body, status = 200) {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });
}
