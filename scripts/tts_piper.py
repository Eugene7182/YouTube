import shutil, glob, os, subprocess, tempfile, json, sys, argparse

def _find_piper_exe():
    # 1) env var
    exe = os.environ.get("PIPER_EXE")
    if exe and os.path.isfile(exe):
        return exe
    # 2) tools\piper\**\piper.exe (handles nested subfolder)
    found = glob.glob(os.path.join("tools", "piper", "**", "piper.exe"), recursive=True)
    if found:
        return found[0]
    # 3) from PATH
    exe = shutil.which("piper")
    if exe:
        return exe
    raise FileNotFoundError("piper.exe not found. Set PIPER_EXE or put piper in PATH.")

def synth_piper(text, model_path, out_wav, rate=48000):
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
        f.write(text)
        temp_path = f.name
    cmd = [_find_piper_exe(), "--model", model_path, "--output_file", out_wav, "--sample_rate", str(rate)]
    with open(temp_path, "rb") as src:
        subprocess.check_call(cmd, stdin=src)
    try:
        os.remove(temp_path)
    except OSError:
        pass

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--script_json", required=True, help="Path to JSON with {title, lines[], cta}")
    p.add_argument("--voice", required=True, help="Piper .onnx model")
    p.add_argument("--out", required=True, help="Output WAV path")
    args = p.parse_args()
    j = json.load(open(args.script_json, encoding="utf-8"))
    text = ("\n".join(j["lines"]) + "\n" + j.get("cta", "")).strip()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    try:
        synth_piper(text, args.voice, args.out)
        print("TTS OK:", args.out)
    except subprocess.CalledProcessError as e:
        print("Piper failed:", e, file=sys.stderr)
        sys.exit(1)
