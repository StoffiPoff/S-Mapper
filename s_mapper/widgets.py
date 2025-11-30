import json
import logging
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QListWidget, QTextBrowser, QLabel
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt

from .utils import resource_path


class HelpWindow(QWidget):
    """Simple help viewer with a list of topics and an HTML content pane."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("S-Mapper Help")
        self.setWindowIcon(QIcon(resource_path('assets/Square44x44Logo.png')))
        self.setGeometry(200, 200, 700, 500)
        self.initUI()

    def initUI(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-size: 10pt;
            }
            QListWidget {
                background-color: #252526;
                border: 1px solid #3a3d41;
            }
            QTextBrowser {
                background-color: #252526;
                border: 1px solid #3a3d41;
            }
        """)
        layout = QHBoxLayout(self)

        self.topics_list = QListWidget()
        self.topics_list.setMaximumWidth(220)
        layout.addWidget(self.topics_list)

        self.content_display = QTextBrowser()
        self.content_display.setOpenExternalLinks(True)
        layout.addWidget(self.content_display)

        self.topics_list.currentItemChanged.connect(self.display_topic)
        self.populate_help()

    def populate_help(self):
        try:
            path = resource_path('assets/help_topics.json')
            with open(path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
                if isinstance(data, dict):
                    self.help_data = data
                    self.topics_list.clear()
                    self.topics_list.addItems(list(self.help_data.keys()))
                    self.topics_list.setCurrentRow(0)
                    return
        except Exception as e:
            logging.warning('Failed to load help topics file: %s', e)

        self.help_data = {
            "Introduction": "<h1>Introduction</h1><p>Welcome to S-Mapper — a lightweight input remapping tool.</p>",
            "Usage": "<h1>Usage</h1><p>Create mappings and scope them to a target window title. Use the Ping Log to see ping output.</p>"
        }
        self.topics_list.clear()
        self.topics_list.addItems(list(self.help_data.keys()))
        self.topics_list.setCurrentRow(0)

    def display_topic(self, current, previous):
        if current:
            topic = current.text()
            self.content_display.setHtml(self.help_data.get(topic, "<p>Help topic not found.</p>"))


class PingStatusLabel(QLabel):
    """A frameless, floating QLabel used to display ping status near the cursor."""
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("font-size: 14pt; font-weight: bold; padding: 5px;")

    def show_message(self, text, color, position):
        self.setText(text)
        self.setStyleSheet(f"color: {color}; font-size: 14pt; font-weight: bold; padding: 5px; background-color: rgba(20, 20, 20, 0.7); border-radius: 5px;")
        self.adjustSize()
        self.move(position.x() + 10, position.y() - self.height())
        self.show()
