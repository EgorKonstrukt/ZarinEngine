import sys
import os
import traceback
import json

from PyQt6.QtGui import QSurfaceFormat

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DEFAULT_SCENE = "SampleScene.zpes"


def excepthook(exc_type, exc_value, exc_traceback):
    from core.logger import Logger
    tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    Logger.error(f"Unhandled exception: {exc_value}\n{tb_str}")
    print(f"[Zarin Player] Unhandled exception:\n{tb_str}", file=sys.stderr)


sys.excepthook = excepthook


def main():
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    QApplication.setAttribute(Qt.ApplicationAttribute(79))
    app = QApplication(sys.argv)
    app.setApplicationName("Zarin Player")
    app.setOrganizationName("Zarin")
    app.setStyle("Fusion")

    fmt = QSurfaceFormat()
    fmt.setDepthBufferSize(24)
    fmt.setVersion(4, 6)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    QSurfaceFormat.setDefaultFormat(fmt)

    from core.engine import Engine
    from editor.scene_viewport import SceneViewport
    from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout
    from PyQt6.QtCore import QTimer

    engine = Engine()
    engine.initialize()
    engine.plugin_manager.load_directory("plugins")
    engine.plugin_manager.load_directory("plugins/user")

    project_settings = {}
    settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ProjectSettings.json")
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r") as f:
                project_settings = json.load(f)
        except Exception:
            pass

    scene_path = DEFAULT_SCENE
    if len(sys.argv) > 1:
        arg_path = sys.argv[1]
        if os.path.exists(arg_path):
            scene_path = arg_path
    elif "default_scene" in project_settings.get("project", {}):
        sp = project_settings["project"]["default_scene"]
        if sp:
            full = os.path.join(os.path.dirname(os.path.abspath(__file__)), sp)
            if os.path.exists(full):
                scene_path = full

    window = QMainWindow()
    window.setWindowTitle("Zarin Player")
    container = QWidget()
    window.setCentralWidget(container)
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)

    viewport = SceneViewport(engine, window)
    engine.viewport = viewport
    layout.addWidget(viewport)

    screen = app.primaryScreen()
    if screen:
        window.resize(screen.size() * 0.8)
    else:
        window.resize(1280, 720)
    window.show()

    if os.path.exists(scene_path):
        engine.load_scene(scene_path)
        QTimer.singleShot(100, lambda: (engine.start_play() if engine.scene else None))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
