#pragma once

#include "MainWindow.g.h"
#include "AudioWorkerBridge.h"
#include "ProcessingController.h"

namespace winrt::VoxRescueNative::implementation
{
    struct MainWindow : MainWindowT<MainWindow>
    {
        MainWindow();
        ~MainWindow();

        void OnMainSwitchToggled(IInspectable const&, Microsoft::UI::Xaml::RoutedEventArgs const&);
        void OnReturnToggled(IInspectable const&, Microsoft::UI::Xaml::RoutedEventArgs const&);
        void OnRefreshClicked(IInspectable const&, Microsoft::UI::Xaml::RoutedEventArgs const&);

    private:
        void ConfigureWindow();
        void ConfigureTrayIcon(HWND hwnd);
        void RemoveTrayIcon() noexcept;
        void ShowFromTray() noexcept;
        static LRESULT CALLBACK WindowSubclassProc(HWND hwnd, UINT message, WPARAM wParam, LPARAM lParam,
                                                    UINT_PTR subclassId, DWORD_PTR referenceData);
        void OnWorkerLine(std::wstring const& line);
        ::VoxRescueNative::ProcessingController m_controller;
        std::unique_ptr<::VoxRescueNative::AudioWorkerBridge> m_audio;
        HWND m_hwnd{};
        NOTIFYICONDATAW m_trayIcon{};
        bool m_exitRequested{ false };
    };
}

namespace winrt::VoxRescueNative::factory_implementation
{
    struct MainWindow : MainWindowT<MainWindow, implementation::MainWindow> {};
}
