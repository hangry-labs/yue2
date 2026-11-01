#pragma once
#include "audio-io.h"

struct AudioOutputFormat {
    const char * name;
    const char * extension;
    const char * mime;
    const char * muxer;
    const char * codec;
};

inline constexpr AudioOutputFormat AUDIO_OUTPUT_FORMATS[] = {
    {"mp3", "mp3", "audio/mpeg", "mp3", "libmp3lame"},
    {"opus", "opus", "audio/ogg; codecs=opus", "ogg", "libopus"},
    {"ogg", "ogg", "audio/ogg; codecs=vorbis", "ogg", "libvorbis"},
    {"flac", "flac", "audio/flac", "flac", "flac"},
    {"aac", "aac", "audio/aac", "adts", "aac"},
    {"m4a", "m4a", "audio/mp4", "ipod", "aac"},
    {"wav16", "wav", "audio/wav", nullptr, nullptr},
    {"wav24", "wav", "audio/wav", nullptr, nullptr},
    {"wav32", "wav", "audio/wav", nullptr, nullptr},
};

static const AudioOutputFormat * audio_output_format(const std::string & name) {
    for (const auto & format : AUDIO_OUTPUT_FORMATS) if (name == format.name) return &format;
    return nullptr;
}

// The WAV path is unchanged, including its exact PCM quantization and headers.
// Compressed output is encoded once from normalized float PCM, never from MP3.
static std::string audio_render(const AudioOutputFormat & format, std::vector<float> & audio,
                                int frames, int rate, int mp3_bitrate, int peak_clip,
                                yue_ffmpeg::Cancel cancel = nullptr, void * opaque = nullptr) {
    if (frames <= 0 || rate <= 0 || audio.size() != (size_t) frames * 2) return {};
    if (cancel && cancel(opaque)) return {};
    if (std::string(format.name) != "wav32") audio_normalize(audio.data(), frames * 2, peak_clip);
    if (!format.codec) {
        WavFormat wav = std::string(format.name) == "wav24" ? WAV_S24 :
                        std::string(format.name) == "wav32" ? WAV_F32 : WAV_S16;
        return audio_encode_wav(audio.data(), frames, rate, wav);
    }
    yue_ffmpeg::Files files;
    if (files.directory.empty()) return {};
    // Use the native float WAV writer: little-endian, stereo, no precision loss.
    auto pcm = audio_encode_wav_f32(audio.data(), frames, rate);
    if (!yue_ffmpeg::write(files.path("input.wav"), pcm.data(), pcm.size())) return {};
    pcm.clear();
    std::vector<std::string> args{"-hide_banner", "-v", "error", "-nostdin", "-y", "-threads", "2",
        "-protocol_whitelist", "file,pipe", "-i", files.path("input.wav"), "-map", "0:a:0", "-vn", "-sn", "-dn",
        "-map_metadata", "-1", "-ar", std::to_string(rate), "-ac", "2", "-c:a", format.codec};
    std::string name = format.name;
    if (name == "opus") args.insert(args.end(), {"-b:a", "96000", "-vbr", "on", "-application", "audio", "-compression_level", "10"});
    else if (name == "mp3") args.insert(args.end(), {"-b:a", std::to_string(mp3_bitrate) + "k"});
    else if (name == "ogg") args.insert(args.end(), {"-q:a", "5"});
    else if (name == "flac") args.insert(args.end(), {"-sample_fmt", "s32", "-bits_per_raw_sample", "24"});
    else args.insert(args.end(), {"-b:a", "192k"});
    if (name == "m4a") args.insert(args.end(), {"-movflags", "+faststart"});
    args.insert(args.end(), {"-threads", "2", "-f", format.muxer, files.path("output")});
    if (!yue_ffmpeg::run(args, files.path("stderr"), cancel, opaque)) return {};
    return yue_ffmpeg::read(files.path("output"));
}
