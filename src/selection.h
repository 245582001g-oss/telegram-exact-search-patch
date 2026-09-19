/* Search-result selection owns copied channel IDs/text, never live Qt rows.
 * Native checkboxes support accessible click/Space and right-button painting. */
#define SELECT_LIMIT 50000u
typedef struct {
    uptr id;
    unsigned int hits,checked;
    u16 name[161],sample[KW_CAP+1];
} SelectionRow;
typedef struct { int x,y; } SelectPoint;
typedef struct { int left,top,right,bottom; } SelectRect;
typedef struct {
    unsigned int mask; int item,subitem; unsigned int state,state_mask;
    u16 *text; int text_cap,image; iptr param;
    int indent,group; unsigned int columns; unsigned int *column;
    int *format; int group_index;
} SelectLvItem;
typedef struct {
    unsigned int mask; int format,width; const u16 *text; int text_cap,subitem;
    int image,order,min_width,default_width,ideal_width;
} SelectColumn;
typedef struct {
    RuleApi rule;
    iptr (*send)(void *,unsigned int,uptr,iptr);
    iptr (*call)(RuleDlgProc,void *,unsigned int,uptr,iptr);
    void *(*capture)(void *);
    int (*release)(void);
    uptr (*timer)(void *,uptr,unsigned int,void *);
    int (*killtimer)(void *,uptr);
    int (*client)(void *,SelectRect *);
    int (*cursor)(SelectPoint *);
    int (*to_client)(void *,SelectPoint *);
    short (*key)(int);
} SelectApi;
typedef struct {
    BlockDb memory;
    SelectApi api;
    SelectionRow *rows;
    unsigned int count,selected;
    void *window,*list,*module;
    RuleDlgProc old_proc;
    int drag,target,last,sync,changed;
    u16 suggestion[KW_CAP+1];
} SelectionUi;
_Static_assert(sizeof(SelectionRow)==600,"selection snapshot row ABI");
_Static_assert(sizeof(SelectionUi)==632,"selection state ABI");
static int select_api(SelectApi *a) {
    if(!rule_api(&a->rule)) return 0;
    void *module=BL_IAT(0x6000140,BlGetModule)(u"user32.dll");
    BlGetProc get=BL_IAT(0x60001b8,BlGetProc);
#define SELECT_API(field,name) a->field=(__typeof__(a->field))get(module,name); if(!a->field) return 0
    SELECT_API(send,"SendMessageW"); SELECT_API(call,"CallWindowProcW");
    SELECT_API(capture,"SetCapture"); SELECT_API(release,"ReleaseCapture");
    SELECT_API(timer,"SetTimer"); SELECT_API(killtimer,"KillTimer");
    SELECT_API(client,"GetClientRect"); SELECT_API(cursor,"GetCursorPos");
    SELECT_API(to_client,"ScreenToClient"); SELECT_API(key,"GetAsyncKeyState");
#undef SELECT_API
    return 1;
}
static unsigned int select_number(u16 *out,unsigned int value) {
    u16 tmp[16]; unsigned int n=0;
    do { tmp[n++]=(u16)('0'+value%10); value/=10; } while(value);
    for(unsigned int i=0;i<n;++i) out[i]=tmp[n-i-1];
    out[n]=0; return n;
}
static void select_status(SelectionUi *s) {
    u16 label[100]; unsigned int n=0;
    const u16 *a=u"已选择 "; while(*a) label[n++]=*a++;
    n+=select_number(label+n,s->selected); label[n++]=' '; label[n++]='/'; label[n++]=' ';
    n+=select_number(label+n,s->count);
    a=u" 个频道"; while(*a) label[n++]=*a++; label[n]=0;
    s->api.rule.settext(s->window,203,label);
}
static void select_check(SelectionUi *s,unsigned int i,int checked) {
    if(i>=s->count || s->rows[i].checked==(unsigned int)checked) return;
    s->selected=checked ? s->selected+1 : s->selected-1;
    s->rows[i].checked=(unsigned int)checked;
    SelectLvItem item; bl_zero(&item,sizeof(item));
    item.state_mask=0xf000; item.state=checked ? 0x2000 : 0x1000;
    s->sync=1; s->api.send(s->list,0x102b,i,(iptr)&item); s->sync=0; /* LVM_SETITEMSTATE */
}
static int select_hit(SelectionUi *s,int x,int y) {
    struct { SelectPoint p; unsigned int flags; int item,subitem,group; } hit;
    bl_zero(&hit,sizeof(hit)); hit.p.x=x; hit.p.y=y;
    int i=(int)s->api.send(s->list,0x1012,0,(iptr)&hit); /* LVM_HITTEST */
    return i>=0 && (unsigned int)i<s->count ? i : -1;
}
EXPORT void SelectionSweep(SelectionUi *s,int i) {
    if(i<0 || (unsigned int)i>=s->count) return;
    int first=s->last<0 ? i : s->last;
    int step=first<=i ? 1 : -1;
    for(int j=first;;j+=step) { select_check(s,(unsigned int)j,s->target); if(j==i) break; }
    s->last=i; select_status(s);
}
static void select_stop(SelectionUi *s) {
    if(!s->drag) return;
    s->drag=0; s->api.killtimer(s->list,1); s->api.release();
}
/* Separated from pointer acquisition so the edge-scroll path can be driven
 * with real controls in the isolated harness without moving the user's mouse. */
EXPORT void SelectionEdgeScroll(SelectionUi *s,int x,int y) {
    SelectRect r,header; bl_zero(&header,sizeof(header));
    if(!s->api.client(s->list,&r) || x<r.left || x>=r.right) return;
    void *hwnd=(void *)s->api.send(s->list,0x101f,0,0);
    if(hwnd) s->api.client(hwnd,&header);
    int top=(int)s->api.send(s->list,0x1027,0,0);
    SelectRect row; bl_zero(&row,sizeof(row));
    int height=s->api.send(s->list,0x100e,(uptr)top,(iptr)&row) ? row.bottom-row.top : 24;
    if(height<1) height=24;
    int start=header.bottom+height/2,end=r.bottom-height/2;
    int dy=y<start ? -height : y>=end ? height : 0;
    if(dy) s->api.send(s->list,0x1014,0,dy);
    if(y<start) y=start;
    if(y>=end) y=end-1;
    SelectionSweep(s,select_hit(s,x,y));
}
EXPORT iptr SelectionListProc(void *w,unsigned int msg,uptr wp,iptr lp) {
    RuleApi a; if(!rule_api(&a)) return 0;
    SelectionUi *s=(SelectionUi *)a.getlong(w,-21); /* GWLP_USERDATA */
    if(!s) return 0;
    int x=(short)(lp&0xffff),y=(short)((lp>>16)&0xffff);
    if(msg==0x204) { /* WM_RBUTTONDOWN */
        int i=select_hit(s,x,y); if(i<0) return 0;
        s->drag=1; s->last=-1; s->target=!s->rows[i].checked;
        s->api.capture(w); s->api.timer(w,1,65,0); SelectionSweep(s,i); return 0;
    }
    if(msg==0x200 && s->drag) { SelectionSweep(s,select_hit(s,x,y)); return 0; }
    if(msg==0x205 || msg==0x215 || msg==0x1f) { select_stop(s); if(msg==0x205) return 0; }
    if(msg==0x7b) return 0; /* no context menu while painting selection */
    if(msg==0x113 && wp==1 && s->drag) {
        if(!(s->api.key(2)&0x8000)) { select_stop(s); return 0; }
        SelectPoint p;
        if(s->api.cursor(&p) && s->api.to_client(w,&p)) SelectionEdgeScroll(s,p.x,p.y);
        return 0;
    }
    return s->api.call(s->old_proc,w,msg,wp,lp);
}
EXPORT iptr SelectionDialogProc(void *w,unsigned int msg,uptr wp,iptr lp) {
    SelectionUi *s;
    if(msg==0x110) {
        rule_ui_window=w;
        s=(SelectionUi *)lp; s->window=w; s->api.rule.setlong(w,16,(iptr)s);
        s->list=s->api.rule.item(w,200);
        s->api.send(s->list,0x1036,0,0x10024); /* checkbox/full row/double buffer */
        SelectRect rect; s->api.client(s->list,&rect); int width=rect.right-rect.left-24;
        const u16 *titles[]={u"频道",u"结果数",u"消息示例"};
        for(unsigned int i=0;i<3;++i) {
            SelectColumn col; bl_zero(&col,sizeof(col)); col.mask=6; col.text=titles[i];
            col.width=i==0 ? width*35/100 : i==1 ? width*12/100 : width*53/100;
            s->api.send(s->list,0x1061,i,(iptr)&col); /* LVM_INSERTCOLUMNW */
        }
        for(unsigned int i=0;i<s->count;++i) {
            SelectLvItem item; bl_zero(&item,sizeof(item)); item.mask=1; item.item=(int)i; item.text=s->rows[i].name;
            s->api.send(s->list,0x104d,0,(iptr)&item); /* LVM_INSERTITEMW */
            u16 number[16]; select_number(number,s->rows[i].hits);
            item.subitem=1; item.text=number; s->api.send(s->list,0x1074,i,(iptr)&item); /* SETITEMTEXTW */
            item.subitem=2; item.text=s->rows[i].sample; s->api.send(s->list,0x1074,i,(iptr)&item);
        }
        s->api.rule.setlong(s->list,-21,(iptr)s);
        s->old_proc=(RuleDlgProc)s->api.rule.setlong(s->list,-4,(iptr)SelectionListProc);
        select_status(s); return 1;
    }
    RuleApi a; if(!rule_api(&a)) return 0;
    s=(SelectionUi *)a.getlong(w,16); if(!s) return 0;
    if(msg==0x82 && rule_ui_window==w) rule_ui_window=0;
    if(msg==0x4e && !s->sync) { /* WM_NOTIFY / LVN_ITEMCHANGED */
        const struct { void *hwnd; uptr id; int code,padding; int index,sub; unsigned int now,before,changed; } *notice=(const void *)lp;
        if(notice && notice->hwnd==s->list && notice->code==-101 && notice->index>=0
            && (unsigned int)notice->index<s->count && (notice->changed&8)) {
            unsigned int checked=(notice->now&0xf000)==0x2000;
            SelectionRow *row=s->rows+notice->index;
            if(row->checked!=checked) { s->selected=checked ? s->selected+1 : s->selected-1; row->checked=checked; select_status(s); }
        }
        return 0;
    }
    if(msg==0x10 || (msg==0x111 && (wp&0xffff)==2)) {
        select_stop(s); s->api.rule.end(w,0); return 1;
    }
    if(msg!=0x111) return 0;
    unsigned int id=(unsigned int)(wp&0xffff);
    if(id==201 || id==202) {
        for(unsigned int i=0;i<s->count;++i) select_check(s,i,id==201);
        select_status(s); return 1;
    }
    if(id==1) {
        select_stop(s);
        if(!s->selected) { s->api.rule.message(w,u"请先勾选频道，也可以按住右键上下滑动快速选取。",u"多选屏蔽",0x40); return 1; }
        uptr *ids=(uptr *)bl_alloc(&s->memory,(uptr)s->selected*8);
        if(!ids) return 1;
        unsigned int n=0;
        for(unsigned int i=0;i<s->count;++i) if(s->rows[i].checked) {
            ids[n++]=s->rows[i].id;
            if(n==1) bl_copy(s->suggestion,s->rows[i].sample,sizeof(s->suggestion));
        }
        int changed=ChannelBatch(ids,n); bl_free(&s->memory,ids);
        if(changed<0) {
            s->api.rule.message(w,changed==-3 ? u"频道屏蔽列表已满，本次没有添加。"
                : u"无法保存，本次所选频道均未添加。请检查规则文件是否可写、完整。",u"多选屏蔽",0x10); return 1;
        }
        s->changed=changed; s->api.rule.end(w,1); return 1;
    }
    return 0;
}
static void select_text(u16 *out,unsigned int cap,Text value) {
    unsigned int n=value.size<cap ? value.size : cap;
    if(n && value.data[n-1]>=0xd800 && value.data[n-1]<=0xdbff) --n;
    for(unsigned int i=0;i<n;++i) out[i]=value.data[i]<32 ? ' ' : value.data[i];
    out[n]=0;
}
EXPORT int SelectionSnapshot(void *inner,SelectionUi *s) {
    typedef const void *(*OriginalText)(void *);
    typedef const void *(*Name)(void *);
    uptr total=0;
    for(unsigned int k=0;k<2;++k) {
        unsigned int o=k ? 0x398 : 0x3c8;
        uptr a=AT(inner,o,uptr),b=AT(inner,o+8,uptr);
        if(b<a || (b-a)%8 || (b-a)/8>500000) return -1;
        total+=(b-a)/8;
    }
    if(!total) return 0;
    unsigned int cap=(unsigned int)(total>SELECT_LIMIT ? SELECT_LIMIT : total);
    s->memory.heap=BL_IAT(0x6000350,BlGetHeap)();
    s->rows=(SelectionRow *)bl_alloc(&s->memory,(uptr)cap*sizeof(SelectionRow));
    unsigned int bucket_count=512; while(bucket_count<cap*2) bucket_count*=2;
    unsigned int *buckets=(unsigned int *)bl_alloc(&s->memory,(uptr)bucket_count*4);
    if(!s->rows || !buckets) { bl_free(&s->memory,buckets); return -1; }
    int result=1;
    for(unsigned int k=0;k<2;++k) {
        unsigned int offset=k ? 0x398 : 0x3c8;
        void **begin=AT(inner,offset,void **),**end=AT(inner,offset+8,void **);
        for(void **p=begin;p!=end;++p) {
            void *item=AT(*p,0x60,void *),*peer=ch_item_peer(item);
            if(!kw_broadcast(peer)) continue;
            uptr id=ch_peer_id(peer); unsigned int bucket=(unsigned int)(id^(id>>32))*0x9e3779b1u&(bucket_count-1);
            while(buckets[bucket] && s->rows[buckets[bucket]-1].id!=id) bucket=(bucket+1)&(bucket_count-1);
            if(buckets[bucket]) { ++s->rows[buckets[bucket]-1].hits; continue; }
            if(s->count==cap) { result=-2; goto done; }
            SelectionRow *row=s->rows+s->count; row->id=id; row->hits=1;
            select_text(row->name,160,text(FN(0x14a5490,Name)(peer)));
            if(!row->name[0]) bl_copy(row->name,u"未命名频道",12);
            Text body=text(FN(0x1c95050,OriginalText)(item));
            KeywordSuggest(body.data,body.size,row->sample);
            if(!row->sample[0]) select_text(row->sample,KW_CAP,body);
            buckets[bucket]=++s->count;
        }
    }
    if(!s->count) result=0;
done:
    bl_free(&s->memory,buckets); return result;
}
static void select_control(u8 **p) {
    while((uptr)*p&3) *(*p)++=0;
    ui_dword(p,0x5081000du); ui_dword(p,0x200); /* report, single focus, border, tab */
    ui_word(p,12);ui_word(p,40);ui_word(p,436);ui_word(p,194);ui_word(p,200);
    ui_string(p,u"SysListView32");ui_string(p,u"");ui_word(p,0);
}
EXPORT int SelectionShow(SelectionUi *s) {
    if(rule_ui_busy) { rule_ui_raise(); return 0; }
    if(!select_api(&s->api)) return -1;
    s->module=BL_IAT(0x6000430,BlLoadLibrary)(u"comctl32.dll",0,0x800);
    typedef int (*InitControls)(const void *);
    InitControls init=s->module ? (InitControls)BL_IAT(0x60001b8,BlGetProc)(s->module,"InitCommonControlsEx") : 0;
    const unsigned int controls[]={8,1};
    int result=-1; u8 *template=0;
    if(!init || !init(controls)) goto done;
    template=(u8 *)bl_alloc(&s->memory,4096); if(!template) goto done;
    u8 *p=template;
    ui_dword(&p,0x80c808c0u);ui_dword(&p,0);ui_word(&p,7);
    ui_word(&p,0);ui_word(&p,0);ui_word(&p,460);ui_word(&p,292);
    ui_word(&p,0);ui_word(&p,0);ui_string(&p,u"搜索结果多选屏蔽");ui_word(&p,9);ui_string(&p,u"Microsoft YaHei UI");
    ui_control(&p,0,12,10,436,28,210,0x82,u"同一频道已合并。勾选或按住右键上下滑动，拖到列表边缘可自动滚动。这里只列出已加载的广播频道。");
    select_control(&p);
    ui_control(&p,0x10000,12,242,58,18,201,0x80,u"全选");
    ui_control(&p,0x10000,78,242,76,18,202,0x80,u"取消全选");
    ui_control(&p,0,165,245,265,16,203,0x82,u"");
    ui_control(&p,0x10001,260,268,102,18,1,0x80,u"屏蔽所选频道");
    ui_control(&p,0x10000,370,268,78,18,2,0x80,u"取消");
    rule_ui_busy=1;
    result=(int)s->api.rule.dialog((void *)base(),template,rule_owner(&s->api.rule),SelectionDialogProc,(iptr)s);
    rule_ui_busy=0; rule_ui_window=0;
done:
    bl_free(&s->memory,template);
    if(s->module) BL_IAT(0x60001c0,BlFreeLibrary)(s->module);
    return result;
}
EXPORT int ShowSelectionDialog(void *inner,u16 *suggestion) {
    if(rule_ui_busy) { rule_ui_raise(); return 0; }
    BlockDb memory; bl_zero(&memory,sizeof(memory)); memory.heap=BL_IAT(0x6000350,BlGetHeap)();
    SelectionUi *s=(SelectionUi *)bl_alloc(&memory,sizeof(SelectionUi)); if(!s) return -1;
    int result=SelectionSnapshot(inner,s);
    if(result>0) result=SelectionShow(s);
    else {
        RuleApi a; if(rule_api(&a)) a.message(rule_owner(&a),result==0 ? u"当前没有可供多选的广播频道搜索结果。"
            : u"无法读取当前选择列表，请减少已加载结果后重试。本次没有屏蔽任何频道。",u"多选屏蔽",0x40);
    }
    if(result>0) bl_copy(suggestion,s->suggestion,sizeof(s->suggestion));
    bl_free(&s->memory,s->rows); bl_free(&memory,s); return result;
}
