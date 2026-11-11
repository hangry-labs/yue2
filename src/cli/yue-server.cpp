// yue-server.cpp: HTTP server (async job queue + embedded webui)
//
// The compute endpoint creates a job and returns its ID immediately. A single
// worker thread owns the resident models and runs jobs in FIFO order. The
// client polls the job and fetches its result, which pairs a replay request
// with its audio: the replay carries the semantic stream, the score and the
// resolved seed, so re-rendering never pays the autoregression again.
//
// The binary orchestrates only: generation, cancellation and encoding all
// live in src/.

#include "audio-formats.h"
#include "backend.h"
#include "httplib.h"
#include "index.html.gz.hpp"
#include "openapi.json.hpp"
#include "music-api.h"
#include "agent/mcp.h"
#include "songwriting-skill.hpp"
#include "pipeline.h"
#include "generation-model.h"
#include "system-gpu.h"
#include "server/http.h"
#include "version.h"
#include "yyjson.h"

#include <atomic>
#include <chrono>
#include <cctype>
#include <condition_variable>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <functional>
#include <memory>
#include <mutex>
#include <random>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#ifdef _WIN32
#    include <fcntl.h>
#    include <io.h>
#    ifndef STDERR_FILENO
#        define STDERR_FILENO 2
#    endif
#else
#    include <unistd.h>
#endif

// portable fd wrappers. avoids macros that collide with C++ method names
// (e.g. sink.write() in httplib would be eaten by a write() macro).
#ifdef _WIN32
static int fd_pipe(int fd[2]) {
    return _pipe(fd, 4096, _O_BINARY);
}

static int fd_dup(int fd) {
    return _dup(fd);
}

static int fd_dup2(int src, int dst) {
    return _dup2(src, dst);
}

static int fd_read(int fd, void * buf, size_t n) {
    return _read(fd, buf, (unsigned) n);
}

static int fd_write(int fd, const void * buf, size_t n) {
    return _write(fd, buf, (unsigned) n);
}

static void fd_close(int fd) {
    _close(fd);
}
#else
static int fd_pipe(int fd[2]) {
    return pipe(fd);
}

static int fd_dup(int fd) {
    return dup(fd);
}

static int fd_dup2(int src, int dst) {
    return dup2(src, dst);
}

static int fd_read(int fd, void * buf, size_t n) {
    return (int) read(fd, buf, n);
}

static int fd_write(int fd, const void * buf, size_t n) {
    return (int) write(fd, buf, n);
}

static void fd_close(int fd) {
    close(fd);
}
#endif

static httplib::Server * g_svr = nullptr;
static std::string g_api_key;
static int g_api_timeout = 600;

// Build a multipart/mixed body with, per rendered track, its JSON replay
// request part, its audio part and its latent part (raw f32 [T, 64] time
// major, the .vae layout). The boundary is fixed; the client splits on it
// and types parts by their header.
static const char * MULTIPART_BOUNDARY = "yue2-batch-boundary";

static void multipart_write_tracks(std::ostream & body, const std::vector<std::string> & request_parts,
                                          const std::vector<std::string> &        audio_parts,
                                          const char *                            audio_mime,
                                          const std::vector<std::vector<float>> & latents) {
    // Stream the existing wire format straight to the result file.
    const char * dash       = "--";
    const char * json_head  = "\r\nContent-Type: application/json\r\n\r\n";
    const char * audio_head = "\r\nContent-Type: ";
    const char * latent_head =
        "\r\nContent-Type: application/octet-stream\r\n"
        "Content-Disposition: form-data; name=\"latent\"\r\n\r\n";
    const char * head_end  = "\r\n\r\n";
    const char * crlf      = "\r\n";
    const char * close_end = "--\r\n";

    for (size_t i = 0; i < audio_parts.size(); i++) {
        body << dash << MULTIPART_BOUNDARY << json_head << request_parts[i] << crlf;
        body << dash << MULTIPART_BOUNDARY << audio_head << audio_mime << head_end;
        body.write(audio_parts[i].data(), (std::streamsize) audio_parts[i].size());
        body << crlf << dash << MULTIPART_BOUNDARY << latent_head;
        body.write(reinterpret_cast<const char *>(latents[i].data()), (std::streamsize) (latents[i].size() * sizeof(float)));
        body << crlf;
    }
    body << dash << MULTIPART_BOUNDARY << close_end;
}

static const std::string MULTIPART_MIME = std::string("multipart/mixed; boundary=") + MULTIPART_BOUNDARY;

// job system: the compute endpoint creates a job and returns its ID
// immediately. the worker thread processes jobs in FIFO order, stores
// the result. the client polls GET /job?id=N until done, then fetches
// the result with GET /job?id=N&result=1.
// cancel: POST /job?id=N&cancel=1 sets the per-job flag.
using yue_server::Job;
using yue_server::JobStatus;
static std::unique_ptr<yue_server::Queue> g_queue;
static std::unique_ptr<yue_server::Results> g_results;
static yue_server::Slots g_waiters(yue_server::API_WAITERS);
static yue_server::Slots g_downloads(yue_server::DOWNLOADS);
static yue_server::Slots g_log_streams(yue_server::LOG_STREAMS);
static yue_server::Slots g_upload_decoders(yue_server::UPLOAD_DECODERS);
static std::atomic<bool> g_shutdown_requested{false};
static std::string json_string(const char * key, const std::string & value);

static std::shared_ptr<yue_server::Slots::Lease> upload_slot(httplib::Response & res) {
    try { g_queue->require_capacity(); g_results->require_space(); }
    catch (const yue_server::QueueFull & e) { yue_server::busy(res, e.what()); return nullptr; }
    catch (const yue_server::StorageFull & e) {
        res.status = 507; res.set_content(json_string("error", e.what()), "application/json"); return nullptr;
    }
    auto slot = g_upload_decoders.acquire();
    if (!slot) {
        g_queue->note_rejection();
        yue_server::busy(res, "Audio upload processing is busy; retry shortly", "uploads_busy");
    }
    return slot;
}

static std::shared_ptr<Job> submit_native(httplib::Response & res, const std::string & kind,
                                        std::function<void(std::shared_ptr<Job>)> run) {
    try {
        g_results->require_space();
        auto job = g_queue->submit(kind, std::move(run));
        fprintf(stderr, "[Server] Job %s: queued %s\n", job->id.c_str(), kind.c_str());
        res.set_content(json_string("id", job->id), "application/json");
        return job;
    } catch (const yue_server::QueueFull & e) { yue_server::busy(res, e.what()); }
      catch (const yue_server::StorageFull & e) {
        res.status = 507; res.set_content(json_string("error", e.what()), "application/json");
    }
    return nullptr;
}

static void publish_result(const std::shared_ptr<Job> & job, const std::string & mime, const char * data, size_t size) {
    g_results->save(job->id, mime, job->metrics_json, [&](std::ostream & out) { out.write(data, (std::streamsize) size); });
    job->status.store(JobStatus::DONE);
}
static void publish_result(const std::shared_ptr<Job> & job, const std::string & mime, const std::string & body) {
    publish_result(job, mime, body.data(), body.size());
}

static bool server_cancel_job(void * data) {
    auto * flag = (const std::atomic<bool> *) data;
    return g_shutdown_requested.load(std::memory_order_relaxed) || (flag && flag->load(std::memory_order_relaxed));
}

// log capture: intercept stderr via pipe, forward to terminal + ring buffer.
// SSE clients connect to /logs and receive lines in real time.
#define LOG_RING_BITS 9
#define LOG_RING_SIZE (1 << LOG_RING_BITS)
#define LOG_RING_MASK (LOG_RING_SIZE - 1)

static std::mutex              mtx_log;
static std::condition_variable cv_log;
static std::string             log_ring[LOG_RING_SIZE];
static uint64_t                log_seq = 0;

static int         g_real_stderr_fd = -1;
static int         g_pipe_read_fd   = -1;
static std::thread g_log_reader;

// reader thread: drain pipe, forward to real stderr, push lines to ring.
// exits when the write end of the pipe is closed (fd_dup2 restores real stderr).
static void log_reader_main() {
    char        buf[4096];
    std::string partial;
    for (;;) {
        int n = fd_read(g_pipe_read_fd, buf, sizeof(buf));
        if (n <= 0) {
            break;
        }
        fd_write(g_real_stderr_fd, buf, (size_t) n);
        partial.append(buf, (size_t) n);
        size_t pos;
        while ((pos = partial.find('\n')) != std::string::npos) {
            std::lock_guard<std::mutex> lock(mtx_log);
            log_ring[log_seq & LOG_RING_MASK] = partial.substr(0, pos);
            log_seq++;
            cv_log.notify_all();
            partial.erase(0, pos + 1);
        }
    }
    if (!partial.empty()) {
        std::lock_guard<std::mutex> lock(mtx_log);
        log_ring[log_seq & LOG_RING_MASK] = std::move(partial);
        log_seq++;
        cv_log.notify_all();
    }
    fd_close(g_pipe_read_fd);
}

// Restore stderr and drain the reader before the pipe dies with the process.
// Idempotent: the destructor and the exit hook both land here, either order.
static void log_capture_stop() {
    if (g_real_stderr_fd < 0) {
        return;
    }
    fflush(stderr);
    // the restore drops the last write end, so the reader reads EOF and returns
    fd_dup2(g_real_stderr_fd, STDERR_FILENO);
    cv_log.notify_all();
    if (g_log_reader.joinable()) {
        g_log_reader.join();
    }
    fd_close(g_real_stderr_fd);
    g_real_stderr_fd = -1;
}

static void setup_log_capture() {
    g_real_stderr_fd = fd_dup(STDERR_FILENO);
    int pipefd[2];
    if (fd_pipe(pipefd) != 0) {
        fd_close(g_real_stderr_fd);
        g_real_stderr_fd = -1;
        return;
    }
    g_pipe_read_fd = pipefd[0];
    fd_dup2(pipefd[1], STDERR_FILENO);
    fd_close(pipefd[1]);
    // A loader aborts the process with exit() on a fatal error, which skips
    // every destructor: the hook still drains the pipe, so the message that
    // explains the failure reaches the terminal.
    atexit(log_capture_stop);
    g_log_reader = std::thread(log_reader_main);
}

// RAII: captures stderr on construction, restores and drains on destruction.
struct LogCapture {
    LogCapture() { setup_log_capture(); }

    ~LogCapture() { log_capture_stop(); }
};

// GET /logs: SSE stream of stderr lines.
// sends backlog (up to LOG_RING_SIZE) then streams new lines in real time.
static void handle_logs(const httplib::Request &, httplib::Response & res) {
    auto slot = g_log_streams.acquire();
    if (!slot) { yue_server::busy(res, "Log stream slots are busy", "log_streams_busy"); return; }
    res.set_header("Cache-Control", "no-cache");
    res.set_header("X-Accel-Buffering", "no");
    res.set_chunked_content_provider(
        "text/event-stream", [slot, cursor = uint64_t(0), init = false](size_t, httplib::DataSink & sink) mutable -> bool {
            if (!g_svr || !g_svr->is_running()) return false;
            std::unique_lock<std::mutex> lock(mtx_log);
            if (!init) {
                uint64_t avail = log_seq < LOG_RING_SIZE ? log_seq : (uint64_t) LOG_RING_SIZE;
                cursor         = log_seq - avail;
                while (cursor < log_seq) {
                    std::string ev = "data: " + log_ring[cursor & LOG_RING_MASK] + "\n\n";
                    cursor++;
                    lock.unlock();
                    if (!sink.write(ev.c_str(), ev.size())) {
                        return false;
                    }
                    lock.lock();
                }
                init = true;
            }
            cv_log.wait_for(lock, std::chrono::seconds(2));
            while (cursor < log_seq) {
                std::string ev = "data: " + log_ring[cursor & LOG_RING_MASK] + "\n\n";
                cursor++;
                lock.unlock();
                if (!sink.write(ev.c_str(), ev.size())) {
                    return false;
                }
                lock.lock();
            }
            lock.unlock();
            return sink.write(": keepalive\n\n", 13);
        });
}

static Yue2Pipeline g_pipeline;
static bool         g_keep_loaded = false;
static std::string  g_model_path;
static std::string  g_vae_path;
static std::string  g_transcriber_path;
static std::string  g_tokenizer_path;

static void on_signal(int) {
    g_shutdown_requested.store(true);
    if (g_svr) {
        g_svr->stop();
    }
}

static uint64_t runtime_limit(const char * name, uint64_t fallback, uint64_t maximum) {
    auto * value = std::getenv(name);
    if (!value) return fallback;
    std::string text(value);
    if (text.empty() || text.find_first_not_of("0123456789") != std::string::npos)
        throw std::runtime_error(std::string(name) + " must be a positive integer");
    size_t end = 0; auto number = std::stoull(text, &end);
    if (end != text.size() || number == 0 || number > maximum)
        throw std::runtime_error(std::string(name) + " is outside its supported range");
    return number;
}

static std::string json_string(const char * key, const std::string & value) {
    yyjson_mut_doc * doc  = yyjson_mut_doc_new(NULL);
    yyjson_mut_val * root = yyjson_mut_obj(doc);
    yyjson_mut_doc_set_root(doc, root);
    yyjson_mut_obj_add_strncpy(doc, root, key, value.c_str(), value.size());
    char *      json = yyjson_mut_write(doc, 0, NULL);
    std::string out  = json ? json : "{}";
    if (json) {
        free(json);
    }
    yyjson_mut_doc_free(doc);
    return out;
}

static void handle_props(const httplib::Request &, httplib::Response & res) {
    Yue2Request d;
    request_init(&d);

    yyjson_mut_doc * doc  = yyjson_mut_doc_new(NULL);
    yyjson_mut_val * root = yyjson_mut_obj(doc);
    yyjson_mut_doc_set_root(doc, root);
    yyjson_mut_obj_add_str(doc, root, "version", YUE2_VERSION);
    yyjson_mut_obj_add_strncpy(doc, root, "model", g_model_path.c_str(), g_model_path.size());
    yyjson_mut_obj_add_strncpy(doc, root, "vae", g_vae_path.c_str(), g_vae_path.size());
    yyjson_mut_obj_add_int(doc, root, "sample_rate", YUE2_SAMPLE_RATE);
    yyjson_mut_obj_add_int(doc, root, "frame_rate", YUE2_FRAME_RATE);
    yyjson_mut_obj_add_int(doc, root, "context", YUE2_CONTEXT);
    auto * limits = yyjson_mut_obj(doc);
    yyjson_mut_obj_add_int(doc, limits, "synth_batch_size_max", YUE2_VARIATIONS_MAX);
    yyjson_mut_obj_add_val(doc, root, "limits", limits);
    res.set_header("Cache-Control", "no-store");
    auto * capabilities = yyjson_mut_obj(doc);
    yyjson_mut_obj_add_bool(doc, capabilities, "transcribe", !g_transcriber_path.empty());
    yyjson_mut_obj_add_bool(doc, capabilities, "tokenize", !g_tokenizer_path.empty());
    yyjson_mut_obj_add_bool(doc, capabilities, "vae", true);
    yyjson_mut_obj_add_val(doc, root, "capabilities", capabilities);
    auto * formats = yyjson_mut_arr(doc);
    for (const auto & format : AUDIO_OUTPUT_FORMATS) {
        auto * item = yyjson_mut_arr_add_obj(doc, formats);
        yyjson_mut_obj_add_str(doc, item, "name", format.name);
        yyjson_mut_obj_add_str(doc, item, "extension", format.extension);
        yyjson_mut_obj_add_str(doc, item, "mime", format.mime);
    }
    yyjson_mut_obj_add_val(doc, root, "output_formats", formats);
    auto * api = yyjson_mut_obj(doc);
    yyjson_mut_obj_add_str(doc, api, "music", "/v1/audio/music");
    yyjson_mut_obj_add_str(doc, api, "speech", "/v1/audio/speech");
    yyjson_mut_obj_add_str(doc, api, "mcp", "/mcp");
    yyjson_mut_obj_add_str(doc, api, "songwriting_skill", yue_agent::SKILL_PATH);
    yyjson_mut_obj_add_int(doc, api, "download_ttl_seconds", yue_agent::LINK_TTL);
    yyjson_mut_obj_add_bool(doc, api, "authentication_required", !g_api_key.empty());
    yyjson_mut_obj_add_int(doc, api, "timeout_seconds", g_api_timeout);
    yyjson_mut_obj_add_val(doc, root, "api", api);
    auto queue_doc = yue_agent::parse(g_queue->snapshot());
    yyjson_mut_obj_add_val(doc, root, "queue", yyjson_val_mut_copy(doc, yyjson_doc_get_root(queue_doc.get())));

    // The adapter directory, each entry with the halves it changes
    yyjson_mut_val * adapters = yyjson_mut_arr(doc);
    for (const AdapterEntry & e : g_pipeline.adapters) {
        yyjson_mut_val * item = yyjson_mut_arr_add_obj(doc, adapters);
        yyjson_mut_obj_add_strncpy(doc, item, "name", e.name.c_str(), e.name.size());
        yyjson_mut_obj_add_bool(doc, item, "ar", e.halves & ADAPTER_AR);
        yyjson_mut_obj_add_bool(doc, item, "nar", e.halves & ADAPTER_NAR);
    }
    yyjson_mut_obj_add_val(doc, root, "adapters", adapters);

    // The defaults are the request schema itself, serialized by the request
    // writer and grafted here: one source of truth, one float formatting
    std::string  def_json = request_to_json(&d, false);
    yyjson_doc * def_doc  = yyjson_read(def_json.c_str(), def_json.size(), 0);
    if (def_doc) {
        yyjson_mut_obj_add_val(doc, root, "defaults", yyjson_val_mut_copy(doc, yyjson_doc_get_root(def_doc)));
        yyjson_doc_free(def_doc);
    }

    char * json = yyjson_mut_write(doc, 0, NULL);
    res.set_content(json ? json : "{}", "application/json");
    if (json) {
        free(json);
    }
    yyjson_mut_doc_free(doc);
}

// Validates what the pipeline would refuse anyway, so a bad request fails
// fast with a 400 instead of occupying the worker
static bool validate(const std::string & json, httplib::Response & res, Yue2Request * r) {
    std::string parse_error;
    if (!request_parse_json(r, json.c_str(), &parse_error)) {
        res.status = 400;
        res.set_content(json_string("error", parse_error), "application/json");
        return false;
    }
    Yue2Cot cot;
    if (!yue2_cot_parse(r->cot, &cot)) {
        res.status = 400;
        res.set_content(json_string("error", "cot must be full, melody or off"), "application/json");
        return false;
    }
    if (!audio_output_format(r->output_format)) {
        res.status = 400;
        res.set_content(json_string("error", "unknown output format"), "application/json");
        return false;
    }
    if (r->steps < 1) {
        res.status = 400;
        res.set_content(json_string("error", "steps must be positive"), "application/json");
        return false;
    }
    if (r->lm_batch_size < 1 || r->lm_batch_size > g_pipeline.params.max_batch) {
        res.status = 400;
        res.set_content(json_string("error", "lm_batch_size exceeds --max-batch"), "application/json");
        return false;
    }
    if (r->synth_batch_size < 1 || r->synth_batch_size > YUE2_VARIATIONS_MAX) {
        res.status = 400;
        res.set_content(json_string("error", "synth_batch_size must be between 1 and 3"), "application/json");
        return false;
    }
    if (!yue2_sampling_valid(r->abc_sampling, "abc") || !yue2_sampling_valid(r->semantic_sampling, "semantic")) {
        res.status = 400;
        res.set_content(json_string("error", "sampling preset outside the protocol bounds"), "application/json");
        return false;
    }
    for (const Yue2Adapter & a : r->adapters) {
        if (!adapter_find(g_pipeline.adapters, a.name)) {
            res.status = 400;
            res.set_content(json_string("error", "adapter not found: " + a.name), "application/json");
            return false;
        }
    }
    if (!r->semantic_tokens.empty() && !r->source_tokens.empty()) {
        res.status = 400;
        res.set_content(json_string("error", "semantic_tokens and source_tokens are exclusive"), "application/json");
        return false;
    }
    request_resolve_seed(r);
    return true;
}

// Transcribe worker: the uploaded recording becomes an ABC score, the chord
// symbols dropped when only the melody is wanted.
static void run_transcribe(std::shared_ptr<Job> job, std::vector<float> audio, bool melody_only) {
    if (g_shutdown_requested || job->cancel) { job->status = JobStatus::CANCELLED; return; }
    fprintf(stderr, "[Server] Transcribe job %s: %.1f s of audio, %s\n", job->id.c_str(),
            (double) audio.size() / MERT_SAMPLE_RATE, melody_only ? "melody only" : "full score");
    std::string abc, error;
    bool        ok = pipeline_transcribe(&g_pipeline, audio.data(), (int) audio.size(), melody_only, &abc, &error);
    if (!ok) {
        fprintf(stderr, "[Server] Transcribe job %s failed: %s\n", job->id.c_str(), error.c_str());
        job->status.store(job->cancel.load() ? JobStatus::CANCELLED : JobStatus::FAILED);
        return;
    }
    publish_result(job, "application/json", json_string("abc", abc));
}

// Tokenize worker: the uploaded recording becomes its semantic codes, the
// stream a card keeps for its replay and for the continuations it opens.
static void run_tokenize(std::shared_ptr<Job> job, std::vector<float> audio) {
    if (g_shutdown_requested || job->cancel) { job->status = JobStatus::CANCELLED; return; }
    fprintf(stderr, "[Server] Tokenize job %s: %.1f s of audio\n", job->id.c_str(),
            (double) audio.size() / MERT_SAMPLE_RATE);
    std::vector<int> codes;
    std::string      error;
    bool             ok = pipeline_tokenize(&g_pipeline, audio.data(), (int) audio.size(), &codes, &error);
    if (!ok) {
        fprintf(stderr, "[Server] Tokenize job %s failed: %s\n", job->id.c_str(), error.c_str());
        job->status.store(job->cancel.load() ? JobStatus::CANCELLED : JobStatus::FAILED);
        return;
    }
    publish_result(job, "application/json", json_string("codes", pipeline_format_tokens(codes)));
}

// The audio part of a track: peak normalized except WAV32, then encoded in
// the output format of the request
static std::string encode_audio(const Yue2Request & request, std::vector<float> & audio, int T_audio,
                                std::atomic<bool> * cancel_flag, double speed = 1, bool pcm = false) {
    auto * format = audio_output_format(request.output_format);
    return format ? audio_render(*format, audio, T_audio, YUE2_SAMPLE_RATE, request.mp3_bitrate,
                                  request.peak_clip, server_cancel_job, cancel_flag, speed, pcm) : std::string{};
}

// VAE worker, encode: the uploaded recording becomes its latents, raw f32
// [T, 64] time major, the .vae layout
static void run_vae_encode(std::shared_ptr<Job> job, std::vector<float> planar, int T, int sr) {
    if (g_shutdown_requested || job->cancel) { job->status = JobStatus::CANCELLED; return; }
    fprintf(stderr, "[Server] VAE encode job %s: %.1f s of audio\n", job->id.c_str(), (double) T / sr);
    std::vector<float> latents;
    int                T_lat = 0;
    bool               ok    = pipeline_encode(&g_pipeline, planar.data(), T, sr, &latents, &T_lat);
    if (!ok) {
        job->status.store(job->cancel.load() ? JobStatus::CANCELLED : JobStatus::FAILED);
        return;
    }
    publish_result(job, "application/octet-stream", reinterpret_cast<const char *>(latents.data()), latents.size() * sizeof(float));
}

// VAE worker, decode: uploaded latents become audio in the output format of
// the request
static void run_vae_decode(std::shared_ptr<Job> job, Yue2Request request, std::vector<float> latents, int T_lat) {
    if (g_shutdown_requested || job->cancel) { job->status = JobStatus::CANCELLED; return; }
    fprintf(stderr, "[Server] VAE decode job %s: %d latent frames\n", job->id.c_str(), T_lat);
    VAEGGML *   vae = require_vae(&g_pipeline);
    bool        ok  = vae != nullptr;
    std::string audio_part;
    if (ok) {
        ModelHandle        hold(g_pipeline.store, vae);
        std::vector<float> audio;
        int                T_audio = 0;
        ok = pipeline_decode(&g_pipeline, vae, latents.data(), T_lat, &audio, &T_audio, server_cancel_job,
                             (void *) &job->cancel);
        if (ok) {
            audio_part = encode_audio(request, audio, T_audio, &job->cancel);
            ok         = !audio_part.empty();
        }
    }
    if (!ok) {
        job->status.store(job->cancel.load() ? JobStatus::CANCELLED : JobStatus::FAILED);
        return;
    }
    publish_result(job, audio_output_format(request.output_format)->mime, audio_part);
}

using SongExport = std::function<void(const std::string &, double, const std::string &)>;
static void run_job(std::shared_ptr<Job> job, Yue2Request request, bool direct = false, double speed = 1, bool pcm = false,
                    const SongExport & song_export = {}) {
    if (g_shutdown_requested || job->cancel.load()) { job->status.store(JobStatus::CANCELLED); return; }
    Timer worker_timer;
    double queue_seconds = std::chrono::duration<double>(worker_timer.t - job->submitted).count();
    size_t loads_before = store_load_count(g_pipeline.store);
    fprintf(stderr, "[Server] Job %s: %s\n", job->id.c_str(), request_to_json(&request).c_str());

    std::vector<Yue2Song> songs;
    // Capture immutable identity on the worker, not from global configuration at GET time.
    const auto model_identity = generation_model(g_pipeline.model_path);
    const auto vae_identity = generation_model(g_pipeline.vae_path);
    bool ok = pipeline_generate(&g_pipeline, request, &songs, server_cancel_job, (void *) &job->cancel);
    double pipeline_seconds = worker_timer.ms() / 1000.0;

    if (!ok) {
        job->status.store(job->cancel.load() ? JobStatus::CANCELLED : JobStatus::FAILED);
        return;
    }

    // One part triple per track, song-major. The replay request of a track
    // carries its semantic stream, its score and the seeds it consumed, so a
    // resubmit reproduces it without the autoregression.
    const int                       M = request.synth_batch_size;
    std::vector<std::string>        audio_parts;
    std::vector<std::string>        request_parts;
    std::vector<std::vector<float>> latents;
    std::vector<std::string> generations;
    for (size_t t = 0; t < songs.size(); t++) {
        Yue2Song & song = songs[t];
        audio_parts.push_back(encode_audio(request, song.audio, song.T_audio, &job->cancel, speed, pcm));
        if (audio_parts.back().empty()) {
            job->status.store(job->cancel.load() ? JobStatus::CANCELLED : JobStatus::FAILED);
            return;
        }
        generations.push_back(generation_json(request, song.execution, model_identity, vae_identity,
                                               YUE2_VERSION, (double) song.T_audio / YUE2_SAMPLE_RATE,
                                               song.truncated, speed, pcm));
        if (direct) continue;
        Yue2Request replay = request_replay(request, song.score.empty() ? request.abc : song.score,
                                            pipeline_format_tokens(song.tokens), (int) t / M, (int) t % M);
        auto replay_json = yue_agent::parse(request_to_json(&replay));
        yue_agent::Json recorded;
        size_t field_index, field_max; yyjson_val * key, * value;
        yyjson_obj_foreach(yyjson_doc_get_root(replay_json.get()), field_index, field_max, key, value)
            recorded.copy(yyjson_get_str(key), value);
        recorded.json("generation", generations.back());
        request_parts.push_back(recorded.dump());
        latents.push_back(std::move(song.latents));
    }

    // The compute worker owns ModelStore. Publish an immutable snapshot before
    // DONE so HTTP threads never inspect resident models while they are changing.
    double audio_seconds = 0;
    bool truncated = false;
    for (const auto & song : songs) {
        audio_seconds += (double) song.T_audio / YUE2_SAMPLE_RATE;
        truncated = truncated || song.truncated;
    }
    auto finalize_metrics = [&] {
        double worker_seconds = worker_timer.ms() / 1000.0;
        auto * metrics_doc = yyjson_mut_doc_new(nullptr);
        auto * metrics = yyjson_mut_obj(metrics_doc);
        yyjson_mut_doc_set_root(metrics_doc, metrics);
        yyjson_mut_obj_add_int(metrics_doc, metrics, "schema", 1);
        yyjson_mut_obj_add_real(metrics_doc, metrics, "queue_seconds", queue_seconds);
        yyjson_mut_obj_add_real(metrics_doc, metrics, "pipeline_seconds", pipeline_seconds);
        yyjson_mut_obj_add_real(metrics_doc, metrics, "encoding_packaging_seconds", worker_seconds - pipeline_seconds);
        yyjson_mut_obj_add_real(metrics_doc, metrics, "worker_seconds", worker_seconds);
        yyjson_mut_obj_add_real(metrics_doc, metrics, "audio_seconds", audio_seconds);
        yyjson_mut_obj_add_bool(metrics_doc, metrics, "truncated", truncated);
        yyjson_mut_obj_add_bool(metrics_doc, metrics, "keep_loaded", g_keep_loaded);
        yyjson_mut_obj_add_int(metrics_doc, metrics, "steps", request.steps);
        yyjson_mut_obj_add_uint(metrics_doc, metrics, "module_loads", store_load_count(g_pipeline.store) - loads_before);
        yyjson_mut_obj_add_uint(metrics_doc, metrics, "resident_weight_bytes", store_vram_bytes(g_pipeline.store));
        yyjson_mut_obj_add_int(metrics_doc, metrics, "resident_modules", store_gpu_module_count(g_pipeline.store));
        char * metrics_text = yyjson_mut_write(metrics_doc, 0, nullptr);
        if (metrics_text) {
            job->metrics_json = metrics_text;
            free(metrics_text);
        }
        yyjson_mut_doc_free(metrics_doc);
    };
    if (job->cancel.load()) { job->status.store(JobStatus::CANCELLED); return; }
    std::string generation_list = "[";
    for (const auto & generation : generations) { if (generation_list.size() > 1) generation_list += ','; generation_list += generation; }
    generation_list += ']'; job->generations_json = generation_list;
    if (song_export) { song_export(audio_parts.front(), audio_seconds, generations.front()); finalize_metrics(); }
    else {
        const std::string mime = direct ? (pcm ? "audio/pcm" : audio_output_format(request.output_format)->mime) : MULTIPART_MIME;
        g_results->save(job->id, mime, job->metrics_json, [&](std::ostream & out) {
            if (direct) out.write(audio_parts.front().data(), (std::streamsize) audio_parts.front().size());
            else multipart_write_tracks(out, request_parts, audio_parts, audio_output_format(request.output_format)->mime, latents);
            finalize_metrics();
        }, job->generations_json);
    }
    job->status.store(JobStatus::DONE);
}

enum class AgentState { QUEUED, GENERATING, COMPLETE, FAILED, CANCELLED };
struct AgentJob {
    std::shared_ptr<Job> native;
    std::atomic<AgentState> state{AgentState::QUEUED};
    std::atomic<int64_t> expires{0};
};
static std::unique_ptr<yue_agent::Artifacts> g_agent_artifacts;
static std::string g_agent_public_url;
static std::mutex mtx_agent_jobs;
static std::map<std::string, std::shared_ptr<AgentJob>> g_agent_jobs;

static void agent_refresh(const std::shared_ptr<AgentJob> & agent) {
    if (agent->state.load() == AgentState::QUEUED && agent->native &&
        agent->native->status.load() == JobStatus::CANCELLED) {
        agent->state.store(AgentState::CANCELLED);
        agent->expires.store(yue_agent::now_seconds() + yue_agent::LINK_TTL);
    }
}
static void agent_cleanup() {
    g_agent_artifacts->cleanup();
    std::lock_guard<std::mutex> lock(mtx_agent_jobs);
    for (auto it = g_agent_jobs.begin(); it != g_agent_jobs.end();) {
        agent_refresh(it->second);
        auto expires = it->second->expires.load();
        if (expires && expires <= yue_agent::now_seconds()) it = g_agent_jobs.erase(it); else ++it;
    }
}

static std::string agent_submit(const Yue2Request & request) {
    agent_cleanup();
    auto handle = yue_agent::token();
    auto agent = std::make_shared<AgentJob>();
    {
        std::lock_guard<std::mutex> lock(mtx_agent_jobs);
        size_t pending = 0;
        for (const auto & entry : g_agent_jobs) {
            agent_refresh(entry.second);
            auto state = entry.second->state.load();
            if (state == AgentState::QUEUED || state == AgentState::GENERATING) ++pending;
        }
        if (pending >= 8 || g_agent_jobs.size() >= 128) {
            g_queue->note_rejection();
            throw yue_server::QueueFull("Agent song queue is full; retry after 5 seconds with exponential backoff and jitter");
        }
        agent->native = g_queue->submit("mcp", [agent, request, handle](std::shared_ptr<Job> job) {
            agent->state.store(AgentState::GENERATING);
            try {
                run_job(job, request, true, 1, false, [&](const std::string & body, double duration, const std::string & generation) {
                    // Publish directly to MCP storage: no second native audio copy.
                    auto artifact = g_agent_artifacts->save(handle, request.output_format, body, duration, generation);
                    agent->expires.store(artifact.expires);
            });
            auto status = job->status.load();
            if (status == JobStatus::DONE) {
                agent->state.store(AgentState::COMPLETE);
                { std::lock_guard<std::mutex> completion_lock(mtx_agent_jobs); agent->native.reset(); }
                return;
            }
            agent->state.store(status == JobStatus::CANCELLED ? AgentState::CANCELLED : AgentState::FAILED);
        } catch (const std::exception & e) {
            fprintf(stderr, "[Server] MCP song failed during generation or export: %s\n", e.what());
            job->status.store(JobStatus::FAILED);
            agent->state.store(AgentState::FAILED);
        }
        agent->expires.store(yue_agent::now_seconds() + yue_agent::LINK_TTL);
        });
        g_agent_jobs.emplace(handle, agent);
        fprintf(stderr, "[Server] Job %s: queued MCP song\n", agent->native->id.c_str());
    }
    yue_agent::Json j; j.text("job_id", handle); j.text("status", "queued"); j.integer("poll_after_seconds", yue_agent::POLL_AFTER_SECONDS);
    return j.dump();
}

static std::string agent_status(const std::string & handle, bool cancel) {
    std::lock_guard<std::mutex> lock(mtx_agent_jobs);
    auto it = g_agent_jobs.find(handle);
    if (it == g_agent_jobs.end() || (it->second->expires.load() && it->second->expires.load() <= yue_agent::now_seconds()))
        throw std::invalid_argument("Song handle not found or expired");
    auto agent = it->second;
    agent_refresh(agent);
    auto state = agent->state.load();
    if (state == AgentState::COMPLETE) {
        // Publication can complete between the transport's lookup and this
        // state load. Recheck before reporting an unavailable file.
        yue_agent::Artifact artifact;
        if (g_agent_artifacts->find(handle, artifact)) return artifact.metadata(g_agent_public_url);
        throw std::invalid_argument("Song download has expired or is unavailable");
    }
    if (cancel && (state == AgentState::QUEUED || state == AgentState::GENERATING)) {
        g_queue->cancel(agent->native->id); agent_refresh(agent); state = agent->state.load();
    }
    yue_agent::Json j; j.text("job_id", handle); j.integer("poll_after_seconds", yue_agent::POLL_AFTER_SECONDS);
    j.text("status", state == AgentState::QUEUED ? "queued" : state == AgentState::GENERATING ? "generating" :
                     state == AgentState::CANCELLED ? "cancelled" : "failed");
    j.boolean("cancel_requested", agent->native->cancel.load());
    j.integer("queue_position", (int64_t) g_queue->position(agent->native->id));
    if (state == AgentState::FAILED) j.text("message", "Song generation or export failed. Check server logs before retrying.");
    return j.dump();
}

static void api_error(httplib::Response & res, int status, const MusicApiError & error,
                       const char * type = "invalid_request_error") {
    res.status = status;
    res.set_header("Cache-Control", "no-store");
    res.set_content(music_api_error(error, type), "application/json");
}

static bool api_authorized(const httplib::Request & req, httplib::Response & res) {
    if (g_api_key.empty()) return true;
    const std::string expected = g_api_key;
    std::string supplied = req.get_header_value("Authorization");
    std::string scheme = supplied.substr(0, 7);
    for (auto & ch : scheme) ch = (char) std::tolower((unsigned char) ch);
    supplied = scheme == "bearer " ? supplied.substr(7) : std::string{};
    size_t difference = expected.size() ^ supplied.size();
    for (size_t i = 0; i < expected.size(); ++i)
        difference |= (unsigned char) expected[i] ^ (i < supplied.size() ? (unsigned char) supplied[i] : 0);
    if (!difference) return true;
    res.set_header("WWW-Authenticate", "Bearer");
    api_error(res, 401, {"A valid local Bearer API key is required.", "", "invalid_api_key"}, "authentication_error");
    return false;
}

static void handle_music_api(const httplib::Request & req, httplib::Response & res) {
    if (!api_authorized(req, res)) return;
    MusicApiRequest parsed;
    MusicApiError error;
    if (!music_api_parse(req.body, parsed, error)) {
        api_error(res, error.code == "model_not_found" ? 404 : 400, error);
        return;
    }
    if (!audio_output_format(parsed.native.output_format)) {
        api_error(res, 400, {"Unknown audio format. See /openapi.json for supported formats.", "response_format", "unsupported_value"});
        return;
    }
    httplib::Response validation;
    Yue2Request request;
    if (!validate(request_to_json(&parsed.native, false), validation, &request)) {
        std::string message = "Invalid music settings.";
        if (auto * doc = yyjson_read(validation.body.data(), validation.body.size(), 0)) {
            auto * value = yyjson_obj_get(yyjson_doc_get_root(doc), "error");
            if (yyjson_is_str(value)) message = yyjson_get_str(value);
            yyjson_doc_free(doc);
        }
        api_error(res, 400, {message, "", "invalid_value"});
        return;
    }
    auto waiter = g_waiters.acquire();
    if (!waiter) {
        g_queue->note_rejection();
        res.set_header("Retry-After", std::to_string(yue_server::RETRY_SECONDS));
        api_error(res, 429, {"Synchronous generation slots are busy; retry with backoff.", "", "server_busy"}, "rate_limit_error");
        return;
    }
    std::shared_ptr<Job> job;
    try {
        g_results->require_space();
        job = g_queue->submit("api", [request, speed = parsed.speed, pcm = parsed.pcm](std::shared_ptr<Job> queued_job) {
            run_job(queued_job, request, true, speed, pcm);
        });
    } catch (const yue_server::QueueFull & e) {
        res.set_header("Retry-After", std::to_string(yue_server::RETRY_SECONDS));
        api_error(res, 429, {e.what(), "", "queue_full"}, "rate_limit_error"); return;
    } catch (const yue_server::StorageFull & e) {
        api_error(res, 507, {e.what(), "", "storage_full"}, "server_error"); return;
    }
    fprintf(stderr, "[Server] Job %s: queued API song\n", job->id.c_str());
    res.set_header("X-Request-ID", job->id);
    res.set_header("X-YuE2-Job-ID", job->id);
    auto waited = yue_server::wait_for_job(req, *g_queue, job, g_api_timeout, [] { return g_svr->is_running(); });
    if (waited == yue_server::Wait::DISCONNECTED) return;
    if (waited == yue_server::Wait::TIMEOUT) {
        api_error(res, 504, {"Generation exceeded the local API timeout. Use /synth for asynchronous jobs.", "", "generation_timeout"}, "timeout_error");
        return;
    }
    if (job->status.load() != JobStatus::DONE) {
        api_error(res, job->status.load() == JobStatus::CANCELLED ? 409 : 500,
                  {job->status.load() == JobStatus::CANCELLED ? "Generation was cancelled." : "Generation failed. Inspect the local server logs for details.", "", "generation_failed"}, "server_error");
        return;
    }
    res.set_header("Cache-Control", "no-store");
    res.set_header("X-Audio-Sample-Rate", parsed.pcm ? "24000" : "48000");
    res.set_header("X-Audio-Channels", parsed.pcm ? "1" : "2");
    res.set_header("Link", "</job?id=" + job->id + ">; rel=\"describedby\"");
    const char * extension = parsed.pcm ? "pcm" : audio_output_format(request.output_format)->extension;
    res.set_header("Content-Disposition", std::string("attachment; filename=\"song.") + extension + "\"");
    auto result = g_results->find(job->id);
    if (!result) { api_error(res, 500, {"Result storage is unavailable.", "", "result_unavailable"}, "server_error"); return; }
    // Keep this API slot through delivery instead of acquiring a second pool
    // slot and potentially returning retryable 429 after generation succeeded.
    yue_server::serve_result(res, result, g_downloads, waiter);
}

static std::string api_model_json() {
    return R"({"id":"yue2","object":"model","created":0,"owned_by":"hangry-labs","capabilities":{"music_generation":true,"live_generation_streaming":false,"parallel_inference":false,"sample_rate":48000,"channels":2},"aliases":["yue2-3b","tts-1","tts-1-hd","gpt-4o-mini-tts"]})";
}

static void print_usage(const char * prog) {
    fprintf(stderr, "yue2.cpp %s\n\n", YUE2_VERSION);
    fprintf(stderr,
            "Usage: %s --model <gguf> --vae <gguf> [options]\n"
            "\n"
            "Required:\n"
            "  --model <gguf>         Backbone GGUF\n"
            "  --vae <gguf>           VAE GGUF\n"
            "\n"
            "Optional:\n"
            "  --device <name>        Compute device: CUDA0, Vulkan0, MTL0, CPU...\n"
            "                         (default: best available)\n"
            "  --transcriber <gguf>   SheetSage2 GGUF, MERT beside it, enables /transcribe\n"
            "  --tokenizer <gguf>     Audio tokenizer GGUF, MERT beside it, enables /tokenize\n"
            "  --adapters <dir>       Directory of LoRA adapters a request can stack\n"
            "  --host <addr>          Listen address (default: 0.0.0.0)\n"
            "  --port <N>             Listen port (default: 8087)\n"
            "  --max-batch <N>        Song batch limit, one KV set each (default: 1)\n"
            "  --keep-loaded          Keep every model resident in VRAM (default: evict between stages)\n"
            "\n"
            "Debug:\n"
            "  --max-seq <N>          KV cache size (default: model context)\n"
            "  --vae-core <N>         VAE tile core frames (default: 512)\n"
            "  --vae-halo <N>         VAE tile halo frames (default: 16)\n"
            "  --no-fa                Disable flash attention\n"
            "  --clamp-fp16           Clamp hidden states to FP16 range\n",
            prog);
}

int main(int argc, char ** argv) {
    if (argc < 2) {
        print_usage(argv[0]);
        return 1;
    }

    const char *       host   = "0.0.0.0";
    const char *       device = nullptr;
    int                port   = 8087;
    Yue2PipelineParams params;

    for (int i = 1; i < argc; i++) {
        bool last = i + 1 >= argc;
        if (!strcmp(argv[i], "--model") && !last) {
            g_model_path = argv[++i];
        } else if (!strcmp(argv[i], "--vae") && !last) {
            g_vae_path = argv[++i];
        } else if (!strcmp(argv[i], "--device") && !last) {
            device = argv[++i];
        } else if (!strcmp(argv[i], "--transcriber") && !last) {
            g_transcriber_path = argv[++i];
        } else if (!strcmp(argv[i], "--tokenizer") && !last) {
            g_tokenizer_path = argv[++i];
        } else if (!strcmp(argv[i], "--adapters") && !last) {
            params.adapters_dir = argv[++i];
        } else if (!strcmp(argv[i], "--host") && !last) {
            host = argv[++i];
        } else if (!strcmp(argv[i], "--port") && !last) {
            port = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--keep-loaded")) {
            g_keep_loaded = true;
        } else if (!strcmp(argv[i], "--max-batch") && !last) {
            params.max_batch = atoi(argv[++i]);
            if (params.max_batch < 1) {
                params.max_batch = 1;
            }
        } else if (!strcmp(argv[i], "--max-seq") && !last) {
            params.max_seq = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--vae-core") && !last) {
            params.vae_core = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--vae-halo") && !last) {
            params.vae_halo = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--no-fa")) {
            params.no_fa = true;
        } else if (!strcmp(argv[i], "--clamp-fp16")) {
            params.clamp_fp16 = true;
        } else {
            print_usage(argv[0]);
            return 1;
        }
    }

    if (g_model_path.empty() || g_vae_path.empty()) {
        print_usage(argv[0]);
        return 1;
    }
    if (device && !backend_set_device(device)) {
        print_usage(argv[0]);
        return 1;
    }

    LogCapture log_capture;
    if (auto * key = std::getenv("YUE2_API_KEY")) g_api_key = key;
    if (auto * timeout = std::getenv("YUE2_API_TIMEOUT_SECONDS")) {
        char * end = nullptr;
        long seconds = strtol(timeout, &end, 10);
        if (!end || *end || seconds < 1 || seconds > 86400) {
            fprintf(stderr, "[Server] FATAL: YUE2_API_TIMEOUT_SECONDS must be between 1 and 86400.\n");
            return 1;
        }
        g_api_timeout = (int) seconds;
    }
    if (!yue_ffmpeg::available()) {
        fprintf(stderr, "[Server] FATAL: install FFmpeg before starting yue-server.\n");
        return 1;
    }

    // Model loads go through the store: STRICT by default (one half of the
    // backbone resident at a time, the cache staying between them), NEVER
    // with --keep-loaded (everything accumulates)
    g_pipeline.store            = store_create(g_keep_loaded ? EVICT_NEVER : EVICT_STRICT);
    g_pipeline.transcriber_path = g_transcriber_path;
    g_pipeline.tokenizer_path   = g_tokenizer_path;
    if (!pipeline_configure(&g_pipeline, g_model_path.c_str(), g_vae_path.c_str(), params)) {
        store_free(g_pipeline.store);
        return 1;
    }

    httplib::Server svr;
    yue_server::configure_http(svr);
    g_svr = &svr;
    std::unique_ptr<yue_agent::Mcp> mcp;
    try {
        yue_server::StorageLimits limits;
        limits.ttl = (int64_t) runtime_limit("YUE2_RESULT_TTL_SECONDS", 86400, 2592000);
        limits.bytes = runtime_limit("YUE2_RESULT_MAX_BYTES", limits.bytes, 1024ULL * 1024 * 1024 * 1024);
        limits.files = (size_t) runtime_limit("YUE2_RESULT_MAX_FILES", limits.files, 10000);
        const char * results = std::getenv("YUE2_RESULT_DIR");
        g_results = std::make_unique<yue_server::Results>(results && *results ? results : "jobs", limits);
        g_queue = std::make_unique<yue_server::Queue>((size_t) runtime_limit("YUE2_QUEUE_LIMIT", 8, 128));
        const char * output = std::getenv("YUE2_MCP_OUTPUT_DIR");
        g_agent_artifacts = std::make_unique<yue_agent::Artifacts>(output && *output ? output : "agent-artifacts");
        const char * public_url = std::getenv("YUE2_MCP_PUBLIC_URL");
        g_agent_public_url = public_url && *public_url ? public_url : "http://localhost:" + std::to_string(port);
        if (g_agent_public_url.ends_with('/')) g_agent_public_url.pop_back();
        mcp = std::make_unique<yue_agent::Mcp>(*g_agent_artifacts,
            g_agent_public_url, port,
            std::string((const char *) SKILL_md, SKILL_md_len), YUE2_VERSION, agent_submit, agent_status);
        mcp->attach(svr, api_authorized, []() -> std::shared_ptr<void> { return g_downloads.acquire(); });
    } catch (const std::exception & e) {
        fprintf(stderr, "[Server] FATAL: runtime initialization: %s\n", e.what());
        pipeline_free(&g_pipeline); store_free(g_pipeline.store); return 1;
    }
    // File expiry and handle cleanup only. This thread never touches models,
    // the pipeline, or the GPU worker's native result fields.
    std::mutex maintenance_mutex;
    std::condition_variable maintenance_cv;
    bool maintenance_stop = false;
    std::thread maintenance([&] {
        std::unique_lock<std::mutex> lock(maintenance_mutex);
        while (!maintenance_cv.wait_for(lock, std::chrono::seconds(30), [&] { return maintenance_stop; })) {
            try { agent_cleanup(); g_results->cleanup(); }
            catch (const std::exception &) { fprintf(stderr, "[Server] Temporary export cleanup failed\n"); }
        }
    });
    svr.Get("/openapi.json", [](const httplib::Request &, httplib::Response & res) {
        res.set_content(std::string((const char *) openapi_json, openapi_json_len), "application/json");
    });
    svr.Get("/v1/models", [](const httplib::Request & req, httplib::Response & res) {
        if (!api_authorized(req, res)) return;
        res.set_content(std::string("{\"object\":\"list\",\"data\":[") + api_model_json() + "]}", "application/json");
    });
    svr.Get(R"(/v1/models/(.+))", [](const httplib::Request & req, httplib::Response & res) {
        if (!api_authorized(req, res)) return;
        if (!music_api_model(req.matches[1].str())) {
            api_error(res, 404, {"Unknown model. Use yue2 or discover /v1/models.", "model", "model_not_found"});
            return;
        }
        res.set_content(api_model_json(), "application/json");
    });
    svr.Post("/v1/audio/music", handle_music_api);
    svr.Post("/v1/audio/speech", handle_music_api);
    svr.set_error_handler([](const httplib::Request & req, httplib::Response & res) {
        if (req.path.rfind("/v1/", 0) == 0 && res.body.empty())
            api_error(res, res.status, {"The requested API route is unavailable.", "", "not_found"});
    });

    // SO_REUSEADDR lets us rebind a port still in TIME_WAIT after a restart.
    // SO_REUSEPORT is deliberately not set: a second instance on the same port
    // then fails with EADDRINUSE instead of silently sharing the socket and
    // splitting traffic between two daemons.
    svr.set_socket_options([](socket_t sock) {
        int one = 1;
#ifdef _WIN32
        setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, (const char *) &one, sizeof(one));
#else
        setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
#endif
    });

    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);

    yue_server::attach_status_routes(svr, *g_queue, *g_results, g_waiters, g_downloads);

    svr.Get("/props", handle_props);

    svr.Get("/system/gpu", [](const httplib::Request &, httplib::Response & res) {
        res.set_header("Cache-Control", "no-store");
        res.set_content(system_gpu_json(), "application/json");
    });

    svr.Get("/logs", handle_logs);

    svr.Post("/synth", [](const httplib::Request & req, httplib::Response & res) {
        Yue2Request request;
        if (!validate(req.body, res, &request)) {
            return;
        }
        submit_native(res, "synth", [request](std::shared_ptr<Job> job) { run_job(job, request); });
    });

    // POST /transcribe, multipart/form-data: a supported "audio" file part
    // and an optional "melody_only" field that drops the chord symbols. The
    // route is served when a transcriber is given.
    if (!g_transcriber_path.empty()) {
        svr.Post("/transcribe", [](const httplib::Request & req, httplib::Response & res) {
            if (!req.is_multipart_form_data() || !req.form.has_file("audio")) {
                res.status = 400;
                res.set_content(json_string("error", "multipart audio part required"), "application/json");
                return;
            }
            bool                melody_only = req.form.has_field("melody_only");
            auto slot = upload_slot(res); if (!slot) return;
            const std::string & file        = req.form.get_file("audio").content;
            int                 T = 0, sr = 0;
            float *             planar = audio_read_buf((const uint8_t *) file.data(), file.size(), &T, &sr);
            std::vector<float>  audio;
            if (!planar || !mert_mono_24k(planar, T, sr, &audio)) {
                res.status = 400;
                res.set_content(json_string("error", "cannot decode audio"), "application/json");
                return;
            }
            submit_native(res, "transcribe", [audio = std::move(audio), melody_only](std::shared_ptr<Job> job) mutable {
                run_transcribe(job, std::move(audio), melody_only);
            });
        });
    }

    // POST /tokenize, multipart/form-data: an "audio" file part. The
    // route is served when an audio tokenizer is given.
    if (!g_tokenizer_path.empty()) {
        svr.Post("/tokenize", [](const httplib::Request & req, httplib::Response & res) {
            if (!req.is_multipart_form_data() || !req.form.has_file("audio")) {
                res.status = 400;
                res.set_content(json_string("error", "multipart audio part required"), "application/json");
                return;
            }
            auto slot = upload_slot(res); if (!slot) return;
            const std::string & file = req.form.get_file("audio").content;
            int                 T = 0, sr = 0;
            float *             planar = audio_read_buf((const uint8_t *) file.data(), file.size(), &T, &sr);
            std::vector<float>  audio;
            if (!planar || !mert_mono_24k(planar, T, sr, &audio)) {
                res.status = 400;
                res.set_content(json_string("error", "cannot decode audio"), "application/json");
                return;
            }
            submit_native(res, "tokenize", [audio = std::move(audio)](std::shared_ptr<Job> job) mutable {
                run_tokenize(job, std::move(audio));
            });
        });
    }

    // POST /vae, multipart/form-data: exactly one of an "audio" file part
    // (encode: raw latents out) or a "src_latents" part (raw f32 [T, 64]
    // time major, decode: audio out), and an optional "request" part whose
    // output format, peak clip and bitrate drive the decode. The result
    // carries the other side alone, the client holds the one it sent.
    svr.Post("/vae", [](const httplib::Request & req, httplib::Response & res) {
        bool has_audio   = req.is_multipart_form_data() && req.form.has_file("audio");
        bool has_latents = req.is_multipart_form_data() && req.form.has_file("src_latents");
        if (has_audio == has_latents) {
            res.status = 400;
            res.set_content(json_string("error", "provide exactly one of audio (encode) or src_latents (decode)"),
                            "application/json");
            return;
        }
        Yue2Request request;
        request_init(&request);
        if (req.form.has_file("request") &&
            !request_parse_json(&request, req.form.get_file("request").content.c_str())) {
            res.status = 400;
            res.set_content(json_string("error", "invalid JSON in the request part"), "application/json");
            return;
        }
        if (has_audio) {
            auto slot = upload_slot(res); if (!slot) return;
            const std::string & file = req.form.get_file("audio").content;
            int                 T = 0, sr = 0;
            float *             planar = audio_read_buf((const uint8_t *) file.data(), file.size(), &T, &sr);
            if (!planar) {
                res.status = 400;
                res.set_content(json_string("error", "cannot decode audio"), "application/json");
                return;
            }
            std::vector<float> audio(planar, planar + (size_t) 2 * T);
            free(planar);
            submit_native(res, "vae_encode", [audio = std::move(audio), T, sr](std::shared_ptr<Job> job) mutable {
                run_vae_encode(job, std::move(audio), T, sr);
            });
        } else {
            const std::string & file    = req.form.get_file("src_latents").content;
            const size_t        frame   = (size_t) YUE2_LATENT_DIM * sizeof(float);
            int                 T_lat   = (int) (file.size() / frame);
            if (file.empty() || file.size() % frame != 0 || T_lat > YUE2_CONTEXT ||
                !audio_output_format(request.output_format)) {
                res.status = 400;
                res.set_content(json_string("error",
                                            "src_latents must be [T, 64] f32 within the context, "
                                            "output_format known"),
                                "application/json");
                return;
            }
            std::vector<float> latents((size_t) T_lat * YUE2_LATENT_DIM);
            memcpy(latents.data(), file.data(), file.size());
            submit_native(res, "vae_decode", [request, latents = std::move(latents), T_lat](std::shared_ptr<Job> job) mutable {
                run_vae_decode(job, request, std::move(latents), T_lat);
            });
        }
    });

    auto serve_ui = [](const httplib::Request & req, httplib::Response & res) {
        if (req.get_header_value("Accept-Encoding").find("gzip") == std::string::npos) {
            res.status = 406;
            res.set_content("gzip required", "text/plain");
            return;
        }
        res.set_header("Content-Encoding", "gzip");
        res.set_content(std::string((const char *) index_html_gz, index_html_gz_len), "text/html");
    };
    svr.Get("/", serve_ui);
    // Locale pages serve the same offline bundle; switching locale never reloads a job.
    svr.Get("/(en|nb|pl|ja|zh|es)(/docs)?/?", serve_ui);
    svr.Get("/docs", serve_ui);
    svr.Get("/docs/", [](const httplib::Request &, httplib::Response & res) { res.set_redirect("/docs"); });

    fprintf(stderr, "[Server] yue-server %s\n", YUE2_VERSION);
    fprintf(stderr, "[Server] Listening on %s:%d\n", host, port);
    // A failed bind must reach the caller: a supervisor that reads only the
    // exit code would otherwise believe the daemon is up.
    int exit_code = 0;
    if (!svr.listen(host, port)) {
        fprintf(stderr, "[Server] FATAL: cannot bind %s:%d\n", host, port);
        exit_code = 1;
    }

    g_queue->stop();
    { std::lock_guard<std::mutex> lock(maintenance_mutex); maintenance_stop = true; }
    maintenance_cv.notify_all(); maintenance.join();
    pipeline_free(&g_pipeline);
    store_free(g_pipeline.store);
    fprintf(stderr, "[Server] Done\n");
    return exit_code;
}
