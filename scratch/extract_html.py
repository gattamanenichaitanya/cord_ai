import re

log_path = r"C:\Users\gatta\.gemini\antigravity\brain\d80acd71-cdf8-47c2-91db-fd452bb115d9\.system_generated\tasks\task-2422.log"
with open(log_path, "r", encoding="utf-8") as f:
    text = f.read()

# Find all occurrences of "Visible sidebar/panel HTML snippet:"
# and dump the following lines
matches = [m.start() for m in re.finditer("Visible sidebar/panel HTML snippet:", text)]
for idx, pos in enumerate(matches):
    print(f"--- SNIPPET {idx} ---")
    snippet = text[pos:pos+4000]
    print(snippet)
    print("\n" + "="*50 + "\n")
