# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

ENGINE_HOST = "127.0.0.1"
ENGINE_PORT = 9271

OP_PING = "ping"
OP_LOAD_SCENE = "load_scene"
OP_SAVE_SCENE = "save_scene"
OP_NEW_SCENE = "new_scene"
OP_PUSH_SCENE = "push_scene"
OP_PULL_SCENE = "pull_scene"
OP_START_PLAY = "start_play"
OP_STOP_PLAY = "stop_play"
OP_SET_TIME_SCALE = "set_time_scale"
OP_SET_FIXED_DT = "set_fixed_dt"
OP_SET_PROJECT_ROOT = "set_project_root"
OP_SHUTDOWN = "shutdown"
OP_SYNC_IDS = "sync_ids"

EV_SCENE_LOADED = "scene_loaded"
EV_SCENE_SAVED = "scene_saved"
EV_PLAY_START = "play_start"
EV_PLAY_STOP = "play_stop"
