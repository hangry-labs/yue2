#pragma once
#include "yyjson.h"
#include <memory>
#include <stdexcept>
#include <string>

namespace yue_agent {
struct RetryableError : std::runtime_error { using std::runtime_error::runtime_error; };
using ReadDoc = std::unique_ptr<yyjson_doc, decltype(&yyjson_doc_free)>;
inline ReadDoc parse(const std::string & text) { return ReadDoc(yyjson_read(text.data(), text.size(), 0), yyjson_doc_free); }
inline std::string str(yyjson_val * v) { return yyjson_is_str(v) ? std::string(yyjson_get_str(v), yyjson_get_len(v)) : ""; }
inline std::string field(yyjson_val * v, const char * key) { return str(yyjson_obj_get(v, key)); }
struct Json {
    yyjson_mut_doc * doc = yyjson_mut_doc_new(nullptr);
    yyjson_mut_val * root = yyjson_mut_obj(doc);
    Json() { if (!doc) throw std::bad_alloc(); yyjson_mut_doc_set_root(doc, root); }
    ~Json() { yyjson_mut_doc_free(doc); }
    Json(const Json &) = delete;
    Json & operator=(const Json &) = delete;
    void text(const char * key, const std::string & value) { yyjson_mut_obj_add_strncpy(doc, root, key, value.data(), value.size()); }
    void integer(const char * key, int64_t value) { yyjson_mut_obj_add_int(doc, root, key, value); }
    void number(const char * key, double value) { yyjson_mut_obj_add_real(doc, root, key, value); }
    void boolean(const char * key, bool value) { yyjson_mut_obj_add_bool(doc, root, key, value); }
    void copy(const char * key, yyjson_val * value) { yyjson_mut_obj_add_val(doc, root, key, yyjson_val_mut_copy(doc, value)); }
    void json(const char * key, const std::string & value) {
        auto parsed = parse(value);
        if (!parsed) throw std::runtime_error("Invalid internal JSON");
        copy(key, yyjson_doc_get_root(parsed.get()));
    }
    std::string dump() const {
        char * data = yyjson_mut_write(doc, 0, nullptr);
        if (!data) throw std::bad_alloc();
        std::string value(data); free(data); return value;
    }
};
}
