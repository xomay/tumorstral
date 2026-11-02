"""All fixtures here are synthetic, not experimental observations."""

import pandas as pd
import pytest


@pytest.fixture
def sample():
    return pd.DataFrame({
        "study": ["S1"] * 4 + ["S2"] * 3,
        "group": ["1"] * 7,
        "treatment": ["Control"] * 7,
        "animal_id": ["001"] * 7,
        "day": [0, 2, 5, 9, 0, 3, 6],
        "tumour_volume": [10., 12., None, 20., 5., 6., 7.],
    })
