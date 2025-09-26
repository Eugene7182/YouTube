# -*- coding: utf-8 -*-
import os, re, json, time, math, hashlib, argparse, pathlib, random
from urllib.parse import quote_plus
import requests
from PIL import Image
from io import BytesIO

TIMEOUT = 20
HEADERS = {"User-Agent": "Dark&Strange/1.0"}
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
    if not key: return []
    base = "https://pixabay.com/api/"
    r = _get(base, params={"key": key, "q": q, "image_type":"photo", "orientation":"vertical", "safesearch":"true"})
    items = []
    for h in r.json().get("hits", []):
        items.append(dict(kind="image", url=h["largeImageURL"], source="pixabay", id=str(h["id"]),
                          author=h.get("user"), license="Pixabay License"))
    return items

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
    pexels_key = os.getenv("PEXELS_API_KEY") or ""
    pixabay_key = os.getenv("PIXABAY_API_KEY") or ""
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

    for q in seeds:
        if len([m for m in meta if m["kind"]=="video"]) < want_videos:
            for it in fetch_pexels_videos(q, pexels_key, per_page=4):
                if len([m for m in meta if m["kind"]=="video"]) >= want_videos: break
                try: add_item(it)
                except: pass
        if len(meta) >= want: break

    for q in seeds:
        if len(meta) >= want: break
        for it in fetch_pexels_photos(q, pexels_key, per_page=6):
            if len(meta) >= want: break
            try: add_item(it)
            except: pass
        if len(meta) >= want: break
        for it in fetch_pixabay(q, pixabay_key, per_page=6):
            if len(meta) >= want: break
            try: add_item(it)
            except: pass
        if len(meta) >= want: break
        for it in fetch_commons(q, per_page=6):
            if len(meta) >= want: break
            try: add_item(it)
            except: pass

    with open(os.path.join(outdir, "_attribution.json"), "w", encoding="utf-8") as f:
        json.dump(dict(script=script_json, seeds=seeds, items=meta,
                       note="Stock only; Pexels/Pixabay/Wikimedia licenses logged."), f, ensure_ascii=False, indent=2)
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
