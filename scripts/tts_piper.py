
import argparse, subprocess, tempfile, json, os, sys

def synth_piper(text, model_path, out_wav, rate=48000):
    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        f.write(text)
        f.flush()
        cmd = ["piper", "--model", model_path, "--input", f.name, "--output_file", out_wav, "--sample_rate", str(rate)]
        subprocess.check_call(cmd)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--script_json", required=True, help="Path to JSON with {title, lines[], cta}")
    p.add_argument("--voice", required=True, help="Piper .onnx model")
    p.add_argument("--out", required=True, help="Output WAV path")
    args = p.parse_args()
    j = json.load(open(args.script_json, encoding="utf-8"))
    text = ("\n".join(j["lines"]) + "\n" + j.get("cta","")).strip()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    try:
        synth_piper(text, args.voice, args.out)
        print("TTS OK:", args.out)
    except subprocess.CalledProcessError as e:
        print("Piper failed:", e, file=sys.stderr); sys.exit(1)
