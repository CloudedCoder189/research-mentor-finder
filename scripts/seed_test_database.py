"""Synthetic test data only. CLI refuses existing files and paths outside test-runtime."""
from pathlib import Path
import argparse

import database


def seed_records() -> None:
    records = []
    for index in range(40):
        records.append({
            "name": f"Synthetic Researcher {index + 1:02d}",
            "university": "Stanford University" if index % 2 == 0 else "University of Washington",
            "department": "Computer Science" if index % 3 else "Electrical Engineering",
            "title": "Assistant Professor",
            "research_interests": "Machine learning, deep learning, computer vision, robotics, systems, Python and visual recognition",
            "categories": "Machine Learning, Computer Vision, Robotics, Artificial Intelligence, Systems",
            "email": f"synthetic-{index + 1}@example.edu",
            "profile_url": f"https://example.edu/synthetic-{index + 1}",
            "website_url": "Not publicly available",
            "source_type": "Synthetic test fixture",
            "opportunity_level": "Strong" if index % 2 == 0 else "Basic",
        })
    database.initialize_database(run_maintenance=False)
    database.upsert_professors(records)
    with database.connect() as connection:
        connection.execute("UPDATE professors SET verification_status = CASE WHEN id % 2 = 1 THEN 'Verified' ELSE 'Review' END")
        connection.execute("UPDATE professors SET field = 'Statistics', discipline = 'Computing' WHERE id = 2")
        database._bump_data_revision(connection)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    target = parser.parse_args().database.resolve()
    allowed = (Path(__file__).resolve().parents[1] / "test-runtime").resolve()
    if not target.is_relative_to(allowed) or target.exists():
        parser.error("Use a NEW database under this working copy's test-runtime directory.")
    database.DB_PATH = target
    seed_records()
    print(f"Created synthetic isolated DB: {target}")
