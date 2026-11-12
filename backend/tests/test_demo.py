from kavra.db import Database
from kavra.demo import DEMO, seed


def test_demo_seed_runs_real_pipeline(db: Database):
    out = seed(db)
    for key, spec in DEMO.items():
        # every hand-written question passes the real code checks incl. verbatim source quote
        assert out[key]["kept"] == len(spec["questions"]), key
        assert not out[key]["rejected"]
    assert out["reviews"] > 50
    assert db.scalar("SELECT COUNT(*) FROM topics") >= 6
    assert db.scalar("SELECT COUNT(*) FROM exams WHERE report IS NOT NULL") == 1
