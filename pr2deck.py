import argparse
import hashlib
import html as html_lib
import json
import os
import re
import sys
import time
import unicodedata

import requests

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


GITHUB_REPO = os.getenv("GITHUB_REPO") or "deepmodeling/abacus-develop"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
LLM_API_KEY = os.getenv("LLM_API_KEY") or DEEPSEEK_API_KEY
LLM_API_BASE_URL = os.getenv("LLM_API_BASE_URL") or os.getenv("OPENAI_BASE_URL") or (
    "https://api.deepseek.com" if DEEPSEEK_API_KEY else ""
)
LLM_MODEL = os.getenv("LLM_MODEL") or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
PROMPT_FILE = os.getenv("PR2DECK_PROMPT_FILE", "prompt.txt")
HAS_LLM_CLIENT = bool(LLM_API_KEY and LLM_API_KEY.lower() != "none" and OpenAI)

HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN and GITHUB_TOKEN.lower() != "none" else {}
AVATAR_DIR = "avatars"
CACHE_FILE = os.getenv("PR_CACHE_FILE", ".pr_cache.json")
CACHE_TTL = int(os.getenv("PR_CACHE_TTL", "86400"))
MODEL_CACHE_FILE = os.getenv("MODEL_CACHE_FILE", ".model_cache.json")
MODEL_CACHE_TTL = int(os.getenv("MODEL_CACHE_TTL", "604800"))

TITLE = "ABACUS Changelog"
MAX_DESC_LINES_PER_CARD = 8
MAX_DESC_CHARS = 76
TITLE_WRAP_WIDTH = 34
DESC_WRAP_WIDTH = 52
LAYOUT_PAGE_WIDTH = 1600
LAYOUT_PAGE_HEIGHT = 900
LAYOUT_PAGE_PADDING = 48
LAYOUT_HEADER_HEIGHT = 52
LAYOUT_HEADER_MARGIN_BOTTOM = 30
LAYOUT_CARD_GAP = 18
LAYOUT_CARD_PADDING_Y = 22
LAYOUT_CARD_CONTENT_WIDTH = 1340
LAYOUT_META_LINE_HEIGHT = 22
LAYOUT_DESC_FONT_SIZE = 28
LAYOUT_DESC_LINE_HEIGHT = 1.38
LAYOUT_DESC_MARGIN_TOP = 14
LAYOUT_DESC_MAX_LINES = 2
LAYOUT_TITLE_FONT_SIZE = 18
LAYOUT_TITLE_LINE_HEIGHT = 1.28
LAYOUT_TITLE_MARGIN_TOP = 8
LAYOUT_TITLE_MAX_LINES = 1
LAYOUT_TITLE_ONLY_FONT_SIZE = 28
LAYOUT_TITLE_ONLY_MAX_LINES = 2
LAYOUT_AVATAR_SIZE = 68
LAYOUT_PAGE_BODY_HEIGHT = (
    LAYOUT_PAGE_HEIGHT
    - LAYOUT_PAGE_PADDING * 2
    - LAYOUT_HEADER_HEIGHT
    - LAYOUT_HEADER_MARGIN_BOTTOM
)

client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_API_BASE_URL or None) if HAS_LLM_CLIENT else None

DEFAULT_PROMPT = (
    "你是 ABACUS changelog 网页卡片的文案编辑。"
    "请把 GitHub Pull Request 的标题和正文改写成适合 16:9 HTML 卡片展示的中文纯文本摘要。"
    "输出必须只有一段正文，不要标题、列表、编号、Markdown、加粗、代码块、反引号或“根据提供的信息”等套话。"
    "长度控制在 35 到 65 个中文字符，最多两句话；优先说明改动对象、解决的问题和直接效果。"
    "如果是 CI、文档或依赖更新，请一句话说明维护目的，不展开上游 changelog。"
    "ABACUS 是第一性原理计算软件，术语需符合第一性原理计算语境。"
)


def load_json_file(path):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
    except Exception:
        return {}
    return {}


def save_json_file(path, payload):
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_cache():
    return load_json_file(CACHE_FILE)


def save_cache(cache):
    save_json_file(CACHE_FILE, cache)


def load_model_cache():
    return load_json_file(MODEL_CACHE_FILE)


def save_model_cache(cache):
    save_json_file(MODEL_CACHE_FILE, cache)


def model_cache_key(model, messages, params=None):
    payload = {"model": model, "messages": messages, "params": params or {}}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_model_response_cached(model, messages, params=None, force_refresh=False):
    if not client:
        return ""

    cache = load_model_cache()
    cache_model = f"{LLM_API_BASE_URL or 'default'}:{model}"
    key = model_cache_key(cache_model, messages, params)
    entry = cache.get(key)
    now = int(time.time())

    if not force_refresh and entry and now - entry.get("fetched_at", 0) <= MODEL_CACHE_TTL:
        return entry.get("response", "")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            **(params or {}),
            stream=False,
        )
        text = response.choices[0].message.content or ""
    except Exception:
        text = ""

    cache[key] = {"fetched_at": now, "response": text}
    save_model_cache(cache)
    return text


def load_prompt():
    try:
        if PROMPT_FILE and os.path.exists(PROMPT_FILE):
            with open(PROMPT_FILE, "r", encoding="utf-8") as handle:
                prompt = handle.read().strip()
                if prompt:
                    return prompt
    except OSError:
        pass
    return DEFAULT_PROMPT


def compact_html_description(text, max_chars=MAX_DESC_CHARS):
    text = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"(?m)^\s*[-*+]\s+", "", text)
    text = re.sub(r"(?m)^\s*\d+[.)]\s+", "", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    label_terms = (
        "简介|摘要|更新摘要|改动内容|主要改动|目的与意义|目的与效果|"
        "目的|影响范围|影响|说明|内容|问题背景|修复内容|幻灯片要点|幻灯片描述"
    )
    text = re.sub(rf"(?m)^\s*(PR\s*)?({label_terms})[:：]?\s*", "", text, flags=re.I)
    text = re.sub(r"根据.*?(生成|如下)[:：]?", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ：:；;。")
    if not text:
        return ""

    sentences = re.split(r"(?<=[。！？.!?])\s*", text)
    compact = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = compact + sentence if compact else sentence
        if len(candidate) > max_chars and compact:
            break
        compact = candidate
        if len(compact) >= max_chars * 0.72:
            break

    compact = compact or text
    if len(compact) > max_chars:
        compact = compact[:max_chars].rstrip(" ，,；;：:") + "..."
    elif compact and not re.search(r"[。！？.!?…]$", compact):
        compact += "。"
    return compact


def fetch_pr_description(pr_info, force_refresh_model=False):
    if not client:
        return compact_html_description(pr_info.get("body", "") or "")

    system_msg = load_prompt()
    user_msg = pr_info.get("title", "") + "\n\n" + pr_info.get("body", "")
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]
    text = get_model_response_cached(
        model=LLM_MODEL,
        messages=messages,
        params={"temperature": 0.2},
        force_refresh=force_refresh_model,
    )
    return compact_html_description(text or pr_info.get("body", "") or "")


def extract_pr_numbers(lines):
    prs = []
    current_type = ""
    for line in lines:
        match = re.search(r"#(\d+)\b", line)
        if match:
            title_hint = line[:match.start()].strip()
            author_match = re.search(r"\s+by\s+@([^\s]+)\s+in\s*$", title_hint, flags=re.IGNORECASE)
            username_hint = ""
            if author_match:
                username_hint = author_match.group(1)
                title_hint = title_hint[:author_match.start()].strip()
            prs.append((int(match.group(1)), current_type, title_hint, username_hint))
        elif line.strip():
            current_type = line.strip()
    return prs


def fetch_pr_info(pr_number):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/pulls/{pr_number}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
    except requests.RequestException:
        response = None

    if response is None or response.status_code != 200:
        return {
            "avatar_url": "",
            "username": f"unknown-{pr_number}",
            "name": "",
            "title": f"PR #{pr_number} (无法获取详情)",
            "body": "",
        }

    data = response.json()
    return {
        "avatar_url": data["user"]["avatar_url"],
        "username": data["user"]["login"],
        "name": data["user"].get("name", ""),
        "title": data.get("title", ""),
        "body": data.get("body", ""),
    }


def is_placeholder_pr_info(pr_info):
    return (pr_info or {}).get("username", "").startswith("unknown-") or "无法获取详情" in (pr_info or {}).get("title", "")


def get_pr_info_cached(pr_number, force_refresh=False):
    cache = load_cache()
    key = str(pr_number)
    entry = cache.get(key)
    now = int(time.time())

    if not force_refresh and entry and now - entry.get("fetched_at", 0) <= CACHE_TTL:
        cached_data = entry.get("data")
        if not is_placeholder_pr_info(cached_data):
            return cached_data

    data = fetch_pr_info(pr_number)
    if is_placeholder_pr_info(data) and entry:
        return entry.get("data")

    cache[key] = {"fetched_at": now, "data": data}
    save_cache(cache)
    return data


def download_avatar(avatar_url, username):
    os.makedirs(AVATAR_DIR, exist_ok=True)
    safe_username = re.sub(r"[^A-Za-z0-9_.@\\[\\]-]+", "_", username or "avatar")
    local_path = os.path.join(AVATAR_DIR, f"{safe_username}.png")
    if not avatar_url:
        return local_path.replace("\\", "/") if os.path.exists(local_path) else ""

    if not os.path.exists(local_path):
        try:
            response = requests.get(avatar_url, timeout=20)
            if response.status_code == 200:
                with open(local_path, "wb") as handle:
                    handle.write(response.content)
        except (requests.RequestException, OSError):
            return ""
    return local_path.replace("\\", "/")


def char_width(char):
    if char in "\r\n":
        return 0
    return 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1


def text_width(text):
    return sum(char_width(char) for char in text or "")


def estimate_wrapped_lines(text, width):
    if not text:
        return 1

    total = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            total += 1
            continue
        total += max(1, (text_width(line) + width - 1) // width)
    return total


def estimate_pixel_lines(text, font_size, max_width, max_lines=None):
    if not text:
        return 0
    unit_width = font_size / 2
    max_units = max(1, int(max_width / unit_width))
    lines = estimate_wrapped_lines(text, max_units)
    if max_lines:
        return min(lines, max_lines)
    return lines


def estimate_card_height(title, desc):
    if desc:
        desc_lines = estimate_pixel_lines(
            desc,
            LAYOUT_DESC_FONT_SIZE,
            LAYOUT_CARD_CONTENT_WIDTH,
            LAYOUT_DESC_MAX_LINES,
        )
        title_lines = estimate_pixel_lines(
            title,
            LAYOUT_TITLE_FONT_SIZE,
            LAYOUT_CARD_CONTENT_WIDTH,
            LAYOUT_TITLE_MAX_LINES,
        )
        content_height = (
            LAYOUT_META_LINE_HEIGHT
            + LAYOUT_DESC_MARGIN_TOP
            + desc_lines * LAYOUT_DESC_FONT_SIZE * LAYOUT_DESC_LINE_HEIGHT
            + LAYOUT_TITLE_MARGIN_TOP
            + title_lines * LAYOUT_TITLE_FONT_SIZE * LAYOUT_TITLE_LINE_HEIGHT
        )
    else:
        title_lines = estimate_pixel_lines(
            title,
            LAYOUT_TITLE_ONLY_FONT_SIZE,
            LAYOUT_CARD_CONTENT_WIDTH,
            LAYOUT_TITLE_ONLY_MAX_LINES,
        )
        content_height = (
            LAYOUT_META_LINE_HEIGHT
            + LAYOUT_TITLE_MARGIN_TOP
            + title_lines * LAYOUT_TITLE_ONLY_FONT_SIZE * LAYOUT_TITLE_LINE_HEIGHT
        )
    return int(max(LAYOUT_AVATAR_SIZE, content_height) + LAYOUT_CARD_PADDING_Y * 2)


def hard_wrap_text(text, width):
    chunks = []
    current = []
    current_width = 0

    for char in text or "":
        if char == "\n":
            if current:
                chunks.append("".join(current).strip())
            current = []
            current_width = 0
            continue

        width_cost = char_width(char)
        if current and current_width + width_cost > width:
            chunks.append("".join(current).strip())
            current = [char]
            current_width = width_cost
        else:
            current.append(char)
            current_width += width_cost

    if current:
        chunks.append("".join(current).strip())
    return [chunk for chunk in chunks if chunk]


def split_text_for_lines(text, width, max_lines):
    normalized = re.sub(r"\n{3,}", "\n\n", text or "").strip()
    if not normalized:
        return [""]

    pieces = re.split(r"(?<=[。！？；.!?])\s+|\n{2,}", normalized)
    pieces = [piece.strip() for piece in pieces if piece.strip()]
    chunks = []
    current = ""

    for piece in pieces:
        candidate = f"{current}\n\n{piece}" if current else piece
        if estimate_wrapped_lines(candidate, width) <= max_lines:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        if estimate_wrapped_lines(piece, width) <= max_lines:
            current = piece
            continue

        wrapped_lines = hard_wrap_text(piece, width)
        for index in range(0, len(wrapped_lines), max_lines):
            chunks.append("\n".join(wrapped_lines[index:index + max_lines]))

    if current:
        chunks.append(current)
    return chunks or [""]


def normalize_pr_info(pr_info, pr_number, title_hint="", username_hint=""):
    pr_info["body"] = pr_info.get("body") or ""
    pr_info["title"] = pr_info.get("title") or f"PR #{pr_number}"
    pr_info["username"] = pr_info.get("username") or ""
    pr_info["name"] = pr_info.get("name") or ""
    if title_hint and (not pr_info["title"] or "无法获取详情" in pr_info["title"]):
        pr_info["title"] = title_hint
    if username_hint and (not pr_info["username"] or pr_info["username"].startswith("unknown-")):
        pr_info["username"] = username_hint
    return pr_info


def build_groups(pr_numbers, refresh_cache=False):
    groups = {}
    for entry in pr_numbers:
        if len(entry) == 2:
            pr_number, pr_type = entry
            title_hint = ""
            username_hint = ""
        else:
            pr_number, pr_type, title_hint, username_hint = entry
        pr_info = normalize_pr_info(
            get_pr_info_cached(pr_number, force_refresh=refresh_cache),
            pr_number,
            title_hint=title_hint,
            username_hint=username_hint,
        )
        avatar_path = download_avatar(pr_info.get("avatar_url", ""), pr_info.get("username", f"pr{pr_number}"))
        group_key = pr_type if pr_type else "其他"
        groups.setdefault(group_key, []).append((pr_info, pr_number, avatar_path))
    return groups


def make_pr_segments(pr_type, pr_info, pr_number, avatar_path, force_refresh_model=False):
    desc = fetch_pr_description(pr_info, force_refresh_model=force_refresh_model)
    desc_chunks = split_text_for_lines(desc, DESC_WRAP_WIDTH, MAX_DESC_LINES_PER_CARD)
    author = " ".join(part for part in [pr_info.get("username", ""), pr_info.get("name", "")] if part).strip()
    segments = []

    for index, desc_chunk in enumerate(desc_chunks):
        title = pr_info.get("title", f"PR #{pr_number}")
        if index > 0:
            title = f"{title}（续）"

        segments.append({
            "pr_type": pr_type,
            "pr_number": pr_number,
            "title": title,
            "author": author,
            "desc": desc_chunk,
            "avatar_path": avatar_path,
            "block_height": estimate_card_height(title, desc_chunk),
        })
    return segments


def paginate_segments(grouped_items, force_refresh_model=False):
    pages = []
    for pr_type, items in grouped_items.items():
        current_blocks = []
        current_height = 0

        for pr_info, pr_number, avatar_path in items:
            for segment in make_pr_segments(
                pr_type,
                pr_info,
                pr_number,
                avatar_path,
                force_refresh_model=force_refresh_model,
            ):
                next_height = segment["block_height"]
                if current_blocks:
                    next_height += LAYOUT_CARD_GAP
                if current_blocks and current_height + next_height > LAYOUT_PAGE_BODY_HEIGHT:
                    pages.append({"pr_type": pr_type, "blocks": current_blocks})
                    current_blocks = []
                    current_height = 0
                    next_height = segment["block_height"]
                current_blocks.append(segment)
                current_height += next_height

        if current_blocks:
            pages.append({"pr_type": pr_type, "blocks": current_blocks})
    return pages


def generate_html_header(title):
    css = """
    :root {
      --page-width: min(96vw, 1600px);
      --page-height: calc(var(--page-width) * 9 / 16);
      --page-padding: clamp(30px, 3vw, 48px);
      --text: #17324d;
      --muted: #5c738b;
      --accent: #187154;
      --accent-soft: #e7f5ef;
      --surface: rgba(255, 255, 255, 0.9);
      --border: rgba(23, 50, 77, 0.12);
    }
    * { box-sizing: border-box; }
    html, body { min-height: 100%; }
    body {
      margin: 0;
      color: var(--text);
      font-family: 'Microsoft YaHei', 'PingFang SC', 'Noto Sans CJK SC', Arial, sans-serif;
      background:
        radial-gradient(circle at top left, rgba(24, 113, 84, 0.08), transparent 30%),
        linear-gradient(180deg, #dfe8f2 0%, #eef3f8 100%);
    }
    .deck {
      min-height: 100vh;
      display: grid;
      grid-template-rows: 1fr auto;
      place-items: center;
      padding: 22px 18px 14px;
    }
    .page {
      position: relative;
      display: none;
      width: var(--page-width);
      height: var(--page-height);
      padding: var(--page-padding);
      overflow: hidden;
      background: linear-gradient(135deg, #f7fbff 0%, #edf4ff 48%, #f8fbf4 100%);
      border: 1px solid rgba(255, 255, 255, 0.72);
      border-radius: 20px;
      box-shadow: 0 24px 72px rgba(23, 50, 77, 0.16);
    }
    .page.active { display: flex; flex-direction: column; }
    .page::before {
      content: '';
      position: absolute;
      inset: 0;
      background:
        radial-gradient(circle at right top, rgba(24, 113, 84, 0.1), transparent 28%),
        radial-gradient(circle at left bottom, rgba(45, 95, 180, 0.1), transparent 30%);
      pointer-events: none;
    }
    .page > * { position: relative; }
    .page-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 24px;
      margin-bottom: clamp(18px, 2.2vw, 30px);
    }
    .type-tag {
      display: inline-flex;
      align-items: center;
      min-height: 52px;
      padding: 0 28px;
      border-radius: 28px;
      color: var(--accent);
      background: var(--accent-soft);
      box-shadow: inset 0 0 0 1px rgba(24, 113, 84, 0.04);
      font-size: clamp(20px, 1.65vw, 28px);
      line-height: 1;
      font-weight: 700;
    }
    .page-index {
      flex: 0 0 auto;
      min-width: 94px;
      padding: 14px 20px;
      border-radius: 999px;
      color: var(--muted);
      background: rgba(255, 255, 255, 0.72);
      text-align: center;
      font-size: clamp(14px, 1.15vw, 18px);
      line-height: 1;
      font-weight: 700;
    }
    .segment-list {
      display: flex;
      flex-direction: column;
      flex: 1 1 auto;
      justify-content: flex-start;
      gap: clamp(12px, 1.25vw, 18px);
      min-height: 0;
    }
    .page.sparse .segment-list {
      justify-content: center;
      gap: clamp(16px, 2vw, 26px);
    }
    .pr-block {
      display: grid;
      grid-template-columns: 74px minmax(0, 1fr);
      align-items: flex-start;
      gap: 22px;
      padding: clamp(16px, 1.5vw, 22px) clamp(20px, 2vw, 30px);
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(255, 255, 255, 0.86));
      border: 1px solid rgba(203, 218, 235, 0.95);
      border-left: 5px solid rgba(24, 113, 84, 0.55);
      border-radius: 14px;
      box-shadow: 0 10px 28px rgba(23, 50, 77, 0.08);
    }
    .page.sparse .pr-block {
      grid-template-columns: 88px minmax(0, 1fr);
      min-height: clamp(164px, 13vw, 210px);
      padding: clamp(22px, 2.1vw, 34px) clamp(28px, 2.6vw, 42px);
    }
    .avatar {
      width: 74px;
      padding-top: 3px;
    }
    .avatar img,
    .avatar-placeholder {
      display: block;
      width: 68px;
      height: 68px;
      border-radius: 13px;
      object-fit: cover;
      box-shadow: 0 6px 16px rgba(23, 50, 77, 0.12);
    }
    .page.sparse .avatar img,
    .page.sparse .avatar-placeholder {
      width: 78px;
      height: 78px;
      border-radius: 15px;
    }
    .avatar-placeholder {
      background:
        linear-gradient(135deg, rgba(151, 176, 217, 0.32), rgba(203, 216, 231, 0.9)),
        linear-gradient(90deg, transparent 32%, rgba(122, 153, 207, 0.7) 32% 52%, transparent 52%),
        linear-gradient(0deg, transparent 34%, rgba(122, 153, 207, 0.65) 34% 54%, transparent 54%);
    }
    .content { flex: 1 1 auto; min-width: 0; }
    .meta-row {
      display: flex;
      align-items: baseline;
      flex-wrap: wrap;
      gap: 10px 14px;
    }
    .meta {
      color: var(--muted);
      font-size: clamp(14px, 1.08vw, 18px);
      font-weight: 700;
    }
    .title {
      margin-top: 12px;
      color: var(--muted);
      font-size: clamp(15px, 1.05vw, 18px);
      line-height: 1.28;
      font-weight: 650;
      display: -webkit-box;
      overflow: hidden;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 1;
    }
    .title.only {
      color: var(--text);
      font-size: clamp(22px, 1.85vw, 30px);
      font-weight: 700;
      -webkit-line-clamp: 2;
    }
    .author {
      color: var(--accent);
      font-size: clamp(14px, 1.08vw, 18px);
      font-weight: 700;
    }
    .author::before {
      content: '@';
      color: rgba(24, 113, 84, 0.62);
      font-weight: 700;
    }
    .desc {
      margin-top: 16px;
      max-width: 58em;
      color: var(--text);
      font-size: clamp(20px, 1.7vw, 28px);
      line-height: 1.38;
      font-weight: 500;
      display: -webkit-box;
      overflow: hidden;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 2;
    }
    .page.sparse .desc {
      max-width: 54em;
      font-size: clamp(24px, 2vw, 34px);
      line-height: 1.36;
      -webkit-line-clamp: 3;
    }
    .controls {
      width: var(--page-width);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-top: 14px;
    }
    .button-row { display: flex; gap: 10px; }
    button {
      min-width: 44px;
      height: 40px;
      border: 1px solid var(--border);
      border-radius: 999px;
      color: var(--text);
      background: rgba(255, 255, 255, 0.82);
      font-size: 20px;
      line-height: 1;
      cursor: pointer;
    }
    button:disabled { opacity: 0.42; cursor: default; }
    .counter {
      color: var(--muted);
      font-size: 14px;
      font-weight: 700;
    }
    @media (max-width: 760px) {
      .deck { place-items: start center; }
      .page {
        height: auto;
        min-height: var(--page-height);
        border-radius: 14px;
      }
      .page-header { gap: 12px; margin-bottom: 14px; }
      .pr-block {
        grid-template-columns: 50px minmax(0, 1fr);
        min-height: 0;
        gap: 14px;
        padding: 14px;
      }
      .page.sparse .pr-block { grid-template-columns: 50px minmax(0, 1fr); }
      .avatar,
      .avatar img,
      .avatar-placeholder {
        width: 48px;
        height: 48px;
      }
      .controls { position: sticky; bottom: 10px; }
    }
    @page { size: 16in 9in; margin: 0; }
    @media print {
      body { background: #fff; }
      .deck { display: block; padding: 0; }
      .page,
      .page.active {
        display: flex;
        width: 16in;
        height: 9in;
        margin: 0;
        border: none;
        border-radius: 0;
        box-shadow: none;
        break-after: page;
        page-break-after: always;
      }
      .controls { display: none; }
    }
    """
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{html_lib.escape(title)}</title>
  <style>{css}</style>
</head>
<body>
<main class="deck" aria-label="{html_lib.escape(title)}">
<div class="slides">
"""


def generate_html_footer(total_pages):
    return f"""
</div>
<nav class="controls" aria-label="Slide navigation">
  <div class="button-row">
    <button id="prevPage" type="button" aria-label="Previous page">‹</button>
    <button id="nextPage" type="button" aria-label="Next page">›</button>
  </div>
  <div class="counter"><span id="currentPage">1</span> / {total_pages}</div>
</nav>
</main>
<script>
(() => {{
  let pages = Array.from(document.querySelectorAll('.page'));
  const prev = document.getElementById('prevPage');
  const next = document.getElementById('nextPage');
  const current = document.getElementById('currentPage');
  const counter = document.querySelector('.counter');
  let index = Math.min(Math.max(parseInt(location.hash.slice(1), 10) || 1, 1), pages.length) - 1;

  function pageType(page) {{
    const tag = page.querySelector('.type-tag');
    return tag ? tag.textContent : '';
  }}

  function pageList(page) {{
    return page.querySelector('.segment-list');
  }}

  function isOverflowing(page) {{
    const list = pageList(page);
    if (!list) return false;
    const previousDisplay = page.style.display;
    const previousFlexDirection = page.style.flexDirection;
    const previousVisibility = page.style.visibility;
    const previousPosition = page.style.position;
    const previousZIndex = page.style.zIndex;
    page.style.display = 'flex';
    page.style.flexDirection = 'column';
    page.style.visibility = 'hidden';
    page.style.position = 'absolute';
    page.style.zIndex = '-1';
    const overflowing = list.scrollHeight > list.clientHeight + 1;
    page.style.display = previousDisplay;
    page.style.flexDirection = previousFlexDirection;
    page.style.visibility = previousVisibility;
    page.style.position = previousPosition;
    page.style.zIndex = previousZIndex;
    return overflowing;
  }}

  function createPageAfter(page) {{
    const newPage = page.cloneNode(false);
    const header = page.querySelector('.page-header').cloneNode(true);
    const list = document.createElement('div');
    list.className = 'segment-list';
    newPage.className = 'page sparse';
    newPage.removeAttribute('aria-hidden');
    newPage.appendChild(header);
    newPage.appendChild(list);
    page.after(newPage);
    return newPage;
  }}

  function refreshPages() {{
    pages = Array.from(document.querySelectorAll('.page'));
    const total = pages.length;
    pages.forEach((page, pageIndex) => {{
      page.setAttribute('aria-label', 'Page ' + (pageIndex + 1));
      const indexNode = page.querySelector('.page-index');
      if (indexNode) indexNode.textContent = (pageIndex + 1) + ' / ' + total;
      const cards = page.querySelectorAll('.pr-block').length;
      page.classList.toggle('sparse', cards <= 2);
    }});
    if (counter) counter.lastChild.textContent = ' / ' + total;
    index = Math.min(index, pages.length - 1);
  }}

  function rebalanceOverflowingPages() {{
    refreshPages();
    for (let pageIndex = 0; pageIndex < pages.length; pageIndex += 1) {{
      let page = pages[pageIndex];
      let list = pageList(page);
      let guard = 0;
      while (list && isOverflowing(page) && list.children.length > 1 && guard < 100) {{
        const moved = list.lastElementChild;
        let nextPage = pages[pageIndex + 1];
        if (!nextPage || pageType(nextPage) !== pageType(page)) {{
          nextPage = createPageAfter(page);
        }}
        pageList(nextPage).prepend(moved);
        refreshPages();
        page = pages[pageIndex];
        list = pageList(page);
        guard += 1;
      }}
    }}
    refreshPages();
  }}

  function show(nextIndex, updateHash = true) {{
    index = Math.min(Math.max(nextIndex, 0), pages.length - 1);
    pages.forEach((page, pageIndex) => {{
      page.classList.toggle('active', pageIndex === index);
      page.setAttribute('aria-hidden', pageIndex === index ? 'false' : 'true');
    }});
    prev.disabled = index === 0;
    next.disabled = index === pages.length - 1;
    current.textContent = String(index + 1);
    if (updateHash) history.replaceState(null, '', '#' + (index + 1));
  }}

  prev.addEventListener('click', () => show(index - 1));
  next.addEventListener('click', () => show(index + 1));
  window.addEventListener('hashchange', () => show((parseInt(location.hash.slice(1), 10) || 1) - 1, false));
  window.addEventListener('keydown', (event) => {{
    if (event.target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(event.target.tagName)) return;
    if (['ArrowRight', 'PageDown', ' '].includes(event.key)) {{
      event.preventDefault();
      show(index + 1);
    }}
    if (['ArrowLeft', 'PageUp'].includes(event.key)) {{
      event.preventDefault();
      show(index - 1);
    }}
    if (event.key === 'Home') show(0);
    if (event.key === 'End') show(pages.length - 1);
  }});
  rebalanceOverflowingPages();
  show(index, !location.hash);
}})();
</script>
</body>
</html>
"""


def generate_pr_html(segment):
    esc_title = html_lib.escape(segment["title"])
    esc_author = html_lib.escape(segment["author"])
    esc_desc = html_lib.escape(segment["desc"]).replace("\n\n", "<br><br>").replace("\n", "<br>")
    esc_avatar = html_lib.escape(segment["avatar_path"])
    esc_alt = html_lib.escape(segment["author"] or f"PR {segment['pr_number']}")
    author_html = f'<div class="author">{esc_author}</div>' if esc_author else ""
    avatar_html = (
        f'<div class="avatar"><img src="{esc_avatar}" alt="{esc_alt}"></div>'
        if esc_avatar
        else '<div class="avatar"><div class="avatar-placeholder"></div></div>'
    )
    desc_html = f'<div class="desc">{esc_desc}</div>' if esc_desc else ""
    title_class = "title" if esc_desc else "title only"
    title_html = f'<div class="{title_class}">{esc_title}</div>'
    body_html = f"{desc_html}\n    {title_html}" if desc_html else title_html
    return f"""
<article class="pr-block">
  {avatar_html}
  <div class="content">
    <div class="meta-row">
      <div class="meta">PR #{segment["pr_number"]}</div>
      {author_html}
    </div>
    {body_html}
  </div>
</article>
"""


def generate_page_html(page, page_number, total_pages):
    blocks = "\n".join(generate_pr_html(segment) for segment in page["blocks"])
    esc_type = html_lib.escape(page["pr_type"])
    density_class = " sparse" if len(page["blocks"]) <= 2 else ""
    return f"""
<section class="page{density_class}" aria-label="Page {page_number}">
  <header class="page-header">
    <div class="type-tag">{esc_type}</div>
    <div class="page-index">{page_number} / {total_pages}</div>
  </header>
  <div class="segment-list">
    {blocks}
  </div>
</section>
"""


def render_html_document(pages, title=TITLE):
    total_pages = len(pages)
    parts = [generate_html_header(title)]
    for index, page in enumerate(pages, start=1):
        parts.append(generate_page_html(page, index, total_pages))
    parts.append(generate_html_footer(total_pages))
    return "\n".join(parts)


def parse_args():
    parser = argparse.ArgumentParser(description="Generate a paginated HTML changelog deck.")
    parser.add_argument("--refresh-cache", action="store_true", help="Force refresh PR info from GitHub API")
    parser.add_argument("--clear-cache", action="store_true", help="Clear the local PR cache and exit")
    parser.add_argument("--refresh-model-cache", action="store_true", help="Force refresh LLM summaries")
    parser.add_argument("--title", default=TITLE, help="HTML document title")
    parser.add_argument("--html", action="store_true", help="Compatibility no-op; HTML is always generated")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.clear_cache:
        for cache_file in [CACHE_FILE, MODEL_CACHE_FILE]:
            try:
                if os.path.exists(cache_file):
                    os.remove(cache_file)
                    sys.stderr.write(f"Cache file {cache_file} removed.\n")
            except OSError as exc:
                sys.stderr.write(f"Failed to remove {cache_file}: {exc}\n")
                return 1
        return 0

    stdin_lines = [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]
    if not stdin_lines:
        sys.stderr.write("No input received from stdin.\n")
        return 1

    pr_numbers = extract_pr_numbers(stdin_lines)
    if not pr_numbers:
        sys.stderr.write("No PR numbers (like #1234) found in input lines.\n")
        return 1

    groups = build_groups(pr_numbers, refresh_cache=args.refresh_cache)
    pages = paginate_segments(groups, force_refresh_model=args.refresh_model_cache)
    sys.stdout.write(render_html_document(pages, title=args.title))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
