from __future__ import annotations

import json
import math
from collections import Counter, OrderedDict, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import torch
from torch.utils.data import Dataset

from .schema import BehaviorEvent
from .synthetic import iter_jsonl


PAD_TOKEN = "[PAD]"
UNK_TOKEN = "[UNK]"
CLS_TOKEN = "[CLS]"


class BehaviorVocabulary:
    def __init__(self, token_to_id: dict[str, int] | None = None):
        self.token_to_id = token_to_id or {PAD_TOKEN: 0, UNK_TOKEN: 1, CLS_TOKEN: 2}
        self.id_to_token = {value: key for key, value in self.token_to_id.items()}

    @property
    def pad_id(self) -> int:
        return self.token_to_id[PAD_TOKEN]

    @property
    def cls_id(self) -> int:
        return self.token_to_id[CLS_TOKEN]

    def __len__(self) -> int:
        return len(self.token_to_id)

    def fit(self, events: Iterable[BehaviorEvent], max_size: int = 2048) -> None:
        counts = Counter(event.token() for event in events)
        self.token_to_id = {PAD_TOKEN: 0, UNK_TOKEN: 1, CLS_TOKEN: 2}
        for token, _ in counts.most_common(max(0, max_size - 3)):
            self.token_to_id[token] = len(self.token_to_id)
        self.id_to_token = {value: key for key, value in self.token_to_id.items()}

    def encode(self, event: BehaviorEvent) -> int:
        return self.token_to_id.get(event.token(), self.token_to_id[UNK_TOKEN])

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.token_to_id, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: str | Path) -> "BehaviorVocabulary":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass(slots=True)
class SequenceRecord:
    entity_id: str
    events: list[BehaviorEvent]
    label: int
    scenario: str


def _make_sequence_record(entity_id: str, events: Sequence[BehaviorEvent]) -> SequenceRecord:
    labels = [event.label for event in events]
    scenarios = [event.scenario for event in events if event.label]
    return SequenceRecord(
        entity_id=entity_id,
        events=list(events),
        label=int(any(labels)),
        scenario=scenarios[0] if scenarios else "normal",
    )


def window_slices(
    length: int,
    window_size: int,
    stride: int,
    min_events: int,
) -> Iterable[tuple[int, int]]:
    """产生完整滑窗，并在需要时补一个末尾对齐窗口。"""

    if window_size <= 0 or stride <= 0 or min_events <= 0:
        raise ValueError("window_size、stride 和 min_events 必须是正整数")
    if min_events > window_size:
        raise ValueError("min_events 不能大于 window_size")
    if length < min_events:
        return
    if length <= window_size:
        yield 0, length
        return
    starts = list(range(0, length - window_size + 1, stride))
    for start in starts:
        yield start, start + window_size
    tail_start = length - window_size
    if tail_start != starts[-1]:
        yield tail_start, length


def iter_sequence_windows(
    events: Iterable[BehaviorEvent],
    window_size: int,
    stride: int,
    min_events: int,
    max_entities: int | None = None,
) -> Iterable[SequenceRecord]:
    """按到达顺序生成窗口；可限制活跃实体数以约束内存。"""

    # 先触发参数校验，即使输入为空也应拒绝无效配置。
    list(window_slices(0, window_size, stride, min_events))
    if max_entities is not None and max_entities < 1:
        raise ValueError("max_entities 必须为正整数或 None")
    buffers: OrderedDict[str, deque[BehaviorEvent]] = OrderedDict()
    counts: dict[str, int] = defaultdict(int)
    last_emitted_end: dict[str, int] = defaultdict(int)
    last_timestamp = {}

    def tail_record(entity_id: str) -> SequenceRecord | None:
        count = counts[entity_id]
        if count < min_events or last_emitted_end[entity_id] == count:
            return None
        return _make_sequence_record(entity_id, list(buffers[entity_id]))

    for event in events:
        entity_id = event.entity_id
        timestamp = event.parsed_time()
        if entity_id in last_timestamp and timestamp < last_timestamp[entity_id]:
            raise ValueError(f"实体 {entity_id} 的事件未按时间排序")
        last_timestamp[entity_id] = timestamp
        if entity_id not in buffers:
            if max_entities is not None and len(buffers) >= max_entities:
                evicted_id = next(iter(buffers))
                tail = tail_record(evicted_id)
                if tail is not None:
                    yield tail
                buffers.pop(evicted_id)
                counts.pop(evicted_id, None)
                last_emitted_end.pop(evicted_id, None)
                last_timestamp.pop(evicted_id, None)
            buffers[entity_id] = deque(maxlen=window_size)
        else:
            buffers.move_to_end(entity_id)
        buffers[entity_id].append(event)
        counts[entity_id] += 1
        count = counts[entity_id]
        if count >= window_size and (count - window_size) % stride == 0:
            yield _make_sequence_record(entity_id, list(buffers[entity_id]))
            last_emitted_end[entity_id] = count

    for entity_id in list(buffers):
        tail = tail_record(entity_id)
        if tail is not None:
            yield tail


def group_sequences(
    events: Iterable[BehaviorEvent],
    window_size: int,
    stride: int,
    min_events: int,
) -> list[SequenceRecord]:
    grouped: dict[str, list[BehaviorEvent]] = defaultdict(list)
    for event in events:
        grouped[event.entity_id].append(event)
    records: list[SequenceRecord] = []
    for entity_id, entity_events in grouped.items():
        entity_events.sort(key=lambda event: event.parsed_time())
        for start, end in window_slices(
            len(entity_events), window_size, stride, min_events
        ):
            records.append(_make_sequence_record(entity_id, entity_events[start:end]))
    return records


def numeric_features(events: Sequence[BehaviorEvent]) -> np.ndarray:
    features = np.zeros((len(events), 6), dtype=np.float32)
    previous = None
    for index, event in enumerate(events):
        timestamp = event.parsed_time()
        delta = 0.0 if previous is None else max(0.0, (timestamp - previous).total_seconds())
        hour = timestamp.hour + timestamp.minute / 60.0
        features[index] = [
            min(math.log1p(delta) / 8.0, 1.0),
            math.sin(2.0 * math.pi * hour / 24.0),
            math.cos(2.0 * math.pi * hour / 24.0),
            float(event.result.lower() not in {"success", "ok", "allowed"}),
            min(len(event.object_name) / 80.0, 1.0),
            float(event.source.lower() == "agent"),
        ]
        previous = timestamp
    return features


class BehaviorSequenceDataset(Dataset):
    def __init__(
        self,
        records: Sequence[SequenceRecord],
        vocabulary: BehaviorVocabulary,
        window_size: int,
    ):
        self.records = list(records)
        self.vocabulary = vocabulary
        self.window_size = window_size

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int):
        record = self.records[index]
        size = min(len(record.events), self.window_size)
        tokens = np.full(self.window_size, self.vocabulary.pad_id, dtype=np.int64)
        values = np.zeros((self.window_size, 6), dtype=np.float32)
        event_labels = np.zeros(self.window_size, dtype=np.float32)
        tokens[:size] = [self.vocabulary.encode(event) for event in record.events[:size]]
        values[:size] = numeric_features(record.events[:size])
        event_labels[:size] = [event.label for event in record.events[:size]]
        return {
            "tokens": torch.from_numpy(tokens),
            "features": torch.from_numpy(values),
            "mask": torch.from_numpy(tokens != self.vocabulary.pad_id),
            "label": torch.tensor(float(record.label), dtype=torch.float32),
            "event_labels": torch.from_numpy(event_labels),
            "index": torch.tensor(index, dtype=torch.long),
        }


def load_records(
    path: str | Path, window_size: int, stride: int, min_events: int
) -> tuple[list[BehaviorEvent], list[SequenceRecord]]:
    events = list(iter_jsonl(path))
    return events, group_sequences(events, window_size, stride, min_events)
