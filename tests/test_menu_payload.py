"""Execute actual compiled menu/blacklist payload using synthetic Qt/Telegram objects.

Native Qt and Windows calls are ABI stubs. No process, account, tdata, or real sidecar
is opened. Persistence bytes remain in this Python object's in-memory filesystem.
"""
from pathlib import Path
import hashlib
import json
import os
import struct
import test_payload as old

ROOT=Path(__file__).resolve().parent
BUILD=Path(os.environ.get('TELEGRAM_TEST_BUILD_DIR',str(ROOT.parent/'build'))).resolve()
old.ROOT=BUILD
from unicorn import UC_HOOK_MEM_READ
from unicorn.x86_const import *

P=old.P
MASK=(1<<64)-1

class Machine(old.Machine):
    def __init__(self,base):
        # pefile uses mmap internally on Windows. Close both source mappings as
        # soon as the original helper has copied section bytes/export addresses.
        factory=old.pefile.PE;opened=[]
        class TrackingPE(factory):
            def __init__(self,*a,**kw):
                super().__init__(*a,**kw);opened.append(self)
        old.pefile.PE=TrackingPE
        try:super().__init__(BUILD/'Telegram.exact.exe',base)
        finally:
            old.pefile.PE=factory
            for pe in opened:pe.close()
        self.native_live={}
        self.heap_live={}
        self.free_events=[]
        self.files={}
        self.handles={}
        self.next_handle=0x9000
        self.last_error=0
        self.stub_next=0x900000000
        self.actions=[]
        self.connections=[]
        self.connection_dtors=[]
        self.dialogs=[]
        self.module_path=r'C:\Synthetic Telegram\Telegram.exe'
        self.final_module_path=r'\\?\C:\Synthetic Telegram\Telegram.exe'
        self.db_path=r'\\?\C:\Synthetic Telegram\exact-search-blacklist.v1.bin'
        self.reject_new_prefix=None
        self.file_creates=[]
        self.final_path_calls=[]
        self.dead_rows=[]
        self.original_text_calls=[]
        self.accept_connection=True
        self.qstring_destroyed=[]
        self.receive_calls=[]
        self.mouse_calls=[]
        self.refresh_calls=[]
        self.research_calls=[]
        self.receive_loading=[]
        self.crypto_hash_calls=0
        self.native(0x1bd5550,self.original_text)
        self.native(0x5cda52c,self.native_alloc)
        self.native(0x5ac71a0,self.native_free)
        self.native(0x405a00,self.native_alloc)
        self.native(0x5883280,self.construct_qstring)
        self.native(0x406b90,self.destroy_qstring)
        self.native(0x53cf580,self.construct_action)
        self.native(0x58cc5d0,self.connect)
        self.native(0x58c9fc0,self.connection_dtor)
        self.native(0x3bd9950,self.add_action)
        self.native(0x1583120,lambda a:self.mouse_calls.append(('searched',a[:2])))
        self.native(0x15830b0,lambda a:self.mouse_calls.append(('preview',a[:2])))
        self.native(0x158f3e0,lambda a:self.mouse_calls.append(('clear',a[:2])))
        self.native(0x158d170,lambda a:self.refresh_calls.append(a[:2]))
        self.native(0x459e00,self.research)
        self.native(0x158c1f0,self.receive)
        self.map(base+0x8e15fa0,8)
        self.u.mem_write(base+0x8e15fa0,struct.pack('<II',1,0))
        self.install_windows()
        self.u.hook_add(UC_HOOK_MEM_READ,self.guard_dead_rows)

    def native(self,rva,handler):
        self.map(self.base+rva,1)
        self.u.mem_write(self.base+rva,b'\xc3')
        self.handlers[self.base+rva]=handler

    def stub(self,name,handler):
        address=self.stub_next
        self.stub_next+=0x10
        self.map(address,1)
        self.u.mem_write(address,b'\xc3')
        self.handlers[address]=handler
        return address

    def iat(self,rva,name,handler):
        address=self.stub(name,handler)
        self.map(self.base+rva,8)
        self.put(self.base+rva,address)

    def u32(self,p,n): self.u.mem_write(p,struct.pack('<I',n&0xffffffff))

    def wide(self,p):
        result=bytearray()
        if not p:return ''
        while True:
            ch=bytes(self.u.mem_read(p,2));p+=2
            if ch==b'\0\0':break
            result+=ch
            assert len(result)<8192
        return result.decode('utf-16-le')

    def narrow(self,p):
        result=bytearray()
        while True:
            ch=bytes(self.u.mem_read(p,1));p+=1
            if ch==b'\0':break
            result+=ch
        return result.decode('ascii')

    def read_qstring(self,q):
        d=self.get(q)
        if not d:return ''
        n=self.i32(d+4)
        offset=struct.unpack('<q',self.u.mem_read(d+16,8))[0]
        return bytes(self.u.mem_read(d+offset,n*2)).decode('utf-16-le')

    def original_text(self,a):
        self.original_text_calls.append(a[0])
        return a[0]+0x30

    def native_alloc(self,a):
        if not a[0]:return 0
        p=self.alloc(a[0]);self.native_live[p]=a[0];return p

    def native_free(self,a):
        if not a[0]:return
        assert a[0] in self.native_live,('double/foreign native free',hex(a[0]),a[1])
        size=self.native_live.pop(a[0])
        assert a[1]==size,('sized native free',hex(a[0]),a[1],size)
        self.free_events.append((a[0],size))

    def construct_qstring(self,a):
        value=bytes(self.u.mem_read(a[1],(a[2]&0xffffffff)*2)).decode('utf-16-le')
        return self.qstring(value,a[0])

    def destroy_qstring(self,a):
        self.qstring_destroyed.append(a[0])

    def construct_action(self,a):
        assert self.native_live[a[0]]==16
        label=self.read_qstring(a[1])
        self.actions.append({'address':a[0],'label':label,'parent':a[2]})
        return a[0]

    def connect(self,a):
        assert self.get(a[2])==self.base+0x53d1540,('signal',a)
        assert a[4]==0 and (a[6]&0xffffffff)==2,('functor/queued arguments',a)
        assert a[7]==self.base+0x8e15fa0
        assert bytes(self.u.mem_read(a[7],8))==struct.pack('<II',1,0)
        assert a[8]==self.base+0x64432e0
        slot=a[5]
        assert self.i32(slot)==1
        assert self.get(slot+8)==self.exports['BlacklistSlotImpl']
        assert self.get(slot+16)==a[3]
        action=next(x for x in self.actions if x['address']==a[1])
        record={'sender':a[1],'inner':a[3],'slot':slot,'handle_out':a[0],
                'label':action['label'],'accepted':self.accept_connection}
        self.connections.append(record)
        handle=self.alloc(8) if self.accept_connection else 0
        if not self.accept_connection:
            # Qt connectImpl consumes the transferred initial reference even on
            # failure. Its native failure cleanup destroys this slot immediately.
            self.native_free([slot,72])
        self.put(a[0],handle)
        return a[0]

    def connection_dtor(self,a):self.connection_dtors.append(a[0])

    def add_action(self,a):
        action=next(x for x in self.actions if x['address']==a[2])
        assert a[0]==action['parent']
        assert a[3]==a[4]==0
        action['inserted']=True
        self.put(a[1],a[2])
        return a[1]

    def research(self,a):
        assert bytes(self.u.mem_read(a[1],1))==b'\1'
        assert bytes(self.u.mem_read(a[0]-0x858+0xa39,1))==b'\1'
        self.research_calls.append(a[0]-0x858)

    def receive(self,a):
        # Native searchReceived consumes the by-value pointer vector. Model its
        # documented replacement flags and create distinct new FakeRows/indexes.
        inner,vector,inject,kind,count=a[:5]
        kind&=255;count&=0xffffffff
        items=self.values(vector)
        with_preview=bytes(self.u.mem_read(inner+0x621,1))!=b'\0'
        to_preview=with_preview and bool(kind&2)
        self.receive_calls.append((inner,list(items),inject,kind,count))
        for offset,clear in ((0x3c8,bool(kind&4) and not bool(kind&1) and (not with_preview or not bool(kind&2))),
                             (0x398,not with_preview or to_preview)):
            if clear:
                for row in self.values(inner+offset):self.dead_rows.append((row,row+0x88))
                self.vector([],inner+offset)
        offset=0x398 if to_preview else 0x3c8
        rows=self.values(inner+offset)
        if inject:items=[inject]+items
        for index,item in enumerate(items,len(rows)):
            row=self.alloc(0x88);self.put(row+0x60,item);self.put(row+0x70,index);rows.append(row)
        self.vector(rows,inner+offset)
        self.u32(inner+(0x3e4 if kind&1 else 0x3b0 if to_preview else 0x3e0),count)
        self.u.mem_write(inner+0xa38,self.receive_loading.pop(0) if self.receive_loading else b'\0\0')
        pointer=self.get(vector)
        if pointer in self.native_live:
            assert self.native_live[pointer]==self.get(vector+16)-pointer
            self.native_free([pointer,self.native_live[pointer]])

    def install_windows(self):
        self.iat(0x5f524a0,'GetProcessHeap',lambda a:0x4444)
        def heap_alloc(a):
            assert a[0]==0x4444 and a[1]==8
            p=self.alloc(a[2]);self.heap_live[p]=a[2];return p
        def heap_free(a):
            assert a[0]==0x4444 and a[1]==0
            assert a[2] in self.heap_live,('heap double free',hex(a[2]))
            del self.heap_live[a[2]];return 1
        self.iat(0x5f52940,'HeapAlloc',heap_alloc)
        self.iat(0x5f524a8,'HeapFree',heap_free)
        def module_name(a):
            encoded=self.module_path.encode('utf-16-le')+b'\0\0'
            assert a[2]>len(encoded)//2
            self.u.mem_write(a[1],encoded);return len(encoded)//2-1
        self.iat(0x5f52118,'GetModuleFileNameW',module_name)
        self.iat(0x5f52078,'GetLastError',lambda a:self.last_error)
        self.iat(0x5f52100,'GetCurrentProcessId',lambda a:12345)
        self.iat(0x5f52220,'GetTickCount64',lambda a:987654321)
        def create(a):
            path=self.wide(a[0]);mode=a[4]&0xffffffff
            self.file_creates.append((path,a[1]&0xffffffff,a[2]&0xffffffff,mode))
            if path==self.module_path:
                assert a[1]==0 and a[2]==7 and mode==3
                handle=self.next_handle;self.next_handle+=1
                self.handles[handle]={'path':path,'position':0,'access':0,'executable':True};return handle
            if mode==1 and self.reject_new_prefix and path.startswith(self.reject_new_prefix):self.last_error=80;return MASK
            if mode==3 and path not in self.files:self.last_error=2;return MASK
            if mode==1 and path in self.files:self.last_error=80;return MASK
            if mode in (1,4):self.files.setdefault(path,b'')
            handle=self.next_handle;self.next_handle+=1
            self.handles[handle]={'path':path,'position':0,'access':a[1]};return handle
        self.iat(0x5f52098,'CreateFileW',create)
        def read(a):
            f=self.handles[a[0]];raw=self.files[f['path']]
            data=raw[f['position']:f['position']+a[2]]
            if data:self.u.mem_write(a[1],data)
            f['position']+=len(data);self.u32(a[3],len(data));return 1
        self.iat(0x5f521e0,'ReadFile',read)
        def write(a):
            f=self.handles[a[0]];raw=self.files[f['path']]
            chunk=bytes(self.u.mem_read(a[1],a[2]));at=f['position']
            self.files[f['path']]=raw[:at]+chunk+raw[at+len(chunk):]
            f['position']+=len(chunk);self.u32(a[3],len(chunk));return 1
        self.iat(0x5f520a0,'WriteFile',write)
        def close(a):assert a[0] in self.handles;del self.handles[a[0]];return 1
        self.iat(0x5f520a8,'CloseHandle',close)
        def size(a):self.put(a[1],len(self.files[self.handles[a[0]]['path']]));return 1
        self.iat(0x5f52068,'GetFileSizeEx',size)
        self.iat(0x5f52288,'FlushFileBuffers',lambda a:1)
        def move(a):
            assert a[2]==9
            self.files[self.wide(a[1])]=self.files.pop(self.wide(a[0]));return 1
        self.iat(0x5f52280,'MoveFileExW',move)
        def delete(a):self.files.pop(self.wide(a[0]),None);return 1
        self.iat(0x5f52080,'DeleteFileW',delete)
        def load(a):assert self.wide(a[0]).lower()=='bcrypt.dll' and a[2]==0x800;return 0x5555
        self.iat(0x5f52398,'LoadLibraryExW',load)
        self.iat(0x5f521c8,'FreeLibrary',lambda a:1)
        def crypto_open(a):assert self.wide(a[1])=='SHA256';self.put(a[0],0x6666);return 0
        def crypto_hash(a):
            self.crypto_hash_calls+=1
            assert a[0]==0x6666 and a[1]==a[2]==0 and (a[6]&0xffffffff)==32
            size=a[4]&0xffffffff
            value=bytes(self.u.mem_read(a[3],size)) if size else b''
            self.u.mem_write(a[5],hashlib.sha256(value).digest());return 0
        names={'BCryptOpenAlgorithmProvider':self.stub('crypto_open',crypto_open),
               'BCryptCloseAlgorithmProvider':self.stub('crypto_close',lambda a:0),
               'BCryptHash':self.stub('crypto_hash',crypto_hash)}
        def message_box(a):self.dialogs.append((self.wide(a[1]),self.wide(a[2]),a[3]));return 1
        names['MessageBoxW']=self.stub('message_box',message_box)
        def final_path(a):
            assert self.handles[a[0]].get('executable') and a[3]==0
            value=self.final_module_path;raw=value.encode('utf-16-le')+b'\0\0'
            self.final_path_calls.append((a[0],value))
            if len(raw)//2>a[2]:return len(raw)//2
            self.u.mem_write(a[1],raw);return len(raw)//2-1
        names['GetFinalPathNameByHandleW']=self.stub('final_path',final_path)
        self.dynamic_names=names
        modules={'user32.dll':0x7777,'kernel32.dll':0x8888}
        self.iat(0x5f52148,'GetModuleHandleW',lambda a:modules.get(self.wide(a[0]).lower(),0))
        self.iat(0x5f521c0,'GetProcAddress',lambda a:names.get(self.narrow(a[1]),0))

    def seed_blacklist(self,values):
        self.files[self.db_path]=b'TGEXBL1\0'+struct.pack('<II',1,len(values))+b''.join(
            struct.pack('<I',len(v.encode('utf-16-le'))//2)+hashlib.sha256(v.encode('utf-16-le')).digest()
            for v in values)

    def saved_keys(self):
        raw=self.files.get(self.db_path,b'')
        if not raw:return []
        assert raw[:8]==b'TGEXBL1\0' and struct.unpack_from('<I',raw,8)[0]==1
        count=struct.unpack_from('<I',raw,12)[0]
        assert len(raw)==16+36*count
        return [(struct.unpack_from('<I',raw,16+i*36)[0],raw[20+i*36:52+i*36]) for i in range(count)]

    def destroy_connections(self):
        for c in self.connections:
            if c['slot'] in self.native_live:self.call('BlacklistSlotImpl',0,c['slot'],0,0,0)
        self.connections.clear()

    def row_items(self,inner,offset):return [self.get(p+0x60) for p in self.values(inner+offset)]

    def install_real_file_api(self,folder):
        """Optional Windows-only probe: VM payload + real isolated file APIs.

        Heap/Qt/crypto remain instrumented. Only the explicitly supplied scratch
        folder may be accessed; no actual Telegram data or sidecar is touched.
        """
        import ctypes as c
        from ctypes import wintypes as w
        folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
        self.module_path=str(folder/'Telegram.exe')
        self.db_path=str(folder/'exact-search-blacklist.v1.bin')
        self.file_api_trace=[];self.real_handles=set()
        kernel=c.WinDLL('kernel32',use_last_error=True)
        def function(name,args,ret):
            fn=getattr(kernel,name);fn.argtypes=args;fn.restype=ret;return fn
        create=function('CreateFileW',[w.LPCWSTR,w.DWORD,w.DWORD,c.c_void_p,w.DWORD,w.DWORD,c.c_void_p],c.c_void_p)
        read=function('ReadFile',[c.c_void_p,c.c_void_p,w.DWORD,c.POINTER(w.DWORD),c.c_void_p],w.BOOL)
        write=function('WriteFile',[c.c_void_p,c.c_void_p,w.DWORD,c.POINTER(w.DWORD),c.c_void_p],w.BOOL)
        close=function('CloseHandle',[c.c_void_p],w.BOOL)
        size=function('GetFileSizeEx',[c.c_void_p,c.POINTER(c.c_longlong)],w.BOOL)
        flush=function('FlushFileBuffers',[c.c_void_p],w.BOOL)
        move=function('MoveFileExW',[w.LPCWSTR,w.LPCWSTR,w.DWORD],w.BOOL)
        delete=function('DeleteFileW',[w.LPCWSTR],w.BOOL)
        def path(pointer):
            value=self.wide(pointer)
            assert Path(value).resolve().parent==folder,('probe escaped folder',value)
            return value
        def trace(name,args,result):
            self.last_error=c.get_last_error()
            self.file_api_trace.append({'function':name,'args':args,'result':result,'last_error':self.last_error})
            return result
        def call_create(a):
            filename=path(a[0]);flags=[a[i]&0xffffffff for i in (1,2,4,5)]
            assert not a[3] and not a[6]
            result=create(filename,flags[0],flags[1],None,flags[2],flags[3],None)
            result=trace('CreateFileW',[filename,*flags],result)
            if result!=MASK:self.real_handles.add(result)
            return result
        def call_read(a):
            length=a[2]&0xffffffff;buf=c.create_string_buffer(length);got=w.DWORD()
            result=read(a[0],buf,length,c.byref(got),None)
            trace('ReadFile',[a[0],length],result)
            if got.value:self.u.mem_write(a[1],buf.raw[:got.value])
            self.u32(a[3],got.value);return result
        def call_write(a):
            length=a[2]&0xffffffff;buf=c.create_string_buffer(bytes(self.u.mem_read(a[1],length)));got=w.DWORD()
            result=write(a[0],buf,length,c.byref(got),None)
            trace('WriteFile',[a[0],length],result);self.u32(a[3],got.value);return result
        def call_close(a):
            result=close(a[0]);trace('CloseHandle',[a[0]],result)
            if result:self.real_handles.remove(a[0])
            return result
        def call_size(a):
            n=c.c_longlong();result=size(a[0],c.byref(n));trace('GetFileSizeEx',[a[0]],result)
            self.put(a[1],n.value);return result
        def call_flush(a):return trace('FlushFileBuffers',[a[0]],flush(a[0]))
        def call_move(a):
            src,dst=path(a[0]),path(a[1]);flags=a[2]&0xffffffff
            return trace('MoveFileExW',[src,dst,flags],move(src,dst,flags))
        def call_delete(a):
            filename=path(a[0]);return trace('DeleteFileW',[filename],delete(filename))
        for rva,name,fn in [(0x5f52098,'CreateFileW',call_create),(0x5f521e0,'ReadFile',call_read),
            (0x5f520a0,'WriteFile',call_write),(0x5f520a8,'CloseHandle',call_close),
            (0x5f52068,'GetFileSizeEx',call_size),(0x5f52288,'FlushFileBuffers',call_flush),
            (0x5f52280,'MoveFileExW',call_move),(0x5f52080,'DeleteFileW',call_delete)]:self.iat(rva,name,fn)

    def guard_dead_rows(self,u,access,address,size,value,data):
        for lo,hi in self.dead_rows:
            assert not (address<hi and address+size>lo),('read old FakeRow after native destruction',hex(address))

    def hook(self,u,addr,size,data):
        if addr==self.stop:u.emu_stop();return
        handler=self.handlers.get(addr)
        if handler is not None:
            rsp=u.reg_read(UC_X86_REG_RSP)
            assert rsp%16==8,('native call stack misaligned',hex(addr),hex(rsp))
            args=[u.reg_read(r) for r in old.REGS]+[self.get(rsp+0x28+i*8) for i in range(5)]
            self.events.append((addr-self.base,args))
            result=handler(args)
            u.reg_write(UC_X86_REG_RAX,0 if result is None else result&MASK)
            u.reg_write(UC_X86_REG_RIP,self.get(rsp));u.reg_write(UC_X86_REG_RSP,rsp+8)

    def call(self,name,*args,extra=None):
        xmm={r:(0x123456789abcdef00123456789abcdef+i) for i,r in enumerate(range(UC_X86_REG_XMM6,UC_X86_REG_XMM15+1))}
        for r,v in xmm.items():self.u.reg_write(r,v)
        result=super().call(name,*args,extra=extra)
        for r,v in xmm.items():assert self.u.reg_read(r)==v,('XMM nonvolatile register changed',r)
        return result

    def message(self,value,history,msgid):
        item=self.item(value);self.put(item+8,msgid);self.put(item+0x10,history)
        row=self.alloc(0x88);self.put(row+0x60,item)
        return item,row

    def menu_scene(self,value='屏蔽这条完整内容',target_preview=False):
        inner=self.inner('内容');self.u32(inner+0x4b0,1)
        control=self.alloc(8);self.u32(control+4,1)
        popup=self.alloc(0x350);menu=self.alloc(0x400)
        self.put(inner+0xa40,control);self.put(inner+0xa48,popup);self.put(popup+0x1b0,menu)
        history=self.alloc(0x400);other_history=self.alloc(0x400)
        selected,selected_row=self.message(value,history,101)
        decoy,decoy_row=self.message('另一条相同编号内容',other_history,101)
        sibling,sibling_row=self.message('同一聊天其他内容',history,102)
        self.vector([decoy_row,selected_row] if target_preview else [sibling_row],inner+0x398)
        self.vector([sibling_row] if target_preview else [decoy_row,selected_row],inner+0x3c8)
        self.put(inner+0x6a0,history);self.put(inner+0x6a8,123456);self.put(inner+0x6b0,101)
        connection=self.alloc(8)
        return inner,connection,selected,value


def suite(m):
    passed=[]
    required={'PatchMenu','BlacklistSlotImpl','RefreshBlocked'}
    assert required<=m.exports.keys(),('build lacks menu exports',sorted(m.exports))
    bridge=next((name for name in ('PatchMenuBridge','PatchMenuConnectBridge') if name in m.exports),None)
    assert bridge,'menu bridge export missing'
    for preview in (False,True):
        m.actions.clear();m.connections.clear()
        inner,handle,item,value=m.menu_scene(target_preview=preview)
        m.call(bridge,handle,extra={UC_X86_REG_RSI:inner})
        assert handle in m.connection_dtors
        blocking=[c for c in m.connections if c['label']=='屏蔽相同内容']
        assert len(blocking)==1,[x['label'] for x in m.actions]
        slot=blocking[0]['slot']
        assert m.native_live[slot]==72
        assert m.i32(slot+24)==1
        assert m.i32(slot+32)==len(value.encode('utf-16-le'))//2
        assert bytes(m.u.mem_read(slot+36,32))==hashlib.sha256(value.encode('utf-16-le')).digest()
        assert all(a.get('inserted') for a in m.actions)
        assert all(c['slot'] in m.native_live for c in m.connections),'producer freed transferred slot'
        assert not m.heap_live and not m.handles,'menu open leaked temporary DB resources'
        # A compare dispatch must have no storage/UI effect and a last-ref destroy
        # must free each native slot exactly once without touching its source row.
        m.u.mem_write(inner+0x6a0,bytes(24))
        compare=m.alloc(1);m.u.mem_write(compare,b'\0')
        m.call('BlacklistSlotImpl',2,slot,0,0,compare)
        assert bytes(m.u.mem_read(compare,1))==b'\0'
        for c in list(m.connections):
            m.call('BlacklistSlotImpl',0,c['slot'],0,0,0)
            assert c['slot'] not in m.native_live
    passed.append('menu bridge: RSI->RDX, all nonvolatile registers/stack, search+preview row identity, Chinese labels')
    passed.append('native QAction/UiMenu ABI, nine connect arguments, queued bool type data, owned 72-byte slots')
    passed.append('slot hash+length snapshot survives menuRow clearing, compare and destruction, temporary DB cleanup')
    m.actions.clear();m.connections.clear();m.accept_connection=False
    inner,handle,item,value=m.menu_scene()
    m.call(bridge,handle,extra={UC_X86_REG_RSI:inner})
    assert len(m.connections)==1 and not m.connections[0]['accepted']
    assert m.connections[0]['slot'] not in m.native_live
    assert m.actions[0]['inserted'] and not m.heap_live and not m.handles
    m.connections.clear();m.accept_connection=True
    passed.append('native failed connect consumes initial slot reference without producer double-free')

    for preview in (False,True):
        m.files.clear();m.actions.clear();m.connections.clear()
        inner,handle,item,value=m.menu_scene(target_preview=False)
        m.u.mem_write(inner+0x621,bytes([preview]))
        history=m.get(item+0x10)
        duplicate,row_duplicate=m.message(value,m.alloc(0x400),908)
        near,row_near=m.message(value+'附加字',history,909)
        before=m.values(inner+0x3c8)
        m.vector(before+[row_duplicate,row_near],inner+0x3c8)
        preview_duplicate,row_preview=m.message(value,history,910)
        preview_keep,row_keep=m.message('不同内容🌸',history,911)
        m.vector([row_preview,row_keep],inner+0x398)
        expected_normal=[m.get(p+0x60) for p in before if m.get(p+0x60)!=item]+[near]
        all_old_rows=m.values(inner+0x3c8)+m.values(inner+0x398)
        m.call(bridge,handle,extra={UC_X86_REG_RSI:inner})
        slot=next(c['slot'] for c in m.connections if c['label']=='屏蔽相同内容')
        # Emulate original popup destruction before queued invocation. Block only
        # the captured whole-text hash, regardless of this cleared mutable row.
        m.u.mem_write(inner+0x6a0,bytes(24))
        m.put(inner+0x1d0,all_old_rows[0]);m.u.mem_write(inner+0x1da,b'\1')
        m.u.mem_write(inner+0xa38,b'\1\1')
        receive_start=len(m.receive_calls);mouse_start=len(m.mouse_calls)
        m.call('BlacklistSlotImpl',1,slot,inner,0,0)
        key=(len(value.encode('utf-16-le'))//2,hashlib.sha256(value.encode('utf-16-le')).digest())
        assert m.saved_keys()==[key]
        assert m.row_items(inner,0x3c8)==expected_normal
        assert m.row_items(inner,0x398)==([preview_keep] if preview else [])
        assert m.i32(inner+0x3e0)==len(expected_normal) and m.i32(inner+0x3e4)==0
        assert m.i32(inner+0x3b0)==int(preview)
        assert bytes(m.u.mem_read(inner+0xa38,2))==b'\1\1'
        assert m.get(inner+0x1d0)==0 and bytes(m.u.mem_read(inner+0x1da,1))==b'\0'
        assert [x[0] for x in m.mouse_calls[mouse_start:]]==['searched','preview','clear']
        assert [x[3] for x in m.receive_calls[receive_start:]]==([4,6] if preview else [4])
        assert not set(m.values(inner+0x3c8)+m.values(inner+0x398))&set(all_old_rows)
        for offset in (0x3c8,0x398):
            assert [m.get(row+0x70) for row in m.values(inner+offset)]==list(range(len(m.values(inner+offset))))
        assert slot in m.native_live,'Call prematurely destroyed slot'
        assert not m.heap_live and not m.handles
        assert all(size in (16,72) for size in m.native_live.values()),'snapshot vector ownership leak'
        m.destroy_connections()
    passed.append('queued Block Call persists full UTF-16 hash; duplicate removal across histories/search/preview, near-text retained')
    passed.append('native replacement rebuilds new FakeRows/indexes, consumes snapshot buffers, old-row poison guard, counts/mouse/loading preserved')
    inner,handle,item,value=m.menu_scene()
    m.u.mem_write(inner+0x621,b'\1')
    m.u.mem_write(inner+0xa38,b'\0\0')
    m.receive_loading=[b'\1\0',b'\0\0']
    m.call('RefreshBlocked',inner)
    assert bytes(m.u.mem_read(inner+0xa38,2))==b'\1\0'
    assert not m.receive_loading and not m.heap_live and not m.handles
    passed.append('loading flag raised during first native rebuild survives second rebuild clearing it')

    # Undo is another owned slot and asks the native reactive search producer to
    # repeat the current search; it never resurrects dangling snapshot rows.
    m.actions.clear();m.connections.clear()
    inner,handle,item,value=m.menu_scene(value='尚未屏蔽的内容')
    m.call(bridge,handle,extra={UC_X86_REG_RSI:inner})
    undo=next(c['slot'] for c in m.connections if c['label']=='撤销上次屏蔽')
    assert m.i32(undo+24)==2 and bytes(m.u.mem_read(undo+32,36))==bytes(36)
    m.u.mem_write(inner+0x6a0,bytes(24))
    re_start=len(m.research_calls)
    m.call('BlacklistSlotImpl',1,undo,inner,0,0)
    assert m.saved_keys()==[] and m.research_calls[re_start:]==[inner]
    assert not m.heap_live and not m.handles
    m.destroy_connections()
    passed.append('Undo label/operation snapshot removes latest record and invokes native instant repeat-search with inner+0x858')

    # A persisted record is applied to a later independent search/page and its
    # injected item, including scoped searches where literal-global is inactive.
    blocked='完整相同内容🌸\n第二行';m.seed_blacklist([blocked])
    for scope in (0,0x5e0):
        inner=m.inner('内容',scope)
        values=[blocked,'完整相同内容🌸\n第二行附加','其他内容']
        items=[m.item(v) for v in values];vector=m.vector(items)
        old_begin=m.get(vector);old_capacity=m.get(vector+16)
        injected=m.item(blocked);receive_start=len(m.receive_calls)
        m.call('PatchMessages',inner,vector,injected,4,100)
        seen=m.receive_calls[receive_start:]
        assert len(seen)==1 and seen[0][1]==items[1:] and seen[0][2]==0
        assert m.get(vector)==old_begin and m.get(vector+16)==old_capacity
        assert not m.heap_live and not m.handles
    passed.append('future-page blacklist exact whole-text filtering in global and scoped search, blocked inject rejected, vector capacity intact')

    # Corrupt storage cannot silently change UI/results or leak a partial record.
    m.actions.clear();m.connections.clear();m.files.clear()
    inner,handle,item,value=m.menu_scene()
    m.call(bridge,handle,extra={UC_X86_REG_RSI:inner})
    block=next(c['slot'] for c in m.connections if c['label']=='屏蔽相同内容')
    m.files[m.db_path]=b'corrupt';before=m.values(inner+0x3c8)
    receive_start=len(m.receive_calls);dialog_start=len(m.dialogs)
    m.call('BlacklistSlotImpl',1,block,inner,0,0)
    assert m.files[m.db_path]==b'corrupt' and m.values(inner+0x3c8)==before
    assert len(m.receive_calls)==receive_start and len(m.dialogs)==dialog_start+1
    assert m.dialogs[-1][1]=='搜索内容屏蔽'
    assert not m.heap_live and not m.handles
    m.destroy_connections()
    passed.append('corrupt DB mutation reports Chinese error, preserves DB/results and closes all temporary resources')

    m.files.clear()
    for kind in ('unfiltered','missing_popup','missing_id','missing_history','missing_item','empty_text'):
        m.actions.clear();m.connections.clear()
        inner,handle,item,value=m.menu_scene(value='' if kind=='empty_text' else '内容')
        if kind=='unfiltered':m.u32(inner+0x4b0,0)
        if kind=='missing_popup':m.put(inner+0xa48,0)
        if kind=='missing_id':m.put(inner+0x6b0,0)
        if kind=='missing_history':m.put(inner+0x6a0,0)
        if kind=='missing_item':m.put(inner+0x6b0,9000)
        m.call(bridge,handle,extra={UC_X86_REG_RSI:inner})
        assert not m.actions and handle in m.connection_dtors
        assert not m.heap_live and not m.handles
    passed.append('non-message, missing-context, unfiltered and empty-text guards retain original connection destruction')

    keyword_cases=[
        ('重庆这里有好人','好人 重庆',True),
        ('好人住在重庆','好人 重庆',True),
        ('好人\n跨行描述\n重庆','好人 重庆',True),
        ('好人只有一个词','好人 重庆',False),
        ('重庆只有一个词','好人 重庆',False),
        ('好 人在重庆','好人 重庆',False),
        ('好人重 庆','好人 重庆',False),
        ('重庆有好人','\t 好人  \n重庆 \r',True),
        ('重庆有好人','好人\u3000重庆',True),
        ('重庆有好人','好人\u00a0重庆',True),
        ('重庆有好人','好人\u2028重庆',True),
        ('AB重庆','AB 重庆',True),
        ('ab重庆','AB 重庆',False),
        ('重慶有好人','好人 重庆',False),
        ('花🌸有好人','🌸 好人',True),
        ('好人重复词','好人 好人',True),
        ('任意内容',' \t\u3000',True),
        ('','好人 重庆',False),
    ]
    assert 'AllKeywordsMatch' in m.exports
    for hay,query,wanted in keyword_cases:
        assert bool(m.call('AllKeywordsMatch',m.qstring(hay),m.qstring(query)))==wanted,(hay,query)
    blocked='重庆的好人完全重复';m.seed_blacklist([blocked])
    inner=m.inner('好人\u3000重庆')
    contents=[blocked,'好人住在重庆','重庆\n这里有好人','只有好人','好 人在重庆','重庆好人附加文本']
    items=[m.item(v) for v in contents];vector=m.vector(items)
    receive_start=len(m.receive_calls)
    m.call('PatchMessages',inner,vector,m.item('只有好人'),4,200)
    assert m.receive_calls[receive_start][1]==[items[1],items[2],items[5]]
    assert m.receive_calls[receive_start][2]==0
    assert not m.heap_live and not m.handles
    passed.append(f'AND whitespace-separated exact message keywords: {len(keyword_cases)} Unicode/order/missing/broken/case cases plus blacklist integration')
    # A migrated launch spelling can accept the read-only EXE metadata handle but
    # reject CREATE_NEW sidecars. Canonical resolution must precede every DB path.
    m.files.clear();m.actions.clear();m.connections.clear();m.file_creates.clear();m.final_path_calls.clear()
    m.module_path=r'C:\Synthetic Telegram Link\Telegram.exe'
    m.final_module_path=r'\\?\D:\Synthetic Telegram Target\Telegram.exe'
    m.db_path=r'\\?\D:\Synthetic Telegram Target\exact-search-blacklist.v1.bin'
    m.reject_new_prefix=r'C:\Synthetic Telegram Link'
    inner,handle,item,value=m.menu_scene(value='迁移目录内的内容🌸')
    m.call(bridge,handle,extra={UC_X86_REG_RSI:inner})
    slot=next(c['slot'] for c in m.connections if c['label']=='屏蔽相同内容')
    m.call('BlacklistSlotImpl',1,slot,inner,0,0)
    assert len(m.saved_keys())==1
    sidecars=[r for r in m.file_creates if r[0]!=m.module_path]
    canonical_directory=m.db_path.rsplit('\\',1)[0]+'\\'
    assert sidecars and all(r[0].startswith(canonical_directory) for r in sidecars)
    assert any(r[3]==1 for r in sidecars),'atomic temporary file was never created'
    assert m.final_path_calls and not m.heap_live and not m.handles
    m.destroy_connections()
    passed.append('junction launch C path resolves via EXE metadata handle to extended D path before sidecar/temp writes; CREATE_NEW C failure avoided')

    m.files.clear();m.file_creates.clear();m.crypto_hash_calls=0
    inner=m.inner('好人 重庆');vector=m.vector([m.item('只有好人'),m.item('重庆缺另一词')])
    before=len(m.receive_calls)
    m.call('PatchMessages',inner,vector,m.item('无关注入'),4,123)
    assert m.receive_calls[before][1]==[] and m.receive_calls[before][2]==0
    assert not m.file_creates and not m.crypto_hash_calls and not m.heap_live
    passed.append('fully keyword-rejected page/inject avoids all DB file opens and crypto calls')

    # A deliberately pathological bucket cluster checks full digest comparison,
    # probe termination and original-order Undo despite duplicate on-disk keys.
    value='同长度索引命中内容';raw=value.encode('utf-16-le');digest=hashlib.sha256(raw).digest()
    length=len(raw)//2
    keys=[(length,digest)]
    for n in range(298):keys.append((length,digest[:4]+struct.pack('<I',n)+bytes([0xa5])*24))
    keys.append((length,digest))
    m.files[m.db_path]=b'TGEXBL1\0'+struct.pack('<II',1,len(keys))+b''.join(struct.pack('<I',n)+d for n,d in keys)
    m.crypto_hash_calls=0
    inner=m.inner('');items=[m.item(value),m.item('X'*length),m.item('不同长度')];vector=m.vector(items)
    before=len(m.receive_calls)
    m.call('PatchMessages',inner,vector,0,4,123)
    assert m.receive_calls[before][1]==items[1:]
    assert m.crypto_hash_calls==2,'impossible length still hashed or equal-length lookup missed hashing'
    assert not m.heap_live and not m.handles
    m.actions.clear();m.connections.clear()
    inner,handle,item,text=m.menu_scene(value='可右键的未屏蔽内容')
    m.call(bridge,handle,extra={UC_X86_REG_RSI:inner})
    undo=next(c['slot'] for c in m.connections if c['label']=='撤销上次屏蔽')
    m.call('BlacklistSlotImpl',1,undo,inner,0,0)
    assert m.saved_keys()==keys[:-1],'Undo changed insertion order or removed more than last record'
    m.destroy_connections()
    # Earlier duplicate remains a valid block after removing the last duplicate.
    inner=m.inner('');vector=m.vector([m.item(value)]);before=len(m.receive_calls)
    m.call('PatchMessages',inner,vector,0,4,99)
    assert m.receive_calls[before][1]==[] and not m.heap_live and not m.handles
    passed.append('300-key collision cluster: equal-length hit/miss full-digest check, impossible lengths skip crypto, duplicate-key Undo preserves order')
    return passed


def timer_patch_suite(m,original):
    with old.pefile.PE(str(original),fast_load=True) as old_pe:
        original_bytes=old_pe.get_data(0x15fdca6,0x13)
    with old.pefile.PE(str(BUILD/'Telegram.exact.exe'),fast_load=True) as new_pe:
        patched_bytes=new_pe.get_data(0x15fdca6,0x13)
    assert original_bytes[6:11]==bytes.fromhex('ba84030000')
    assert patched_bytes[6:11]==bytes.fromhex('ba2c010000')
    assert patched_bytes[:6]==original_bytes[:6] and patched_bytes[11:]==original_bytes[11:]
    capture=[];m.native(0x39d1450,lambda a:capture.append(a[:4]))
    address=m.base+0x15fdca2;m.map(address,64)
    m.u.mem_write(address,bytes.fromhex('4883ec28')+patched_bytes+bytes.fromhex('4883c428c3'))
    m.exports['TimerPatchBlock']=address
    timer=m.alloc(128);m.call('TimerPatchBlock',timer)
    assert capture==[[timer,300,1,1]],capture
    return 'single five-byte timer literal changes 900 to 300 ms; native callee/RCX/R8/R9 and register/stack ABI preserved'


def main():
    import argparse
    global BUILD
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir',type=Path,default=BUILD,
                        help='Build output directory (default: repository/build)')
    parser.add_argument('--original',type=Path,required=True,
                        help='Original unmodified EXE used to build the patch (read-only)')
    options=parser.parse_args()
    BUILD=options.build_dir.resolve();old.ROOT=BUILD
    reports=[]
    executable_digest=hashlib.sha256((BUILD/'Telegram.exact.exe').read_bytes()).hexdigest()
    payload_digest=hashlib.sha256((BUILD/'build'/'payload.exe').read_bytes()).hexdigest()
    for base in (0x140000000,0x7ff400000000):
        regression=Machine(base)
        legacy=old.suite(regression)
        assert not regression.heap_live and not regression.handles
        del regression
        machine=Machine(base)
        passed=suite(machine);passed.append(timer_patch_suite(machine,options.original.resolve()))
        reports.append({'base':hex(base),'passed':passed,'original_exact_search_regression':legacy})
        del machine
    assert executable_digest==hashlib.sha256((BUILD/'Telegram.exact.exe').read_bytes()).hexdigest(),'EXE changed during test'
    assert payload_digest==hashlib.sha256((BUILD/'build'/'payload.exe').read_bytes()).hexdigest(),'payload changed during test'
    report={'status':'passed','kind':'actual compiled Windows x64 under Unicorn with synthetic Qt/WinAPI',
            'executable_sha256':executable_digest,'payload_sha256':payload_digest,
            'bases':reports,'limits':['No real Telegram UI/account data used.','Native Qt/WinAPI callees are instrumented ABI stubs.']}
    (BUILD/'menu-payload-test-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
