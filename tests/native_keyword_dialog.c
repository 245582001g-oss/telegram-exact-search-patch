/* Isolated real Win32 dialog harness. Never loads Telegram or its account.
 * argv[1] must be an existing scratch Documents directory. */
#ifndef UNICODE
#define UNICODE
#endif
#define _UNICODE
#include <windows.h>
#include <shlobj.h>
#include <stdio.h>
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned long long uptr;
typedef long long iptr;
typedef struct {const u16 *data;unsigned int size;} Text;
#define EXPORT
#define AT(p,o,t) (*(t *)((u8 *)(p)+(o)))
static u8 *mock_image;
static uptr base(void){return (uptr)mock_image;}
#define FN(r,t) ((t)(base()+(r)))
static Text text(const void *p){(void)p;return (Text){0,0};}
static int contains(Text h,Text n){
    if(!n.size)return 1;if(n.size>h.size)return 0;
    for(unsigned int i=0;i<=h.size-n.size;++i){unsigned int j=0;while(j<n.size&&h.data[i+j]==n.data[j])++j;if(j==n.size)return 1;}return 0;
}
#include "../src/blacklist.h"
#include "../src/keywords.h"
#include "../src/rule_ui.h"
static wchar_t scratch[1024];
static HRESULT WINAPI scratch_documents(const void *guid,DWORD flags,HANDLE token,PWSTR *out){
    (void)guid;(void)flags;(void)token;
    size_t bytes=(wcslen(scratch)+1)*sizeof(wchar_t);
    *out=CoTaskMemAlloc(bytes);if(!*out)return E_OUTOFMEMORY;
    memcpy(*out,scratch,bytes);return S_OK;
}
static FARPROC WINAPI scratch_proc(HMODULE m,LPCSTR n){
    if(!strcmp(n,"SHGetKnownFolderPath"))return (FARPROC)scratch_documents;
    return GetProcAddress(m,n);
}
int wmain(int argc,wchar_t **argv){
    if(argc<2||wcslen(argv[1])>900||GetFileAttributesW(argv[1])==INVALID_FILE_ATTRIBUTES)return 2;
    SetProcessDPIAware();
    wcscpy(scratch,argv[1]);
    mock_image=VirtualAlloc(0,0x6001000,MEM_RESERVE,PAGE_NOACCESS);
    if(!mock_image||!VirtualAlloc(mock_image+0x6000000,4096,MEM_COMMIT,PAGE_READWRITE))return 3;
#define IMPORT(r,f) AT(mock_image,r,uptr)=(uptr)f
    IMPORT(0x6000350,GetProcessHeap);IMPORT(0x60003d0,HeapAlloc);IMPORT(0x6000358,HeapFree);
    IMPORT(0x6000140,GetModuleHandleW);IMPORT(0x60001b8,scratch_proc);
    IMPORT(0x6000430,LoadLibraryExW);IMPORT(0x60001c0,FreeLibrary);
    IMPORT(0x6000090,CreateFileW);IMPORT(0x60000a0,CloseHandle);IMPORT(0x6000038,GetFileSizeEx);
    IMPORT(0x60001d8,ReadFile);IMPORT(0x6000098,WriteFile);IMPORT(0x6000070,GetLastError);
    IMPORT(0x6000078,DeleteFileW);IMPORT(0x6000278,MoveFileExW);IMPORT(0x6000280,FlushFileBuffers);
    IMPORT(0x60000f8,GetCurrentProcessId);IMPORT(0x6000218,GetTickCount64);
    if(KeywordChange(0,0)<0)return 4;
    int mode=argc>2?_wtoi(argv[2]):1;
    int result=ShowKeywordDialog(mode,u"✅固定广告模板🌹");
    printf("dialog_result=%d\n",result);
    KeywordDb db;kw_open(&db);printf("valid=%d count=%u\n",db.valid,db.count);kw_close(&db);
    VirtualFree(mock_image,0,MEM_RELEASE);return result<0?5:0;
}
