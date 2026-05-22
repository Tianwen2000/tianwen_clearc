from tianwen_clearc.treemap import Rect, WeightedItem, layout_treemap


def test_layout_treemap_preserves_item_count() -> None:
    items = [
        WeightedItem("a", 60),
        WeightedItem("b", 30),
        WeightedItem("c", 10),
    ]

    result = layout_treemap(items, Rect(0, 0, 100, 80), padding=0)

    assert [item.value for item in result] == ["a", "b", "c"]
    assert len(result) == 3


def test_layout_treemap_stays_inside_bounds() -> None:
    result = layout_treemap(
        [WeightedItem(str(index), index + 1) for index in range(12)],
        Rect(10, 20, 300, 200),
        padding=4,
    )

    for item in result:
        assert item.rect.x >= 14
        assert item.rect.y >= 24
        assert item.rect.x + item.rect.width <= 306.000001
        assert item.rect.y + item.rect.height <= 216.000001


def test_layout_treemap_ignores_zero_weight() -> None:
    result = layout_treemap([WeightedItem("empty", 0), WeightedItem("full", 1)], Rect(0, 0, 10, 10))

    assert [item.value for item in result] == ["full"]

