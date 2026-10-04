#include "pch.h"
#include "App.xaml.h"
#include "MainWindow.xaml.h"

namespace winrt::VoxRescueNative::implementation
{
    App::App()
    {
        UnhandledException([](IInspectable const&, Microsoft::UI::Xaml::UnhandledExceptionEventArgs const& args)
        {
            std::wofstream log{ std::filesystem::path{ L"vox_rescue_startup_error.txt" }, std::ios::trunc };
            log << L"HRESULT: 0x" << std::hex << static_cast<uint32_t>(args.Exception().value) << L"\n";
            log << args.Message().c_str() << L"\n";
            args.Handled(true);
        });
        InitializeComponent();
    }

    void App::OnLaunched(Microsoft::UI::Xaml::LaunchActivatedEventArgs const&)
    {
        m_window = winrt::make<MainWindow>();
        m_window.Activate();
    }
}
