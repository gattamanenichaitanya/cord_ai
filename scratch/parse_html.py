import re

log_path = r"c:\Users\gatta\OneDrive\Documents\CordAI\cord-ai-poc\scratch\sidebar_dump.html"
with open(log_path, "r", encoding="utf-8") as f:
    html = f.read()

print("Labels:")
for m in re.finditer(r'<label[^>]*>(.*?)</label>', html, flags=re.DOTALL):
    print(f"Label text (raw): {m.group(1).strip()}")
    
print("Looking for Choose a value block...")
for m in re.finditer(r'<div[^>]*class="[^"]*FormControl[^"]*"[^>]*>(.*?)</div></div></div></div>', html, flags=re.DOTALL):
    if "Choose a value" in m.group(1):
        print("Found FormControl containing 'Choose a value':")
        print(m.group(0)[:2000]) # Print the matched block

