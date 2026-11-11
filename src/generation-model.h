#pragma once
#include "generation.h"
#include "gguf-weights.h"
#include <map>
#include <cctype>
#include <memory>

// Read only GGUF descriptors, never tensor data or a filename-based quant guess.
// Called on the compute worker at execution, never by a metadata GET handler.
inline std::string generation_model(const std::string & path) {
    using yue_agent::Json;
    Json j; j.text("filename", generation_basename(path));
    ggml_context * meta = nullptr;
    gguf_init_params params{true, &meta};
    auto * header = gguf_init_from_file(path.c_str(), params);
    if (!header) { j.json("quantization", "null"); return j.dump(); }
    std::unique_ptr<gguf_context, decltype(&gguf_free)> owner(header, gguf_free);
    std::unique_ptr<ggml_context, decltype(&ggml_free)> tensors(meta, ggml_free);
    std::map<ggml_type, std::pair<int64_t, size_t>> types;
    for (auto * tensor = ggml_get_first_tensor(meta); tensor; tensor = ggml_get_next_tensor(meta, tensor)) {
        auto & item = types[tensor->type]; ++item.first; item.second += ggml_nbytes(tensor);
    }
    std::string quant, source, list = "[";
    size_t dominant = 0;
    for (const auto & entry : types) {
        std::string name = ggml_type_name(entry.first);
        for (auto & c : name) c = (char) std::toupper((unsigned char) c);
        Json item; item.text("type", name); item.integer("count", entry.second.first);
        if (list.size() > 1) list += ',';
        list += item.dump();
        if (entry.second.second > dominant) { dominant = entry.second.second; quant = name; source = "dominant_tensor_storage"; }
    }
    list += ']'; j.json("tensor_types", list);
    auto index = gguf_find_key(header, "general.file_type");
    if (index >= 0 && gguf_get_kv_type(header, index) == GGUF_TYPE_STRING) {
        std::string declared = gguf_get_val_str(header, index);
        if (!declared.empty() && declared.size() <= 64 && declared.find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-. ") == std::string::npos) {
            quant = declared; source = "gguf.general.file_type";
        }
    }
    if (index >= 0 && gguf_get_kv_type(header, index) == GGUF_TYPE_UINT32)
        j.integer("gguf_file_type", gguf_get_val_u32(header, index));
    if (quant.empty()) j.json("quantization", "null"); else j.text("quantization", quant);
    if (source.empty()) j.json("quantization_source", "null"); else j.text("quantization_source", source);
    return j.dump();
}
