"""Compiled selection snapshots, atomic batches and queued menu integration."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import test_menu_payload as f
from test_channel_payload import CHANNEL,peer,bind,open_menu,clean,channel_path,raw_channels

def buffer(m,raw):
    p=m.alloc(len(raw));m.u.mem_write(p,raw);return p
def batch(m,ids):return m.call('ChannelBatch',buffer(m,struct.pack('<'+'Q'*len(ids),*ids)),len(ids))&0xffffffff
def row(m,item):
    p=m.alloc(0x88);m.put(p+0x60,item);return p

def suite(base):
    m=f.Machine(base);passed=[]
    ids=[CHANNEL+i for i in range(1,1001)]
    assert batch(m,ids)==1 and m.files[channel_path(m)]==raw_channels(ids)
    assert batch(m,ids+ids[:90])==0
    assert batch(m,[ids[-1],CHANNEL+1001,CHANNEL+1001])==1
    assert m.files[channel_path(m)]==raw_channels(ids+[CHANNEL+1001])
    before=m.files[channel_path(m)]
    assert batch(m,[CHANNEL+2000,0])==0xfffffffe and m.files[channel_path(m)]==before
    assert m.call('ChannelBatch',0,1)&0xffffffff==0xfffffffe
    assert m.call('ChannelBatch',1,50001)&0xffffffff==0xfffffffe
    m.reject_new_prefix=channel_path(m)+'.tmp.'
    assert batch(m,[CHANNEL+2001,CHANNEL+2002])==0xffffffff and m.files[channel_path(m)]==before
    assert not any('.tmp.' in p for p in m.files)
    clean(m);passed.append('1000-channel atomic batch; union deduplication/order; invalid late ID and failed save leave every original byte unchanged; no partial commit')
    m.reject_new_prefix=None;m.files[channel_path(m)]=b'corrupt'
    assert batch(m,[CHANNEL+2001])==0xffffffff and m.files[channel_path(m)]==b'corrupt'
    clean(m);passed.append('corrupt existing channel database is not overwritten')

    # Snapshot owns its text and ID. Repeated rows collapse by stable ID, while
    # equally named distinct channels remain individually selectable.
    inner=m.inner('内容');p=peer(m,CHANNEL+71,'同名频道')
    p2=peer(m,CHANNEL+72,'同名频道');group=peer(m,CHANNEL+73,broadcast=False);user=peer(m,74)
    items=[bind(m,m.item('固定广告第一条'),p),bind(m,m.item('换了正文的第二条'),p),
           bind(m,m.item('另一个频道'),p2),bind(m,m.item('普通群组'),group),bind(m,m.item('普通用户'),user)]
    m.vector([row(m,i) for i in items],inner+0x3c8)
    m.vector([row(m,bind(m,m.item('预览第三条'),p))],inner+0x398)
    state=m.alloc(632);assert m.call('SelectionSnapshot',inner,state)==1
    rows=m.get(state+304);assert m.i32(state+312)==2
    assert m.get(rows)==CHANNEL+71 and m.i32(rows+8)==3
    assert m.get(rows+600)==CHANNEL+72 and m.i32(rows+608)==1
    assert m.wide(rows+16)==m.wide(rows+616)=='同名频道'
    assert m.wide(rows+338)=='固定广告第一条'
    m.qstring('原始名称已改变',p+0x100);m.qstring('原始内容已改变',items[0]+0x30)
    m.u.mem_write(inner+0x3c8,bytes(24));m.u.mem_write(inner+0x398,bytes(24))
    assert m.wide(rows+16)=='同名频道' and m.wide(rows+338)=='固定广告第一条'
    assert list(m.heap_live)==[rows];m.handlers[m.get(base+0x6000358)]([0x4444,0,rows]);clean(m)
    passed.append('normal/preview snapshot merges same ID, retains equal-name distinct IDs, excludes users/groups; copied ID/name/sample survive source mutation')

    # A confirmed selection is followed by the optional keyword prompt. Cancel
    # has neither a refresh nor a keyword prompt. Call boundaries retain guard.
    m.files.clear();inner,handle,item,_=m.menu_scene();bind(m,item,peer(m,CHANNEL+88))
    labels=open_menu(m,inner,handle);assert '进入多选屏蔽…' in labels
    selection=m.exports['ShowSelectionDialog'];prompt=m.exports['ShowKeywordDialog'];seen=[]
    m.native(selection-base,lambda a:0)
    m.native(prompt-base,lambda a:seen.append((a[0],m.wide(a[1]))) or 0)
    m.call('BlacklistSlotImpl',1,labels['进入多选屏蔽…'],inner,0,0)
    assert seen==[] and m.receive_calls==[]
    def confirm(a):
        m.u.mem_write(a[1],'共同广告特征\0'.encode('utf-16-le'));return 1
    m.native(selection-base,confirm)
    m.call('BlacklistSlotImpl',1,labels['进入多选屏蔽…'],inner,0,0)
    assert seen==[(1,'共同广告特征')] and len(m.receive_calls)==1
    assert len(m.guard_connections)==1;m.destroy_connections();clean(m)
    passed.append('queued multi-select menu action; cancel has no side effects; confirm refreshes then opens editable keyword prompt with owned text')
    return passed

def main():
    p=argparse.ArgumentParser();p.add_argument('--build-dir',type=Path,required=True);a=p.parse_args()
    f.BUILD=a.build_dir.resolve();f.old.ROOT=f.BUILD
    report={'status':'passed','kind':'compiled x64 with synthetic Qt/WinAPI',
            'sha256':hashlib.sha256((f.BUILD/'Telegram.exact.exe').read_bytes()).hexdigest(),
            'bases':[{'base':hex(b),'passed':suite(b)} for b in (0x140000000,0x7ff400000000)]}
    (f.BUILD/'selection-test-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
