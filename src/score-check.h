// Generated-score checks and bounded replanning, adapted from yue2.cpp PR #21
// (timoncool, MIT): https://github.com/ServeurpersoCom/yue2.cpp/pull/21
// This is a conservative corruption check, not a complete ABC/quality validator.
#pragma once

#include <charconv>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <string>
#include <string_view>

constexpr int YUE2_PLAN_RETRIES_DEFAULT = 2;
constexpr int YUE2_PLAN_RETRIES_MAX = 8;

static bool yue2_plan_retries_valid(int retries) {
    return retries >= 0 && retries <= YUE2_PLAN_RETRIES_MAX;
}

static std::string_view yue2_score_trim(std::string_view text) {
    const size_t first = text.find_first_not_of(" \t\r");
    if (first == std::string_view::npos) return {};
    const size_t last = text.find_last_not_of(" \t\r");
    return text.substr(first, last - first + 1);
}

// Comments start outside quoted chord symbols; escaped quotes stay in the quote.
static std::string_view yue2_score_uncomment(std::string_view line) {
    bool quoted = false;
    for (size_t i = 0; i < line.size(); ++i) {
        if (line[i] == '\\' && i + 1 < line.size()) { ++i; continue; }
        if (line[i] == '"') quoted = !quoted;
        else if (!quoted && line[i] == '%') return line.substr(0, i);
    }
    return line;
}

static bool yue2_score_positive(std::string_view text) {
    text = yue2_score_trim(text);
    if (text.empty()) return false;
    int value = 0;
    const auto parsed = std::from_chars(text.data(), text.data() + text.size(), value);
    return parsed.ec == std::errc() && parsed.ptr == text.data() + text.size() && value > 0;
}

static bool yue2_score_fraction(std::string_view value, bool meter = false) {
    const size_t slash = value.find('/');
    if (slash == std::string_view::npos || !yue2_score_positive(value.substr(slash + 1))) return false;
    auto numerator = yue2_score_trim(value.substr(0, slash));
    // Accept additive meters such as (2+3)/8 without judging their musical use.
    if (meter && numerator.size() >= 2 && numerator.front() == '(' && numerator.back() == ')')
        numerator = numerator.substr(1, numerator.size() - 2);
    for (;;) {
        const size_t plus = meter ? numerator.find('+') : std::string_view::npos;
        if (!yue2_score_positive(numerator.substr(0, plus))) return false;
        if (plus == std::string_view::npos) return true;
        numerator.remove_prefix(plus + 1);
    }
}

static int yue2_score_stray_colons(std::string_view line) {
    int stray = 0, depth = 0;
    bool quoted = false;
    for (size_t i = 0; i < line.size(); ++i) {
        const char c = line[i];
        if (c == '\\' && i + 1 < line.size()) { ++i; continue; }
        if (c == '"') quoted = !quoted;
        else if (quoted) continue;
        else if (c == '%') break;
        else if (c == '[') ++depth;
        else if (c == ']') depth = depth > 0 ? depth - 1 : 0;
        else if (c == ':' && depth == 0) {
            const char before = i ? line[i - 1] : 0;
            const char after = i + 1 < line.size() ? line[i + 1] : 0;
            if (before != '|' && after != '|' && before != ':' && after != ':') ++stray;
        }
    }
    return stray;
}

// Printable ASCII keeps a damaged UTF-8 plan from breaking log consumers.
static std::string yue2_score_excerpt(const std::string & abc, size_t limit) {
    std::string out;
    out.reserve(abc.size() < limit ? abc.size() : limit);
    for (unsigned char c : abc) {
        if (out.size() == limit) break;
        out += c == '\n' || (c >= 0x20 && c < 0x7f) ? (char) c : '?';
    }
    return out;
}

static std::string yue2_score_problem(const std::string & abc) {
    bool meter = false, length = false, key = false, voice = false, bars = false;
    int stray = 0;
    size_t from = 0;
    while (from < abc.size()) {
        const size_t end = abc.find('\n', from);
        auto line = yue2_score_trim(yue2_score_uncomment(std::string_view(abc).substr(
            from, end == std::string::npos ? std::string::npos : end - from)));
        from = end == std::string::npos ? abc.size() : end + 1;
        if (line.empty()) continue;
        const bool field = line.size() >= 2 && line[1] == ':' &&
            ((line[0] >= 'A' && line[0] <= 'Z') || (line[0] >= 'a' && line[0] <= 'z'));
        if (field) {
            const auto value = yue2_score_trim(line.substr(2));
            if (!key && line[0] == 'M')
                meter = meter || value == "C" || value == "C|" || value == "none" || yue2_score_fraction(value, true);
            else if (!key && line[0] == 'L') length = length || yue2_score_fraction(value);
            else if (line[0] == 'K') key = key || !value.empty();
            else if (line[0] == 'V') voice = voice || !value.empty();
            continue;
        }
        bars = bars || line.find('|') != std::string_view::npos;
        stray += yue2_score_stray_colons(line);
    }
    std::string missing;
    const auto need = [&](bool present, const char * name) {
        if (!present) { if (!missing.empty()) missing += ", "; missing += name; }
    };
    need(meter, "M:"); need(length, "L:"); need(key, "K:");
    if (!missing.empty()) return "header has no well-formed " + missing;
    if (!voice || !bars) return "score has no voice with bars";
    if (stray) return "stray colons inside note runs (" + std::to_string(stray) + ")";
    return {};
}

static bool yue2_plan_retry_seed(int64_t base, int song, int songs, int attempt, int64_t * result) {
    if (songs < 1 || song < 0 || song >= songs || attempt < 1 || attempt > YUE2_PLAN_RETRIES_MAX) return false;
    const int64_t offset = (int64_t) attempt * songs + song;
    if (base > std::numeric_limits<int64_t>::max() - offset) return false;
    *result = base + offset;
    return true;
}

// Replan updates score and its captured token/truncation data together. Keeping
// this small loop model-free lets tests exercise the same retry policy as CUDA.
template<class Replan, class Cancelled>
static bool yue2_check_planned_score(const std::string & score, int64_t base_seed, int song, int songs,
                                    int retries, bool stochastic, Replan replan, Cancelled cancelled) {
    if (!yue2_plan_retries_valid(retries)) return false;
    std::string problem = yue2_score_problem(score);
    for (int attempt = 1; !problem.empty() && stochastic && attempt <= retries; ++attempt) {
        if (cancelled()) return false;
        int64_t seed = 0;
        if (!yue2_plan_retry_seed(base_seed, song, songs, attempt, &seed)) {
            fprintf(stderr, "[Plan] FATAL: retry seed exceeds the signed 64-bit range\n");
            return false;
        }
        fprintf(stderr, "[Plan] song %d: %s; retry %d/%d with lm_seed %lld\n", song + 1,
                problem.c_str(), attempt, retries, (long long) seed);
        if (!replan(seed)) return false;
        problem = yue2_score_problem(score);
    }
    if (cancelled()) return false;
    if (problem.empty()) return true;
    fprintf(stderr, "[Plan] score of song %d:\n%s\n", song + 1, yue2_score_excerpt(score, 800).c_str());
    fprintf(stderr, "[Plan] FATAL: generated score is malformed: %s. %s\n", problem.c_str(),
            stochastic ? "Try another seed, reduce score-stage adapter strength, or allow a larger planning budget."
                       : "Greedy planning does not change with another seed; check the planning budget or sampling settings.");
    return false;
}
