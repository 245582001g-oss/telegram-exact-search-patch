/* Standard Unicode Windows dialog. No shell, child processes or new imports.
 * Owns only copied text/rules, never Telegram message/peer pointers. */
typedef iptr (*RuleDlgProc)(void *,unsigned int,uptr,iptr);
typedef struct {
    iptr (*dialog)(void *,const void *,void *,RuleDlgProc,iptr);
    int (*end)(void *,iptr);
    iptr (*setlong)(void *,int,iptr);
    iptr (*getlong)(void *,int);
    int (*settext)(void *,int,const u16 *);
    unsigned int (*gettext)(void *,int,u16 *,int);
    iptr (*send)(void *,int,unsigned int,uptr,iptr);
    int (*check)(void *,int,int,int);
    unsigned int (*checked)(void *,int);
    int (*message)(void *,const u16 *,const u16 *,unsigned int);
    void *(*active)(void);
    void *(*item)(void *,int);
    int (*length)(void *);
    void *(*ancestor)(void *,unsigned int);
} RuleApi;
typedef struct {
    RuleApi api;
    KeywordDb db;
    int mode,changed;
    u16 suggestion[KW_CAP+1];
} RuleUi;
static int rule_ui_busy;
static void *rule_ui_window;
static int rule_api(RuleApi *a) {
    void *module=BL_IAT(0x6000140,BlGetModule)(u"user32.dll");
    if(!module) return 0;
    BlGetProc get=BL_IAT(0x60001b8,BlGetProc);
#define RULE_API(field,name) a->field=(__typeof__(a->field))get(module,name); if(!a->field) return 0
    RULE_API(dialog,"DialogBoxIndirectParamW"); RULE_API(end,"EndDialog");
    RULE_API(setlong,"SetWindowLongPtrW"); RULE_API(getlong,"GetWindowLongPtrW");
    RULE_API(settext,"SetDlgItemTextW"); RULE_API(gettext,"GetDlgItemTextW");
    RULE_API(send,"SendDlgItemMessageW"); RULE_API(check,"CheckRadioButton");
    RULE_API(checked,"IsDlgButtonChecked"); RULE_API(message,"MessageBoxW");
    RULE_API(active,"GetActiveWindow"); RULE_API(item,"GetDlgItem");
    RULE_API(length,"GetWindowTextLengthW");
    RULE_API(ancestor,"GetAncestor");
#undef RULE_API
    return 1;
}
typedef struct {
    RuleApi *api;
    void *best;
    uptr area;
    int (*visible)(void *);
    void *(*owner)(void *,unsigned int);
    int (*rect)(void *,void *);
} RuleOwnerSearch;
static int rule_owner_window(void *w,iptr value) {
    RuleOwnerSearch *s=(RuleOwnerSearch *)value;
    if(!s->visible(w) || s->owner(w,4) || (s->api->getlong(w,-20)&0x8000080)
        || (s->api->getlong(w,-16)&0x40000000)) return 1;
    struct { int left,top,right,bottom; } r;
    if(s->rect(w,&r) && r.right>r.left && r.bottom>r.top) {
        uptr area=(uptr)(r.right-r.left)*(uptr)(r.bottom-r.top);
        if(area>s->area) { s->best=w; s->area=area; }
    }
    return 1;
}
/* Telegram's fading menu is an UNOWNED tool HWND, so GA_ROOTOWNER alone does
 * not find the main window. Enumerate only this UI thread's visible, unowned,
 * non-tool windows and prefer its largest stable application window. */
static void *rule_owner(RuleApi *a) {
    void *active=a->active();
    void *owner=active ? a->ancestor(active,3) : 0; /* GA_ROOTOWNER */
    if(owner && !(a->getlong(owner,-20)&0x8000080)) return owner;
    BlGetProc get=BL_IAT(0x60001b8,BlGetProc);
    void *user=BL_IAT(0x6000140,BlGetModule)(u"user32.dll");
    void *kernel=BL_IAT(0x6000140,BlGetModule)(u"kernel32.dll");
    typedef unsigned int (*ThreadId)(void);
    typedef int (*EnumThread)(unsigned int,int (*)(void *,iptr),iptr);
    ThreadId thread=kernel ? (ThreadId)get(kernel,"GetCurrentThreadId") : 0;
    EnumThread enumerate=user ? (EnumThread)get(user,"EnumThreadWindows") : 0;
    RuleOwnerSearch search; bl_zero(&search,sizeof(search)); search.api=a;
    search.visible=user ? (void *)get(user,"IsWindowVisible") : 0;
    search.owner=user ? (void *)get(user,"GetWindow") : 0;
    search.rect=user ? (void *)get(user,"GetWindowRect") : 0;
    if(!thread || !enumerate || !search.visible || !search.owner || !search.rect) return 0;
    enumerate(thread(),rule_owner_window,(iptr)&search);
    return search.best;
}
static void rule_ui_raise(void) {
    if(!rule_ui_window) return;
    void *user=BL_IAT(0x6000140,BlGetModule)(u"user32.dll");
    if(!user) return;
    BlGetProc get=BL_IAT(0x60001b8,BlGetProc);
    typedef int (*WindowCall)(void *);
    typedef int (*Show)(void *,int);
    WindowCall valid=(WindowCall)get(user,"IsWindow");
    Show show=(Show)get(user,"ShowWindow");
    WindowCall top=(WindowCall)get(user,"BringWindowToTop");
    WindowCall foreground=(WindowCall)get(user,"SetForegroundWindow");
    typedef void *(*Activate)(void *);
    Activate active=(Activate)get(user,"SetActiveWindow");
    if(!valid || !valid(rule_ui_window)) return;
    if(show) show(rule_ui_window,9);
    if(top) top(rule_ui_window);
    if(active) active(rule_ui_window);
    if(foreground) foreground(rule_ui_window);
}
static void rule_ui_error(RuleUi *s,void *w,int result) {
    s->api.message(w,result==-3 ? u"关键词规则已达到 256 条。请先删除不需要的规则。"
        : u"关键词没有保存。请检查我的文档中 Telegram 文件夹是否可写、规则文件是否完整；原有规则会保留。",
        u"关键词屏蔽",0x10);
}
static void rule_ui_list(RuleUi *s,void *w) {
    kw_close(&s->db); kw_open(&s->db);
    s->api.send(w,104,0x184,0,0); /* LB_RESETCONTENT */
    if(!s->db.valid) { rule_ui_error(s,w,-1); return; }
    for(unsigned int i=0;i<s->db.count;++i) {
        KeywordRule *r=s->db.rules+i; u16 label[KW_CAP+16];
        const u16 *prefix=r->scope==1 ? u"正文：" : u"频道名：";
        unsigned int n=0; while(prefix[n]) { label[n]=prefix[n]; ++n; }
        bl_copy(label+n,r->word,r->length*2); label[n+r->length]=0;
        s->api.send(w,104,0x180,0,(iptr)label); /* LB_ADDSTRING */
    }
}
EXPORT iptr KeywordDialogProc(void *window,unsigned int message,uptr wp,iptr lp) {
    RuleUi *s;
    if(message==0x110) { /* WM_INITDIALOG */
        rule_ui_window=window;
        s=(RuleUi *)lp; s->api.setlong(window,16,(iptr)s); /* DWLP_USER */
        s->api.settext(window,100,s->suggestion);
        s->api.send(window,100,0xc5,4096,0); /* EM_LIMITTEXT */
        s->api.check(window,101,102,101);
        if(s->mode==3) rule_ui_list(s,window);
        return 1;
    }
    RuleApi a; if(!rule_api(&a)) return 0;
    s=(RuleUi *)a.getlong(window,16); if(!s) return 0;
    if(message==0x82 && rule_ui_window==window) rule_ui_window=0;
    if(message==0x10 || (message==0x111 && (wp&0xffff)==2)) {
        s->api.end(window,s->changed); return 1;
    }
    if(message!=0x111) return 0;
    unsigned int id=(unsigned int)(wp&0xffff);
    if(id==1) {
        int length=s->api.length(s->api.item(window,100));
        if(length<=0 || length>(int)KW_CAP) {
            s->api.message(window,u"请输入 1 至 128 个字的连续片段。空白不能作为屏蔽规则。",u"关键词屏蔽",0x30); return 1;
        }
        u16 word[KW_CAP+1]; KeywordRule rule; bl_zero(&rule,sizeof(rule));
        unsigned int n=s->api.gettext(window,100,word,KW_CAP+1);
        rule.scope=s->api.checked(window,102)==1 ? 2 : 1;
        rule.length=n; bl_copy(rule.word,word,n*2);
        if(!kw_valid(&rule)) {
            s->api.message(window,u"请输入有效文字，不能只包含空格或不可见字符。",u"关键词屏蔽",0x30); return 1;
        }
        if(n<4 && s->api.message(window,u"这个关键词很短，可能同时隐藏大量正常内容。仍要保存吗？",u"确认关键词",0x134)!=6) return 1;
        int result=KeywordChange(1,&rule);
        if(result<0) { rule_ui_error(s,window,result); return 1; }
        if(result) s->changed|=1;
        if(s->mode!=3) s->api.end(window,s->changed);
        else { rule_ui_list(s,window); s->api.settext(window,100,u""); }
        return 1;
    }
    if(id==105 && s->mode==3) {
        iptr selected=s->api.send(window,104,0x188,0,0); /* LB_GETCURSEL */
        if(selected<0 || (uptr)selected>=s->db.count) return 1;
        int result=KeywordChange(2,s->db.rules+selected);
        if(result<0) rule_ui_error(s,window,result);
        else { if(result) s->changed|=2; rule_ui_list(s,window); }
        return 1;
    }
    return 0;
}
static void ui_word(u8 **p,unsigned int n) { (*p)[0]=(u8)n; (*p)[1]=(u8)(n>>8); *p+=2; }
static void ui_dword(u8 **p,unsigned int n) { bl_put32(*p,n); *p+=4; }
static void ui_string(u8 **p,const u16 *s) { do { ui_word(p,*s); } while(*s++); }
static void ui_control(u8 **p,unsigned int style,unsigned int x,unsigned int y,
                       unsigned int width,unsigned int height,unsigned int id,
                       unsigned int cls,const u16 *title) {
    while((uptr)*p&3) *(*p)++=0;
    ui_dword(p,style|0x50000000u); ui_dword(p,0);
    ui_word(p,x); ui_word(p,y); ui_word(p,width); ui_word(p,height); ui_word(p,id);
    ui_word(p,0xffff); ui_word(p,cls); ui_string(p,title); ui_word(p,0);
}
EXPORT int ShowKeywordDialog(int mode,const u16 *suggestion) {
    if(rule_ui_busy) { rule_ui_raise(); return 0; }
    BlockDb memory; bl_zero(&memory,sizeof(memory));
    memory.heap=BL_IAT(0x6000350,BlGetHeap)(); if(!memory.heap) return -1;
    RuleUi *s=(RuleUi *)bl_alloc(&memory,sizeof(RuleUi));
    u8 *template=(u8 *)bl_alloc(&memory,4096); int result=-1;
    if(!s || !template || !rule_api(&s->api)) goto done;
    s->mode=mode;
    if(suggestion) for(unsigned int i=0;i<KW_CAP && suggestion[i];++i) s->suggestion[i]=suggestion[i];
    u8 *p=template;
    ui_dword(&p,0x80c808c0u); ui_dword(&p,0); /* popup/caption/sysmenu/font/center */
    ui_word(&p,mode==3 ? 9 : 7);
    ui_word(&p,0); ui_word(&p,0); ui_word(&p,376); ui_word(&p,mode==3 ? 280 : 155);
    ui_word(&p,0); ui_word(&p,0);
    ui_string(&p,mode==1 ? u"频道已屏蔽 — 要额外屏蔽关键词吗？" : mode==3 ? u"管理关键词屏蔽" : u"添加关键词屏蔽");
    ui_word(&p,9); ui_string(&p,u"Microsoft YaHei UI");
    ui_control(&p,0,12,10,352,28,110,0x82,mode==1
        ? u"该频道已屏蔽。下面是从所选消息提取的建议片段，请检查或修改后保存；也可以跳过。"
        : u"规则仅用于广播频道的搜索结果。可按消息正文或频道名称匹配；不会删除消息或退出频道。");
    ui_control(&p,0x30009,12,44,352,14,101,0x80,u"消息正文包含（隐藏命中的消息）");
    ui_control(&p,0x10009,12,62,352,14,102,0x80,u"频道名称包含（隐藏该频道的搜索结果）");
    ui_control(&p,0x810080,12,82,352,18,100,0x81,u"");
    ui_control(&p,0,12,105,352,20,111,0x82,u"连续文字匹配，英文区分大小写；多条规则命中任意一条即过滤。最多 128 个字。");
    ui_control(&p,0x10001,210,130,74,18,1,0x80,u"保存关键词");
    ui_control(&p,0x10000,292,130,72,18,2,0x80,mode==1 ? u"跳过" : u"关闭");
    if(mode==3) {
        ui_control(&p,0xa10001,12,158,352,89,104,0x83,u"");
        ui_control(&p,0x10000,12,252,100,18,105,0x80,u"删除选中的规则");
    }
    rule_ui_busy=1;
    result=(int)s->api.dialog((void *)base(),template,rule_owner(&s->api),KeywordDialogProc,(iptr)s);
    rule_ui_busy=0; rule_ui_window=0;
done:
    if(s) kw_close(&s->db);
    bl_free(&memory,template); bl_free(&memory,s); return result;
}
