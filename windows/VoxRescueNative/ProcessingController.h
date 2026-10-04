#pragma once

namespace VoxRescueNative
{
    enum class ModelMode
    {
        V3,
        Legacy5K,
    };

    class ProcessingController final
    {
    public:
        void Enabled(bool value) noexcept;
        bool Enabled() const noexcept;
        void Mode(ModelMode value) noexcept;
        ModelMode Mode() const noexcept;
        std::wstring ActiveModelFile() const;

    private:
        std::atomic_bool m_enabled{ false };
        std::atomic<ModelMode> m_mode{ ModelMode::V3 };
    };
}
