#pragma once
// External host-runtime declarations absent from the pinned N64Recomp output.
//
// These are PROTOTYPES ONLY: no stubs or implementations are supplied here.
// Final native PC linking MUST resolve all referenced symbols to the pinned
// N64ModernRuntime, project-provided platform APIs or reviewed JP patches.
#include "recomp.h"

#ifdef __cplusplus
extern "C" {
#endif
void __ll_lshift_recomp(uint8_t*, recomp_context*);
void __osCheckId_recomp(uint8_t*, recomp_context*);
void __osContRamRead_recomp(uint8_t*, recomp_context*);
void __osContRamWrite_recomp(uint8_t*, recomp_context*);
void __osPfsRWInode_recomp(uint8_t*, recomp_context*);
void __osPfsSelectBank_recomp(uint8_t*, recomp_context*);
void __osTimerInterrupt_recomp(uint8_t*, recomp_context*);
void __osViSwapContext_recomp(uint8_t*, recomp_context*);
void osMapTLB_recomp(uint8_t*, recomp_context*);
void osPfsInit_recomp(uint8_t*, recomp_context*);
void osPfsIsPlug_recomp(uint8_t*, recomp_context*);
void osPfsNumFiles_recomp(uint8_t*, recomp_context*);
void osPfsRepairId_recomp(uint8_t*, recomp_context*);
void osPiWriteIo_recomp(uint8_t*, recomp_context*);
void osUnmapTLBAll_recomp(uint8_t*, recomp_context*);
#ifdef __cplusplus
}
#endif
