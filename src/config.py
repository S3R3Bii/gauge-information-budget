"""Fixed daily-flow simulation; operational vintage availability is unverified."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PAIRS={'wisconsin': [{'site': '05407000', 'series': '89f98d67cb76436cb1c7e4fc4442a4fd'}, {'site': '05400760', 'series': '67da93f42f0f435797e2c1a1ca9a3c22'}], 'delaware': [{'site': '01463500', 'series': 'd60c9905534e420eb01c0ae95f18c94e'}, {'site': '01457500', 'series': 'ee1bb1834239494293a8e3e560132241'}], 'susquehanna': [{'site': '01576000', 'series': 'e3c56541c1234488b6591cd94cec4a4f'}, {'site': '01570500', 'series': 'ed81ed5456d149a29517a72cb27d9d53'}], 'mississippi': [{'site': '05420500', 'series': 'c4895881ba81471c806eed7ba394f034'}, {'site': '05378500', 'series': 'abd38042f58a422082cdd2ffe6a91b55'}]}
DEVELOPMENT_BASINS=['wisconsin','delaware']
HELD_BASINS=['susquehanna','mississippi']
LAMBDAS=[0.001,0.01,0.1,1.0]
LAGS=[3,1]
MODELS=['persistence','local','pair']
TRAIN_YEARS=[2020,2021,2022]
VALIDATION_YEAR=2023
EVALUATION_YEARS=[2024,2025]
START='2019-12-01'
END='2025-12-31'
SEED=20261029
BOOTSTRAP_REPLICATES=500
BOOTSTRAP_BLOCK=14
