def callback_button(text, callback_data):
    return {"text": text, "callback_data": callback_data}


def url_button(text, url):
    return {"text": text, "url": url}


def inline_keyboard(*rows):
    return {"inline_keyboard": [list(row) for row in rows]}
