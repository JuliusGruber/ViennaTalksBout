"""Tests for viennatalksbout.store — Topic store, lifecycle, merging, and snapshots."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from viennatalksbout.extractor import ExtractedTopic
from viennatalksbout.store import (
    DEFAULT_DECAY_FACTOR,
    DEFAULT_MAX_ACTIVE,
    DEFAULT_MIN_SCORE,
    DEFAULT_RETENTION_HOURS,
    DEFAULT_STALE_AFTER,
    Topic,
    TopicState,
    TopicStore,
    normalize_topic_name,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
SOURCE = "mastodon:wien.rocks"


def _et(topic: str, score: float = 0.5, count: int = 1) -> ExtractedTopic:
    """Shorthand for creating an ExtractedTopic."""
    return ExtractedTopic(topic=topic, score=score, count=count)


# ===========================================================================
# normalize_topic_name
# ===========================================================================


class TestNormalizeTopicName:
    """Tests for the topic name normalization function."""

    def test_lowercase(self):
        assert normalize_topic_name("Donauinselfest") == "donauinselfest"

    def test_strip_whitespace(self):
        assert normalize_topic_name("  Test  ") == "test"

    def test_collapse_internal_whitespace(self):
        assert normalize_topic_name("U2   Störung") == "u2 störung"

    def test_unicode_nfc_normalization(self):
        # ö can be represented as single char or o + combining umlaut
        composed = "Störung"
        decomposed = "Sto\u0308rung"
        assert normalize_topic_name(composed) == normalize_topic_name(decomposed)

    def test_empty_string(self):
        assert normalize_topic_name("") == ""

    def test_whitespace_only(self):
        assert normalize_topic_name("   ") == ""

    def test_mixed_case_german(self):
        assert normalize_topic_name("Wiener LINIEN") == "wiener linien"

    def test_tabs_and_newlines_collapsed(self):
        assert normalize_topic_name("U2\tStörung\n") == "u2 störung"

    def test_already_normalized(self):
        assert normalize_topic_name("u2 störung") == "u2 störung"


# ===========================================================================
# TopicState enum
# ===========================================================================


class TestTopicState:
    """Tests for the TopicState enum."""

    def test_entering_value(self):
        assert TopicState.ENTERING.value == "entering"

    def test_growing_value(self):
        assert TopicState.GROWING.value == "growing"

    def test_shrinking_value(self):
        assert TopicState.SHRINKING.value == "shrinking"

    def test_from_string(self):
        assert TopicState("entering") == TopicState.ENTERING
        assert TopicState("growing") == TopicState.GROWING
        assert TopicState("shrinking") == TopicState.SHRINKING

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            TopicState("disappeared")


# ===========================================================================
# Topic dataclass
# ===========================================================================


class TestTopic:
    """Tests for the Topic dataclass."""

    def test_create_topic(self):
        t = Topic(
            name="Donauinselfest",
            normalized_name="donauinselfest",
            score=0.9,
            first_seen=NOW,
            last_seen=NOW,
            source=SOURCE,
            state=TopicState.ENTERING,
        )
        assert t.name == "Donauinselfest"
        assert t.score == 0.9
        assert t.state == TopicState.ENTERING
        assert t.batches_since_seen == 0

    def test_default_batches_since_seen(self):
        t = Topic(
            name="Test",
            normalized_name="test",
            score=0.5,
            first_seen=NOW,
            last_seen=NOW,
            source=SOURCE,
            state=TopicState.GROWING,
        )
        assert t.batches_since_seen == 0

    def test_mutable(self):
        """Topic is a mutable dataclass (not frozen) — score and state can change."""
        t = Topic(
            name="Test",
            normalized_name="test",
            score=0.5,
            first_seen=NOW,
            last_seen=NOW,
            source=SOURCE,
            state=TopicState.ENTERING,
        )
        t.score = 0.8
        t.state = TopicState.GROWING
        assert t.score == 0.8
        assert t.state == TopicState.GROWING


# ===========================================================================
# TopicStore — construction and configuration
# ===========================================================================


class TestTopicStoreConfig:
    """Tests for TopicStore constructor and configuration."""

    def test_default_values(self):
        store = TopicStore()
        assert store.max_active == DEFAULT_MAX_ACTIVE
        assert store.stale_after == DEFAULT_STALE_AFTER
        assert store.decay_factor == DEFAULT_DECAY_FACTOR
        assert store.min_score == DEFAULT_MIN_SCORE
        assert store.retention_hours == DEFAULT_RETENTION_HOURS

    def test_custom_values(self):
        store = TopicStore(
            max_active=10,
            stale_after=5,
            decay_factor=0.7,
            min_score=0.01,
            retention_hours=48,
        )
        assert store.max_active == 10
        assert store.stale_after == 5
        assert store.decay_factor == 0.7
        assert store.min_score == 0.01
        assert store.retention_hours == 48

    def test_zero_max_active_raises(self):
        with pytest.raises(ValueError, match="max_active must be positive"):
            TopicStore(max_active=0)

    def test_negative_max_active_raises(self):
        with pytest.raises(ValueError, match="max_active must be positive"):
            TopicStore(max_active=-1)

    def test_zero_stale_after_raises(self):
        with pytest.raises(ValueError, match="stale_after must be positive"):
            TopicStore(stale_after=0)

    def test_decay_factor_zero_raises(self):
        with pytest.raises(ValueError, match="decay_factor must be in"):
            TopicStore(decay_factor=0.0)

    def test_decay_factor_one_raises(self):
        with pytest.raises(ValueError, match="decay_factor must be in"):
            TopicStore(decay_factor=1.0)

    def test_decay_factor_above_one_raises(self):
        with pytest.raises(ValueError, match="decay_factor must be in"):
            TopicStore(decay_factor=1.5)

    def test_decay_factor_negative_raises(self):
        with pytest.raises(ValueError, match="decay_factor must be in"):
            TopicStore(decay_factor=-0.5)

    def test_zero_min_score_raises(self):
        with pytest.raises(ValueError, match="min_score must be positive"):
            TopicStore(min_score=0)

    def test_negative_min_score_raises(self):
        with pytest.raises(ValueError, match="min_score must be positive"):
            TopicStore(min_score=-0.01)

    def test_zero_retention_hours_raises(self):
        with pytest.raises(ValueError, match="retention_hours must be positive"):
            TopicStore(retention_hours=0)

    def test_starts_empty(self):
        store = TopicStore()
        assert store.get_topic_count() == 0
        assert store.get_current_topics() == []


# ===========================================================================
# TopicStore.merge — new topics
# ===========================================================================


class TestTopicStoreMergeNew:
    """Tests for adding new topics via merge."""

    def test_new_topic_enters_store(self):
        store = TopicStore()
        store.merge([_et("Donauinselfest", 0.9)], SOURCE, now=NOW)
        assert store.get_topic_count() == 1

    def test_new_topic_has_entering_state(self):
        store = TopicStore()
        store.merge([_et("Donauinselfest", 0.9)], SOURCE, now=NOW)
        topics = store.get_current_topics()
        assert topics[0].state == TopicState.ENTERING

    def test_new_topic_score_set_correctly(self):
        store = TopicStore()
        store.merge([_et("Donauinselfest", 0.9)], SOURCE, now=NOW)
        topics = store.get_current_topics()
        assert topics[0].score == 0.9

    def test_new_topic_timestamps(self):
        store = TopicStore()
        store.merge([_et("Donauinselfest", 0.9)], SOURCE, now=NOW)
        topics = store.get_current_topics()
        assert topics[0].first_seen == NOW
        assert topics[0].last_seen == NOW

    def test_new_topic_source(self):
        store = TopicStore()
        store.merge([_et("Donauinselfest", 0.9)], SOURCE, now=NOW)
        topics = store.get_current_topics()
        assert topics[0].source == SOURCE

    def test_new_topic_name_preserved(self):
        store = TopicStore()
        store.merge([_et("Donauinselfest", 0.9)], SOURCE, now=NOW)
        topics = store.get_current_topics()
        assert topics[0].name == "Donauinselfest"

    def test_new_topic_name_stripped(self):
        store = TopicStore()
        store.merge([_et("  Donauinselfest  ", 0.9)], SOURCE, now=NOW)
        topics = store.get_current_topics()
        assert topics[0].name == "Donauinselfest"

    def test_multiple_new_topics(self):
        store = TopicStore()
        store.merge(
            [_et("Donauinselfest", 0.9), _et("U2 Störung", 0.6)],
            SOURCE,
            now=NOW,
        )
        assert store.get_topic_count() == 2

    def test_empty_extraction_no_change(self):
        store = TopicStore()
        store.merge([], SOURCE, now=NOW)
        assert store.get_topic_count() == 0

    def test_empty_topic_name_skipped(self):
        store = TopicStore()
        store.merge([_et("", 0.5)], SOURCE, now=NOW)
        assert store.get_topic_count() == 0

    def test_whitespace_only_topic_skipped(self):
        store = TopicStore()
        store.merge([_et("   ", 0.5)], SOURCE, now=NOW)
        assert store.get_topic_count() == 0


# ===========================================================================
# TopicStore.merge — topic matching (case-insensitive)
# ===========================================================================


class TestTopicStoreMergeMatching:
    """Tests for topic matching during merge — case-insensitive normalization."""

    def test_case_insensitive_match(self):
        store = TopicStore()
        store.merge([_et("Donauinselfest", 0.9)], SOURCE, now=NOW)
        t1 = NOW + timedelta(minutes=10)
        store.merge([_et("donauinselfest", 0.8)], SOURCE, now=t1)
        assert store.get_topic_count() == 1

    def test_whitespace_normalized_match(self):
        store = TopicStore()
        store.merge([_et("U2 Störung", 0.9)], SOURCE, now=NOW)
        t1 = NOW + timedelta(minutes=10)
        store.merge([_et("U2  Störung", 0.8)], SOURCE, now=t1)
        assert store.get_topic_count() == 1

    def test_matched_topic_score_updated(self):
        store = TopicStore()
        store.merge([_et("Donauinselfest", 0.9)], SOURCE, now=NOW)
        t1 = NOW + timedelta(minutes=10)
        store.merge([_et("Donauinselfest", 0.7)], SOURCE, now=t1)
        topics = store.get_current_topics()
        assert topics[0].score == 0.7

    def test_matched_topic_last_seen_updated(self):
        store = TopicStore()
        store.merge([_et("Donauinselfest", 0.9)], SOURCE, now=NOW)
        t1 = NOW + timedelta(minutes=10)
        store.merge([_et("Donauinselfest", 0.9)], SOURCE, now=t1)
        topics = store.get_current_topics()
        assert topics[0].last_seen == t1

    def test_matched_topic_first_seen_preserved(self):
        store = TopicStore()
        store.merge([_et("Donauinselfest", 0.9)], SOURCE, now=NOW)
        t1 = NOW + timedelta(minutes=10)
        store.merge([_et("Donauinselfest", 0.9)], SOURCE, now=t1)
        topics = store.get_current_topics()
        assert topics[0].first_seen == NOW

    def test_matched_topic_batches_since_seen_reset(self):
        store = TopicStore(stale_after=5)
        store.merge([_et("A", 0.9)], SOURCE, now=NOW)
        # Several merges without A to bump batches_since_seen
        for i in range(2):
            store.merge([], SOURCE, now=NOW + timedelta(minutes=10 * (i + 1)))
        topics = store.get_current_topics()
        assert topics[0].batches_since_seen == 2
        # Now A appears again
        store.merge(
            [_et("A", 0.8)], SOURCE, now=NOW + timedelta(minutes=30)
        )
        topics = store.get_current_topics()
        assert topics[0].batches_since_seen == 0

    def test_original_display_name_preserved_on_update(self):
        """The display name keeps the casing from the first extraction."""
        store = TopicStore()
        store.merge([_et("Donauinselfest", 0.9)], SOURCE, now=NOW)
        t1 = NOW + timedelta(minutes=10)
        store.merge([_et("DONAUINSELFEST", 0.8)], SOURCE, now=t1)
        topics = store.get_current_topics()
        assert topics[0].name == "Donauinselfest"


# ===========================================================================
# TopicStore.merge — lifecycle state transitions
# ===========================================================================


class TestTopicStoreLifecycle:
    """Tests for lifecycle state transitions through merge cycles."""

    def test_entering_to_growing(self):
        """A topic seen again transitions from entering to growing."""
        store = TopicStore()
        store.merge([_et("A", 0.9)], SOURCE, now=NOW)
        assert store.get_current_topics()[0].state == TopicState.ENTERING
        t1 = NOW + timedelta(minutes=10)
        store.merge([_et("A", 0.8)], SOURCE, now=t1)
        assert store.get_current_topics()[0].state == TopicState.GROWING

    def test_growing_stays_growing(self):
        """A growing topic seen again stays growing."""
        store = TopicStore()
        store.merge([_et("A", 0.9)], SOURCE, now=NOW)
        t1 = NOW + timedelta(minutes=10)
        store.merge([_et("A", 0.8)], SOURCE, now=t1)
        assert store.get_current_topics()[0].state == TopicState.GROWING
        t2 = NOW + timedelta(minutes=20)
        store.merge([_et("A", 0.7)], SOURCE, now=t2)
        assert store.get_current_topics()[0].state == TopicState.GROWING

    def test_entering_to_shrinking_after_stale(self):
        """An entering topic becomes shrinking after stale_after unseen merges."""
        store = TopicStore(stale_after=2)
        store.merge([_et("A", 0.9)], SOURCE, now=NOW)

        # 1 unseen merge — still entering
        store.merge([], SOURCE, now=NOW + timedelta(minutes=10))
        topics = store.get_current_topics()
        assert topics[0].state == TopicState.ENTERING

        # 2 unseen merges — now shrinking
        store.merge([], SOURCE, now=NOW + timedelta(minutes=20))
        topics = store.get_current_topics()
        assert topics[0].state == TopicState.SHRINKING

    def test_growing_to_shrinking_after_stale(self):
        """A growing topic becomes shrinking after stale_after unseen merges."""
        store = TopicStore(stale_after=2)
        store.merge([_et("A", 0.9)], SOURCE, now=NOW)
        store.merge([_et("A", 0.8)], SOURCE, now=NOW + timedelta(minutes=10))
        assert store.get_current_topics()[0].state == TopicState.GROWING

        # 2 unseen merges → shrinking
        store.merge([], SOURCE, now=NOW + timedelta(minutes=20))
        store.merge([], SOURCE, now=NOW + timedelta(minutes=30))
        assert store.get_current_topics()[0].state == TopicState.SHRINKING

    def test_shrinking_to_growing_on_recovery(self):
        """A shrinking topic that reappears transitions to growing."""
        store = TopicStore(stale_after=1)
        store.merge([_et("A", 0.9)], SOURCE, now=NOW)

        # 1 unseen merge → shrinking
        store.merge([], SOURCE, now=NOW + timedelta(minutes=10))
        assert store.get_current_topics()[0].state == TopicState.SHRINKING

        # Reappears → growing
        store.merge(
            [_et("A", 0.8)], SOURCE, now=NOW + timedelta(minutes=20)
        )
        assert store.get_current_topics()[0].state == TopicState.GROWING

    def test_shrinking_topic_score_decays(self):
        """Score is multiplied by decay_factor each merge cycle while shrinking."""
        store = TopicStore(stale_after=1, decay_factor=0.5)
        store.merge([_et("A", 0.8)], SOURCE, now=NOW)

        # 1 unseen → shrinking, score decayed
        store.merge([], SOURCE, now=NOW + timedelta(minutes=10))
        topics = store.get_current_topics()
        assert topics[0].score == pytest.approx(0.4)

        # Another unseen → more decay
        store.merge([], SOURCE, now=NOW + timedelta(minutes=20))
        topics = store.get_current_topics()
        assert topics[0].score == pytest.approx(0.2)

    def test_topic_disappears_when_score_below_min(self):
        """A shrinking topic is removed once its score falls below min_score."""
        store = TopicStore(stale_after=1, decay_factor=0.5, min_score=0.1)
        store.merge([_et("A", 0.2)], SOURCE, now=NOW)

        # Unseen → shrinking, score = 0.2 * 0.5 = 0.1 → still >= min_score
        store.merge([], SOURCE, now=NOW + timedelta(minutes=10))
        assert store.get_topic_count() == 1

        # Another unseen → score = 0.1 * 0.5 = 0.05 → below 0.1, removed
        store.merge([], SOURCE, now=NOW + timedelta(minutes=20))
        assert store.get_topic_count() == 0

    def test_stale_after_default_is_three(self):
        """With default stale_after=3, topic doesn't shrink until 3 unseen merges."""
        store = TopicStore()
        store.merge([_et("A", 0.9)], SOURCE, now=NOW)

        for i in range(2):
            store.merge([], SOURCE, now=NOW + timedelta(minutes=10 * (i + 1)))
        # After 2 unseen: still entering
        assert store.get_current_topics()[0].state == TopicState.ENTERING

        # After 3 unseen: now shrinking
        store.merge([], SOURCE, now=NOW + timedelta(minutes=30))
        assert store.get_current_topics()[0].state == TopicState.SHRINKING

    def test_entering_not_shrinking_stays_entering_before_stale(self):
        """Entering topics stay entering when batches_since_seen < stale_after."""
        store = TopicStore(stale_after=3)
        store.merge([_et("A", 0.9)], SOURCE, now=NOW)
        store.merge([], SOURCE, now=NOW + timedelta(minutes=10))
        topics = store.get_current_topics()
        assert topics[0].state == TopicState.ENTERING
        assert topics[0].batches_since_seen == 1


# ===========================================================================
# TopicStore.merge — 20-topic cap and eviction
# ===========================================================================


class TestTopicStoreCap:
    """Tests for the max_active cap and eviction logic."""

    def test_respects_max_active(self):
        store = TopicStore(max_active=5)
        topics = [_et(f"Topic{i}", 0.5 + i * 0.01) for i in range(7)]
        store.merge(topics, SOURCE, now=NOW)
        assert store.get_topic_count() == 5

    def test_evicts_lowest_scoring(self):
        store = TopicStore(max_active=3)
        store.merge(
            [
                _et("Low", 0.1),
                _et("Mid", 0.5),
                _et("High", 0.9),
                _et("VeryHigh", 1.0),
            ],
            SOURCE,
            now=NOW,
        )
        names = {t.name for t in store.get_current_topics()}
        assert "Low" not in names
        assert "Mid" in names
        assert "High" in names
        assert "VeryHigh" in names

    def test_cap_default_is_twenty(self):
        store = TopicStore()
        topics = [_et(f"T{i}", 0.5 + i * 0.01) for i in range(25)]
        store.merge(topics, SOURCE, now=NOW)
        assert store.get_topic_count() == 20

    def test_cap_enforced_after_adding_new_topics(self):
        """When new topics push past the cap, lowest-scoring are evicted."""
        store = TopicStore(max_active=3)
        store.merge(
            [_et("A", 0.5), _et("B", 0.6), _et("C", 0.7)],
            SOURCE,
            now=NOW,
        )
        assert store.get_topic_count() == 3

        # Add a new high-scoring topic
        t1 = NOW + timedelta(minutes=10)
        store.merge(
            [_et("A", 0.5), _et("B", 0.6), _et("C", 0.7), _et("D", 0.9)],
            SOURCE,
            now=t1,
        )
        assert store.get_topic_count() == 3
        names = {t.name for t in store.get_current_topics()}
        assert "A" not in names  # lowest scoring evicted
        assert "D" in names

    def test_single_active_topic(self):
        store = TopicStore(max_active=1)
        store.merge(
            [_et("Low", 0.1), _et("High", 0.9)], SOURCE, now=NOW
        )
        assert store.get_topic_count() == 1
        assert store.get_current_topics()[0].name == "High"


# ===========================================================================
# TopicStore.get_current_topics
# ===========================================================================


class TestTopicStoreGetCurrentTopics:
    """Tests for the get_current_topics method."""

    def test_returns_empty_for_empty_store(self):
        store = TopicStore()
        assert store.get_current_topics() == []

    def test_sorted_by_score_descending(self):
        store = TopicStore()
        store.merge(
            [_et("Low", 0.3), _et("High", 0.9), _et("Mid", 0.6)],
            SOURCE,
            now=NOW,
        )
        topics = store.get_current_topics()
        assert topics[0].name == "High"
        assert topics[1].name == "Mid"
        assert topics[2].name == "Low"

    def test_returns_copies(self):
        """Modifying returned topics does not affect the store."""
        store = TopicStore()
        store.merge([_et("A", 0.9)], SOURCE, now=NOW)
        topics = store.get_current_topics()
        topics[0].score = 0.0
        # Store should be unaffected
        assert store.get_current_topics()[0].score == 0.9

    def test_includes_all_states(self):
        """Topics in all lifecycle states are included."""
        store = TopicStore(stale_after=1)
        store.merge([_et("A", 0.9), _et("B", 0.5)], SOURCE, now=NOW)
        # B is not seen again → becomes shrinking after 1 unseen merge
        t1 = NOW + timedelta(minutes=10)
        store.merge([_et("A", 0.8), _et("C", 0.7)], SOURCE, now=t1)

        topics = store.get_current_topics()
        states = {t.name: t.state for t in topics}
        assert states["A"] == TopicState.GROWING
        assert states["B"] == TopicState.SHRINKING
        assert states["C"] == TopicState.ENTERING


# ===========================================================================
# TopicStore — thread safety
# ===========================================================================


class TestTopicStoreThreadSafety:
    """Tests for concurrent access from multiple threads."""

    def test_concurrent_merges(self):
        """Multiple threads merging simultaneously should not corrupt state."""
        store = TopicStore(max_active=100)
        num_threads = 10
        topics_per_thread = 5
        barrier = threading.Barrier(num_threads)

        def merger(thread_id: int):
            barrier.wait()
            topics = [
                _et(f"T{thread_id}_{i}", 0.5)
                for i in range(topics_per_thread)
            ]
            store.merge(topics, SOURCE, now=NOW)

        threads = [
            threading.Thread(target=merger, args=(t,))
            for t in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have topics from all threads (with possible overwrites from
        # concurrent merges, but no crashes or data corruption)
        count = store.get_topic_count()
        assert count > 0
        assert count <= num_threads * topics_per_thread

    def test_concurrent_merge_and_read(self):
        """Reading while merging should not raise or return corrupt data."""
        store = TopicStore()
        stop_event = threading.Event()

        def reader():
            while not stop_event.is_set():
                topics = store.get_current_topics()
                # Each topic should have valid fields
                for t in topics:
                    assert isinstance(t.name, str)
                    assert isinstance(t.score, float)

        def merger():
            for i in range(50):
                store.merge(
                    [_et(f"Topic{i}", 0.5)],
                    SOURCE,
                    now=NOW + timedelta(minutes=i),
                )

        reader_thread = threading.Thread(target=reader)
        reader_thread.start()

        merger()

        stop_event.set()
        reader_thread.join()

        assert store.get_topic_count() > 0


# ===========================================================================
# TopicStore — snapshot persistence
# ===========================================================================


class TestTopicStoreSnapshot:
    """Tests for saving and loading JSON snapshots."""

    def test_save_snapshot_creates_file(self, tmp_path):
        store = TopicStore(snapshot_dir=tmp_path)
        store.merge([_et("A", 0.9)], SOURCE, now=NOW)
        path = store.save_snapshot(now=NOW)
        assert path is not None
        assert path.exists()

    def test_save_snapshot_filename_format(self, tmp_path):
        store = TopicStore(snapshot_dir=tmp_path)
        store.merge([_et("A", 0.9)], SOURCE, now=NOW)
        path = store.save_snapshot(now=NOW)
        assert path.name == "topics_20250615_12.json"

    def test_save_snapshot_returns_none_without_dir(self):
        store = TopicStore(snapshot_dir=None)
        assert store.save_snapshot(now=NOW) is None

    def test_save_snapshot_creates_directory(self, tmp_path):
        snap_dir = tmp_path / "nested" / "snapshots"
        store = TopicStore(snapshot_dir=snap_dir)
        store.merge([_et("A", 0.9)], SOURCE, now=NOW)
        path = store.save_snapshot(now=NOW)
        assert path is not None
        assert snap_dir.exists()

    def test_snapshot_contains_valid_json(self, tmp_path):
        store = TopicStore(snapshot_dir=tmp_path)
        store.merge(
            [_et("Donauinselfest", 0.9), _et("U2 Störung", 0.6)],
            SOURCE,
            now=NOW,
        )
        path = store.save_snapshot(now=NOW)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert "timestamp" in data
        assert "topics" in data
        assert len(data["topics"]) == 2

    def test_snapshot_topic_fields(self, tmp_path):
        store = TopicStore(snapshot_dir=tmp_path)
        store.merge([_et("Donauinselfest", 0.9)], SOURCE, now=NOW)
        path = store.save_snapshot(now=NOW)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        topic = data["topics"][0]
        assert topic["name"] == "Donauinselfest"
        assert topic["score"] == 0.9
        assert topic["source"] == SOURCE
        assert topic["state"] == "entering"
        assert "first_seen" in topic
        assert "last_seen" in topic
        assert topic["batches_since_seen"] == 0

    def test_snapshot_preserves_unicode(self, tmp_path):
        store = TopicStore(snapshot_dir=tmp_path)
        store.merge([_et("U2 Störung", 0.6)], SOURCE, now=NOW)
        path = store.save_snapshot(now=NOW)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["topics"][0]["name"] == "U2 Störung"

    def test_save_snapshot_overwrites_same_hour(self, tmp_path):
        store = TopicStore(snapshot_dir=tmp_path)
        store.merge([_et("A", 0.9)], SOURCE, now=NOW)
        store.save_snapshot(now=NOW)

        store.merge([_et("B", 0.8)], SOURCE, now=NOW + timedelta(minutes=30))
        store.save_snapshot(now=NOW + timedelta(minutes=30))

        # Same hour, should overwrite
        files = list(tmp_path.glob("topics_*.json"))
        assert len(files) == 1

    def test_empty_store_saves_empty_topics(self, tmp_path):
        store = TopicStore(snapshot_dir=tmp_path)
        path = store.save_snapshot(now=NOW)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["topics"] == []

    def test_load_snapshot(self, tmp_path):
        store = TopicStore(snapshot_dir=tmp_path)
        store.merge(
            [_et("Donauinselfest", 0.9), _et("U2 Störung", 0.6)],
            SOURCE,
            now=NOW,
        )
        path = store.save_snapshot(now=NOW)

        topics = store.load_snapshot(path)
        assert len(topics) == 2
        assert topics[0].name == "Donauinselfest"
        assert topics[0].score == 0.9
        assert topics[0].state == TopicState.ENTERING

    def test_load_snapshot_from_string_path(self, tmp_path):
        store = TopicStore(snapshot_dir=tmp_path)
        store.merge([_et("A", 0.5)], SOURCE, now=NOW)
        path = store.save_snapshot(now=NOW)
        topics = store.load_snapshot(str(path))
        assert len(topics) == 1

    def test_load_snapshot_file_not_found(self):
        store = TopicStore()
        with pytest.raises(FileNotFoundError):
            store.load_snapshot("/nonexistent/path.json")

    def test_load_snapshot_invalid_format(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text('{"no_topics_key": true}')
        store = TopicStore()
        with pytest.raises(ValueError, match="Invalid snapshot format"):
            store.load_snapshot(bad_file)

    def test_load_snapshot_skips_malformed_entries(self, tmp_path):
        """Malformed topic entries are skipped, valid ones are loaded."""
        snapshot = {
            "timestamp": NOW.isoformat(),
            "topics": [
                {
                    "name": "Valid",
                    "score": 0.9,
                    "first_seen": NOW.isoformat(),
                    "last_seen": NOW.isoformat(),
                    "source": SOURCE,
                    "state": "entering",
                    "batches_since_seen": 0,
                },
                {
                    "name": "Bad",
                    # missing score and other fields
                },
            ],
        }
        path = tmp_path / "partial.json"
        path.write_text(json.dumps(snapshot))

        store = TopicStore()
        topics = store.load_snapshot(path)
        assert len(topics) == 1
        assert topics[0].name == "Valid"

    def test_load_snapshot_normalizes_names(self, tmp_path):
        """Loaded topics get their normalized_name computed."""
        store = TopicStore(snapshot_dir=tmp_path)
        store.merge([_et("Donauinselfest", 0.9)], SOURCE, now=NOW)
        path = store.save_snapshot(now=NOW)

        topics = store.load_snapshot(path)
        assert topics[0].normalized_name == "donauinselfest"

    def test_snapshot_sorted_by_score(self, tmp_path):
        """Snapshot topics are sorted by score descending (via get_current_topics)."""
        store = TopicStore(snapshot_dir=tmp_path)
        store.merge(
            [_et("Low", 0.3), _et("High", 0.9), _et("Mid", 0.6)],
            SOURCE,
            now=NOW,
        )
        path = store.save_snapshot(now=NOW)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        scores = [t["score"] for t in data["topics"]]
        assert scores == sorted(scores, reverse=True)


# ===========================================================================
# TopicStore — snapshot cleanup
# ===========================================================================


class TestTopicStoreCleanup:
    """Tests for snapshot retention and cleanup policy."""

    def test_removes_old_snapshots(self, tmp_path):
        store = TopicStore(snapshot_dir=tmp_path, retention_hours=24)

        # Create snapshots at various times
        old_time = NOW - timedelta(hours=25)
        recent_time = NOW - timedelta(hours=1)

        store.merge([_et("A", 0.9)], SOURCE, now=old_time)
        store.save_snapshot(now=old_time)

        store.merge([_et("B", 0.8)], SOURCE, now=recent_time)
        store.save_snapshot(now=recent_time)

        removed = store.cleanup_snapshots(now=NOW)
        assert removed == 1
        assert len(list(tmp_path.glob("topics_*.json"))) == 1

    def test_keeps_recent_snapshots(self, tmp_path):
        store = TopicStore(snapshot_dir=tmp_path, retention_hours=24)

        recent_time = NOW - timedelta(hours=2)
        store.merge([_et("A", 0.9)], SOURCE, now=recent_time)
        store.save_snapshot(now=recent_time)

        removed = store.cleanup_snapshots(now=NOW)
        assert removed == 0
        assert len(list(tmp_path.glob("topics_*.json"))) == 1

    def test_cleanup_returns_zero_for_no_dir(self):
        store = TopicStore(snapshot_dir=None)
        assert store.cleanup_snapshots(now=NOW) == 0

    def test_cleanup_returns_zero_for_nonexistent_dir(self, tmp_path):
        store = TopicStore(snapshot_dir=tmp_path / "nonexistent")
        assert store.cleanup_snapshots(now=NOW) == 0

    def test_cleanup_handles_malformed_filenames(self, tmp_path):
        """Files that don't match the expected naming are ignored."""
        store = TopicStore(snapshot_dir=tmp_path, retention_hours=24)

        # Create a valid old snapshot
        old_time = NOW - timedelta(hours=25)
        store.merge([_et("A", 0.9)], SOURCE, now=old_time)
        store.save_snapshot(now=old_time)

        # Create a file with a malformed name
        (tmp_path / "topics_badname.json").write_text("{}")

        removed = store.cleanup_snapshots(now=NOW)
        assert removed == 1  # only the valid old one
        # Malformed file should still exist
        assert (tmp_path / "topics_badname.json").exists()

    def test_cleanup_multiple_old_snapshots(self, tmp_path):
        store = TopicStore(snapshot_dir=tmp_path, retention_hours=2)

        for h in range(5):
            t = NOW - timedelta(hours=h)
            store.merge([_et(f"T{h}", 0.5)], SOURCE, now=t)
            store.save_snapshot(now=t)

        removed = store.cleanup_snapshots(now=NOW)
        # Hours 3 and 4 are older than 2 hours
        assert removed == 2
        assert len(list(tmp_path.glob("topics_*.json"))) == 3

    def test_cleanup_at_exact_boundary(self, tmp_path):
        """Snapshots at exactly the cutoff time are kept (not strictly less)."""
        store = TopicStore(snapshot_dir=tmp_path, retention_hours=24)

        boundary_time = NOW - timedelta(hours=24)
        store.merge([_et("A", 0.9)], SOURCE, now=boundary_time)
        store.save_snapshot(now=boundary_time)

        # The snapshot timestamp (hour-truncated) should be at the cutoff
        # Since it's at the boundary, it should NOT be removed
        # (file_time < cutoff, but file_time = cutoff here, so not removed)
        removed = store.cleanup_snapshots(now=NOW)
        assert removed == 0


# ===========================================================================
# TopicStore.merge — complex scenarios
# ===========================================================================


class TestTopicStoreComplexScenarios:
    """End-to-end scenarios testing multiple merge cycles."""

    def test_full_lifecycle(self):
        """Topic goes through entering → growing → shrinking → disappeared."""
        store = TopicStore(stale_after=1, decay_factor=0.3, min_score=0.05)

        # Merge 1: topic enters
        store.merge([_et("A", 0.5)], SOURCE, now=NOW)
        assert store.get_current_topics()[0].state == TopicState.ENTERING

        # Merge 2: topic seen again → growing
        t1 = NOW + timedelta(minutes=10)
        store.merge([_et("A", 0.6)], SOURCE, now=t1)
        assert store.get_current_topics()[0].state == TopicState.GROWING

        # Merge 3: topic not seen → shrinking (score 0.6 * 0.3 = 0.18)
        t2 = NOW + timedelta(minutes=20)
        store.merge([], SOURCE, now=t2)
        topics = store.get_current_topics()
        assert topics[0].state == TopicState.SHRINKING
        assert topics[0].score == pytest.approx(0.18)

        # Merge 4: still not seen → more decay (0.18 * 0.3 = 0.054)
        t3 = NOW + timedelta(minutes=30)
        store.merge([], SOURCE, now=t3)
        topics = store.get_current_topics()
        assert topics[0].score == pytest.approx(0.054)

        # Merge 5: still not seen → score 0.054 * 0.3 = 0.0162 < 0.05 → removed
        t4 = NOW + timedelta(minutes=40)
        store.merge([], SOURCE, now=t4)
        assert store.get_topic_count() == 0

    def test_topic_replacement_flow(self):
        """New topics replace old ones when cap is reached."""
        store = TopicStore(max_active=3, stale_after=1, decay_factor=0.5)

        # Fill with 3 topics
        store.merge(
            [_et("A", 0.3), _et("B", 0.5), _et("C", 0.7)],
            SOURCE,
            now=NOW,
        )
        assert store.get_topic_count() == 3

        # New topic D appears, all others still present
        t1 = NOW + timedelta(minutes=10)
        store.merge(
            [_et("B", 0.5), _et("C", 0.7), _et("D", 0.9)],
            SOURCE,
            now=t1,
        )
        # A was not seen → shrinking (score 0.3 * 0.5 = 0.15)
        # 4 topics now: B, C, D, A — cap is 3, A is lowest → evicted
        assert store.get_topic_count() == 3
        names = {t.name for t in store.get_current_topics()}
        assert "A" not in names
        assert "D" in names

    def test_mixed_entering_growing_shrinking(self):
        """Store can contain topics in all three active states simultaneously."""
        store = TopicStore(stale_after=1, decay_factor=0.5, min_score=0.01)

        # Merge 1: A, B, C all enter
        store.merge(
            [_et("A", 0.9), _et("B", 0.7), _et("C", 0.5)],
            SOURCE,
            now=NOW,
        )

        # Merge 2: A seen again (growing), B not seen (shrinking after 1),
        #          D is new (entering)
        t1 = NOW + timedelta(minutes=10)
        store.merge([_et("A", 0.8), _et("D", 0.6)], SOURCE, now=t1)

        topics = store.get_current_topics()
        state_map = {t.name: t.state for t in topics}

        assert state_map["A"] == TopicState.GROWING
        assert state_map["B"] == TopicState.SHRINKING
        assert state_map["C"] == TopicState.SHRINKING
        assert state_map["D"] == TopicState.ENTERING

    def test_merge_with_duplicate_topics_in_batch(self):
        """If the same topic appears twice in one batch, last one wins."""
        store = TopicStore()
        store.merge(
            [_et("A", 0.3), _et("A", 0.9)],
            SOURCE,
            now=NOW,
        )
        # The second "A" should overwrite the first
        assert store.get_topic_count() == 1
        assert store.get_current_topics()[0].score == 0.9

    def test_many_merge_cycles_with_churn(self):
        """Simulate many merge cycles with topics appearing and disappearing."""
        store = TopicStore(
            max_active=5, stale_after=2, decay_factor=0.5, min_score=0.01
        )

        for cycle in range(20):
            # Each cycle introduces 2 new topics and keeps 1 old one
            topics = [
                _et(f"Cycle{cycle}_A", 0.8),
                _et(f"Cycle{cycle}_B", 0.6),
            ]
            if cycle > 0:
                topics.append(_et(f"Cycle{cycle - 1}_A", 0.5))
            t = NOW + timedelta(minutes=10 * cycle)
            store.merge(topics, SOURCE, now=t)

        # Should never exceed max_active
        assert store.get_topic_count() <= 5
        assert store.get_topic_count() > 0
