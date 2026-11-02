// Include first: score checking must be usable without GGML or transitive headers.
#include "score-check.h"
#include "request.h"

#include <set>
#include <vector>

static int failures = 0;
static void check(bool ok, const char * message) {
    if (!ok) { fprintf(stderr, "FAIL: %s\n", message); ++failures; }
}

static const std::string GOOD =
    "X:1\nT:\nM:4/4\nL:1/8\nQ:1/4=100\n"
    "V: Vocal clef=treble\nV: Ins clef=treble\nK:C\n"
    "% verse\nV: Vocal\n|:\"C\"C2D2E2F2:|[K:G]GABc|\n"
    "V: Ins\nz8|Z2|\n";

int main(int argc, char ** argv) {
    if (argc > 1) {
        for (int i = 1; i < argc; ++i) {
            FILE * file = fopen(argv[i], "rb");
            if (!file) return 2;
            std::string score; char buffer[4096]; size_t n;
            while ((n = fread(buffer, 1, sizeof buffer, file))) score.append(buffer, n);
            fclose(file);
            const std::string problem = yue2_score_problem(score);
            printf("%s: %s\n", argv[i], problem.empty() ? "OK" : problem.c_str());
            if (!problem.empty()) ++failures;
        }
        return failures ? 1 : 0;
    }
    check(yue2_score_problem(GOOD).empty(), "native two-voice score passes");
    for (auto meter : {"C", "C|", "none", "3/4", "(2+3)/8", "2+3/8"}) {
        check(yue2_score_problem(std::string("M:") + meter + "\nL:1/8\nK:C\nV:1\nCDEF|\n").empty(),
              "supported meter variants pass");
    }
    check(yue2_score_problem("  M:4/4 % comment: yes\r\n L:1/8\r\nK:C\r\nV:1\r\nCDEF| % clock 1:20\r\n").empty(),
          "comments, CRLF and leading whitespace do not reject valid notation");
    check(!yue2_score_problem("").empty(), "empty plan refused");
    check(!yue2_score_problem("M:4/x\nL:0/8\nK:C\nV:1\nCDEF|\n").empty(), "invalid fractions refused");
    check(!yue2_score_problem("M:999999999999999999/4\nL:1/8\nK:C\nV:1\nCDEF|\n").empty(), "fraction overflow rejected safely");
    check(!yue2_score_problem("M:4/4\nL:1/8\nV:1\nCDEF|\n").empty(), "missing key refused");
    check(!yue2_score_problem("M:4/4\nL:1/8\nK:C\n").empty(), "no voice/body refused");
    check(!yue2_score_problem("M:4/4\nL:1/8\nK:C\nV:1\nCD:E:F|\n").empty(), "damaged note runs refused");
    check(yue2_score_stray_colons("|:CDEF:|::GABc|\"A:7\"C[K:G]D") == 0, "legal colons pass");
    check(yue2_score_stray_colons("\"chord \\\" : \\\"\"CD| % 1:20") == 0, "escaped quotes and comment colons pass");
    check(yue2_score_excerpt("K:C\n\xd0\xb0\x1b", 64) == "K:C\n???", "log excerpt is printable and omits control escapes");
    check(yue2_score_excerpt("abcdef", 3) == "abc", "log excerpt is bounded");

    const auto never_cancel = [] { return false; };
    std::string score = GOOD;
    std::vector<int64_t> seeds;
    auto replan = [&](int64_t seed) { seeds.push_back(seed); score = GOOD; return true; };
    check(yue2_check_planned_score(score, 100, 0, 1, 2, true, replan, never_cancel) && seeds.empty(),
          "valid first plan invokes no generator/retry");
    score = "broken";
    check(yue2_check_planned_score(score, 100, 1, 3, 2, true, replan, never_cancel) && seeds == std::vector<int64_t>{104},
          "one retry replaces failed plan with a valid plan using its batch seed");
    score = "broken"; seeds.clear();
    auto broken = [&](int64_t seed) { seeds.push_back(seed); score = "still broken"; return true; };
    check(!yue2_check_planned_score(score, 100, 1, 3, 2, true, broken, never_cancel) &&
          seeds == std::vector<int64_t>{104,107}, "exhaustion is bounded to extra attempts");
    score = "broken"; seeds.clear();
    check(!yue2_check_planned_score(score, 100, 0, 1, 0, true, replan, never_cancel) && seeds.empty(),
          "zero retries still checks and refuses a broken score");
    check(!yue2_check_planned_score(score, 100, 0, 1, 2, false, replan, never_cancel) && seeds.empty(),
          "greedy planning does not retry an identical deterministic plan");
    check(!yue2_check_planned_score(score, 100, 0, 1, 2, true, replan, [] { return true; }) && seeds.empty(),
          "cancellation before retry never invokes the generator");
    bool cancel = false;
    auto cancel_during = [&](int64_t seed) { seeds.push_back(seed); cancel = true; return false; };
    check(!yue2_check_planned_score(score, 100, 0, 1, 8, true, cancel_during, [&] { return cancel; }) && seeds.size() == 1,
          "cancel/failure during generation does not start another retry");
    score = "broken"; seeds.clear();
    int attempts = 0;
    auto recover_second = [&](int64_t seed) { seeds.push_back(seed); if (++attempts == 2) score = GOOD; return true; };
    check(yue2_check_planned_score(score, 100, 0, 1, 2, true, recover_second, never_cancel) &&
          seeds == std::vector<int64_t>{101,102}, "final allowed retry can succeed");
    score = "broken"; seeds.clear();
    check(!yue2_check_planned_score(score, INT64_MAX, 0, 1, 2, true, replan, never_cancel) && seeds.empty(),
          "retry seed overflow fails safely before invoking generator");
    int64_t retry_seed = 0;
    check(yue2_plan_retry_seed(INT64_MAX-1, 0, 1, 1, &retry_seed) && retry_seed == INT64_MAX,
          "largest representable retry seed remains usable");
    std::set<int64_t> distinct;
    for (int i = 0; i < 4; ++i) distinct.insert(100+i);
    for (int k = 1; k <= 8; ++k) for (int i = 0; i < 4; ++i) {
        check(yue2_plan_retry_seed(100, i, 4, k, &retry_seed) && distinct.insert(retry_seed).second,
              "retry seeds do not collide with another song or attempt");
    }

    Yue2Request request;
    std::string error;
    check(request_parse_json(&request, "{}", &error) && request.plan_retries == 2 && error.empty(), "default two retries");
    check(request.synth_batch_size == 2, "fresh requests default to two acoustic variations");
    for (int value : {1,2,3}) {
        const std::string json = "{\"synth_batch_size\":" + std::to_string(value) + "}";
        check(request_parse_json(&request, json.c_str()) && request.synth_batch_size == value, "allowed variation count");
    }
    for (const char * value : {"0", "-1", "4", "9", "4294967298", "9223372036854775807", "2.0", "2.5", "true", "null", "\"2\"", "[]", "{}"}) {
        const std::string json = std::string("{\"synth_batch_size\":") + value + "}";
        check(!request_parse_json(&request, json.c_str(), &error) && error.find("synth_batch_size") != std::string::npos,
              "variation cap and integer validation cannot be bypassed");
    }
    check(request_parse_json(&request, "{\"semantic_tokens\":\"1,2,3\"}") && request.synth_batch_size == 1,
          "legacy per-track replay stays one variation");
    check(request_parse_json(&request, "{\"semantic_tokens\":\"1,2,3\",\"synth_batch_size\":3}") && request.synth_batch_size == 3,
          "explicit variation override on replay is preserved");
    for (int value : {0,2,8}) {
        const std::string json = "{\"plan_retries\":" + std::to_string(value) + "}";
        check(request_parse_json(&request, json.c_str()) && request.plan_retries == value, "allowed retry count parsed");
        const std::string saved = request_to_json(&request, false);
        check(request_parse_json(&request, saved.c_str()) && request.plan_retries == value, "retry count round trip");
    }
    for (const char * value : {"-1","9","1.5","true","null","\"2\"","2147483648","18446744073709551615"}) {
        const std::string json = std::string("{\"plan_retries\":") + value + "}";
        check(!request_parse_json(&request, json.c_str(), &error) && error.find("plan_retries") != std::string::npos,
              "invalid types/ranges do not silently use the default");
    }
    request_init(&request); request.plan_retries = 0;
    Yue2Request replay = request_replay(request, GOOD, "1,2,3", 0, 0);
    check(replay.abc == GOOD && replay.semantic_tokens == "1,2,3" && replay.plan_retries == 0 && replay.synth_batch_size == 1,
          "replay retains actual score/tokens and retry policy");
    if (failures) return 1;
    puts("PASS: score corruption checks, bounded retry/recovery, batch seeds, cancellation and request contracts");
    return 0;
}
