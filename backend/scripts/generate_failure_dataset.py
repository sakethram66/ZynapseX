"""Generate the project's reproducible, explicitly synthetic training CSV."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ml.synthetic_failure_data import generate_dataset, split_by_transformer


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=root / "data" / "synthetic_transformer_failure_dataset.csv")
    parser.add_argument("--train-output", type=Path, default=root / "data" / "synthetic_transformer_failure_train.csv")
    parser.add_argument("--test-output", type=Path, default=root / "data" / "synthetic_transformer_failure_test.csv")
    parser.add_argument("--episodes", type=int, default=240)
    parser.add_argument("--ticks", type=int, default=100)
    parser.add_argument("--seed", type=int, default=73021)
    args = parser.parse_args()
    frame = generate_dataset(args.episodes, args.ticks, args.seed)
    train, test = split_by_transformer(frame)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output, index=False, float_format="%.6f")
    args.train_output.parent.mkdir(parents=True, exist_ok=True)
    args.test_output.parent.mkdir(parents=True, exist_ok=True)
    train.to_csv(args.train_output, index=False, float_format="%.6f")
    test.to_csv(args.test_output, index=False, float_format="%.6f")
    print(f"Wrote {len(frame)} synthetic rows to {args.output}")
    print(f"Wrote {len(train)} train rows / {train.episode_id.nunique()} episodes to {args.train_output}")
    print(f"Wrote {len(test)} test rows / {test.episode_id.nunique()} episodes to {args.test_output}")
    print(frame["failure_within_horizon"].value_counts().sort_index().to_dict())


if __name__ == "__main__":
    main()
