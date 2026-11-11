#include "generation-model.h"
#include "agent/artifacts.h"
#include <iostream>
#include <filesystem>

static void check(bool ok, const char * why) { if (!ok) throw std::runtime_error(why); }
int main() {
    using namespace yue_agent;
    auto root = std::filesystem::temp_directory_path() / ("yue2-generation-" + token());
    try {
        std::filesystem::create_directory(root);
        auto * tensors = ggml_init({4096, nullptr, false});
        auto * tensor = ggml_new_tensor_1d(tensors, GGML_TYPE_F32, 8);
        ggml_set_name(tensor, "test.weight"); memset(tensor->data, 0, ggml_nbytes(tensor));
        auto * file = gguf_init_empty(); gguf_add_tensor(file, tensor);
        gguf_set_val_str(file, "general.file_type", "F32");
        auto path = root / "misleading-Q8_0.gguf";
        check(gguf_write_to_file(file, path.string().c_str(), false), "write synthetic GGUF");
        gguf_free(file); ggml_free(tensors);
        auto model = generation_model(path.string()); auto parsed_model = parse(model);
        check(field(yyjson_doc_get_root(parsed_model.get()), "quantization") == "F32", "quantization comes from GGUF, not filename");
        check(model.find(root.string()) == std::string::npos, "model never discloses directory");

        Yue2Request r; request_init(&r); r.lyrics = "PRIVATE LYRICS"; r.style = "PRIVATE STYLE";
        r.seed = 9007199254740993LL; r.lm_seed = 100; r.tempo_bpm_hint = 112;
        r.adapters = {{"/private/provider/test-adapter", .5f}};
        Yue2Execution e; e.mode = "full"; e.planning_source = "generated";
        e.semantic_source = "generated"; e.planning_seed = 104; e.planning_retries = 1;
        e.song_index = 1; e.variation_index = 2; e.guidance = 1;
        e.semantic_sampling = r.semantic_sampling; e.semantic_sampling.max_tokens = 750;
        auto text = generation_json(r, e, model, model, "1.0.0 (test-revision)", 30, false);
        auto doc = parse(text); auto * j = yyjson_doc_get_root(doc.get());
        check(field(j, "seed") == "9007199254740995", "int64 acoustic variation seed preserved exactly");
        check(field(j, "lm_seed") == "101", "semantic batch seed independent of planning retry");
        check(field(yyjson_obj_get(j, "planning"), "seed") == "104", "final planning retry seed recorded");
        check(yyjson_get_int(yyjson_obj_get(yyjson_obj_get(j, "tempo"), "hint_bpm")) == 112, "explicit tempo hint");
        auto * samplers = yyjson_obj_get(j, "sampling");
        check(yyjson_get_int(yyjson_obj_get(yyjson_obj_get(samplers, "semantic"), "max_tokens")) == 750, "effective clamped budget");
        check(text.find("PRIVATE") == std::string::npos && text.find("/private/") == std::string::npos &&
              text.find("guide_token") == std::string::npos && text.find("http") == std::string::npos, "allowlist excludes prompt/path/capability data");
        check(text.size() <= YUE2_GENERATION_MAX_BYTES, "bounded snapshot");
        check(generation_offset_seed(std::numeric_limits<int64_t>::max(), 1) == -1, "unknown overflowing seed is never fabricated");
        r.peak_clip = 1000;
        r.tempo_bpm_hint = 0; e.semantic_source = "replay"; e.planning_source = "supplied"; e.planning_seed = -1;
        text = generation_json(r, e, model, model, "1.0.0 (unknown)", 30, false, 2, true);
        doc = parse(text); j = yyjson_doc_get_root(doc.get());
        check(field(yyjson_obj_get(j, "tempo"), "mode") == "automatic" &&
              yyjson_is_null(yyjson_obj_get(yyjson_obj_get(j, "tempo"), "hint_bpm")), "no invented BPM default");
        check(yyjson_is_null(yyjson_obj_get(j, "lm_seed")) &&
              yyjson_is_null(yyjson_obj_get(yyjson_obj_get(j, "sampling"), "semantic")), "replay does not claim sampled tokens");
        auto * audio = yyjson_obj_get(j, "audio");
        check(yyjson_get_int(yyjson_obj_get(audio, "peak_clip")) == 999, "normalization reports effective clamped setting");
        check(yyjson_get_int(yyjson_obj_get(audio, "sample_rate")) == 24000 &&
              yyjson_is_null(yyjson_obj_get(audio, "duration_seconds")) &&
              yyjson_get_num(yyjson_obj_get(audio, "duration_estimate_seconds")) == 15 && field(audio, "format") == "pcm", "transformed export does not invent a measured duration");
        r.adapters.resize(17, {"adapter", 1});
        doc = parse(generation_json(r, e, model, model, "1.0.0", 30, false));
        check(yyjson_is_null(yyjson_obj_get(yyjson_doc_get_root(doc.get()), "adapters")), "large adapter lists are explicitly unknown, never silently partial");
        std::filesystem::remove_all(root);
        std::cout << "Generation snapshots, exact seeds, effective settings, model identity and bounded disclosure: passed\n";
        return 0;
    } catch (const std::exception & error) {
        std::cerr << error.what() << '\n'; std::filesystem::remove_all(root); return 1;
    }
}
