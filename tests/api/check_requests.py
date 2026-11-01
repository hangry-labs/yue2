"""Model-free native request translation contracts for both audio routes."""
import json
import subprocess
import sys


def main():
    binary = sys.argv[1]
    def translate(body, error=None):
        text = body if isinstance(body, str) else json.dumps(body)
        run = subprocess.run([binary], input=text, text=True, capture_output=True)
        value = json.loads(run.stdout)
        if error:
            assert run.returncode == 1 and value['error']['param'] == (error[0] or None), (body, value)
            assert value['error']['code'] == error[1], (body, value)
        else:
            assert run.returncode == 0, (body, value)
        return value
    original = '[Verse]\nWords, punctuation… and blank lines!\n\nOne more line.'
    mapped = translate({'model': 'tts-1', 'input': original, 'instructions': 'country, acoustic guitar',
                        'voice': 'alloy', 'response_format': 'wav', 'seed': 9007199254740999, 'user': 'harmless'})
    assert mapped['native']['lyrics'] == original and mapped['native']['output_format'] == 'wav16'
    assert mapped['native']['style'] == 'country, acoustic guitar, warm clear lead vocals'
    assert mapped['native']['seed'] == 9007199254740999 and mapped['native']['lm_seed'] == -1
    assert mapped['native']['steps'] == 8
    pcm = translate({'lyrics': original, 'style': 'piano', 'response_format': 'pcm', 'speed': .25})
    assert pcm['pcm'] and pcm['speed'] == .25 and pcm['native']['output_format'] == 'wav16'
    direct = translate({'lyrics': original, 'input': original, 'style': 'pop', 'instructions': 'gentle',
                        'abc': 'X:1\nK:C\nC D E F|', 'model': None, 'voice': None})
    assert direct['native']['abc'] == 'X:1\nK:C\nC D E F|' and direct['native']['style'] == 'pop, gentle'
    instrumental = translate({'style': 'instrumental techno', 'input': '', 'speed': 4})
    assert instrumental['native']['lyrics'] == '' and instrumental['native']['style'] == 'instrumental techno'
    invalid = [
        ('[]', ('', 'invalid_json')), ('{', ('', 'invalid_json')),
        ({}, ('input', 'missing_required_parameter')),
        ({'input': 'words', 'lyrics': 'different'}, ('input', 'invalid_value')),
        ({'input': 'words', 'model': 'unknown'}, ('model', 'model_not_found')),
        ({'input': 'words', 'voice': {'id': 'unknown'}}, ('voice', 'invalid_value')),
        ({'input': 'words', 'voice': 'unknown'}, ('voice', 'unsupported_value')),
        ({'input': 'words', 'stream_format': 'sse'}, ('stream_format', 'unsupported_value')),
        ({'input': 'words', 'stream': True}, ('stream', 'unsupported_value')),
        ({'input': 'words', 'speed': .1}, ('speed', 'invalid_value')),
        ({'input': 'words', 'speed': '2'}, ('speed', 'invalid_value')),
        ({'input': 'words', 'n': 2}, ('n', 'unsupported_value')),
        ({'input': 'words', 'synth_batch_size': 2}, ('n', 'unsupported_value')),
        ({'input': 'words', 'response_format': 'opus', 'output_format': 'mp3'}, ('response_format', 'invalid_value')),
        ({'input': 'words', 'steps': 2147483648}, ('steps', 'invalid_value')),
        ({'input': 'words', 'seed': 9223372036854775808}, ('seed', 'invalid_value')),
        ({'input': 'words', 'adapters': [123]}, ('adapters', 'invalid_value')),
        ({'input': 'words', 'abc_sampling': {'max_tokens': 1.5}}, ('abc_sampling.max_tokens', 'invalid_value')),
        ({'input': 'embedded\0null'}, ('input', 'invalid_value'))
    ]
    for body, error in invalid:
        translate(body, error)
    print(f'PASS: request aliases, exact lyrics/int64 seeds, explicit conditioning, PCM/speed and {len(invalid)} errors.')


if __name__ == '__main__':
    main()
