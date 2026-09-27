#!/usr/bin/env python3
"""AI-EqfLow MCP server (stdio, JSON-RPC 2.0) — stable edition.

Tools:
    aieqflow_quota          余额预检
    aieqflow_list_models    模型列表（支持 ASCII 别名过滤）
    aieqflow_chat           文本对话（自动预检）
    aieqflow_generate_image 图像生成（自动预检 + 400 参数剔除重试 + 魔数纠扩展名）
    aieqflow_generate_video 视频生成（按厂商路由：Seedance/Hailuo/Kling，提交+短轮询）
    aieqflow_video_status   视频任务状态查询 / 成片下载
    aieqflow_tts            MiniMax 同步语音合成（t2a_v2，hex 音频落盘 mp3）

Auth: AIEQFLOW_API_KEY（.env 回退）。BASE: API_BASE（默认 https://aieqflow.com/v1）
"""

from __future__ import annotations

import base64
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# MCP stdio 按规范应为 UTF-8；Windows 默认 cp936 会弄乱中文参数与输出。
for _stream in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from aieqflow_client import (  # noqa: E402
    DEFAULT_BASE_URL,
    AIEqFlowClient,
    AIEqFlowError,
    _load_env_file,
    env_str,
    mask,
)

SERVER_NAME = "ai-eqflow"
SERVER_VERSION = "0.3.0"
PROTOCOL_VERSION = "2024-11-05"
POINTS_PER_USD = 500000.0

_load_env_file()

KEY_ENV = env_str("MCP_KEY_ENV") or "AIEQFLOW_API_KEY"
BASE_URL = (env_str("API_BASE") or DEFAULT_BASE_URL).rstrip("/")
try:
    MIN_QUOTA = float(env_str("MIN_QUOTA_USD") or "1.0")
except ValueError:
    MIN_QUOTA = 1.0

# ASCII 别名 -> API 返回的 model_type（Windows 通道传中文易乱码，别名最稳）
TYPE_ALIASES = {
    "chat": "对话", "text": "对话", "llm": "对话", "对话": "对话",
    "image": "图像", "img": "图像", "图像": "图像",
    "video": "音视频", "audio": "音视频", "av": "音视频", "音视频": "音视频",
    "embedding": "检索", "embed": "检索", "检索": "检索",
}

# OpenAI 兼容生图：各模型对可选参数支持不一，400 报 Unknown parameter 时剔除重试
_UNKNOWN_PARAM_RE = re.compile(r"Unknown parameter:\s*'([^']+)'")
_DROPPABLE_PARAMS = ("response_format", "quality", "size", "n", "style", "background")
_IMAGE_MAGIC = ((b"\xff\xd8\xff", ".jpg"), (b"\x89PNG\r\n\x1a\n", ".png"),
                (b"GIF87a", ".gif"), (b"GIF89a", ".gif"), (b"BM", ".bmp"))

DEFAULT_IMAGE_MODEL = "gpt-image-2.5-sunburst"
FALLBACK_IMAGE_MODELS = ("gpt-image-2.5-flare", "gpt-image-2", "gpt-image-1.5")

# 视频生成：任务式 /video/generations 优先，Sora 式 /videos 兜底（new-api 双风格）
DEFAULT_VIDEO_MODELS = (
    "doubao-seedance-2-5-260628", "doubao-seedance-2-0-260128",
    "happyhorse-1.1-t2v", "kling-3.0-turbo", "MiniMax-Hailuo-2.3",
)
_VIDEO_KEYWORDS = ("seedance", "kling", "hailuo", "happyhorse", "vidu", "sora", "video", "wan", "pixverse")
_VIDEO_OK = {"succeeded", "success", "completed", "complete"}
_VIDEO_BAD = {"failed", "failure", "error", "cancelled", "canceled"}


def client() -> AIEqFlowClient:
    return AIEqFlowClient(base_url=BASE_URL)


# ---------------------------------------------------------------- quota
def quota_report() -> str:
    try:
        c = client()
    except RuntimeError as e:
        return f"错误：{e}（请设置环境变量 {KEY_ENV}）"
    try:
        d = c.get_token_usage()
        data = d.get("data") or {}
        unlimited = bool(data.get("unlimited_quota"))
        used = float(data.get("total_used") or 0)
        avail = float(data.get("total_available") or 0)
        lines = [
            f"令牌名称     : {data.get('name')}",
            f"unlimited    : {unlimited}",
            f"total_used   : {used:.0f} 点 (≈ ${used / POINTS_PER_USD:.4f})",
        ]
        if unlimited:
            lines.append("判定         : 不限额度，余额预检通过")
        else:
            lines.append(f"total_available: {avail:.0f} 点 (≈ ${avail / POINTS_PER_USD:.4f})")
            lines.append("判定         : " + ("余额充足" if avail / POINTS_PER_USD >= MIN_QUOTA
                                              else f"余额不足（< {MIN_QUOTA:g} USD）"))
        return "\n".join(lines)
    except AIEqFlowError as e:
        bill = c.get_billing()
        return (f"/api/usage/token 不可用（{e.status}），改用 billing 接口：\n"
                f"token_name={bill.get('token_name')!r} used_usd={bill.get('used_usd')} "
                f"hard_limit_usd={bill.get('hard_limit_usd')}")
    except RuntimeError as e:
        return f"错误：{e}（请设置环境变量 {KEY_ENV}）"


def quota_ok() -> tuple[bool, str]:
    try:
        c = client()
    except RuntimeError as e:
        return False, str(e)
    try:
        d = c.get_token_usage()
        data = d.get("data") or {}
        if data.get("unlimited_quota"):
            return True, "unlimited_quota=true"
        avail = float(data.get("total_available") or 0) / POINTS_PER_USD
        if avail < MIN_QUOTA:
            return False, f"余额不足：剩余 ${avail:.4f} < 阈值 ${MIN_QUOTA:g}"
        return True, f"剩余 ${avail:.4f}"
    except AIEqFlowError:
        return False, "无法核算余额（/api/usage/token 不可用）"
    except RuntimeError as e:
        return False, str(e)


# ---------------------------------------------------------------- helpers
def _norm_type(raw: str) -> str:
    key = (raw or "").strip().lower()
    return TYPE_ALIASES.get(key, (raw or "").strip())


def _unknown_param(msg: str) -> str | None:
    m = _UNKNOWN_PARAM_RE.search(msg or "")
    return m.group(1) if m else None


def _sniff_image_ext(data: bytes) -> str | None:
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    for magic, ext in _IMAGE_MAGIC:
        if data.startswith(magic):
            return ext
    return None


def _download_b64_image(b64: str, save_path: str) -> str:
    data = base64.b64decode(b64)
    path = Path(save_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    real = _sniff_image_ext(data)
    if real and path.suffix.lower() != real:
        path = path.with_suffix(real)
    path.write_bytes(data)
    return str(path)


def _download_url_image(url: str, save_path: str) -> str:
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "aieqflow-mcp/0.1"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    path = Path(save_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    real = _sniff_image_ext(data)
    if real and path.suffix.lower() != real:
        path = path.with_suffix(real)
    path.write_bytes(data)
    return str(path)


def _pick_image_model(c: AIEqFlowClient, requested: str) -> str:
    models = c.list_models()
    ids = [m["id"] for m in models if m.get("model_type") == "图像"]
    if requested:
        return requested if requested in ids else requested  # 用户显式指定则尊重
    for cand in (DEFAULT_IMAGE_MODEL, *FALLBACK_IMAGE_MODELS):
        if cand in ids:
            return cand
    if not ids:
        # fallback：站点未标注 model_type 时，退回支持 openai 端点的模型
        ids = [m["id"] for m in models if "openai" in (m.get("supported_endpoint_types") or [])]
    return ids[0] if ids else DEFAULT_IMAGE_MODEL


def _req(c: AIEqFlowClient, method: str, path: str, body: dict | None = None) -> dict:
    """专线路由（/minimax /kling /runwayml /api/v3）挂在站点根而非 /v1 下。"""
    saved = c.base_url
    if path.startswith(("/minimax/", "/kling/", "/runwayml/", "/api/v3/")):
        root = saved[:-3] if saved.endswith("/v1") else saved
        c.base_url = root
    try:
        return c._request_json(method, path, body)
    finally:
        c.base_url = saved


# ---------------------------------------------------------------- video helpers
def _sniff_video_ext(data: bytes) -> str | None:
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return ".mp4"
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return ".webm"
    if data.startswith(b"FLV"):
        return ".flv"
    return None


def _download_video(url: str, save_path: str, c: AIEqFlowClient) -> str:
    import urllib.request
    from urllib.parse import urlparse
    path = Path(save_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if url.startswith("/"):
        url = c.base_url + url
    # 站内 content/retrieve 端点需要 Bearer；外部预签名 URL（S3/OSS）带鉴权头反而 400
    host = urlparse(url).netloc
    internal = host in (urlparse(c.base_url).netloc,
                        urlparse(c.base_url[:-3] if c.base_url.endswith("/v1") else c.base_url).netloc)
    headers = {"User-Agent": "aieqflow-mcp/0.3"}
    if internal:
        headers["Authorization"] = f"Bearer {c.api_key}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = resp.read()
    real = _sniff_video_ext(data)
    if real and path.suffix.lower() != real:
        path = path.with_suffix(real)
    path.write_bytes(data)
    return str(path)


def _pick_video_model(c: AIEqFlowClient, requested: str) -> str:
    if requested:
        return requested
    models = c.list_models()
    vids = [m["id"] for m in models if m.get("model_type") == "音视频"]
    for cand in DEFAULT_VIDEO_MODELS:
        if cand in vids:
            return cand
    kw = [i for i in vids if any(k in i.lower() for k in _VIDEO_KEYWORDS)]
    pool = kw or vids
    return pool[0] if pool else DEFAULT_VIDEO_MODELS[0]


def _video_vendor(model: str) -> str:
    m = (model or "").lower()
    if "hailuo" in m or "minimax" in m:
        return "minimax"
    if "kling" in m:
        return "kling"
    if "seedance" in m or "doubao" in m:
        return "seedance"
    return "generic"


def _video_ok(resp: dict) -> bool:
    """跨厂商判断任务是否成功（base_resp 站点错误优先）。"""
    br = resp.get("base_resp") or {}
    if isinstance(br, dict) and br.get("status_code") not in (None, 0):
        return False
    st = _video_status(resp)
    return st in _VIDEO_OK


def _video_failed(resp: dict) -> bool:
    br = resp.get("base_resp") or {}
    if isinstance(br, dict) and br.get("status_code") not in (None, 0):
        return True
    st = _video_status(resp)
    st2 = str(resp.get("data", {}).get("status") if isinstance(resp.get("data"), dict) else "").lower()
    return st in _VIDEO_BAD or st2 in _VIDEO_BAD


def _extract_task_id(resp: dict) -> str | None:
    for k in ("task_id", "id", "video_id"):
        v = resp.get(k)
        if v:
            return str(v)
    data = resp.get("data")
    if isinstance(data, dict):
        for k in ("task_id", "id"):
            v = data.get(k)
            if v:
                return str(v)
    return None


def _video_url(resp: dict) -> str | None:
    """跨厂商提取成片 URL。"""
    candidates = []
    u = resp.get("url") or resp.get("video_url") or resp.get("download_url")
    if u:
        candidates.append(u)
    content = resp.get("content")
    if isinstance(content, dict):
        candidates.append(content.get("video_url") or content.get("url"))
    data = resp.get("data")
    if isinstance(data, dict):
        f = data.get("file")
        if isinstance(f, dict):
            candidates.append(f.get("download_url") or f.get("url"))
        tr = data.get("task_result")
        if isinstance(tr, dict):
            vids = tr.get("videos") or []
            if vids and isinstance(vids[0], dict):
                candidates.append(vids[0].get("url"))
        candidates.append(data.get("video_url") or data.get("url"))
    f = resp.get("file")
    if isinstance(f, dict):
        candidates.append(f.get("download_url") or f.get("url"))
    for u in candidates:
        if u:
            return str(u)
    return None


def _submit_video(c: AIEqFlowClient, model: str, prompt: str, args: dict) -> tuple[str, str, str]:
    """按厂商路由提交视频任务。返回 (task_id, vendor, 轮询上下文)。"""
    image = (args.get("image") or "").strip()
    vendor = _video_vendor(model)
    duration = args.get("duration")
    resolution = args.get("resolution")
    ratio = args.get("ratio")

    if vendor == "minimax":
        body = {"model": model, "prompt": prompt}
        if duration:
            body["duration"] = int(duration)
        if resolution:
            body["resolution"] = str(resolution).upper()
        resp = _req(c, "POST", "/minimax/v1/video_generation", body)
        task_id = _extract_task_id(resp)
        return task_id, vendor, "minimax"

    if vendor == "kling":
        action = "image2video" if image else "text2video"
        body = {"model_name": model, "prompt": prompt}
        if image:
            body["image"] = image
        if duration:
            body["duration"] = str(duration)
        resp = _req(c, "POST", f"/kling/v1/videos/{action}", body)
        task_id = _extract_task_id(resp)
        return task_id, vendor, f"kling:{action}"

    if vendor == "seedance":
        content: list[dict] = [{"type": "text", "text": prompt}]
        if image:
            content.append({"type": "image_url", "image_url": {"url": image},
                            "role": "reference_image"})
        body: dict = {"model": model, "content": content}
        meta = {}
        if duration:
            meta["duration"] = int(duration)
        if resolution:
            meta["resolution"] = str(resolution)
        if ratio:
            meta["ratio"] = str(ratio)
        if meta:
            body["metadata"] = meta
        # VEO 统一通道（content+metadata）
        try:
            resp = _req(c, "POST", "/video/generations", body)
            task_id = _extract_task_id(resp)
            if task_id:
                return task_id, vendor, "unified"
        except AIEqFlowError:
            pass
        # 平铺参数重试（prompt 风格）
        flat: dict = {"model": model, "prompt": prompt}
        if duration:
            flat["duration"] = int(duration)
        if resolution:
            flat["resolution"] = str(resolution)
        if ratio:
            flat["ratio"] = str(ratio)
        if image:
            flat["image"] = image
        try:
            resp = _req(c, "POST", "/video/generations", flat)
            task_id = _extract_task_id(resp)
            if task_id:
                return task_id, vendor, "unified"
        except AIEqFlowError:
            pass
        # Ark v3 兜底
        resp = _req(c, "POST", "/api/v3/contents/generations/tasks", body)
        task_id = _extract_task_id(resp)
        return task_id, vendor, "arkv3"

    # generic：/video/generations 平铺 → Sora 式 /videos
    flat = {"model": model, "prompt": prompt}
    for k in ("duration", "resolution", "size", "ratio", "seconds", "image"):
        if args.get(k) is not None:
            flat[k] = args[k]
    try:
        resp = _req(c, "POST", "/video/generations", flat)
        task_id = _extract_task_id(resp)
        if task_id:
            return task_id, vendor, "generic"
    except AIEqFlowError as e:
        if e.status not in (400, 404, 422):
            raise
    sora = {"model": model, "prompt": prompt}
    if args.get("seconds"):
        sora["seconds"] = str(args["seconds"])
    if args.get("size"):
        sora["size"] = args["size"]
    resp = _req(c, "POST", "/videos", sora)
    return _extract_task_id(resp), vendor, "sora"


def _poll_video(c: AIEqFlowClient, task_id: str, vendor: str, ctx: str) -> dict:
    if vendor == "minimax":
        return _req(c, "GET", f"/minimax/v1/query/video_generation?task_id={task_id}")
    if vendor == "kling":
        action = ctx.split(":", 1)[1] if ":" in ctx else "text2video"
        for a in ({action, "text2video", "image2video"} - {None}):
            try:
                return _req(c, "GET", f"/kling/v1/videos/{a}/{task_id}")
            except AIEqFlowError:
                continue
        raise AIEqFlowError(404, f"kling task not found: {task_id}")
    paths = {
        "unified": [f"/video/generations/{task_id}", f"/api/v3/contents/generations/tasks/{task_id}"],
        "arkv3": [f"/api/v3/contents/generations/tasks/{task_id}", f"/video/generations/{task_id}"],
        "generic": [f"/video/generations/{task_id}", f"/videos/{task_id}"],
        "sora": [f"/videos/{task_id}", f"/video/generations/{task_id}"],
    }.get(ctx, [f"/video/generations/{task_id}", f"/api/v3/contents/generations/tasks/{task_id}"])
    last: Exception | None = None
    for p in paths:
        try:
            return _req(c, "GET", p)
        except AIEqFlowError as e:
            last = e
    raise last if last else RuntimeError("poll failed")


def _resolve_video_url(c: AIEqFlowClient, resp: dict) -> str | None:
    url = _video_url(resp)
    if url:
        return url
    # MiniMax：仅有 file_id 时走 files/retrieve
    fid = resp.get("file_id")
    data = resp.get("data")
    if not fid and isinstance(data, dict):
        f = data.get("file") or {}
        fid = data.get("file_id") or f.get("file_id")
    if fid:
        try:
            r2 = _req(c, "GET", f"/minimax/v1/files/retrieve?file_id={fid}")
            return _video_url(r2)
        except AIEqFlowError:
            return None
    return None


def _video_status(resp: dict) -> str:
    st = str(resp.get("status") or resp.get("state") or "").strip().lower()
    if not st:
        data = resp.get("data")
        if isinstance(data, dict):
            st = str(data.get("status") or "").strip().lower()
    return st


# ---------------------------------------------------------------- tools
def tool_quota(_args: dict) -> str:
    return quota_report()


def tool_list_models(args: dict) -> str:
    c = client()
    models = c.list_models()
    raw = (args.get("model_type") or "").strip()
    mt = _norm_type(raw) if raw else ""
    limit = int(args.get("limit") or 60)
    if mt:
        models = [m for m in models if (m.get("model_type") or "") == mt]
    out = [f"共 {len(models)} 个模型" + (f"（已过滤 model_type={mt}）" if mt else "")]
    for m in models[:limit]:
        out.append(f"- {m.get('id')} | {m.get('model_type')} | {','.join(m.get('supported_endpoint_types') or []) or '-'}")
    if len(models) > limit:
        out.append(f"... 其余 {len(models) - limit} 个已省略")
    return "\n".join(out)


def tool_chat(args: dict) -> str:
    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        return "错误：prompt 不能为空"
    ok, why = quota_ok()
    if not ok:
        return f"已拒绝调用：{why}"

    c = client()
    model = (args.get("model") or "").strip()
    if not model:
        ids = c.find_chat_models()
        if not ids:
            return "错误：模型列表中没有对话类型模型，请显式指定 model"
        model = ids[0]

    messages = []
    if args.get("system"):
        messages.append({"role": "system", "content": args["system"]})
    messages.append({"role": "user", "content": prompt})

    try:
        resp = c.chat(messages, model=model,
                      max_tokens=int(args.get("max_tokens") or 1024),
                      temperature=float(args.get("temperature", 0.7)))
    except AIEqFlowError as e:
        return f"调用失败：{e}"
    content = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    usage = resp.get("usage") or {}
    return (f"model: {model}\n"
            f"preflight: {why}\n"
            f"usage: prompt={usage.get('prompt_tokens')} completion={usage.get('completion_tokens')} "
            f"total={usage.get('total_tokens')}\n\n{content}")


def tool_generate_image(args: dict) -> str:
    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        return "错误：prompt 不能为空"
    save_path = (args.get("save_path") or "").strip()
    if not save_path:
        return "错误：save_path 不能为空（绝对路径，如 E:/out/poster.png）"
    ok, why = quota_ok()
    if not ok:
        return f"已拒绝调用：{why}"

    c = client()
    try:
        model = _pick_image_model(c, (args.get("model") or "").strip())
    except AIEqFlowError as e:
        return f"获取模型列表失败：{e}"

    optional = {"size": args.get("size"), "quality": args.get("quality"),
                "response_format": args.get("response_format")}
    dropped, b64, url, err = [], None, None, None
    for _ in range(len(_DROPPABLE_PARAMS) + 2):
        kwargs = {k: v for k, v in optional.items() if v is not None and k not in dropped}
        try:
            resp = _req(c, "POST", "/images/generations",
                                   {"model": model, "prompt": prompt, **kwargs})
            item = (resp.get("data") or [{}])[0]
            b64, url = item.get("b64_json"), item.get("url")
            if not b64 and not url:
                err = f"响应无图像数据：{json.dumps(resp, ensure_ascii=False)[:300]}"
                continue
            break
        except AIEqFlowError as e:
            bad = _unknown_param(str(e))
            if e.status == 400 and bad and bad in _DROPPABLE_PARAMS and bad not in dropped:
                dropped.append(bad)
                continue
            if e.status == 503:
                nxt = [m for m in (DEFAULT_IMAGE_MODEL, *FALLBACK_IMAGE_MODELS) if m != model]
                if nxt:
                    model = nxt[0]
                    continue
            err = f"调用失败：{e}"
            break
    if not b64 and not url:
        return f"生图失败：{err or '未知错误'}"

    try:
        final = _download_b64_image(b64, save_path) if b64 else _download_url_image(url, save_path)
    except Exception as e:  # noqa: BLE001
        return f"图像已生成但保存失败：{e}\nurl: {url}"
    notes = f"param_degraded: {dropped}" if dropped else "-"
    return f"model: {model}\npreflight: {why}\n{notes}\nsaved: {final}"


def tool_generate_video(args: dict) -> str:
    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        return "错误：prompt 不能为空"
    save_path = (args.get("save_path") or "").strip()
    if not save_path:
        return "错误：save_path 不能为空（绝对路径，如 E:/out/clip.mp4）"
    image = (args.get("image") or "").strip()
    if image and not image.lower().startswith(("http://", "https://")):
        return "错误：image 须为可公网访问的 URL（站点不支持上传本地文件做图生视频）"
    ok, why = quota_ok()
    if not ok:
        return f"已拒绝调用：{why}"

    c = client()
    try:
        model = _pick_video_model(c, (args.get("model") or "").strip())
    except AIEqFlowError as e:
        return f"获取模型列表失败：{e}"

    try:
        task_id, vendor, ctx = _submit_video(c, model, prompt, args)
    except AIEqFlowError as e:
        return (f"提交失败：{e}\n提示：确认模型 ID 是否为该站音视频模型"
                f"（可用 aieqflow_list_models model_type=video 查看）")
    if not task_id:
        return f"提交响应无 task_id：{model}"

    # 短轮询：最多约 20 秒，超时返回 task_id 交给 aieqflow_video_status
    try:
        resp = _poll_video(c, task_id, vendor, ctx)
    except AIEqFlowError as e:
        return f"task_id: {task_id}\n首次轮询失败：{e}"
    for _ in range(2):
        if _video_ok(resp) or _video_failed(resp):
            break
        time.sleep(8)
        try:
            resp = _poll_video(c, task_id, vendor, ctx)
        except AIEqFlowError as e:
            return f"task_id: {task_id}\n轮询失败：{e}"

    if _video_failed(resp):
        err = resp.get("error") or resp.get("fail_reason") or resp.get("message") or ""
        return f"任务失败：task_id={task_id} status={_video_status(resp)} {err}"
    if _video_ok(resp):
        url = _resolve_video_url(c, resp)
        if not url:
            return f"任务完成但未返回视频 URL：{json.dumps(resp, ensure_ascii=False)[:300]}"
        try:
            final = _download_video(url, save_path, c)
        except Exception as e:  # noqa: BLE001
            return f"视频已生成但保存失败：{e}\nurl: {url}"
        return f"model: {model}\nvendor: {vendor}\nsaved: {final}"

    return (f"已提交，仍在生成中（视频通常需要 1-5 分钟）\n"
            f"task_id: {task_id}\nstatus: {_video_status(resp) or 'unknown'}\n"
            f"model: {model}\nvendor: {vendor}\n"
            f"稍后调用 aieqflow_video_status(task_id, save_path) 取片")


def tool_video_status(args: dict) -> str:
    task_id = (args.get("task_id") or "").strip()
    if not task_id:
        return "错误：task_id 不能为空（来自 aieqflow_generate_video 的返回）"
    vendor = (args.get("vendor") or "").strip().lower()
    c = client()
    try:
        resp = _poll_video(c, task_id, vendor, "generic")
    except AIEqFlowError:
        try:
            resp = _poll_video(c, task_id, "minimax", "minimax")
        except AIEqFlowError as e:
            return f"查询失败：{e}（确认 task_id 是否正确）"
    if _video_failed(resp):
        return f"任务失败：status={_video_status(resp)} {resp.get('error') or resp.get('fail_reason') or ''}"
    if not _video_ok(resp):
        progress = resp.get("progress", "-")
        return f"仍在生成中：status={_video_status(resp)} progress={progress}（稍后再查）"
    url = _resolve_video_url(c, resp)
    if not url:
        return f"任务完成但未返回视频 URL：{json.dumps(resp, ensure_ascii=False)[:300]}"
    save_path = (args.get("save_path") or "").strip()
    if not save_path:
        return f"任务完成。\nurl: {url}\n（提供 save_path 可直接下载到本地）"
    try:
        final = _download_video(url, save_path, c)
    except Exception as e:  # noqa: BLE001
        return f"下载失败（可稍后重试或手动下载）：{e}\nurl: {url}"
    return f"saved: {final}"


def tool_tts(args: dict) -> str:
    """MiniMax 同步语音合成（t2a_v2）：text → hex 音频 → 本地 mp3。"""
    text = (args.get("text") or "").strip()
    if not text:
        return "错误：text 不能为空"
    save_path = (args.get("save_path") or "").strip()
    if not save_path:
        return "错误：save_path 不能为空（绝对路径，如 E:/out/voice.mp3）"
    ok, why = quota_ok()
    if not ok:
        return f"已拒绝调用：{why}"
    c = client()
    voice_setting = {"voice_id": (args.get("voice_id") or "male-qn-qingse")}
    for k in ("speed", "vol", "pitch"):
        if args.get(k) is not None:
            voice_setting[k] = args[k]
    body = {
        "model": (args.get("model") or "speech-02-hd"),
        "text": text,
        "voice_setting": voice_setting,
    }
    if args.get("language_boost"):
        body["language_boost"] = args["language_boost"]
    try:
        resp = _req(c, "POST", "/minimax/v1/t2a_v2", body)
    except AIEqFlowError as e:
        return f"合成失败：{e}"
    br = resp.get("base_resp") or {}
    if br.get("status_code") not in (None, 0):
        return f"合成失败：{br.get('status_code')} {br.get('status_msg')}"
    audio_hex = (resp.get("data") or {}).get("audio")
    if not audio_hex:
        return f"响应无音频数据：{json.dumps(resp, ensure_ascii=False)[:300]}"
    try:
        data = bytes.fromhex(audio_hex)
    except ValueError:
        return "音频数据不是合法 hex（可能返回 url，请把响应反馈给开发者）"
    path = Path(save_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() != ".mp3":
        path = path.with_suffix(".mp3")
    path.write_bytes(data)
    extra = resp.get("extra_info") or {}
    return (f"model: {body['model']}\nvoice: {voice_setting['voice_id']}\n"
            f"chars: {extra.get('usage_characters', '-')}\nsaved: {path}")


HANDLERS = {
    "aieqflow_quota": tool_quota,
    "aieqflow_list_models": tool_list_models,
    "aieqflow_chat": tool_chat,
    "aieqflow_generate_image": tool_generate_image,
    "aieqflow_generate_video": tool_generate_video,
    "aieqflow_video_status": tool_video_status,
    "aieqflow_tts": tool_tts,
}

TOOLS = [
    {
        "name": "aieqflow_quota",
        "description": "查询 AI-EqfLow (aieqflow.com) 令牌余额与用量（余额预检）。返回 unlimited_quota、total_available、total_used 与换算后的美元额度。",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "aieqflow_list_models",
        "description": "列出 AI-EqfLow 当前令牌可用的模型。可按 model_type 过滤：chat/对话、image/图像、video/音视频、embedding/检索（推荐用 ASCII 别名）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_type": {"type": "string", "description": "类型过滤，推荐 ASCII 别名：chat/image/video/embedding"},
                "limit": {"type": "integer", "description": "最多返回条数，默认 60", "default": 60},
            },
            "required": [],
        },
    },
    {
        "name": "aieqflow_chat",
        "description": "通过 AI-EqfLow 调用文本对话接口。执行前会自动做余额预检，余额不足则拒绝调用。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "用户提示词"},
                "model": {"type": "string", "description": "模型 ID；留空则自动挑选第一个可用对话模型"},
                "system": {"type": "string", "description": "可选 system 提示词"},
                "temperature": {"type": "number", "description": "采样温度，默认 0.7"},
                "max_tokens": {"type": "integer", "description": "最大输出 token，默认 1024"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "aieqflow_generate_image",
        "description": "通过 AI-EqfLow 文生图（OpenAI images 接口）。默认模型 gpt-image-2.5-sunburst，不可用时按 flare→gpt-image-2→gpt-image-1.5 降级。可选参数被模型拒收时自动剔除重试。",
        "inputSchema": {
            "type": "object",
            "required": ["prompt", "save_path"],
            "properties": {
                "prompt": {"type": "string", "description": "画面描述（中文海报请写清文案、版式、比例）"},
                "save_path": {"type": "string", "description": "本地保存绝对路径，如 E:/out/poster.png"},
                "model": {"type": "string", "description": "图像模型 ID；留空自动选"},
                "size": {"type": "string", "description": "如 1024x1536；模型拒收则自动剔除"},
                "quality": {"type": "string", "description": "如 high；模型拒收则自动剔除"},
                "response_format": {"type": "string", "description": "留空即可；模型拒收则自动剔除"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "aieqflow_generate_video",
        "description": "通过 AI-EqfLow 文生视频/图生视频（异步任务）。默认自动挑选 Seedance/Happyhorse/Kling/Hailuo 等视频模型；提交后短轮询约 20 秒，未完成则返回 task_id，用 aieqflow_video_status 取片。视频按秒计费，成本高于生图。",
        "inputSchema": {
            "type": "object",
            "required": ["prompt", "save_path"],
            "properties": {
                "prompt": {"type": "string", "description": "画面与声音描述（Seedance 支持原生音频，可写明环境音/台词）"},
                "save_path": {"type": "string", "description": "本地保存绝对路径，如 E:/out/clip.mp4"},
                "model": {"type": "string", "description": "视频模型 ID；留空自动选（优先 doubao-seedance-2-5）"},
                "image": {"type": "string", "description": "图生视频参考图 URL（可选，须公网可访问）"},
                "duration": {"type": "integer", "description": "时长秒数（可选，模型支持范围不一，如 5/10）"},
                "resolution": {"type": "string", "description": "分辨率（可选，如 480p/720p/1080p）"},
                "size": {"type": "string", "description": "尺寸（可选，如 768P/2K 或 1280x720）"},
                "ratio": {"type": "string", "description": "宽高比（可选，如 16:9、9:16）"},
                "seconds": {"type": "integer", "description": "时长（Sora 式模型用，如 sora 系 4/8/12）"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "aieqflow_video_status",
        "description": "查询 AI-EqfLow 视频生成任务状态；完成时可直接下载成片到本地。兼容 Seedance/Hailuo/Kling 各厂商任务。",
        "inputSchema": {
            "type": "object",
            "required": ["task_id"],
            "properties": {
                "task_id": {"type": "string", "description": "aieqflow_generate_video 返回的任务 ID"},
                "vendor": {"type": "string", "description": "可选：seedance/minimax/kling；留空自动尝试各通道"},
                "save_path": {"type": "string", "description": "可选；任务完成时下载保存的绝对路径"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "aieqflow_tts",
        "description": "MiniMax 同步语音合成（t2a_v2）：文本转语音并保存为本地 mp3。按字符计费。",
        "inputSchema": {
            "type": "object",
            "required": ["text", "save_path"],
            "properties": {
                "text": {"type": "string", "description": "要合成的文本"},
                "save_path": {"type": "string", "description": "本地保存绝对路径，如 E:/out/voice.mp3"},
                "voice_id": {"type": "string", "description": "音色 ID；默认 male-qn-qingse，克隆音色填自定义 voice_id"},
                "model": {"type": "string", "description": "合成模型，默认 speech-02-hd"},
                "language_boost": {"type": "string", "description": "语言增强，如 Chinese/English/auto"},
                "speed": {"type": "number", "description": "语速 0.5-2，默认 1"},
                "vol": {"type": "number", "description": "音量 0.1-10，默认 1"},
                "pitch": {"type": "integer", "description": "音调 -12~12，默认 0"},
            },
            "additionalProperties": False,
        },
    },
]


# ---------------------------------------------------------------- json-rpc
def respond(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def ok(id_, result):
    respond({"jsonrpc": "2.0", "id": id_, "result": result})


def err(id_, code: int, message: str):
    respond({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}})


def text_result(payload: str, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": payload}], "isError": is_error}


def handle(req: dict) -> None:
    method = req.get("method")
    id_ = req.get("id")
    if method == "initialize":
        ok(id_, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
        return
    if method == "tools/list":
        ok(id_, {"tools": TOOLS})
        return
    if method == "tools/call":
        params = req.get("params") or {}
        fn = HANDLERS.get(params.get("name"))
        if not fn:
            err(id_, -32601, f"unknown tool: {params.get('name')}")
            return
        try:
            ok(id_, text_result(fn(params.get("arguments") or {})))
        except Exception as e:  # noqa: BLE001
            ok(id_, text_result(f"工具执行异常：{type(e).__name__}: {e}", is_error=True))
        return
    if method and method.startswith("notifications/"):
        return
    if id_ is not None:
        err(id_, -32601, f"method not found: {method}")


def main() -> None:
    key = env_str(KEY_ENV)
    if not key:
        sys.stderr.write(f"[ai-eqflow-mcp] 警告：{KEY_ENV} 未设置且无 .env 回退，工具将报错\n")
    else:
        sys.stderr.write(f"[ai-eqflow-mcp] key={mask(key)} base={BASE_URL}\n")
    sys.stderr.flush()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        handle(req)


if __name__ == "__main__":
    main()
