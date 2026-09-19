"""Real checkbox/right-drag interactions in an isolated native test process.

Only the child harness PID may be opened; no Telegram process/account is read.
"""
import argparse
import ctypes as c
from ctypes import wintypes as w
import json
from pathlib import Path
import struct
import tempfile
import time
import test_native_keyword_dialog as t

k=c.WinDLL('kernel32',use_last_error=True)
class Remote:
    def __init__(self,proc):
        self.handle=t.api(k,'OpenProcess',[w.DWORD,w.BOOL,w.DWORD],w.HANDLE)(0x38,False,proc.pid)
        assert self.handle
        self.address=t.api(k,'VirtualAllocEx',[w.HANDLE,c.c_void_p,c.c_size_t,w.DWORD,w.DWORD],c.c_void_p)(self.handle,None,1024,0x3000,4)
        assert self.address
    def put(self,raw):
        n=c.c_size_t();buf=c.create_string_buffer(raw)
        assert t.api(k,'WriteProcessMemory',[w.HANDLE,c.c_void_p,c.c_void_p,c.c_size_t,c.POINTER(c.c_size_t)],w.BOOL)(self.handle,self.address,buf,len(raw),c.byref(n)) and n.value==len(raw)
        return self.address
    def get(self,n):
        buf=c.create_string_buffer(n);count=c.c_size_t()
        assert t.api(k,'ReadProcessMemory',[w.HANDLE,c.c_void_p,c.c_void_p,c.c_size_t,c.POINTER(c.c_size_t)],w.BOOL)(self.handle,self.address,buf,n,c.byref(count)) and count.value==n
        return buf.raw
    def close(self):
        t.api(k,'VirtualFreeEx',[w.HANDLE,c.c_void_p,c.c_size_t,w.DWORD],w.BOOL)(self.handle,self.address,0,0x8000)
        t.api(k,'CloseHandle',[w.HANDLE],w.BOOL)(self.handle)

def point(remote,view,index):
    remote.put(bytes(16))
    assert t.send(view,0x100e,index,remote.address) # LVM_GETITEMRECT
    x,y,right,bottom=struct.unpack('<4i',remote.get(16))
    return (max(x,0)+50,(y+bottom)//2)
def lp(point):return (point[0]&0xffff)|((point[1]&0xffff)<<16)
def checked(view,count=240):
    return [i for i in range(count) if t.send(view,0x102c,i,0xf000)==0x2000]
def sweep(remote,view,start,end):
    t.send(view,0x204,2,lp(point(remote,view,start)))
    t.send(view,0x200,2,lp(point(remote,view,end)))
    t.send(view,0x205,0,lp(point(remote,view,end)))

def main():
    p=argparse.ArgumentParser();p.add_argument('--exe',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    folder=Path(tempfile.mkdtemp(prefix='selection-',dir=a.output));checks=[];reports=[]
    proc,dialog=t.run(a.exe.resolve(),folder,12);remote=Remote(proc);view=t.item(dialog,200)
    time.sleep(.8);assert proc.poll() is None and t.send(view,0x1004,0,0)==240
    owner=t.api(t.u,'GetWindow',[w.HWND,w.UINT],w.HWND)(dialog,4)
    assert owner and not t.api(t.u,'IsWindowEnabled',[w.HWND],w.BOOL)(owner)
    checks.append('240 real native list rows survive destruction of transient active popup')
    assert checked(view)==[] and t.read(t.item(dialog,203))=='已选择 0 / 240 个频道'
    sweep(remote,view,0,5);assert checked(view)==list(range(6))
    sweep(remote,view,3,1);assert checked(view)==[0,4,5]
    t.send(dialog,0x8002,0,0);assert t.window(proc)==dialog and checked(view)==[0,4,5]
    checks.append('unowned menu resolves stable main owner; repeat-open raises same dialog and preserves checkboxes')
    checks.append('right drag selects every crossed row; reverse drag starting checked clears a range')
    # Normal checkbox click is handled by the common control, not test logic.
    x,y=point(remote,view,8)
    t.send(view,0x201,1,lp((8,y)));t.send(view,0x202,0,lp((8,y)))
    assert checked(view)==[0,4,5,8] and t.read(t.item(dialog,203))=='已选择 4 / 240 个频道'
    checks.append('ordinary checkbox click updates check state and selected count')
    t.send(dialog,0x111,202,0)
    t.send(view,0x204,2,lp(point(remote,view,2)))
    rect=w.RECT();t.api(t.u,'GetClientRect',[w.HWND,c.POINTER(w.RECT)],w.BOOL)(view,c.byref(rect))
    for _ in range(35):t.send(dialog,0x8001,0,lp((60,rect.bottom+5)))
    t.send(view,0x205,0,0)
    selected=checked(view);assert selected==list(range(2,selected[-1]+1)) and selected[-1]>35
    assert t.send(view,0x1027,0,0)>25
    # Direction reversal paints without toggling an already traversed row.
    t.send(view,0x204,2,lp(point(remote,view,selected[-1])))
    for _ in range(8):t.send(dialog,0x8001,0,lp((60,-5)))
    t.send(view,0x205,0,0)
    assert len(checked(view))<len(selected)
    checks.append('edge scroll traverses additional pages in both directions with continuous check ranges')
    t.send(dialog,0x111,202,0)
    t.send(view,0x1013,0,False)
    sweep(remote,view,0,5);sweep(remote,view,3,1)
    x,y=point(remote,view,8);t.send(view,0x201,1,lp((8,y)));t.send(view,0x202,0,lp((8,y)))
    t.send(view,0x115,1,0) # vertical line down
    t.send(view,0x1013,180,False) # ensure row 180 is visible
    assert checked(view)==[0,4,5,8]
    sweep(remote,view,178,180);assert checked(view)==[0,4,5,8,178,179,180]
    checks.append('selection persists while scrolling; right drag works on later pages')
    t.capture(dialog,a.output/'search-selection.png')
    t.send(dialog,0x111,202,0);assert checked(view)==[]
    t.send(dialog,0x111,201,0);assert len(checked(view))==240
    assert t.read(t.item(dialog,203))=='已选择 240 / 240 个频道'
    remote.close();t.send(dialog,0x111,2,0);reports.append(t.finish(proc))
    db=folder/'Telegram/blacklists/exact-search-channels.v1.bin'
    assert not db.exists()
    checks.append('select all/clear all and cancel leave the channel database untouched')
    proc,dialog=t.run(a.exe.resolve(),folder,12);remote=Remote(proc);view=t.item(dialog,200)
    sweep(remote,view,0,6);remote.close();t.send(dialog,0x111,1,0);reports.append(t.finish(proc))
    raw=db.read_bytes();assert raw[:8]==b'TGEXCH1\0' and struct.unpack_from('<II',raw,8)==(1,7)
    ids=[struct.unpack_from('<Q',raw,20+36*i)[0] for i in range(7)]
    assert ids==[0x2000000000001+i for i in range(7)]
    checks.append('one explicit commit persists exactly the seven selected channel IDs')
    # Reopen in the SAME running process: global busy/HWND state must reset.
    proc,dialog=t.run(a.exe.resolve(),folder,16);t.send(dialog,0x111,201,0);t.send(dialog,0x111,2,0)
    deadline=time.monotonic()+5
    while True:
        again=t.window(proc)
        if again!=dialog:break
        assert time.monotonic()<deadline
        time.sleep(.03)
    assert checked(t.item(again,200))==[]
    t.send(again,0x111,2,0);reports.append(t.finish(proc));assert db.read_bytes()==raw
    checks.append('cancel then reopen in the same process opens a fresh usable dialog; no stuck busy state or new rules')
    result={'status':'passed','account_data_accessed':False,'checks':checks,'runs':reports}
    (a.output/'native-selection-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
