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
