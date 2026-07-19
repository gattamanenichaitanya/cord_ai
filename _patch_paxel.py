from pathlib import Path

src = Path(r"C:\Users\gatta\AppData\Local\Temp\paxel_upload.sh")
# Git Bash /tmp often maps under the user's temp or under Git's tmp.
# Prefer the file we saved earlier if it exists; else download again via note.

candidates = [
    Path("/tmp/paxel_upload.sh"),
    Path(r"C:\Users\gatta\AppData\Local\Temp\paxel_upload.sh"),
]

# Also check common Git-for-Windows temp mount
import subprocess, os
bash = r"C:\Program Files\Git\bin\bash.exe"
raw = subprocess.check_output([bash, "-lc", "cygpath -w /tmp/paxel_upload.sh"], text=True).strip()
candidates.insert(0, Path(raw))

src = next((p for p in candidates if p.exists()), None)
if src is None:
    raise SystemExit(f"source not found. tried={candidates}")

text = src.read_text(encoding="utf-8", errors="replace")
# Find the interactive menu and replace with auto ALL_PROJECTS=1
needle_start = 'echo "None of your sessions match this directory." >&2'
idx = text.find(needle_start)
if idx < 0:
    raise SystemExit("needle_start not found")

# From the next "if [ -c /dev/tty ]" after that echo, replace the whole if/else
marker = 'if [ -c /dev/tty ]; then'
midx = text.find(marker, idx)
if midx < 0:
    raise SystemExit("tty if not found")

# Find matching end: the "fi" that closes this if, after the else branch with exit 1
# Look for the pattern that ends with exit 1 and fi shortly after
end_marker = 'echo "  $(rerun_cmd --all)" >&2\n        exit 1\n      fi'
eidx = text.find(end_marker, midx)
if eidx < 0:
    raise SystemExit("end_marker not found")
eidx_end = eidx + len(end_marker)

replacement = (
    'echo "No matching sessions for this directory — '
    'auto-selecting Analyze ALL projects." >&2\n'
    '      ALL_PROJECTS=1'
)

new_text = text[:midx] + replacement + text[eidx_end:]
out = src.with_name("paxel_upload_auto.sh")
out.write_text(new_text, encoding="utf-8")
print(f"patched: {out}")
print(f"size: {out.stat().st_size}")
