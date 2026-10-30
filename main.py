"""import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
"""

# main.py
import sys
import os

# 1. Добавляем корневую папку проекта в sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# 2. Указываем локальную папку с моделями (автономный режим)
project_dir = os.path.dirname(os.path.abspath(__file__))
local_models_dir = os.path.join(project_dir, "models")

if os.path.exists(local_models_dir):
    os.environ["HF_HOME"] = local_models_dir
    os.environ["TRANSFORMERS_CACHE"] = local_models_dir
    os.environ["HF_HUB_CACHE"] = os.path.join(local_models_dir, "hub")
    print(f"[INIT] Используем локальные модели из: {local_models_dir}")
else:
    print("[INIT] Локальные модели не найдены, будет использован стандартный кэш.")

from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()