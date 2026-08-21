from audio_classifier.resolver import best_fingerprint_match_without_metadata, best_result_recording_ids


def test_best_fingerprint_match_without_metadata_returns_high_score_id():
    payload = {"results": [{"score": 0.92, "id": "aid", "recordings": []}]}
    match = best_fingerprint_match_without_metadata(payload, min_score=0.85)
    assert match == (0.92, "aid")


def test_best_fingerprint_match_without_metadata_ignores_low_score():
    payload = {"results": [{"score": 0.5, "id": "aid", "recordings": []}]}
    assert best_fingerprint_match_without_metadata(payload, min_score=0.85) is None


def test_best_result_recording_ids_returns_ids_even_without_metadata():
    payload = {
        "results": [
            {"score": 0.5, "id": "low", "recordings": [{"id": "r-low"}]},
            {"score": 0.93, "id": "aid", "recordings": [{"id": "r-1"}, {"id": "r-2"}, {"no_id": 1}]},
        ]
    }
    assert best_result_recording_ids(payload, min_score=0.85) == (0.93, "aid", ["r-1", "r-2"])


def test_best_result_recording_ids_ignores_low_scores():
    payload = {"results": [{"score": 0.4, "id": "aid", "recordings": [{"id": "r-1"}]}]}
    assert best_result_recording_ids(payload, min_score=0.85) is None
