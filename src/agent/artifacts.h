#pragma once
// Capability-addressed, bounded temporary exports. No model or inference state.
#include "json.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <functional>
#include <mutex>
#include <regex>
#include <vector>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <bcrypt.h>
#endif

namespace yue_agent {
inline constexpr int LINK_TTL = 3600;
inline int64_t now_seconds() {
    return std::chrono::duration_cast<std::chrono::seconds>(std::chrono::system_clock::now().time_since_epoch()).count();
}
inline std::string token() {
    std::array<unsigned char, 32> bytes{};
#ifdef _WIN32
    if (BCryptGenRandom(nullptr, bytes.data(), (ULONG) bytes.size(), BCRYPT_USE_SYSTEM_PREFERRED_RNG) != 0)
        throw std::runtime_error("OS random generator unavailable");
#else
    std::ifstream random("/dev/urandom", std::ios::binary);
    if (!random.read((char *) bytes.data(), bytes.size())) throw std::runtime_error("OS random generator unavailable");
#endif
    std::string value;
    for (auto byte : bytes) { value += "0123456789abcdef"[byte >> 4]; value += "0123456789abcdef"[byte & 15]; }
    return value;
}
inline bool valid_token(const std::string & value) {
    return value.size() == 64 && value.find_first_not_of("0123456789abcdef") == std::string::npos;
}
inline std::string utc(int64_t seconds) {
    std::time_t time = (std::time_t) seconds;
    std::tm tm{};
#ifdef _WIN32
    gmtime_s(&tm, &time);
#else
    gmtime_r(&time, &tm);
#endif
    char result[32]; std::strftime(result, sizeof(result), "%Y-%m-%dT%H:%M:%SZ", &tm); return result;
}
struct Artifact {
    std::string id, format;
    int64_t expires = 0;
    size_t size = 0;
    double duration = 0;
    const char * mime() const { return format == "opus" ? "audio/ogg" : "audio/flac"; }
    std::string metadata(const std::string & base) const {
        Json j; j.text("job_id", id); j.text("status", "complete"); j.text("format", format);
        j.text("url", base + "/artifacts/" + id + "/song." + format);
        j.text("mime_type", mime()); j.integer("size_bytes", (int64_t) size);
        j.number("duration_seconds", duration); j.integer("sample_rate", 48000); j.integer("channels", 2);
        j.integer("ttl_seconds", LINK_TTL); j.text("expires_at", utc(expires)); return j.dump();
    }
};
class Artifacts {
    std::filesystem::path root_;
    std::function<int64_t()> clock_;
    std::mutex mutex_;
    static constexpr size_t MAX_FILE = 512ULL * 1024 * 1024;
    static constexpr size_t MAX_BYTES = 2ULL * 1024 * 1024 * 1024;
    static constexpr size_t MAX_FILES = 128;
    bool regular(const std::filesystem::path & p) const {
        return std::filesystem::is_regular_file(std::filesystem::symlink_status(p));
    }
    bool read_locked(const std::string & id, Artifact & a, bool expired = false) const {
        if (!valid_token(id)) return false;
        auto meta = root_ / (id + ".json");
        if (!regular(meta) || std::filesystem::file_size(meta) > 4096) return false;
        std::ifstream in(meta, std::ios::binary);
        auto doc = parse(std::string(std::istreambuf_iterator<char>(in), {}));
        if (!doc) return false;
        auto * r = yyjson_doc_get_root(doc.get());
        a.id = id; a.format = field(r, "format");
        a.expires = yyjson_get_sint(yyjson_obj_get(r, "expires"));
        a.size = (size_t) yyjson_get_uint(yyjson_obj_get(r, "size"));
        a.duration = yyjson_get_num(yyjson_obj_get(r, "duration"));
        if ((a.format != "opus" && a.format != "flac") || !a.size || a.size > MAX_FILE ||
            (!expired && clock_() >= a.expires)) return false;
        auto path = root_ / (id + "." + a.format);
        return regular(path) && std::filesystem::file_size(path) == a.size;
    }
    void cleanup_locked() {
        // Only remove our precisely named files, never arbitrary output contents.
        for (const auto & entry : std::filesystem::directory_iterator(root_)) {
            auto name = entry.path().filename().string();
            auto dot = name.find('.');
            if (dot == std::string::npos || !valid_token(name.substr(0, dot))) continue;
            auto ext = name.substr(dot);
            if (ext != ".opus" && ext != ".flac" && ext != ".json" && ext != ".part") continue;
            Artifact a;
            if (read_locked(name.substr(0, dot), a, true) && a.expires > clock_()) continue;
            std::error_code error; std::filesystem::remove(entry.path(), error);
        }
    }
public:
    explicit Artifacts(std::filesystem::path root, std::function<int64_t()> clock = now_seconds)
        : root_(std::filesystem::absolute(root)), clock_(std::move(clock)) {
        std::filesystem::create_directories(root_);
        if (std::filesystem::is_symlink(std::filesystem::symlink_status(root_)))
            throw std::runtime_error("Artifact directory must not be a symlink");
        std::filesystem::permissions(root_, std::filesystem::perms::owner_all, std::filesystem::perm_options::replace);
        cleanup();
    }
    std::filesystem::path path(const Artifact & a) const { return root_ / (a.id + "." + a.format); }
    void cleanup() { std::lock_guard<std::mutex> lock(mutex_); cleanup_locked(); }
    bool find(const std::string & id, Artifact & a) {
        std::lock_guard<std::mutex> lock(mutex_); return read_locked(id, a);
    }
    Artifact save(const std::string & id, const std::string & format, const std::string & body, double duration) {
        std::lock_guard<std::mutex> lock(mutex_);
        cleanup_locked();
        if (!valid_token(id) || (format != "opus" && format != "flac") || body.empty() || body.size() > MAX_FILE)
            throw std::runtime_error("Invalid or oversized export");
        size_t count = 0, bytes = 0;
        for (const auto & entry : std::filesystem::directory_iterator(root_)) {
            Artifact existing;
            if (entry.path().extension() == ".json" && read_locked(entry.path().stem().string(), existing)) {
                ++count; bytes += existing.size;
            }
        }
        if (count >= MAX_FILES || bytes > MAX_BYTES || body.size() > MAX_BYTES - bytes)
            throw std::runtime_error("Temporary export storage is full; existing links are retained until expiry");
        Artifact a{id, format, clock_() + LINK_TTL, body.size(), duration};
        auto staging = root_ / (id + ".part");
        auto write = [&](const std::filesystem::path & dest, const std::string & data) {
            if (std::filesystem::exists(dest)) throw std::runtime_error("Export already exists");
            std::ofstream out(staging, std::ios::binary | std::ios::trunc);
            out.write(data.data(), (std::streamsize) data.size()); out.close();
            if (!out) throw std::runtime_error("Could not write temporary export");
            std::filesystem::rename(staging, dest);
        };
        write(path(a), body);
        Json meta; meta.text("format", format); meta.integer("expires", a.expires);
        meta.integer("size", (int64_t) a.size); meta.number("duration", duration);
        try { write(root_ / (id + ".json"), meta.dump()); }
        catch (...) { std::filesystem::remove(path(a)); throw; }
        return a;
    }
};
}
