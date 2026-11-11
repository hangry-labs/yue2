#pragma once
// Disk-backed native job results. Only small immutable metadata is indexed in RAM.
#include "agent/artifacts.h"
#include <array>
#include <map>
#include <limits>

namespace yue_server {
using yue_agent::Json;
inline bool job_id_valid(const std::string & id) {
    return id.size() == 16 && id.find_first_not_of("0123456789abcdef") == std::string::npos;
}
struct StorageFull : std::runtime_error { using std::runtime_error::runtime_error; };
struct Result {
    std::string id, mime, metrics, generations;
    std::filesystem::path path;
    uint64_t size = 0;
    int64_t expires = 0;
};
struct StorageLimits {
    int64_t ttl = 86400;
    uint64_t bytes = 10ULL * 1024 * 1024 * 1024;
    uint64_t file_bytes = 1024ULL * 1024 * 1024;
    size_t files = 256;
};
class Results {
    std::filesystem::path root_;
    StorageLimits limits_;
    std::function<int64_t()> clock_;
    mutable std::mutex mutex_;
    std::map<std::string, std::shared_ptr<Result>> files_;
    uint64_t bytes_ = 0;
    bool writing_ = false;
    static bool regular(const std::filesystem::path & p) {
        std::error_code ec;
        return std::filesystem::is_regular_file(std::filesystem::symlink_status(p, ec));
    }
    void remove_owned(const std::string & id) {
        for (auto ext : {".bin", ".json", ".part", ".meta-part"}) {
            std::error_code ec;
            std::filesystem::remove(root_ / (id + ext), ec);
        }
    }
    void cleanup_locked() {
        for (auto it = files_.begin(); it != files_.end();) {
            // A download owns a lease. Expiry refuses new readers immediately,
            // but does not delete bytes beneath an existing download.
            if (it->second->expires <= clock_() && it->second.use_count() == 1) {
                remove_owned(it->first); bytes_ -= it->second->size; it = files_.erase(it);
            } else ++it;
        }
    }
    void restore() {
        for (const auto & entry : std::filesystem::directory_iterator(root_)) {
            auto id = entry.path().stem().string();
            if (entry.path().extension() != ".json" || !job_id_valid(id) || !regular(entry.path())) continue;
            if (std::filesystem::file_size(entry.path()) > 1024 * 1024) continue;
            std::ifstream in(entry.path(), std::ios::binary);
            auto doc = yue_agent::parse(std::string(std::istreambuf_iterator<char>(in), {}));
            if (!doc) continue;
            auto * r = yyjson_doc_get_root(doc.get());
            auto file = std::make_shared<Result>();
            file->id = id; file->path = root_ / (id + ".bin");
            file->mime = yue_agent::field(r, "mime"); file->metrics = yue_agent::field(r, "metrics");
            file->generations = yue_agent::field(r, "generations");
            file->expires = yyjson_get_sint(yyjson_obj_get(r, "expires"));
            file->size = yyjson_get_uint(yyjson_obj_get(r, "size"));
            if (file->expires <= clock_()) { remove_owned(id); continue; }
            if (file->mime.empty() || file->mime.find_first_of("\r\n") != std::string::npos ||
                !regular(file->path) || std::filesystem::file_size(file->path) != file->size) continue;
            // Keep existing unexpired files even when the operator lowers limits.
            bytes_ += file->size; files_.emplace(id, std::move(file));
        }
        for (const auto & entry : std::filesystem::directory_iterator(root_)) {
            auto id = entry.path().stem().string();
            if (!job_id_valid(id)) continue;
            auto ext = entry.path().extension().string();
            if ((ext == ".part" || ext == ".meta-part") ||
                ((ext == ".bin" || ext == ".json") && !files_.count(id))) {
                std::error_code ec; std::filesystem::remove(entry.path(), ec);
            }
        }
    }
public:
    explicit Results(std::filesystem::path root, StorageLimits limits = {},
                     std::function<int64_t()> clock = yue_agent::now_seconds)
        : root_(std::filesystem::absolute(root)), limits_(limits), clock_(std::move(clock)) {
        std::filesystem::create_directories(root_);
        if (std::filesystem::is_symlink(std::filesystem::symlink_status(root_)))
            throw std::runtime_error("Job result directory must not be a symlink");
        std::filesystem::permissions(root_, std::filesystem::perms::owner_all, std::filesystem::perm_options::replace);
        restore();
    }
    void cleanup() { std::lock_guard<std::mutex> lock(mutex_); cleanup_locked(); }
    void require_space() {
        std::lock_guard<std::mutex> lock(mutex_);
        cleanup_locked();
        if (files_.size() >= limits_.files || bytes_ >= limits_.bytes)
            throw StorageFull("Job result storage is full; wait for retained results to expire or increase its limits");
    }
    std::shared_ptr<const Result> find(const std::string & id) const {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = files_.find(id);
        return it != files_.end() && it->second->expires > clock_() ? it->second : nullptr;
    }
    // Writes are synchronous on the single compute worker; no full result copy
    // is retained by Jobs, HTTP responses, or the storage index.
    void save(const std::string & id, const std::string & mime, const std::string & metrics,
              const std::function<void(std::ostream &)> & write, const std::string & generations = "") {
        std::unique_lock<std::mutex> lock(mutex_);
        cleanup_locked();
        if (!job_id_valid(id) || files_.count(id)) throw std::runtime_error("Invalid or duplicate result id");
        if (writing_ || files_.size() >= limits_.files || bytes_ >= limits_.bytes)
            throw StorageFull("Job result storage is full; download retained results or wait for expiry");
        const auto bound = std::min(limits_.file_bytes, limits_.bytes - bytes_);
        auto file = std::make_shared<Result>();
        file->id = id; file->mime = mime; file->metrics = metrics;
        file->path = root_ / (id + ".bin"); file->expires = clock_() + limits_.ttl;
        auto staging = root_ / (id + ".part");
        writing_ = true;
        lock.unlock(); // Slow disk writes must not block health/status/cancellation.
        try {
            // A bounded streambuf prevents a large multipart/batch from filling
            // the volume before its size is checked.
            class BoundedBuffer : public std::streambuf {
                std::ofstream out_;
                uint64_t remaining_;
                std::streamsize xsputn(const char * data, std::streamsize n) override {
                    if (n < 0 || (uint64_t) n > remaining_) throw StorageFull("Job result exceeds storage limits");
                    out_.write(data, n); if (!out_) throw std::runtime_error("Could not write job result");
                    remaining_ -= (uint64_t) n; return n;
                }
                int_type overflow(int_type ch) override {
                    if (traits_type::eq_int_type(ch, traits_type::eof())) return traits_type::not_eof(ch);
                    char c = traits_type::to_char_type(ch); xsputn(&c, 1); return ch;
                }
            public:
                BoundedBuffer(const std::filesystem::path & p, uint64_t bound)
                    : out_(p, std::ios::binary | std::ios::trunc), remaining_(bound) {
                    if (!out_) throw std::runtime_error("Job result directory is not writable");
                }
                void close() { out_.close(); if (!out_) throw std::runtime_error("Could not finish job result"); }
            } buffer(staging, bound);
            std::ostream stream(&buffer); stream.exceptions(std::ios::badbit | std::ios::failbit);
            write(stream); buffer.close();
            // The worker may finalize its immutable timing snapshot after
            // serializing the body, without buffering that body in RAM.
            file->metrics = metrics;
            file->expires = clock_() + limits_.ttl;
            file->size = std::filesystem::file_size(staging);
            Json meta; meta.text("mime", mime); meta.text("metrics", metrics);
            file->generations = generations; meta.text("generations", generations);
            meta.integer("size", (int64_t) file->size); meta.integer("expires", file->expires);
            auto text = meta.dump();
            std::ofstream out(root_ / (id + ".meta-part"), std::ios::binary | std::ios::trunc);
            out.write(text.data(), (std::streamsize) text.size()); out.close();
            if (!out) throw std::runtime_error("Could not write job result metadata");
            std::filesystem::rename(staging, file->path);
            std::filesystem::rename(root_ / (id + ".meta-part"), root_ / (id + ".json"));
            lock.lock();
            bytes_ += file->size; files_.emplace(id, std::move(file)); writing_ = false;
        } catch (...) {
            remove_owned(id); if (!lock.owns_lock()) lock.lock(); writing_ = false; throw;
        }
    }
    std::string snapshot() const {
        std::lock_guard<std::mutex> lock(mutex_);
        Json j; j.text("location", "volume"); j.integer("files", (int64_t) files_.size());
        j.integer("bytes", (int64_t) bytes_); j.integer("limit_bytes", (int64_t) limits_.bytes);
        j.integer("limit_files", (int64_t) limits_.files); j.integer("max_file_bytes", (int64_t) limits_.file_bytes);
        j.integer("ttl_seconds", limits_.ttl); j.boolean("full", files_.size() >= limits_.files || bytes_ >= limits_.bytes);
        return j.dump();
    }
};
}
