#!/usr/bin/env python3
"""Manual agent evaluation: an OpenAI-compatible model drives the real MCP tools.

Test-only dependency: pip install 'mcp>=2,<3'. No model URL is assumed.
Default: inspect proposed calls without submitting generation. --generate-audio
explicitly enables real generation. Traces go into ignored data/results/.
The host forwards tool descriptions/results without rewriting model arguments.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
SECTION = re.compile(r'^\[(?:verse(?:\s+\d+)?|chorus|final\s+chorus|pre[- ]?chorus|bridge|intro|outro|interlude|instrumental(?:\s+(?:bridge|break))?)\]$', re.I)


def json_http(url, body=None, headers=None, timeout=300):
    values = {'Content-Type': 'application/json', **(headers or {})}
    request = urllib.request.Request(url, data=None if body is None else json.dumps(body, ensure_ascii=False).encode(), headers=values)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def sung_lines(lyrics):
    return [line.strip() for line in lyrics.splitlines() if line.strip() and not SECTION.fullmatch(line.strip())]


def assess(case, trace):
    calls = [event for event in trace['events'] if event['type'] == 'tool']
    generations = [event for event in calls if event['name'] == 'generate_song' and not event.get('error')]
    guides = [event for event in calls if event['name'] == 'skill' and not event.get('error')]
    song = generations[0]['arguments'] if generations else {}
    lyrics = song.get('lyrics', '')
    direction = song.get('direction', '')
    lines = sung_lines(lyrics)
    received = trace.get('completed', [])
    final = trace.get('final', '')
    checks = {
        'read_guide_first': bool(guides and generations and guides[0]['sequence'] < generations[0]['sequence']),
        'one_song_request': len(generations) == 1,
        'no_tool_errors': not any(e.get('error') for e in calls),
        'completion_observed': bool(received),
        'real_link_in_final': bool(received) and any(s['url'] in final for s in received),
        'no_early_finish': bool(received) or not generations,
        'requested_duration': song.get('duration_seconds', 300) == case.get('duration_seconds', 300),
        'allowed_arguments_only': all(set(e['arguments']) <= {'guide_token', 'lyrics', 'direction', 'duration_seconds', 'tempo_bpm', 'format'} for e in generations),
    }
    if trace.get('inspection_only') and case['kind'] != 'lyrics_only':
        for key in ('completion_observed', 'real_link_in_final', 'no_early_finish'):
            checks.pop(key)
        checks['call_validated_without_generation'] = bool(generations) and all(e.get('inspection_only') for e in generations)
    if case['kind'] == 'lyrics_only':
        lyrics = final
        lines = sung_lines(lyrics)
        # Human-facing drafts may use Markdown headings. This relaxation is
        # assessment only; no submitted MCP lyrics or tool arguments are edited.
        section_headings = [line.strip().strip('#* _') for line in lyrics.splitlines()]
        checks = {'read_guide': bool(guides), 'no_generation_requested': not generations,
                  'no_tool_errors': not any(e.get('error') for e in calls),
                  'has_lyrics': len(lines) >= 4,
                  'has_section_labels': any(SECTION.fullmatch(line) or SECTION.fullmatch('[' + line + ']') for line in section_headings),
                  'no_fabricated_download': not re.search(r'https?://', final)}
        if case.get('required_sections'):
            headings = {label.strip('[]').casefold().replace('-', ' ') for label in section_headings}
            checks['requested_song_structure'] = all(s.casefold().replace('-', ' ') in headings for s in case['required_sections'])
    if case['kind'] == 'instrumental':
        checks['instrumental_lyrics_empty'] = lyrics == '' and bool(generations)
        checks['instrumental_direction_present'] = any(term in direction.casefold()
            for term in ('instrumental', 'no vocals', 'without vocals', 'no singing', 'without singing'))
    elif case['kind'] != 'lyrics_only':
        checks['has_section_labels'] = any(SECTION.fullmatch(line.strip()) for line in lyrics.splitlines())
        checks['has_sung_words'] = len(lines) >= 4
    if case['kind'] == 'supplied':
        checks['supplied_words_preserved'] = ' '.join(' '.join(lines).split()) == ' '.join(case['supplied_lyrics'].split())
    if case.get('required_sections') and generations:
        headings = {label.casefold().replace('-', ' ') for label in re.findall(r'^\[([^\]]+)\]\s*$', lyrics, re.M)}
        checks['requested_song_structure'] = all(section.casefold().replace('-', ' ') in headings for section in case['required_sections'])
    if case.get('exact_style') and generations:
        checks['supplied_style_preserved'] = direction == case['exact_style']
    direction_hits = [word for word in case.get('direction_keywords', []) if word.casefold() in direction.casefold()]
    theme_hits = [word for word in case.get('theme_keywords', []) if re.search(r'\b' + re.escape(word) + r'\b', lyrics, re.I)]
    if case.get('required_style_terms') and generations:
        checks['requested_style_details'] = all(term.casefold() in direction.casefold() for term in case['required_style_terms'])
    if case.get('tempo_bpm') and generations:
        checks['requested_tempo_hint'] = song.get('tempo_bpm') == case['tempo_bpm'] or bool(re.search(
            rf"\b{case['tempo_bpm']}\s*bpm\b", direction, re.I))
    return {'checks': checks, 'technical_pass': all(checks.values()),
            'skill_version': guides[0].get('result', {}).get('skill_version') if guides and isinstance(guides[0].get('result'), dict) else None,
            'sung_line_count': len(lines),
            'direction_keyword_hits': direction_hits, 'theme_keyword_hits': theme_hits,
            'lyrics': lyrics, 'direction': direction,
            'note': 'Call and input inspection only; this does not assess generated audio, genre fidelity or ASR.'}


async def run_case(client, tools, instructions, case, args, output):
    trace = {'case': case['id'], 'prompt': case['prompt'], 'events': [], 'completed': [], 'final': '',
             'inspection_only': args.inspect_calls}
    path = output / (case['id'] + '.trace.json')
    messages = [{'role': 'system', 'content': 'You are a music assistant. Fulfil the user request using the available tools.\n\n' + instructions},
                {'role': 'user', 'content': case['prompt']}]
    jobs = set()
    terminal = set()
    last_poll = {}
    started = time.monotonic()
    headers = {}
    if os.environ.get('YUE2_AGENT_MODEL_KEY'):
        headers['Authorization'] = 'Bearer ' + os.environ['YUE2_AGENT_MODEL_KEY']
    def save():
        trace['elapsed_seconds'] = time.monotonic() - started
        path.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    try:
        for turn in range(args.max_turns):
            print(f'{case["id"]}: model turn {turn + 1}', flush=True)
            response = await asyncio.to_thread(json_http, args.model_url.rstrip('/') + '/v1/chat/completions',
                {'model': args.model, 'messages': messages, 'tools': tools, 'tool_choice': 'auto',
                 'stream': False, 'max_tokens': args.max_tokens,
                 'chat_template_kwargs': {'enable_thinking': True}}, headers, args.model_timeout)
            choice = response['choices'][0]
            message = choice['message']
            trace['events'].append({'type': 'assistant', 'turn': turn + 1, 'message': message,
                                    'finish_reason': choice.get('finish_reason'), 'usage': response.get('usage')})
            messages.append(message)
            save()
            calls = message.get('tool_calls') or []
            if not calls:
                trace['final'] = message.get('content') or ''
                trace['finish_reason'] = choice.get('finish_reason')
                if choice.get('finish_reason') == 'length':
                    trace['evaluation_limit'] = 'Model response reached the configured token cap; this is not an MCP failure.'
                break
            for call in calls:
                name = call.get('function', {}).get('name', '')
                event = {'type': 'tool', 'sequence': len(trace['events']), 'name': name,
                         'arguments': {}, 'requested_after_seconds': time.monotonic() - started}
                try:
                    arguments = json.loads(call['function']['arguments'])
                    event['arguments'] = arguments
                    if name not in {t['function']['name'] for t in tools}:
                        raise ValueError('Unknown tool name')
                    if args.inspect_calls and name != 'skill':
                        from jsonschema import Draft202012Validator
                        schema = next(t['function']['parameters'] for t in tools if t['function']['name'] == name)
                        Draft202012Validator(schema).validate(arguments)
                        if name != 'generate_song':
                            raise ValueError('This case has no existing job to inspect or cancel')
                        guides = [e for e in trace['events'] if e['type'] == 'tool' and e['name'] == 'skill' and not e.get('error')]
                        if not guides or arguments.get('guide_token') != guides[-1]['result']['guide_token']:
                            raise ValueError('Retrieve skill first and copy its actual guide_token')
                        expires = datetime.fromisoformat(guides[-1]['result']['expires_at'].replace('Z', '+00:00'))
                        if datetime.now(timezone.utc) >= expires:
                            raise ValueError('The guide token expired during model processing; retrieve skill again')
                        event.update(inspection_only=True, error=False,
                                     result={'status': 'call_validated', 'generation_submitted': False})
                        trace['events'].append(event)
                        trace['finish_reason'] = 'host_stopped_after_call_inspection'
                        trace['assessment'] = assess(case, trace)
                        save()
                        print(f'{case["id"]}: generate_song validated; no generation submitted', flush=True)
                        return trace
                    if name == 'generate_song' and jobs:
                        raise ValueError('This qualification case permits one generated song; do not submit duplicates')
                    if name == 'get_song':
                        job = arguments.get('job_id', '')
                        delay = max(0, 30 - (time.monotonic() - last_poll.get(job, 0)))
                        # Host scheduling only; report it rather than attributing
                        # an actual timed wait to the model.
                        event['host_poll_wait_seconds'] = delay
                        if delay: await asyncio.sleep(delay)
                        last_poll[job] = time.monotonic()
                    result = await client.call_tool(name, arguments)
                    data = result.structured_content
                    text = '\n'.join(item.text for item in result.content if item.type == 'text')
                    event['result'] = data if data is not None else text
                    event['error'] = bool(result.is_error)
                    if not result.is_error and isinstance(data, dict):
                        if name == 'generate_song':
                            jobs.add(data['job_id'])
                            last_poll[data['job_id']] = time.monotonic()
                        if name in ('get_song', 'cancel_song') and data.get('status') in ('complete', 'failed', 'cancelled'):
                            terminal.add(data['job_id'])
                        if name == 'get_song' and data.get('status') == 'complete':
                            if data['job_id'] not in {s['job_id'] for s in trace['completed']}:
                                trace['completed'].append(data)
                                def download():
                                    with urllib.request.urlopen(data['url'], timeout=60) as response:
                                        audio = response.read()
                                    target = output / (case['id'] + '.' + data['format'])
                                    target.write_bytes(audio)
                                    return {'path': target.name, 'size': len(audio), 'sha256': hashlib.sha256(audio).hexdigest()}
                                trace.setdefault('downloads', []).append(await asyncio.to_thread(download))
                    messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': text})
                except Exception as error:
                    event['error'] = True
                    event['result'] = str(error)
                    messages.append({'role': 'tool', 'tool_call_id': call.get('id', ''), 'content': json.dumps({'error': str(error)})})
                trace['events'].append(event)
                print(f'{case["id"]}: {name} -> ' + ('error' if event.get('error') else
                    str(event.get('result', {}).get('status', 'ok')) if isinstance(event.get('result'), dict) else 'text'), flush=True)
                save()
        else:
            trace['finish_reason'] = 'host_turn_limit'
        trace['assessment'] = assess(case, trace)
        return trace
    finally:
        # Cancel only jobs submitted by this evaluation if the model leaves an
        # incomplete workflow. Do not touch unrelated Studio/native work.
        for job in jobs - terminal:
            try:
                result = await client.call_tool('cancel_song', {'job_id': job})
                trace['events'].append({'type': 'host_cleanup', 'job_id': job, 'result': result.structured_content})
            except Exception as error:
                trace['events'].append({'type': 'host_cleanup', 'job_id': job, 'error': str(error)})
        save()


async def main(args):
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
    if not args.inspect_calls:
        # Inference is explicitly opted into; ordinary call inspection has no
        # GPU interaction and never forwards mutation tools to the service.
        sys.path.insert(0, str(ROOT))
        from benchmarks.runtime import container_info, gpu_workers, require_idle_dev
        others = gpu_workers(exclude=(args.container,))
        if others: raise RuntimeError('Other GPU containers are active: ' + ', '.join(others))
        info = container_info(args.container)
        if not info or not info['State']['Running']: raise RuntimeError('Expected local owned container is not running')
        require_idle_dev(info)
    output = args.output or ROOT / 'data/results/mcp-agent' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output.mkdir(parents=True, exist_ok=False)
    case_data = json.loads(args.cases.read_text(encoding='utf-8'))
    if args.case: case_data = [case for case in case_data if case['id'] in args.case]
    if not case_data: raise ValueError('No matching evaluation cases')
    if not args.model:
        listing = await asyncio.to_thread(json_http, args.model_url.rstrip('/') + '/v1/models')
        args.model = listing['data'][0]['id']
    headers = {}
    if os.environ.get('YUE2_API_KEY'): headers['Authorization'] = 'Bearer ' + os.environ['YUE2_API_KEY']
    summary = {'model': args.model, 'max_tokens': args.max_tokens, 'thinking_enabled': True,
               'model_timeout_seconds': args.model_timeout, 'inspection_only': args.inspect_calls,
               'cases': [], 'status': 'running'}
    async with httpx2.AsyncClient(headers=headers) as http:
        async with Client(streamable_http_client(args.mcp_url, http_client=http)) as client:
            instructions = client.instructions or ''
            listing = await client.list_tools()
            tools = [{'type': 'function', 'function': {'name': tool.name, 'description': tool.description,
                                                      'parameters': tool.input_schema}} for tool in listing.tools]
            (output / 'discovery.json').write_text(json.dumps({'instructions': instructions, 'tools': tools}, indent=2), encoding='utf-8')
            for case in case_data:
                try:
                    result = await run_case(client, tools, instructions, case, args, output)
                except Exception as error:
                    summary['status'] = 'host_error'
                    summary['host_error'] = {'case': case['id'], 'message': str(error)}
                    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
                    raise
                summary['cases'].append({'id': case['id'], **result['assessment'], 'elapsed_seconds': result['elapsed_seconds']})
                (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    summary['status'] = 'complete'
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(str(output / 'summary.json'), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-url', default=os.environ.get('YUE2_AGENT_MODEL_URL'))
    parser.add_argument('--model')
    parser.add_argument('--mcp-url', default='http://localhost:8087/mcp')
    parser.add_argument('--container', default='yue2-dev')
    parser.add_argument('--cases', type=Path, default=Path(__file__).with_name('cases.json'))
    parser.add_argument('--case', action='append')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--max-turns', type=int, help='Default: 8 for call inspection, 48 for generation')
    parser.add_argument('--max-tokens', type=int, default=100000)
    parser.add_argument('--model-timeout', type=int, default=7200, help='Per model response timeout in seconds')
    parser.add_argument('--generate-audio', action='store_true', help='Opt into generation; default only inspects proposed calls')
    args = parser.parse_args()
    args.inspect_calls = not args.generate_audio
    if args.max_turns is None: args.max_turns = 8 if args.inspect_calls else 48
    if not args.model_url: parser.error('--model-url or YUE2_AGENT_MODEL_URL is required')
    asyncio.run(main(args))
