from core.settings import settings

SUPPORTED_BROWSERS = [
    ("none", "Отключено (Без cookies)"),
    ("chrome", "Google Chrome"),
    ("edge", "Microsoft Edge"),
    ("firefox", "Mozilla Firefox"),
    ("brave", "Brave Browser"),
    ("opera", "Opera"),
    ("vivaldi", "Vivaldi")
]

def get_cookies_config():
    browser = settings.get("browser_cookies", "none")
    if browser and browser != "none":
        return (browser,)
    return None
