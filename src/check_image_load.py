"""Ask the Windows kernel to validate SEC_IMAGE without executing the image."""
import ctypes, json, sys
from ctypes import wintypes
from pathlib import Path

k32 = ctypes.WinDLL('kernel32',use_last_error=True)
ntdll = ctypes.WinDLL('ntdll')
k32.CreateFileW.argtypes = (wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,
    ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE)
k32.CreateFileW.restype = wintypes.HANDLE
k32.CloseHandle.argtypes = (wintypes.HANDLE,)
ntdll.NtCreateSection.argtypes = (ctypes.POINTER(wintypes.HANDLE),wintypes.DWORD,
    ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE)
ntdll.NtCreateSection.restype = ctypes.c_long
ntdll.RtlNtStatusToDosError.argtypes = (ctypes.c_long,)
ntdll.RtlNtStatusToDosError.restype = wintypes.ULONG

def check(path):
    path = str(Path(path).resolve())
    handle = k32.CreateFileW(path,0x80000000,0x7,None,3,0x80,None)
    if handle == ctypes.c_void_p(-1).value:
        return {'path':path,'open_error':ctypes.get_last_error()}
    section=wintypes.HANDLE()
    try:
        status=ntdll.NtCreateSection(ctypes.byref(section),1,None,None,2,0x1000000,handle)
        return {'path':path,'ntstatus':hex(status&0xffffffff),
            'win32_error':ntdll.RtlNtStatusToDosError(status),
            'sec_image_created':status>=0,'image_code_executed':False}
    finally:
        if section.value:
            k32.CloseHandle(section)
        k32.CloseHandle(handle)

if __name__=='__main__':
    print(json.dumps([check(path) for path in sys.argv[1:]],indent=2))
