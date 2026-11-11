#pragma once
// Small, stateless Streamable HTTP profile. All compute is supplied by the
// application's existing FIFO; no model/store/settings access in this layer.
#include "artifacts.h"
#include "request.h"
#include "httplib.h"
#include <cmath>
#include <map>
#include <set>

namespace yue_agent {
inline constexpr const char * SKILL_URI = "yue2://skills/songwriting";
inline constexpr const char * SKILL_PATH = "/skills/songwriting/SKILL.md";
inline constexpr const char * GUIDE_VERSION = "6";
inline constexpr int POLL_AFTER_SECONDS = 30;
inline constexpr const char * INSTRUCTIONS =
    "Retrieve skill first if you have not read it in this conversation, before writing lyrics or using the music tools. "
    "If skill already returned an unexpired guide_token, retrieval is complete: keep the token and proceed rather than calling skill again. "
    "For a lyrics-only request, still read the guide first, then write the lyrics without generating audio. "
    "Write complete songs that suit the brief, usually 2-4 minutes. Prioritize lyrical pacing, rhyme and structure, not word counts. "
    "Use direction for musical style and instruments; put song sections and their order in lyrics. Preserve the user's choices and supplied sung wording unless edits are allowed. "
    "Pass its guide_token to generate_song. Only lyrics, musical direction, duration, tempo hint and export format are available. "
    "Normally omit duration_seconds to use the 300-second ceiling. Override it only for a user-requested duration constraint; do not write enough material to fill five minutes just because that is the ceiling. "
    "Wait poll_after_seconds before checking get_song; normally poll every 30 seconds. Return its HTTP download link, valid one hour after completion. "
    "No inline audio, runtime settings, voice cloning or concurrent inference.";

inline std::string catalog() {
    return R"({"tools":[
      {"name":"skill","description":"Read this skill first if not already read in this conversation, including lyrics-only requests. Call once: a successful result means the skill is loaded. Keep its guide_token and proceed; retrieve again only after expiry. Covers full songs, style, instruments, lyric structure and API use.","inputSchema":{"type":"object","properties":{},"additionalProperties":false},"annotations":{"readOnlyHint":true,"destructiveHint":false,"openWorldHint":false}},
      {"name":"generate_song","description":"Retrieve skill first if you have not read it in this conversation or its token expired. Then use this tool to generate one complete song from lyrics and musical style. Usually plan for 2-4 minutes. Returns a job handle; wait poll_after_seconds before polling get_song for the HTTP link (normally 30 seconds). No settings or advanced inference controls.","inputSchema":{"type":"object","properties":{"guide_token":{"type":"string","pattern":"^[0-9a-f]{64}$","description":"Copy the actual token from skill."},"lyrics":{"type":"string","maxLength":12000,"description":"Complete song lyrics, section labels and sung ad-libs. Use labels for form and order. When formatting supplied lyrics, add only section labels/line breaks unless edits are allowed; no extra production-note prose. Empty for an instrumental."},"direction":{"type":"string","minLength":1,"maxLength":2000,"description":"Musical STYLE: genre blends, mood, instruments (including flute, guitars, strings, synths), vocal delivery, language and production character. Express song structure in lyrics. Request instrumental music if lyrics is empty."},"duration_seconds":{"type":"number","minimum":10,"maximum":360,"default":300,"description":"Ceiling, not a target. Raising it alone does not extend short lyrics. Actual length depends on lyrics, phrasing, repetitions, tempo and arrangement; write enough lyrics for longer vocal songs. Defaults to 300 seconds (five minutes). Normally omit this field; override only for a user-requested duration constraint or range. Do not add material to fill the ceiling. Cannot enforce a minimum or exact length."},"tempo_bpm":{"type":"integer","minimum":30,"maximum":300,"description":"Musical prompt hint, not a guaranteed metronomic tempo or playback-speed change."},"format":{"type":"string","enum":["opus","flac"],"default":"opus","description":"Compact Opus or lossless FLAC, both 48 kHz stereo. Only one file is stored."}},"required":["guide_token","lyrics","direction"],"additionalProperties":false},"annotations":{"readOnlyHint":false,"destructiveHint":false,"openWorldHint":false}},
      {"name":"get_song","description":"Retrieve skill first if you have not read it in this conversation. Then check an existing song job; on completion returns its HTTP download URL, expiry and recorded generation metadata (resolved seeds and effective settings), never audio bytes. Wait poll_after_seconds before the first check and between checks; normally poll every 30 seconds.","inputSchema":{"type":"object","properties":{"job_id":{"type":"string","pattern":"^[0-9a-f]{64}$"}},"required":["job_id"],"additionalProperties":false},"annotations":{"readOnlyHint":true,"destructiveHint":false,"idempotentHint":true,"openWorldHint":false}},
      {"name":"cancel_song","description":"Retrieve skill first if you have not read it in this conversation. Then cancel only the queued or generating song identified by its job handle. Does not change settings or remove completed exports.","inputSchema":{"type":"object","properties":{"job_id":{"type":"string","pattern":"^[0-9a-f]{64}$"}},"required":["job_id"],"additionalProperties":false},"annotations":{"readOnlyHint":false,"destructiveHint":false,"idempotentHint":true,"openWorldHint":false}}
    ]})";
}
inline void strict_keys(yyjson_val * object, std::initializer_list<const char *> allowed) {
    if (!yyjson_is_obj(object)) throw std::invalid_argument("Arguments must be an object");
    size_t index, maximum; yyjson_val * key, * value;
    std::set<std::string> seen;
    yyjson_obj_foreach(object, index, maximum, key, value) {
        (void) value;
        std::string name = str(key);
        bool ok = false;
        for (auto * candidate : allowed) if (name == candidate) ok = true;
        if (!ok || !seen.insert(name).second) throw std::invalid_argument("Unsupported or duplicate argument: " + name);
    }
}
inline std::string required_string(yyjson_val * object, const char * name, size_t max, bool empty = false) {
    auto * value = yyjson_obj_get(object, name);
    if (!yyjson_is_str(value))
        throw std::invalid_argument(std::string(name) + " must be a string within its documented size limit");
    auto text = str(value);
    size_t characters = 0;
    for (unsigned char c : text) if ((c & 0xc0) != 0x80) ++characters;
    if (characters > max) throw std::invalid_argument(std::string(name) + " exceeds its documented character limit");
    if (text.find('\0') != std::string::npos || (!empty && text.find_first_not_of(" \r\n\t") == std::string::npos))
        throw std::invalid_argument(std::string(name) + " must contain text without embedded nulls");
    return text;
}
inline Yue2Request song_request(yyjson_val * args) {
    strict_keys(args, {"guide_token", "lyrics", "direction", "duration_seconds", "tempo_bpm", "format"});
    Yue2Request r; request_init(&r);
    r.synth_batch_size = 1;  // One song artifact per agent call.
    r.duration = 300;  // Generous ceiling, not a target song length.
    r.lyrics = required_string(args, "lyrics", 12000, true);
    r.style = required_string(args, "direction", 2000);
    r.output_format = "opus";
    if (auto * v = yyjson_obj_get(args, "format")) {
        r.output_format = str(v);
        if (r.output_format != "opus" && r.output_format != "flac") throw std::invalid_argument("format must be opus or flac");
    }
    if (auto * v = yyjson_obj_get(args, "duration_seconds")) {
        double n = yyjson_get_num(v);
        if (!yyjson_is_num(v) || !std::isfinite(n) || n < 10 || n > 360)
            throw std::invalid_argument("duration_seconds must be between 10 and 360");
        r.duration = (float) n;
    }
    if (auto * v = yyjson_obj_get(args, "tempo_bpm")) {
        if (!yyjson_is_int(v) || yyjson_get_sint(v) < 30 || yyjson_get_sint(v) > 300)
            throw std::invalid_argument("tempo_bpm must be an integer between 30 and 300");
        r.tempo_bpm_hint = (int) yyjson_get_sint(v);
        r.style += ", " + std::to_string(r.tempo_bpm_hint) + " BPM";
    }
    return r;
}

class Mcp {
    Artifacts & artifacts_;
    std::string base_, authority_, skill_, version_;
    std::set<std::string> hosts_, origins_;
    std::mutex mutex_;
    std::map<std::string, int64_t> guides_;
    std::function<std::string(const Yue2Request &)> submit_;
    std::function<std::string(const std::string &, bool)> status_;

    static std::string lower(std::string value) {
        for (auto & c : value) c = (char) std::tolower((unsigned char) c);
        return value;
    }
    static std::string decode_name(const std::string & value) {
        if (!value.starts_with("=?base64?") || !value.ends_with("?=")) return value;
        auto encoded = value.substr(9, value.size() - 11);
        if (encoded.empty() || encoded.size() % 4 || encoded.size() > 4096) return "";
        const std::string alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        std::string result;
        for (size_t i = 0; i < encoded.size(); i += 4) {
            unsigned n = 0; int padding = 0;
            for (size_t k = 0; k < 4; ++k) {
                auto c = encoded[i + k];
                if (c == '=') { if (k < 2 || i + 4 != encoded.size()) return ""; ++padding; n <<= 6; }
                else {
                    auto at = alphabet.find(c);
                    if (at == std::string::npos || padding) return "";
                    n = (n << 6) | (unsigned) at;
                }
            }
            result += (char) (n >> 16);
            if (padding < 2) result += (char) (n >> 8);
            if (!padding) result += (char) n;
        }
        return result;
    }
    static std::string reply(yyjson_val * id, const std::string & result, bool modern, bool cacheable) {
        Json j; j.text("jsonrpc", "2.0"); j.copy("id", id);
        auto r = parse(result);
        if (!r || !yyjson_is_obj(yyjson_doc_get_root(r.get()))) throw std::runtime_error("Invalid MCP result");
        auto * item = yyjson_val_mut_copy(j.doc, yyjson_doc_get_root(r.get()));
        if (modern) {
            yyjson_mut_obj_add_str(j.doc, item, "resultType", "complete");
            if (cacheable) {
                yyjson_mut_obj_add_str(j.doc, item, "cacheScope", "private");
                yyjson_mut_obj_add_int(j.doc, item, "ttlMs", 0);
            }
        }
        yyjson_mut_obj_add_val(j.doc, j.root, "result", item);
        return j.dump();
    }
    static void error(httplib::Response & res, yyjson_val * id, int code, const std::string & message,
                      int http = 200, const std::string & data = "") {
        Json j, e; j.text("jsonrpc", "2.0");
        if (id) j.copy("id", id); else yyjson_mut_obj_add_null(j.doc, j.root, "id");
        e.integer("code", code); e.text("message", message); if (!data.empty()) e.json("data", data);
        j.json("error", e.dump()); res.status = http; res.set_content(j.dump(), "application/json");
    }
    bool guard(const httplib::Request & req, httplib::Response & res) const {
        res.set_header("Cache-Control", "no-store");
        if (!hosts_.count(lower(req.get_header_value("Host"))) ||
            (req.has_header("Origin") && !origins_.count(lower(req.get_header_value("Origin"))))) {
            error(res, nullptr, -32600, "Untrusted Host or Origin", 403); return false;
        }
        return true;
    }
    std::string tool(const std::string & name, yyjson_val * args) {
        if (name == "skill") {
            strict_keys(args, {});
            std::lock_guard<std::mutex> lock(mutex_);
            auto now = now_seconds();
            for (auto it = guides_.begin(); it != guides_.end();) {
                if (it->second <= now) it = guides_.erase(it); else ++it;
            }
            if (guides_.size() >= 256) throw std::runtime_error("Too many active guide acknowledgements; reuse your existing token");
            std::string key = token(); guides_[key] = now + LINK_TTL;
            Json j; j.text("guide_token", key); j.text("skill_version", GUIDE_VERSION); j.text("skill", skill_);
            j.boolean("skill_loaded", true);
            j.text("next_step", "Skill retrieval is complete. Keep guide_token and continue. For a song, write or prepare the full lyrics and style, then call generate_song. For lyrics only, return the lyrics without generation. Do not retrieve skill again unless the token expires.");
            j.text("expires_at", utc(now + LINK_TTL)); return j.dump();
        }
        if (name == "generate_song") {
            auto request = song_request(args);
            auto guide = required_string(args, "guide_token", 64);
            {
                std::lock_guard<std::mutex> lock(mutex_);
                auto found = guides_.find(guide);
                if (found == guides_.end() || found->second <= now_seconds())
                    throw std::invalid_argument("Read skill first; guide_token is missing, invalid or expired");
            }
            // Native HTTP requests resolve these before queueing. This adapter
            // must do the same: -1 is a sentinel, not a seed for the pipeline.
            request_resolve_seed(&request);
            return submit_(request);
        }
        if (name == "get_song" || name == "cancel_song") {
            strict_keys(args, {"job_id"});
            auto id = required_string(args, "job_id", 64);
            if (!valid_token(id)) throw std::invalid_argument("Invalid song job handle");
            Artifact artifact;
            if (artifacts_.find(id, artifact)) return artifact.metadata(base_);
            return status_(id, name == "cancel_song");
        }
        throw std::invalid_argument("Unknown tool");
    }
    void post(const httplib::Request & req, httplib::Response & res) {
        if (req.body.size() > 128 * 1024) { error(res, nullptr, -32600, "Request too large", 413); return; }
        if (req.get_header_value("Content-Type").find("application/json") != 0) {
            error(res, nullptr, -32600, "Content-Type must be application/json", 415); return;
        }
        auto accept = req.get_header_value("Accept");
        if (accept.find("application/json") == std::string::npos || accept.find("text/event-stream") == std::string::npos) {
            error(res, nullptr, -32600, "Accept must include application/json and text/event-stream", 406); return;
        }
        auto doc = parse(req.body);
        if (!doc) { error(res, nullptr, -32700, "Parse error", 400); return; }
        auto * root = yyjson_doc_get_root(doc.get());
        auto * id = yyjson_obj_get(root, "id");
        auto method = field(root, "method");
        auto * params = yyjson_obj_get(root, "params");
        if (!yyjson_is_obj(root) || field(root, "jsonrpc") != "2.0" || method.empty() ||
            (id && !yyjson_is_str(id) && !yyjson_is_int(id)) || (params && !yyjson_is_obj(params))) {
            error(res, nullptr, -32600, "Invalid request", 400); return;
        }
        if (!id) {
            if (method != "notifications/initialized" && method != "notifications/cancelled") {
                res.status = 400; return;
            }
            // Tool calls return immediately. Cancellation of a song is explicit,
            // via cancel_song, never inferred from another RPC's request id.
            res.status = 202; return;
        }
        auto * meta = yyjson_obj_get(params, "_meta");
        auto protocol = field(meta, "io.modelcontextprotocol/protocolVersion");
        bool modern = !protocol.empty();
        auto header_version = req.get_header_value("MCP-Protocol-Version");
        if (modern) {
            if (protocol != "2026-07-28") {
                Json data; data.json("supported", R"(["2026-07-28","2025-11-25","2025-06-18"])" ); data.text("requested", protocol);
                error(res, id, -32022, "Unsupported protocol version", 400, data.dump()); return;
            }
            if (!yyjson_is_obj(yyjson_obj_get(meta, "io.modelcontextprotocol/clientCapabilities"))) {
                error(res, id, -32602, "Missing clientCapabilities metadata", 400); return;
            }
            auto name = method == "resources/read" ? field(params, "uri") : field(params, "name");
            auto supplied_name = decode_name(req.get_header_value("Mcp-Name"));
            // The only names accepted by this profile are plain ASCII. Accept
            // the protocol's base64 sentinel form too, then compare decoded data.
            if (header_version != protocol || req.get_header_value("Mcp-Method") != method ||
                ((method == "tools/call" || method == "resources/read") && supplied_name != name)) {
                error(res, id, -32020, "MCP header/body mismatch", 400); return;
            }
        } else if (method != "initialize" && header_version != "2025-11-25" && header_version != "2025-06-18") {
            error(res, id, -32602, "Unsupported or missing MCP-Protocol-Version", 400); return;
        }
        try {
            std::string result;
            if ((method == "initialize" && !modern) || method == "server/discover") {
                Json j; j.json("capabilities", R"({"tools":{"listChanged":false},"resources":{"subscribe":false,"listChanged":false}})");
                Json info; info.text("name", "yue2"); info.text("version", version_); j.json("serverInfo", info.dump());
                j.text("instructions", INSTRUCTIONS);
                if (method == "initialize") {
                    auto requested = field(params, "protocolVersion");
                    j.text("protocolVersion", requested == "2025-06-18" ? requested : "2025-11-25");
                } else {
                    j.json("supportedVersions", R"(["2026-07-28","2025-11-25","2025-06-18"])" );
                    j.text("cacheScope", "private"); j.integer("ttlMs", 0);
                }
                result = j.dump();
            } else if (method == "ping" && !modern) result = "{}";
            else if (method == "tools/list") result = catalog();
            else if (method == "resources/list") {
                Json j, item; item.text("uri", SKILL_URI); item.text("name", "yue2-music");
                item.text("description", "Music skill. Retrieve skill first to read and acknowledge it before using the music tools.");
                item.text("mimeType", "text/markdown"); j.json("resources", "[" + item.dump() + "]"); result = j.dump();
            } else if (method == "resources/templates/list") result = R"({"resourceTemplates":[]})";
            else if (method == "resources/read") {
                if (field(params, "uri") != SKILL_URI) { error(res, id, -32602, "Unknown resource", modern ? 400 : 200); return; }
                Json j, item; item.text("uri", SKILL_URI); item.text("mimeType", "text/markdown"); item.text("text", skill_);
                j.json("contents", "[" + item.dump() + "]"); result = j.dump();
            } else if (method == "tools/call") {
                auto name = field(params, "name");
                if (name != "skill" && name != "generate_song" && name != "get_song" && name != "cancel_song") {
                    error(res, id, -32602, "Unknown tool", modern ? 400 : 200); return;
                }
                auto * args = yyjson_obj_get(params, "arguments");
                auto empty = parse("{}"); if (!args) args = yyjson_doc_get_root(empty.get());
                Json j, content;
                try {
                    auto data = tool(name, args);
                    j.json("structuredContent", data); content.text("type", "text"); content.text("text", data);
                    j.boolean("isError", false);
                } catch (const RetryableError & e) {
                    Json retry; retry.text("code", "queue_full"); retry.text("message", e.what());
                    retry.integer("retry_after_seconds", 5);
                    j.json("structuredContent", retry.dump()); content.text("type", "text"); content.text("text", retry.dump());
                    j.boolean("isError", true); res.set_header("Retry-After", "5");
                } catch (const std::exception & e) {
                    content.text("type", "text"); content.text("text", e.what()); j.boolean("isError", true);
                }
                j.json("content", "[" + content.dump() + "]"); result = j.dump();
            } else { error(res, id, -32601, "Method not found", modern ? 404 : 200); return; }
            res.set_content(reply(id, result, modern, method != "tools/call"), "application/json");
        } catch (const std::exception &) { error(res, id, -32603, "Internal error", 500); }
    }
public:
    Mcp(Artifacts & artifacts, std::string base, int internal_port, std::string skill, std::string version,
        std::function<std::string(const Yue2Request &)> submit,
        std::function<std::string(const std::string &, bool)> status)
        : artifacts_(artifacts), base_(std::move(base)), skill_(std::move(skill)), version_(std::move(version)),
          submit_(std::move(submit)), status_(std::move(status)) {
        if (base_.ends_with('/')) base_.pop_back();
        if (!std::regex_match(base_, std::regex(R"(https?://(\[[0-9a-fA-F:]+\]|[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?)(:[0-9]{1,5})?)")))
            throw std::runtime_error("YUE2_MCP_PUBLIC_URL must be an http(s) origin without credentials, path, query or fragment");
        authority_ = lower(base_.substr(base_.find("://") + 3));
        hosts_.insert(authority_); origins_.insert(lower(base_));
        for (const auto & host : {"localhost", "127.0.0.1", "[::1]", "host.docker.internal"}) {
            auto authority = std::string(host) + ":" + std::to_string(internal_port);
            hosts_.insert(authority); origins_.insert("http://" + authority);
        }
    }
    void attach(httplib::Server & svr, std::function<bool(const httplib::Request &, httplib::Response &)> auth,
                std::function<std::shared_ptr<void>()> download_slot = {}) {
        svr.Post("/mcp", [this, auth](const httplib::Request & req, httplib::Response & res) {
            if (guard(req, res) && auth(req, res)) post(req, res);
        });
        auto unsupported = [this, auth](const httplib::Request & req, httplib::Response & res) {
            if (!guard(req, res) || !auth(req, res)) return;
            res.status = 405; res.set_header("Allow", "POST");
        };
        svr.Get("/mcp", unsupported); svr.Delete("/mcp", unsupported);
        svr.Get(SKILL_PATH, [this](const httplib::Request &, httplib::Response & res) {
            res.set_header("Cache-Control", "no-cache"); res.set_content(skill_, "text/markdown; charset=utf-8");
        });
        svr.Get(R"(/artifacts/([0-9a-f]{64})/song\.(opus|flac))", [this, download_slot](const httplib::Request & req, httplib::Response & res) {
            res.set_header("Cache-Control", "no-store"); res.set_header("X-Content-Type-Options", "nosniff");
            Artifact a;
            if (!artifacts_.find(req.matches[1], a) || a.format != req.matches[2]) { res.status = 404; return; }
            auto slot = download_slot ? download_slot() : std::shared_ptr<void>{};
            if (download_slot && !slot) { res.status = 429; res.set_header("Retry-After", "5"); return; }
            auto file = std::make_shared<std::ifstream>(artifacts_.path(a), std::ios::binary);
            if (!*file) { res.status = 404; return; }
            res.set_header("Content-Disposition", "attachment; filename=\"song." + a.format + "\"");
            res.set_header("Accept-Ranges", "bytes");
            res.set_content_provider(a.size, a.mime(), [file, slot](size_t offset, size_t length, httplib::DataSink & sink) {
                std::array<char, 64 * 1024> buffer{};
                file->clear(); file->seekg((std::streamoff) offset);
                auto count = std::min(length, buffer.size()); file->read(buffer.data(), (std::streamsize) count);
                return file->gcount() == (std::streamsize) count && sink.write(buffer.data(), count);
            });
        });
    }
};
}
