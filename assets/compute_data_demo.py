import numpy as np
from core.compute_shader import ComputeShader
from core.logger import Logger


class ComputeDataDemo:
    compute_shader_path: str = "assets/shaders/DataFill.compute"
    data_size: int = 65536
    multiplier: float = 5.0
    offset: float = 10.0

    def __init__(self):
        self._entity = None
        self._cs = None
        self._ctx = None
        self._frame = 0

    def _get_ctx(self):
        if self._ctx:
            return self._ctx
        try:
            from core.engine import Engine
            eng = Engine.instance()
            if not eng:
                return None
            vp = getattr(eng, '_viewport', None)
            if vp:
                self._ctx = vp._ctx
                return self._ctx
            pw = getattr(eng, '_play_window', None)
            if pw:
                self._ctx = pw._ctx
                return self._ctx
        except Exception as e:
            Logger.error(f"ComputeDataDemo: контекст не достать: {e}")
        return None

    def on_start(self):
        ctx = self._get_ctx()
        if not ctx:
            Logger.error("ComputeDataDemo: нет контекста")
            return

        cs = ComputeShader.load_from_file(ctx, self.compute_shader_path)
        if not cs:
            Logger.error(f"ComputeDataDemo: {self.compute_shader_path} не загрузился")
            return
        self._cs = cs

        n = self.data_size
        input_data = np.random.rand(n).astype(np.float32)
        output_data = np.zeros(n, dtype=np.float32)

        self._cs.set_buffer("InputBuffer", 0, input_data)
        self._cs.set_buffer("OutputBuffer", 1, output_data)
        self._cs.set_uniform("u_multiplier", self.multiplier)
        self._cs.set_uniform("u_offset", self.offset)

        Logger.info(f"ComputeDataDemo: {n} элементов, поехали")

    def on_update(self, dt: float):
        if not self._cs:
            return
        self._frame += 1
        self._cs.set_uniform("u_time", self._frame * 0.016)
        self._cs.dispatch(self.data_size)

        if self._frame % 30 == 0:
            buf = self._cs.get_buffer("OutputBuffer")
            if buf:
                data = buf.read()
                mn = float(np.min(data))
                mx = float(np.max(data))
                mean = float(np.mean(data))
                Logger.info(f"[COMPUTE] min={mn:.3f} max={mx:.3f} mean={mean:.3f}")

    def on_destroy(self):
        if self._cs:
            self._cs.release()
            self._cs = None
