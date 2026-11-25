from html.parser import HTMLParser

from .change_detector import normalize_text


class ContentExtractor(HTMLParser):
    IGNORED_TAGS = {
        "script",
        "style",
        "noscript",
        "svg",
        "head",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.ignored_stack = []

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORED_TAGS:
            self.ignored_stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.IGNORED_TAGS and tag in self.ignored_stack:
            index = len(self.ignored_stack) - 1 - self.ignored_stack[::-1].index(tag)
            del self.ignored_stack[index:]

    def handle_data(self, data):
        if not self.ignored_stack:
            self.parts.append(data)


def extract_text(html: str) -> str:
    parser = ContentExtractor()
    parser.feed(html)
    parser.close()

    return normalize_text(" ".join(parser.parts))
