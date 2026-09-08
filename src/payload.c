/* Local exact-search patch, bound to Telegram Desktop 7.2.7 SHA-256 in build_patch.py.
 * No new network code, imports, or credential access. The optional content
 * blacklist persists only UTF-16 lengths and SHA-256 hashes beside this EXE.
 * All original
 * allocations remain owned by their original Telegram containers. */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned long long uptr;
typedef long long iptr;
typedef struct { void **begin, **end, **capacity; } PtrVector;
typedef struct { const u16 *data; unsigned int size; } Text;
#define EXPORT __declspec(dllexport)
#define AT(p,o,t) (*(t *)((u8 *)(p)+(o)))
static __attribute__((always_inline)) inline uptr base(void) {
    uptr value;
    __asm__("lea __ImageBase(%%rip), %0" : "=r"(value));
    return value;
}
#define FN(r,t) ((t)(base()+(r)))
static Text text(const void *qstring) {
    const u8 *d = AT(qstring,0,const u8 *);
    Text result = { 0, 0 };
    if (d) {
        int length = AT(d,4,int);
        if (length > 0) {
            result.size = (unsigned int)length;
            result.data = (const u16 *)(d + AT(d,16,iptr));
        }
    }
    return result;
}
#include "blacklist.h"
static int contains(Text haystack, Text needle) {
    if (!needle.size) return 1;
    if (needle.size > haystack.size) return 0;
    for (unsigned int i=0; i<=haystack.size-needle.size; ++i) {
        unsigned int j=0;
        while (j<needle.size && haystack.data[i+j]==needle.data[j]) ++j;
        if (j==needle.size) return 1;
    }
    return 0;
}
EXPORT int ExactContains(const void *haystack, const void *needle) {
    return contains(text(haystack),text(needle));
}
static int query_space(u16 c) {
    return (c>=9 && c<=13) || c==0x20 || c==0x85 || c==0xa0
        || c==0x1680 || (c>=0x2000 && c<=0x200a) || c==0x2028
        || c==0x2029 || c==0x202f || c==0x205f || c==0x3000;
}
static int all_keywords(Text haystack, Text query) {
    unsigned int i=0;
    while (i<query.size) {
        while (i<query.size && query_space(query.data[i])) ++i;
        unsigned int start=i;
        while (i<query.size && !query_space(query.data[i])) ++i;
        if (i>start) {
            Text keyword={query.data+start,i-start};
            if (!contains(haystack,keyword)) return 0;
        }
    }
    return 1;
}
EXPORT int AllKeywordsMatch(const void *haystack, const void *query) {
    return all_keywords(text(haystack),text(query));
}
static int active(void *inner) {
    return !AT(inner,0x5e0,void *) && !AT(inner,0x98,void *)
        && !AT(inner,0xb8,void *) && text((u8 *)inner+0x618).size;
}
static int message_matches(void *item, Text query) {
    typedef const void *(*OriginalText)(void *);
    return item && all_keywords(text(FN(0x1c88390,OriginalText)(item)),query);
}
static int username_matches(const void *name, Text query) {
    Text value=text(name);
    if (contains(value,query)) return 1;
    /* '@'+username is a separate searchable value, without concatenating aliases. */
    if (query.size && query.data[0]=='@' && query.size-1<=value.size) {
        unsigned int j=1;
        while (j<query.size && query.data[j]==value.data[j-1]) ++j;
        if (j==query.size) return 1;
    }
    return 0;
}
static int peer_matches(void *peer, Text query) {
    typedef const void *(*Name)(void *);
    if (!peer) return 0;
    if (contains(text(FN(0x149b950,Name)(peer)),query)) return 1;
    unsigned int kind=AT(peer,0xe,u8);
    unsigned int offset=(kind==0) ? 0x1d8 : (kind==2 ? 0x228 : 0);
    if (offset) {
        const u8 *p=AT(peer,offset,const u8 *);
        const u8 *end=AT(peer,offset+8,const u8 *);
        for (; p!=end; p+=8) if (username_matches(p,query)) return 1;
    }
    return 0;
}
EXPORT void PatchMessages(void *inner, PtrVector *items, void *inject,
                          unsigned char type, int full_count) {
    typedef void (*Receive)(void *,PtrVector *,void *,unsigned char,int);
    typedef const void *(*OriginalText)(void *);
    int exact=active(inner);
    int filtering=exact;
    /* Reject by cheap text predicates first. Pages with no exact matches need
     * no path resolution, file open, blacklist allocation, or crypto setup. */
    if (exact) {
        Text query=text((u8 *)inner+0x618);
        void **out=items->begin;
        for (void **p=items->begin; p!=items->end; ++p) {
            if (message_matches(*p,query)) *out++=*p;
        }
        items->end=out;
        if (inject && !message_matches(inject,query)) inject=0;
    }
    if (!exact || items->end!=items->begin || inject) {
        BlockDb blocked;
        bl_open(&blocked);
        if (blocked.valid && blocked.count) {
            filtering=1;
            void **out=items->begin;
            for (void **p=items->begin; p!=items->end; ++p) {
                if (!bl_contains(&blocked,text(FN(0x1c88390,OriginalText)(*p)))) *out++=*p;
            }
            items->end=out;
            if (inject && bl_contains(&blocked,text(FN(0x1c88390,OriginalText)(inject)))) inject=0;
        }
        bl_close(&blocked);
    }
    if (filtering) {
        full_count=(int)(items->end-items->begin)
            + ((type&4) ? 0 : (int)((AT(inner,0x3d0,uptr)-AT(inner,0x3c8,uptr))/8));
    }
    FN(0x163a810,Receive)(inner,items,inject,type,full_count);
    if (filtering) {
        AT(inner,0x3e0,int)=(int)((AT(inner,0x3d0,uptr)-AT(inner,0x3c8,uptr))/8);
        AT(inner,0x3e4,int)=0;
        AT(inner,0x3b0,int)=(int)((AT(inner,0x3a0,uptr)-AT(inner,0x398,uptr))/8);
    }
}
static void filter_peers(PtrVector *peers, Text query) {
    void **out=peers->begin;
    for (void **p=peers->begin; p!=peers->end; ++p)
        if (peer_matches(*p,query)) *out++=*p;
    peers->end=out;
}
EXPORT void PatchPeers(void *inner, void *result) {
    typedef void (*Receive)(void *,void *);
    typedef void (*Destroy)(void *);
    if (active(inner)) {
        Text query=text((u8 *)inner+0x618);
        filter_peers((PtrVector *)((u8 *)result+8),query);
        filter_peers((PtrVector *)((u8 *)result+0x20),query);
        /* Move entire ownership-bearing sponsored objects by swapping all bytes.
         * Accepted order stays stable. Destroy rejected tail objects exactly once. */
        u8 *out=AT(result,0x38,u8 *);
        u8 *end=AT(result,0x40,u8 *);
        for (u8 *p=out; p!=end; p+=0x30) {
            if (!peer_matches(AT(p,0,void *),query)) continue;
            if (p!=out) for (unsigned int i=0; i<0x30; ++i) {
                u8 tmp=out[i]; out[i]=p[i]; p[i]=tmp;
            }
            out+=0x30;
        }
        for (u8 *p=out; p!=end; p+=0x30) FN(0x5c0750,Destroy)(p);
        AT(result,0x40,u8 *)=out;
    }
    FN(0x163af50,Receive)(inner,result);
}
static int entry_matches(void *entry, Text query) {
    typedef const void *(*Name)(void *);
    Name get_name=AT(AT(entry,0,void *),0x48,Name);
    if (contains(text(get_name(entry)),query)) return 1;
    if ((AT(entry,0x104,unsigned int)&2)!=0) {
        void *peer=AT(entry,0x2d8,void *);
        /* Reuse aliases without conflating separate peer names. */
        unsigned int kind=AT(peer,0xe,u8);
        unsigned int offset=(kind==0) ? 0x1d8 : (kind==2 ? 0x228 : 0);
        if (offset) {
            const u8 *p=AT(peer,offset,const u8 *);
            const u8 *end=AT(peer,offset+8,const u8 *);
            for (; p!=end; p+=8) if (username_matches(p,query)) return 1;
        }
    }
    return 0;
}
EXPORT PtrVector *PatchLocal(void *list, PtrVector *result, void *words, void *inner) {
    typedef PtrVector *(*Filtered)(void *,PtrVector *,void *);
    typedef void *(*Allocate)(uptr);
    if (!active(inner)) return FN(0x161eb20,Filtered)(list,result,words);
    Text query=text((u8 *)inner+0x618);
    void **begin=AT(list,0x30,void **), **end=AT(list,0x38,void **);
    uptr count=0;
    for (void **p=begin; p!=end; ++p)
        if (entry_matches(AT(*p,0x60,void *),query)) ++count;
    result->begin=(void **)FN(0x4a3690,Allocate)(count*8);
    result->end=result->begin;
    result->capacity=result->begin+count;
    for (void **p=begin; p!=end; ++p)
        if (entry_matches(AT(*p,0x60,void *),query)) *result->end++=*p;
    return result;
}
EXPORT void *PatchWords(void *out, const void *query, int flags, void *inner) {
    typedef void *(*Prepare)(void *,const void *,int);
    typedef void *(*EmptyList)(void *);
    typedef void (*Append)(void *,const void *);
    if (!active(inner)) return FN(0x3afad60,Prepare)(out,query,flags);
    FN(0x7331a0,EmptyList)(out);
    FN(0x7330c0,Append)(out,query);
    return out;
}
#include "menu.h"
