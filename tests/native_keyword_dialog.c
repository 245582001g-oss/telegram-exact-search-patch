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
#include "../src/selection.h"
static wchar_t scratch[1024];
static void CALLBACK close_popup(HWND w,UINT msg,UINT_PTR timer,DWORD time){
    (void)msg;(void)time;KillTimer(w,timer);DestroyWindow(w);
}
/* Harness-only message: drive the production edge-scroll implementation with
 * real controls while keeping the physical mouse and keyboard untouched. */
static RuleDlgProc selection_proc;
static iptr selection_test_proc(void *w,unsigned int msg,uptr wp,iptr lp){
    if(msg==0x8002){
        if(selection_proc==SelectionDialogProc)return ShowSelectionDialog(0,0);
        return ShowKeywordDialog(2,u"Do not replace existing edits");
    }
    if(msg==0x8001){
        SelectionUi *s=(SelectionUi *)GetWindowLongPtrW(w,DWLP_USER);
        if(s) SelectionEdgeScroll(s,(short)(lp&0xffff),(short)((lp>>16)&0xffff));
        return 1;
    }
    return selection_proc(w,msg,wp,lp);
}
static iptr WINAPI harness_dialog(void *instance,const void *form,void *owner,RuleDlgProc proc,iptr value){
    (void)instance;
    selection_proc=proc;proc=selection_test_proc;
    return DialogBoxIndirectParamW(GetModuleHandleW(0),form,owner,(DLGPROC)proc,value);
}
static HRESULT WINAPI scratch_documents(const void *guid,DWORD flags,HANDLE token,PWSTR *out){
    (void)guid;(void)flags;(void)token;
    size_t bytes=(wcslen(scratch)+1)*sizeof(wchar_t);
    *out=CoTaskMemAlloc(bytes);if(!*out)return E_OUTOFMEMORY;
    memcpy(*out,scratch,bytes);return S_OK;
}
static FARPROC WINAPI scratch_proc(HMODULE m,LPCSTR n){
    if(!strcmp(n,"SHGetKnownFolderPath"))return (FARPROC)scratch_documents;
    if(!strcmp(n,"DialogBoxIndirectParamW"))return (FARPROC)harness_dialog;
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
    HWND main_window=0,popup=0;
    if(mode==11 || mode==12 || mode==14 || mode==16){
        main_window=CreateWindowExW(0,L"STATIC",L"Isolated main window",WS_OVERLAPPEDWINDOW|WS_VISIBLE,80,80,600,400,0,0,GetModuleHandleW(0),0);
        popup=CreateWindowExW(WS_EX_TOOLWINDOW,L"STATIC",L"Closing context menu",WS_POPUP|WS_VISIBLE,100,100,180,80,mode==11?main_window:0,0,GetModuleHandleW(0),0);
        SetActiveWindow(popup);SetTimer(popup,1,400,close_popup);if(mode==11||mode==14)mode=1;
    }
    int result;
    if(mode==12 || mode==16){
      for(int pass=0;pass<(mode==16?2:1);++pass){
        SelectionUi ui;bl_zero(&ui,sizeof(ui));ui.memory.heap=GetProcessHeap();ui.count=240;
        ui.rows=bl_alloc(&ui.memory,ui.count*sizeof(SelectionRow));
        for(unsigned int i=0;i<ui.count;++i){
            ui.rows[i].id=0x2000000000001ULL+i;ui.rows[i].hits=i+1;
            swprintf((wchar_t *)ui.rows[i].name,161,L"测试频道 %u",i+1);
            swprintf((wchar_t *)ui.rows[i].sample,129,L"固定广告内容 %u",i+1);
        }
        result=SelectionShow(&ui);printf("selected=%u changed=%d\n",ui.selected,ui.changed);
        bl_free(&ui.memory,ui.rows);
      }
    }else result=ShowKeywordDialog(mode,u"✅固定广告模板🌹");
    if(main_window){printf("popup_destroyed=%d main_reenabled=%d\n",!IsWindow(popup),IsWindowEnabled(main_window));DestroyWindow(main_window);}
    printf("dialog_result=%d\n",result);
    KeywordDb db;kw_open(&db);printf("valid=%d count=%u\n",db.valid,db.count);kw_close(&db);
    VirtualFree(mock_image,0,MEM_RELEASE);return result<0?5:0;
}
