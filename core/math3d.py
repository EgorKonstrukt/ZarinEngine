from __future__ import annotations
import math
import numpy as np
from typing import Union
FLOAT_TYPE = np.float64
class Vec2:
    __slots__ = ("_d",)
    def __init__(self, x: float = 0.0, y: float = 0.0):
        self._d = np.array([x, y], dtype=FLOAT_TYPE)
    @classmethod
    def from_array(cls, a: np.ndarray) -> Vec2:
        v = cls.__new__(cls)
        v._d = np.array(a[:2], dtype=FLOAT_TYPE)
        return v
    @property
    def x(self) -> float: return float(self._d[0])
    @x.setter
    def x(self, v: float): self._d[0] = v
    @property
    def y(self) -> float: return float(self._d[1])
    @y.setter
    def y(self, v: float): self._d[1] = v
    def __add__(self, o: Vec2) -> Vec2: return Vec2.from_array(self._d + o._d)
    def __sub__(self, o: Vec2) -> Vec2: return Vec2.from_array(self._d - o._d)
    def __mul__(self, s: float) -> Vec2: return Vec2.from_array(self._d * s)
    def __rmul__(self, s: float) -> Vec2: return self.__mul__(s)
    def __truediv__(self, s: float) -> Vec2: return Vec2.from_array(self._d / s)
    def __neg__(self) -> Vec2: return Vec2.from_array(-self._d)
    def __repr__(self) -> str: return f"Vec2({self.x:.4f}, {self.y:.4f})"
    def dot(self, o: Vec2) -> float: return float(np.dot(self._d, o._d))
    def length(self) -> float: return float(np.linalg.norm(self._d))
    def normalized(self) -> Vec2:
        l = self.length()
        return Vec2.from_array(self._d / l) if l > 1e-10 else Vec2()
    def to_list(self) -> list: return self._d.tolist()
    @staticmethod
    def zero() -> Vec2: return Vec2(0, 0)
    @staticmethod
    def one() -> Vec2: return Vec2(1, 1)
class Vec3:
    __slots__ = ("_d",)
    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0):
        self._d = np.array([x, y, z], dtype=FLOAT_TYPE)
    @classmethod
    def from_array(cls, a: np.ndarray) -> Vec3:
        v = cls.__new__(cls)
        v._d = np.array(a[:3], dtype=FLOAT_TYPE)
        return v
    @property
    def x(self) -> float: return float(self._d[0])
    @x.setter
    def x(self, v: float): self._d[0] = v
    @property
    def y(self) -> float: return float(self._d[1])
    @y.setter
    def y(self, v: float): self._d[1] = v
    @property
    def z(self) -> float: return float(self._d[2])
    @z.setter
    def z(self, v: float): self._d[2] = v
    def __add__(self, o: Vec3) -> Vec3: return Vec3.from_array(self._d + o._d)
    def __sub__(self, o: Vec3) -> Vec3: return Vec3.from_array(self._d - o._d)
    def __mul__(self, s: float) -> Vec3: return Vec3.from_array(self._d * s)
    def __rmul__(self, s: float) -> Vec3: return self.__mul__(s)
    def __truediv__(self, s: float) -> Vec3: return Vec3.from_array(self._d / s)
    def __neg__(self) -> Vec3: return Vec3.from_array(-self._d)
    def __repr__(self) -> str: return f"Vec3({self.x:.4f}, {self.y:.4f}, {self.z:.4f})"
    def __eq__(self, o: object) -> bool:
        return isinstance(o, Vec3) and np.allclose(self._d, o._d)
    def dot(self, o: Vec3) -> float: return float(np.dot(self._d, o._d))
    def cross(self, o: Vec3) -> Vec3: return Vec3.from_array(np.cross(self._d, o._d))
    def length(self) -> float: return float(np.linalg.norm(self._d))
    def length_sq(self) -> float: return float(np.dot(self._d, self._d))
    def normalized(self) -> Vec3:
        l = self.length()
        return Vec3.from_array(self._d / l) if l > 1e-10 else Vec3()
    def lerp(self, o: Vec3, t: float) -> Vec3:
        return Vec3.from_array(self._d + (o._d - self._d) * t)
    def to_array(self) -> np.ndarray: return self._d.copy()
    def to_list(self) -> list: return self._d.tolist()
    @staticmethod
    def zero() -> Vec3: return Vec3(0, 0, 0)
    @staticmethod
    def one() -> Vec3: return Vec3(1, 1, 1)
    @staticmethod
    def up() -> Vec3: return Vec3(0, 1, 0)
    @staticmethod
    def forward() -> Vec3: return Vec3(0, 0, -1)
    @staticmethod
    def right() -> Vec3: return Vec3(1, 0, 0)
class Vec4:
    __slots__ = ("_d",)
    def __init__(self, x=0.0, y=0.0, z=0.0, w=1.0):
        self._d = np.array([x, y, z, w], dtype=FLOAT_TYPE)
    @classmethod
    def from_array(cls, a: np.ndarray) -> Vec4:
        v = cls.__new__(cls)
        v._d = np.array(a[:4], dtype=FLOAT_TYPE)
        return v
    @property
    def x(self) -> float: return float(self._d[0])
    @property
    def y(self) -> float: return float(self._d[1])
    @property
    def z(self) -> float: return float(self._d[2])
    @property
    def w(self) -> float: return float(self._d[3])
    def to_list(self) -> list: return self._d.tolist()
class Quat:
    __slots__ = ("_d",)
    def __init__(self, x=0.0, y=0.0, z=0.0, w=1.0):
        self._d = np.array([x, y, z, w], dtype=FLOAT_TYPE)
    @classmethod
    def from_array(cls, a: np.ndarray) -> Quat:
        q = cls.__new__(cls)
        q._d = np.array(a[:4], dtype=FLOAT_TYPE)
        return q
    @classmethod
    def identity(cls) -> Quat: return cls(0, 0, 0, 1)
    @classmethod
    def from_euler(cls, x: float, y: float, z: float) -> Quat:
        hx, hy, hz = math.radians(x)*0.5, math.radians(y)*0.5, math.radians(z)*0.5
        sx, cx = math.sin(hx), math.cos(hx)
        sy, cy = math.sin(hy), math.cos(hy)
        sz, cz = math.sin(hz), math.cos(hz)
        return cls(
            sx*cy*cz - cx*sy*sz,
            cx*sy*cz + sx*cy*sz,
            cx*cy*sz - sx*sy*cz,
            cx*cy*cz + sx*sy*sz
        )
    @classmethod
    def from_axis_angle(cls, axis: Vec3, angle_deg: float) -> Quat:
        a = math.radians(angle_deg) * 0.5
        ax = axis.normalized()
        s = math.sin(a)
        return cls(ax.x*s, ax.y*s, ax.z*s, math.cos(a))
    @classmethod
    def look_rotation(cls, forward: Vec3, up: Vec3 = None) -> Quat:
        if up is None: up = Vec3.up()
        f = forward.normalized()
        r = up.cross(f).normalized()
        u = f.cross(r)
        m = np.eye(3, dtype=FLOAT_TYPE)
        m[0] = r.to_array()
        m[1] = u.to_array()
        m[2] = f.to_array()
        return cls._from_rotation_matrix3(m)
    @classmethod
    def _from_rotation_matrix3(cls, m: np.ndarray) -> Quat:
        t = m[0,0] + m[1,1] + m[2,2]
        if t > 0:
            s = 0.5 / math.sqrt(t + 1.0)
            return cls((m[2,1]-m[1,2])*s, (m[0,2]-m[2,0])*s, (m[1,0]-m[0,1])*s, 0.25/s)
        elif m[0,0] > m[1,1] and m[0,0] > m[2,2]:
            s = 2.0*math.sqrt(1.0+m[0,0]-m[1,1]-m[2,2])
            return cls(0.25*s, (m[0,1]+m[1,0])/s, (m[0,2]+m[2,0])/s, (m[2,1]-m[1,2])/s)
        elif m[1,1] > m[2,2]:
            s = 2.0*math.sqrt(1.0+m[1,1]-m[0,0]-m[2,2])
            return cls((m[0,1]+m[1,0])/s, 0.25*s, (m[1,2]+m[2,1])/s, (m[0,2]-m[2,0])/s)
        else:
            s = 2.0*math.sqrt(1.0+m[2,2]-m[0,0]-m[1,1])
            return cls((m[0,2]+m[2,0])/s, (m[1,2]+m[2,1])/s, 0.25*s, (m[1,0]-m[0,1])/s)
    @property
    def x(self) -> float: return float(self._d[0])
    @property
    def y(self) -> float: return float(self._d[1])
    @property
    def z(self) -> float: return float(self._d[2])
    @property
    def w(self) -> float: return float(self._d[3])
    def __mul__(self, o: Quat) -> Quat:
        ax,ay,az,aw = self._d
        bx,by,bz,bw = o._d
        return Quat(
            aw*bx+ax*bw+ay*bz-az*by,
            aw*by-ax*bz+ay*bw+az*bx,
            aw*bz+ax*by-ay*bx+az*bw,
            aw*bw-ax*bx-ay*by-az*bz
        )
    def conjugate(self) -> Quat: return Quat(-self.x, -self.y, -self.z, self.w)
    def normalized(self) -> Quat:
        n = np.linalg.norm(self._d)
        return Quat.from_array(self._d/n) if n > 1e-10 else Quat.identity()
    def rotate_vec3(self, v: Vec3) -> Vec3:
        q = self.normalized()
        vq = Quat(v.x, v.y, v.z, 0)
        res = (q * vq) * q.conjugate()
        return Vec3(res.x, res.y, res.z)
    def to_euler(self) -> Vec3:
        x,y,z,w = self._d
        sinx_cosp = 2*(w*x + y*z)
        cosx_cosp = 1 - 2*(x*x + y*y)
        rx = math.degrees(math.atan2(sinx_cosp, cosx_cosp))
        siny_cosp = 2*(w*y - z*x)
        sy = max(-1.0, min(1.0, siny_cosp))
        ry = math.degrees(math.asin(sy))
        sinz_cosp = 2*(w*z + x*y)
        cosz_cosp = 1 - 2*(y*y + z*z)
        rz = math.degrees(math.atan2(sinz_cosp, cosz_cosp))
        return Vec3(rx, ry, rz)
    def to_matrix4(self) -> Mat4:
        n = self.normalized()
        x,y,z,w = n._d
        m = np.eye(4, dtype=FLOAT_TYPE)
        m[0,0]=1-2*y*y-2*z*z; m[0,1]=2*x*y+2*w*z; m[0,2]=2*x*z-2*w*y
        m[1,0]=2*x*y-2*w*z;   m[1,1]=1-2*x*x-2*z*z; m[1,2]=2*y*z+2*w*x
        m[2,0]=2*x*z+2*w*y;   m[2,1]=2*y*z-2*w*x;   m[2,2]=1-2*x*x-2*y*y
        return Mat4(m)
    def slerp(self, o: Quat, t: float) -> Quat:
        dot = float(np.dot(self._d, o._d))
        if dot < 0:
            od = -o._d
            dot = -dot
        else:
            od = o._d
        if dot > 0.9995:
            return Quat.from_array(self._d + t*(od - self._d)).normalized()
        theta0 = math.acos(dot)
        theta = theta0 * t
        s0 = math.cos(theta) - dot*math.sin(theta)/math.sin(theta0)
        s1 = math.sin(theta)/math.sin(theta0)
        return Quat.from_array(s0*self._d + s1*od).normalized()
    def to_list(self) -> list: return self._d.tolist()
class Mat4:
    __slots__ = ("_d",)
    def __init__(self, data: np.ndarray = None):
        if data is not None:
            self._d = np.array(data, dtype=FLOAT_TYPE)
        else:
            self._d = np.eye(4, dtype=FLOAT_TYPE)
    @staticmethod
    def identity() -> Mat4: return Mat4()
    @staticmethod
    def translation(v: Vec3) -> Mat4:
        m = Mat4()
        m._d[3,0] = v.x; m._d[3,1] = v.y; m._d[3,2] = v.z
        return m
    @staticmethod
    def scale(v: Vec3) -> Mat4:
        m = Mat4()
        m._d[0,0] = v.x; m._d[1,1] = v.y; m._d[2,2] = v.z
        return m
    @staticmethod
    def perspective(fov_deg: float, aspect: float, near: float, far: float) -> Mat4:
        f = 1.0 / math.tan(math.radians(fov_deg) * 0.5)
        m = np.zeros((4,4), dtype=FLOAT_TYPE)
        m[0,0] = f / aspect
        m[1,1] = f
        m[2,2] = (far+near)/(near-far)
        m[2,3] = -1.0
        m[3,2] = (2*far*near)/(near-far)
        return Mat4(m)
    @staticmethod
    def orthographic(left: float, right: float, bottom: float, top: float, near: float, far: float) -> Mat4:
        m = np.zeros((4,4), dtype=FLOAT_TYPE)
        m[0,0] = 2/(right-left); m[3,0] = -(right+left)/(right-left)
        m[1,1] = 2/(top-bottom); m[3,1] = -(top+bottom)/(top-bottom)
        m[2,2] = -2/(far-near);  m[3,2] = -(far+near)/(far-near)
        m[3,3] = 1
        return Mat4(m)
    @staticmethod
    def look_at(eye: Vec3, center: Vec3, up: Vec3) -> Mat4:
        f = (center - eye).normalized()
        r = f.cross(up).normalized()
        u = r.cross(f)
        m = np.eye(4, dtype=FLOAT_TYPE)
        m[0,0]=r.x; m[1,0]=r.y; m[2,0]=r.z
        m[0,1]=u.x; m[1,1]=u.y; m[2,1]=u.z
        m[0,2]=-f.x; m[1,2]=-f.y; m[2,2]=-f.z
        m[3,0]=-r.dot(eye); m[3,1]=-u.dot(eye); m[3,2]=f.dot(eye)
        return Mat4(m)
    def __mul__(self, o: Mat4) -> Mat4: return Mat4(self._d @ o._d)
    def __matmul__(self, o: Mat4) -> Mat4: return self.__mul__(o)
    def transposed(self) -> Mat4: return Mat4(self._d.T)
    def inverted(self) -> Mat4: return Mat4(np.linalg.inv(self._d))
    def to_array(self) -> np.ndarray: return self._d.copy()
    def to_f32(self) -> np.ndarray:
        return self._d.T.astype(np.float32).flatten(order='F')
    def to_list(self) -> list: return self._d.tolist()
    def get_translation(self) -> Vec3: return Vec3(self._d[3,0], self._d[3,1], self._d[3,2])
    def decompose(self) -> tuple[Vec3, Quat, Vec3]:
        pos = Vec3(self._d[3,0], self._d[3,1], self._d[3,2])
        sx = float(np.linalg.norm(self._d[:3,0]))
        sy = float(np.linalg.norm(self._d[:3,1]))
        sz = float(np.linalg.norm(self._d[:3,2]))
        scale = Vec3(sx, sy, sz)
        rm = np.array(self._d[:3,:3], dtype=FLOAT_TYPE)
        if sx > 1e-10: rm[:,0] /= sx
        if sy > 1e-10: rm[:,1] /= sy
        if sz > 1e-10: rm[:,2] /= sz
        rot = Quat._from_rotation_matrix3(rm.T)
        return pos, rot, scale