"""Channel ID rules and startup storage: compiled x64, synthetic Qt/Windows ABI."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import test_menu_payload as f
from unicorn.x86_const import UC_X86_REG_RSI, UC_X86_REG_R14

CHANNEL = 2 << 48

def raw_channels(ids):
    return b'TGEXCH1\0'+struct.pack('<II',1,len(ids))+b''.join(
        struct.pack('<IQ24x',8,i) for i in ids)

def channel_path(m):
    return m.db_path.replace('blacklist.v1','channels.v1')

def peer(m,identifier,name='内容频道',broadcast=True):
    p=m.peer(name,kind=2)
    m.put(p+8,identifier);m.put(p+0x1a8,0x400 if broadcast else 0)
    return p

def bind(m,item,p):
    history=m.get(item+0x10)
    if not history:
        history=m.alloc(0x400);m.put(item+0x10,history)
    m.put(history+0x2d8,p)
    return item

def open_menu(m,inner,handle):
    m.actions.clear();m.destroy_connections()
    m.call('PatchMenuBridge',handle,extra={UC_X86_REG_RSI:inner})
    return {c['label']:c['slot'] for c in m.connections}

def clean(m):
    assert not m.heap_live and not m.handles and not m.task_paths

def suite(base):
    passed=[]
    m=f.Machine(base)
    for identifier,broadcast,wanted in [(CHANNEL+101,True,True),(CHANNEL+102,False,False),
                                         (101,True,False),((1<<48)+101,True,False)]:
        inner,handle,item,_=m.menu_scene()
        bind(m,item,peer(m,identifier,broadcast=broadcast))
        labels=open_menu(m,inner,handle)
        assert ('屏蔽整个频道' in labels)==wanted
        assert '屏蔽相同内容' in labels
        clean(m)
    m.destroy_connections()
    passed.append('broadcast-only menu eligibility; user/group IDs excluded; original content action retained')

    m.seed_blacklist(['另一条独立规则']);content=m.files[m.db_path]
    inner,handle,item,_=m.menu_scene()
    blocked_peer=peer(m,CHANNEL+200);bind(m,item,blocked_peer)
    m.u.mem_write(inner+0x621,b'\1')
    # menu_scene's preview sibling shares the selected history and different text.
    other=peer(m,CHANNEL+201)
    keep=m.item('内容相同频道名不同ID');bind(m,keep,other)
    keep_row=m.alloc(0x88);m.put(keep_row+0x60,keep)
    m.vector(m.values(inner+0x398)+[keep_row],inner+0x398)
    normal_keep=[x for x in m.row_items(inner,0x3c8) if x!=item]
    labels=open_menu(m,inner,handle);slot=labels['屏蔽整个频道']
    assert m.i32(slot+24)==4 and m.get(slot+36)==CHANNEL+200
    m.u.mem_write(inner+0x6a8,bytes(24))
    m.qstring('频道已经改名',blocked_peer+0x100)
    m.u.mem_write(inner+0xa40,b'\1\1')
    m.put(inner+0x1d0,m.values(inner+0x3c8)[0]);m.u.mem_write(inner+0x1da,b'\1')
    m.call('BlacklistSlotImpl',1,slot,inner,0,0)
    assert m.files[channel_path(m)]==raw_channels([CHANNEL+200])
    assert m.files[m.db_path]==content
    assert m.row_items(inner,0x3c8)==normal_keep and m.row_items(inner,0x398)==[keep]
    assert m.i32(inner+0x3e0)==len(normal_keep) and m.i32(inner+0x3b0)==1 and m.i32(inner+0x3e4)==0
    assert m.get(inner+0x1d0)==0 and bytes(m.u.mem_read(inner+0xa40,2))==b'\1\1'
    clean(m);m.destroy_connections()
    passed.append('queued stable ID survives menu clearing and rename; normal/preview variants removed; counts/selection/loading preserved; content bytes unchanged')

    for scope in (0,0x5e0):
        inner=m.inner('内容',scope)
        bad=[bind(m,m.item('内容'+str(i)+'🌸'*100),blocked_peer) for i in range(40)]
        user=peer(m,200)
        kept=[bind(m,m.item('内容同名频道'),other),bind(m,m.item('内容同裸ID用户'),user)]
        # A content blacklist remains effective in addition to channel blocking.
        duplicate=m.item('另一条独立规则')
        vector=m.vector(bad+kept+[duplicate]);begin=m.get(vector);capacity=m.get(vector+16)
        m.original_text_calls.clear();m.crypto_hash_calls=0
        m.call('PatchMessages',inner,vector,bad[0],4,900)
        assert m.receive_calls[-1][1]==kept and m.receive_calls[-1][2]==0
        assert not set(bad).intersection(m.original_text_calls)
        assert m.get(vector)==begin and m.get(vector+16)==capacity
        clean(m)
    passed.append('future/scoped pages and injected spam filtered by typed ID before text; 40 varying long messages; same-name other channel and same-bare-ID user survive')

    inner=m.inner('内容');result=m.alloc(0x50);m.qstring('内容',result)
    ps=[blocked_peer,other,peer(m,CHANNEL+999,name='不匹配')]
    m.qstring('内容改名',blocked_peer+0x100)
    m.vector(ps,result+8);m.vector(ps,result+0x20)
    sponsored=m.alloc(3*0x30);tokens=[]
    for i,p in enumerate(ps):
        m.put(sponsored+i*0x30,p)
        for j in range(1,6):m.put(sponsored+i*0x30+j*8,0xf000+i*16+j)
        tokens.append(bytes(m.u.mem_read(sponsored+i*0x30,0x30)))
    for off,value in [(0x38,sponsored),(0x40,sponsored+0x90),(0x48,sponsored+0x90)]:m.put(result+off,value)
    destroyed=[];received=[]
    m.native(0x5c5750,lambda a:destroyed.append(bytes(m.u.mem_read(a[0],0x30))))
    m.native(0x16449f0,lambda a:received.append((m.values(a[1]+8),m.values(a[1]+0x20))))
    m.call('PatchPeers',inner,result)
    assert received==[([other],[other])]
    assert bytes(m.u.mem_read(sponsored,0x30))==tokens[1] and sorted(destroyed)==sorted([tokens[0],tokens[2]])
    assert m.get(result+0x48)==sponsored+0x90
    listp=m.alloc(0x80);out=m.alloc(24);capture=m.alloc(16);m.put(capture+8,inner)
    rows=[m.row(m.entry('内容',p)) for p in ps[:2]];m.vector(rows,listp+0x30)
    m.call('PatchLocalBridge',listp,out,0,extra={UC_X86_REG_R14:capture})
    assert m.values(out)==rows[1:]
    clean(m)
    passed.append('remote/my/sponsored peer results and local History rows filtered; sponsored destructor ownership remains exact')

    persisted=dict(m.files);del m
    m=f.Machine(base);m.files.update(persisted)
    inner,handle,item,_=m.menu_scene()
    bind(m,item,peer(m,CHANNEL+201))
    labels=open_menu(m,inner,handle)
    m.call('BlacklistSlotImpl',1,labels['屏蔽整个频道'],inner,0,0)
    assert m.files[channel_path(m)]==raw_channels([CHANNEL+200,CHANNEL+201])
    inner,handle,item,_=m.menu_scene();labels=open_menu(m,inner,handle)
    assert '撤销上次频道屏蔽' in labels
    m.call('BlacklistSlotImpl',1,labels['撤销上次频道屏蔽'],inner,0,0)
    assert m.files[channel_path(m)]==raw_channels([CHANNEL+200])
    assert m.files[m.db_path]==content and m.research_calls==[inner]
    clean(m);m.destroy_connections()
    passed.append('new process loads persisted IDs; undo removes only most recent channel and repeats search; content DB remains unchanged')

    malformed=[b'bad',raw_channels([CHANNEL+1]).replace(b'TGEXCH1',b'TGEXBL1'),
               raw_channels([1]),raw_channels([CHANNEL]),raw_channels([CHANNEL+1])[:-1]+b'\1',
               b'TGEXCH1\0'+struct.pack('<II',1,50001)]
    for raw in malformed:
        m.files[channel_path(m)]=raw
        inner,handle,item,_=m.menu_scene();bind(m,item,peer(m,CHANNEL+1))
        labels=open_menu(m,inner,handle)
        assert '屏蔽整个频道' not in labels
        m.call('InitRuleStore')
        assert m.files[channel_path(m)]==raw
        clean(m)
    m.destroy_connections();del m
    passed.append('bad magic, truncated/oversized file, invalid typed IDs, nonzero reserved bytes rejected without overwrite')

    for mode in ('empty','migrate','existing','bad-legacy','denied','unicode'):
        m=f.Machine(base)
        if mode=='unicode':
            m.documents_path=r'D:\重定向文档🌸';m.directories={m.documents_path}
            m.db_path=m.documents_path+r'\Telegram\blacklists\exact-search-blacklist.v1.bin'
        legacy=m.final_module_path.rsplit('\\',1)[0]+r'\exact-search-blacklist.v1.bin'
        legacy_channel=legacy.replace('blacklist.v1','channels.v1')
        if mode in ('migrate','existing'):
            m.seed_blacklist(['旧规则🌸']);legacy_data=m.files.pop(m.db_path)
            m.files[legacy]=legacy_data;m.files[legacy_channel]=raw_channels([CHANNEL+456])
        if mode=='existing':m.files[m.db_path]=b'TGEXBL1\0'+struct.pack('<II',1,0)
        if mode=='bad-legacy':m.files[legacy]=b'bad legacy'
        if mode=='denied':m.reject_directory_prefix=m.documents_path
        native=[];m.native(0x5d828ac,lambda a:native.append(a[:4]))
        m.call('PatchStartupBridge',11,22,33,44)
        assert native==[[11,22,33,44]]
        if mode=='denied':assert not m.files
        elif mode=='bad-legacy':assert m.db_path not in m.files and m.files[legacy]==b'bad legacy'
        else:
            assert m.files[m.db_path]==(legacy_data if mode=='migrate' else b'TGEXBL1\0'+struct.pack('<II',1,0))
            assert m.files[channel_path(m)]==raw_channels([CHANNEL+456] if mode in ('migrate','existing') else [])
            before=dict(m.files);m.call('InitRuleStore');assert m.files==before
            if mode in ('migrate','existing'):assert m.files[legacy]==legacy_data
        clean(m);del m
    passed.append('startup bridge reaches native entry with arguments/stack/nonvolatile registers; clean/Unicode/redirected folder creation; legacy migration idempotent; existing/corrupt rules preserved; denied Documents does not block startup')
    return passed

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir',type=Path,required=True)
    parser.add_argument('--original',type=Path,required=True)
    args=parser.parse_args();f.BUILD=args.build_dir.resolve();f.old.ROOT=f.BUILD
    with f.old.pefile.PE(str(args.original),fast_load=True) as original, f.old.pefile.PE(str(f.BUILD/'Telegram.exact.exe'),fast_load=True) as patched:
        assert original.get_data(0x8e348c4,1)==b'\1' and patched.get_data(0x8e348c4,1)==b'\0'
        for rva,size in [(0x12b71b5,14),(0x12b9679,7),(0x29c7bc6,6)]:
            assert original.get_data(rva,size)==patched.get_data(rva,size)
    report={'status':'passed','kind':'compiled Windows x64 under Unicorn; synthetic Qt/Windows ABI',
            'sha256':hashlib.sha256((f.BUILD/'Telegram.exact.exe').read_bytes()).hexdigest(),
            'default_updates':'false; native gate, enable setter and saved preference parser unchanged',
            'bases':[{'base':hex(base),'passed':suite(base)} for base in (0x140000000,0x7ff400000000)],
            'limits':['No real Telegram account/network/menu click in this suite.']}
    (f.BUILD/'channel-test-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
