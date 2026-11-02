#pragma once
// Request translation only. Model execution stays on the native FIFO worker.
#include "request.h"
#include "yyjson.h"
#include <cmath>
#include <cstring>
#include <limits>
#include <memory>

struct MusicApiError {
    std::string message;
    std::string param;
    std::string code = "invalid_value";
};

struct MusicApiRequest {
    Yue2Request native;
    bool pcm = false;
    double speed = 1;
};

inline constexpr const char * MUSIC_MODEL_ALIASES[] = {"yue2", "yue2-3b", "tts-1", "tts-1-hd", "gpt-4o-mini-tts"};

static bool music_api_model(const std::string & name) {
    for (auto * alias : MUSIC_MODEL_ALIASES) if (name == alias) return true;
    return false;
}

static std::string music_api_error(const MusicApiError & error, const char * type = "invalid_request_error") {
    auto * doc = yyjson_mut_doc_new(nullptr);
    auto * root = yyjson_mut_obj(doc);
    yyjson_mut_doc_set_root(doc, root);
    auto * item = yyjson_mut_obj(doc);
    yyjson_mut_obj_add_val(doc, root, "error", item);
    yyjson_mut_obj_add_strcpy(doc, item, "message", error.message.c_str());
    yyjson_mut_obj_add_str(doc, item, "type", type);
    if (error.param.empty()) yyjson_mut_obj_add_null(doc, item, "param");
    else yyjson_mut_obj_add_strcpy(doc, item, "param", error.param.c_str());
    yyjson_mut_obj_add_strcpy(doc, item, "code", error.code.c_str());
    char * text = yyjson_mut_write(doc, 0, nullptr);
    std::string result = text ? text : "{}";
    free(text);
    yyjson_mut_doc_free(doc);
    return result;
}

static const char * music_api_voice(const std::string & voice) {
    if (voice.empty() || voice == "auto" || voice == "default") return "";
    if (voice == "female" || voice == "nova" || voice == "shimmer" || voice == "coral") return "clear female lead vocals";
    if (voice == "male" || voice == "echo" || voice == "onyx" || voice == "cedar") return "clear male lead vocals";
    if (voice == "alloy" || voice == "ash" || voice == "sage" || voice == "marin") return "warm clear lead vocals";
    if (voice == "ballad" || voice == "fable" || voice == "verse") return "expressive storytelling lead vocals";
    return nullptr;
}

static bool music_api_parse(const std::string & body, MusicApiRequest & out, MusicApiError & error) {
    out = {};
    error = {};
    auto fail = [&](const std::string & param, const std::string & message, const char * code = "invalid_value") {
        error = {message, param, code};
        return false;
    };
    std::unique_ptr<yyjson_doc, decltype(&yyjson_doc_free)> doc(yyjson_read(body.data(), body.size(), 0), yyjson_doc_free);
    if (!doc || !yyjson_is_obj(yyjson_doc_get_root(doc.get()))) return fail("", "The request body must be a JSON object.", "invalid_json");
    auto * root = yyjson_doc_get_root(doc.get());
    auto get = [&](const char * key) { auto * value = yyjson_obj_get(root, key); return value && !yyjson_is_null(value) ? value : nullptr; };
    for (auto * key : {"model", "input", "lyrics", "style", "instructions", "voice", "response_format", "output_format",
                       "stream_format", "cot", "abc", "semantic_tokens", "source_tokens"}) {
        auto * value = get(key);
        if (value && !yyjson_is_str(value)) return fail(key, std::string(key) + " must be a string.");
        if (value && yyjson_get_len(value) != strlen(yyjson_get_str(value))) return fail(key, "Embedded null characters are not supported.");
    }
    for (auto * key : {"speed", "duration", "cfg_scale", "source_start", "source_end"}) {
        auto * value = get(key);
        if (value && (!yyjson_is_num(value) || !std::isfinite(yyjson_get_num(value)) ||
                      std::abs(yyjson_get_num(value)) > (double) std::numeric_limits<float>::max()))
            return fail(key, std::string(key) + " must be a finite number.");
    }
    for (auto * key : {"steps", "lm_batch_size", "synth_batch_size", "peak_clip", "mp3_bitrate", "seed", "lm_seed", "n"}) {
        auto * value = get(key);
        if (!value) continue;
        if (!yyjson_is_int(value) || (yyjson_is_uint(value) && yyjson_get_uint(value) > (uint64_t) INT64_MAX))
            return fail(key, std::string(key) + " must be a signed 64-bit integer.");
        if (std::string(key) != "seed" && std::string(key) != "lm_seed" &&
            (yyjson_get_sint(value) < INT32_MIN || yyjson_get_sint(value) > INT32_MAX))
            return fail(key, std::string(key) + " is outside the supported integer range.");
    }
    if (auto * value = yyjson_obj_get(root, "plan_retries")) {
        if (!yyjson_is_int(value) || (yyjson_is_uint(value) && yyjson_get_uint(value) > 8) ||
            yyjson_get_sint(value) < 0 || yyjson_get_sint(value) > 8)
            return fail("plan_retries", "plan_retries must be an integer between 0 and 8.");
    }
    for (auto * key : {"abc_sampling", "semantic_sampling"}) {
        auto * sampling = get(key);
        if (!sampling) continue;
        if (!yyjson_is_obj(sampling)) return fail(key, std::string(key) + " must be an object.");
        for (auto * field : {"temperature", "top_p", "repetition_penalty", "top_k", "penalty_window", "min_tokens", "max_tokens"}) {
            auto * value = yyjson_obj_get(sampling, field);
            if (value && (!yyjson_is_num(value) || !std::isfinite(yyjson_get_num(value)) ||
                          std::abs(yyjson_get_num(value)) > (double) INT32_MAX))
                return fail(std::string(key) + "." + field, "Sampling values must be finite numbers within the supported range.");
            if (value && (std::string(field) == "top_k" || std::string(field) == "penalty_window" ||
                          std::string(field) == "min_tokens" || std::string(field) == "max_tokens") && !yyjson_is_int(value))
                return fail(std::string(key) + "." + field, "This sampling setting must be an integer.");
        }
    }
    if (auto * adapters = get("adapters")) {
        if (!yyjson_is_arr(adapters)) return fail("adapters", "adapters must be an array.");
        size_t i, count; yyjson_val * adapter;
        yyjson_arr_foreach(adapters, i, count, adapter) {
            auto * name = yyjson_obj_get(adapter, "name");
            auto * scale = yyjson_obj_get(adapter, "scale");
            if (!yyjson_is_obj(adapter) || !yyjson_is_str(name) ||
                (scale && (!yyjson_is_num(scale) || !std::isfinite(yyjson_get_num(scale)) || std::abs(yyjson_get_num(scale)) > (double) std::numeric_limits<float>::max())))
                return fail("adapters", "Each adapter needs a name and a finite numeric scale.");
        }
    }
    auto text = [&](const char * key) { auto * value = get(key); return value ? std::string(yyjson_get_str(value)) : std::string{}; };
    if (get("model") && !music_api_model(text("model"))) return fail("model", "Unknown model. Use yue2 or discover /v1/models.", "model_not_found");
    if (get("input") && get("lyrics") && text("input") != text("lyrics")) return fail("input", "input and lyrics contain different lyrics. Supply one or matching values.");
    if (get("stream_format") && text("stream_format") != "audio") return fail("stream_format", "Only stream_format=audio is supported. The complete song is generated before delivery.", "unsupported_value");
    if (auto * stream = get("stream")) {
        if (!yyjson_is_bool(stream) || yyjson_get_bool(stream)) return fail("stream", "Live generation streaming is not available. Use stream_format=audio for a completed audio response.", "unsupported_value");
    }
    const char * voice = music_api_voice(text("voice"));
    if (!voice) return fail("voice", "Unknown voice hint. Use auto, female, male or a documented compatibility alias; describe other vocals in instructions.", "unsupported_value");
    if (!request_parse_json(&out.native, body.c_str())) return fail("", "Invalid native music settings.");
    if (get("input")) out.native.lyrics = text("input");
    if (!text("instructions").empty()) {
        if (!out.native.style.empty()) out.native.style += ", ";
        out.native.style += text("instructions");
    }
    if (*voice) {
        if (!out.native.style.empty()) out.native.style += ", ";
        out.native.style += voice;
    }
    if (out.native.style.empty()) out.native.style = out.native.lyrics.empty() ? "instrumental music" : "melodic song, clear lead vocals";
    if (!get("input") && !get("lyrics") && !get("style") && !get("instructions")) return fail("input", "Supply input/lyrics, or style/instructions for an instrumental.", "missing_required_parameter");
    if (get("speed")) out.speed = yyjson_get_num(get("speed"));
    if (out.speed < .25 || out.speed > 4) return fail("speed", "speed must be between 0.25 and 4.0.");
    auto normalize_format = [](std::string name) { if (name == "wav") return std::string("wav16"); return name; };
    if (get("response_format") && get("output_format") && normalize_format(text("response_format")) != normalize_format(text("output_format")))
        return fail("response_format", "response_format and output_format disagree.");
    std::string format = get("response_format") ? text("response_format") : out.native.output_format;
    out.pcm = format == "pcm";
    out.native.output_format = out.pcm ? "wav16" : normalize_format(format);
    if (out.native.lm_batch_size != 1 || out.native.synth_batch_size != 1 || (get("n") && yyjson_get_sint(get("n")) != 1))
        return fail("n", "These endpoints return one track. Use /synth for native multi-track requests.", "unsupported_value");
    if (out.native.duration < 0 || out.native.duration > (float) (INT32_MAX / 25)) return fail("duration", "duration must be a nonnegative frame-budget ceiling within the supported range.");
    return true;
}
