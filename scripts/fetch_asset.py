import argparse
import os
import sys
from pathlib import Path
from typing import Generator, Iterable, Optional, Tuple

import requests
import json

FALLBACK_QUERIES = ["dark texture", "misty forest", "moonlit sky"]
DEFAULT_ORIENTATION = "vertical"

PEXELS_ORIENTATION = {"vertical": "portrait", "horizontal": "landscape"}
PIXABAY_ORIENTATION = {"vertical": "vertical", "horizontal": "horizontal"}
PHOTO_SIZE_ORDER = ("original", "large2x", "large", "medium", "small")
VIDEO_SIZE_ORDER = ("large", "medium", "small", "tiny")


def log(message: str, *, enabled: bool) -> None:
    if enabled:
        print(message)


def ensure_extension(path: Path, kind: str) -> Path:
    if kind == "photo" and path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
        return path.with_suffix(".jpg")
    if kind == "video" and path.suffix.lower() not in {".mp4", ".mov", ".webm", ".mkv"}:
        return path.with_suffix(".mp4")
    return path


def iter_pexels(
    query: str,
    *,
    kind: str,
    orientation: str,
    count: int,
    min_width: int,
    min_height: int,
    verbose: bool,
) -> Generator[Tuple[str, int, int], None, None]:
    api_key = os.getenv("PEXELS_API_KEY")
    # fallback to secrets/api_keys.json if env var not set
    if not api_key:
        try:
            secret_path = Path("secrets/api_keys.json")
            if secret_path.exists():
                with secret_path.open("r", encoding="utf-8") as fh:
                    j = json.load(fh)
                    api_key = j.get("PEXELS_API_KEY")
        except Exception:
            api_key = None
    if not api_key:
        log("PEXELS_API_KEY is not set; skipping Pexels", enabled=verbose)
        return

    headers = {"Authorization": api_key}
    params = {"query": query, "per_page": str(max(1, min(count, 80)))}
    orientation_token = PEXELS_ORIENTATION.get(orientation)
    if orientation_token:
        params["orientation"] = orientation_token

    if kind == "photo":
        url = "https://api.pexels.com/v1/search"
    else:
        url = "https://api.pexels.com/videos/search"

    log(f"Pexels request: {url} params={params}", enabled=verbose)
    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    if kind == "photo":
        for photo in data.get("photos", []):
            width = int(photo.get("width") or 0)
            height = int(photo.get("height") or 0)
            if width < min_width or height < min_height:
                continue
            src = photo.get("src", {})
            for key in PHOTO_SIZE_ORDER:
                url_candidate = src.get(key)
                if url_candidate:
                    yield url_candidate, width, height
                    break
    else:
        for video in data.get("videos", []):
            files = video.get("video_files", [])
            sorted_files = sorted(
                files,
                key=lambda item: (int(item.get("width") or 0) * int(item.get("height") or 0)),
                reverse=True,
            )
            for file_info in sorted_files:
                width = int(file_info.get("width") or 0)
                height = int(file_info.get("height") or 0)
                if width < min_width or height < min_height:
                    continue
                link = file_info.get("link")
                if link:
                    yield link, width, height
                    break


def iter_pixabay(
    query: str,
    *,
    kind: str,
    orientation: str,
    count: int,
    min_width: int,
    min_height: int,
    safesearch: str,
    verbose: bool,
) -> Generator[Tuple[str, int, int], None, None]:
    api_key = os.getenv("PIXABAY_API_KEY")
    # fallback to secrets/api_keys.json if env var not set
    if not api_key:
        try:
            secret_path = Path("secrets/api_keys.json")
            if secret_path.exists():
                with secret_path.open("r", encoding="utf-8") as fh:
                    j = json.load(fh)
                    api_key = j.get("PIXABAY_API_KEY")
        except Exception:
            api_key = None
    if not api_key:
        log("PIXABAY_API_KEY is not set; skipping Pixabay", enabled=verbose)
        return

    if kind == "photo":
        base_url = "https://pixabay.com/api/"
    else:
        base_url = "https://pixabay.com/api/videos/"

    params = {
        "key": api_key,
        "q": query,
        "per_page": str(max(1, min(count, 200))),
        "safesearch": safesearch.lower(),
    }

    orientation_token = PIXABAY_ORIENTATION.get(orientation)
    if orientation_token:
        params["orientation"] = orientation_token

    if kind == "photo":
        params["image_type"] = "photo"
    else:
        params["image_type"] = "video"

    log(f"Pixabay request: {base_url} params={params}", enabled=verbose)
    response = requests.get(base_url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    hits = data.get("hits", [])
    if kind == "photo":
        for hit in hits:
            width = int(hit.get("imageWidth") or 0)
            height = int(hit.get("imageHeight") or 0)
            if width < min_width or height < min_height:
                continue
            candidates = [
                hit.get("largeImageURL"),
                hit.get("fullHDURL"),
                hit.get("imageURL"),
                hit.get("webformatURL"),
            ]
            for url_candidate in candidates:
                if url_candidate:
                    yield url_candidate, width, height
                    break
    else:
        for hit in hits:
            videos = hit.get("videos", {})
            for key in VIDEO_SIZE_ORDER:
                file_info = videos.get(key)
                if not file_info:
                    continue
                width = int(file_info.get("width") or 0)
                height = int(file_info.get("height") or 0)
                if width < min_width or height < min_height:
                    continue
                url_candidate = file_info.get("url")
                if url_candidate:
                    yield url_candidate, width, height
                    break


def download(url: str, destination: Path, *, verbose: bool) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    log(f"Downloading {url} -> {destination}", enabled=verbose)
    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with destination.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1 << 15):
                if chunk:
                    fh.write(chunk)


def select_asset(
    fetchers: Iterable,
    *,
    min_width: int,
    min_height: int,
    verbose: bool,
) -> Optional[Tuple[str, int, int]]:
    for fetch in fetchers:
        try:
            for url, width, height in fetch:
                log(f"Candidate {width}x{height}: {url}", enabled=verbose)
                if width >= min_width and height >= min_height:
                    return url, width, height
        except requests.HTTPError as exc:
            log(f"HTTP error: {exc}", enabled=verbose)
        except requests.RequestException as exc:
            log(f"Request failed: {exc}", enabled=verbose)
    return None


def build_fetchers(
    provider: str,
    query: str,
    *,
    args: argparse.Namespace,
) -> Generator:
    if provider == "pexels":
        yield iter_pexels(
            query,
            kind=args.kind,
            orientation=args.orientation,
            count=args.count,
            min_width=args.min_width,
            min_height=args.min_height,
            verbose=args.verbose,
        )
    elif provider == "pixabay":
        yield iter_pixabay(
            query,
            kind=args.kind,
            orientation=args.orientation,
            count=args.count,
            min_width=args.min_width,
            min_height=args.min_height,
            safesearch=args.safesearch,
            verbose=args.verbose,
        )
    else:
        yield from ()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch background assets from stock providers.")
    parser.add_argument("--query", required=True, help="Primary search query")
    parser.add_argument("--kind", choices=["photo", "video"], default="photo")
    parser.add_argument("--out", required=True, help="Output path for the downloaded file")
    parser.add_argument(
        "--provider",
        default="pexels,pixabay",
        help="Comma-separated providers priority list",
    )
    parser.add_argument(
        "--orientation",
        choices=["vertical", "horizontal"],
        default=DEFAULT_ORIENTATION,
        help="Desired asset orientation",
    )
    parser.add_argument("--min_width", type=int, default=0, help="Minimum width in pixels")
    parser.add_argument("--min_height", type=int, default=0, help="Minimum height in pixels")
    parser.add_argument(
        "--safesearch",
        choices=["true", "false"],
        default="true",
        help="Safe search flag for providers that support it",
    )
    parser.add_argument("--count", type=int, default=1, help="How many results to request per provider")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    providers = [provider.strip().lower() for provider in args.provider.split(",") if provider.strip()]
    if not providers:
        providers = ["pexels", "pixabay"]

    queries = [args.query] + FALLBACK_QUERIES
    output_path = ensure_extension(Path(args.out), args.kind)

    for query in queries:
        log(f"Searching for '{query}'", enabled=args.verbose)
        for provider in providers:
            log(f"Provider: {provider}", enabled=args.verbose)
            fetchers = build_fetchers(provider, query, args=args)
            asset = select_asset(
                fetchers,
                min_width=args.min_width,
                min_height=args.min_height,
                verbose=args.verbose,
            )
            if asset:
                url, width, height = asset
                log(f"Selected {width}x{height} asset from {provider}", enabled=args.verbose)
                download(url, output_path, verbose=args.verbose)
                print(str(output_path))
                return

    print("NO_RESULTS")
    sys.exit(2)


if __name__ == "__main__":
    main()

