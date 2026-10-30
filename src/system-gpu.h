#pragma once
#include <string>

// Cached, read-only telemetry. Sampling happens only on demand, at most once
// per second; no background thread or subprocess is started.
std::string system_gpu_json();
