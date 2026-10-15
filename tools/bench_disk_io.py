# Bench: raw disk ceiling vs asset loader throughput.
import os, sys, time, tempfile, threading
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = os.path.join(tempfile.gettempdir(), "zarin_disk_bench")
os.makedirs(TMP, exist_ok=True)

SIZE_MB = int(sys.argv[1]) if len(sys.argv) > 1 else 512
NTHREADS = int(sys.argv[2]) if len(sys.argv) > 2 else 4


def make_blob(path, nbytes):
    if os.path.exists(path) and os.path.getsize(path) == nbytes:
        return
    chunk = np.random.default_rng(0).integers(0, 256, size=1 << 20, dtype=np.uint8).tobytes()
    with open(path, "wb") as f:
        for _ in range(nbytes // len(chunk)):
            f.write(chunk)


def bench_raw_single(path):
    n = os.path.getsize(path)
    t0 = time.perf_counter()
    with open(path, "rb") as f:
        while f.read(1 << 20):
            pass
    dt = time.perf_counter() - t0
    return n / dt / 1e6


def bench_raw_parallel(path, nthreads):
    n = os.path.getsize(path)
    per = n // nthreads
    def worker(i):
        with open(path, "rb") as f:
            f.seek(i * per)
            left = per if i < nthreads - 1 else n - i * per
            while left > 0:
                b = f.read(min(1 << 20, left))
                if not b:
                    break
                left -= len(b)
    ts = [threading.Thread(target=worker, args=(i,)) for i in range(nthreads)]
    t0 = time.perf_counter()
    [t.start() for t in ts]
    [t.join() for t in ts]
    return n / (time.perf_counter() - t0) / 1e6


def make_big_ply(path, nverts=2_000_000):
    if os.path.exists(path):
        return
    rng = np.random.default_rng(1)
    names = (["x", "y", "z", "nx", "ny", "nz", "f_dc_0", "f_dc_1", "f_dc_2"]
             + [f"f_rest_{i}" for i in range(45)]
             + ["opacity", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3"])
    header = "ply\nformat binary_little_endian 1.0\nelement vertex %d\n" % nverts
    header += "".join(f"property float {nm}\n" for nm in names) + "end_header\n"
    with open(path, "wb") as f:
        f.write(header.encode())
        f.write(rng.standard_normal((nverts, len(names)), dtype=np.float32).tobytes())


def make_big_obj(path, nverts=2_000_000):
    if os.path.exists(path):
        return
    rng = np.random.default_rng(2)
    with open(path, "w") as f:
        for v in rng.random((nverts, 3), dtype=np.float32):
            f.write(f"v {v[0]} {v[1]} {v[2]}\n")
        for i in range(1, nverts - 1, 3):
            f.write(f"f {i} {i+1} {i+2}\n")


def main():
    blob = os.path.join(TMP, f"blob_{SIZE_MB}mb.bin")
    make_blob(blob, SIZE_MB << 20)
    s1 = bench_raw_single(blob)
    sp = bench_raw_parallel(blob, NTHREADS)
    print(f"RAW single-thread read : {s1:8.1f} MB/s")
    print(f"RAW {NTHREADS}-thread read     : {sp:8.1f} MB/s   <- disk ceiling reference")

    ply = os.path.join(TMP, "big.ply")
    make_big_ply(ply)
    fsize = os.path.getsize(ply)
    from core.assets.ply_loader import load_ply_gaussian_splat
    t0 = time.perf_counter()
    d = load_ply_gaussian_splat(ply)
    dt = time.perf_counter() - t0
    print(f"PLY load               : {fsize/dt/1e6:8.1f} MB/s  ({dt:.2f}s, {fsize/1e6:.0f}MB file, {d.num_splats} splats)")

    obj = os.path.join(TMP, "big.obj")
    make_big_obj(obj)
    fsize = os.path.getsize(obj)
    from core.assets.importer import load_obj
    t0 = time.perf_counter()
    m = load_obj(obj)
    dt = time.perf_counter() - t0
    print(f"OBJ load               : {fsize/dt/1e6:8.1f} MB/s  ({dt:.2f}s, {fsize/1e6:.0f}MB file)")

    import shutil
    from core.assets.streaming import prefetch_files, load_many, disk_ceiling_mbps
    copies = []
    for i in range(4):
        c = os.path.join(TMP, f"big_copy{i}.obj")
        if not os.path.exists(c):
            shutil.copyfile(obj, c)
        copies.append(c)
    total = sum(os.path.getsize(c) for c in copies)
    b, dt = prefetch_files(copies, workers=4)
    print(f"prefetch 4 files      : {b/dt/1e6:8.1f} MB/s  ({dt:.2f}s, {b/1e6:.0f}MB)")
    from core.assets.importer import load_obj as _load_obj
    t0 = time.perf_counter()
    res = load_many(copies, _load_obj, workers=4, prefetch=False)
    dt = time.perf_counter() - t0
    ok = sum(1 for v in res.values() if v is not None)
    print(f"OBJ batch x4 threaded : {total/dt/1e6:8.1f} MB/s  ({dt:.2f}s, {ok}/4 ok)")

    plys = []
    for i in range(2):
        c = os.path.join(TMP, f"big_copy{i}.ply")
        if not os.path.exists(c):
            shutil.copyfile(ply, c)
        plys.append(c)
    total = sum(os.path.getsize(c) for c in plys)
    from core.assets.ply_loader import load_ply_gaussian_splat as _load_ply
    t0 = time.perf_counter()
    res = load_many(plys, _load_ply, workers=2, prefetch=False)
    dt = time.perf_counter() - t0
    ok = sum(1 for v in res.values() if v is not None)
    print(f"PLY batch x2 threaded : {total/dt/1e6:8.1f} MB/s  ({dt:.2f}s, {ok}/2 ok)")

    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from raw_disk_speed import uncached_read
    disk = uncached_read(blob)
    print(f"DISK ceiling uncached : {disk:8.1f} MB/s")
    print("TMPDIR:", TMP)


if __name__ == "__main__":
    main()
