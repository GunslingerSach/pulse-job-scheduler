import os
import secrets

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg2://scheduler:scheduler@localhost:5432/job_scheduler_test"
)


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)


@pytest.fixture()
def db(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    # Clean slate for every test: truncate rather than recreate for speed.
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    yield session
    session.close()


@pytest.fixture()
def project_and_queue(db):
    user = models.User(email="test@example.com", hashed_password="x", full_name="Test User")
    db.add(user)
    db.flush()
    org = models.Organization(name="Test Org", owner_id=user.id)
    db.add(org)
    db.flush()
    project = models.Project(organization_id=org.id, name="Test Project", api_key=secrets.token_hex(16))
    db.add(project)
    db.flush()

    retry_policy = models.RetryPolicy(name="default", strategy=models.RetryStrategyType.FIXED,
                                       max_retries=2, base_delay_seconds=0, max_delay_seconds=60)
    db.add(retry_policy)
    db.flush()

    queue = models.Queue(project_id=project.id, name="default", max_concurrency=2,
                          default_retry_policy_id=retry_policy.id)
    db.add(queue)
    db.commit()
    return project, queue


@pytest.fixture()
def worker(db):
    w = models.Worker(name="test-worker", concurrency=5)
    db.add(w)
    db.commit()
    return w
