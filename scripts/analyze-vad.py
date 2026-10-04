#!/usr/bin/env python3
"""Aggregate bounded VAD metadata, never transcripts or recordings."""
import argparse
import json
from pathlib import Path


def summarize(directory):
    windows = frames = above = triggers = accepted = rejected = 0
    means = []
    thresholds = set()
    for path in sorted(directory.glob('events-*.jsonl')):
        with path.open(encoding='utf-8') as source:
            for line in source:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get('event') != 'vad_summary':
                    continue
                windows += 1
                frames += row['frames']
                above += row['above_threshold_frames']
                triggers += row['triggers']
                accepted += row['accepted']
                rejected += row['rejected']
                thresholds.add(row['threshold'])
                means.append(row['rms_mean'])
    print(json.dumps(dict(windows=windows, sampled_seconds=frames/50,
        thresholds=sorted(thresholds), above_threshold_percent=round(100*above/max(1,frames),2),
        triggers=triggers, accepted=accepted, rejected=rejected,
        window_mean_rms_min=min(means,default=0), window_mean_rms_max=max(means,default=0)),
        ensure_ascii=False, indent=2))
    print('先分别采集无人说话与正常说话的样本。音量统计不能判断声音是否为人声，不能据此自动给出最优阈值。')


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('directory',type=Path,nargs='?',default=Path(__file__).resolve().parent.parent/'logs')
    summarize(parser.parse_args().directory)
