from pathlib import Path
import random

def gen_cats(title: str) -> str:
    T = Path("templates/script_template_en.md").read_text(encoding="utf-8")
    hooks = [
        "Luxury bed vs cardboard box. Guess what wins?",
        "Today: the red dot files a complaint.",
        "Three alarms vs one very lazy cat.",
        "Bossfight: vacuum cleaner with low battery.",
    ]
    setups = [
        "Iris brings a fancy bed. Plombir inspects it like a critic.",
        "Cashback the hamster claims he found a *deal*. It's a box.",
        "Three alarms ring. Plombir has a plan.",
    ]
    twists = [
        "A wrinkled box appears. First class dive.",
        "The laser stops. Plombir freezes—it's behind him.",
        "Alarm one: paw. Two: tail. Three: nose.",
        "Hamster pulls the plug from the vacuum. Tactical victory!",
    ]
    punches = [
        "Iris: It's not a box. It's Box Edition.",
        "Plombir: I wasn't scared. I was charging.",
        "Made it by lunch. Perfect schedule.",
    ]
    data = {
        "title": title,
        "hook": random.choice(hooks),
        "setup": random.choice(setups),
        "twist": random.choice(twists),
        "punch": random.choice(punches),
    }
    return T.format(**data)

def gen_picks(title: str) -> str:
    T = Path("templates/script_template_pick_en.md").read_text(encoding="utf-8")
    pts = [
        ["AMOLED 120Hz under $300", "5000 mAh battery+", "2 years of updates minimum"],
        ["Best camera under $400", "OIS matters more than 108 MP", "Balanced SoC over raw clocks"],
    ]
    p = random.choice(pts)
    return T.format(title=title, p1=p[0], p2=p[1], p3=p[2])

def generate_script(title: str, mode: str) -> str:
    if mode == "shorts":
        return gen_cats(title)
    else:
        return gen_picks(title)

if __name__ == "__main__":
    print(generate_script("Box vs Bed — Cat chooses luxury cardboard", mode="shorts"))
