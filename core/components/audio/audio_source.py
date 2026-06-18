from __future__ import annotations
import math
from core.ecs import Component, ComponentRegistry
from core.math3d import Vec3
from core.components.inspector_meta import FieldType, InspectorField
from core.audio_system import AudioSystem, AudioSourceManager
from core.logger import Logger


@ComponentRegistry.register
class AudioSource(Component):
    _icon = "AudioSource.png"
    _gizmo_icon_color = (80, 220, 80)
    _gizmo_icon_label = "A"

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("clip_path", "Clip", FieldType.RESOURCE_PATH, file_filter="Audio (*.wav *.mp3 *.ogg)"),
            InspectorField("volume", "Volume", FieldType.FLOAT, min_val=0.0, max_val=1.0, step=0.01),
            InspectorField("pitch", "Pitch", FieldType.FLOAT, min_val=-3.0, max_val=3.0, step=0.01),
            InspectorField("loop", "Loop", FieldType.BOOL),
            InspectorField("play_on_awake", "Play On Awake", FieldType.BOOL),
            InspectorField("spatial_blend", "Spatial Blend", FieldType.FLOAT, min_val=0.0, max_val=1.0, step=0.01),
            InspectorField("volume_rolloff", "Volume Rolloff", FieldType.CURVE),
            InspectorField("min_distance", "Min Distance", FieldType.FLOAT, min_val=0.0, max_val=10000.0, step=0.5, decimals=2),
            InspectorField("max_distance", "Max Distance", FieldType.FLOAT, min_val=0.0, max_val=10000.0, step=1.0, decimals=2),
        ]

    def __init__(self):
        super().__init__()
        self.clip_path: str = ""
        self.volume: float = 1.0
        self.pitch: float = 1.0
        self.loop: bool = False
        self.play_on_awake: bool = False
        self.spatial_blend: float = 1.0
        self.volume_rolloff: list[list[float]] = [[0, 1], [1, 0]]
        self.min_distance: float = 1.0
        self.max_distance: float = 50.0
        self._source_id: int = 0
        self._playing: bool = False

    def on_start(self):
        if self.play_on_awake and self.clip_path and not self._playing:
            self.play()

    def on_enable(self):
        if self.clip_path and not self._playing:
            self.play()

    def on_disable(self):
        if self._source_id:
            mgr = AudioSourceManager.instance()
            if mgr:
                mgr.stop(self._source_id)
                self._source_id = 0
            self._playing = False

    def on_destroy(self):
        if self._source_id:
            mgr = AudioSourceManager.instance()
            if mgr:
                mgr.stop(self._source_id)
                self._source_id = 0

    @staticmethod
    def linear_preset() -> list[list[float]]:
        return [[0, 1], [1, 0]]

    @staticmethod
    def logarithmic_preset() -> list[list[float]]:
        keys = [[0.0, 1.0]]
        for t in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
            keys.append([t, 1.0 / (1.0 + 2.0 * t)])
        keys.append([1.0, 0.0])
        return keys

    def play(self):
        if not self.clip_path or self._playing: return
        audio_sys = AudioSystem.instance()
        if not audio_sys: return
        mgr = AudioSourceManager.instance()
        if not mgr: return
        source = mgr.play(
            clip_path=self.clip_path,
            loop=self.loop,
            volume=self.volume,
            pitch=self.pitch,
            spatial_blend=self.spatial_blend,
            min_distance=self.min_distance,
            max_distance=self.max_distance,
            volume_rolloff=self.volume_rolloff,
        )
        if source:
            self._source_id = source
            self._playing = True

    def stop(self):
        if not self._source_id or not self._playing: return
        mgr = AudioSourceManager.instance()
        if mgr:
            mgr.stop(self._source_id)
            self._source_id = 0
        self._playing = False

    @property
    def is_playing(self) -> bool: return self._playing

    def on_update(self, dt: float):
        if not self._source_id or not self._playing: return
        try:
            import openal as al
            state = al.ctypes.c_int()
            al.alGetSourcei(self._source_id, al.AL_SOURCE_STATE, state)
            if state.value != al.AL_PLAYING and self.clip_path:
                # Logger.debug(f"AudioSource stopped, restarting loop={self.loop}")
                self.stop()
                if self.loop:
                    self.play()
                return

            mgr = AudioSourceManager.instance()
            if not mgr: return

            tr = self.transform
            pos = (0.0, 0.0, 0.0)
            if tr:
                p = tr.position
                pos = (p.x, p.y, p.z)
            # else:
            #     Logger.debug("AudioSource: no Transform, using (0,0,0)")

            # Logger.debug(f"AudioSource src={self._source_id} entity_pos=({pos[0]:.2f},{pos[1]:.2f},{pos[2]:.2f})")
            mgr.update_source(self._source_id, self.volume, self.pitch, pos, self.spatial_blend)
        except Exception as e:
            Logger.error(f"AudioSource.on_update error: {e}")

    def gizmo_lines(self) -> list[tuple[Vec3, Vec3, list[float]]]:
        tr = self.transform
        if not tr:
            return []
        pos = tr.position
        min_dist = self.min_distance
        max_dist = self.max_distance
        lines: list[tuple[Vec3, Vec3, list[float]]] = []
        segments = 24
        min_color = [0.2, 1.0, 0.2, 0.5]
        max_color = [1.0, 0.7, 0.1, 0.4]
        if min_dist > 0.01:
            for axis_idx in range(3):
                pts = []
                for i in range(segments + 1):
                    theta = 2.0 * math.pi * i / segments
                    if axis_idx == 0:
                        pt = Vec3(0, math.cos(theta) * min_dist, math.sin(theta) * min_dist)
                    elif axis_idx == 1:
                        pt = Vec3(math.cos(theta) * min_dist, 0, math.sin(theta) * min_dist)
                    else:
                        pt = Vec3(math.cos(theta) * min_dist, math.sin(theta) * min_dist, 0)
                    pts.append(pos + pt)
                for i in range(segments):
                    lines.append((pts[i], pts[i + 1], min_color))
        if max_dist > 0.01 and max_dist > min_dist:
            for axis_idx in range(3):
                pts = []
                for i in range(segments + 1):
                    theta = 2.0 * math.pi * i / segments
                    if axis_idx == 0:
                        pt = Vec3(0, math.cos(theta) * max_dist, math.sin(theta) * max_dist)
                    elif axis_idx == 1:
                        pt = Vec3(math.cos(theta) * max_dist, 0, math.sin(theta) * max_dist)
                    else:
                        pt = Vec3(math.cos(theta) * max_dist, math.sin(theta) * max_dist, 0)
                    pts.append(pos + pt)
                for i in range(segments):
                    lines.append((pts[i], pts[i + 1], max_color))
        return lines

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "clip_path": self.clip_path, "volume": self.volume, "pitch": self.pitch,
            "loop": self.loop, "play_on_awake": self.play_on_awake,
            "spatial_blend": self.spatial_blend,
            "volume_rolloff": self.volume_rolloff or [[0, 1], [1, 0]],
            "min_distance": self.min_distance, "max_distance": self.max_distance
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> AudioSource:
        a = cls()
        a.enabled = data.get("enabled", True)
        a.clip_path = data.get("clip_path", "")
        a.volume = data.get("volume", 1.0)
        a.pitch = data.get("pitch", 1.0)
        a.loop = data.get("loop", False)
        a.play_on_awake = data.get("play_on_awake", False)
        a.spatial_blend = data.get("spatial_blend", 1.0)
        a.volume_rolloff = data.get("volume_rolloff", [[0, 1], [1, 0]])
        a.min_distance = data.get("min_distance", 1.0)
        a.max_distance = data.get("max_distance", 50.0)
        return a
