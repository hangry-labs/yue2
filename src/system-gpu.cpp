#include "system-gpu.h"

#include "yyjson.h"

#include <algorithm>
#include <chrono>
#include <deque>
#include <map>
#include <mutex>
#include <optional>
#include <vector>

#if defined(YUE2_NVML) && defined(__linux__)
#    include <dlfcn.h>
#    include <nvml.h>
#endif

namespace {
using Clock                   = std::chrono::steady_clock;
constexpr size_t MAX_SAMPLES  = 600;
constexpr double RETENTION_MS = 600000;

struct Sample {
    unsigned int                                 index     = 0;
    double                                       timestamp = 0;
    std::string                                  name;
    std::map<std::string, std::optional<double>> values;
};

#if defined(YUE2_NVML) && defined(__linux__)
// Use the toolkit's declarations, loading only read-only NVML entry points.
// The driver supplies this library at runtime; CPU builds need neither NVML
// headers nor a new runtime dependency.
class Nvidia {
    void *            library     = nullptr;
    bool              initialized = false;
    Clock::time_point next_attempt{};

    template <typename T> T symbol(const char * name) { return reinterpret_cast<T>(dlsym(library, name)); }

    template <typename Fn, typename... Args> std::optional<double> number(const char * name, Args... args) {
        auto         fn    = symbol<Fn>(name);
        unsigned int value = 0;
        if (!fn || fn(args..., &value) != NVML_SUCCESS) {
            return std::nullopt;
        }
        return static_cast<double>(value);
    }

    bool ready() {
        if (initialized) {
            return true;
        }
        if (Clock::now() < next_attempt) {
            return false;
        }
        next_attempt = Clock::now() + std::chrono::seconds(10);
        if (!library) {
            library = dlopen("libnvidia-ml.so.1", RTLD_LAZY | RTLD_LOCAL);
        }
        if (!library) {
            return false;
        }
        auto init   = symbol<decltype(&nvmlInit_v2)>("nvmlInit_v2");
        initialized = init && init() == NVML_SUCCESS;
        return initialized;
    }

  public:
    ~Nvidia() {
        if (library) {
            auto shutdown = symbol<decltype(&nvmlShutdown)>("nvmlShutdown");
            if (initialized && shutdown) {
                shutdown();
            }
            dlclose(library);
        }
    }

    std::vector<Sample> sample(double timestamp) {
        std::vector<Sample> result;
        if (!ready()) {
            return result;
        }
        auto         count_fn  = symbol<decltype(&nvmlDeviceGetCount_v2)>("nvmlDeviceGetCount_v2");
        auto         handle_fn = symbol<decltype(&nvmlDeviceGetHandleByIndex_v2)>("nvmlDeviceGetHandleByIndex_v2");
        auto         name_fn   = symbol<decltype(&nvmlDeviceGetName)>("nvmlDeviceGetName");
        unsigned int count     = 0;
        if (!count_fn || !handle_fn || count_fn(&count) != NVML_SUCCESS) {
            return result;
        }
        for (unsigned int index = 0; index < std::min(count, 32u); ++index) {
            nvmlDevice_t device = nullptr;
            if (handle_fn(index, &device) != NVML_SUCCESS) {
                continue;
            }
            Sample s;
            s.index        = index;
            s.timestamp    = timestamp;
            char name[128] = {};
            s.name         = name_fn && name_fn(device, name, sizeof(name)) == NVML_SUCCESS ? name : "NVIDIA GPU";
            auto & v       = s.values;
            auto   util_fn = symbol<decltype(&nvmlDeviceGetUtilizationRates)>("nvmlDeviceGetUtilizationRates");
            nvmlUtilization_t util{};
            const bool        util_ok    = util_fn && util_fn(device, &util) == NVML_SUCCESS;
            v["gpu_utilization_percent"] = util_ok ? std::optional<double>(std::min(util.gpu, 100u)) : std::nullopt;
            v["memory_utilization_percent"] =
                util_ok ? std::optional<double>(std::min(util.memory, 100u)) : std::nullopt;
            auto         memory_fn = symbol<decltype(&nvmlDeviceGetMemoryInfo)>("nvmlDeviceGetMemoryInfo");
            nvmlMemory_t memory{};
            const bool   memory_ok = memory_fn && memory_fn(device, &memory) == NVML_SUCCESS;
            v["memory_used_mb"] =
                memory_ok ? std::optional<double>(static_cast<double>(memory.used) / 1048576) : std::nullopt;
            v["memory_total_mb"] =
                memory_ok ? std::optional<double>(static_cast<double>(memory.total) / 1048576) : std::nullopt;
            v["temperature_c"] =
                number<decltype(&nvmlDeviceGetTemperature)>("nvmlDeviceGetTemperature", device, NVML_TEMPERATURE_GPU);
            v["fan_percent"] = number<decltype(&nvmlDeviceGetFanSpeed)>("nvmlDeviceGetFanSpeed", device);
            if (v["fan_percent"]) {
                v["fan_percent"] = std::min(*v["fan_percent"], 100.0);
            }
            v["power_w"] = number<decltype(&nvmlDeviceGetPowerUsage)>("nvmlDeviceGetPowerUsage", device);
            v["power_limit_w"] =
                number<decltype(&nvmlDeviceGetPowerManagementLimit)>("nvmlDeviceGetPowerManagementLimit", device);
            for (const char * key : { "power_w", "power_limit_w" }) {
                if (v[key]) {
                    v[key] = *v[key] / 1000;
                }
            }
            v["clock_mhz"] =
                number<decltype(&nvmlDeviceGetClockInfo)>("nvmlDeviceGetClockInfo", device, NVML_CLOCK_GRAPHICS);
            v["clock_max_mhz"] =
                number<decltype(&nvmlDeviceGetMaxClockInfo)>("nvmlDeviceGetMaxClockInfo", device, NVML_CLOCK_GRAPHICS);
            v["memory_clock_mhz"] =
                number<decltype(&nvmlDeviceGetClockInfo)>("nvmlDeviceGetClockInfo", device, NVML_CLOCK_MEM);
            v["memory_clock_max_mhz"] =
                number<decltype(&nvmlDeviceGetMaxClockInfo)>("nvmlDeviceGetMaxClockInfo", device, NVML_CLOCK_MEM);
            v["pcie_generation"] =
                number<decltype(&nvmlDeviceGetCurrPcieLinkGeneration)>("nvmlDeviceGetCurrPcieLinkGeneration", device);
            v["pcie_width"] =
                number<decltype(&nvmlDeviceGetCurrPcieLinkWidth)>("nvmlDeviceGetCurrPcieLinkWidth", device);
            auto          state_fn = symbol<decltype(&nvmlDeviceGetPerformanceState)>("nvmlDeviceGetPerformanceState");
            nvmlPstates_t state{};
            v["performance_state"] =
                state_fn && state_fn(device, &state) == NVML_SUCCESS ? std::optional<double>(state) : std::nullopt;
            result.push_back(std::move(s));
        }
        return result;
    }
};
#else
class Nvidia {
  public:
    std::vector<Sample> sample(double) { return {}; }
};
#endif

yyjson_mut_val * sample_json(yyjson_mut_doc * doc, const Sample & s) {
    auto * value = yyjson_mut_obj(doc);
    yyjson_mut_obj_add_uint(doc, value, "index", s.index);
    yyjson_mut_obj_add_real(doc, value, "timestamp", s.timestamp);
    yyjson_mut_obj_add_strcpy(doc, value, "name", s.name.c_str());
    for (const auto & entry : s.values) {
        if (entry.second) {
            yyjson_mut_obj_add_real(doc, value, entry.first.c_str(), *entry.second);
        } else {
            yyjson_mut_obj_add_null(doc, value, entry.first.c_str());
        }
    }
    return value;
}
}  // namespace

std::string system_gpu_json() {
    static std::mutex                      mutex;
    static Nvidia                          nvidia;
    static std::deque<std::vector<Sample>> history;
    static std::vector<Sample>             current;
    static Clock::time_point               last_sample{};
    std::lock_guard<std::mutex>            lock(mutex);
    const auto                             now = Clock::now();
    const double                           timestamp =
        std::chrono::duration<double, std::milli>(std::chrono::system_clock::now().time_since_epoch()).count();
    if (last_sample == Clock::time_point{} || now - last_sample >= std::chrono::seconds(1)) {
        current     = nvidia.sample(timestamp);
        last_sample = now;
        if (!current.empty()) {
            history.push_back(current);
        }
    }
    while (!history.empty() &&
           (history.size() > MAX_SAMPLES || timestamp - history.front().front().timestamp > RETENTION_MS)) {
        history.pop_front();
    }

    auto * doc  = yyjson_mut_doc_new(nullptr);
    auto * root = yyjson_mut_obj(doc);
    yyjson_mut_doc_set_root(doc, root);
    yyjson_mut_obj_add_int(doc, root, "sample_interval_seconds", 1);
    yyjson_mut_obj_add_int(doc, root, "history_seconds", 600);
    yyjson_mut_obj_add_str(doc, root, "sampling", "on_request");
    yyjson_mut_obj_add_str(
        doc, root, "message",
        current.empty() ? "NVIDIA GPU telemetry is unavailable. The driver must expose NVML to the container." : "");
    auto * gpus = yyjson_mut_arr(doc);
    for (const auto & s : current) {
        yyjson_mut_arr_append(gpus, sample_json(doc, s));
    }
    yyjson_mut_obj_add_val(doc, root, "gpus", gpus);
    auto * samples = yyjson_mut_arr(doc);
    for (const auto & batch : history) {
        for (const auto & s : batch) {
            yyjson_mut_arr_append(samples, sample_json(doc, s));
        }
    }
    yyjson_mut_obj_add_val(doc, root, "history", samples);
    char *      json   = yyjson_mut_write(doc, 0, nullptr);
    std::string result = json ? json : "{}";
    free(json);
    yyjson_mut_doc_free(doc);
    return result;
}
