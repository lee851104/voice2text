STYLE = """
QMainWindow, QDialog { background: #f4f6f8; }
QWidget { color: #1b2b3c; font-family: 'Microsoft JhengHei UI', 'Microsoft JhengHei', 'Segoe UI'; font-size: 13px; }
QLabel#brand { font-size: 24px; font-weight: 700; }
QLabel#muted { color: #68798b; }
QLabel#badge { background: #e3f2ed; color: #196852; border-radius: 10px; padding: 5px 12px; }
QFrame#card { background: white; border: 1px solid #dde4eb; border-radius: 12px; }
QFrame#drop { background: #f8fbfc; border: 1px dashed #9dafbd; border-radius: 9px; }
QLineEdit, QDateEdit, QComboBox { background: white; border: 1px solid #cad4de; border-radius: 6px; padding: 7px 10px; min-height: 20px; }
QLineEdit:focus, QDateEdit:focus, QComboBox:focus { border: 1px solid #21836d; }
QPushButton { background: white; border: 1px solid #cbd5de; border-radius: 7px; padding: 8px 15px; min-height: 20px; }
QPushButton:hover { background: #edf3f6; border-color: #98afbd; }
QPushButton#primary { background: #176c58; color: white; border: 1px solid #176c58; font-weight: 600; }
QPushButton#primary:hover { background: #115541; }
QPushButton:disabled { color: #9ba6b2; background: #e9eef1; border-color: #dce3e9; }
QPushButton#primary:disabled { color: #9ba6b2; background: #e9eef1; border-color: #dce3e9; }
QToolButton { border: none; color: #426073; padding: 6px 0; }
QTableWidget, QListWidget, QPlainTextEdit { background: white; border: 1px solid #dce3e9; border-radius: 7px; selection-background-color: #d9eee7; selection-color: #14362b; }
QTableWidget::item { padding: 7px; border-bottom: 1px solid #eef2f5; }
QListWidget::item { padding: 10px; }
QHeaderView::section { background: #f0f4f7; color: #516576; padding: 9px; border: none; font-weight: 600; }
QTabWidget::pane { border: none; background: transparent; }
QTabBar::tab { padding: 10px 18px; color: #65798a; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #176c58; border-bottom-color: #176c58; font-weight: 700; }
QProgressBar { border: none; border-radius: 3px; background: #e3eaf0; max-height: 6px; min-height: 6px; }
QProgressBar::chunk { background: #278c71; border-radius: 3px; }
QSplitter::handle { background: transparent; width: 12px; }
QScrollBar:vertical { width: 10px; background: #f3f6f8; }
QScrollBar::handle:vertical { background: #c5d1da; border-radius: 4px; min-height: 30px; }
"""
