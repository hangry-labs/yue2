#include "music-api.h"
#include <iostream>
#include <iterator>

int main() {
    std::string body((std::istreambuf_iterator<char>(std::cin)), std::istreambuf_iterator<char>());
    MusicApiRequest request;
    MusicApiError error;
    if (!music_api_parse(body, request, error)) {
        std::cout << music_api_error(error) << '\n';
        return 1;
    }
    std::cout << "{\"native\":" << request_to_json(&request.native, false)
              << ",\"pcm\":" << (request.pcm ? "true" : "false") << ",\"speed\":" << request.speed << "}\n";
    return 0;
}
