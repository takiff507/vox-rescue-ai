#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <Windows.h>
#include <bcrypt.h>
#include <dpapi.h>
#include <shlobj.h>

#include <algorithm>
#include <array>
#include <cstring>
#include <cstdint>
#include <limits>
#include <string>
#include <vector>

#include "model_key.generated.h"

#pragma comment(lib, "bcrypt.lib")
#pragma comment(lib, "crypt32.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "shell32.lib")

namespace {

constexpr std::array<std::uint8_t, 8> kMagic = {'V', 'X', 'V', 'R', 'M', '0', '0', '1'};
constexpr std::size_t kNonceSize = 12;
constexpr std::size_t kTagSize = 16;
constexpr std::size_t kHeaderSize = kMagic.size() + kNonceSize + kTagSize;

void set_windows_error(const char* action, DWORD error = GetLastError()) {
    PyErr_Format(PyExc_RuntimeError, "%s failed (Windows error %lu)", action,
                 static_cast<unsigned long>(error));
}

bool constant_time_equal(const std::uint8_t* left, const std::uint8_t* right,
                         std::size_t size) {
    std::uint8_t difference = 0;
    for (std::size_t index = 0; index < size; ++index) {
        difference |= left[index] ^ right[index];
    }
    return difference == 0;
}

std::array<std::uint8_t, 32> embedded_key() {
    std::array<std::uint8_t, 32> key{};
    for (std::size_t index = 0; index < key.size(); ++index) {
        key[index] = vox_model_key::kEncoded[index] ^ vox_model_key::kMaskA[index] ^
                     vox_model_key::kMaskB[index];
    }
    return key;
}

bool read_file(const std::wstring& path, std::vector<std::uint8_t>* contents) {
    HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr,
                              OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        set_windows_error("Opening protected model");
        return false;
    }
    LARGE_INTEGER size{};
    if (!GetFileSizeEx(file, &size) || size.QuadPart < 0 ||
        static_cast<unsigned long long>(size.QuadPart) >
            static_cast<unsigned long long>(std::numeric_limits<std::size_t>::max())) {
        set_windows_error("Reading protected model size");
        CloseHandle(file);
        return false;
    }
    contents->resize(static_cast<std::size_t>(size.QuadPart));
    std::size_t offset = 0;
    while (offset < contents->size()) {
        const DWORD request = static_cast<DWORD>(
            (std::min)(contents->size() - offset,
                       static_cast<std::size_t>(std::numeric_limits<DWORD>::max())));
        DWORD received = 0;
        if (!ReadFile(file, contents->data() + offset, request, &received, nullptr)) {
            set_windows_error("Reading protected model");
            CloseHandle(file);
            return false;
        }
        if (received == 0) {
            PyErr_SetString(PyExc_RuntimeError, "Protected model ended unexpectedly");
            CloseHandle(file);
            return false;
        }
        offset += received;
    }
    CloseHandle(file);
    return true;
}

bool write_new_file(const std::wstring& path, const BYTE* data, DWORD size) {
    HANDLE file = CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW,
                              FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        if (GetLastError() == ERROR_FILE_EXISTS) {
            return true;
        }
        set_windows_error("Creating protected key cache");
        return false;
    }
    DWORD written = 0;
    const bool ok = WriteFile(file, data, size, &written, nullptr) && written == size &&
                    FlushFileBuffers(file);
    const DWORD error = ok ? ERROR_SUCCESS : GetLastError();
    CloseHandle(file);
    if (!ok) {
        set_windows_error("Writing protected key cache", error);
    }
    return ok;
}

bool local_key_path(std::wstring* path) {
    PWSTR local_app_data = nullptr;
    const HRESULT result =
        SHGetKnownFolderPath(FOLDERID_LocalAppData, KF_FLAG_CREATE, nullptr, &local_app_data);
    if (FAILED(result) || local_app_data == nullptr) {
        PyErr_Format(PyExc_RuntimeError, "Locating LocalAppData failed (HRESULT 0x%08lx)",
                     static_cast<unsigned long>(result));
        return false;
    }
    std::wstring directory(local_app_data);
    CoTaskMemFree(local_app_data);
    directory += L"\\VoxRescue";
    if (!CreateDirectoryW(directory.c_str(), nullptr) &&
        GetLastError() != ERROR_ALREADY_EXISTS) {
        set_windows_error("Creating Vox Rescue data directory");
        return false;
    }
    *path = directory + L"\\" + vox_model_key::kKeyFileName;
    return true;
}

bool unprotect_cached_key(const std::wstring& path,
                          std::array<std::uint8_t, 32>* output) {
    std::vector<std::uint8_t> protected_blob;
    if (!read_file(path, &protected_blob)) {
        return false;
    }
    DATA_BLOB input{static_cast<DWORD>(protected_blob.size()), protected_blob.data()};
    DATA_BLOB entropy{static_cast<DWORD>(vox_model_key::kDpapiEntropy.size()),
                      const_cast<BYTE*>(vox_model_key::kDpapiEntropy.data())};
    DATA_BLOB clear{};
    if (!CryptUnprotectData(&input, nullptr, &entropy, nullptr, nullptr,
                            CRYPTPROTECT_UI_FORBIDDEN, &clear)) {
        set_windows_error("Unlocking protected model key");
        return false;
    }
    const bool valid = clear.cbData == output->size();
    if (valid) {
        memcpy(output->data(), clear.pbData, output->size());
    } else {
        PyErr_SetString(PyExc_RuntimeError, "Protected model key has an invalid size");
    }
    SecureZeroMemory(clear.pbData, clear.cbData);
    LocalFree(clear.pbData);
    return valid;
}

bool load_device_key(std::array<std::uint8_t, 32>* key) {
    std::wstring path;
    if (!local_key_path(&path)) {
        return false;
    }
    const DWORD attributes = GetFileAttributesW(path.c_str());
    if (attributes != INVALID_FILE_ATTRIBUTES) {
        return unprotect_cached_key(path, key);
    }

    auto bootstrap = embedded_key();
    DATA_BLOB clear{static_cast<DWORD>(bootstrap.size()), bootstrap.data()};
    DATA_BLOB entropy{static_cast<DWORD>(vox_model_key::kDpapiEntropy.size()),
                      const_cast<BYTE*>(vox_model_key::kDpapiEntropy.data())};
    DATA_BLOB protected_blob{};
    if (!CryptProtectData(&clear, L"Vox Rescue model key", &entropy, nullptr, nullptr,
                          CRYPTPROTECT_UI_FORBIDDEN, &protected_blob)) {
        set_windows_error("Protecting model key for this Windows user");
        SecureZeroMemory(bootstrap.data(), bootstrap.size());
        return false;
    }
    const bool stored = write_new_file(path, protected_blob.pbData, protected_blob.cbData);
    SecureZeroMemory(protected_blob.pbData, protected_blob.cbData);
    LocalFree(protected_blob.pbData);
    if (!stored) {
        SecureZeroMemory(bootstrap.data(), bootstrap.size());
        return false;
    }

    if (GetFileAttributesW(path.c_str()) != INVALID_FILE_ATTRIBUTES) {
        std::array<std::uint8_t, 32> cached{};
        if (!unprotect_cached_key(path, &cached)) {
            SecureZeroMemory(bootstrap.data(), bootstrap.size());
            return false;
        }
        if (!constant_time_equal(bootstrap.data(), cached.data(), bootstrap.size())) {
            PyErr_SetString(PyExc_RuntimeError, "Protected model key validation failed");
            SecureZeroMemory(bootstrap.data(), bootstrap.size());
            SecureZeroMemory(cached.data(), cached.size());
            return false;
        }
        *key = cached;
        SecureZeroMemory(cached.data(), cached.size());
    } else {
        *key = bootstrap;
    }
    SecureZeroMemory(bootstrap.data(), bootstrap.size());
    return true;
}

PyObject* decrypt_model(PyObject*, PyObject* args) {
    PyObject* path_object = nullptr;
    if (!PyArg_ParseTuple(args, "U:decrypt", &path_object)) {
        return nullptr;
    }
    Py_ssize_t path_length = 0;
    wchar_t* path_text = PyUnicode_AsWideCharString(path_object, &path_length);
    if (path_text == nullptr) {
        return nullptr;
    }
    std::wstring path(path_text, static_cast<std::size_t>(path_length));
    PyMem_Free(path_text);

    std::vector<std::uint8_t> container;
    if (!read_file(path, &container)) {
        return nullptr;
    }
    if (container.size() <= kHeaderSize ||
        !constant_time_equal(container.data(), kMagic.data(), kMagic.size())) {
        PyErr_SetString(PyExc_RuntimeError, "Protected model header is invalid");
        return nullptr;
    }
    const std::size_t ciphertext_size = container.size() - kHeaderSize;
    if (ciphertext_size > static_cast<std::size_t>(std::numeric_limits<ULONG>::max()) ||
        ciphertext_size > static_cast<std::size_t>(PY_SSIZE_T_MAX)) {
        PyErr_SetString(PyExc_OverflowError, "Protected model is too large");
        return nullptr;
    }

    std::array<std::uint8_t, 32> key{};
    if (!load_device_key(&key)) {
        SecureZeroMemory(key.data(), key.size());
        return nullptr;
    }

    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_KEY_HANDLE symmetric_key = nullptr;
    std::vector<std::uint8_t> key_object;
    PyObject* plaintext = nullptr;
    NTSTATUS status = BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_AES_ALGORITHM, nullptr, 0);
    if (status >= 0) {
        status = BCryptSetProperty(
            algorithm, BCRYPT_CHAINING_MODE,
            reinterpret_cast<PUCHAR>(const_cast<wchar_t*>(BCRYPT_CHAIN_MODE_GCM)),
            sizeof(BCRYPT_CHAIN_MODE_GCM), 0);
    }
    DWORD object_size = 0;
    DWORD returned = 0;
    if (status >= 0) {
        status = BCryptGetProperty(algorithm, BCRYPT_OBJECT_LENGTH,
                                   reinterpret_cast<PUCHAR>(&object_size), sizeof(object_size),
                                   &returned, 0);
    }
    if (status >= 0) {
        key_object.resize(object_size);
        status = BCryptGenerateSymmetricKey(
            algorithm, &symmetric_key, key_object.data(), object_size, key.data(),
            static_cast<ULONG>(key.size()), 0);
    }
    if (status >= 0) {
        plaintext = PyByteArray_FromStringAndSize(nullptr,
                                                  static_cast<Py_ssize_t>(ciphertext_size));
        if (plaintext == nullptr) {
            status = static_cast<NTSTATUS>(0xC0000017L);
        }
    }
    ULONG clear_size = 0;
    if (status >= 0) {
        BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO authentication{};
        BCRYPT_INIT_AUTH_MODE_INFO(authentication);
        authentication.pbNonce = container.data() + kMagic.size();
        authentication.cbNonce = static_cast<ULONG>(kNonceSize);
        authentication.pbTag = container.data() + kMagic.size() + kNonceSize;
        authentication.cbTag = static_cast<ULONG>(kTagSize);
        authentication.pbAuthData = container.data();
        authentication.cbAuthData = static_cast<ULONG>(kMagic.size());
        status = BCryptDecrypt(
            symmetric_key, container.data() + kHeaderSize,
            static_cast<ULONG>(ciphertext_size), &authentication, nullptr, 0,
            reinterpret_cast<PUCHAR>(PyByteArray_AS_STRING(plaintext)),
            static_cast<ULONG>(ciphertext_size), &clear_size, 0);
    }

    if (symmetric_key != nullptr) {
        BCryptDestroyKey(symmetric_key);
    }
    if (algorithm != nullptr) {
        BCryptCloseAlgorithmProvider(algorithm, 0);
    }
    SecureZeroMemory(key.data(), key.size());
    if (!key_object.empty()) {
        SecureZeroMemory(key_object.data(), key_object.size());
    }
    if (status < 0 || clear_size != ciphertext_size) {
        Py_XDECREF(plaintext);
        PyErr_SetString(PyExc_RuntimeError,
                        "Protected model authentication or decryption failed");
        return nullptr;
    }
    return plaintext;
}

PyMethodDef kMethods[] = {
    {"decrypt", decrypt_model, METH_VARARGS,
     "Decrypt and authenticate a Vox Rescue model into a mutable memory buffer."},
    {nullptr, nullptr, 0, nullptr},
};

PyModuleDef kModule = {
    PyModuleDef_HEAD_INIT,
    "model_guard",
    "Native Windows protection for the Vox Rescue model.",
    -1,
    kMethods,
};

}  // namespace

PyMODINIT_FUNC PyInit_model_guard() { return PyModule_Create(&kModule); }
