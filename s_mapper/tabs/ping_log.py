from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextEdit


def build_ping_log_tab(app):
    """Create and attach the 'Ping Log' tab UI to the app instance."""
    ping_log_tab = QWidget()
    app.tabs.addTab(ping_log_tab, "Ping Log")
    ping_log_layout = QVBoxLayout(ping_log_tab)

    app.ping_output_view = QTextEdit()
    app.ping_output_view.setReadOnly(True)
    app.ping_output_view.setStyleSheet("background-color: #0d0d0d; color: #d4d4d4; font-family: 'Courier New', Courier, monospace;")
    ping_log_layout.addWidget(app.ping_output_view)

    return ping_log_tab
