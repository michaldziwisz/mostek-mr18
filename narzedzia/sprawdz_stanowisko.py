"""Cienkie wejście walidatora; nigdy nie uruchamia mostka ze sprzętem."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mostek.glowny import main as mostek


def main(argv=None):
    return mostek(['--sprawdz', *(sys.argv[1:] if argv is None else argv)])


if __name__ == '__main__':
    raise SystemExit(main())
