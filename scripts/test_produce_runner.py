from scripts.produce_shorts import run_one, load_jsonl
from pathlib import Path
import traceback

def main():
    items = load_jsonl('data/topics_test2.jsonl')
    outdir = Path('build/test_run')
    for it in items:
        try:
            print('\n=== RUN ITEM ===', it)
            res = run_one(it, 'assets/voices/en_US-amy-medium.onnx', outdir, want_assets=10, want_videos=3)
            print('OK ->', res)
        except Exception as e:
            print('EXCEPTION for', it)
            traceback.print_exc()

if __name__ == '__main__':
    main()
