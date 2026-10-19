"""Arithmetic capacity and allocation preflight; no grid-resolution policy."""
import ctypes
import os
import sys

INT_MAX = 2**31 - 1  # Native loops, FFT dimensions and displacement coordinates.


def geometry_capacity(nx, ny, periodic, mirrors=(0, 0), *, fm=False):
    if any(type(n) is not int or n < 1 for n in (nx, ny)):
        raise ValueError('grid capacity: positive integer XY counts required')
    px, py = (nx, ny) if periodic else (2*nx, 2*ny)
    # Open-kernel wrap expressions add a displacement to the padded dimension.
    displacement = ((mirrors[0]+1)*nx-1, (mirrors[1]+1)*ny-1) if periodic else (3*nx-1, 3*ny-1)
    if max(nx*ny, px*py, py*(px//2+1), *displacement) > INT_MAX:
        raise ValueError(f'grid capacity: native signed 32-bit index/FFT/displacement overflow for {nx}x{ny}')
    coefficients = (2*nx-1)*(2*ny-1)
    if fm:
        if periodic:
            raise ValueError('FM capacity: only open XY is implemented')
        px = max(2, 1 << (2*nx-2).bit_length())
        py = max(2, 1 << (2*ny-2).bit_length())
        if max(px*py, coefficients) > INT_MAX:
            raise ValueError(f'grid capacity: Accelerate FFT/coefficient signed 32-bit overflow for {nx}x{ny}')
    count = nx*ny
    spectrum = py*(px//2+1)
    # 32 live vector-array slots cover initial/RK4/static/native/serialization copies.
    # FFT terms cover kernel, transform buffers, spectra and qualification copies.
    simulation = (32*(1 if fm else 2)*3*8*count +
                  (18*16*px*py + 48*coefficients if fm else 96*px*py + 192*spectrum))
    return dict(cells=count, fft_shape=(px, py), fft_real_count=px*py,
                fft_complex_count=spectrum, simulation_bytes=simulation,
                kernel_working_bytes=8*6*8*((nx*ny) if periodic else 4*nx*ny),
                kernel_file_bytes=6*8*((nx*ny) if periodic else 4*nx*ny),
                tensor_evaluations=(count*(2*mirrors[0]+1)*(2*mirrors[1]+1) if periodic else coefficients))


def available_memory():
    """Free+inactive Darwin pages (snapshot), or Linux available physical pages."""
    if sys.platform == 'darwin':
        lib = ctypes.CDLL('/usr/lib/libSystem.B.dylib')
        lib.mach_host_self.restype = ctypes.c_uint
        lib.mach_task_self.restype = ctypes.c_uint
        lib.host_page_size.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_size_t)]
        lib.host_statistics.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
        lib.mach_port_deallocate.argtypes = [ctypes.c_uint, ctypes.c_uint]
        values = (ctypes.c_uint * 15)(); count = ctypes.c_uint(15); page = ctypes.c_size_t()
        host = lib.mach_host_self()
        try:
            if lib.host_page_size(host, ctypes.byref(page)) or lib.host_statistics(host, 2, values, ctypes.byref(count)):
                raise RuntimeError('grid capacity: unable to query available memory')
        finally:
            lib.mach_port_deallocate(lib.mach_task_self(), host)
        amount = (int(values[0])+int(values[2]))*page.value
    else:
        amount = os.sysconf('SC_AVPHYS_PAGES')*os.sysconf('SC_PAGE_SIZE')
    configured = os.environ.get('FIMRUN_MEMORY_BUDGET_BYTES')
    if configured is not None:
        try: limit = int(configured)
        except ValueError: raise ValueError('FIMRUN_MEMORY_BUDGET_BYTES must be a positive integer') from None
        if limit <= 0: raise ValueError('FIMRUN_MEMORY_BUDGET_BYTES must be a positive integer')
        amount = min(amount, limit)
    return amount


def require_memory(estimated_bytes, operation):
    available = available_memory()
    if estimated_bytes > available:
        raise MemoryError(f'{operation}: estimated working arrays {estimated_bytes:,} bytes exceed '
                          f'available/configured budget {available:,} bytes; reduce grid/workload or free memory')
    return dict(estimated_bytes=estimated_bytes, available_bytes=available)


def model_capacity(model):
    from .micromagnetics.model import FM
    g = model.mesh
    return geometry_capacity(*g.cells[:2], g.boundary=='periodic_xy', g.mirrors, fm=isinstance(model, FM))
