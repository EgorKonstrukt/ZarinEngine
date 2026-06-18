from __future__ import annotations
from core.ecs import Component, ComponentRegistry
from core.audio_system import AudioSystem
from core.logger import Logger


@ComponentRegistry.register
class AudioListener(Component):
    _icon = "AudioListener.png"
    _gizmo_icon_color = (80, 220, 80)
    _gizmo_icon_label = "L"
    _show_gizmo_icon: bool = False

    @classmethod
    def _inspector_fields(cls) -> list:
        return []

    def on_start(self):
        pass

    def on_update(self, dt: float):
        audio_sys = AudioSystem.instance()
        # if not audio_sys:
        #     Logger.debug("AudioListener: no AudioSystem instance")
        #     return
        tr = self.transform
        # if not tr:
        #     Logger.debug("AudioListener: no Transform component")
        #     return
        pos = tr.position
        forward = tr.forward
        up = tr.up
        # Logger.debug(f"Listener pos=({pos.x:.2f},{pos.y:.2f},{pos.z:.2f}) fwd=({forward.x:.2f},{forward.y:.2f},{forward.z:.2f})")
        audio_sys.set_listener_position((pos.x, pos.y, pos.z))
        audio_sys.set_listener_orientation((forward.x, forward.y, forward.z), (up.x, up.y, up.z))

    def serialize(self) -> dict: return super().serialize()

    @classmethod
    def deserialize(cls, data: dict) -> AudioListener:
        al = cls()
        al.enabled = data.get("enabled", True)
        return al
