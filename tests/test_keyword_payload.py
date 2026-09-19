"""Compiled x64 keyword storage, filtering, captured prompt and widget lifetime."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import test_menu_payload as f
from test_channel_payload import CHANNEL, peer, bind, open_menu, clean, channel_path, raw_channels

def record(value,scope=1):
    raw=value.encode('utf-16-le')
    return struct.pack('<II',scope,len(raw)//2)+raw+bytes(256-len(raw))

def pointer(m,raw):
    p=m.alloc(len(raw));m.u.mem_write(p,raw);return p

def path(m):return m.db_path.replace('blacklist.v1','keywords.v1')
def file(*rules):return b'TGEXKW1\0'+struct.pack('<II',1,len(rules))+b''.join(rules)
def change(m,op,value,scope=1):return m.call('KeywordChange',op,pointer(m,record(value,scope)))

def suite(base):
    passed=[];m=f.Machine(base)
    a=record('固定广告🌹');b=record('校园推广',2)
    assert m.call('KeywordChange',0,0)==1 and m.files[path(m)]==file()
    assert change(m,1,'固定广告🌹')==1 and change(m,1,'校园推广',2)==1
    before=m.files[path(m)]
    assert before==file(a,b) and change(m,1,'固定广告🌹')==0
    assert change(m,2,'不存在')==0 and m.files[path(m)]==before
    assert change(m,2,'固定广告🌹')==1 and m.files[path(m)]==file(b)
    assert change(m,1,'固定广告🌹')==1
    clean(m)
    passed.append('atomic bootstrap/add/deduplicate/delete, typed UTF-16 rules, other records preserved')

    # Different channel IDs, variable prose, preview and injected pages; users
    # and groups containing the same word are deliberately outside rule scope.
    for scoped in (0,0x5e0):
        inner=m.inner('消息',scoped)
        blocked=[bind(m,m.item('消息 固定广告🌹 随机正文 '+str(i)),peer(m,CHANNEL+100+i)) for i in range(90)]
        blocked.append(bind(m,m.item('消息 任意正文'),peer(m,CHANNEL+1000,'校园推广第二站')))
        kept=[bind(m,m.item('消息 固定广告 普通花'),peer(m,CHANNEL+500)),
              bind(m,m.item('消息 固定广告🌹'),peer(m,505)),
              bind(m,m.item('消息 固定广告🌹'),peer(m,CHANNEL+501,broadcast=False))]
        vector=m.vector(blocked+kept)
        m.call('PatchMessages',inner,vector,blocked[0],4,9999)
        assert m.receive_calls[-1][1]==kept and m.receive_calls[-1][2]==0
        assert m.i32(inner+0x3e0)==3
        clean(m)
    passed.append('91 different broadcast channels filtered across global/scoped/injected pages; changed filler irrelevant; nonmatching messages/private users/groups survive')

    inner,handle,item,_=m.menu_scene();bind(m,item,peer(m,CHANNEL+888))
    m.qstring('固定广告🌹 changed',item+0x30)
    m.call('RefreshBlocked',inner)
    assert item not in m.row_items(inner,0x3c8)
    clean(m)
    passed.append('newly added keyword removes already loaded search rows')

    # Channel-name rules also remove global peer results, preserving ownership.
    inner=m.inner('校园');result=m.alloc(0x50);m.qstring('校园',result)
    bad=peer(m,CHANNEL+77,'校园推广');good=peer(m,CHANNEL+78,'校园新闻')
    user=peer(m,79,'校园推广');group=peer(m,CHANNEL+80,'校园推广',broadcast=False)
    m.vector([bad,good,user,group],result+8);m.vector([bad,good],result+0x20)
    seen=[];m.native(0x16449f0,lambda x:seen.append((m.values(x[1]+8),m.values(x[1]+0x20))))
    m.call('PatchPeers',inner,result)
    assert seen==[([good,user,group],[good])]
    clean(m)
    passed.append('channel-name keyword filters remote/my peers without affecting user or group names')

    # Literal semantics: no regex, token splitting, case folding or empty match.
    m.files[path(m)]=file(record('Ab c.*'))
    inner=m.inner('消息')
    values=['消息 Ab c.*','消息 ab c.*','消息 Ab xx cZZ','消息 Abc.*']
    items=[bind(m,m.item(v),peer(m,CHANNEL+3000+i)) for i,v in enumerate(values)]
    m.call('PatchMessages',inner,m.vector(items),0,4,4)
    assert m.receive_calls[-1][1]==items[1:]
    for invalid in [record(''),record('   '),record('词',9),record('\u200b'),record('\n')]:
        assert m.call('KeywordChange',1,pointer(m,invalid))&0xffffffff==0xfffffffe
    before=m.files[path(m)]
    bad=struct.pack('<II',1,1)+b'\x00\xd8'+bytes(254)
    assert m.call('KeywordChange',1,pointer(m,bad))&0xffffffff==0xfffffffe
    assert m.files[path(m)]==before
    passed.append('literal matching; invalid/empty/invisible/surrogate/control/scope records rejected')

    for corrupt in [b'bad',file(record('有效词'))[:-1],file(record('有效词'))+b'x',
                    b'TGEXKW1\0'+struct.pack('<II',1,257),file(bad),file(record('有效词')).replace(b'KW1',b'KW2')]:
        m.files[path(m)]=corrupt
        assert change(m,1,'新关键词')&0xffffffff==0xffffffff
        assert m.files[path(m)]==corrupt
        inner=m.inner('消息');i=bind(m,m.item('消息 有效词'),peer(m,CHANNEL+10))
        m.call('PatchMessages',inner,m.vector([i]),0,4,1)
        assert m.receive_calls[-1][1]==[i]
        clean(m)
    m.files[path(m)]=file(*[record('规则'+str(i)) for i in range(256)])
    assert change(m,1,'超出容量')&0xffffffff==0xfffffffd
    assert change(m,2,'规则120')==1 and change(m,1,'恢复可用')==1
    before=m.files[path(m)];m.reject_new_prefix=path(m)+'.tmp.'
    assert change(m,2,'恢复可用')&0xffffffff==0xffffffff and m.files[path(m)]==before
    assert not any('.tmp.' in p for p in m.files)
    clean(m)
    passed.append('malformed/oversized/versioned databases fail open without overwrite; rule cap; temp-write failure atomic')

    m.reject_new_prefix=None
    m.files[path(m)]=file(record('A'*127+'B'))
    inner=m.inner('消息')
    items=[bind(m,m.item('消息'+'A'*12000+ending),peer(m,CHANNEL+7000+i)) for i,ending in enumerate(('C','B'))]
    m.call('PatchMessages',inner,m.vector(items),0,4,2)
    assert m.receive_calls[-1][1]==items[:1]
    clean(m)
    passed.append('128-unit near-repeat keyword against 12000-unit adversarial body uses linear matching, with positive/negative cases')

    # Suggestions quote source lines and remain independent of live FakeRows.
    m.reject_new_prefix=None;m.files[path(m)]=file()
    value='一段每次变化的普通句子\n✅禁秘固定广告🌹\n✅禁秘固定广告🌹\n另一个句子'
    raw=value.encode('utf-16-le');out=m.alloc(258)
    m.call('KeywordSuggest',pointer(m,raw),len(raw)//2,out)
    assert m.wide(out)=='✅禁秘固定广告🌹'
    m.call('KeywordSuggest',pointer(m,('字'*140).encode('utf-16-le')),140,out)
    assert m.wide(out)==''
    inner,handle,item,_=m.menu_scene(value=value);bind(m,item,peer(m,CHANNEL+8888))
    labels=open_menu(m,inner,handle)
    assert '添加关键词屏蔽…' in labels and '管理关键词屏蔽…' in labels
    prompt=[]
    show=m.exports['ShowKeywordDialog'];m.native(show-base,lambda a:prompt.append((a[0],m.wide(a[1]))) or 0)
    # Clear menu and change original text after capturing the action.
    m.u.mem_write(inner+0x6a8,bytes(24));m.qstring('已经改变',item+0x30)
    m.call('BlacklistSlotImpl',1,labels['屏蔽整个频道'],inner,0,0)
    assert prompt==[(1,'✅禁秘固定广告🌹')]
    assert m.files[channel_path(m)]==raw_channels([CHANNEL+8888])
    assert m.files[path(m)]==file() # skipping does not create a keyword
    assert len(m.guard_connections)==1
    m.call('BlacklistSlotImpl',1,labels['管理关键词屏蔽…'],inner,0,0)
    assert len(m.guard_connections)==1 and prompt[-1][0]==3
    m.destroy_connections();clean(m)
    passed.append('channel commit before optional prompt; copied suggestion survives menu/message change; skipping saves no keyword; manager reachable; guard reused and destroyed')

    # Native trampoline simulates QObject destruction inside the dialog's nested
    # message loop. A changed dialog result must not touch the destroyed widget.
    inner,handle,item,_=m.menu_scene();bind(m,item,peer(m,CHANNEL+9999))
    labels=open_menu(m,inner,handle)
    original_connect=m.connect
    def connect(args):
        r=original_connect(args)
        if m.get(args[2])==base+0x5974e60:
            slot=args[5]
            code=b'\x48\x83\xec\x28\xb9\x01\0\0\0\x48\xba'+struct.pack('<Q',slot)
            code+=b'\x45\x31\xc0\x45\x31\xc9\x48\xc7\x44\x24\x20\0\0\0\0\x48\xb8'+struct.pack('<Q',m.exports['RuleGuardImpl'])
            code+=b'\xff\xd0\x48\x83\xc4\x28\xb8\x01\0\0\0\xc3'
            m.u.mem_write(show,code);m.u.ctl_remove_cache(show,show+len(code));m.handlers.pop(show,None)
        return r
    m.native(0x5973af0,connect);m.receive_calls.clear()
    m.call('BlacklistSlotImpl',1,labels['屏蔽整个频道'],inner,0,0)
    assert len(m.receive_calls)==1, (m.receive_calls, [(hex(x[0]),x[1]) for x in m.events if x[0] in (show-base,0x5973af0)],m.guard_connections) # channel refresh only
    m.destroy_connections();clean(m)
    passed.append('actual x64 guard callback during modal dialog prevents post-destruction refresh/use-after-free')
    return passed

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build-dir',type=Path,required=True)
    a=p.parse_args();f.BUILD=a.build_dir.resolve();f.old.ROOT=f.BUILD
    report={'status':'passed','kind':'compiled x64 under Unicorn; synthetic Telegram/Windows objects',
            'sha256':hashlib.sha256((f.BUILD/'Telegram.exact.exe').read_bytes()).hexdigest(),
            'bases':[{'base':hex(b),'passed':suite(b)} for b in (0x140000000,0x7ff400000000)]}
    (f.BUILD/'keyword-test-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
