#!/usr/bin/env python3
"""
HXAudio Pro 云端预设仓库工具（零依赖，Python 3.9+）。

  python3 scripts/hxcloud.py validate                 只校验 presets/ 与 ratings/，不写任何文件
  python3 scripts/hxcloud.py build                    校验并重新生成 api/v1/* 和评分表单
  python3 scripts/hxcloud.py build --check            生成物不是最新时失败（不写文件）
  python3 scripts/hxcloud.py add 导出.hx4 --id my-preset --title 标题 [--author ...]
  python3 scripts/hxcloud.py add 新版.hx4 --id my-preset --replace
  python3 scripts/hxcloud.py rate <预设ID> <1-5> --voter manual:me
  python3 scripts/hxcloud.py purge-seed               删除内置的测试评分

GitHub Actions 调用的也只是这几个命令，本地跑出来的结果与云端完全一致。
人工维护的只有 presets/ 与 cloud.config.json；api/、ratings/ 以及 README 中的预设列表由工具写入，不要手改。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRESETS_DIR = ROOT / "presets"
RATINGS_DIR = ROOT / "ratings"
API_DIR = ROOT / "api" / "v1"
INDEX_PATH = API_DIR / "index.json"
MANIFEST_PATH = API_DIR / "manifest.json"
CONFIG_PATH = ROOT / "cloud.config.json"
ISSUE_FORM_PATH = ROOT / ".github" / "ISSUE_TEMPLATE" / "rating.yml"
README_PATH = ROOT / "README.md"
README_START, README_END = "<!-- presets:start -->", "<!-- presets:end -->"

API_SCHEMA_VERSION = 1
PRESET_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,46}[a-z0-9]$")
VOTER = re.compile(r"^(app|gh|manual|seed):[A-Za-z0-9_.-]{1,128}$")
VOTE_KEY = re.compile(r"^[0-9a-f]{16}$")
MIRROR_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
DEVICE_KINDS = ("SPEAKER", "WIRED_ANALOG", "WIRED_USB", "BLUETOOTH", "OTHER")
DEVICE_KIND_LABELS = {
    "SPEAKER": "手机外放", "WIRED_ANALOG": "3.5mm 有线耳机", "WIRED_USB": "USB 耳机",
    "BLUETOOTH": "蓝牙耳机", "OTHER": "其他设备",
}
SCORE_MIN, SCORE_MAX = 1, 5
MAX_HX4_BYTES = 64 * 1024
META_KEYS = {"title", "subtitle", "description", "author", "tags", "device_kinds", "target_devices", "featured"}

# —— 以下常量与 App 源码一致（com.lab.hxaudio.audio.*Definition / Hx4ProfileStore）——
HX4_FORMAT = "HXAudioPro4"
HX4_VERSIONS = (1, 2)
PRE_EQ_HZ = (31, 65, 125, 250, 500, 1000, 2000, 4000, 8000, 12000, 16000, 20000)
POST_EQ_HZ = tuple(
    math.exp(math.log(20.0) + (math.log(20000.0) - math.log(20.0)) * i / 30) for i in range(31)
)
VOLUME_NODES = 11
BASS_BOOST_RANGE_HZ = (60.0, 165.0)


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, where: str, message: str) -> None:
        self.errors.append(f"{where}: {message}")

    def warn(self, where: str, message: str) -> None:
        self.warnings.append(f"{where}: {message}")

    def emit(self) -> None:
        for line in self.warnings:
            print(f"::warning::{line}" if os.environ.get("GITHUB_ACTIONS") else f"警告  {line}")
        for line in self.errors:
            print(f"::error::{line}" if os.environ.get("GITHUB_ACTIONS") else f"错误  {line}")


class InvalidInput(Exception):
    """评分请求本身不合法（预设不存在、分数越界等），不应重试。"""


# ───────────────────────────── 通用 ─────────────────────────────

def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso(moment: dt.datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def dump_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def read_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def vote_key(voter: str) -> str:
    return hashlib.sha256(voter.encode("utf-8")).hexdigest()[:16]


# ───────────────────────────── .hx4 校验 ─────────────────────────────

class AudioReader:
    """按 Hx4ProfileStore.decodeAudio 的读取规则校验一个 audio 对象。

    App 读取时会把越界值悄悄夹到合法范围；云端目录更严格——越界直接报错，
    这样仓库里的数值就是用户实际听到的数值。
    """

    def __init__(self, report: Report, where: str) -> None:
        self.report = report
        self.where = where

    def obj(self, parent: dict, key: str, required: bool = True) -> dict | None:
        value = parent.get(key)
        if value is None:
            if required:
                self.report.error(self.where, f"缺少 {key}")
            return None
        if not isinstance(value, dict):
            self.report.error(self.where, f"{key} 必须是对象")
            return None
        return value

    def boolean(self, parent: dict | None, path: str, key: str, required: bool = True) -> bool:
        if parent is None:
            return False
        value = parent.get(key)
        if value is None and not required:
            return False
        if not isinstance(value, bool):
            self.report.error(self.where, f"{path}.{key} 必须是 true/false")
            return False
        return value

    def num(self, parent: dict | None, path: str, key: str, lo: float, hi: float, *,
            integer: bool = False, required: bool = True, default: float = 0) -> float:
        if parent is None:
            return default
        value = parent.get(key)
        if value is None and not required:
            return default
        if not is_number(value) or (integer and float(value) != int(value)):
            kind = "整数" if integer else "数字"
            self.report.error(self.where, f"{path}.{key} 必须是{kind}")
            return default
        if not lo <= value <= hi:
            self.report.error(self.where, f"{path}.{key} = {value} 超出 App 允许范围 [{lo}, {hi}]")
            return min(max(value, lo), hi)
        return value

    def floats(self, parent: dict | None, path: str, key: str, size: int, limit: float, *,
               required: bool = True) -> list[float]:
        if parent is None:
            return [0.0] * size
        value = parent.get(key)
        if value is None and not required:
            return [0.0] * size
        if not isinstance(value, list) or len(value) != size:
            self.report.error(self.where, f"{path}.{key} 必须是长度为 {size} 的数组")
            return [0.0] * size
        out = []
        for index, item in enumerate(value):
            if not is_number(item):
                self.report.error(self.where, f"{path}.{key}[{index}] 不是有效数字")
                out.append(0.0)
            elif abs(item) > limit:
                self.report.error(self.where, f"{path}.{key}[{index}] = {item} 超出 ±{limit}")
                out.append(max(-limit, min(limit, item)))
            else:
                out.append(float(item))
        return out


def check_audio(audio: dict, report: Report, where: str) -> dict:
    r = AudioReader(report, where)
    pre = r.floats(audio, "audio", "pre_eq_gains_db", len(PRE_EQ_HZ), 12.0)

    points: list[tuple[float, float, float]] = []
    raw_points = audio.get("post_eq_points")
    if not isinstance(raw_points, list):
        report.error(where, "audio.post_eq_points 必须是数组")
        raw_points = []
    seen_ids = set()
    for index, point in enumerate(raw_points):
        path = f"audio.post_eq_points[{index}]"
        if not isinstance(point, dict):
            report.error(where, f"{path} 必须是对象")
            continue
        point_id = point.get("id")
        if not isinstance(point_id, str) or not point_id.strip():
            report.warn(where, f"{path}.id 为空，App 导入时会随机生成")
        elif point_id in seen_ids:
            report.warn(where, f"{path}.id 重复：{point_id}")
        else:
            seen_ids.add(point_id)
        points.append((
            r.num(point, path, "frequency_hz", 20.0, 20000.0, default=1000.0),
            r.num(point, path, "gain_db", -15.0, 15.0),
            r.num(point, path, "q", 0.2, 12.0, default=1.0),
        ))
    if [p[0] for p in points] != sorted(p[0] for p in points):
        report.warn(where, "post_eq_points 未按频率升序排列（App 导入时会自动排序）")
    if len(points) > 24:
        report.warn(where, f"PostEQ 有 {len(points)} 个控制点，建议不超过 24 个")

    bass = r.obj(audio, "bass_boost")
    bass_on = r.boolean(bass, "bass_boost", "enabled")
    bass_db = r.num(bass, "bass_boost", "gain_db", 0.0, 15.0, default=6.0)

    gain = r.obj(audio, "input_gain")
    r.num(gain, "input_gain", "balance_percent", -100.0, 100.0)
    total_db = r.num(gain, "input_gain", "total_gain_db", -20.0, 20.0)
    r.boolean(gain, "input_gain", "use_dynamics_processing_gain")

    limiter = r.obj(audio, "main_limiter")
    limiter_on = r.boolean(limiter, "main_limiter", "enabled")
    r.num(limiter, "main_limiter", "link_group", 0, 31, integer=True)
    r.num(limiter, "main_limiter", "attack_time_ms", 0.1, 200.0, default=1.0)
    r.num(limiter, "main_limiter", "release_time_ms", 10.0, 2000.0, default=60.0)
    r.num(limiter, "main_limiter", "ratio", 1.0, 100.0, default=10.0)
    r.num(limiter, "main_limiter", "threshold_db", -60.0, 0.0, default=-1.0)
    r.num(limiter, "main_limiter", "post_gain_db", -15.0, 15.0)

    surround = r.obj(audio, "virtual_surround", required=False)
    surround_on = r.boolean(surround, "virtual_surround", "enabled", required=False)
    width = r.num(surround, "virtual_surround", "width_percent", 0, 100,
                  integer=True, required=False, default=55)

    pulse = r.obj(audio, "eq_pulse", required=False)
    pulse_on = r.boolean(pulse, "eq_pulse", "enabled", required=False)
    strength = r.num(pulse, "eq_pulse", "strength_percent", 0, 100,
                     integer=True, required=False, default=100)
    impulse_id = (pulse or {}).get("impulse_id", "")
    pulse_pre = r.floats(pulse, "eq_pulse", "pre_eq_db", len(PRE_EQ_HZ), 9.0, required=False)
    pulse_post = r.floats(pulse, "eq_pulse", "post_eq_db", len(POST_EQ_HZ), 12.0, required=False)
    pulse_audible = (pulse_on and isinstance(impulse_id, str) and impulse_id.strip() != ""
                     and strength > 0 and any(v != 0 for v in pulse_pre + pulse_post))

    comp = r.obj(audio, "volume_compensation", required=False)
    comp_on = r.boolean(comp, "volume_compensation", "enabled", required=False)
    low = r.floats(comp, "volume_compensation", "low_db", VOLUME_NODES, 12.0, required=False)
    mid = r.floats(comp, "volume_compensation", "mid_db", VOLUME_NODES, 12.0, required=False)
    high = r.floats(comp, "volume_compensation", "high_db", VOLUME_NODES, 12.0, required=False)
    comp_audible = comp_on and any(v != 0 for v in low + mid + high)

    post = [sample_post_eq(points, hz) for hz in POST_EQ_HZ]

    # 粗略的峰值增益估计，只用来提醒可能削波；不代表 DynamicsProcessing 的精确响应。
    # 响度补偿只计 100% 音量那个节点：低音量时信号本身已被衰减，补偿不会顶到满幅。
    peak = max(
        pre_eq_at(pre, hz) + post[i] + total_db
        + (bass_db if bass_on and BASS_BOOST_RANGE_HZ[0] <= hz <= BASS_BOOST_RANGE_HZ[1] else 0.0)
        for i, hz in enumerate(POST_EQ_HZ)
    )
    if comp_audible:
        peak += max(0.0, low[-1], mid[-1], high[-1])
    if peak > 6.0 and not limiter_on:
        report.warn(where, f"估计峰值增益约 +{peak:.1f} dB 且未开启限幅器，可能削波")
    elif peak > 12.0:
        report.warn(where, f"估计峰值增益约 +{peak:.1f} dB，建议降低 input_gain.total_gain_db")

    return {
        "features": {
            "post_eq_points": len(points),
            "bass_boost_db": round(bass_db, 2) if bass_on else None,
            "input_gain_db": round(total_db, 2),
            "limiter": limiter_on,
            "virtual_surround_percent": int(width) if surround_on else None,
            "volume_compensation": comp_audible,
            "eq_pulse": pulse_audible,
        },
        "preview": {
            "pre_eq_db": [round(v, 2) for v in pre],
            "post_eq_db": [round(v, 2) for v in post],
        },
    }


def sample_post_eq(points: list[tuple[float, float, float]], hz: float) -> float:
    """PostEqDefinition.sampleAt 的等价实现。"""
    total = 0.0
    for freq, gain, q in points:
        octaves = math.log(hz / freq) / math.log(2.0)
        width = max(0.12, 1.0 / (q * 1.35))
        total += gain * math.exp(-0.5 * octaves ** 2 / width ** 2)
    return max(-15.0, min(15.0, total))


def pre_eq_at(pre: list[float], hz: float) -> float:
    if hz <= PRE_EQ_HZ[0]:
        return pre[0]
    for i in range(len(PRE_EQ_HZ) - 1):
        lo, hi = PRE_EQ_HZ[i], PRE_EQ_HZ[i + 1]
        if hz <= hi:
            t = math.log(hz / lo) / math.log(hi / lo)
            return pre[i] + (pre[i + 1] - pre[i]) * t
    return pre[-1]


def check_hx4_bytes(raw: bytes, report: Report, where: str) -> tuple[int, dict] | None:
    if len(raw) > MAX_HX4_BYTES:
        report.error(where, f"文件 {len(raw)} 字节，超过 {MAX_HX4_BYTES} 字节上限")
        return None
    try:
        root = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        report.error(where, f"不是有效的 UTF-8 JSON：{error}")
        return None
    if not isinstance(root, dict) or root.get("format") != HX4_FORMAT:
        report.error(where, "不是 HXAudio Pro .hx4 配置文件（format 必须为 HXAudioPro4）")
        return None
    version = root.get("version")
    if version not in HX4_VERSIONS or isinstance(version, bool):
        report.error(where, f"不支持的 .hx4 版本：{version!r}")
        return None
    if root.get("encrypted", False) is not False:
        report.error(where, "云端预设必须是未加密的 .hx4")
    if "devices" in root:
        report.error(where, "云端预设不能包含 devices 数组——App 导入时会用它覆盖用户各设备的独立记忆。"
                            "用 `python3 scripts/hxcloud.py add` 导入会自动移除，或手动删掉该字段")
    audio = root.get("audio")
    if not isinstance(audio, dict):
        report.error(where, "缺少 audio 对象")
        return None
    return version, check_audio(audio, report, where)


# ───────────────────────────── 预设目录 ─────────────────────────────

def check_meta(meta, report: Report, where: str) -> dict | None:
    if not isinstance(meta, dict):
        report.error(where, "meta.json 必须是对象")
        return None

    def text(key: str, limit: int, required: bool) -> str:
        value = meta.get(key, "")
        if not isinstance(value, str):
            report.error(where, f"{key} 必须是字符串")
            return ""
        value = value.strip()
        if required and not value:
            report.error(where, f"{key} 不能为空")
        if len(value) > limit:
            report.error(where, f"{key} 超过 {limit} 个字符")
        return value

    out = {
        "title": text("title", 24, True),
        "subtitle": text("subtitle", 40, False),
        "description": text("description", 600, False),
        "author": text("author", 32, True),
    }
    tags = meta.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(t, str) and 0 < len(t.strip()) <= 12 for t in tags):
        report.error(where, "tags 必须是字符串数组，每项 1–12 个字符")
        tags = []
    if len(tags) > 8:
        report.error(where, "tags 最多 8 个")
    kinds = meta.get("device_kinds", [])
    if not isinstance(kinds, list) or any(k not in DEVICE_KINDS for k in kinds):
        report.error(where, f"device_kinds 只能取 {', '.join(DEVICE_KINDS)}（留空表示通用）")
        kinds = []
    featured = meta.get("featured", False)
    if not isinstance(featured, bool):
        report.error(where, "featured 必须是 true/false")
        featured = False
    targets = check_target_devices(meta.get("target_devices", []), report, where)
    for unknown in sorted(set(meta) - META_KEYS - {"$comment"}):
        report.warn(where, f"未知字段 {unknown} 会被忽略")
    out.update(
        tags=[t.strip() for t in tags],
        device_kinds=[k for k in DEVICE_KINDS if k in kinds],
        target_devices=targets,
        featured=featured,
    )
    return out


def check_target_devices(targets, report: Report, where: str) -> list[dict]:
    """适配机型：App 用它判断「适合当前设备」。外放填手机型号，蓝牙 / USB 填耳机产品名。"""
    if not isinstance(targets, list):
        report.error(where, "target_devices 必须是数组")
        return []
    if len(targets) > 20:
        report.error(where, "target_devices 最多 20 个")
    out = []
    for index, target in enumerate(targets[:20]):
        path = f"target_devices[{index}]"
        if not isinstance(target, dict):
            report.error(where, f"{path} 必须是对象")
            continue
        kind, name, aliases = target.get("kind"), target.get("name"), target.get("aliases", [])
        if kind not in DEVICE_KINDS:
            report.error(where, f"{path}.kind 只能取 {', '.join(DEVICE_KINDS)}")
            continue
        if kind == "WIRED_ANALOG":
            report.warn(where, f"{path}：3.5mm 耳机无法被系统识别型号，这一项只会显示、不会参与匹配")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 40:
            report.error(where, f"{path}.name 必须是 1–40 个字符")
            continue
        if not isinstance(aliases, list) or len(aliases) > 10 or \
                not all(isinstance(a, str) and 2 <= len(a.strip()) <= 40 for a in aliases):
            report.error(where, f"{path}.aliases 最多 10 个，每个 2–40 个字符")
            aliases = []
        out.append({"kind": kind, "name": name.strip(), "aliases": [a.strip() for a in aliases]})
    return out


def list_preset_dirs() -> list[Path]:
    if not PRESETS_DIR.is_dir():
        return []
    return sorted(p for p in PRESETS_DIR.iterdir() if p.is_dir() and not p.name.startswith("."))


def load_preset(folder: Path, report: Report, previous: dict | None, today: str) -> dict | None:
    preset_id = folder.name
    where = rel(folder)
    if not PRESET_ID.match(preset_id):
        report.error(where, "文件夹名即预设 ID：只能用小写字母、数字和连字符，3–48 个字符")
        return None
    meta_path = folder / "meta.json"
    hx4_path = folder / f"{preset_id}.hx4"
    try:
        meta = check_meta(read_json(meta_path), report, rel(meta_path)) if meta_path.exists() else None
    except json.JSONDecodeError as error:
        report.error(rel(meta_path), f"不是有效 JSON：{error}")
        meta = None
    if not meta_path.exists():
        report.error(where, "缺少 meta.json")
    for extra in sorted(folder.glob("*.hx4")):
        if extra != hx4_path:
            report.error(rel(extra), f"每个预设只放一个 .hx4，且文件名必须是 {preset_id}.hx4")
    if not hx4_path.exists():
        report.error(where, f"缺少 {preset_id}.hx4")
        return None
    raw = hx4_path.read_bytes()
    checked = check_hx4_bytes(raw, report, rel(hx4_path))
    if meta is None or checked is None:
        return None
    version, summary = checked

    sha = hashlib.sha256(raw).hexdigest()
    # revision / created / updated 全部由构建推导：文件内容变了就 +1，不需要手动维护。
    if previous and previous.get("file", {}).get("sha256") == sha:
        revision, created, updated = previous["revision"], previous["created"], previous["updated"]
    elif previous:
        revision, created, updated = previous["revision"] + 1, previous["created"], today
    else:
        revision, created, updated = 1, today, today

    return {
        "id": preset_id,
        **meta,
        "revision": revision,
        "created": created,
        "updated": updated,
        "file": {
            "path": rel(hx4_path),
            "sha256": sha,
            "bytes": len(raw),
            "hx4_version": version,
        },
        **summary,
    }


# ───────────────────────────── 评分 ─────────────────────────────

def ratings_path(preset_id: str) -> Path:
    return RATINGS_DIR / f"{preset_id}.json"


def load_votes(preset_id: str, report: Report | None = None) -> dict:
    path = ratings_path(preset_id)
    data = read_json(path)
    if data is None:
        return {}
    where = rel(path)
    problems = Report() if report is None else report
    if not isinstance(data, dict) or data.get("preset_id") != preset_id or not isinstance(data.get("votes"), dict):
        problems.error(where, "格式错误：需要 {preset_id, votes}，且 preset_id 与文件名一致")
        return {}
    votes = {}
    for key, vote in data["votes"].items():
        ok = (VOTE_KEY.match(key) and isinstance(vote, dict)
              and isinstance(vote.get("score"), int) and not isinstance(vote.get("score"), bool)
              and SCORE_MIN <= vote["score"] <= SCORE_MAX
              and vote.get("via") in ("app", "gh", "manual", "seed"))
        if ok:
            votes[key] = vote
        else:
            problems.error(where, f"无效投票 {key}")
    return votes


def save_votes(preset_id: str, votes: dict) -> None:
    RATINGS_DIR.mkdir(parents=True, exist_ok=True)
    ordered = {key: votes[key] for key in sorted(votes)}
    ratings_path(preset_id).write_text(
        dump_json({"preset_id": preset_id, "votes": ordered}), encoding="utf-8")


def summarize(votes: dict, global_mean: float, prior: float) -> dict:
    histogram = [0] * (SCORE_MAX - SCORE_MIN + 1)
    for vote in votes.values():
        histogram[vote["score"] - SCORE_MIN] += 1
    count = sum(histogram)
    total = sum((i + SCORE_MIN) * n for i, n in enumerate(histogram))
    return {
        "count": count,
        "average": round(total / count, 2) if count else None,
        # 贝叶斯平均：票数少时向全站均分收缩，用于排序，避免 1 票 5 分排到最前。
        "weighted": round((prior * global_mean + total) / (prior + count), 3),
        "histogram": histogram,
    }


# ───────────────────────────── 构建 ─────────────────────────────

def load_config(report: Report) -> dict:
    config = read_json(CONFIG_PATH) or {}
    rating = config.get("rating", {}) if isinstance(config.get("rating"), dict) else {}
    endpoint = rating.get("submit_endpoint", "") or ""
    if endpoint and not re.match(r"^https://[^\s]+$", endpoint):
        report.error("cloud.config.json", "rating.submit_endpoint 必须为空或 https:// 地址")
    client_id = rating.get("github_client_id", "") or ""
    if client_id and not re.match(r"^[A-Za-z0-9._-]{8,64}$", client_id):
        report.error("cloud.config.json", "rating.github_client_id 格式不正确（应为 GitHub App 的 Client ID）")
    prior = rating.get("prior_weight", 5)
    if not is_number(prior) or prior < 0:
        report.error("cloud.config.json", "rating.prior_weight 必须是非负数")
        prior = 5
    min_code = config.get("min_app_version_code", 0)
    if not isinstance(min_code, int) or isinstance(min_code, bool):
        report.error("cloud.config.json", "min_app_version_code 必须是整数")
        min_code = 0
    return {
        "name": str(config.get("name", "HXAudio Pro 云端预设")),
        "notice": str(config.get("notice", "")),
        "min_app_version_code": min_code,
        "submit_endpoint": endpoint or None,
        "github_client_id": client_id or None,
        "prior_weight": prior,
        "mirrors": check_mirrors(config.get("mirrors", []), report),
    }


def check_mirrors(mirrors, report: Report) -> list[dict]:
    """App 的下载线路。随签名后的 manifest 下发，App 下次同步起即按新列表选路，无需发版。"""
    where = "cloud.config.json"
    if not isinstance(mirrors, list):
        report.error(where, "mirrors 必须是数组")
        return []
    out, seen = [], set()
    for index, mirror in enumerate(mirrors):
        path = f"mirrors[{index}]"
        if not isinstance(mirror, dict):
            report.error(where, f"{path} 必须是对象")
            continue
        mirror_id, kind, url = mirror.get("id"), mirror.get("kind"), mirror.get("url")
        enabled = mirror.get("enabled", True)
        if not isinstance(mirror_id, str) or not MIRROR_ID.match(mirror_id) or mirror_id in seen:
            report.error(where, f"{path}.id 必须唯一，且只含小写字母、数字、连字符")
            continue
        seen.add(mirror_id)
        if kind not in ("raw", "cdn"):
            report.error(where, f"{path}.kind 只能是 raw（直连 GitHub，内容最新）或 cdn（有缓存）")
        if not isinstance(url, str) or not url.startswith("https://") or "{path}" not in url:
            report.error(where, f"{path}.url 必须是 https:// 地址且包含 {{path}}")
        elif set(re.findall(r"\{(\w+)\}", url)) - {"owner", "repo", "branch", "path"}:
            report.error(where, f"{path}.url 只能使用 {{owner}} {{repo}} {{branch}} {{path}} 占位符")
        if not isinstance(enabled, bool):
            report.error(where, f"{path}.enabled 必须是 true/false")
        out.append({"id": mirror_id, "kind": kind, "url": url, "enabled": enabled})
    return out


def with_stable_timestamp(body: dict, path: Path, stamp: str) -> dict:
    """内容没变就沿用旧的 generated_at，避免每次构建都产生无意义的提交。"""
    old = read_json(path) if path.exists() else None
    if isinstance(old, dict):
        old_stamp = old.pop("generated_at", None)
        if old_stamp and old == body:
            stamp = old_stamp
    return {"schema_version": body["schema_version"], "generated_at": stamp,
            **{k: v for k, v in body.items() if k != "schema_version"}}


def render_issue_form(entries: list[dict]) -> str:
    options = [f"{e['id']} · {e['title']}" for e in entries] or ["（暂无可评分的预设）"]
    q = lambda s: json.dumps(s, ensure_ascii=False)  # JSON 字符串同时是合法的 YAML 双引号字符串
    lines = [
        "# 此文件由 scripts/hxcloud.py build 自动生成，手改会被覆盖。",
        "name: ⭐ 给预设评分",
        "description: 为云端预设打 1–5 星。每个 GitHub 账号对同一预设只计一票，再次提交会覆盖上一票。",
        'title: "[评分] "',
        "labels: [\"rating\"]",
        "body:",
        "  - type: markdown",
        "    attributes:",
        "      value: 提交后机器人会自动记录评分并关闭此 issue，1–2 分钟内同步到云端目录。",
        "  - type: dropdown",
        "    id: preset",
        "    attributes:",
        "      label: 预设",
        "      options:",
        *[f"        - {q(o)}" for o in options],
        "    validations:",
        "      required: true",
        "  - type: dropdown",
        "    id: score",
        "    attributes:",
        "      label: 评分",
        "      options:",
        *[f"        - {q(f'{s} ' + '★' * s)}" for s in range(SCORE_MAX, SCORE_MIN - 1, -1)],
        "    validations:",
        "      required: true",
    ]
    return "\n".join(lines) + "\n"


def render_readme(entries: list[dict]) -> str | None:
    """重写 README 中 presets:start/end 标记之间的预设列表；没有标记时不动 README。"""
    if not README_PATH.exists():
        return None
    text = README_PATH.read_text(encoding="utf-8")
    start, end = text.find(README_START), text.find(README_END)
    if start < 0 or end < start:
        return None
    cell = lambda s: s.replace("|", "\\|").replace("\n", " ")
    rows = ["| 预设 | 适用设备 | 说明 | 文件 |", "| --- | --- | --- | --- |"]
    for e in sorted(entries, key=lambda e: not e["featured"]):
        kinds = "、".join(DEVICE_KIND_LABELS[k] for k in e["device_kinds"]) or "通用"
        models = "、".join(t["name"] for t in e["target_devices"])
        if models:
            kinds = f"{kinds}（{models}）"
        note = e["subtitle"] or e["description"].split("。")[0]
        path = e["file"]["path"]
        rows.append(f"| {cell(e['title'])} | {kinds} | {cell(note)} | [{path.rsplit('/', 1)[-1]}]({path}) |")
    body = "\n".join(rows) if entries else "暂无预设。"
    return f"{text[:start]}{README_START}\n{body}\n{text[end:]}"


def build(check_only: bool = False, quiet: bool = False) -> int:
    report = Report()
    config = load_config(report)
    moment = now_utc()
    today = moment.date().isoformat()
    previous_index = read_json(INDEX_PATH) or {}
    previous = {p["id"]: p for p in previous_index.get("presets", []) if isinstance(p, dict) and "id" in p}

    entries = []
    for folder in list_preset_dirs():
        entry = load_preset(folder, report, previous.get(folder.name), today)
        if entry:
            entries.append(entry)
    known = {folder.name for folder in list_preset_dirs()}
    for path in sorted(RATINGS_DIR.glob("*.json")) if RATINGS_DIR.is_dir() else []:
        if path.stem not in known:
            report.warn(rel(path), "对应的预设已不存在，这些评分不会出现在目录里")

    votes = {e["id"]: load_votes(e["id"], report) for e in entries}
    all_scores = [v["score"] for vs in votes.values() for v in vs.values()]
    global_mean = round(sum(all_scores) / len(all_scores), 3) if all_scores else 3.5
    for entry in entries:
        entry["rating"] = summarize(votes[entry["id"]], global_mean, config["prior_weight"])

    report.emit()
    if report.errors:
        print(f"失败：{len(report.errors)} 个错误。")
        return 1

    stamp = iso(moment)
    index = with_stable_timestamp({
        "schema_version": API_SCHEMA_VERSION,
        "frequencies": {
            "pre_eq_hz": list(PRE_EQ_HZ),
            "post_eq_hz": [round(hz, 1) for hz in POST_EQ_HZ],
        },
        "presets": entries,
    }, INDEX_PATH, stamp)
    index_text = dump_json(index)
    manifest = with_stable_timestamp({
        "schema_version": API_SCHEMA_VERSION,
        "name": config["name"],
        "notice": config["notice"],
        "min_app_version_code": config["min_app_version_code"],
        "hx4_versions": list(HX4_VERSIONS),
        "index": {
            "path": rel(INDEX_PATH),
            "sha256": hashlib.sha256(index_text.encode("utf-8")).hexdigest(),
            "preset_count": len(entries),
        },
        "rating": {
            "min": SCORE_MIN,
            "max": SCORE_MAX,
            "total_votes": len(all_scores),
            "global_mean": global_mean,
            "prior_weight": config["prior_weight"],
            "submit_endpoint": config["submit_endpoint"],
            "github_client_id": config["github_client_id"],
            "issue_template": ISSUE_FORM_PATH.name,
        },
        "mirrors": config["mirrors"],
    }, MANIFEST_PATH, stamp)

    outputs = {
        INDEX_PATH: index_text,
        MANIFEST_PATH: dump_json(manifest),
        ISSUE_FORM_PATH: render_issue_form(entries),
    }
    readme = render_readme(entries)
    if readme is not None:
        outputs[README_PATH] = readme
    stale = [path for path, text in outputs.items()
             if not path.exists() or path.read_text(encoding="utf-8") != text]
    if check_only:
        for path in stale:
            print(f"生成物不是最新：{rel(path)}（运行 python3 scripts/hxcloud.py build）")
        return 1 if stale else 0
    for path in stale:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(outputs[path], encoding="utf-8")
    if not quiet:
        changed = "、".join(rel(p) for p in stale) or "无变化"
        print(f"完成：{len(entries)} 个预设，{len(all_scores)} 票。更新：{changed}")
    return 0


# ───────────────────────────── 命令 ─────────────────────────────

def cmd_validate(_args) -> int:
    report = Report()
    load_config(report)
    for folder in list_preset_dirs():
        if load_preset(folder, report, None, "1970-01-01"):
            load_votes(folder.name, report)
    report.emit()
    print(f"失败：{len(report.errors)} 个错误。" if report.errors else "校验通过。")
    return 1 if report.errors else 0


def cmd_build(args) -> int:
    return build(check_only=args.check)


def cmd_add(args) -> int:
    preset_id = args.id
    if not PRESET_ID.match(preset_id):
        print("错误  --id 只能用小写字母、数字和连字符，3–48 个字符")
        return 1
    source = Path(args.file).expanduser()
    root = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(root, dict) and root.pop("devices", None) is not None:
        print("提示  已移除导出文件里的 devices 数组（云端预设只保留当前生效的 audio）")
    audio = root.get("audio") if isinstance(root, dict) else None
    if isinstance(audio, dict) and isinstance(audio.get("post_eq_points"), list):
        audio["post_eq_points"].sort(key=lambda p: p.get("frequency_hz", 0) if isinstance(p, dict) else 0)
    text = dump_json(root)
    report = Report()
    check_hx4_bytes(text.encode("utf-8"), report, source.name)
    report.emit()
    if report.errors:
        return 1

    folder = PRESETS_DIR / preset_id
    meta_path = folder / "meta.json"
    if args.replace:
        if not meta_path.exists():
            print(f"错误  presets/{preset_id} 不存在，去掉 --replace 新建")
            return 1
    else:
        if folder.exists():
            print(f"错误  presets/{preset_id} 已存在；只想换曲线请加 --replace")
            return 1
        if not args.title:
            print("错误  新建预设需要 --title")
            return 1
        folder.mkdir(parents=True)
        meta = {
            "title": args.title,
            "subtitle": args.subtitle or "",
            "description": args.description or "",
            "author": args.author,
            "tags": [t.strip() for t in (args.tags or "").split(",") if t.strip()],
            "device_kinds": [k.strip().upper() for k in (args.kinds or "").split(",") if k.strip()],
            "target_devices": [
                {"kind": kind.strip().upper(), "name": names.split(",")[0].strip(),
                 "aliases": [a.strip() for a in names.split(",")[1:] if a.strip()]}
                for kind, _, names in (m.partition(":") for m in args.model)
            ],
            "featured": args.featured,
        }
        meta_path.write_text(dump_json(meta), encoding="utf-8")
    (folder / f"{preset_id}.hx4").write_text(text, encoding="utf-8")
    print(f"已写入 presets/{preset_id}/")
    return build()


def parse_issue(body: str) -> tuple[str, int]:
    """解析 rating.yml 表单生成的 issue 正文（### 预设 / ### 评分）。"""
    body = body.replace("\r\n", "\n")
    fields = {}
    for match in re.finditer(r"^###[ \t]+(.+?)[ \t]*\n(.*?)(?=^###[ \t]|\Z)", body, re.M | re.S):
        fields[match.group(1).strip()] = match.group(2).strip()
    preset = fields.get("预设", "").split()
    score = re.match(r"([1-5])(?!\d)", fields.get("评分", ""))
    if not preset or not score:
        raise InvalidInput("没有识别到表单内容。请用 Issues → New issue → “⭐ 给预设评分” 模板提交。")
    return preset[0], int(score.group(1))


def resolve_vote(args) -> tuple[str, int, str]:
    env = os.environ
    if args.from_issue:
        preset_id, score = parse_issue(env.get("ISSUE_BODY", ""))
        voter = env.get("HXCLOUD_VOTER", "")
        if not voter.startswith("gh:"):
            raise InvalidInput("缺少 GitHub 用户标识")
        return preset_id, score, voter
    if args.from_payload:
        try:
            payload = json.loads(env.get("HXCLOUD_PAYLOAD", "") or "{}")
        except json.JSONDecodeError:
            raise InvalidInput("payload 不是有效 JSON")
        if not isinstance(payload, dict):
            raise InvalidInput("payload 必须是对象")
        via = env.get("HXCLOUD_VIA", "")
        if via == "app":
            voter = str(payload.get("voter", ""))
            if not voter.startswith("app:"):
                raise InvalidInput("App 评分必须带 voter，且以 app: 开头")
        elif via == "manual":
            voter = env.get("HXCLOUD_VOTER", "")
        else:
            raise InvalidInput("HXCLOUD_VIA 只能是 app 或 manual")
        raw_score = payload.get("score")
        try:
            score = int(str(raw_score).strip())
        except ValueError:
            raise InvalidInput(f"分数无效：{raw_score!r}")
        return str(payload.get("preset_id", "")).strip(), score, voter
    if args.preset_id is None or args.score is None or not args.voter:
        raise InvalidInput("用法：rate <预设ID> <1-5> --voter manual:你的标识")
    return args.preset_id, args.score, args.voter


def cmd_rate(args) -> int:
    result_path = os.environ.get("HXCLOUD_RESULT")

    def finish(message: str, code: int) -> int:
        print(message)
        if result_path:
            Path(result_path).write_text(message + "\n", encoding="utf-8")
        return code

    try:
        preset_id, score, voter = resolve_vote(args)
        if not PRESET_ID.match(preset_id) or not (PRESETS_DIR / preset_id / "meta.json").exists():
            raise InvalidInput(f"预设 `{preset_id}` 不存在")
        if not SCORE_MIN <= score <= SCORE_MAX:
            raise InvalidInput(f"分数必须是 {SCORE_MIN}–{SCORE_MAX} 的整数")
        if not VOTER.match(voter):
            raise InvalidInput("投票人标识格式无效")
    except InvalidInput as error:
        return finish(f"未能记录评分：{error}", 2)

    index = read_json(INDEX_PATH) or {}
    entry = next((p for p in index.get("presets", []) if p.get("id") == preset_id), {})
    votes = load_votes(preset_id)
    key = vote_key(voter)
    before = votes.get(key)
    votes[key] = {
        "score": score,
        "rev": entry.get("revision", 1),
        "via": voter.split(":", 1)[0],
        "at": iso(now_utc()),
    }
    save_votes(preset_id, votes)
    if build(quiet=True) != 0:
        return finish("评分已写入，但重建索引失败，请查看 Actions 日志。", 1)

    rating = next(p for p in read_json(INDEX_PATH)["presets"] if p["id"] == preset_id)["rating"]
    title = entry.get("title") or preset_id
    replaced = f"（已覆盖你之前的 {before['score']} 分）" if before and before["score"] != score else ""
    return finish(
        f"感谢评分！已记录 **{title}**（`{preset_id}`）：{'★' * score} {score} 分{replaced}。\n\n"
        f"该预设现有 {rating['count']} 票，平均 {rating['average']} 分。"
        f"每个账号对同一预设只计一票，再次提交会覆盖。",
        0,
    )


def cmd_purge_seed(_args) -> int:
    removed = 0
    for folder in list_preset_dirs():
        votes = load_votes(folder.name)
        kept = {k: v for k, v in votes.items() if v.get("via") != "seed"}
        if len(kept) != len(votes):
            removed += len(votes) - len(kept)
            save_votes(folder.name, kept)
    print(f"已删除 {removed} 条测试评分。")
    return build()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HXAudio Pro 云端预设仓库工具")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate", help="只校验，不写文件").set_defaults(func=cmd_validate)

    p = sub.add_parser("build", help="校验并重新生成 api/v1/*")
    p.add_argument("--check", action="store_true", help="生成物不是最新时失败，不写文件")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("add", help="从 App 导出的 .hx4 新建或替换预设")
    p.add_argument("file")
    p.add_argument("--id", required=True)
    p.add_argument("--replace", action="store_true", help="只替换曲线，保留 meta.json")
    p.add_argument("--title")
    p.add_argument("--subtitle")
    p.add_argument("--description")
    p.add_argument("--author", default="HXAudio 官方")
    p.add_argument("--tags", help="逗号分隔")
    p.add_argument("--kinds", help=f"逗号分隔：{','.join(DEVICE_KINDS)}")
    p.add_argument("--featured", action="store_true")
    p.add_argument("--model", action="append", default=[], metavar="KIND:名称[,别名…]",
                   help="适配机型，可重复，例如 --model BLUETOOTH:WH-1000XM5 或 --model SPEAKER:Xiaomi 15,24129PN74C")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("rate", help="记录一票（同一投票人重复投票会覆盖）")
    p.add_argument("preset_id", nargs="?")
    p.add_argument("score", nargs="?", type=int)
    p.add_argument("--voter", help="app:… / gh:… / manual:… / seed:…")
    p.add_argument("--from-issue", action="store_true", help="从 ISSUE_BODY 与 HXCLOUD_VOTER 读取")
    p.add_argument("--from-payload", action="store_true", help="从 HXCLOUD_PAYLOAD 与 HXCLOUD_VIA 读取")
    p.set_defaults(func=cmd_rate)

    sub.add_parser("purge-seed", help="删除内置测试评分").set_defaults(func=cmd_purge_seed)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
