from app.ai.related import pick_candidates


def _item(item_id, title, summary="filler text"):
    return {"id": item_id, "title": title, "summary": summary}


def test_always_keeps_recent_items_even_without_overlap():
    items = [_item(i, f"unrelated {i}") for i in range(5, 0, -1)]
    result = pick_candidates("completely different words", items, recent_limit=3)
    assert [item["id"] for item in result] == [5, 4, 3]


def test_adds_older_item_sharing_keywords():
    recent = [_item(i, "coffee shop review") for i in range(20, 10, -1)]
    old_related = _item(2, "Interview tips", "Use the STAR method in behavioral interview answers")
    old_unrelated = _item(1, "Gardening", "Water tomatoes every morning")
    result = pick_candidates(
        "More interview advice: structure behavioral answers with STAR",
        recent + [old_related, old_unrelated],
    )
    ids = [item["id"] for item in result]
    assert ids[:10] == list(range(20, 10, -1))
    assert 2 in ids
    assert 1 not in ids


def test_single_shared_keyword_is_not_enough():
    recent = [_item(i, "recent") for i in range(12, 2, -1)]
    old = _item(1, "Interview", "nothing else matches")
    result = pick_candidates("interview tomorrow morning", recent + [old])
    assert 1 not in [item["id"] for item in result]


def test_stopwords_do_not_count_as_shared_keywords():
    recent = [_item(i, "recent") for i in range(12, 2, -1)]
    old = _item(1, "Note", "this would have been with them")
    result = pick_candidates("this would have been with them", recent + [old])
    assert 1 not in [item["id"] for item in result]


def test_ranks_by_overlap_and_caps_keyword_matches():
    recent = [_item(i, "recent") for i in range(30, 20, -1)]
    weak = _item(3, "budget travel", "cheap flights")
    strong = _item(2, "budget travel japan", "cheap flights tokyo hostels")
    result = pick_candidates("budget travel japan cheap flights tokyo", recent + [weak, strong], keyword_limit=1)
    assert [item["id"] for item in result][10:] == [2]
