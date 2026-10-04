"""Bounded diagnostics without transcripts, credentials or remote error bodies."""
import json
from pathlib import Path
import sys
import time

FIELDS = {'service', 'duration_ms', 'error_type', 'cause_type', 'status', 'errno',
          'action', 'reason', 'characters', 'count', 'mode',
          'frames', 'above_threshold_frames', 'threshold', 'triggers', 'accepted',
          'rejected', 'rms_peak', 'rms_mean', 'rms_p50_bucket', 'rms_p95_bucket',
          'silence_ms', 'min_speech_ms'}


class EventLog:
    def __init__(self, directory, clock=time.time, max_bytes=2*1024*1024, backups=2,
                 total_bytes=20*1024*1024):
        self.directory = directory
        self.clock = clock
        self.max_bytes = max_bytes
        self.backups = backups
        self.total_bytes = total_bytes
        self.warned = False

    def write(self, event, **fields):
        try:
            now = self.clock()
            self.directory.mkdir(parents=True, exist_ok=True)
            files = list(self.directory.glob('events-*.jsonl'))
            for path in files:
                try:
                    bucket = int(path.name.split('-')[1].split('.')[0])
                except ValueError:
                    continue
                if bucket < now - 72*3600:
                    path.unlink(missing_ok=True)
            bucket = int(now // 3600) * 3600
            path = self.directory / f'events-{bucket:010d}.jsonl'
            record = {'time': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now)),
                      'event': str(event)[:64]}
            record.update({k: (v if isinstance(v, (int, float, bool)) else str(v)[:100])
                           for k, v in fields.items() if k in FIELDS})
            line = (json.dumps(record, ensure_ascii=False)+'\n').encode()
            if len(line) > self.max_bytes:
                return
            if path.exists() and path.stat().st_size + len(line) > self.max_bytes:
                for i in range(self.backups, 0, -1):
                    old = path if i == 1 else path.with_suffix(f'.{i-1}.jsonl')
                    new = path.with_suffix(f'.{i}.jsonl')
                    if old.exists():
                        old.replace(new)
            with path.open('ab') as out:
                out.write(line)
            files = sorted(self.directory.glob('events-*.jsonl'), key=lambda p: p.stat().st_mtime)
            size = sum(p.stat().st_size for p in files)
            for old in files:
                if size <= self.total_bytes:
                    break
                size -= old.stat().st_size
                old.unlink()
        except OSError:
            if not self.warned:
                print('日志写入失败；请检查磁盘空间和目录权限。', file=sys.stderr)
                self.warned = True


_logger = None


def configure(directory):
    global _logger
    _logger = EventLog(Path(directory))
    emit('startup')


def emit(event, **fields):
    if _logger is not None:
        _logger.write(event, **fields)
