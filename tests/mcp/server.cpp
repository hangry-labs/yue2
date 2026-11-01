// Model-free transport/expiry fixture. This executable is not shipped.
#include "agent/mcp.h"
#include "songwriting-skill.hpp"
#include <iostream>

static void check(bool ok, const char * message) { if (!ok) throw std::runtime_error(message); }
int main() {
    using namespace yue_agent;
    auto root = std::filesystem::temp_directory_path() / ("yue2-mcp-check-" + token());
    try {
        int64_t clock = 100000;
        auto expire_root = root / "expiry";
        auto key = token();
        check(key != token() && valid_token(key), "OS capability token");
        {
            Artifacts files(expire_root, [&] { return clock; });
            auto a = files.save(key, "opus", "sample-opus-bytes", 30);
            check(a.expires == clock + 3600, "TTL starts on completion");
            Artifact found;
            check(files.find(key, found), "find fresh artifact");
            check(!files.find("../" + key, found), "path traversal");
            clock += 3599; check(files.find(key, found), "link valid before boundary");
        }
        {
            Artifacts files(expire_root, [&] { return clock; }); Artifact found;
            check(files.find(key, found), "completed link survives restart");
            ++clock; check(!files.find(key, found), "link invalid at exact expiry");
            std::ofstream(expire_root / "user-file.txt") << "keep";
            files.cleanup();
            check(!std::filesystem::exists(expire_root / (key + ".json")), "expired metadata removed");
            check(!std::filesystem::exists(expire_root / (key + ".opus")), "expired audio removed");
            check(std::filesystem::exists(expire_root / "user-file.txt"), "cleanup preserves unrelated files");
        }
        auto args = parse(R"({"guide_token":"ack","lyrics":"[Verse]\nExact words","direction":"English piano","tempo_bpm":90,"duration_seconds":30,"format":"flac"})");
        auto r = song_request(yyjson_doc_get_root(args.get()));
        check(r.lyrics == "[Verse]\nExact words" && r.style == "English piano, 90 BPM", "verbatim translation");
        check(r.steps == 8 && r.seed == -1 && r.lm_seed == -1 && r.lm_batch_size == 1 &&
              r.synth_batch_size == 1 && r.abc.empty() && r.adapters.empty() && r.semantic_tokens.empty(), "fresh normal quality");
        auto default_args = parse(R"({"lyrics":"words","direction":"style"})");
        check(song_request(yyjson_doc_get_root(default_args.get())).duration == 150, "agent full-song default");
        {
            Artifacts bounded(root / "bounded");
            auto first = token(); bounded.save(first, "opus", "retained", 30);
            for (int i = 1; i < 128; ++i) bounded.save(token(), "opus", "small export", 30);
            bool refused = false;
            try { bounded.save(token(), "opus", "overflow", 30); }
            catch (const std::runtime_error &) { refused = true; }
            Artifact still_live;
            check(refused && bounded.find(first, still_live), "capacity never evicts a live download");
        }

        Artifacts artifacts(root / "transport");
        httplib::Server server;
        int port = server.bind_to_any_port("0.0.0.0");
        check(port > 0, "bind fixture");
        auto base = "http://127.0.0.1:" + std::to_string(port);
        std::set<std::pair<int64_t, int64_t>> resolved_seeds;
        Mcp mcp(artifacts, base, port, std::string((const char *) SKILL_md, SKILL_md_len), "test",
            [&](const Yue2Request & request) {
                check(request.lm_seed >= 0 && request.seed >= 0, "random seeds resolved before queueing");
                check(resolved_seeds.emplace(request.lm_seed, request.seed).second, "every take resolves fresh seeds");
                auto id = token();
                artifacts.save(id, request.output_format, "sample-audio-bytes-0123456789", request.duration);
                Json j; j.text("job_id", id); j.text("status", "queued"); return j.dump();
            }, [](const std::string &, bool) -> std::string { throw std::invalid_argument("Song handle not found or expired"); });
        mcp.attach(server, [](const httplib::Request & req, httplib::Response & res) {
            if (req.get_header_value("Authorization") == "Bearer fixture-key") return true;
            res.status = 401; return false;
        });
        std::cout << base << std::endl;
        server.listen_after_bind();
        std::filesystem::remove_all(root);
        return 0;
    } catch (const std::exception & e) {
        std::cerr << e.what() << std::endl;
        std::filesystem::remove_all(root); return 1;
    }
}
