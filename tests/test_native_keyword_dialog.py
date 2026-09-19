"""Drive only the isolated native_keyword_dialog.exe process, never Telegram."""
import argparse
import ctypes as c
from ctypes import wintypes as w
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import time

u=c.WinDLL('user32',use_last_error=True);g=c.WinDLL('gdi32',use_last_error=True)
def api(lib,name,args,result):
    f=getattr(lib,name);f.argtypes=args;f.restype=result;return f
send=api(u,'SendMessageW',[w.HWND,w.UINT,w.WPARAM,w.LPARAM],w.LPARAM)
item=api(u,'GetDlgItem',[w.HWND,c.c_int],w.HWND)
def settext(hwnd,value):
    buf=c.create_unicode_buffer(value);assert send(hwnd,0x0c,0,c.addressof(buf))
    assert read(hwnd)==value
gettext=api(u,'GetWindowTextW',[w.HWND,w.LPWSTR,c.c_int],c.c_int)
getpid=api(u,'GetWindowThreadProcessId',[w.HWND,c.POINTER(w.DWORD)],w.DWORD)
getclass=api(u,'GetClassNameW',[w.HWND,w.LPWSTR,c.c_int],c.c_int)
callback=c.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
enum=api(u,'EnumWindows',[callback,w.LPARAM],w.BOOL)
api(u,'SetProcessDpiAwarenessContext',[w.HANDLE],w.BOOL)(w.HANDLE(-4))
def window(proc):
    deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        found=[]
        @callback
        def visit(hwnd,lp):
            pid=w.DWORD();getpid(hwnd,c.byref(pid));name=c.create_unicode_buffer(80);getclass(hwnd,name,80)
            if pid.value==proc.pid and name.value=='#32770':found.append(hwnd)
            return True
        enum(visit,0)
        if found and item(found[0],100) and read(item(found[0],100)):return found[0]
        if proc.poll() is not None:raise AssertionError(proc.communicate())
        time.sleep(.05)
    raise AssertionError('isolated dialog did not open')
def read(hwnd):
    out=c.create_unicode_buffer(1024);send(hwnd,0x0d,1024,c.addressof(out));return out.value
def capture(hwnd,path):
    from PIL import Image
    rect=w.RECT();api(u,'GetWindowRect',[w.HWND,c.POINTER(w.RECT)],w.BOOL)(hwnd,c.byref(rect))
    width,height=rect.right-rect.left,rect.bottom-rect.top
    dc=api(u,'GetDC',[w.HWND],w.HDC)(hwnd)
    mem=api(g,'CreateCompatibleDC',[w.HDC],w.HDC)(dc)
    bmp=api(g,'CreateCompatibleBitmap',[w.HDC,c.c_int,c.c_int],w.HBITMAP)(dc,width,height)
    select=api(g,'SelectObject',[w.HDC,w.HANDLE],w.HANDLE);old=select(mem,bmp)
    assert api(u,'PrintWindow',[w.HWND,w.HDC,w.UINT],w.BOOL)(hwnd,mem,2)
    class Header(c.Structure):
        _fields_=[('size',w.DWORD),('width',w.LONG),('height',w.LONG),('planes',w.WORD),('bits',w.WORD),
                  ('compression',w.DWORD),('image',w.DWORD),('x',w.LONG),('y',w.LONG),('used',w.DWORD),('important',w.DWORD)]
    header=Header(40,width,-height,1,32,0,0,0,0,0,0);pixels=c.create_string_buffer(width*height*4)
    assert api(g,'GetDIBits',[w.HDC,w.HBITMAP,w.UINT,w.UINT,c.c_void_p,c.c_void_p,w.UINT],c.c_int)(mem,bmp,0,height,pixels,c.byref(header),0)
    Image.frombytes('RGB',(width,height),pixels.raw,'raw','BGRX').save(path)
    select(mem,old);api(g,'DeleteObject',[w.HANDLE],w.BOOL)(bmp);api(g,'DeleteDC',[w.HDC],w.BOOL)(mem)
    api(u,'ReleaseDC',[w.HWND,w.HDC],c.c_int)(hwnd,dc)
def run(exe,folder,mode):
    proc=subprocess.Popen([str(exe),str(folder),str(mode)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
    return proc,window(proc)
def finish(proc):
    stdout,stderr=proc.communicate(timeout=10)
    assert proc.returncode==0,(proc.returncode,stdout,stderr)
    return stdout.decode()
def main():
    p=argparse.ArgumentParser();p.add_argument('--exe',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    folder=Path(tempfile.mkdtemp(prefix='keyword-ui-',dir=a.output));reports=[]
    db=folder/'Telegram/blacklists/exact-search-keywords.v1.bin'
    proc,hwnd=run(a.exe.resolve(),folder,1)
    assert read(item(hwnd,100))=='✅固定广告模板🌹'
    time.sleep(.2);capture(hwnd,a.output/'keyword-prompt.png')
    settext(item(hwnd,100),'用户修改的广告🌹');send(hwnd,0x111,1,0)
    reports.append(finish(proc));raw=db.read_bytes()
    assert struct.unpack_from('<II',raw,12)==(1,1) and '用户修改的广告🌹'.encode('utf-16-le') in raw
    proc,hwnd=run(a.exe.resolve(),folder,1);send(hwnd,0x111,2,0)
    reports.append(finish(proc));assert db.read_bytes()==raw
    proc,hwnd=run(a.exe.resolve(),folder,3)
    assert send(item(hwnd,104),0x18b,0,0)==1
    settext(item(hwnd,100),'校园推广网络');send(item(hwnd,102),0xf5,0,0)
    assert send(item(hwnd,102),0xf0,0,0)==1
    send(hwnd,0x111,1,0);assert send(item(hwnd,104),0x18b,0,0)==2
    time.sleep(.2);capture(hwnd,a.output/'keyword-manager.png')
    send(item(hwnd,104),0x186,0,0);send(hwnd,0x111,105,0)
    assert send(item(hwnd,104),0x18b,0,0)==1
    send(hwnd,0x111,2,0);reports.append(finish(proc));raw=db.read_bytes()
    assert struct.unpack_from('<II',raw,12)==(1,2) and '校园推广网络'.encode('utf-16-le') in raw
    # The standalone PS 5.1 helper reads/writes precisely the same binary format.
    script=Path(__file__).resolve().parent.parent/'tools/Manage-Keywords.ps1'
    for operation in ('Add','Remove'):
        r=subprocess.run(['powershell.exe','-NoProfile','-File',str(script),'-Action',operation,'-Scope','Body','-Text','外部管理测试🌹','-Path',str(db)],capture_output=True)
        assert r.returncode==0,(operation,r.stdout,r.stderr)
    assert db.read_bytes()==raw
    result={'status':'passed','kind':'real Win32 dialogs + real scratch filesystem + PowerShell 5.1',
            'checks':['suggestion prefill','custom body keyword persisted','skip is a no-op','manager list',
                      'name-scope radio switch','multiple rules','delete exact selected rule','PowerShell interoperability'],
            'account_data_accessed':False,'runs':reports}
    (a.output/'native-keyword-test-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
