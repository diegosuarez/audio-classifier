from audio_classifier.resolver import best_fingerprint_match_without_metadata


def test_best_fingerprint_match_without_metadata_returns_high_score_id():
    payload = {"results": [{"score": 0.92, "id": "aid", "recordings": []}]}
    match = best_fingerprint_match_without_metadata(payload, min_score=0.85)
    assert match == (0.92, "aid")


def test_best_fingerprint_match_without_metadata_ignores_low_score():
    payload = {"results": [{"score": 0.5, "id": "aid", "recordings": []}]}
    assert best_fingerprint_match_without_metadata(payload, min_score=0.85) is None
