import os

files = [
    "m1_trend.py",
    "m2_revert.py",
    "m2_revert_opt.py",
    "m3_breakout.py",
    "m4_leadership.py",
    "m5_defensive.py",
    "m6_high_beta.py",
    "m7_washout.py",
    "m8_camarilla.py",
    "m9_controller.py"
]

output_file = "combined.txt"
separator = "\n" + "="*50 + "\n"

with open(output_file, "w", encoding="utf-8") as out:
    for file in files:
        if not os.path.exists(file):
            print(f"Skip (not found): {file}")
            continue

        with open(file, "r", encoding="utf-8") as f:
            content = f.read()

        out.write(f"# FILE: {file}\n")
        out.write(content)
        out.write(separator)

print(f"Done -> {output_file}")
