#include "VoxRescueBridge.h"

namespace
{
    constexpr ULONG kSampleRate = 48000;
    constexpr ULONG kRingFrames = kSampleRate * 2;
    constexpr ULONGLONG kMaximumBacklogFrames = kSampleRate / 10; // 100 ms
    constexpr ULONGLONG kRecoveryBacklogFrames = kSampleRate / 50; // 20 ms

    SHORT g_Ring[kRingFrames] = {};
    ULONGLONG g_WriteFrame = 0;
    KSPIN_LOCK g_BridgeLock = {};
    volatile LONG g_InitializationState = 0;

    VOID EnsureInitialized()
    {
        const LONG state = InterlockedCompareExchange(&g_InitializationState, 1, 0);
        if (state == 0)
        {
            KeInitializeSpinLock(&g_BridgeLock);
            KeMemoryBarrier();
            InterlockedExchange(&g_InitializationState, 2);
            return;
        }

        while (InterlockedCompareExchange(&g_InitializationState, 2, 2) != 2)
        {
            YieldProcessor();
        }
    }
}

ULONGLONG VoxRescueBridgeAttachReader()
{
    EnsureInitialized();

    KIRQL oldIrql;
    KeAcquireSpinLock(&g_BridgeLock, &oldIrql);
    const ULONGLONG readerFrame = g_WriteFrame;
    KeReleaseSpinLock(&g_BridgeLock, oldIrql);
    return readerFrame;
}

VOID VoxRescueBridgeWriteStereo16(
    _In_reads_bytes_(ByteCount) const UCHAR* Buffer,
    _In_ ULONG ByteCount
)
{
    EnsureInitialized();
    const ULONG frameCount = ByteCount / (sizeof(SHORT) * 2);
    const SHORT* samples = reinterpret_cast<const SHORT*>(Buffer);

    KIRQL oldIrql;
    KeAcquireSpinLock(&g_BridgeLock, &oldIrql);
    for (ULONG frame = 0; frame < frameCount; ++frame)
    {
        const LONG left = samples[frame * 2];
        const LONG right = samples[(frame * 2) + 1];
        g_Ring[g_WriteFrame % kRingFrames] = static_cast<SHORT>((left + right) / 2);
        ++g_WriteFrame;
    }
    KeReleaseSpinLock(&g_BridgeLock, oldIrql);
}

VOID VoxRescueBridgeReadMono16(
    _Out_writes_bytes_(ByteCount) UCHAR* Buffer,
    _In_ ULONG ByteCount,
    _Inout_ ULONGLONG* ReaderFrame
)
{
    EnsureInitialized();
    SHORT* samples = reinterpret_cast<SHORT*>(Buffer);
    const ULONG requestedFrames = ByteCount / sizeof(SHORT);
    ULONG copiedFrames = 0;

    KIRQL oldIrql;
    KeAcquireSpinLock(&g_BridgeLock, &oldIrql);

    if (*ReaderFrame > g_WriteFrame || (g_WriteFrame - *ReaderFrame) > kRingFrames)
    {
        *ReaderFrame = g_WriteFrame;
    }

    ULONGLONG availableFrames = g_WriteFrame - *ReaderFrame;
    if (availableFrames > kMaximumBacklogFrames)
    {
        *ReaderFrame = g_WriteFrame - kRecoveryBacklogFrames;
        availableFrames = kRecoveryBacklogFrames;
    }

    const ULONGLONG framesToCopy =
        availableFrames < requestedFrames ? availableFrames : requestedFrames;
    copiedFrames = static_cast<ULONG>(framesToCopy);
    for (ULONG frame = 0; frame < copiedFrames; ++frame)
    {
        samples[frame] = g_Ring[(*ReaderFrame + frame) % kRingFrames];
    }
    *ReaderFrame += copiedFrames;

    KeReleaseSpinLock(&g_BridgeLock, oldIrql);

    if (copiedFrames < requestedFrames)
    {
        RtlZeroMemory(samples + copiedFrames, (requestedFrames - copiedFrames) * sizeof(SHORT));
    }
    if ((ByteCount % sizeof(SHORT)) != 0)
    {
        Buffer[ByteCount - 1] = 0;
    }
}
