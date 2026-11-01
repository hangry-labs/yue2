#pragma once
// FFmpeg is an external runtime dependency. Arguments never pass through a shell.
// Each operation owns a private temporary directory; seekable files also support M4A.
#include <chrono>
#include <cstdio>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <limits>
#include <random>
#include <string>
#include <thread>
#include <vector>

#ifdef _WIN32
#    ifndef NOMINMAX
#        define NOMINMAX
#    endif
#    include <windows.h>
#else
#    include <cerrno>
#    include <fcntl.h>
#    include <signal.h>
#    include <spawn.h>
#    include <sys/wait.h>
#    include <unistd.h>
extern char ** environ;
#endif

namespace yue_ffmpeg {
constexpr size_t MAX_BYTES = 512ULL * 1024 * 1024;
using Cancel = bool (*)(void *);

struct Files {
    std::filesystem::path directory;
    Files() {
        std::error_code error;
        auto root = std::filesystem::temp_directory_path(error);
        if (error) return;
        std::random_device random;
        for (int attempt = 0; attempt < 16; ++attempt) {
            auto candidate = root / ("yue2-audio-" + std::to_string(random()) + "-" + std::to_string(random()));
            if (!std::filesystem::create_directory(candidate, error)) continue;
            directory = candidate;
            std::filesystem::permissions(directory, std::filesystem::perms::owner_all,
                                         std::filesystem::perm_options::replace, error);
            if (error) { std::filesystem::remove(directory, error); directory.clear(); }
            return;
        }
    }
    Files(const Files &) = delete;
    Files & operator=(const Files &) = delete;
    ~Files() {
        if (!directory.empty()) {
            std::error_code error;
            std::filesystem::remove_all(directory, error);
        }
    }
    std::string path(const char * name) const {
        auto utf8 = (directory / name).u8string();
        return std::string(utf8.begin(), utf8.end());
    }
};

static std::filesystem::path utf8_path(const std::string & path) {
    return std::filesystem::path(std::u8string(path.begin(), path.end()));
}

static bool write(const std::string & path, const void * data, size_t size) {
    std::ofstream file(utf8_path(path), std::ios::binary);
    return file && bool(file.write(static_cast<const char *>(data), (std::streamsize) size));
}

static std::string read(const std::string & path, size_t limit = MAX_BYTES) {
    std::ifstream file(utf8_path(path), std::ios::binary | std::ios::ate);
    if (!file) return {};
    auto size = file.tellg();
    if (size <= 0 || (uint64_t) size >= limit) return {};
    std::string bytes((size_t) size, '\0');
    file.seekg(0);
    if (!file.read(bytes.data(), size)) return {};
    return bytes;
}

#ifdef _WIN32
static std::wstring wide(const std::string & value) {
    int count = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, value.data(), (int) value.size(), nullptr, 0);
    std::wstring result((size_t) count, L'\0');
    if (count) MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, value.data(), (int) value.size(), result.data(), count);
    return result;
}

static std::wstring quoted(const std::string & value) {
    std::wstring out = L"\"";
    size_t slashes = 0;
    for (wchar_t ch : wide(value)) {
        if (ch == L'\\') { ++slashes; continue; }
        out.append(ch == L'\"' ? slashes * 2 + 1 : slashes, L'\\');
        out += ch;
        slashes = 0;
    }
    out.append(slashes * 2, L'\\');
    return out + L'\"';
}
#endif

static bool run(const std::vector<std::string> & arguments, const std::string & errors,
                Cancel cancel = nullptr, void * opaque = nullptr, int timeout_seconds = 120) {
    if (cancel && cancel(opaque)) return false;
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(timeout_seconds);
    bool success = false;
#ifdef _WIN32
    SECURITY_ATTRIBUTES security{sizeof(SECURITY_ATTRIBUTES), nullptr, TRUE};
    HANDLE log = CreateFileW(wide(errors).c_str(), GENERIC_WRITE, FILE_SHARE_READ, &security,
                             CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    HANDLE null_file = CreateFileW(L"NUL", GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                   &security, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (log == INVALID_HANDLE_VALUE || null_file == INVALID_HANDLE_VALUE) {
        if (log != INVALID_HANDLE_VALUE) CloseHandle(log);
        if (null_file != INVALID_HANDLE_VALUE) CloseHandle(null_file);
        return false;
    }
    std::wstring line = L"ffmpeg";
    for (const auto & argument : arguments) line += L" " + quoted(argument);
    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdInput = null_file;
    startup.hStdOutput = null_file;
    startup.hStdError = log;
    PROCESS_INFORMATION process{};
    if (CreateProcessW(nullptr, line.data(), nullptr, nullptr, TRUE, CREATE_NO_WINDOW, nullptr, nullptr, &startup, &process)) {
        while (WaitForSingleObject(process.hProcess, 25) == WAIT_TIMEOUT) {
            if ((cancel && cancel(opaque)) || std::chrono::steady_clock::now() >= deadline) {
                TerminateProcess(process.hProcess, 1);
                WaitForSingleObject(process.hProcess, INFINITE);
                break;
            }
        }
        DWORD code = 1;
        GetExitCodeProcess(process.hProcess, &code);
        success = code == 0;
        CloseHandle(process.hThread);
        CloseHandle(process.hProcess);
    }
    CloseHandle(log);
    CloseHandle(null_file);
#else
    std::vector<char *> argv{const_cast<char *>("ffmpeg")};
    for (const auto & argument : arguments) argv.push_back(const_cast<char *>(argument.c_str()));
    argv.push_back(nullptr);
    posix_spawn_file_actions_t actions;
    if (posix_spawn_file_actions_init(&actions) != 0) return false;
    int setup = posix_spawn_file_actions_addopen(&actions, STDIN_FILENO, "/dev/null", O_RDONLY, 0);
    if (!setup) setup = posix_spawn_file_actions_addopen(&actions, STDOUT_FILENO, "/dev/null", O_WRONLY, 0);
    if (!setup) setup = posix_spawn_file_actions_addopen(&actions, STDERR_FILENO, errors.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (setup) { posix_spawn_file_actions_destroy(&actions); return false; }
    pid_t child = 0;
    int started = posix_spawnp(&child, "ffmpeg", &actions, nullptr, argv.data(), environ);
    posix_spawn_file_actions_destroy(&actions);
    if (started == 0) {
        for (;;) {
            int status = 0;
            pid_t result = waitpid(child, &status, WNOHANG);
            if (result == child) { success = WIFEXITED(status) && WEXITSTATUS(status) == 0; break; }
            if (result < 0 && errno != EINTR) break;
            if ((cancel && cancel(opaque)) || std::chrono::steady_clock::now() >= deadline) {
                kill(child, SIGKILL);
                while (waitpid(child, &status, 0) < 0 && errno == EINTR) {}
                break;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(25));
        }
    }
#endif
    if (!success) {
        // Do not print user-supplied paths or the whole FFmpeg command line.
        fprintf(stderr, "[Audio] FFmpeg failed, was cancelled, or exceeded its timeout. Check that ffmpeg is installed.\n");
    }
    return success;
}

static bool available() {
    Files files;
    return !files.directory.empty() && run({"-v", "error", "-version"}, files.path("stderr"), nullptr, nullptr, 5);
}
} // namespace yue_ffmpeg
