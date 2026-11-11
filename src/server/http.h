#pragma once
#include "queue.h"
#include "httplib.h"

namespace yue_server {
inline constexpr size_t HTTP_THREADS = 20, API_WAITERS = 8, DOWNLOADS = 4, LOG_STREAMS = 2, UPLOAD_DECODERS = 2;
inline constexpr uint64_t MAX_UPLOAD_BYTES = 64ULL * 1024 * 1024;
inline void configure_http(httplib::Server & server) {
    server.new_task_queue = [] { return new httplib::ThreadPool(HTTP_THREADS, HTTP_THREADS, 128); };
    server.set_payload_max_length(MAX_UPLOAD_BYTES);
    server.set_read_timeout(15); server.set_write_timeout(15);
    server.set_keep_alive_timeout(2); server.set_keep_alive_max_count(100);
}
inline void busy(httplib::Response & res, const std::string & message, const char * code = "queue_full") {
    res.status = 429; res.set_header("Retry-After", std::to_string(RETRY_SECONDS));
    res.set_header("Cache-Control", "no-store");
    Json j; j.text("error", message); j.text("code", code); j.integer("retry_after_seconds", RETRY_SECONDS);
    res.set_content(j.dump(), "application/json");
}
inline void serve_result(httplib::Response & res, std::shared_ptr<const Result> result,
                         Slots & downloads, std::shared_ptr<Slots::Lease> reserved = {}) {
    auto slot = reserved ? std::move(reserved) : downloads.acquire();
    if (!slot) { busy(res, "Download slots are busy; retry shortly", "downloads_busy"); return; }
    auto file = std::make_shared<std::ifstream>(result->path, std::ios::binary);
    if (!*file) { res.status = 404; return; }
    res.set_header("Cache-Control", "no-store"); res.set_header("Accept-Ranges", "bytes");
    res.set_header("X-Content-Type-Options", "nosniff");
    res.set_content_provider((size_t) result->size, result->mime,
        [file, result, slot](size_t offset, size_t length, httplib::DataSink & sink) {
            std::array<char, 64 * 1024> buffer{};
            file->clear(); file->seekg((std::streamoff) offset);
            size_t n = std::min(length, buffer.size()); file->read(buffer.data(), (std::streamsize) n);
            return file->gcount() == (std::streamsize) n && sink.write(buffer.data(), n);
        });
}
enum class Wait { COMPLETE, TIMEOUT, DISCONNECTED };
inline Wait wait_for_job(const httplib::Request & req, Queue & queue, const std::shared_ptr<Job> & job,
                          double timeout, const std::function<bool()> & alive) {
    auto deadline = std::chrono::steady_clock::now() + std::chrono::duration<double>(timeout);
    for (;;) {
        auto state = job->status.load();
        if (state != JobStatus::QUEUED && state != JobStatus::RUNNING) return Wait::COMPLETE;
        if (req.is_connection_closed() || !alive()) { queue.cancel(job->id); return Wait::DISCONNECTED; }
        if (std::chrono::steady_clock::now() >= deadline) { queue.cancel(job->id); return Wait::TIMEOUT; }
        std::this_thread::sleep_for(std::chrono::milliseconds(25));
    }
}
inline std::string status_json(const Queue & queue, const Results & results, const Slots & waiters) {
    Json j; j.text("status", "ok"); j.json("queue", queue.snapshot()); j.json("results", results.snapshot());
    Json http; http.integer("workers", HTTP_THREADS); http.integer("synchronous_limit", API_WAITERS);
    http.integer("synchronous_waiters", (int64_t) waiters.used()); http.integer("download_limit", DOWNLOADS);
    http.integer("log_stream_limit", LOG_STREAMS); http.integer("max_upload_bytes", (int64_t) MAX_UPLOAD_BYTES);
    http.integer("upload_decoder_limit", UPLOAD_DECODERS);
    j.json("http", http.dump()); return j.dump();
}
inline std::string job_json(const Queue & queue, const std::shared_ptr<Job> & job) {
    Json j; auto state = job->status.load(); j.text("status", job_status_str(state));
    j.integer("queue_position", (int64_t) queue.position(job->id)); j.boolean("cancel_requested", job->cancel.load());
    if (state == JobStatus::DONE && !job->metrics_json.empty()) j.json("metrics", job->metrics_json);
    if (state == JobStatus::DONE) j.json("generations", job->generations_json.empty() ? "null" : job->generations_json);
    if (state == JobStatus::FAILED) j.text("error", "Job failed; inspect the local server logs");
    return j.dump();
}
inline void attach_status_routes(httplib::Server & server, Queue & queue, Results & results,
                                 Slots & waiters, Slots & downloads) {
    auto status = [&](const httplib::Request &, httplib::Response & res) {
        res.set_header("Cache-Control", "no-store");
        res.set_content(status_json(queue, results, waiters), "application/json");
    };
    server.Get("/health", status); server.Get("/status", status); server.Get("/system/queue", status);
    server.Get("/job", [&](const httplib::Request & req, httplib::Response & res) {
        res.set_header("Cache-Control", "no-store");
        auto id = req.get_param_value("id"); auto job = queue.find(id);
        if (req.has_param("result")) {
            auto result = results.find(id);
            if (!result) { res.status = 404; res.set_content("{\"error\":\"result unavailable or expired\"}", "application/json"); return; }
            serve_result(res, result, downloads); return;
        }
        // Disk metadata recovers completed results after process/container restart.
        auto result = results.find(id);
        if (job && (job->status.load() != JobStatus::DONE || result)) {
            auto body = job_json(queue, job);
            if (result) { body.pop_back(); body += ",\"expires_at\":\"" + yue_agent::utc(result->expires) + "\"}"; }
            res.set_content(body, "application/json"); return;
        }
        if (result) {
            Json j; j.text("status", "done"); j.integer("queue_position", 0);
            j.text("expires_at", yue_agent::utc(result->expires));
            if (!result->metrics.empty()) j.json("metrics", result->metrics);
            j.json("generations", result->generations.empty() ? "null" : result->generations);
            res.set_content(j.dump(), "application/json"); return;
        }
        res.status = 404; res.set_content("{\"error\":\"job not found or expired\"}", "application/json");
    });
    server.Post("/job", [&](const httplib::Request & req, httplib::Response & res) {
        res.set_header("Cache-Control", "no-store");
        auto id = req.get_param_value("id"); auto job = queue.find(id);
        if (!job) {
            if (results.find(id)) { res.set_content("{\"status\":\"done\"}", "application/json"); return; }
            res.status = 404; res.set_content("{\"error\":\"job not found\"}", "application/json"); return;
        }
        if (req.has_param("cancel")) queue.cancel(id);
        res.set_content(job_json(queue, job), "application/json");
    });
}
}
