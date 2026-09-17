/* Leaf bridge preserves original nonvolatile registers and caller frame.
 * Local lambda capture in R14 has {words*, InnerWidget*}. */
.text
.global PatchLocalBridge
.def PatchLocalBridge; .scl 2; .type 32; .endef
.seh_proc PatchLocalBridge
PatchLocalBridge:
    .seh_endprologue
    mov 8(%r14), %r9
    jmp PatchLocal
.seh_endproc

/* Initialize the optional rule directory before entering the untouched CRT
 * startup. Preserve the loader's volatile integer registers and stack. */
.global PatchStartupBridge
.def PatchStartupBridge; .scl 2; .type 32; .endef
.seh_proc PatchStartupBridge
PatchStartupBridge:
    sub $0x68, %rsp
    .seh_stackalloc 0x68
    .seh_endprologue
    mov %rcx, 0x20(%rsp)
    mov %rdx, 0x28(%rsp)
    mov %r8, 0x30(%rsp)
    mov %r9, 0x38(%rsp)
    mov %rax, 0x40(%rsp)
    mov %r10, 0x48(%rsp)
    mov %r11, 0x50(%rsp)
    call InitRuleStore
    mov 0x20(%rsp), %rcx
    mov 0x28(%rsp), %rdx
    mov 0x30(%rsp), %r8
    mov 0x38(%rsp), %r9
    mov 0x40(%rsp), %rax
    mov 0x48(%rsp), %r10
    mov 0x50(%rsp), %r11
    add $0x68, %rsp
    jmp __ImageBase+0x5d828ac
.seh_endproc
.global PatchMenuBridge
.def PatchMenuBridge; .scl 2; .type 32; .endef
.seh_proc PatchMenuBridge
PatchMenuBridge:
    .seh_endprologue
    mov %rsi, %rdx
    jmp PatchMenu
.seh_endproc
.global PatchApplyWordsBridge
.def PatchApplyWordsBridge; .scl 2; .type 32; .endef
.seh_proc PatchApplyWordsBridge
PatchApplyWordsBridge:
    .seh_endprologue
    mov %rsi, %r9
    jmp PatchWords
.seh_endproc
.global PatchRefreshWordsBridge
.def PatchRefreshWordsBridge; .scl 2; .type 32; .endef
.seh_proc PatchRefreshWordsBridge
PatchRefreshWordsBridge:
    .seh_endprologue
    mov %r15, %r9
    jmp PatchWords
.seh_endproc
