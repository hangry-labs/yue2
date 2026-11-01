import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'agents/songwriting.py'
spec = importlib.util.spec_from_file_location('songwriting_agent', path)
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class SongwritingAssessmentTests(unittest.TestCase):
    def fixture(self):
        case = {'kind': 'supplied', 'duration_seconds': 30, 'supplied_lyrics': 'One small light\nThrough the night\nWe will stay\nFind our way'}
        lyrics = '[Verse]\nOne small light\nThrough the night\n[Chorus]\nWe will stay\nFind our way'
        trace = {'events': [
            {'type': 'tool', 'sequence': 1, 'name': 'skill', 'arguments': {}, 'error': False},
            {'type': 'tool', 'sequence': 2, 'name': 'generate_song',
             'arguments': {'guide_token': 'token', 'lyrics': lyrics, 'direction': 'piano', 'duration_seconds': 30}, 'error': False}],
            'completed': [{'url': 'http://localhost/audio'}], 'final': 'Download: http://localhost/audio'}
        return case, trace

    def test_labels_can_enrich_supplied_lyrics_without_changing_words(self):
        case, trace = self.fixture()
        self.assertTrue(agent.assess(case, trace)['technical_pass'])
        trace['events'][1]['arguments']['lyrics'] += '\nAn extra line'
        self.assertFalse(agent.assess(case, trace)['checks']['supplied_words_preserved'])

    def test_invented_link_does_not_pass_completed_workflow(self):
        case, trace = self.fixture()
        trace['final'] = 'Here is http://localhost/invented'
        self.assertFalse(agent.assess(case, trace)['checks']['real_link_in_final'])
        trace['completed'] = []
        self.assertFalse(agent.assess(case, trace)['checks']['no_early_finish'])

    def test_generation_before_reading_and_advanced_args_are_failures(self):
        case, trace = self.fixture()
        trace['events'][0]['sequence'] = 3
        trace['events'][1]['arguments']['steps'] = 32
        result = agent.assess(case, trace)['checks']
        self.assertFalse(result['read_guide_first'])
        self.assertFalse(result['allowed_arguments_only'])

    def test_call_inspection_requires_no_job_or_download(self):
        case, trace = self.fixture()
        trace['inspection_only'] = True
        trace['events'][1]['inspection_only'] = True
        trace['completed'] = []
        trace['final'] = ''
        result = agent.assess(case, trace)
        self.assertTrue(result['technical_pass'])
        self.assertTrue(result['checks']['call_validated_without_generation'])
        self.assertNotIn('completion_observed', result['checks'])

    def test_no_vocals_is_a_valid_instrumental_style_description(self):
        case, trace = self.fixture()
        case['kind'] = 'instrumental'
        case['required_style_terms'] = ['techno']
        trace['events'][1]['arguments'].update(lyrics='', direction='Dark techno, no vocals')
        self.assertTrue(agent.assess(case, trace)['technical_pass'])

    def test_style_and_full_song_structure_are_checked_when_requested(self):
        case, trace = self.fixture()
        case['exact_style'] = 'cinematic folk, flute, bowed strings'
        case['required_sections'] = ['Verse 1', 'Chorus', 'Bridge']
        result = agent.assess(case, trace)['checks']
        self.assertFalse(result['supplied_style_preserved'])
        self.assertFalse(result['requested_song_structure'])

    def test_lyrics_only_request_does_not_require_audio(self):
        case, trace = self.fixture()
        case['kind'] = 'lyrics_only'
        case.pop('duration_seconds')
        trace['final'] = trace['events'][1]['arguments']['lyrics']
        trace['events'] = trace['events'][:1]
        trace['completed'] = []
        self.assertTrue(agent.assess(case, trace)['technical_pass'])

    def test_human_markdown_headings_count_but_missing_guide_is_visible(self):
        case = {'kind': 'lyrics_only'}
        trace = {'events': [], 'completed': [], 'final': '**Verse**\nOne small light\nThrough the night\n**Chorus**\nWe will stay\nFind our way'}
        checks = agent.assess(case, trace)['checks']
        self.assertTrue(checks['has_section_labels'])
        self.assertTrue(checks['no_generation_requested'])
        self.assertFalse(checks['read_guide'])
