// Model-free qualification of the production queue/storage/HTTP primitives.
// Never installed in the runtime image; artificial workers expose no production knobs.
#include "server/http.h"
#include "agent/mcp.h"
#include "songwriting-skill.hpp"
#include <iostream>
#include <future>

using namespace yue_server;
static void check(bool ok, const char * message) { if (!ok) throw std::runtime_error(message); }
template<class F> static void throws(F fn, const char * message) {
    bool caught = false; try { fn(); } catch (const std::exception &) { caught = true; } check(caught, message);
}
static int64_t number(const std::string & text, const char * key) {
    auto doc = yue_agent::parse(text); return yyjson_get_sint(yyjson_obj_get(yyjson_doc_get_root(doc.get()), key));
}
static void await(const std::function<bool()> & ready) {
    auto end = std::chrono::steady_clock::now() + std::chrono::seconds(5);
    while (!ready()) {
        check(std::chrono::steady_clock::now() < end, "fixture wait timed out");
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
}
static void storage_checks(const std::filesystem::path & root) {
    int64_t now = 100000;
    StorageLimits limits; limits.ttl = 10; limits.bytes = 20; limits.files = 2; limits.file_bytes = 12;
    auto put = [](Results & store, const char * id, const std::string & body) {
        store.save(id, "application/octet-stream", "{\"schema\":1}", [&](std::ostream & out) { out << body; },
                   R"([{"schema_version":1,"seed":"9007199254740993"}])");
    };
    {
        Results store(root, limits, [&] { return now; });
        put(store, "0123456789abcdef", std::string("abc\0xyz", 7));
        auto saved = store.find("0123456789abcdef"); check(saved && saved->size == 7, "binary persisted");
        check(!store.find("../0123456789abcdef"), "traversal rejected");
        throws([&] { put(store, "0123456789abcdef", "replace"); }, "duplicate does not overwrite");
        throws([&] { put(store, "1123456789abcdef", std::string(13, 'X')); }, "per-file bound enforced during write");
        check(!std::filesystem::exists(root / "1123456789abcdef.part"), "partial file cleaned");
        put(store, "2123456789abcdef", "123456789012");
        throws([&] { put(store, "3123456789abcdef", "next"); }, "count/space full keeps live files");
        check(store.find("0123456789abcdef") != nullptr, "no early eviction");
        ++now;
    }
    {
        Results store(root, limits, [&] { return now; });
        auto saved = store.find("0123456789abcdef");
        check(saved && saved->metrics == "{\"schema\":1}" && saved->expires == 100010, "restart retains metadata and expiry");
        check(saved->generations == R"([{"schema_version":1,"seed":"9007199254740993"}])", "native generation metadata survives restart exactly");
        std::ofstream(root / "user-notes.txt") << "keep";
        now = 100010;
        check(!store.find("0123456789abcdef"), "exact expiry refuses new reader");
        store.cleanup(); check(std::filesystem::exists(saved->path), "download lease survives expiry");
        auto path = saved->path; saved.reset(); store.cleanup();
        check(!std::filesystem::exists(path), "expired file removed after last reader");
        check(std::filesystem::exists(root / "user-notes.txt"), "unrelated file untouched");
        check(number(store.snapshot(), "bytes") == 0, "byte accounting released");
    }
    {
        StorageLimits small; small.bytes = 3;
        Results store(root / "bytes", small);
        throws([&] { put(store, "0123456789abcdef", "four"); }, "total byte bound enforced during write");
        check(number(store.snapshot(), "bytes") == 0, "failed write never indexed");
        throws([&] { store.save("0123456789abcdef", "audio/wav", "", [](std::ostream & out) {
            out << "a"; throw std::runtime_error("disk failure");
        }); }, "writer failure unwinds");
        put(store, "0123456789abcdef", "ok"); check(store.find("0123456789abcdef") != nullptr, "worker can recover after storage failure");
    }
    {
        Results store(root / "metrics"); std::string metrics;
        store.save("0123456789abcdef", "audio/wav", metrics, [&](std::ostream & out) {
            out << "body"; metrics = "{\"schema\":1,\"worker_seconds\":2.5}";
        });
        check(store.find("0123456789abcdef")->metrics == metrics, "post-serialization metrics published without body buffering");
    }
    {
        Results store(root / "slow");
        std::promise<void> started, release; auto gate = release.get_future().share();
        auto writing = std::async(std::launch::async, [&] {
            store.save("0123456789abcdef", "audio/wav", "", [&](std::ostream & out) {
                started.set_value(); gate.wait(); out << "ok";
            });
        });
        started.get_future().wait();
        auto reading = std::async(std::launch::async, [&] { return store.snapshot(); });
        bool responsive = reading.wait_for(std::chrono::milliseconds(100)) == std::future_status::ready;
        release.set_value(); writing.get(); reading.get(); check(responsive, "status never waits for a slow result write");
    }
}
static void queue_checks() {
    Queue queue(4); std::atomic<bool> release{false};
    auto blocked = [&](std::shared_ptr<Job> job) {
        while (!release && !job->cancel) std::this_thread::sleep_for(std::chrono::milliseconds(2));
        job->status.store(job->cancel ? JobStatus::CANCELLED : JobStatus::DONE);
    };
    auto first = queue.submit("synth", blocked);
    await([&] { return first->status.load() == JobStatus::RUNNING; });
    auto second = queue.submit("api", blocked);
    auto third = queue.submit("mcp", blocked);
    auto fourth = queue.submit("vae", blocked);
    check(queue.position(second->id) == 1 && queue.position(fourth->id) == 3, "FIFO positions");
    std::vector<std::future<void>> contenders;
    for (int i = 0; i < 32; ++i) contenders.push_back(std::async(std::launch::async, [&] {
        throws([&] { queue.submit("burst", blocked); }, "atomic full admission");
    }));
    for (auto & f : contenders) f.get();
    check(number(queue.snapshot(), "pending") == 4, "global bound across operation kinds");
    check(number(queue.snapshot(), "rejected") == 32, "rejections counted");
    queue.cancel(second->id);
    check(second->status == JobStatus::CANCELLED && queue.position(third->id) == 1, "queued cancel immediately releases slot");
    auto replacement = queue.submit("api", blocked);
    queue.cancel(first->id);
    await([&] { return third->status == JobStatus::RUNNING; });
    release = true;
    await([&] { return number(queue.snapshot(), "pending") == 0; });
    check(replacement->status == JobStatus::DONE, "FIFO drains after active cancellation");
    auto failed = queue.submit("error", [](std::shared_ptr<Job>) { throw std::runtime_error("fixture error"); });
    await([&] { return failed->status == JobStatus::FAILED; });
    auto next = queue.submit("after-error", [](std::shared_ptr<Job> job) { job->status = JobStatus::DONE; });
    await([&] { return next->status == JobStatus::DONE; });
    queue.stop(); throws([&] { queue.submit("stopped", blocked); }, "shutdown refuses new work");
}
int main(int argc, char ** argv) {
    auto root = std::filesystem::temp_directory_path() / ("yue2-server-check-" + yue_agent::token());
    try {
        storage_checks(root / "storage"); queue_checks();
        // Optional caller-owned root lets the HTTP driver restart this exact
        // fixture and verify production storage restoration over the wire.
        auto output = argc > 1 ? std::filesystem::path(argv[1]) : root / "http";
        Queue queue(12); Results results(output); Slots waiters(API_WAITERS), downloads(DOWNLOADS);
        httplib::Server server; configure_http(server);
        attach_status_routes(server, queue, results, waiters, downloads);
        std::atomic<bool> released{false};
        auto submit = [&](const std::string & kind) {
            results.require_space();
            return queue.submit(kind, [&](std::shared_ptr<Job> job) {
                while (!released && !job->cancel) std::this_thread::sleep_for(std::chrono::milliseconds(5));
                if (job->cancel) { job->status = JobStatus::CANCELLED; return; }
                job->metrics_json = "{\"schema\":1,\"fixture\":true}";
                job->generations_json = R"([{"schema_version":1,"seed":"9007199254740993"}])";
                results.save(job->id, "audio/wav", job->metrics_json, [](std::ostream & out) {
                    std::string block(64 * 1024, 'R');
                    for (int i = 0; i < 64; ++i) out.write(block.data(), (std::streamsize) block.size());
                }, job->generations_json);
                job->status = JobStatus::DONE;
            });
        };
        server.Post("/synth", [&](const httplib::Request &, httplib::Response & res) {
            try { auto job = submit("synth"); Json j; j.text("id", job->id); res.set_content(j.dump(), "application/json"); }
            catch (const QueueFull & e) { busy(res, e.what()); }
        });
        auto api = [&](const httplib::Request & req, httplib::Response & res) {
            auto slot = waiters.acquire(); if (!slot) { queue.note_rejection(); busy(res, "Synchronous slots busy"); return; }
            std::shared_ptr<Job> job;
            try { job = submit("api"); } catch (const QueueFull & e) { busy(res, e.what()); return; }
            double timeout = req.has_param("short") ? 0.15 : 30;
            auto waited = wait_for_job(req, queue, job, timeout, [&] { return server.is_running(); });
            if (waited == Wait::DISCONNECTED) return;
            if (waited == Wait::TIMEOUT) { res.status = 504; return; }
            if (job->status != JobStatus::DONE) { res.status = 409; return; }
            serve_result(res, results.find(job->id), downloads, slot);
        };
        server.Post("/v1/audio/music", api); server.Post("/v1/audio/speech", api);
        server.Post("/fixture/release", [&](const httplib::Request &, httplib::Response & res) { released = true; res.status = 204; });
        server.Post("/fixture/hold", [&](const httplib::Request &, httplib::Response & res) { released = false; res.status = 204; });
        server.Post("/fixture/stop", [&](const httplib::Request &, httplib::Response &) { queue.request_stop(); server.stop(); });
        int port = server.bind_to_any_port("127.0.0.1"); check(port > 0, "bind fixture");
        yue_agent::Artifacts artifacts(root / "artifacts");
        auto base = "http://127.0.0.1:" + std::to_string(port);
        yue_agent::Mcp mcp(artifacts, base, port, std::string((const char *) SKILL_md, SKILL_md_len), "fixture",
            [&](const Yue2Request &) { auto job = submit("mcp"); Json j; j.text("job_id", job->id); return j.dump(); },
            [](const std::string &, bool) { return "{}"; });
        mcp.attach(server, [](const httplib::Request &, httplib::Response &) { return true; },
            [&]() -> std::shared_ptr<void> { return downloads.acquire(); });
        std::cout << base << std::endl; server.listen_after_bind(); queue.stop();
        std::filesystem::remove_all(root); return 0;
    } catch (const std::exception & e) {
        std::cerr << e.what() << std::endl; std::filesystem::remove_all(root); return 1;
    }
}
