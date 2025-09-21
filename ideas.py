# ruff: noqa

import os, json, time, math
from datetime import datetime, timezone
from typing import List, Dict, Any
import httpx

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
DATA_DIR = os.getenv("DATA_DIR", "data")
IDEAS_FILE = os.path.join(DATA_DIR, "ideas.queue.json")

os.makedirs(DATA_DIR, exist_ok=True)

# --- Helpers ---
def _sec_from_iso8601_dur(dur: str) -> int:
    # e.g. PT0M42S, PT1M5S, PT59S
    if not dur or not dur.startswith("PT"): return 999999
    s = 0
    num = ""
    for ch in dur[2:]:
        if ch.isdigit():
            num += ch
            continue
        if ch == "H":
            s += int(num) * 3600; num = ""
        elif ch == "M":
            s += int(num) * 60; num = ""
        elif ch == "S":
            s += int(num); num = ""
    return s


def _safe_int(x, default=0):
    try: return int(x)
    except: return default


def _like_rate(stats: Dict[str, Any]) -> float:
    v = _safe_int(stats.get("viewCount", 0), 0)
    l = _safe_int(stats.get("likeCount", 0), 0)
    return (l / v) if v else 0.0


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# --- Sources: YouTube mostPopular (shorts only), Google Trends, Reddit JSON ---
async def _yt_most_popular(client: httpx.AsyncClient, region: str, category_id: str, max_results=50) -> List[Dict]:
    if not YOUTUBE_API_KEY:
        return []
    # 1) Get mostPopular list
    params = {
        "part": "id,snippet,contentDetails,statistics",
        "chart": "mostPopular",
        "regionCode": region,
        "videoCategoryId": category_id,
        "maxResults": max_results,
        "key": YOUTUBE_API_KEY,
    }
    r = await client.get("https://www.googleapis.com/youtube/v3/videos", params=params, timeout=30)
    r.raise_for_status()
    items = r.json().get("items", [])
    out = []
    for it in items:
        dur = it.get("contentDetails", {}).get("duration", "PT0S")
        sec = _sec_from_iso8601_dur(dur)
        if sec == 0 or sec > 60:  # фильтруем только шорты <= 60s
            continue
        stats = it.get("statistics", {})
        out.append({
            "source": "yt",
            "videoId": it.get("id"),
            "title": it.get("snippet", {}).get("title", ""),
            "tags": it.get("snippet", {}).get("tags", []),
            "durationSec": sec,
            "likeRate": _like_rate(stats),
            "viewCount": _safe_int(stats.get("viewCount", 0), 0),
            "region": region,
            "category": category_id,
        })
    return out


async def _reddit_top_daily(client: httpx.AsyncClient, sub: str, limit=50) -> List[Dict]:
    # без токена: публичное JSON API reddit
    url = f"https://www.reddit.com/r/{sub}/top/.json"
    params = {"t": "day", "limit": str(limit)}
    r = await client.get(url, params=params, headers={"User-Agent": "trend-bot/1.0"}, timeout=30)
    if r.status_code >= 400:
        return []
    data = r.json()
    out = []
    for ch in data.get("data", {}).get("children", []):
        d = ch.get("data", {})
        title = d.get("title", "")
        score = d.get("score", 0)
        if not title: continue
        out.append({
            "source": "reddit",
            "subreddit": sub,
            "title": title,
            "score": score,
            "permalink": f"https://www.reddit.com{d.get('permalink','')}",
        })
    return out


def _hashtags(base_words: List[str], extra: List[str]=[]) -> List[str]:
    uniq = []
    for w in (base_words + extra):
        h = "#" + w.lower().replace(" ", "")
        if h not in uniq:
            uniq.append(h)
    # добавим базовые
    for h in ["#shorts", "#viral", "#trending"]:
        if h not in uniq:
            uniq.append(h)
    return uniq[:12]


def _title_from_seed(seed: str) -> str:
    seed = seed.strip()
    if len(seed) > 80: seed = seed[:77] + "..."
    return seed


def _script_for_cat_meme(seed: str) -> str:
    # короткий скрипт озвучки (15–30s)
    return (
        f"Hook (0-2s): {seed}!\n"
        "Beat (2-5s): Мягкая шутка, интрига.\n"
        "Body (5-18s): 2-3 быстрых факта/мини-сцены про кота.\n"
        "Punch (18-25s): неожиданный твист/ми-ми-ми.\n"
        "CTA (25-30s): лайк/подписка, ещё котики завтра."
    )


async def refresh_ideas(regions=("US","GB","CA","KZ"), categories=("15","24")) -> Dict[str, Any]:
    # 15 = Pets & Animals, 24 = Entertainment
    out: List[Dict] = []
    async with httpx.AsyncClient() as client:
        # YouTube trending shorts
        for rg in regions:
            for cat in categories:
                try:
                    out.extend(await _yt_most_popular(client, rg, cat))
                except Exception:
                    pass
        # Reddit top daily for aww/cats
        for sub in ["aww", "cats", "Catmemes", "AnimalsBeingDerps"]:
            try:
                out.extend(await _reddit_top_daily(client, sub))
            except Exception:
                pass

    # нормализуем в "идею" (seed -> title/script/hashtags)
    seeds: List[str] = []
    for it in out:
        if it.get("source") == "yt":
            seeds.append(it.get("title",""))
            tags = it.get("tags") or []
            seeds.extend(tags[:3])
        elif it.get("source") == "reddit":
            seeds.append(it.get("title",""))

    # дедуп по нижнему регистру
    seen = set()
    uniq_seeds = []
    for s in seeds:
        k = (s or "").strip().lower()
        if not k: continue
        if k in seen: continue
        seen.add(k)
        uniq_seeds.append(s.strip())

    # берём топ N по простым эвристикам (длина, "cat" в тексте и т.д.)
    scored = []
    for s in uniq_seeds:
        score = 0
        ls = s.lower()
        if "cat" in ls or "кот" in ls: score += 2
        if "cute" in ls or "мил" in ls: score += 1
        if len(s) <= 60: score += 1
        scored.append((score, s))
    scored.sort(reverse=True, key=lambda x: x[0])

    ideas = []
    for _, seed in scored[:60]:  # оставим топ-60 на сутки
        title = _title_from_seed(seed)
        hashtags = _hashtags([ "cats", "funny cats", "kitten", "memes" ])
        script = _script_for_cat_meme(seed)
        ideas.append({
            "seed": seed,
            "title": title,
            "script": script,
            "hashtags": hashtags,
            "style": {
                "pace": "fast",
                "sfx": ["pop","meow"],
                "caption": "bold meme",
                "bg": "clean-gradient",
                "lengthSecTarget": 25
            }
        })

    payload = {
        "generatedAt": _now_iso(),
        "count": len(ideas),
        "items": ideas
    }
    with open(IDEAS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload


def load_ideas() -> Dict[str, Any]:
    if not os.path.exists(IDEAS_FILE):
        return {"generatedAt": None, "count": 0, "items": []}
    return json.loads(open(IDEAS_FILE, "r", encoding="utf-8").read())


def pop_n(n=1) -> List[Dict[str,Any]]:
    data = load_ideas()
    items = data.get("items", [])
    take = items[:max(0, n)]
    data["items"] = items[len(take):]
    data["count"] = len(data["items"])
    with open(IDEAS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return take
