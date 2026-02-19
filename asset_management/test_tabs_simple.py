import urllib.request
from html.parser import HTMLParser

class SimpleHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_tab = False
        self.in_active = False
        self.tabs = []
        self.current_text = ""
        
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == 'a' and 'class' in attrs_dict and 'tab' in attrs_dict['class']:
            self.in_tab = True
            if 'active' in attrs_dict['class']:
                self.in_active = True
        
    def handle_endtag(self, tag):
        if tag == 'a' and self.in_tab:
            tab_info = (self.current_text.strip(), self.in_active)
            self.tabs.append(tab_info)
            self.in_tab = False
            self.in_active = False
            self.current_text = ""
    
    def handle_data(self, data):
        if self.in_tab:
            self.current_text += data

# Проверяем основную вкладку
response = urllib.request.urlopen('http://127.0.0.1:5000/asset/2641')
html = response.read().decode('utf-8')

parser = SimpleHTMLParser()
parser.feed(html)

print(f"Найдено вкладок: {len(parser.tabs)}")
for text, active in parser.tabs:
    status = "АКТИВНА" if active else "неактивна"
    print(f"- {text} ({status})")

# Проверяем наличие ID вкладок
if 'id="main-tab"' in html:
    print("✅ Основной контент найден")
if 'id="history-tab"' in html:
    print("✅ Контент истории найден")
if 'tab-content active' in html:
    print("✅ Активный контент найден")
