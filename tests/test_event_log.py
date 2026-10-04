import tempfile
import unittest
from pathlib import Path
from event_log import EventLog

class LogTests(unittest.TestCase):
    def test_retention_and_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            now=[1000000.0]
            log=EventLog(Path(tmp),clock=lambda:now[0],max_bytes=400,backups=2)
            for i in range(40):log.write('event',count=i)
            self.assertLessEqual(len(list(Path(tmp).glob('*.jsonl'))),3)
            self.assertTrue(all(p.stat().st_size<=400 for p in Path(tmp).glob('*.jsonl')))
            now[0]+=3*86400+1
            log.write('new')
            content=''.join(p.read_text() for p in Path(tmp).glob('*.jsonl'))
            self.assertNotIn('"event": "event"',content)
            self.assertIn('"event": "new"',content)

    def test_only_diagnostic_fields_are_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            log=EventLog(Path(tmp))
            log.write('error',api_key='secret',text='child transcript',error_type='TimeoutError')
            content=''.join(p.read_text() for p in Path(tmp).glob('*.jsonl'))
            self.assertNotIn('secret',content)
            self.assertNotIn('child transcript',content)
            self.assertIn('TimeoutError',content)

    def test_total_limit_across_hours(self):
        with tempfile.TemporaryDirectory() as tmp:
            now=[1000000.0]
            log=EventLog(Path(tmp),clock=lambda:now[0],total_bytes=500)
            for i in range(20):
                now[0]+=3600
                log.write('event',count=i)
            self.assertLessEqual(sum(p.stat().st_size for p in Path(tmp).glob('*.jsonl')),500)
