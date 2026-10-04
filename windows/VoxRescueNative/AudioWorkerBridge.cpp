#include "pch.h"
#include "AudioWorkerBridge.h"

namespace VoxRescueNative
{
    namespace
    {
        std::wstring DecodeWorkerText(std::string const& text)
        {
            UINT codePage = CP_UTF8;
            DWORD flags = MB_ERR_INVALID_CHARS;
            int size = MultiByteToWideChar(codePage, flags, text.data(), static_cast<int>(text.size()), nullptr, 0);
            if (size <= 0)
            {
                codePage = CP_ACP;
                flags = 0;
                size = MultiByteToWideChar(codePage, flags, text.data(), static_cast<int>(text.size()), nullptr, 0);
            }
            if (size <= 0) return L"";
            std::wstring result(static_cast<size_t>(size), L'\0');
            MultiByteToWideChar(codePage, flags, text.data(), static_cast<int>(text.size()), result.data(), size);
            return result;
        }
    }

    AudioWorkerBridge::AudioWorkerBridge(LineHandler handler) : m_handler(std::move(handler)) {}

    AudioWorkerBridge::~AudioWorkerBridge()
    {
        Stop();
    }

    std::filesystem::path AudioWorkerBridge::ExecutableDirectory()
    {
        std::wstring path(32768, L'\0');
        const DWORD length = GetModuleFileNameW(nullptr, path.data(), static_cast<DWORD>(path.size()));
        if (length == 0 || length >= path.size())
        {
            return {};
        }
        path.resize(length);
        return std::filesystem::path(path).parent_path();
    }

    std::filesystem::path AudioWorkerBridge::FindPython()
    {
        for (auto const* name : { L"pythonw.exe", L"python.exe" })
        {
            std::wstring path(32768, L'\0');
            const DWORD length = SearchPathW(nullptr, name, nullptr, static_cast<DWORD>(path.size()), path.data(), nullptr);
            if (length > 0 && length < path.size())
            {
                path.resize(length);
                return path;
            }
        }
        return {};
    }

    bool AudioWorkerBridge::Start()
    {
        if (Running())
        {
            return true;
        }

        const auto root = ExecutableDirectory();
        const auto worker = root / L"Scripts" / L"audio_worker.py";
        const auto python = FindPython();
        if (python.empty() || !std::filesystem::exists(worker))
        {
            Notify(L"ERROR\tAudio runtime is not installed");
            return false;
        }

        SECURITY_ATTRIBUTES security{ sizeof(SECURITY_ATTRIBUTES), nullptr, TRUE };
        HANDLE stdoutWrite{};
        HANDLE stdinRead{};
        if (!CreatePipe(&m_stdoutRead, &stdoutWrite, &security, 0) ||
            !SetHandleInformation(m_stdoutRead, HANDLE_FLAG_INHERIT, 0) ||
            !CreatePipe(&stdinRead, &m_stdinWrite, &security, 0) ||
            !SetHandleInformation(m_stdinWrite, HANDLE_FLAG_INHERIT, 0))
        {
            if (stdoutWrite) CloseHandle(stdoutWrite);
            if (stdinRead) CloseHandle(stdinRead);
            Stop();
            Notify(L"ERROR\tCould not create the audio runtime pipes");
            return false;
        }

        std::wstring command = L"\"" + python.wstring() + L"\" \"" + worker.wstring() +
            L"\" --root \"" + root.wstring() + L"\"";
        std::vector<wchar_t> mutableCommand(command.begin(), command.end());
        mutableCommand.push_back(L'\0');

        STARTUPINFOW startup{};
        startup.cb = sizeof(startup);
        startup.dwFlags = STARTF_USESTDHANDLES;
        startup.hStdInput = stdinRead;
        startup.hStdOutput = stdoutWrite;
        startup.hStdError = stdoutWrite;
        PROCESS_INFORMATION process{};
        const BOOL created = CreateProcessW(
            python.c_str(), mutableCommand.data(), nullptr, nullptr, TRUE,
            CREATE_NO_WINDOW, nullptr, root.c_str(), &startup, &process);
        CloseHandle(stdinRead);
        CloseHandle(stdoutWrite);

        if (!created)
        {
            Stop();
            Notify(L"ERROR\tCould not start the audio runtime");
            return false;
        }

        m_process = process.hProcess;
        m_threadHandle = process.hThread;
        m_stopping = false;
        m_reader = std::thread(&AudioWorkerBridge::ReadLoop, this);
        return true;
    }

    bool AudioWorkerBridge::Running() const noexcept
    {
        return m_process && WaitForSingleObject(m_process, 0) == WAIT_TIMEOUT;
    }

    bool AudioWorkerBridge::Send(std::wstring const& command) noexcept
    {
        std::scoped_lock lock(m_writeMutex);
        if (!m_stdinWrite || !Running())
        {
            return false;
        }
        const std::string utf8 = winrt::to_string(command + L"\n");
        DWORD written{};
        return WriteFile(m_stdinWrite, utf8.data(), static_cast<DWORD>(utf8.size()), &written, nullptr) &&
            written == utf8.size();
    }

    void AudioWorkerBridge::Stop() noexcept
    {
        if (m_stopping.exchange(true))
        {
            return;
        }
        Send(L"QUIT");
        if (m_stdinWrite)
        {
            CloseHandle(m_stdinWrite);
            m_stdinWrite = nullptr;
        }
        if (m_process && WaitForSingleObject(m_process, 3000) == WAIT_TIMEOUT)
        {
            TerminateProcess(m_process, 0);
        }
        if (m_stdoutRead)
        {
            CloseHandle(m_stdoutRead);
            m_stdoutRead = nullptr;
        }
        if (m_reader.joinable())
        {
            m_reader.join();
        }
        if (m_threadHandle)
        {
            CloseHandle(m_threadHandle);
            m_threadHandle = nullptr;
        }
        if (m_process)
        {
            CloseHandle(m_process);
            m_process = nullptr;
        }
    }

    void AudioWorkerBridge::ReadLoop()
    {
        try
        {
            std::string pending;
            std::array<char, 2048> buffer{};
            while (!m_stopping && m_stdoutRead)
            {
                DWORD read{};
                if (!ReadFile(m_stdoutRead, buffer.data(), static_cast<DWORD>(buffer.size()), &read, nullptr) || read == 0)
                {
                    break;
                }
                pending.append(buffer.data(), read);
                for (;;)
                {
                    const auto newline = pending.find('\n');
                    if (newline == std::string::npos)
                    {
                        break;
                    }
                    auto line = pending.substr(0, newline);
                    pending.erase(0, newline + 1);
                    if (!line.empty() && line.back() == '\r') line.pop_back();
                    if (!line.empty()) Notify(DecodeWorkerText(line));
                }
            }
        }
        catch (...) {}
    }

    void AudioWorkerBridge::Notify(std::wstring const& line) const
    {
        if (m_handler)
        {
            try { m_handler(line); } catch (...) {}
        }
    }
}
