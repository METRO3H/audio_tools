import ctypes
import ctypes.wintypes
from pathlib import Path

# Definir estructura GUID (porque ctypes no la trae incluida)
class GUID(ctypes.Structure):
    _fields_ = [
        ('Data1', ctypes.c_ulong),
        ('Data2', ctypes.c_ushort),
        ('Data3', ctypes.c_ushort),
        ('Data4', ctypes.c_ubyte * 8)
    ]

    def __init__(self, guid_string):
        import uuid
        u = uuid.UUID(guid_string)
        ctypes.Structure.__init__(self)
        self.Data1 = u.time_low
        self.Data2 = u.time_mid
        self.Data3 = u.time_hi_version
        self.Data4[:] = u.bytes[8:]

# GUID oficial de la carpeta Descargas
FOLDERID_Downloads = '{374DE290-123F-4565-9164-39C4925E467B}'

def get_downloads_folder_windows():
    SHGetKnownFolderPath = ctypes.windll.shell32.SHGetKnownFolderPath
    SHGetKnownFolderPath.argtypes = [
        ctypes.POINTER(GUID), ctypes.wintypes.DWORD,
        ctypes.wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)
    ]
    SHGetKnownFolderPath.restype = ctypes.HRESULT

    path_ptr = ctypes.c_wchar_p()
    result = SHGetKnownFolderPath(
        ctypes.byref(GUID(FOLDERID_Downloads)), 0, None, ctypes.byref(path_ptr)
    )

    if result != 0:
        raise ctypes.WinError(result)

    return Path(path_ptr.value)

