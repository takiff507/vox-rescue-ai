#include <windows.h>
#include <newdev.h>
#include <setupapi.h>

#include <cwchar>
#include <iostream>
#include <string>
#include <vector>

#pragma comment(lib, "newdev.lib")
#pragma comment(lib, "setupapi.lib")

namespace
{
    constexpr wchar_t kHardwareId[] = L"Root\\VoxRescueVirtualAudio";
    constexpr int kRebootRequired = 3010;

    std::wstring FullPath(const wchar_t* path)
    {
        const DWORD required = GetFullPathNameW(path, 0, nullptr, nullptr);
        if (required == 0)
        {
            return {};
        }
        std::wstring result(required, L'\0');
        const DWORD written = GetFullPathNameW(path, required, result.data(), nullptr);
        if (written == 0 || written >= required)
        {
            return {};
        }
        result.resize(written);
        return result;
    }

    void PrintLastError(const wchar_t* operation)
    {
        const DWORD error = GetLastError();
        wchar_t* message = nullptr;
        FormatMessageW(
            FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM |
                FORMAT_MESSAGE_IGNORE_INSERTS,
            nullptr,
            error,
            0,
            reinterpret_cast<wchar_t*>(&message),
            0,
            nullptr);
        std::wcerr << operation << L" failed (" << error << L")";
        if (message != nullptr)
        {
            std::wcerr << L": " << message;
            LocalFree(message);
        }
        else
        {
            std::wcerr << L'\n';
        }
    }

    bool IsAdministrator()
    {
        SID_IDENTIFIER_AUTHORITY authority = SECURITY_NT_AUTHORITY;
        PSID administrators = nullptr;
        BOOL isMember = FALSE;
        if (!AllocateAndInitializeSid(
                &authority,
                2,
                SECURITY_BUILTIN_DOMAIN_RID,
                DOMAIN_ALIAS_RID_ADMINS,
                0,
                0,
                0,
                0,
                0,
                0,
                &administrators))
        {
            return false;
        }
        const BOOL checked = CheckTokenMembership(nullptr, administrators, &isMember);
        FreeSid(administrators);
        return checked && isMember;
    }

    bool DeviceHasHardwareId(HDEVINFO deviceSet, SP_DEVINFO_DATA& device)
    {
        DWORD type = 0;
        DWORD required = 0;
        SetupDiGetDeviceRegistryPropertyW(
            deviceSet,
            &device,
            SPDRP_HARDWAREID,
            &type,
            nullptr,
            0,
            &required);
        if (required == 0)
        {
            return false;
        }

        std::vector<BYTE> buffer(required);
        if (!SetupDiGetDeviceRegistryPropertyW(
                deviceSet,
                &device,
                SPDRP_HARDWAREID,
                &type,
                buffer.data(),
                required,
                nullptr))
        {
            return false;
        }

        const wchar_t* current = reinterpret_cast<const wchar_t*>(buffer.data());
        const wchar_t* end = reinterpret_cast<const wchar_t*>(buffer.data() + buffer.size());
        while (current < end && *current != L'\0')
        {
            if (_wcsicmp(current, kHardwareId) == 0)
            {
                return true;
            }
            current += std::wcslen(current) + 1;
        }
        return false;
    }

    template <typename Callback>
    bool ForEachVoxDevice(Callback callback, DWORD* matchCount = nullptr)
    {
        HDEVINFO deviceSet = SetupDiGetClassDevsW(
            nullptr,
            nullptr,
            nullptr,
            DIGCF_ALLCLASSES);
        if (deviceSet == INVALID_HANDLE_VALUE)
        {
            PrintLastError(L"SetupDiGetClassDevs");
            return false;
        }

        DWORD matches = 0;
        bool result = true;
        for (DWORD index = 0;; ++index)
        {
            SP_DEVINFO_DATA device = {};
            device.cbSize = sizeof(device);
            if (!SetupDiEnumDeviceInfo(deviceSet, index, &device))
            {
                if (GetLastError() != ERROR_NO_MORE_ITEMS)
                {
                    PrintLastError(L"SetupDiEnumDeviceInfo");
                    result = false;
                }
                break;
            }
            if (DeviceHasHardwareId(deviceSet, device))
            {
                ++matches;
                if (!callback(deviceSet, device))
                {
                    result = false;
                }
            }
        }

        SetupDiDestroyDeviceInfoList(deviceSet);
        if (matchCount != nullptr)
        {
            *matchCount = matches;
        }
        return result;
    }

    bool RemoveDevice(HDEVINFO deviceSet, SP_DEVINFO_DATA& device, bool* reboot)
    {
        SP_REMOVEDEVICE_PARAMS params = {};
        params.ClassInstallHeader.cbSize = sizeof(SP_CLASSINSTALL_HEADER);
        params.ClassInstallHeader.InstallFunction = DIF_REMOVE;
        params.Scope = DI_REMOVEDEVICE_GLOBAL;

        if (!SetupDiSetClassInstallParamsW(
                deviceSet,
                &device,
                &params.ClassInstallHeader,
                sizeof(params)) ||
            !SetupDiCallClassInstaller(DIF_REMOVE, deviceSet, &device))
        {
            PrintLastError(L"Remove Vox Rescue virtual audio device");
            return false;
        }

        SP_DEVINSTALL_PARAMS_W installParams = {};
        installParams.cbSize = sizeof(installParams);
        if (SetupDiGetDeviceInstallParamsW(deviceSet, &device, &installParams) &&
            (installParams.Flags & (DI_NEEDREBOOT | DI_NEEDRESTART)) != 0)
        {
            *reboot = true;
        }
        return true;
    }

    bool CreateRootDevice(const std::wstring& infPath, HDEVINFO* createdSet, SP_DEVINFO_DATA* createdDevice)
    {
        GUID classGuid = {};
        wchar_t className[MAX_PATH] = {};
        if (!SetupDiGetINFClassW(
                infPath.c_str(),
                &classGuid,
                className,
                ARRAYSIZE(className),
                nullptr))
        {
            PrintLastError(L"Read driver INF class");
            return false;
        }

        HDEVINFO deviceSet = SetupDiCreateDeviceInfoList(&classGuid, nullptr);
        if (deviceSet == INVALID_HANDLE_VALUE)
        {
            PrintLastError(L"Create device information list");
            return false;
        }

        SP_DEVINFO_DATA device = {};
        device.cbSize = sizeof(device);
        if (!SetupDiCreateDeviceInfoW(
                deviceSet,
                className,
                &classGuid,
                L"Vox Rescue Virtual Audio",
                nullptr,
                DICD_GENERATE_ID,
                &device))
        {
            PrintLastError(L"Create Vox Rescue virtual audio device");
            SetupDiDestroyDeviceInfoList(deviceSet);
            return false;
        }

        wchar_t hardwareIds[ARRAYSIZE(kHardwareId) + 1] = {};
        wcscpy_s(hardwareIds, ARRAYSIZE(hardwareIds), kHardwareId);
        if (!SetupDiSetDeviceRegistryPropertyW(
                deviceSet,
                &device,
                SPDRP_HARDWAREID,
                reinterpret_cast<const BYTE*>(hardwareIds),
                sizeof(hardwareIds)) ||
            !SetupDiCallClassInstaller(DIF_REGISTERDEVICE, deviceSet, &device))
        {
            PrintLastError(L"Register Vox Rescue virtual audio device");
            SetupDiDestroyDeviceInfoList(deviceSet);
            return false;
        }

        *createdSet = deviceSet;
        *createdDevice = device;
        return true;
    }

    int Install(const std::wstring& infPath)
    {
        DWORD existing = 0;
        if (!ForEachVoxDevice([](HDEVINFO, SP_DEVINFO_DATA&) { return true; }, &existing))
        {
            return 1;
        }

        HDEVINFO createdSet = INVALID_HANDLE_VALUE;
        SP_DEVINFO_DATA createdDevice = {};
        if (existing == 0 && !CreateRootDevice(infPath, &createdSet, &createdDevice))
        {
            return 1;
        }

        BOOL reboot = FALSE;
        if (!UpdateDriverForPlugAndPlayDevicesW(
                nullptr,
                kHardwareId,
                infPath.c_str(),
                INSTALLFLAG_FORCE,
                &reboot))
        {
            PrintLastError(L"Install Vox Rescue virtual audio driver");
            if (createdSet != INVALID_HANDLE_VALUE)
            {
                bool ignoredReboot = false;
                RemoveDevice(createdSet, createdDevice, &ignoredReboot);
            }
            if (createdSet != INVALID_HANDLE_VALUE)
            {
                SetupDiDestroyDeviceInfoList(createdSet);
            }
            return 1;
        }

        if (createdSet != INVALID_HANDLE_VALUE)
        {
            SetupDiDestroyDeviceInfoList(createdSet);
        }
        std::wcout << L"Vox Rescue virtual microphone installed.\n";
        return reboot ? kRebootRequired : 0;
    }

    int Remove(const std::wstring& infPath)
    {
        bool reboot = false;
        DWORD removed = 0;
        const bool devicesRemoved = ForEachVoxDevice(
            [&reboot](HDEVINFO set, SP_DEVINFO_DATA& device) {
                return RemoveDevice(set, device, &reboot);
            },
            &removed);

        BOOL packageReboot = FALSE;
        if (!DiUninstallDriverW(nullptr, infPath.c_str(), 0, &packageReboot))
        {
            const DWORD error = GetLastError();
            if (error != ERROR_NOT_FOUND && error != ERROR_FILE_NOT_FOUND)
            {
                PrintLastError(L"Remove Vox Rescue driver package");
                return 1;
            }
        }
        reboot = reboot || packageReboot;

        if (!devicesRemoved)
        {
            return 1;
        }
        std::wcout << L"Vox Rescue virtual microphone removed (" << removed << L" device(s)).\n";
        return reboot ? kRebootRequired : 0;
    }
}

int wmain(int argc, wchar_t* argv[])
{
    if (argc < 2)
    {
        std::wcerr << L"Usage: VoxRescueDeviceTool <install|remove|status> [driver.inf]\n";
        return 2;
    }
    if (!IsAdministrator())
    {
        std::wcerr << L"Administrator access is required.\n";
        return ERROR_ACCESS_DENIED;
    }

    if (_wcsicmp(argv[1], L"status") == 0)
    {
        DWORD count = 0;
        if (!ForEachVoxDevice([](HDEVINFO, SP_DEVINFO_DATA&) { return true; }, &count))
        {
            return 1;
        }
        std::wcout << (count > 0 ? L"installed\n" : L"not-installed\n");
        return count > 0 ? 0 : 3;
    }

    if (argc < 3)
    {
        std::wcerr << L"A fully qualified driver INF path is required.\n";
        return 2;
    }
    const std::wstring infPath = FullPath(argv[2]);
    if (infPath.empty() || GetFileAttributesW(infPath.c_str()) == INVALID_FILE_ATTRIBUTES)
    {
        std::wcerr << L"Driver INF was not found.\n";
        return ERROR_FILE_NOT_FOUND;
    }

    if (_wcsicmp(argv[1], L"install") == 0)
    {
        return Install(infPath);
    }
    if (_wcsicmp(argv[1], L"remove") == 0)
    {
        return Remove(infPath);
    }

    std::wcerr << L"Unknown command.\n";
    return 2;
}
