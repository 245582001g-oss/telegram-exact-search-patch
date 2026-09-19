/* Native Qt5 QAction/QSlotObject bridge. Context-bound queued connections
 * protect InnerWidget lifetime and allow the popup to close before rebuilding. */
typedef struct BlacklistSlot BlacklistSlot;
typedef void (*SlotImpl)(int,BlacklistSlot *,void *,void **,u8 *);
struct BlacklistSlot {
    int reference_count;
    unsigned int padding;
    SlotImpl implementation;
    void *inner;
    int operation;
    unsigned int reserved;
    BlockKey key;
    u16 suggestion[KW_CAP+1];
};
_Static_assert(sizeof(BlacklistSlot)==328,"Qt slot capture layout");
#include "rule_ui.h"
#include "selection.h"
/* Match the native popup's QObject::destroyed self-connection ABI. A direct
 * heap-owned guard outlives modal message loops without retaining a stack or
 * widget pointer after destruction. Reused for repeated dialogs on one widget. */
typedef struct { int refs,padding; SlotImpl impl; void *inner; uptr epoch; } RuleGuard;
static void *guarded_inner;
static uptr guard_epoch;
EXPORT void RuleGuardImpl(int which,BlacklistSlot *raw,void *receiver,void **args,u8 *equal) {
    (void)receiver; (void)args;
    RuleGuard *slot=(RuleGuard *)raw;
    if(which==0 || which==1) {
        if(guarded_inner==slot->inner && guard_epoch==slot->epoch) guarded_inner=0;
        if(which==0) {
            typedef void (*Free)(void *,uptr);
            FN(0x5b6e670,Free)(slot,sizeof(*slot));
        }
    } else if(which==2 && equal) *equal=0;
}
static uptr guard_inner(void *inner) {
    if(guarded_inner==inner) return guard_epoch;
    typedef void *(*Allocate)(uptr);
    typedef void *(*Connect)(void *,void *,const void *,void *,void *,void *,int,const void *,const void *);
    typedef void (*Destroy)(void *);
    RuleGuard *slot=(RuleGuard *)FN(0x5d819cc,Allocate)(sizeof(RuleGuard));
    slot->refs=1; slot->padding=0; slot->impl=RuleGuardImpl; slot->inner=inner;
    slot->epoch=++guard_epoch; guarded_inner=0;
    uptr signal=base()+0x5974e60; void *connection=0;
    FN(0x5973af0,Connect)(&connection,inner,&signal,inner,0,slot,1,0,(void *)(base()+0x6624120));
    int ok=connection!=0;
    FN(0x59714e0,Destroy)(&connection);
    if(ok) { guarded_inner=inner; return guard_epoch; }
    return 0;
}

static void operation_error(void) {
    typedef void *(*GetModule)(const u16 *);
    typedef void *(*GetProc)(void *,const char *);
    typedef int (*MessageBox)(void *,const u16 *,const u16 *,unsigned int);
    GetModule module=AT((void *)base(),0x6000140,GetModule);
    GetProc proc=AT((void *)base(),0x60001b8,GetProc);
    void *user32=module(u"user32.dll");
    if (!user32) return;
    MessageBox message=(MessageBox)proc(user32,"MessageBoxW");
    if (message) message(0,u"无法保存搜索屏蔽规则，本次操作没有生效。请检查我的文档中的 Telegram 文件夹是否可写，以及规则文件是否完整。",
                         u"搜索屏蔽",0x10);
}

static PtrVector snapshot_survivors(void *inner,unsigned int vector_offset,BlockDb *blocked,BlockDb *channels,KeywordDb *keywords) {
    typedef const void *(*OriginalText)(void *);
    typedef void *(*Allocate)(uptr);
    void **begin=AT(inner,vector_offset,void **);
    void **end=AT(inner,vector_offset+8,void **);
    PtrVector result={0,0,0};
    uptr capacity=(uptr)(end-begin);
    if (!capacity) return result;
    result.begin=(void **)FN(0x4a8690,Allocate)(capacity*8);
    result.end=result.begin;
    result.capacity=result.begin+capacity;
    for (void **p=begin;p!=end;++p) {
        void *item=AT(*p,0x60,void *);
        if (!ch_contains_item(channels,item)
            && !kw_item(keywords,item)
            && (!blocked->valid || !blocked->count
                || !bl_contains(blocked,text(FN(0x1c95050,OriginalText)(item)))))
            *result.end++=item;
    }
    return result;
}

EXPORT void RefreshBlocked(void *inner) {
    typedef void (*Receive)(void *,PtrVector *,void *,unsigned char,int);
    typedef void (*SetPressed)(void *,int);
    typedef void (*ClearMouse)(void *,unsigned char);
    typedef void (*Refresh)(void *,unsigned char);
    if (AT(inner,0x4b0,int)!=1) return;
    BlockDb blocked,channels;
    bl_open(&blocked);
    ch_open(&channels);
    KeywordDb keywords; kw_open(&keywords);
    if (!blocked.valid && !channels.valid && !keywords.valid) { bl_close(&blocked); bl_close(&channels); kw_close(&keywords); return; }
    /* Snapshot both before either native receive can destroy old FakeRows. */
    PtrVector normal=snapshot_survivors(inner,0x3c8,&blocked,&channels,&keywords);
    int preview_mode=AT(inner,0x621,u8)!=0;
    PtrVector preview={0,0,0};
    if (preview_mode) preview=snapshot_survivors(inner,0x398,&blocked,&channels,&keywords);
    bl_close(&blocked);
    bl_close(&channels);
    kw_close(&keywords);
    u16 loading=AT(inner,0xa40,u16);
    FN(0x163b1e0,SetPressed)(inner,-1);
    FN(0x163b170,SetPressed)(inner,-1);
    FN(0x16474b0,ClearMouse)(inner,1);
    AT(inner,0x1d0,void *)=0;
    AT(inner,0x1da,u8)=0;
    FN(0x16442b0,Receive)(inner,&normal,0,4,(int)(normal.end-normal.begin));
    loading|=AT(inner,0xa40,u16);
    if (preview_mode) {
        FN(0x16442b0,Receive)(inner,&preview,0,6,(int)(preview.end-preview.begin));
        loading|=AT(inner,0xa40,u16);
    }
    AT(inner,0x3e0,int)=(int)((AT(inner,0x3d0,uptr)-AT(inner,0x3c8,uptr))/8);
    AT(inner,0x3e4,int)=0;
    AT(inner,0x3b0,int)=(int)((AT(inner,0x3a0,uptr)-AT(inner,0x398,uptr))/8);
    /* No event loop is entered here; keep any pre-existing/new loading flags. */
    AT(inner,0xa40,u16)|=loading;
    FN(0x1645240,Refresh)(inner,0);
}

static void repeat_search(void *inner) {
    typedef void (*FireSearch)(void *,const unsigned char *);
    typedef void (*Refresh)(void *,unsigned char);
    if (AT(inner,0x4b0,int)!=1) return;
    unsigned char instant=1;
    AT(inner,0xa41,u8)=1;
    FN(0x4fca90,FireSearch)((u8 *)inner+0x860,&instant);
    if (AT(inner,0xa41,u8)) FN(0x1645240,Refresh)(inner,0);
}

EXPORT void BlacklistSlotImpl(int which,BlacklistSlot *slot,void *receiver,void **args,u8 *equal) {
    (void)receiver; (void)args;
    typedef void (*Free)(void *,uptr);
    if (which==0) {
        FN(0x5b6e670,Free)(slot,sizeof(*slot));
    } else if (which==1) {
        if(slot->operation==8) {
            void *inner=slot->inner; uptr epoch=guard_inner(inner);
            u16 suggestion[KW_CAP+1]; bl_zero(suggestion,sizeof(suggestion));
            int saved=ShowSelectionDialog(inner,suggestion);
            if(saved>0) {
                if(epoch && guarded_inner==inner && guard_epoch==epoch) RefreshBlocked(inner);
                int changed=ShowKeywordDialog(1,suggestion);
                if(changed>0 && epoch && guarded_inner==inner && guard_epoch==epoch) {
                    RefreshBlocked(inner); repeat_search(inner);
                }
            }
            return;
        }
        if(slot->operation==6 || slot->operation==7) {
            void *inner=slot->inner; uptr epoch=guard_inner(inner);
            int changed=ShowKeywordDialog(slot->operation==7 ? 3 : 2,slot->suggestion);
            if(changed>0 && epoch && guarded_inner==inner && guard_epoch==epoch) {
                RefreshBlocked(inner); repeat_search(inner);
            }
            return;
        }
        int result=(slot->operation==4 || slot->operation==5)
            ? ch_change(slot->operation-3,&slot->key)
            : bl_change(slot->operation,&slot->key);
        if (result<0) { operation_error(); return; }
        if (slot->operation==1 || slot->operation==4) RefreshBlocked(slot->inner);
        else if (result) repeat_search(slot->inner);
        if(slot->operation==4) {
            void *inner=slot->inner; uptr epoch=guard_inner(inner);
            int changed=ShowKeywordDialog(1,slot->suggestion);
            if(changed>0 && epoch && guarded_inner==inner && guard_epoch==epoch) {
                RefreshBlocked(inner); repeat_search(inner);
            }
        }
    } else if (which==2 && equal) {
        *equal=0;
    }
}

static void add_blacklist_action(void *menu,void *inner,const u16 *label,int length,
                                 int operation,const BlockKey *key,const u16 *suggestion) {
    typedef void *(*Allocate)(uptr);
    typedef void *(*StringCtor)(void *,const u16 *,int);
    typedef void (*Destroy)(void *);
    typedef void *(*ActionCtor)(void *,const void *,void *);
    typedef void *(*Connect)(void *,void *,const void *,void *,void *,void *,int,const void *,const void *);
    typedef void *(*AddAction)(void *,void *,void *,void *,void *);
    void *qstring=0;
    FN(0x592a9c0,StringCtor)(&qstring,label,length);
    void *action=FN(0x5d819cc,Allocate)(0x10);
    FN(0x5479ac0,ActionCtor)(action,&qstring,menu);
    FN(0x4a9820,Destroy)(&qstring);
    BlacklistSlot *slot=(BlacklistSlot *)FN(0x5d819cc,Allocate)(sizeof(BlacklistSlot));
    slot->reference_count=1;
    slot->padding=0;
    slot->implementation=BlacklistSlotImpl;
    slot->inner=inner;
    slot->operation=operation;
    slot->reserved=0;
    bl_zero(slot->suggestion,sizeof(slot->suggestion));
    if(suggestion) for(unsigned int i=0;i<KW_CAP && suggestion[i];++i) slot->suggestion[i]=suggestion[i];
    if (key) slot->key=*key;
    else { slot->key.length=0; for (unsigned int i=0;i<32;++i)slot->key.digest[i]=0; }
    uptr signal=base()+0x547bb00;
    void *connection=0;
    /* connectImpl owns the initial slot reference on success AND failure. */
    FN(0x5973af0,Connect)(&connection,action,&signal,inner,0,slot,2,
                        (const void *)(base()+0x8ee6610),(const void *)(base()+0x65003b0));
    FN(0x59714e0,Destroy)(&connection);
    void *added=0;
    FN(0x3ca8990,AddAction)(menu,&added,action,0,0);
}

static void *menu_message(void *inner) {
    void *history=AT(inner,0x6a8,void *);
    uptr id=AT(inner,0x6b8,uptr);
    if (!history || !id) return 0;
    for (unsigned int k=0;k<2;++k) {
        unsigned int offset=k ? 0x398 : 0x3c8;
        void **begin=AT(inner,offset,void **),**end=AT(inner,offset+8,void **);
        for (void **p=begin;p!=end;++p) {
            void *item=AT(*p,0x60,void *);
            if (AT(item,0x10,void *)==history && AT(item,8,uptr)==id) return item;
        }
    }
    return 0;
}

EXPORT void PatchMenu(void *old_connection,void *inner) {
    typedef void (*Destroy)(void *);
    typedef const void *(*OriginalText)(void *);
    FN(0x59714e0,Destroy)(old_connection);
    if (AT(inner,0x4b0,int)!=1) return;
    void *popup=AT(inner,0xa50,void *);
    void *item=menu_message(inner);
    if (!popup || !item) return;
    void *menu=AT(popup,0x1b0,void *);
    BlockDb blocked;
    bl_open(&blocked);
    BlockKey key;
    Text value=text(FN(0x1c95050,OriginalText)(item));
    int usable=value.size && blocked.valid && bl_key(&blocked,value,&key);
    if (usable) add_blacklist_action(menu,inner,u"屏蔽相同内容",6,1,&key,0);
    if (blocked.valid && blocked.count)
        add_blacklist_action(menu,inner,u"撤销上次屏蔽",6,2,0,0);
    bl_close(&blocked);
    BlockDb channels;
    ch_open(&channels);
    void *peer=ch_item_peer(item);
    uptr channel=ch_peer_id(peer);
    u16 suggestion[KW_CAP+1]; KeywordSuggest(value.data,value.size,suggestion);
    /* Broadcast flag is 1<<10 at ChannelData+0x1a8. Do not offer this action
     * for users or groups; capture only the stable ID, never a live pointer. */
    if (channels.valid && channel && (AT(peer,0x1a8,uptr)&0x400)
        && !ch_contains_peer(&channels,peer) && ch_make_key(channel,&key))
        add_blacklist_action(menu,inner,u"屏蔽整个频道",6,4,&key,suggestion);
    if (channels.valid && channels.count)
        add_blacklist_action(menu,inner,u"撤销上次频道屏蔽",8,5,0,0);
    if(kw_broadcast(peer))
        add_blacklist_action(menu,inner,u"添加关键词屏蔽…",8,6,0,suggestion);
    add_blacklist_action(menu,inner,u"管理关键词屏蔽…",8,7,0,0);
    add_blacklist_action(menu,inner,u"进入多选屏蔽…",7,8,0,0);
    bl_close(&channels);
}
