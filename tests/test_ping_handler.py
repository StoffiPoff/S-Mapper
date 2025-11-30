from s_mapper import KeyMapperApp

class DummyCursor:
    def movePosition(self, *args, **kwargs):
        pass

class DummyPingOutput:
    def __init__(self):
        self.inserted_html = None
        self._cursor = None

    def toPlainText(self):
        return ''

    def textCursor(self):
        return DummyCursor()

    def setTextCursor(self, cursor):
        self._cursor = cursor

    def insertHtml(self, html):
        self.inserted_html = html

class DummyClipboard:
    def text(self):
        return '127.0.0.1'

class DummyApp:
    def __init__(self):
        self.ping_output_view = DummyPingOutput()
        self.clipboard = DummyClipboard()
        self._last_color = None

    def update_ping_indicator(self, color):
        self._last_color = color


def test_handle_ping_result_escapes_html():
    app = DummyApp()

    # Call handle_ping_result as an unbound method using our dummy app
    KeyMapperApp.handle_ping_result(app, 'green', '<div>OK & <script>alert(1)</script></div>')

    assert app._last_color == 'green'
    assert app.ping_output_view.inserted_html is not None
    # Ensure the output has been escaped (no raw '<script>' should be present)
    assert '<script>' not in app.ping_output_view.inserted_html
    assert '&lt;script&gt;' in app.ping_output_view.inserted_html
