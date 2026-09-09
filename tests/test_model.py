import copy
import unittest

from trading_bot.model import ModelError, validate_agent_output
from trading_bot.model.nvidia import NvidiaKimiClient

GOOD = {
    'market_regime': 'neutral',
    'portfolio_view': 'neutral',
    'candidates': [{
        'symbol': 'ETH-USDT', 'action': 'BUY', 'confidence': 0.7, 'target_allocation': 0.12,
        'thesis': 'trend up', 'invalidation': 'loses 20d sma', 'risk_notes': ['macro']
    }],
}


class ValidateTests(unittest.TestCase):
    def test_good_returns_obj(self):
        obj = copy.deepcopy(GOOD)
        self.assertIs(validate_agent_output(obj), obj)

    def test_empty_candidates_ok(self):
        validate_agent_output({'market_regime': 'unclear', 'portfolio_view': 'neutral', 'candidates': []})

    def test_bad_regime(self):
        o = copy.deepcopy(GOOD); o['market_regime'] = 'moon'
        self.assertRaises(ValueError, validate_agent_output, o)

    def test_bad_symbol(self):
        o = copy.deepcopy(GOOD); o['candidates'][0]['symbol'] = 'DOGE-USDT'
        self.assertRaises(ValueError, validate_agent_output, o)

    def test_confidence_out_of_range(self):
        o = copy.deepcopy(GOOD); o['candidates'][0]['confidence'] = 1.4
        self.assertRaises(ValueError, validate_agent_output, o)

    def test_extra_field_rejected(self):
        o = copy.deepcopy(GOOD); o['candidates'][0]['size_usdt'] = 500
        self.assertRaises(ValueError, validate_agent_output, o)

    def test_duplicate_symbol(self):
        o = copy.deepcopy(GOOD); o['candidates'].append(copy.deepcopy(GOOD['candidates'][0]))
        self.assertRaises(ValueError, validate_agent_output, o)


class NvidiaClientTests(unittest.TestCase):
    def test_no_key_fails_clearly(self):
        c = NvidiaKimiClient(api_key='')
        self.assertFalse(c.available)
        with self.assertRaises(ModelError):
            c.evaluate({'request_id': 'r', 'snapshot_hash': 'h', 'system_prompt': 's', 'context': {}})

    def test_parses_and_validates_content(self):
        c = NvidiaKimiClient(api_key='test-key')
        c._post = lambda payload, timeout: {
            'id': 'chatcmpl-x', 'model': 'moonshotai/kimi-k3',
            'usage': {'total_tokens': 10},
            'choices': [{'message': {'content': __import__('json').dumps(GOOD)}}],
        }
        r = c.evaluate({'request_id': 'r', 'snapshot_hash': 'h', 'system_prompt': 's', 'context': {}})
        self.assertEqual(r['provider'], 'nvidia_nim')
        self.assertEqual(r['request_id'], 'chatcmpl-x')
        self.assertEqual(r['output']['candidates'][0]['symbol'], 'ETH-USDT')

    def test_malformed_content_raises_modelerror(self):
        c = NvidiaKimiClient(api_key='test-key')
        c._post = lambda payload, timeout: {'choices': [{'message': {'content': 'not json'}}]}
        with self.assertRaises(ModelError):
            c.evaluate({'request_id': 'r', 'snapshot_hash': 'h', 'system_prompt': 's', 'context': {}})

    def test_schema_invalid_content_raises_modelerror(self):
        bad = copy.deepcopy(GOOD); bad['candidates'][0]['symbol'] = 'DOGE-USDT'
        c = NvidiaKimiClient(api_key='test-key')
        c._post = lambda payload, timeout: {'choices': [{'message': {'content': __import__('json').dumps(bad)}}]}
        with self.assertRaises(ModelError):
            c.evaluate({'request_id': 'r', 'snapshot_hash': 'h', 'system_prompt': 's', 'context': {}})


if __name__ == '__main__':
    unittest.main()
