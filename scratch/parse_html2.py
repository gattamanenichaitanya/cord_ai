import re
from html.parser import HTMLParser

log_path = r"c:\Users\gatta\OneDrive\Documents\CordAI\cord-ai-poc\scratch\sidebar_dump.html"
with open(log_path, "r", encoding="utf-8") as f:
    html = f.read()

class MyParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.buttons = []
        self.current_button = None
        self.current_text = ""

    def handle_starttag(self, tag, attrs):
        if tag == 'button' or tag == 'a':
            self.current_button = (tag, dict(attrs))
            self.current_text = ""

    def handle_data(self, data):
        if self.current_button is not None:
            self.current_text += data

    def handle_endtag(self, tag):
        if tag == 'button' or tag == 'a':
            if self.current_button:
                self.buttons.append((self.current_button[0], self.current_button[1], self.current_text.strip()))
            self.current_button = None

parser = MyParser()
parser.feed(html)

print("Buttons and Links found:")
for tag, attrs, text in parser.buttons:
    print(f"<{tag}> text='{text}' attrs={attrs}")

