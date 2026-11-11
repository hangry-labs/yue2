#pragma once
// Small execution snapshots. Never serialize the request wholesale: it contains
// lyrics, supplied tokens and other material that is not generation metadata.
#include "request.h"
#include "agent/json.h"
#include <algorithm>
#include <limits>

inline constexpr size_t YUE2_GENERATION_MAX_BYTES = 16384;
inline std::string generation_basename(const std::string & value) {
    return value.substr(value.find_last_of("/\\") == std::string::npos ? 0 : value.find_last_of("/\\") + 1);
}
struct Yue2Execution {
    std::string mode, planning_source, semantic_source;
    int64_t planning_seed = -1;
    int planning_retries = 0, song_index = 0, variation_index = 0;
    float guidance = 1;
    Yue2Sampling semantic_sampling{};
};
inline void generation_seed(yue_agent::Json & out, const char * key, int64_t value) {
    // Decimal strings preserve the full int64 value in JavaScript consumers.
    if (value < 0) out.json(key, "null"); else out.text(key, std::to_string(value));
}
inline int64_t generation_offset_seed(int64_t base, int offset) {
    if (base < 0 || offset < 0 || base > std::numeric_limits<int64_t>::max() - offset) return -1;
    return base + offset;
}
inline std::string generation_sampler(const Yue2Sampling & s) {
    yue_agent::Json j;
    j.number("temperature", s.temperature); j.number("top_p", s.top_p); j.integer("top_k", s.top_k);
    j.number("repetition_penalty", s.repetition_penalty); j.integer("penalty_window", s.penalty_window);
    j.integer("min_tokens", s.min_tokens); j.integer("max_tokens", s.max_tokens); return j.dump();
}
inline std::string generation_json(const Yue2Request & r, const Yue2Execution & e,
                                    const std::string & model, const std::string & vae,
                                    const std::string & build, double duration, bool truncated,
                                    double speed = 1, bool pcm = false) {
    using yue_agent::Json;
    Json j; j.integer("schema_version", 1);
    j.json("model", model); j.json("decoder", vae);
    Json serving; auto split = build.find(" (");
    serving.text("version", build.substr(0, split));
    if (split != std::string::npos && build.back() == ')' && build.substr(split + 2, build.size() - split - 3) != "unknown")
        serving.text("revision", build.substr(split + 2, build.size() - split - 3));
    else serving.json("revision", "null");
    j.json("serving", serving.dump());
    generation_seed(j, "base_seed", r.seed); generation_seed(j, "seed", generation_offset_seed(r.seed, e.variation_index));
    generation_seed(j, "base_lm_seed", r.lm_seed);
    generation_seed(j, "lm_seed", e.semantic_source == "replay" ? -1 : generation_offset_seed(r.lm_seed, e.song_index));
    Json plan; plan.text("mode", e.mode); plan.text("source", e.planning_source);
    generation_seed(plan, "base_seed", e.planning_source == "generated" ? generation_offset_seed(r.lm_seed, e.song_index) : -1);
    generation_seed(plan, "seed", e.planning_seed); plan.integer("retries_used", e.planning_retries);
    plan.integer("retry_limit", r.plan_retries); j.json("planning", plan.dump());
    Json tempo; tempo.text("mode", r.tempo_bpm_hint ? "hint" : "automatic");
    if (r.tempo_bpm_hint) tempo.integer("hint_bpm", r.tempo_bpm_hint); else tempo.json("hint_bpm", "null");
    tempo.json("measured_bpm", "null"); j.json("tempo", tempo.dump());
    j.integer("steps", r.steps);
    if (e.semantic_source == "replay") j.json("guidance", "null"); else j.number("guidance", e.guidance);
    j.text("semantic_source", e.semantic_source);
    Json sampling;
    sampling.json("planning", e.planning_source == "generated" ? generation_sampler(r.abc_sampling) : "null");
    sampling.json("semantic", e.semantic_source == "replay" ? "null" : generation_sampler(e.semantic_sampling));
    j.json("sampling", sampling.dump());
    j.integer("song_index", e.song_index); j.integer("variation_index", e.variation_index);
    j.number("duration_ceiling_seconds", r.duration); j.boolean("truncated", truncated);
    // Adapter identifiers are the public request IDs, never resolved file paths.
    j.integer("adapter_count", (int64_t) r.adapters.size());
    bool complete = r.adapters.size() <= 16;
    std::string adapters = "[";
    if (complete) for (const auto & a : r.adapters) {
        if (adapters.size() > 1) adapters += ',';
        Json item; auto name = generation_basename(a.name);
        if (name.size() > 255) { complete = false; break; }
        item.text("id", name); item.number("scale", a.scale); adapters += item.dump();
    }
    adapters += ']'; complete = complete && adapters.size() <= 8192;
    j.json("adapters", complete ? adapters : "null"); j.boolean("adapters_complete", complete);
    Json audio; audio.text("format", pcm ? "pcm" : r.output_format);
    audio.integer("sample_rate", pcm ? 24000 : 48000); audio.integer("channels", pcm ? 1 : 2);
    audio.number("source_duration_seconds", duration); audio.number("speed", speed);
    if (speed == 1) {
        audio.number("duration_seconds", duration); audio.text("duration_basis", "generated_pcm_samples");
    } else {
        // atempo output framing is not necessarily exactly input_samples/speed.
        audio.json("duration_seconds", "null"); audio.number("duration_estimate_seconds", duration / speed);
        audio.text("duration_basis", "unmeasured_after_speed_adjustment");
    }
    const bool normalized = r.output_format != "wav32" || pcm;
    audio.text("normalization", normalized ? "percentile_peak" : "none");
    if (normalized) audio.integer("peak_clip", std::clamp(r.peak_clip, 0, 999)); else audio.json("peak_clip", "null");
    if (r.output_format == "mp3" && !pcm) audio.integer("mp3_bitrate_kbps", r.mp3_bitrate);
    j.json("audio", audio.dump());
    auto result = j.dump();
    if (result.size() > YUE2_GENERATION_MAX_BYTES) throw std::runtime_error("Generation metadata exceeds its bound");
    return result;
}
