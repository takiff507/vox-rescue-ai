#pragma once

#include <ntddk.h>

// Fixed product path: 48 kHz stereo PCM enters the render endpoint and
// 48 kHz mono PCM leaves the capture endpoint.
ULONGLONG VoxRescueBridgeAttachReader();

VOID VoxRescueBridgeWriteStereo16(
    _In_reads_bytes_(ByteCount) const UCHAR* Buffer,
    _In_ ULONG ByteCount
);

VOID VoxRescueBridgeReadMono16(
    _Out_writes_bytes_(ByteCount) UCHAR* Buffer,
    _In_ ULONG ByteCount,
    _Inout_ ULONGLONG* ReaderFrame
);
