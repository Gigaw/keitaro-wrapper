import pytest

from app.weights import WeightError, distribute


@pytest.mark.parametrize(
    "pinned, expected",
    [
        ([], []),
        ([None], [100]),
        ([None, None, None], [34, 33, 33]),
        ([None] * 4, [25, 25, 25, 25]),
        ([25, None, None, None], [25, 25, 25, 25]),
        ([25, None, None], [25, 38, 37]),
        ([None, 25, None], [38, 25, 37]),
        ([60, 40], [60, 40]),
        ([100], [100]),
        ([98, None, None, None], [98, 1, 1, 0]),
    ],
)
def test_distribute(pinned, expected):
    result = distribute(pinned)
    assert result == expected
    assert not result or sum(result) == 100


@pytest.mark.parametrize("pinned", [[60, 50, None], [50, 40], [100, None]])
def test_distribute_errors(pinned):
    with pytest.raises(WeightError):
        distribute(pinned)
