# -*- coding: utf-8 -*-
import os, re, json, time, math, hashlib, argparse, pathlib, random, logging
from urllib.parse import quote_plus
import requests
from PIL import Image
from io import BytesIO

TIMEOUT = 20
HEADERS = {"User-Agent": "Dark&Strange/1.0"}
LOG = logging.getLogger("fetch_assets")
if not LOG.handlers:
    logging.basicConfig(level=logging.INFO)
STOP = set("""
a an the and or of on in to from for with by at as is are was were be being been
this that those these it its they them he she we you i not no yes do did done
over under between into onto out up down left right near far old new one two three four five
""".split())

def sha1(b: bytes) -> str: return hashlib.sha1(b).hexdigest()
def ensure_dir(p): pathlib.Path(p).mkdir(parents=True, exist_ok=True)

def keywords_from_script(script_json, topk=6):
    data = json.load(open(script_json, "r", encoding="utf-8"))
    text = " ".join([data.get("title","")] + data.get("lines", []))
    text = re.sub(r"[^A-Za-z0-9\s-]", " ", text).lower()
    words = [w for w in re.split(r"\s+", text) if w and w not in STOP and len(w) > 3]
    counts = {}
    for w in words: counts[w] = counts.get(w,0)+1
    seeds = [w for w,_ in sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:topk]]
    for extra in ["horror","haunted","mystery","forest","night","abandoned","legend","ghost","bridge"]:
        if extra not in seeds: seeds.append(extra)
    return seeds[:max(topk, 6)]

def _get(url, headers=None, params=None, api_key=None):
    h = dict(HEADERS)
    if headers: h.update(headers)
    if api_key: h["Authorization"] = api_key
    r = requests.get(url, headers=h, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r


def _get_with_retries(url, headers=None, params=None, api_key=None, max_retries=3, backoff=1.0):
    """GET with basic retries and backoff. Handles 429 by inspecting retry-after headers where available.
    Returns requests.Response or raises the last exception.
    """
    attempt = 0
    while True:
        try:
            r = _get(url, headers=headers, params=params, api_key=api_key)
            return r
        except requests.HTTPError as e:
            status = getattr(e.response, 'status_code', None)
            # Handle rate limit
            if status == 429 and attempt < max_retries:
                # Prefer Retry-After header if present
                ra = e.response.headers.get('Retry-After') or e.response.headers.get('X-RateLimit-Reset')
                try:
                    wait = float(ra) if ra else backoff * (2 ** attempt)
                except Exception:
                    wait = backoff * (2 ** attempt)
                time.sleep(min(wait, 30))
                attempt += 1
                continue
            raise



def _cache_get(cache_dir, key):
    p = pathlib.Path(cache_dir)
    p.mkdir(parents=True, exist_ok=True)
    fn = p / (quote_plus(key) + '.json')
    if fn.exists():
        try:
            age = time.time() - fn.stat().st_mtime
            if age < 24*3600:
                return json.loads(fn.read_text(encoding='utf-8'))
        except Exception:
            pass
    return None


def _cache_set(cache_dir, key, data):
    p = pathlib.Path(cache_dir)
    p.mkdir(parents=True, exist_ok=True)
    fn = p / (quote_plus(key) + '.json')
    try:
        fn.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    except Exception:
        pass

def fetch_pexels_photos(q, key, per_page=8):
    if not key: return []
    url = "https://api.pexels.com/v1/search"
    r = _get(url, params={"query": q, "per_page": per_page, "orientation": "portrait"}, api_key=key)
    items = []
    for ph in r.json().get("photos", []):
        src = ph["src"].get("large2x") or ph["src"].get("original") or ph["src"].get("large")
        if src:
            items.append(dict(kind="image", url=src, source="pexels", id=str(ph["id"]),
                              author=ph.get("photographer"), license="Pexels License"))
    return items

def fetch_pexels_videos(q, key, per_page=6):
    if not key: return []
    url = "https://api.pexels.com/videos/search"
    r = _get(url, params={"query": q, "per_page": per_page}, api_key=key)
    items = []
    for v in r.json().get("videos", []):
        files = v.get("video_files", [])
        files.sort(key=lambda f: (abs((f.get("width",0)-1080)) + abs((f.get("height",0)-1920))))
        if files:
            best = files[0]
            items.append(dict(kind="video", url=best["link"], source="pexels", id=str(v["id"]),
                              width=best.get("width"), height=best.get("height"),
                              license="Pexels License"))
    return items

def fetch_pixabay(q, key, per_page=8):
    # Deprecated: kept for backward compat. Prefer fetch_pixabay_images or fetch_pixabay_videos
    return fetch_pixabay_images(q, key, per_page=per_page)


def _select_pixabay_image_url(hit):
    # Prefer fullHDURL, then largeImageURL, then webformatURL, then previewURL
    for k in ('fullHDURL', 'largeImageURL', 'webformatURL', 'previewURL'):
        url = hit.get(k)
        if url:
            return url
    # fallback: try 'imageURL'
    return hit.get('imageURL') or ''


def fetch_pixabay_images(q, key, per_page=8, orientation='vertical'):
    """Search Pixabay images with caching, retries and orientation preference.
    Returns list of items like {kind:'image', url:..., source:'pixabay', id:..., author:..., license:...}
    """
    if not key:
        return []
    cache_key = f'pixabay_images::{q}::{orientation}::{per_page}'
    cached = _cache_get('.cache/pixabay', cache_key)
    if cached is not None:
        return cached
    base = "https://pixabay.com/api/"
    params = {"key": key, "q": q, "image_type": "photo", "orientation": orientation, "safesearch": "true", "per_page": per_page}
    try:
        r = _get_with_retries(base, params=params)
    except Exception as e:
        print('pixabay images request failed', e)
        return []
    hdr = r.headers
    # log rate-limit hints if present
    rl = hdr.get('X-RateLimit-Remaining') or hdr.get('x-ratelimit-remaining')
    if rl is not None:
        try:
            if int(rl) < 5:
                print('pixabay: low rate-limit remaining:', rl)
        except Exception:
            pass
    data = r.json()
    items = []
    for h in data.get('hits', []):
        url = _select_pixabay_image_url(h)
        if not url: continue
        items.append(dict(kind='image', url=url, source='pixabay', id=str(h.get('id')), author=h.get('user'), license='Pixabay License'))
    _cache_set('.cache/pixabay', cache_key, items)
    return items


def fetch_pixabay_videos(q, key, per_page=6):
    """Search Pixabay videos. Returns items with kind='video' and a chosen rendition URL.
    """
    if not key:
        return []
    cache_key = f'pixabay_videos::{q}::{per_page}'
    cached = _cache_get('.cache/pixabay', cache_key)
    if cached is not None:
        return cached
    base = 'https://pixabay.com/api/videos/'
    params = {'key': key, 'q': q, 'per_page': per_page}
    try:
        r = _get_with_retries(base, params=params)
    except Exception as e:
        print('pixabay videos request failed', e)
        return []
    data = r.json()
    items = []
    for hit in data.get('hits', []):
        vids = hit.get('videos', {})
        # prefer 'large' or 'medium' then 'small'
        chosen = None
        for k in ('large', 'medium', 'small', 'tiny'):
            v = vids.get(k)
            if v and v.get('url'):
                chosen = v
                break
        if not chosen: continue
        items.append(dict(kind='video', url=chosen['url'], source='pixabay', id=str(hit.get('id')), width=chosen.get('width'), height=chosen.get('height'), license='Pixabay License'))
    _cache_set('.cache/pixabay', cache_key, items)
    return items


def _score_item(item, prefer_vertical=True):
    """Return a score for sorting items. Prefer videos, portrait orientation, larger resolution and popular sources."""
    score = 0
    if item.get('kind') == 'video':
        score += 200
    w = item.get('width') or 0
    h = item.get('height') or 0
    # prefer tall (portrait)
    if prefer_vertical and h >= w:
        score += 100
    # resolution influence
    score += int(min(200, (w + h) / 20))
    # source preference
    src = item.get('source','')
    if src == 'pexels': score += 20
    if src == 'pixabay': score += 10
    if src == 'wikimedia': score += 5
    return score


def combined_search(q, pexels_key=None, pixabay_key=None, want=10, want_videos=3):
    """Query multiple providers for images and videos and return a deduplicated, scored list.
    Caches provider responses separately; respects per-provider rate limit hints and retries.
    """
    items = []
    seen_ids = set()

    # 1) try video-first providers
    if pexels_key:
        try:
            vids = fetch_pexels_videos(q, pexels_key, per_page=max(4, want_videos*2))
            for v in vids:
                uid = (v.get('source'), v.get('id'))
                if uid in seen_ids: continue
                seen_ids.add(uid)
                items.append(v)
        except Exception as e:
            LOG.warning('pexels videos failed: %s', e)

    if pixabay_key:
        try:
            vids = fetch_pixabay_videos(q, pixabay_key, per_page=max(4, want_videos*2))
            for v in vids:
                uid = (v.get('source'), v.get('id'))
                if uid in seen_ids: continue
                seen_ids.add(uid)
                items.append(v)
        except Exception as e:
            LOG.warning('pixabay videos failed: %s', e)

    # 2) images
    try:
        if pexels_key:
            for im in fetch_pexels_photos(q, pexels_key, per_page=max(6, want*2)):
                uid = (im.get('source'), im.get('id'))
                if uid in seen_ids: continue
                seen_ids.add(uid)
                items.append(im)
    except Exception as e:
        LOG.warning('pexels images failed: %s', e)

    try:
        if pixabay_key:
            for im in fetch_pixabay_images(q, pixabay_key, per_page=max(6, want*2)):
                uid = (im.get('source'), im.get('id'))
                if uid in seen_ids: continue
                seen_ids.add(uid)
                items.append(im)
    except Exception as e:
        LOG.warning('pixabay images failed: %s', e)

    # fallback: commons
    try:
        for im in fetch_commons(q, per_page=max(3, want)):
            uid = (im.get('source'), im.get('id'))
            if uid in seen_ids: continue
            seen_ids.add(uid)
            items.append(im)
    except Exception as e:
        LOG.warning('wikimedia failed: %s', e)

    # score and sort
    items = sorted(items, key=lambda it: _score_item(it, prefer_vertical=True), reverse=True)
    # ensure we return enough videos first
    videos = [it for it in items if it.get('kind') == 'video']
    images = [it for it in items if it.get('kind') == 'image']
    out = videos[:want_videos] + images[:max(0, want - len(videos))]
    return out

def fetch_commons(q, per_page=6):
    url = "https://commons.wikimedia.org/w/api.php"
    params = {"action":"query","generator":"search","gsrsearch":q+" filetype:bitmap","gsrlimit":str(per_page),
              "prop":"imageinfo","iiprop":"url|size|mime|extmetadata","format":"json","origin":"*"}
    r = _get(url, params=params)
    data = r.json().get("query", {}).get("pages", {}) or {}
    items = []
    for _,pg in data.items():
        ii = (pg.get("imageinfo") or [{}])[0]
        url_i = ii.get("url")
        if not url_i: continue
        w,h = ii.get("width",0), ii.get("height",0)
        if min(w,h) < 1080: continue
        lic = (ii.get("extmetadata",{}).get("LicenseShortName",{}) or {}).get("value","Commons")
        items.append(dict(kind="image", url=url_i, source="wikimedia", id=str(pg.get("pageid")), license=lic))
    return items

def download_to(url, out_path):
    r = _get(url)
    data = r.content
    if len(data) < 100: return None
    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f: f.write(data)
    return out_path

def vertical_crop_if_needed(path, min_w=1080, min_h=1920):
    if path.lower().endswith((".mp4",".mov",".mkv",".webm",".m4v")): return
    im = Image.open(path).convert("RGB")
    w,h = im.size
    scale = max(min_h / h, min_w / w, 1.0)
    nw, nh = int(w*scale), int(h*scale)
    im = im.resize((nw, nh), Image.LANCZOS)
    left = max(0, (nw - min_w)//2); top = max(0, (nh - min_h)//2)
    im = im.crop((left, top, left+min_w, top+min_h))
    im.save(path, quality=95, subsampling=2)

def fetch_assets(script_json, outdir, want=10, want_videos=3):
    seeds = keywords_from_script(script_json)
    # prefer environment variables; fall back to secrets/api_keys.json when available
    pexels_key = os.getenv("PEXELS_API_KEY") or ""
    pixabay_key = os.getenv("PIXABAY_API_KEY") or ""
    if (not pexels_key or not pixabay_key) and os.path.exists('secrets/api_keys.json'):
        try:
            sk = json.loads(open('secrets/api_keys.json', 'r', encoding='utf-8').read())
            if not pexels_key:
                pexels_key = sk.get('PEXELS_API_KEY') or pexels_key
            if not pixabay_key:
                pixabay_key = sk.get('PIXABAY_API_KEY') or pixabay_key
        except Exception:
            LOG.debug('failed to read secrets/api_keys.json')
    ensure_dir(outdir)
    meta, seen_hash, idx = [], set(), 1

    def add_item(item):
        nonlocal idx
        url = item["url"]
        ext = ".mp4" if item["kind"] == "video" else os.path.splitext(url.split("?")[0])[1].lower()
        if ext not in (".jpg",".jpeg",".png",".mp4",".mov",".webm",".mkv",".m4v"):
            ext = ".jpg" if item["kind"]=="image" else ".mp4"
        tmp = download_to(url, os.path.join(outdir, f"{idx:02d}{ext}"))
        if not tmp: return False
        with open(tmp, "rb") as f: h = sha1(f.read(1024*1024))
        if h in seen_hash:
            try: os.remove(tmp)
            except: pass
            return False
        seen_hash.add(h)
        if item["kind"]=="image":
            try: vertical_crop_if_needed(tmp)
            except Exception as e: print("crop fail", e)
        meta.append(dict(local=os.path.basename(tmp), **{k:v for k,v in item.items() if k!="url"}))
        idx += 1
        return True

    # Use combined search to get best candidates per seed
    for q in seeds:
        if len(meta) >= want: break
        try:
            cand = combined_search(q, pexels_key, pixabay_key, want=want, want_videos=want_videos)
        except Exception as e:
            LOG.warning('combined_search failed for %s: %s', q, e)
            cand = []
        for it in cand:
            if len(meta) >= want: break
            try:
                added = add_item(it)
                if not added:
                    LOG.debug('item skipped or duplicate: %s', it.get('url'))
            except Exception:
                LOG.exception('failed to add item')
        # small sleep to be polite
        time.sleep(0.2)

    attrib = dict(script=script_json, seeds=seeds, items=meta, note="Stock only; Pexels/Pixabay/Wikimedia licenses logged.")
    # Add last-known rate-limit headers if available (from cache files)
    try:
        attrib['cache_info'] = {}
        cdir = pathlib.Path('.cache/pixabay')
        if cdir.exists():
            attrib['cache_info']['pixabay_cached'] = [p.name for p in cdir.glob('*.json')][:50]
    except Exception:
        pass
    with open(os.path.join(outdir, "_attribution.json"), "w", encoding="utf-8") as f:
        json.dump(attrib, f, ensure_ascii=False, indent=2)
    return meta

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--script_json", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--want", type=int, default=10)
    ap.add_argument("--want_videos", type=int, default=3)
    args = ap.parse_args()
    m = fetch_assets(args.script_json, args.outdir, args.want, args.want_videos)
    print("Saved", len(m), "items to", args.outdir)
