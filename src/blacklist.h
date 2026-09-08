/* Hash-only sidecar storage. Requires u8/u16/uptr/iptr, Text, base(), AT().
 * Windows x64, exact original Telegram import slots. No CRT or mutable globals. */
#ifndef TELEGRAM_EXACT_BLACKLIST_H
#define TELEGRAM_EXACT_BLACKLIST_H

#define BL_LIMIT 50000u
#define BL_PATH_CAP 1024u
#define BL_INVALID ((void *)(uptr)-1)
#define BL_IAT(r,t) ((t)AT((void *)base(),(r),uptr))
typedef void *(*BlGetHeap)(void);
typedef void *(*BlAlloc)(void *,unsigned int,uptr);
typedef int (*BlFree)(void *,unsigned int,void *);
typedef void *(*BlCreateFile)(const u16 *,unsigned int,unsigned int,void *,unsigned int,unsigned int,void *);
typedef int (*BlReadFile)(void *,void *,unsigned int,unsigned int *,void *);
typedef int (*BlWriteFile)(void *,const void *,unsigned int,unsigned int *,void *);
typedef int (*BlCloseHandle)(void *);
typedef int (*BlFileSize)(void *,long long *);
typedef int (*BlFlush)(void *);
typedef int (*BlMove)(const u16 *,const u16 *,unsigned int);
typedef int (*BlDelete)(const u16 *);
typedef unsigned int (*BlModuleName)(void *,u16 *,unsigned int);
typedef void *(*BlGetModule)(const u16 *);
typedef unsigned int (*BlFinalPath)(void *,u16 *,unsigned int,unsigned int);
typedef unsigned int (*BlLastError)(void);
typedef unsigned int (*BlProcessId)(void);
typedef uptr (*BlTick)(void);
typedef void *(*BlLoadLibrary)(const u16 *,void *,unsigned int);
typedef void *(*BlGetProc)(void *,const char *);
typedef int (*BlFreeLibrary)(void *);
typedef int (*BlCryptoOpen)(void **,const u16 *,const u16 *,unsigned int);
typedef int (*BlCryptoClose)(void *,unsigned int);
typedef int (*BlCryptoHash)(void *,u8 *,unsigned int,u8 *,unsigned int,u8 *,unsigned int);

typedef struct { unsigned int length; u8 digest[32]; } BlockKey;
typedef struct {
    BlockKey *keys;
    unsigned int count;
    unsigned int *buckets, bucket_mask;
    unsigned int shortest, longest;
    uptr length_bits;
    int valid, error;
    void *heap, *crypto_module, *algorithm;
    BlCryptoHash hash;
    BlCryptoClose close_algorithm;
    u16 *path;
} BlockDb;
_Static_assert(sizeof(BlockKey)==36,"BlockKey must be 36 bytes");

static void bl_zero(void *p,uptr n) { u8 *s=(u8 *)p; while(n--) *s++=0; }
static void bl_copy(void *d,const void *s,uptr n) {
    u8 *to=(u8 *)d; const u8 *from=(const u8 *)s;
    while(n--) *to++=*from++;
}
static unsigned int bl_u32(const u8 *p) {
    return (unsigned int)p[0]|((unsigned int)p[1]<<8)
        |((unsigned int)p[2]<<16)|((unsigned int)p[3]<<24);
}
static void bl_put32(u8 *p,unsigned int v) {
    for(unsigned int i=0;i<4;++i) p[i]=(u8)(v>>(8*i));
}
static int bl_same(const BlockKey *a,const BlockKey *b) {
    if(a->length!=b->length) return 0;
    for(unsigned int i=0;i<32;++i) if(a->digest[i]!=b->digest[i]) return 0;
    return 1;
}
static unsigned int bl_bucket_hash(const BlockKey *key) {
    unsigned int h=bl_u32(key->digest)^key->length;
    h^=h>>16; h*=0x7feb352du; h^=h>>15;
    return h;
}
static void *bl_alloc(BlockDb *db,uptr n) {
    return n ? BL_IAT(0x5fec3c8,BlAlloc)(db->heap,8,n) : (void *)0;
}
static void bl_free(BlockDb *db,void *p) {
    if(p) BL_IAT(0x5fec350,BlFree)(db->heap,0,p);
}
static void bl_index(BlockDb *db) {
    db->shortest=0xffffffffu;
    for(unsigned int i=0;i<db->count;++i) {
        unsigned int n=db->keys[i].length;
        if(n<db->shortest) db->shortest=n;
        if(n>db->longest) db->longest=n;
        db->length_bits|=(uptr)1<<(n&63);
    }
    /* Small lists are cheaper to scan. Keep original order in keys so Undo
     * still removes the last inserted rule; buckets only contain indexes. */
    if(db->count<256) return;
    unsigned int capacity=512;
    while(capacity<db->count*2) capacity*=2;
    db->buckets=(unsigned int *)bl_alloc(db,(uptr)capacity*4);
    if(!db->buckets) return; /* Allocation failure retains the exact slow path. */
    db->bucket_mask=capacity-1;
    for(unsigned int i=0;i<db->count;++i) {
        unsigned int slot=bl_bucket_hash(db->keys+i)&db->bucket_mask;
        while(db->buckets[slot]) slot=(slot+1)&db->bucket_mask;
        db->buckets[slot]=i+1;
    }
}
static int bl_find_key(BlockDb *db,const BlockKey *key) {
    if(db->buckets) {
        unsigned int slot=bl_bucket_hash(key)&db->bucket_mask;
        while(db->buckets[slot]) {
            if(bl_same(db->keys+db->buckets[slot]-1,key)) return 1;
            slot=(slot+1)&db->bucket_mask;
        }
        return 0;
    }
    for(unsigned int i=0;i<db->count;++i) if(bl_same(db->keys+i,key)) return 1;
    return 0;
}
static unsigned int bl_path_len(const u16 *p) {
    unsigned int n=0; while(n<BL_PATH_CAP && p[n]) ++n; return n;
}
static int bl_suffix(u16 *out,const u16 *path,const u16 *suffix) {
    unsigned int a=bl_path_len(path), b=bl_path_len(suffix);
    if(a>=BL_PATH_CAP || b>=BL_PATH_CAP || a+b>=BL_PATH_CAP) return 0;
    bl_copy(out,path,(uptr)a*2);
    bl_copy(out+a,suffix,((uptr)b+1)*2);
    return 1;
}
static int bl_initialize(BlockDb *db) {
    bl_zero(db,sizeof(*db));
    db->heap=BL_IAT(0x5fec348,BlGetHeap)();
    if(!db->heap) { db->error=-1; return 0; }
    db->path=(u16 *)bl_alloc(db,BL_PATH_CAP*2);
    if(!db->path) { db->error=-1; return 0; }
    unsigned int n=BL_IAT(0x5fec118,BlModuleName)(0,db->path,BL_PATH_CAP);
    if(!n || n>=BL_PATH_CAP) { db->error=-1; return 0; }
    /* Resolve migrated/junction installation paths before creating sidecars.
     * The launch spelling can be redirected and reject CREATE_NEW while the
     * actual installation directory is writable. No executable data is read. */
    void *kernel=BL_IAT(0x5fec148,BlGetModule)((const u16 *)L"kernel32.dll");
    BlFinalPath final_path=kernel ? (BlFinalPath)BL_IAT(0x5fec1c0,BlGetProc)(
        kernel,"GetFinalPathNameByHandleW") : (BlFinalPath)0;
    if(!final_path) { db->error=-1; return 0; }
    void *executable=BL_IAT(0x5fec098,BlCreateFile)(db->path,0,7,0,3,0x80,0);
    if(executable==BL_INVALID) { db->error=-1; return 0; }
    n=final_path(executable,db->path,BL_PATH_CAP,0);
    int closed=BL_IAT(0x5fec0a8,BlCloseHandle)(executable);
    if(!closed || !n || n>=BL_PATH_CAP) { db->error=-1; return 0; }
    unsigned int slash=n;
    while(slash && db->path[slash-1]!='\\' && db->path[slash-1]!='/') --slash;
    const u16 *name=(const u16 *)L"exact-search-blacklist.v1.bin";
    unsigned int length=bl_path_len(name);
    if(!slash || slash+length>=BL_PATH_CAP) { db->error=-1; return 0; }
    bl_copy(db->path+slash,name,((uptr)length+1)*2);
    return 1;
}
static int bl_read_all(void *handle,void *buffer,unsigned int size) {
    u8 *p=(u8 *)buffer;
    while(size) {
        unsigned int got=0;
        if(!BL_IAT(0x5fec1e0,BlReadFile)(handle,p,size,&got,0)
            || !got || got>size) return 0;
        p+=got; size-=got;
    }
    return 1;
}
static int bl_load(BlockDb *db) {
    db->valid=0;
    void *file=BL_IAT(0x5fec098,BlCreateFile)(db->path,0x80000000u,5,0,3,0x80,0);
    if(file==BL_INVALID) {
        if(BL_IAT(0x5fec078,BlLastError)()==2) { db->valid=1; return 1; }
        db->error=-1; return 0;
    }
    long long size=0;
    u8 header[16];
    int ok=BL_IAT(0x5fec038,BlFileSize)(file,&size)
        && size>=16 && size<=16+(long long)BL_LIMIT*36
        && bl_read_all(file,header,16);
    const u8 *magic=(const u8 *)"TGEXBL1";
    if(ok) for(unsigned int i=0;i<8;++i) if(header[i]!=magic[i]) ok=0;
    unsigned int count=ok ? bl_u32(header+12) : 0;
    if(ok && (bl_u32(header+8)!=1 || count>BL_LIMIT
        || size!=16+(long long)count*36)) ok=0;
    if(ok && count) {
        db->keys=(BlockKey *)bl_alloc(db,(uptr)count*36);
        if(!db->keys) ok=0;
        else if(!bl_read_all(file,db->keys,count*36)) ok=0;
        if(ok) for(unsigned int i=0;i<count;++i) {
            /* This file/target is explicitly little-endian Windows x64. */
            db->keys[i].length=bl_u32((const u8 *)&db->keys[i]);
            if(db->keys[i].length>0x7fffffffu) { ok=0; break; }
        }
    }
    if(!BL_IAT(0x5fec0a8,BlCloseHandle)(file)) ok=0;
    if(!ok) { db->error=-1; return 0; }
    db->count=count; db->valid=1; bl_index(db); return 1;
}
static int bl_open(BlockDb *db) {
    return bl_initialize(db) && bl_load(db);
}
static int bl_crypto(BlockDb *db) {
    if(db->algorithm && db->hash) return 1;
    if(db->crypto_module) return 0; /* Failed initialization is not retried in this DB. */
    db->crypto_module=BL_IAT(0x5fec428,BlLoadLibrary)((const u16 *)L"bcrypt.dll",0,0x800);
    if(!db->crypto_module) { db->error=-2; return 0; }
    BlGetProc get=BL_IAT(0x5fec1c0,BlGetProc);
    BlCryptoOpen open=(BlCryptoOpen)get(db->crypto_module,"BCryptOpenAlgorithmProvider");
    db->close_algorithm=(BlCryptoClose)get(db->crypto_module,"BCryptCloseAlgorithmProvider");
    db->hash=(BlCryptoHash)get(db->crypto_module,"BCryptHash");
    if(!open || !db->close_algorithm || !db->hash
        || open(&db->algorithm,(const u16 *)L"SHA256",0,0)<0) {
        db->error=-2; return 0;
    }
    return 1;
}
static int bl_key(BlockDb *db,Text value,BlockKey *out) {
    if(!out || value.size>0x7fffffffu || (value.size && !value.data)) {
        db->error=-2; return 0;
    }
    bl_zero(out,sizeof(*out));
    if(!bl_crypto(db)) return 0;
    if(db->hash(db->algorithm,0,0,(u8 *)value.data,value.size*2,out->digest,32)<0) {
        db->error=-2; return 0;
    }
    out->length=value.size; return 1;
}
static int bl_contains(BlockDb *db,Text value) {
    if(!db->valid || !db->count) return 0;
    if(value.size<db->shortest || value.size>db->longest
        || !(db->length_bits&((uptr)1<<(value.size&63)))) return 0;
    BlockKey key;
    if(!bl_key(db,value,&key)) return 0;
    return bl_find_key(db,&key);
}
static void bl_close(BlockDb *db) {
    if(db->algorithm && db->close_algorithm) db->close_algorithm(db->algorithm,0);
    if(db->crypto_module) BL_IAT(0x5fec1c8,BlFreeLibrary)(db->crypto_module);
    if(db->heap) { bl_free(db,db->buckets); bl_free(db,db->keys); bl_free(db,db->path); }
    bl_zero(db,sizeof(*db));
}
static void bl_hex(u16 *out,uptr value,unsigned int digits) {
    for(unsigned int i=0;i<digits;++i) {
        unsigned int n=(unsigned int)(value&15);
        out[digits-1-i]=(u16)(n<10 ? '0'+n : 'a'+n-10); value>>=4;
    }
}
static int bl_write_all(void *file,const u8 *bytes,unsigned int size) {
    while(size) {
        unsigned int wrote=0;
        if(!BL_IAT(0x5fec0a0,BlWriteFile)(file,bytes,size,&wrote,0)
            || !wrote || wrote>size) return 0;
        bytes+=wrote; size-=wrote;
    }
    return 1;
}
static int bl_save(BlockDb *db,unsigned int count,const BlockKey *added) {
    unsigned int bytes=16+count*36;
    u8 *buffer=(u8 *)bl_alloc(db,bytes);
    u16 *temporary=(u16 *)bl_alloc(db,BL_PATH_CAP*2);
    int result=-1;
    void *file=BL_INVALID;
    int created=0;
    if(!buffer || !temporary) goto done;
    bl_copy(buffer,"TGEXBL1",8); bl_put32(buffer+8,1); bl_put32(buffer+12,count);
    for(unsigned int i=0;i<count;++i) {
        const BlockKey *key=i<db->count ? db->keys+i : added;
        if(!key) goto done;
        bl_put32(buffer+16+i*36,key->length);
        bl_copy(buffer+20+i*36,key->digest,32);
    }
    if(!bl_suffix(temporary,db->path,(const u16 *)L".tmp.")) goto done;
    unsigned int at=bl_path_len(temporary);
    if(at+8+1+16+1+2>=BL_PATH_CAP) goto done;
    bl_hex(temporary+at,BL_IAT(0x5fec100,BlProcessId)(),8); at+=8;
    temporary[at++]='.';
    bl_hex(temporary+at,BL_IAT(0x5fec220,BlTick)(),16); at+=16;
    temporary[at++]='.'; temporary[at+2]=0;
    for(unsigned int attempt=0;attempt<32;++attempt) {
        bl_hex(temporary+at,attempt,2);
        file=BL_IAT(0x5fec098,BlCreateFile)(temporary,0x40000000u,0,0,1,0x80,0);
        if(file!=BL_INVALID) { created=1; break; }
        unsigned int error=BL_IAT(0x5fec078,BlLastError)();
        if(error!=80 && error!=183) goto done;
    }
    if(file==BL_INVALID) goto done;
    int ok=bl_write_all(file,buffer,bytes)
        && BL_IAT(0x5fec288,BlFlush)(file);
    if(!BL_IAT(0x5fec0a8,BlCloseHandle)(file)) ok=0;
    file=BL_INVALID;
    if(!ok) goto done;
    if(!BL_IAT(0x5fec280,BlMove)(temporary,db->path,9)) goto done;
    created=0; result=1;
done:
    if(file!=BL_INVALID) BL_IAT(0x5fec0a8,BlCloseHandle)(file);
    if(created) BL_IAT(0x5fec080,BlDelete)(temporary);
    bl_free(db,temporary); bl_free(db,buffer); return result;
}
/* 1=changed; 0=no-op; -1=I/O/format/memory; -2=invalid key/crypto; -3=limit. */
static int bl_change(int op,const BlockKey *key) {
    BlockDb db;
    int result=-1;
    void *lock=BL_INVALID;
    u16 *lockpath=0;
    if(!bl_initialize(&db)) goto done;
    if(op<1 || op>3) goto done;
    lockpath=(u16 *)bl_alloc(&db,BL_PATH_CAP*2);
    if(!lockpath || !bl_suffix(lockpath,db.path,(const u16 *)L".lock")) goto done;
    lock=BL_IAT(0x5fec098,BlCreateFile)(lockpath,0xc0000000u,0,0,4,0x80,0);
    if(lock==BL_INVALID || !bl_load(&db)) goto done;
    if(op==1) {
        if(!key || key->length>0x7fffffffu) { result=-2; goto done; }
        if(bl_find_key(&db,key)) {
            result=0; goto done;
        }
        if(db.count>=BL_LIMIT) { result=-3; goto done; }
        result=bl_save(&db,db.count+1,key);
    } else if(!db.count) result=0;
    else result=bl_save(&db,op==2 ? db.count-1 : 0,0);
done:
    if(lock!=BL_INVALID) BL_IAT(0x5fec0a8,BlCloseHandle)(lock);
    if(db.heap) bl_free(&db,lockpath);
    bl_close(&db); return result;
}
#endif
