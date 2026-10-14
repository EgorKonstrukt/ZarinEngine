# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os

from PyQt6.QtCore import Qt, QThread, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget

from core.foundation.plugins import _zarin_user_dir
from ...rend import TrackerSoftwareRenderer, load_module
from ..instrument_list import InstrumentListWidget
from ..mixer_widget import MixerWidget
from ..module_info import ModuleInfoWidget
from ..pattern import PatternEditorWidget
from ..sample_manager import SampleManagerWidget
from .pattern import TrackerPatternMixin
from .preview import TrackerPreviewMixin, _PreviewJob

class TrackerEditorWidget(QWidget, TrackerPatternMixin, TrackerPreviewMixin):
    SAMPLE_RATES = (22050, 44100, 48000)

    def __init__(self, engine, plugin):
        super().__init__()
        self._engine = engine
        self._plugin = plugin
        self._song = None
        self._song_path = ""
        self._pattern_seq_index = 0
        self._edit_rev = 0
        self._source_id = 0
        self._playing = False
        self._play_start = 0.0
        self._paused_elapsed = 0.0
        self._thread: QThread | None = None
        self._worker: _PreviewJob | None = None
        self._job_id = 0
        self._job_kind = "preview"
        self._job_dest = ""
        self._pending_autoplay = False
        self._preview_wav = ""
        self._preview_duration = 0.0
        self._meter_block_sec = TrackerSoftwareRenderer.METER_BLOCK_SEC
        self._meter_peaks: list = []
        self._playback_map: list = []
        self._playback_ends: list = []
        self._timeline: list = []
        self._timeline_ends: list = []
        self._build_ui()
        self._rerender_timer = QTimer(self)
        self._rerender_timer.setSingleShot(True)
        self._rerender_timer.setInterval(400)
        self._rerender_timer.timeout.connect(self._on_rerender_timeout)
        self._ticker = QTimer(self)
        self._ticker.timeout.connect(self._on_tick)
        self._ticker.start(50)
        self._pattern_editor.patternChanged.connect(self._on_pattern_edited)
        self._module_info.metadataEdited.connect(self._on_metadata_edited)
        self._save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        self._save_shortcut.activated.connect(self._save_module)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)

        top = QHBoxLayout()
        self._open_btn = QPushButton("Open Module...")
        self._open_btn.clicked.connect(self._open_module)
        top.addWidget(self._open_btn)

        self._save_btn = QPushButton("Save")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save_module)
        top.addWidget(self._save_btn)

        self._seq_combo = QComboBox()
        self._seq_combo.setMinimumWidth(160)
        self._seq_combo.currentIndexChanged.connect(self._on_seq_changed)
        top.addWidget(self._seq_combo)

        self._seq_ins_btn = QPushButton("Ins")
        self._seq_ins_btn.setToolTip("Insert a copy of the current pattern before this position")
        self._seq_ins_btn.setEnabled(False)
        self._seq_ins_btn.clicked.connect(self._seq_insert)
        top.addWidget(self._seq_ins_btn)

        self._seq_add_btn = QPushButton("Add")
        self._seq_add_btn.setToolTip("Append a copy of the current pattern to the sequence")
        self._seq_add_btn.setEnabled(False)
        self._seq_add_btn.clicked.connect(self._seq_add)
        top.addWidget(self._seq_add_btn)

        self._seq_del_btn = QPushButton("Del")
        self._seq_del_btn.setToolTip("Remove this sequence position")
        self._seq_del_btn.setEnabled(False)
        self._seq_del_btn.clicked.connect(self._seq_remove)
        top.addWidget(self._seq_del_btn)

        self._seq_up_btn = QPushButton("Up")
        self._seq_up_btn.setToolTip("Move this position earlier")
        self._seq_up_btn.setEnabled(False)
        self._seq_up_btn.clicked.connect(lambda: self._seq_move(-1))
        top.addWidget(self._seq_up_btn)

        self._seq_down_btn = QPushButton("Down")
        self._seq_down_btn.setToolTip("Move this position later")
        self._seq_down_btn.setEnabled(False)
        self._seq_down_btn.clicked.connect(lambda: self._seq_move(1))
        top.addWidget(self._seq_down_btn)

        self._play_btn = QPushButton("Play")
        self._play_btn.clicked.connect(self._toggle_play)
        top.addWidget(self._play_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.clicked.connect(self._stop)
        top.addWidget(self._stop_btn)

        self._export_btn = QPushButton("Export WAV...")
        self._export_btn.clicked.connect(self._export_wav)
        top.addWidget(self._export_btn)

        self._export_mod_btn = QPushButton("Export Module...")
        self._export_mod_btn.clicked.connect(self._export_module)
        top.addWidget(self._export_mod_btn)

        self._time_lbl = QLabel("0:00.00")
        top.addWidget(self._time_lbl)
        top.addStretch()

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setMaximumWidth(160)
        self._progress.setVisible(False)
        top.addWidget(self._progress)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setVisible(False)
        self._cancel_btn.clicked.connect(self._cancel_job)
        top.addWidget(self._cancel_btn)
        root.addLayout(top)

        self._pattern_editor = PatternEditorWidget()
        self._pattern_editor.setEnabled(False)

        edit_bar = QHBoxLayout()
        self._edit_undo_btn = QPushButton("Undo")
        self._edit_undo_btn.setEnabled(False)
        self._edit_undo_btn.clicked.connect(self._pattern_editor.undo)
        edit_bar.addWidget(self._edit_undo_btn)
        self._edit_redo_btn = QPushButton("Redo")
        self._edit_redo_btn.setEnabled(False)
        self._edit_redo_btn.clicked.connect(self._pattern_editor.redo)
        edit_bar.addWidget(self._edit_redo_btn)
        edit_bar.addSpacing(8)
        self._edit_ins_btn = QPushButton("Insert Row")
        self._edit_ins_btn.setEnabled(False)
        self._edit_ins_btn.clicked.connect(self._pattern_editor.insert_row)
        edit_bar.addWidget(self._edit_ins_btn)
        self._edit_del_btn = QPushButton("Delete Row")
        self._edit_del_btn.setEnabled(False)
        self._edit_del_btn.clicked.connect(self._pattern_editor.delete_row)
        edit_bar.addWidget(self._edit_del_btn)
        self._edit_clear_btn = QPushButton("Clear Row")
        self._edit_clear_btn.setEnabled(False)
        self._edit_clear_btn.clicked.connect(self._pattern_editor.clear_row)
        edit_bar.addWidget(self._edit_clear_btn)
        edit_bar.addSpacing(8)
        self._edit_down_btn = QPushButton("T -")
        self._edit_down_btn.setToolTip("Transpose selection down")
        self._edit_down_btn.setEnabled(False)
        self._edit_down_btn.clicked.connect(lambda: self._pattern_editor.transpose_rows(-1))
        edit_bar.addWidget(self._edit_down_btn)
        self._edit_up_btn = QPushButton("T +")
        self._edit_up_btn.setToolTip("Transpose selection up")
        self._edit_up_btn.setEnabled(False)
        self._edit_up_btn.clicked.connect(lambda: self._pattern_editor.transpose_rows(1))
        edit_bar.addWidget(self._edit_up_btn)
        edit_bar.addSpacing(8)
        self._edit_copy_btn = QPushButton("Copy")
        self._edit_copy_btn.setEnabled(False)
        self._edit_copy_btn.clicked.connect(self._pattern_editor.copy_row)
        edit_bar.addWidget(self._edit_copy_btn)
        self._edit_cut_btn = QPushButton("Cut")
        self._edit_cut_btn.setEnabled(False)
        self._edit_cut_btn.clicked.connect(self._pattern_editor.cut_row)
        edit_bar.addWidget(self._edit_cut_btn)
        self._edit_paste_btn = QPushButton("Paste")
        self._edit_paste_btn.setEnabled(False)
        self._edit_paste_btn.clicked.connect(self._pattern_editor.paste_row)
        edit_bar.addWidget(self._edit_paste_btn)
        edit_bar.addStretch()
        root.addLayout(edit_bar)

        self._module_lbl = QLabel("No module loaded")
        root.addWidget(self._module_lbl)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._pattern_editor)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)

        mixer_group = QGroupBox("Mixer")
        mixer_layout = QVBoxLayout(mixer_group)
        mixer_layout.setContentsMargins(4, 4, 4, 4)
        self._mixer = MixerWidget()
        self._mixer.muteChanged.connect(self._on_mute_changed)
        self._mixer.gainChanged.connect(self._on_gain_changed)
        self._mixer.masterChanged.connect(self._on_master_changed)
        self._mixer.soloChanged.connect(self._on_solo_changed)
        mixer_layout.addWidget(self._mixer)
        mixer_group.setMaximumHeight(300)
        side_layout.addWidget(mixer_group)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)

        inst_group = QGroupBox("Instruments")
        inst_layout = QVBoxLayout(inst_group)
        self._instruments = InstrumentListWidget()
        inst_layout.addWidget(self._instruments)
        scroll_layout.addWidget(inst_group)

        sample_group = QGroupBox("Samples")
        sample_layout = QVBoxLayout(sample_group)
        self._sample_manager = SampleManagerWidget()
        self._sample_manager.samplesChanged.connect(self._on_samples_changed)
        sample_layout.addWidget(self._sample_manager)
        scroll_layout.addWidget(sample_group)

        info_group = QGroupBox("Module Info")
        info_layout = QVBoxLayout(info_group)
        self._module_info = ModuleInfoWidget()
        info_layout.addWidget(self._module_info)
        scroll_layout.addWidget(info_group)

        settings_group = QGroupBox("Music Settings")
        settings_layout = QVBoxLayout(settings_group)
        rate_row = QHBoxLayout()
        rate_row.addWidget(QLabel("Sample rate:"))
        self._rate_combo = QComboBox()
        self._rate_combo.addItems([str(r) for r in self.SAMPLE_RATES])
        self._rate_combo.currentTextChanged.connect(self._on_settings_changed)
        rate_row.addWidget(self._rate_combo, 1)
        settings_layout.addLayout(rate_row)
        qual_row = QHBoxLayout()
        qual_row.addWidget(QLabel("Quality:"))
        self._quality_combo = QComboBox()
        self._quality_combo.addItems(["software", "external"])
        self._quality_combo.currentTextChanged.connect(self._on_settings_changed)
        qual_row.addWidget(self._quality_combo, 1)
        settings_layout.addLayout(qual_row)
        self._clear_cache_btn = QPushButton("Clear Preview Cache")
        self._clear_cache_btn.clicked.connect(self._clear_cache)
        settings_layout.addWidget(self._clear_cache_btn)
        scroll_layout.addWidget(settings_group)
        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        side_layout.addWidget(scroll, 1)

        splitter.addWidget(side)
        splitter.setStretchFactor(0, 3)
        splitter.setSizes([700, 260])
        root.addWidget(splitter, 1)
        self._load_settings_into_ui()

    def _load_settings_into_ui(self):
        try:
            rate = int(self._plugin.get_config("tracker_sample_rate", 44100))
        except Exception:
            rate = 44100
        if rate not in self.SAMPLE_RATES:
            rate = 44100
        self._rate_combo.blockSignals(True)
        self._rate_combo.setCurrentText(str(rate))
        self._rate_combo.blockSignals(False)
        quality = str(self._plugin.get_config("tracker_quality", "software"))
        if quality not in ("software", "external"):
            quality = "software"
        self._quality_combo.blockSignals(True)
        self._quality_combo.setCurrentText(quality)
        self._quality_combo.blockSignals(False)
        try:
            master_db = float(self._plugin.get_config("tracker_master_db", 0.0))
        except Exception:
            master_db = 0.0
        self._mixer.set_master_db(master_db)

    def _sample_rate(self) -> int:
        try:
            rate = int(self._plugin.get_config("tracker_sample_rate", 44100))
        except Exception:
            rate = 44100
        return rate if rate in self.SAMPLE_RATES else 44100

    def _quality(self) -> str:
        quality = str(self._plugin.get_config("tracker_quality", "software"))
        return quality if quality in ("software", "external") else "software"

    def _master_gain(self) -> float:
        try:
            return TrackerSoftwareRenderer.db_to_gain(self._mixer.master_db())
        except Exception:
            return 1.0

    def _cache_dir(self) -> str:
        return _zarin_user_dir("tracker_cache")

    def _open_module(self):
        last_dir = self._plugin.get_config("last_tracker_dir", "")
        start = last_dir if last_dir and os.path.isdir(last_dir) else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Module", start,
            "Tracker modules (*.mod *.xm *.s3m *.it);;All files (*)",
        )
        if not path:
            return
        self._plugin.set_config("last_tracker_dir", os.path.dirname(path))
        self._load_module(path)

    def _load_module(self, path: str):
        song = load_module(path)
        if song is None:
            QMessageBox.warning(self, "Tracker", f"Failed to load module:\n{path}")
            return
        self._stop()
        self._song_path = path
        self._song = song
        self._paused_elapsed = 0.0
        self._preview_wav = ""
        self._preview_duration = 0.0
        self._meter_peaks = []
        self._playback_map = []
        self._playback_ends = []
        self._timeline = []
        self._timeline_ends = []
        self._pattern_seq_index = 0
        self._refresh_sequence_ui(0)
        self._refresh_pattern()
        self._instruments.load_song(song)
        self._module_info.load_song(song)
        self._sample_manager.load_song(song)
        try:
            self._mixer.set_channels(int(song.n_channels))
        except Exception:
            self._mixer.set_channels(0)
        try:
            saved_master = float(self._plugin.get_config("tracker_master_db", 0.0))
        except Exception:
            saved_master = 0.0
        self._mixer.set_master_db(saved_master)
        try:
            info = song.get_song_info() or {}
            self._preview_duration = float(info.get("duration_seconds") or 0.0)
        except Exception:
            pass
        title = getattr(song, "songname", "") or ""
        self._module_lbl.setText(f"{os.path.basename(path)}   -   {title}")
        self._pattern_editor.setEnabled(True)
        self._save_btn.setEnabled(True)
        self._seq_ins_btn.setEnabled(True)
        self._seq_add_btn.setEnabled(True)
        self._seq_del_btn.setEnabled(True)
        self._seq_up_btn.setEnabled(True)
        self._seq_down_btn.setEnabled(True)
        self._update_edit_state()
        self._start_render(autoplay=False)

    def _on_mute_changed(self, ch: int, muted: bool):
        self._schedule_rerender()

    def _on_solo_changed(self):
        self._schedule_rerender()

    def _on_gain_changed(self, ch: int, db: float):
        self._schedule_rerender()

    def _on_master_changed(self, db: float):
        try:
            self._plugin.set_config("tracker_master_db", float(db))
        except Exception:
            pass
        if self._playing and self._source_id:
            mgr = TrackerEditorWidget._audio_mgr()
            if mgr:
                try:
                    mgr.update_source(self._source_id, self._master_gain(), 1.0, (0.0, 0.0, 0.0))
                except Exception:
                    pass

    def _on_settings_changed(self, _text: str = ""):
        try:
            self._plugin.set_config("tracker_sample_rate", int(self._rate_combo.currentText()))
            self._plugin.set_config("tracker_quality", str(self._quality_combo.currentText()))
        except Exception:
            pass
        if self._song is not None:
            self._schedule_rerender()
