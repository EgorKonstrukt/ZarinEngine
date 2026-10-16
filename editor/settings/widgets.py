# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDoubleSpinBox, QHBoxLayout, QSlider, QSpinBox, QWidget
from core.config.editor_scale import scale

SECTION_ICONS = {
    "editor": "fa5s.edit",
    "camera": "fa5s.camera",
    "rendering": "fa5s.palette",
    "gizmo": "fa5s.arrows-alt",
    "viewport": "fa5s.desktop",
    "console": "fa5s.terminal",
    "terminal": "fa5s.window-maximize",
    "profiler": "fa5s.chart-bar",
    "hierarchy": "fa5s.sitemap",
    "inspector": "fa5s.search",
    "project": "fa5s.folder-open",
    "engine": "fa5s.cogs",
    "collab": "fa5s.users",
    "undo": "fa5s.undo",
    "input": "fa5s.keyboard",
    "physics": "fa5s.atom",
    "audio": "fa5s.music",
    "toolbar": "fa5s.wrench",
    "file_assoc": "fa5s.file-code",
    "mesh_preview": "fa5s.cube",
}

SECTION_DESCRIPTIONS = {
    "editor": "Editor appearance and behavior",
    "camera": "Viewport camera settings",
    "rendering": "Graphics and rendering quality",
    "gizmo": "Transform gizmo appearance and behavior",
    "viewport": "Viewport display settings",
    "console": "Console log settings",
    "terminal": "Embedded terminal settings",
    "profiler": "Performance profiler settings",
    "hierarchy": "Hierarchy panel settings",
    "inspector": "Inspector panel settings",
    "project": "Project browser settings",
    "engine": "Engine time and physics settings",
    "collab": "Collaboration network settings",
    "undo": "Undo history settings",
    "input": "Input axis and sensitivity",
    "physics": "Physics simulation settings",
    "audio": "Audio volume settings",
    "toolbar": "Toolbar toggle states",
    "file_assoc": "File type associations in Windows",
    "mesh_preview": "3D model thumbnail preview appearance",
}

FIELD_TOOLTIPS = {
    "physics.multi_threaded": "Run physics simulation in a separate process for better performance",
    "editor.theme": "Editor color theme (restart required)",
    "editor.font_size": "Base font size in the editor (restart required)",
    "editor.ui_scale": "Global UI scale percentage (50-200, restart required)",
    "editor.language": "Editor UI language (restart required)",
    "editor.auto_save": "Automatically save the current scene",
    "editor.auto_save_interval": "Auto-save interval in seconds",
    "editor.thumb_cache_mode": "Thumbnail cache key: metadata (fast, uses mtime/size) or content (full file hash, slower but exact)",
    "editor.thumb_resolution": "Thumbnail render resolution in pixels (higher = sharper but slower)",
    "editor.hover_delay": "Delay in milliseconds before the resource hover preview appears near the cursor",
    "mesh_preview.camera_rot_x": "Camera X rotation angle in degrees for mesh thumbnails",
    "mesh_preview.camera_rot_y": "Camera Y rotation angle in degrees for mesh thumbnails",
    "mesh_preview.bg": "Background color [R, G, B, A] (0-1, A=0 is transparent)",
    "mesh_preview.tri": "Triangle fill color [R, G, B, A] (0-1)",
    "mesh_preview.wire": "Wireframe color [R, G, B, A] (0-1)",
    "mesh_preview.wire_width": "Wireframe line width in pixels",
    "camera.fov": "Camera field of view in degrees",
    "camera.near": "Near clipping plane distance",
    "camera.far": "Far clipping plane distance",
    "camera.move_speed": "Camera movement speed",
    "camera.fast_mult": "Speed multiplier when holding Shift",
    "camera.rotate_speed": "Camera orbit rotation speed",
    "camera.zoom_speed": "Camera zoom speed",
    "camera.pan_speed": "Camera pan speed",
    "camera.zoom_strength": "Zoom strength multiplier",
    "camera.damping": "Camera smooth movement damping",
    "camera.acceleration": "Camera movement acceleration",
    "camera.transition_speed": "Camera transition animation speed",
    "camera.zoom_smooth_speed": "Zoom smooth interpolation speed",
    "camera.use_ortho_in_2d": "Use orthographic projection in 2D mode",
    "camera.speed_boost_enabled": "Enable camera speed boost",
    "camera.speed_boost_mult": "Speed boost multiplier",
    "camera.speed_boost_ramp_time": "Time to reach full boost speed (seconds)",
    "rendering.vsync": "Enable vertical synchronization",
    "rendering.target_fps": "Target frame rate (0 = unlimited)",
    "rendering.show_grid": "Show the reference grid in the viewport",
    "rendering.grid_size": "Reference grid cell size",
    "rendering.grid_world_size": "Reference grid total world size",
    "rendering.exposure": "HDR exposure in EV applied before tonemapping",
    "rendering.light_scale": "Global multiplier applied to all light intensities",
    "rendering.ambient": "Ambient light color [R, G, B] (0-1)",
    "rendering.selection_outline": "Selection outline color [R, G, B, A] (0-1)",
    "rendering.selection_outline_thickness": "Selection outline thickness",
    "rendering.tick_rate": "Game logic update rate (ticks per second)",
    "rendering.fixed_tick_rate": "Physics fixed update rate (ticks per second)",
    "rendering.max_lights": "Maximum number of dynamic lights",
    "rendering.high_precision_rtc": "Camera-relative 64-bit rendering on CPU, fixes jitter at far coordinates",
    "rendering.high_precision_gpu": "Double precision (float64) in all shaders, requires fp64 GPU",
    "rendering.play_viewport_throttle": "Play mode dual-viewport throttle: editor, game, or off",
    "rendering.play_viewport_throttle_step": "Play mode throttle rate (render every Nth frame)",
    "gizmo.handle_size": "Gizmo handle size in world units",
    "gizmo.base_axis_length": "Length of gizmo axis arrows",
    "gizmo.plane_handle_size": "Size of plane translation handles",
    "gizmo.pick_threshold": "Gizmo click pick threshold in pixels",
    "gizmo.arrow_size_ratio": "Size ratio of arrowheads",
    "gizmo.center_handle_size": "Size of the center (scale all) handle",
    "gizmo.screen_axis_length": "Length of screen-space axis overlay",
    "gizmo.line_width": "Gizmo line width",
    "gizmo.show_delta_label": "Show delta value label during drag",
    "gizmo.smooth_snap": "Enable smooth snap interpolation",
    "gizmo.smooth_snap_speed": "Smooth snap interpolation speed",
    "gizmo.show_icons": "Show component icons in the viewport",
    "gizmo.icon_scale": "Scale of component icons",
    "gizmo.selection_bounds": "Show animated bounding box around selected entities",
    "gizmo.selection_bounds_speed": "Smooth animation speed for selection bounds",
    "gizmo.selection_bounds_color": "Selection bounds line color [R, G, B] (0-1)",
    "gizmo.multigizmo_enabled": "Enable Vertex Tools style Multi Gizmo (Move+Rotate+Scale combined) - requires restart or toggle in toolbar",
    "gizmo.multigizmo_alignment": "Multi Gizmo alignment: local, world, view, custom",
    "gizmo.multigizmo_orientation_lock": "Multi Gizmo orientation lock - retain orientation when rotating",
    "gizmo.multigizmo_visible": "Multi Gizmo visibility",
    "viewport.clear": "Viewport clear color [R, G, B] (0-1)",
    "viewport.no_scene": "No-scene background color [R, G, B] (0-1)",
    "viewport.update_interval": "Viewport update interval (ms)",
    "viewport.grid_step": "Grid step size for snapping",
    "console.font_size": "Console font size",
    "console.font_family": "Console font family name",
    "console.max_blocks": "Maximum console log blocks",
    "console.refresh_interval": "Console refresh interval (ms)",
    "terminal.font_size": "Terminal font size",
    "terminal.font_family": "Terminal font family name",
    "profiler.enabled": "Enable the performance profiler",
    "profiler.update_interval": "Profiler update interval (seconds)",
    "profiler.max_samples": "Maximum profiler samples to keep",
    "profiler.refresh_interval": "Profiler UI refresh interval (ms)",
    "hierarchy.refresh_interval": "Hierarchy panel refresh interval (ms)",
    "inspector.refresh_interval": "Inspector panel refresh interval (ms)",
    "project.thumb_size": "Project browser thumbnail size",
    "engine.time_scale": "Global time scale factor",
    "engine.fixed_update_dt": "Fixed update timestep (seconds)",
    "collab.cursor_rate": "Collaboration cursor sync rate (Hz)",
    "collab.camera_rate": "Collaboration camera sync rate (Hz)",
    "collab.transform_rate": "Collaboration transform sync rate (Hz)",
    "collab.gizmo_rate": "Collaboration gizmo sync rate (Hz)",
    "collab.ping_interval": "Collaboration ping interval (seconds)",
    "collab.poll_interval": "Collaboration poll interval (seconds)",
    "undo.max_stack": "Maximum undo history steps",
    "input.control_scheme": "Control scheme: fps = first person, tps = third person",
    "input.horizontal": "Horizontal movement axis (positive,negative key names, comma separated)",
    "input.vertical": "Vertical movement axis (positive,negative key names, comma separated)",
    "input.jump": "Jump button binding",
    "input.fire": "Fire / primary action button binding",
    "input.crouch": "Crouch button binding",
    "input.sprint": "Sprint button binding",
    "input.interact": "Interact button binding",
    "input.reload": "Reload button binding",
    "input.mouse_axis_x": "Name of the mouse X axis (defaults to Mouse X)",
    "input.mouse_axis_y": "Name of the mouse Y axis (defaults to Mouse Y)",
    "input.mouse_sensitivity": "Mouse look sensitivity multiplier",
    "input.invert_mouse_x": "Invert horizontal mouse look",
    "input.invert_mouse_y": "Invert vertical mouse look",
    "input.axis_gravity": "Axis return-to-zero speed when released",
    "input.axis_sensitivity": "Axis ramp-up speed while held",
    "input.axis_dead": "Axis dead zone threshold",
    "physics.gravity_x": "Global gravity X component",
    "physics.gravity_y": "Global gravity Y component",
    "physics.gravity_z": "Global gravity Z component",
    "physics.fixed_time_step": "Physics fixed timestep (seconds)",
    "physics.num_sub_steps": "Physics solver sub-steps per frame",
    "physics.solver_iterations": "Physics constraint solver iterations",
    "physics.erp": "Physics error reduction parameter",
    "physics.contact_erp": "Physics contact error reduction parameter",
    "physics.friction_erp": "Physics friction error reduction parameter",
    "physics.contact_breaking_threshold": "Contact breaking threshold",
    "physics.restitution": "Default restitution (bounciness)",
    "physics.linear_damping": "Default linear damping",
    "physics.angular_damping": "Default angular damping",
    "physics.max_contacts_per_body": "Maximum contacts per rigid body",
    "physics.simulation_mode": "How physics simulation is executed. single = main thread, multi_threaded = one separate process, per_layer_process = one process per collision layer (for extreme parallel workloads)",
    "physics.solver": "Physics engine backend (default: culverin = Jolt Physics)",
    "audio.enable_audio": "Enable the audio system on startup",
    "audio.device_name": "Audio output device name (leave empty for Windows system default)",
    "audio.sample_rate": "Audio sample rate in Hz (44100 or 48000 recommended)",
    "audio.master_volume": "Master audio volume",
    "audio.sfx_volume": "Sound effects volume",
    "audio.music_volume": "Music volume",
    "audio.voice_volume": "Voice / dialogue volume",
    "audio.ambient_volume": "Ambient / environment volume",
    "audio.max_sources": "Maximum number of simultaneous audio sources",
    "audio.stream_buffer_size": "Streaming buffer size in bytes",
    "audio.distance_model": "3D audio distance attenuation model",
    "audio.doppler_factor": "Doppler effect intensity factor",
    "audio.speed_of_sound": "Speed of sound in world units per second",
    "audio.priority_threshold": "Volume threshold below which sounds can be culled",
    "audio.enable_spatialization": "Enable 3D spatial audio positioning",
    "audio.enable_reverb": "Enable reverb / environmental audio effects",
    "audio.enable_occlusion": "Enable audio occlusion simulation",
    "rendering.render_pipeline": "Active render pipeline",
    "rendering.anti_aliasing": "Anti-aliasing mode",
    "toolbar.grid": "Show grid in viewport",
    "toolbar.snap": "Enable snapping",
    "toolbar.snap_translate": "Translate snap increment",
    "toolbar.snap_rotate": "Rotate snap increment (degrees)",
    "toolbar.snap_scale": "Scale snap increment",
    "toolbar.skybox": "Show skybox in viewport",
    "toolbar.effects": "Enable post-processing effects",
}

_FIELD_RANGES = {
    "editor.font_size": (8, 72),
    "editor.ui_scale": (50, 200),
    "editor.auto_save_interval": (10, 600),
    "editor.thumb_resolution": (64, 2048),
    "editor.hover_delay": (0, 2000),
    "camera.fov": (1, 179),
    "camera.near": (0.001, 10.0),
    "camera.far": (10.0, 50000.0),
    "camera.move_speed": (0.1, 100.0),
    "camera.fast_mult": (1.0, 20.0),
    "camera.rotate_speed": (0.01, 5.0),
    "camera.zoom_speed": (0.1, 50.0),
    "camera.pan_speed": (0.0001, 1.0),
    "camera.zoom_strength": (0.01, 5.0),
    "camera.damping": (0.1, 50.0),
    "camera.acceleration": (0.1, 50.0),
    "camera.transition_speed": (0.1, 20.0),
    "camera.zoom_smooth_speed": (0.1, 50.0),
    "camera.speed_boost_mult": (1.0, 20.0),
    "camera.speed_boost_ramp_time": (0.1, 10.0),
    "rendering.target_fps": (0, 10000),
    "rendering.show_grid": None,
    "rendering.grid_size": (0.1, 100.0),
    "rendering.grid_world_size": (10.0, 10000.0),
    "rendering.ambient": None,
    "rendering.light_scale": (0.0, 10.0),
    "rendering.selection_outline": None,
    "rendering.selection_outline_thickness": (0.0, 0.5),
    "rendering.tick_rate": (30.0, 1000.0),
    "rendering.fixed_tick_rate": (10.0, 500.0),
    "rendering.max_lights": (1, 64),
    "rendering.play_viewport_throttle_step": (2, 16),
    "gizmo.handle_size": (0.01, 2.0),
    "gizmo.base_axis_length": (0.1, 10.0),
    "gizmo.plane_handle_size": (0.02, 2.0),
    "gizmo.pick_threshold": (1.0, 100.0),
    "gizmo.arrow_size_ratio": (0.01, 1.0),
    "gizmo.center_handle_size": (0.01, 2.0),
    "gizmo.screen_axis_length": (10.0, 500.0),
    "gizmo.line_width": (0.5, 10.0),
    "gizmo.smooth_snap_speed": (0.01, 2.0),
    "gizmo.selection_bounds_speed": (0.1, 50.0),
    "gizmo.selection_bounds_color": None,
    "gizmo.icon_scale": (0.5, 20.0),
    "viewport.clear": None,
    "viewport.no_scene": None,
    "viewport.update_interval": (1, 500),
    "viewport.grid_step": (0.1, 100.0),
    "console.font_size": (6, 72),
    "console.max_blocks": (100, 10000),
    "console.refresh_interval": (16, 2000),
    "terminal.font_size": (6, 72),
    "profiler.update_interval": (0.05, 5.0),
    "profiler.max_samples": (50, 5000),
    "profiler.refresh_interval": (16, 2000),
    "hierarchy.refresh_interval": (50, 5000),
    "inspector.refresh_interval": (16, 2000),
    "project.thumb_size": (16, 256),
    "engine.time_scale": (0.0, 10.0),
    "engine.fixed_update_dt": (0.001, 1.0),
    "collab.cursor_rate": (1.0, 120.0),
    "collab.camera_rate": (1.0, 120.0),
    "collab.transform_rate": (1.0, 120.0),
    "collab.gizmo_rate": (1.0, 120.0),
    "collab.ping_interval": (0.5, 60.0),
    "collab.poll_interval": (1, 120),
    "undo.max_stack": (10, 2000),
    "input.mouse_sensitivity": (0.01, 10.0),
    "input.axis_gravity": (0.01, 50.0),
    "input.axis_sensitivity": (0.01, 20.0),
    "input.axis_dead": (0.0, 1.0),
    "physics.gravity_x": (-100.0, 100.0),
    "physics.gravity_y": (-100.0, 100.0),
    "physics.gravity_z": (-100.0, 100.0),
    "physics.fixed_time_step": (0.001, 1.0),
    "physics.num_sub_steps": (1, 16),
    "physics.solver_iterations": (1, 50),
    "physics.erp": (0.0, 1.0),
    "physics.contact_erp": (0.0, 1.0),
    "physics.friction_erp": (0.0, 1.0),
    "physics.contact_breaking_threshold": (0.0, 1.0),
    "physics.restitution": (0.0, 1.0),
    "physics.linear_damping": (0.0, 10.0),
    "physics.angular_damping": (0.0, 10.0),
    "physics.max_contacts_per_body": (1, 256),
    "audio.enable_audio": None,
    "audio.sample_rate": (8000, 192000),
    "audio.master_volume": (0.0, 1.0),
    "audio.sfx_volume": (0.0, 1.0),
    "audio.music_volume": (0.0, 1.0),
    "audio.voice_volume": (0.0, 1.0),
    "audio.ambient_volume": (0.0, 1.0),
    "audio.max_sources": (8, 256),
    "audio.stream_buffer_size": (1024, 65536),
    "audio.distance_model": None,
    "audio.doppler_factor": (0.0, 10.0),
    "audio.speed_of_sound": (0.1, 10000.0),
    "audio.priority_threshold": (0.0, 1.0),
    "audio.enable_spatialization": None,
    "audio.enable_reverb": None,
    "audio.enable_occlusion": None,
    "toolbar.snap_translate": (0.001, 100.0),
    "toolbar.snap_rotate": (0.1, 360.0),
    "toolbar.snap_scale": (0.001, 100.0),
    "mesh_preview.camera_rot_x": (-180.0, 180.0),
    "mesh_preview.camera_rot_y": (-180.0, 180.0),
    "mesh_preview.bg": None,
    "mesh_preview.tri": None,
    "mesh_preview.wire": None,
    "mesh_preview.wire_width": (0.5, 5.0),
}


class SliderSpinBox(QWidget):
    valueChanged = Signal(object)
    def __init__(self, key: str, value, is_float: bool, slider_range, parent=None):
        super().__init__(parent)
        self._key = key
        self._is_float = is_float
        self._updating = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimumWidth(120)
        if slider_range:
            lo, hi = slider_range
            if is_float:
                self._slider.setRange(int(lo * 1000), int(hi * 1000))
            else:
                self._slider.setRange(lo, hi)
        else:
            if is_float:
                self._slider.setRange(-999999000, 999999000)
            else:
                self._slider.setRange(-999999, 999999)
        if is_float:
            self._spin = QDoubleSpinBox()
            self._spin.setDecimals(4)
            self._spin.setRange(-999999.0, 999999.0)
            self._spin.setValue(float(value))
        else:
            self._spin = QSpinBox()
            self._spin.setRange(-999999, 999999)
            self._spin.setValue(int(value))
        self._spin.setFixedWidth(scale(100))
        if slider_range:
            lo, hi = slider_range
            if is_float:
                self._slider.setValue(int(float(value) * 1000))
            else:
                self._slider.setValue(int(value))
        else:
            if is_float:
                self._slider.setValue(int(float(value) * 1000))
            else:
                self._slider.setValue(int(value))
        self._slider.valueChanged.connect(self._on_slider)
        self._spin.valueChanged.connect(self._on_spin)
        layout.addWidget(self._slider)
        layout.addWidget(self._spin)
    def _on_slider(self, val: int):
        if self._updating:
            return
        self._updating = True
        if self._is_float:
            v = val / 1000.0
            self._spin.setValue(v)
        else:
            self._spin.setValue(val)
        self._updating = False
        self.valueChanged.emit(self._spin.value())
    def _on_spin(self, val):
        if self._updating:
            return
        self._updating = True
        if self._is_float:
            self._slider.setValue(int(val * 1000))
        else:
            self._slider.setValue(int(val))
        self._updating = False
        self.valueChanged.emit(val)
    def setValue(self, value):
        if self._updating:
            return
        self._updating = True
        if self._is_float:
            v = float(value)
            self._spin.setValue(v)
            self._slider.setValue(int(v * 1000))
        else:
            v = int(value)
            self._spin.setValue(v)
            self._slider.setValue(v)
        self._updating = False
        self.valueChanged.emit(self._spin.value())
