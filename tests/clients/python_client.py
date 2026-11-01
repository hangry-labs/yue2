"""Explicit live SDK check. Requires openai; accepts a native request JSON fixture."""
import argparse
import hashlib
import json
import os
import wave
from pathlib import Path
from urllib.request import Request, urlopen
import openai
from openai import OpenAI


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, help='Local service root, without /v1')
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    original = json.loads(args.request.read_text(encoding='utf-8'))
    extra = {key: value for key, value in original.items() if key not in ('style', 'lyrics', 'output_format')}
    client = OpenAI(base_url=args.url.rstrip('/') + '/v1', api_key=os.environ.get('YUE2_API_KEY') or 'local',
                    timeout=180, max_retries=0)
    assert client.models.list().data[0].id == 'yue2'
    assert client.models.retrieve('tts-1').id == 'yue2'
    with client.audio.speech.with_streaming_response.create(
        model='yue2', input=original['lyrics'], instructions=original['style'], voice='auto',
        response_format='wav', extra_body=extra,
    ) as response:
        response.stream_to_file(args.output / 'python.wav')
        assert response.headers['x-audio-sample-rate'] == '48000'
        assert response.headers['x-audio-channels'] == '2'
    with wave.open(str(args.output / 'python.wav'), 'rb') as audio:
        expected_seconds = audio.getnframes() / audio.getframerate()
    try:
        client.audio.speech.create(model='yue2', input='words', voice='auto', stream_format='sse')
    except openai.BadRequestError as error:
        assert error.status_code == 400
    else:
        raise AssertionError('SDK did not receive a structured BadRequestError')
    # The music extension returns binary audio using the same request controls.
    body = dict(original, response_format='pcm', speed=2)
    body.pop('output_format', None)
    headers = {'Content-Type': 'application/json'}
    if os.environ.get('YUE2_API_KEY'): headers['Authorization'] = 'Bearer ' + os.environ['YUE2_API_KEY']
    with urlopen(Request(args.url.rstrip('/') + '/v1/audio/music', data=json.dumps(body).encode(), headers=headers), timeout=180) as response:
        pcm = response.read()
        assert response.headers['Content-Type'].startswith('audio/pcm')
        assert response.headers['X-Audio-Sample-Rate'] == '24000'
        assert response.headers['X-Audio-Channels'] == '1'
        assert not pcm.startswith(b'RIFF') and abs(len(pcm) / 48000 - expected_seconds / 2) < .3
        (args.output / 'python.pcm').write_bytes(pcm)
    print(json.dumps({'sdk': 'python', 'version': openai.__version__, 'wav_sha256': hashlib.sha256((args.output / 'python.wav').read_bytes()).hexdigest(),
                      'pcm_seconds': len(pcm) / 48000}), flush=True)


if __name__ == '__main__':
    main()
