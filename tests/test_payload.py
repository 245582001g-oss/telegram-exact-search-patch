"""Execute compiled Windows x64 payload with synthetic Telegram objects.

Original ABI callees are instrumented stubs, not a live account or network.
This tests the emitted instructions, calling convention, container ownership,
and ASLR independently of a native application startup/search smoke test.
"""
from pathlib import Path
import argparse, json, struct
import pefile
ROOT=Path(__file__).resolve().parent.parent/'build'
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn.x86_const import *
P=lambda n:struct.pack('<Q',n)
REGS=[UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8,UC_X86_REG_R9]
SAVED=[UC_X86_REG_RBX,UC_X86_REG_RBP,UC_X86_REG_RSI,UC_X86_REG_RDI,
       UC_X86_REG_R12,UC_X86_REG_R13,UC_X86_REG_R14,UC_X86_REG_R15]

class Machine:
    def __init__(self,exe,base):
        self.base=base
        pe=pefile.PE(str(exe),fast_load=True)
        self.u=Uc(UC_ARCH_X86,UC_MODE_64)
        self.pages=set()
        for section in pe.sections:
            if section.Name.rstrip(b'\0')==b'.exact':
                self.map(base+section.VirtualAddress,max(section.Misc_VirtualSize,section.SizeOfRawData))
                self.u.mem_write(base+section.VirtualAddress,section.get_data())
        # Payload exports are read from separately linked file to avoid altering
        # the original client's public export table in the deliverable.
        payload=pefile.PE(str(ROOT/'build'/'payload.exe'))
        self.exports={s.name.decode():base+s.address for s in payload.DIRECTORY_ENTRY_EXPORT.symbols if s.name}
        self.data=0x600000000
        self.map(self.data,0x800000)
        self.cursor=self.data
        self.stack=0x700000000
        self.map(self.stack,0x10000)
        self.stop=base+0x1000
        self.map(self.stop,0x1000)
        self.handlers={}
        self.events=[]
        for rva in [0x1c88390,0x149b950,0x163a810,0x163af50,0x5c0750,0x161eb20,0x4a3690,0x1100,
                    0x3afad60,0x7331a0,0x7330c0]:
            self.map(base+rva,1)
        self.u.hook_add(UC_HOOK_CODE,self.hook)
        self.handlers[base+0x1c88390]=lambda a:a[0]+0x30
        self.handlers[base+0x149b950]=lambda a:a[0]+0x100
        self.handlers[base+0x1100]=lambda a:a[0]+0x120
        self.handlers[base+0x4a3690]=lambda a:self.alloc(a[0]) if a[0] else 0
    def map(self,addr,size):
        for page in range(addr&~4095,(addr+size+4095)&~4095,4096):
            if page not in self.pages:
                self.u.mem_map(page,4096); self.pages.add(page)
    def alloc(self,n):
        p=self.cursor; self.cursor=(p+max(n,1)+15)&~15
        assert self.cursor<self.data+0x800000
        self.u.mem_write(p,bytes(max(n,1)))
        return p
    def put(self,p,n): self.u.mem_write(p,P(n))
    def get(self,p): return struct.unpack('<Q',self.u.mem_read(p,8))[0]
    def i32(self,p): return struct.unpack('<i',self.u.mem_read(p,4))[0]
    def qstring(self,value,target=None):
        raw=value.encode('utf-16-le')
        d=self.alloc(24+len(raw)+2)
        self.u.mem_write(d,struct.pack('<iii4xq',-1,len(raw)//2,0,24)+raw+b'\0\0')
        q=target or self.alloc(8); self.put(q,d)
        return q
    def inner(self,query,scope=0):
        p=self.alloc(0xb00); self.qstring(query,p+0x618)
        if scope:self.put(p+scope,0x1234)
        return p
    def vector(self,values,where=None,padding=2):
        v=where or self.alloc(24)
        b=self.alloc((len(values)+padding)*8)
        for i,x in enumerate(values):self.put(b+i*8,x)
        self.put(v,b);self.put(v+8,b+len(values)*8);self.put(v+16,b+(len(values)+padding)*8)
        return v
    def values(self,v):return [self.get(p) for p in range(self.get(v),self.get(v+8),8)]
    def item(self,value):
        p=self.alloc(0x100); self.qstring(value,p+0x30);return p
    def peer(self,name,aliases=(),kind=0):
        p=self.alloc(0x400);self.u.mem_write(p+0xe,bytes([kind]));self.qstring(name,p+0x100)
        offset=0x1d8 if kind==0 else 0x228 if kind==2 else None
        if offset:
            b=self.alloc(len(aliases)*8)
            for i,value in enumerate(aliases):self.qstring(value,b+i*8)
            self.put(p+offset,b);self.put(p+offset+8,b+len(aliases)*8)
        return p
    def entry(self,name,peer=None):
        p=self.alloc(0x400);v=self.alloc(0x80);self.put(p,v);self.put(v+0x48,self.base+0x1100)
        self.qstring(name,p+0x120)
        if peer:self.put(p+0x2d8,peer);self.u.mem_write(p+0x104,struct.pack('<I',2))
        return p
    def row(self,entry):p=self.alloc(0x100);self.put(p+0x60,entry);return p
    def hook(self,u,addr,size,data):
        if addr==self.stop:u.emu_stop();return
        handler=self.handlers.get(addr)
        if handler is not None:
            rsp=u.reg_read(UC_X86_REG_RSP)
            assert rsp%16==8,('native call stack misaligned',hex(addr),hex(rsp))
            args=[u.reg_read(r) for r in REGS]+[self.get(rsp+0x28)]
            self.events.append((addr-self.base,args))
            value=handler(args)
            u.reg_write(UC_X86_REG_RAX,0 if value is None else value)
            u.reg_write(UC_X86_REG_RIP,self.get(rsp));u.reg_write(UC_X86_REG_RSP,rsp+8)
    def call(self,name,*args,extra=None):
        self.events=[]
        rsp=self.stack+0xf008
        self.put(rsp,self.stop)
        for i,value in enumerate(args):
            if i<4:self.u.reg_write(REGS[i],value)
            else:self.put(rsp+0x28+8*(i-4),value)
        expected={r:0x1230000+i for i,r in enumerate(SAVED)}
        if extra:expected.update(extra)
        for r,value in expected.items():self.u.reg_write(r,value)
        self.u.reg_write(UC_X86_REG_RSP,rsp)
        self.u.emu_start(self.exports[name],self.stop,timeout=5_000_000,count=5_000_000)
        assert self.u.reg_read(UC_X86_REG_RIP)==self.stop, 'did not return'
        assert self.u.reg_read(UC_X86_REG_RSP)==rsp+8, 'stack ownership'
        for r,value in expected.items():assert self.u.reg_read(r)==value,('nonvolatile register',r)
        return self.u.reg_read(UC_X86_REG_RAX)

def suite(m):
    passed=[]
    cases=[('美丽的风景','美丽'),('美好','美丽'),('好人一生平安','好人'),('好的','好人'),
           ('丽美','美丽'),('美 丽','美丽'),('美丽','美 丽'),('xxAByy','AB'),('xxAByy','ab'),
           (' foo ',' foo '),('foo',' foo '),('é','e\u0301'),('美麗','美丽'),
           ('🌸美丽🌸','🌸美丽'),('美丽',''),('','美丽'),('a'*100+'b','a'*32+'b'),
           ('生活很美好','美好'),('美好的一天','美好'),('美 好','美好'),
           ('美\n好','美好'),('第一行\n生活很美好\n第三行','美好'),('美丽','美好')]
    for hay,needle in cases:
        assert bool(m.call('ExactContains',m.qstring(hay),m.qstring(needle)))==(needle in hay),(hay,needle)
    passed.append(f'literal UTF-16: {len(cases)} cases')
    items=[m.item(s) for s in ['美好','很美丽','美 丽','美丽']]
    for scope in [0,0x5e0,0x98,0xb8]:
        inner=m.inner('美丽',scope);v=m.vector(items);old_begin=m.get(v);old_cap=m.get(v+16)
        injected=m.item('美好');captured={}
        def receive(args):
            captured.update(items=m.values(args[1]),inject=args[2],type=args[3]&255,count=args[4]&0xffffffff)
            assert m.get(v)==old_begin and m.get(v+16)==old_cap
            m.vector(captured['items'],inner+0x3c8)
        m.handlers[m.base+0x163a810]=receive
        m.call('PatchMessages',inner,v,injected,4,999)
        assert captured['items']==([items[1],items[3]] if not scope else items)
        assert captured['inject']==(injected if scope else 0)
        assert captured['type']==4
        assert captured['count']==(999 if scope else 2)
        if not scope:assert m.i32(inner+0x3e0)==2
    passed.append('message compaction, injected mismatch, scoped passthrough, allocation ownership')
    inner=m.inner('好人');v=m.vector([m.item('好的')]);captured={}
    m.handlers[m.base+0x163a810]=lambda a:captured.update(items=m.values(a[1]),count=a[4])
    m.call('PatchMessages',inner,v,0,4,100)
    assert captured=={'items':[],'count':0}
    passed.append('empty filtered message page reaches original receiver')
    inner=m.inner('美丽');result=m.alloc(0x50);m.qstring('美丽',result)
    peers=[m.peer('美好'),m.peer('美丽频道',kind=2),m.peer('other',['a美丽b']),m.peer('美 丽')]
    m.vector(peers,result+8);m.vector(peers,result+0x20)
    sponsored=m.alloc(0x30*4)
    tokens=[]
    for i,p in enumerate(peers):
        m.put(sponsored+i*0x30,p)
        for j in range(1,6):m.put(sponsored+i*0x30+j*8,0xf000+i*16+j)
        tokens.append(bytes(m.u.mem_read(sponsored+i*0x30,0x30)))
    m.put(result+0x38,sponsored);m.put(result+0x40,sponsored+0xc0);m.put(result+0x48,sponsored+0xc0)
    destroyed=[];seen={}
    m.handlers[m.base+0x5c0750]=lambda a:destroyed.append(bytes(m.u.mem_read(a[0],0x30)))
    def peers_receive(a):
        seen['my']=m.values(a[1]+8);seen['peers']=m.values(a[1]+0x20)
        seen['sponsored']=[bytes(m.u.mem_read(p,0x30)) for p in range(m.get(result+0x38),m.get(result+0x40),0x30)]
    m.handlers[m.base+0x163af50]=peers_receive
    m.call('PatchPeers',inner,result)
    assert seen['my']==seen['peers']==peers[1:3]
    assert seen['sponsored']==tokens[1:3]
    assert sorted(destroyed)==sorted([tokens[0],tokens[3]])
    assert m.get(result+0x48)==sponsored+0xc0
    passed.append('peers, aliases, channels, sponsored stable ownership partition')
    for query in ['美丽','@exact','美 丽']:
        inner=m.inner(query);listp=m.alloc(0x80)
        names=['美好','很美丽','美 丽','other']
        aliaspeer=m.peer('other',['exact'])
        rows=[m.row(m.entry(s,aliaspeer if i==3 else None)) for i,s in enumerate(names)]
        m.vector(rows,listp+0x30);out=m.alloc(24)
        capture=m.alloc(16);m.put(capture+8,inner)
        m.call('PatchLocalBridge',listp,out,0,extra={UC_X86_REG_R14:capture})
        expected=[rows[i] for i,s in enumerate(names) if query in s or (i==3 and query in '@exact')]
        assert m.values(out)==expected
        assert m.get(out+8)==m.get(out+16)
    passed.append('local full-list scan, interior match, aliases, original Row pointers, assembly capture bridge')
    inner=m.inner('美丽',0x98);seen={}
    m.handlers[m.base+0x161eb20]=lambda a:seen.update(args=a[:3]) or a[1]
    values=[m.alloc(0x80),m.alloc(24),m.alloc(8)]
    assert m.call('PatchLocal',*values,inner)==values[1]
    assert seen['args']==values
    passed.append('local scoped native ABI passthrough')
    for query in ['美 丽','AB',' ab ','!',' ','美丽']:
        inner=m.inner(query);raw=inner+0x618;out=m.alloc(8);seen=[]
        m.handlers[m.base+0x7331a0]=lambda a:seen.append(('construct',a[0])) or a[0]
        m.handlers[m.base+0x7330c0]=lambda a:seen.append(('append',a[0],a[1]))
        for name,reg in [('PatchApplyWordsBridge',UC_X86_REG_RSI),('PatchRefreshWordsBridge',UC_X86_REG_R15)]:
            seen.clear()
            assert m.call(name,out,raw,0,extra={reg:inner})==out
            assert seen==[('construct',out),('append',out,raw)]
    inner=m.inner('');out=m.alloc(8);seen=[]
    m.handlers[m.base+0x3afad60]=lambda a:seen.append(a[:3]) or a[0]
    assert m.call('PatchWords',out,inner+0x618,0,inner)==out
    assert seen==[[out,inner+0x618,0]]
    passed.append('query preparation retains whole raw string including punctuation/space/case; empty native fallback')
    return passed

def main():
    global ROOT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir',type=Path,default=ROOT,
                        help='Build output directory (default: repository/build)')
    options=parser.parse_args()
    ROOT=options.build_dir.resolve()
    # Current payload includes blacklist WinAPI calls. Reuse the expanded,
    # entirely synthetic ABI fixtures when running the original search suite.
    import test_menu_payload as fixtures
    fixtures.BUILD=ROOT
    fixtures.old.ROOT=ROOT
    reports=[]
    for base in [0x140000000,0x7ff400000000]:
        m=fixtures.Machine(base)
        reports.append({'image_base':hex(base),'passed':suite(m)})
        assert not m.heap_live and not m.handles
        del m
    report={'status':'passed','type':'actual compiled x64 payload under Unicorn; native callees instrumented',
            'bases':reports,'limits':['Not a real Telegram GUI/network search test.','Native callee implementations are instrumented ABI stubs.']}
    (ROOT/'payload-test-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
