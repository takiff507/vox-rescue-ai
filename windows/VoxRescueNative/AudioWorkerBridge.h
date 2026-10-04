#pragma once

namespace VoxRescueNative
{
    class AudioWorkerBridge final
    {
    public:
        using LineHandler = std::function<void(std::wstring const&)>;

        explicit AudioWorkerBridge(LineHandler handler);
        ~AudioWorkerBridge();
        AudioWorkerBridge(AudioWorkerBridge const&) = delete;
        AudioWorkerBridge& operator=(AudioWorkerBridge const&) = delete;

        bool Start();
        void Stop() noexcept;
        bool Send(std::wstring const& command) noexcept;
        bool Running() const noexcept;

    private:
        void ReadLoop();
        void Notify(std::wstring const& line) const;
        static std::filesystem::path ExecutableDirectory();
        static std::filesystem::path FindPython();

        LineHandler m_handler;
        HANDLE m_process{ nullptr };
        HANDLE m_threadHandle{ nullptr };
        HANDLE m_stdinWrite{ nullptr };
        HANDLE m_stdoutRead{ nullptr };
        std::thread m_reader;
        std::mutex m_writeMutex;
        std::atomic_bool m_stopping{ false };
    };
}
