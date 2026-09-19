/* User-confirmed literal rules. Plain UTF-16, no account identifiers or network.
 * scope 1: broadcast message body; scope 2: broadcast channel display name.
 * No regex, implicit token splitting, or automatic channel-ID additions. */
#define KW_LIMIT 256u
#define KW_CAP 128u
typedef struct { unsigned int scope,length; u16 word[KW_CAP]; } KeywordRule;
typedef struct { BlockDb io; KeywordRule *rules; unsigned int count; int valid; u8 *failure; } KeywordDb;
_Static_assert(sizeof(KeywordRule)==264,"keyword record layout");
static int kw_valid(const KeywordRule *r) {
    if(!r || (r->scope!=1 && r->scope!=2) || !r->length || r->length>KW_CAP) return 0;
    int meaningful=0;
    for(unsigned int i=0;i<r->length;++i) {
        u16 c=r->word[i];
        if(!c || c<0x20 || c==0x7f) return 0;
        if(c>=0xd800 && c<=0xdbff) {
            if(++i>=r->length || r->word[i]<0xdc00 || r->word[i]>0xdfff) return 0;
        } else if(c>=0xdc00 && c<=0xdfff) return 0;
        if(c!=0x20 && c!=0x3000 && c!=0x200b && c!=0xfeff) meaningful=1;
    }
    for(unsigned int i=r->length;i<KW_CAP;++i) if(r->word[i]) return 0;
    return meaningful;
}
static int kw_equal(const KeywordRule *a,const KeywordRule *b) {
    if(a->scope!=b->scope || a->length!=b->length) return 0;
    for(unsigned int i=0;i<a->length;++i) if(a->word[i]!=b->word[i]) return 0;
    return 1;
}
static int kw_initialize(KeywordDb *db) {
    bl_zero(db,sizeof(*db));
    if(!bl_initialize_type(&db->io,0)) return 0;
    return bl_rule_directory(db->io.path)
        && bl_suffix(db->io.path,db->io.path,u"\\exact-search-keywords.v1.bin");
}
static int kw_load(KeywordDb *db) {
    void *f=BL_IAT(0x6000090,BlCreateFile)(db->io.path,0x80000000u,5,0,3,0x80,0);
    if(f==BL_INVALID) {
        db->valid=BL_IAT(0x6000070,BlLastError)()==2;
        return db->valid;
    }
    db->io.present=1;
    long long size=0; u8 header[16];
    int ok=BL_IAT(0x6000038,BlFileSize)(f,&size)
        && size>=16 && size<=16+KW_LIMIT*sizeof(KeywordRule)
        && bl_read_all(f,header,16);
    if(ok) for(unsigned int i=0;i<8;++i) if(header[i]!=((const u8 *)"TGEXKW1")[i]) ok=0;
    unsigned int n=ok ? bl_u32(header+12) : 0;
    if(ok && (bl_u32(header+8)!=1 || n>KW_LIMIT || size!=16+n*sizeof(KeywordRule))) ok=0;
    if(ok && n) {
        db->rules=(KeywordRule *)bl_alloc(&db->io,n*sizeof(KeywordRule));
        if(!db->rules || !bl_read_all(f,db->rules,n*sizeof(KeywordRule))) ok=0;
        if(ok) for(unsigned int i=0;i<n;++i) if(!kw_valid(db->rules+i)) { ok=0; break; }
    }
    if(!BL_IAT(0x60000a0,BlCloseHandle)(f)) ok=0;
    db->count=ok ? n : 0; db->valid=ok;
    if(ok && n) {
        db->failure=(u8 *)bl_alloc(&db->io,n*KW_CAP);
        if(db->failure) for(unsigned int i=0;i<n;++i) {
            KeywordRule *r=db->rules+i; u8 *f=db->failure+i*KW_CAP;
            for(unsigned int j=1,k=0;j<r->length;++j) {
                while(k && r->word[j]!=r->word[k]) k=f[k-1];
                if(r->word[j]==r->word[k]) ++k;
                f[j]=(u8)k;
            }
        }
    }
    return ok;
}
static int kw_open(KeywordDb *db) { return kw_initialize(db) && kw_load(db); }
static void kw_close(KeywordDb *db) {
    bl_free(&db->io,db->failure); bl_free(&db->io,db->rules); bl_close(&db->io); bl_zero(db,sizeof(*db));
}
/* op 0 bootstrap, 1 add, 2 remove the exact selected record. Reload under lock
 * so other processes' changes survive. A failed write never replaces the file. */
EXPORT int KeywordChange(int op,const KeywordRule *rule) {
    KeywordDb db; void *lock=BL_INVALID; u16 *path=0; u8 *buffer=0; int result=-1;
    if(!kw_initialize(&db)) goto done;
    if(op<0 || op>2 || (op && !kw_valid(rule))) { result=-2; goto done; }
    path=(u16 *)bl_alloc(&db.io,BL_PATH_CAP*2);
    if(!path || !bl_suffix(path,db.io.path,u".lock")) goto done;
    lock=BL_IAT(0x6000090,BlCreateFile)(path,0xc0000000u,0,0,4,0x80,0);
    if(lock==BL_INVALID || !kw_load(&db)) goto done;
    unsigned int found=db.count;
    if(op) for(unsigned int i=0;i<db.count;++i) if(kw_equal(db.rules+i,rule)) { found=i; break; }
    if((op==0 && db.io.present) || (op==1 && found<db.count) || (op==2 && found==db.count)) { result=0; goto done; }
    if(op==1 && db.count>=KW_LIMIT) { result=-3; goto done; }
    unsigned int count=db.count+(op==1 ? 1 : 0)-(op==2 ? 1 : 0);
    unsigned int bytes=16+count*sizeof(KeywordRule);
    buffer=(u8 *)bl_alloc(&db.io,bytes); if(!buffer) goto done;
    bl_copy(buffer,"TGEXKW1",8); bl_put32(buffer+8,1); bl_put32(buffer+12,count);
    KeywordRule *out=(KeywordRule *)(buffer+16);
    for(unsigned int i=0;i<db.count;++i) if(op!=2 || i!=found) *out++=db.rules[i];
    if(op==1) *out=*rule;
    result=bl_atomic_write(&db.io,buffer,bytes);
done:
    if(lock!=BL_INVALID) BL_IAT(0x60000a0,BlCloseHandle)(lock);
    bl_free(&db.io,path); bl_free(&db.io,buffer); kw_close(&db); return result;
}
static int kw_text(KeywordDb *db,Text value,unsigned int scope) {
    if(!db->valid) return 0;
    for(unsigned int i=0;i<db->count;++i) {
        KeywordRule *r=db->rules+i;
        if(r->scope!=scope || r->length>value.size) continue;
        /* KMP bounds work per rule to linear time even for adversarial repeats.
         * Allocation failure retains correct literal semantics via slow path. */
        if(!db->failure) { Text word={r->word,r->length}; if(contains(value,word)) return 1; continue; }
        u8 *f=db->failure+i*KW_CAP;
        for(unsigned int j=0,k=0;j<value.size;++j) {
            while(k && value.data[j]!=r->word[k]) k=f[k-1];
            if(value.data[j]==r->word[k]) ++k;
            if(k==r->length) return 1;
        }
    }
    return 0;
}
static int kw_broadcast(void *peer) {
    return ch_peer_id(peer) && (AT(peer,0x1a8,uptr)&0x400);
}
static int kw_peer(KeywordDb *db,void *peer) {
    typedef const void *(*Name)(void *);
    return db->valid && db->count && kw_broadcast(peer)
        && kw_text(db,text(FN(0x14a5490,Name)(peer)),2);
}
static int kw_item(KeywordDb *db,void *item) {
    typedef const void *(*OriginalText)(void *);
    void *peer=ch_item_peer(item);
    return db->valid && db->count && kw_broadcast(peer)
        && (kw_peer(db,peer) || kw_text(db,text(FN(0x1c95050,OriginalText)(item)),1));
}
static int kw_entry(KeywordDb *db,void *entry) {
    return entry && (AT(entry,0x104,unsigned int)&2) && kw_peer(db,AT(entry,0x2d8,void *));
}
/* A suggestion is a quoted source fragment, not a claim of spam detection.
 * Prefer a repeated complete line, otherwise the first nonempty line. Never
 * parse more than 4096 UTF-16 units and never cut a surrogate pair. */
EXPORT void KeywordSuggest(const u16 *data,unsigned int size,u16 *out) {
    out[0]=0; if(!data) return;
    if(size>4096) size=4096;
    unsigned int best=0,start=0,length=0;
    for(unsigned int i=0;i<size;) {
        unsigned int a=i; while(i<size && data[i]!='\r' && data[i]!='\n') ++i;
        unsigned int b=i; while(i<size && (data[i]=='\r' || data[i]=='\n')) ++i;
        while(a<b && (data[a]==' ' || data[a]=='\t')) ++a;
        while(b>a && (data[b-1]==' ' || data[b-1]=='\t')) --b;
        unsigned int n=b-a;
        if(n<2 || n>KW_CAP) continue;
        unsigned int score=1;
        Text line={data+a,n}, tail={data+i,size-i};
        if(contains(tail,line)) score=2;
        if(score>best) { best=score; start=a; length=n; }
    }
    if(length) { bl_copy(out,data+start,length*2); out[length]=0; }
}
