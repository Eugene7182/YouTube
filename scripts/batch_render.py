
import argparse, json, os, subprocess, sys, time

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--jsonl", required=True, help="One JSON per line (title, lines[], cta)")
    p.add_argument("--voice", required=True, help="Piper model path")
    p.add_argument("--bg", required=True)
    p.add_argument("--music", default="")
    p.add_argument("--outdir", required=True)
    args = p.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    with open(args.jsonl, encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            line = line.strip()
            if not line: continue
            j = json.loads(line)
            base = f"{idx:02d}_" + j["title"].strip().replace(" ", "_")[:40]
            script_path = os.path.join(args.outdir, base + ".json")
            wav_path = os.path.join(args.outdir, base + ".wav")
            mp4_path = os.path.join(args.outdir, base + ".mp4")

            json.dump(j, open(script_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

            subprocess.check_call([sys.executable, "scripts/tts_piper.py", "--script_json", script_path, "--voice", args.voice, "--out", wav_path])
            subprocess.check_call([sys.executable, "scripts/render_short.py", "--script", script_path, "--voice", wav_path, "--bg", args.bg, "--music", args.music, "--out", mp4_path])
            print("DONE:", mp4_path); time.sleep(0.1)

if __name__ == "__main__":
    main()
