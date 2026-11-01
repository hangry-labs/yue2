// Codec integration probe: synthetic stereo, no models or GPU required.
#include "audio-formats.h"
#include <cmath>

int main(int argc, char ** argv) {
    if (argc < 2) return 2;
    std::string mode = argv[1];
    if (mode == "render" && argc == 3) {
        constexpr int frames = 96000;
        std::vector<float> original(frames * 2);
        for (int i = 0; i < frames; ++i) {
            original[(size_t) i] = 0.5f * (float) sin(2 * 3.141592653589793 * 440 * i / 48000);
            original[(size_t) frames + i] = 0.25f * (float) sin(2 * 3.141592653589793 * 880 * i / 48000);
        }
        for (const auto & format : AUDIO_OUTPUT_FORMATS) {
            auto audio = original;
            auto encoded = audio_render(format, audio, frames, 48000, 128, 10);
            auto path = (std::filesystem::path(argv[2]) / (std::string(format.name) + "." + format.extension)).string();
            if (encoded.empty() || !yue_ffmpeg::write(path, encoded.data(), encoded.size())) return 1;
            if (!format.codec) {
                auto expected = original;
                WavFormat wav = std::string(format.name) == "wav24" ? WAV_S24 :
                                std::string(format.name) == "wav32" ? WAV_F32 : WAV_S16;
                if (wav != WAV_F32) audio_normalize(expected.data(), frames * 2, 10);
                if (encoded != audio_encode_wav(expected.data(), frames, 48000, wav)) return 1;
            }
        }
        for (double speed : {.25, 4.0}) {
            auto audio = original;
            auto encoded = audio_render(*audio_output_format("opus"), audio, frames, 48000, 128, 10,
                                        nullptr, nullptr, speed);
            auto path = (std::filesystem::path(argv[2]) / (speed < 1 ? "slow.opus" : "fast.opus")).string();
            if (encoded.empty() || !yue_ffmpeg::write(path, encoded.data(), encoded.size())) return 1;
        }
        auto audio = original;
        auto pcm = audio_render(*audio_output_format("wav16"), audio, frames, 48000, 128, 10, nullptr, nullptr, 1, true);
        if (pcm.size() != 24000 * 2 * 2 || !yue_ffmpeg::write((std::filesystem::path(argv[2]) / "compat.pcm").string(), pcm.data(), pcm.size())) return 1;
        return 0;
    }
    if (mode == "decode" && argc == 4) {
        int frames = 0, rate = 0;
        float * audio = audio_read(argv[2], &frames, &rate);
        if (!audio) return 1;
        auto encoded = audio_encode_wav_f32(audio, frames, rate);
        free(audio);
        return yue_ffmpeg::write(argv[3], encoded.data(), encoded.size()) ? 0 : 1;
    }
    if (mode == "cancel" || mode == "timeout") {
        yue_ffmpeg::Files files;
        if (files.directory.empty()) return 1;
        auto start = std::chrono::steady_clock::now();
        auto cancelled = [](void * data) {
            return std::chrono::steady_clock::now() - *static_cast<decltype(start) *>(data) > std::chrono::milliseconds(150);
        };
        bool ok = yue_ffmpeg::run({"-v", "error", "-nostdin", "-re", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                                   "-t", "30", "-f", "null", "-"}, files.path("stderr"),
                                  mode == "cancel" ? +cancelled : nullptr, &start, mode == "timeout" ? 1 : 30);
        return !ok && std::chrono::steady_clock::now() - start < std::chrono::seconds(3) ? 0 : 1;
    }
    return 2;
}
