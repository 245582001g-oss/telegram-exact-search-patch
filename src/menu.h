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
};
_Static_assert(sizeof(BlacklistSlot)==72,"Qt slot capture layout");

static void operation_error(void) {
    typedef void *(*GetModule)(const u16 *);
    typedef void *(*GetProc)(void *,const char *);
    typedef int (*MessageBox)(void *,const u16 *,const u16 *,unsigned int);
    GetModule module=AT((void *)base(),0x5fec148,GetModule);
    GetProc proc=AT((void *)base(),0x5fec1c0,GetProc);
    void *user32=module(u"user32.dll");
    if (!user32) return;
    MessageBox message=(MessageBox)proc(user32,"MessageBoxW");
    if (message) message(0,u"无法保存内容黑名单，本次操作没有生效。请检查程序文件夹是否可写，以及黑名单文件是否完整。",
                         u"搜索内容屏蔽",0x10);
}

static PtrVector snapshot_survivors(void *inner,unsigned int vector_offset,BlockDb *blocked) {
    typedef const void *(*OriginalText)(void *);
    typedef void *(*Allocate)(uptr);
    void **begin=AT(inner,vector_offset,void **);
    void **end=AT(inner,vector_offset+8,void **);
    PtrVector result={0,0,0};
    uptr capacity=(uptr)(end-begin);
    if (!capacity) return result;
    result.begin=(void **)FN(0x4a3690,Allocate)(capacity*8);
    result.end=result.begin;
    result.capacity=result.begin+capacity;
    for (void **p=begin;p!=end;++p) {
        void *item=AT(*p,0x60,void *);
        if (!bl_contains(blocked,text(FN(0x1c88390,OriginalText)(item))))
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
    BlockDb blocked;
    bl_open(&blocked);
    if (!blocked.valid) { bl_close(&blocked); return; }
    /* Snapshot both before either native receive can destroy old FakeRows. */
    PtrVector normal=snapshot_survivors(inner,0x3c8,&blocked);
    int preview_mode=AT(inner,0x621,u8)!=0;
    PtrVector preview={0,0,0};
    if (preview_mode) preview=snapshot_survivors(inner,0x398,&blocked);
    bl_close(&blocked);
    u16 loading=AT(inner,0xa40,u16);
    FN(0x1631740,SetPressed)(inner,-1);
    FN(0x16316d0,SetPressed)(inner,-1);
    FN(0x163da10,ClearMouse)(inner,1);
    AT(inner,0x1d0,void *)=0;
    AT(inner,0x1da,u8)=0;
    FN(0x163a810,Receive)(inner,&normal,0,4,(int)(normal.end-normal.begin));
    loading|=AT(inner,0xa40,u16);
    if (preview_mode) {
        FN(0x163a810,Receive)(inner,&preview,0,6,(int)(preview.end-preview.begin));
        loading|=AT(inner,0xa40,u16);
    }
    AT(inner,0x3e0,int)=(int)((AT(inner,0x3d0,uptr)-AT(inner,0x3c8,uptr))/8);
    AT(inner,0x3e4,int)=0;
    AT(inner,0x3b0,int)=(int)((AT(inner,0x3a0,uptr)-AT(inner,0x398,uptr))/8);
    /* No event loop is entered here; keep any pre-existing/new loading flags. */
    AT(inner,0xa40,u16)|=loading;
    FN(0x163b7a0,Refresh)(inner,0);
}

static void repeat_search(void *inner) {
    typedef void (*FireSearch)(void *,const unsigned char *);
    typedef void (*Refresh)(void *,unsigned char);
    if (AT(inner,0x4b0,int)!=1) return;
    unsigned char instant=1;
    AT(inner,0xa41,u8)=1;
    FN(0x4f7a90,FireSearch)((u8 *)inner+0x860,&instant);
    if (AT(inner,0xa41,u8)) FN(0x163b7a0,Refresh)(inner,0);
}

EXPORT void BlacklistSlotImpl(int which,BlacklistSlot *slot,void *receiver,void **args,u8 *equal) {
    (void)receiver; (void)args;
    typedef void (*Free)(void *,uptr);
    if (which==0) {
        FN(0x5b5b2c0,Free)(slot,sizeof(*slot));
    } else if (which==1) {
        int result=bl_change(slot->operation,&slot->key);
        if (result<0) { operation_error(); return; }
        if (slot->operation==1) RefreshBlocked(slot->inner);
        else if (result) repeat_search(slot->inner);
    } else if (which==2 && equal) {
        *equal=0;
    }
}

static void add_blacklist_action(void *menu,void *inner,const u16 *label,int length,
                                 int operation,const BlockKey *key) {
    typedef void *(*Allocate)(uptr);
    typedef void *(*StringCtor)(void *,const u16 *,int);
    typedef void (*Destroy)(void *);
    typedef void *(*ActionCtor)(void *,const void *,void *);
    typedef void *(*Connect)(void *,void *,const void *,void *,void *,void *,int,const void *,const void *);
    typedef void *(*AddAction)(void *,void *,void *,void *,void *);
    void *qstring=0;
    FN(0x5917620,StringCtor)(&qstring,label,length);
    void *action=FN(0x5d6e61c,Allocate)(0x10);
    FN(0x5466720,ActionCtor)(action,&qstring,menu);
    FN(0x4a4820,Destroy)(&qstring);
    BlacklistSlot *slot=(BlacklistSlot *)FN(0x5d6e61c,Allocate)(sizeof(BlacklistSlot));
    slot->reference_count=1;
    slot->padding=0;
    slot->implementation=BlacklistSlotImpl;
    slot->inner=inner;
    slot->operation=operation;
    slot->reserved=0;
    if (key) slot->key=*key;
    else { slot->key.length=0; for (unsigned int i=0;i<32;++i)slot->key.digest[i]=0; }
    uptr signal=base()+0x5468760;
    void *connection=0;
    /* connectImpl owns the initial slot reference on success AND failure. */
    FN(0x5960740,Connect)(&connection,action,&signal,inner,0,slot,2,
                        (const void *)(base()+0x8ecd4d0),(const void *)(base()+0x64ec2c0));
    FN(0x595e130,Destroy)(&connection);
    void *added=0;
    FN(0x3c95c80,AddAction)(menu,&added,action,0,0);
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
    FN(0x595e130,Destroy)(old_connection);
    if (AT(inner,0x4b0,int)!=1) return;
    void *popup=AT(inner,0xa50,void *);
    void *item=menu_message(inner);
    if (!popup || !item) return;
    void *menu=AT(popup,0x1b0,void *);
    BlockDb blocked;
    bl_open(&blocked);
    BlockKey key;
    Text value=text(FN(0x1c88390,OriginalText)(item));
    int usable=value.size && blocked.valid && bl_key(&blocked,value,&key);
    if (usable) add_blacklist_action(menu,inner,u"屏蔽相同内容",6,1,&key);
    if (blocked.valid && blocked.count)
        add_blacklist_action(menu,inner,u"撤销上次屏蔽",6,2,0);
    bl_close(&blocked);
}
