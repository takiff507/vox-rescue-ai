#include "pch.h"
#include "ProcessingController.h"

namespace VoxRescueNative
{
    void ProcessingController::Enabled(bool value) noexcept { m_enabled = value; }
    bool ProcessingController::Enabled() const noexcept { return m_enabled.load(); }
    void ProcessingController::Mode(ModelMode value) noexcept { m_mode = value; }
    ModelMode ProcessingController::Mode() const noexcept { return m_mode.load(); }

    std::wstring ProcessingController::ActiveModelFile() const
    {
        return Mode() == ModelMode::Legacy5K
            ? L"Models\\vox_rescue_5k.pt"
            : L"Models\\vox_rescue_universal_v3_step7000.pt";
    }
}
