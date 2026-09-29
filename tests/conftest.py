import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# Ensure test configuration
os.environ["APP_ENV"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-32-chars-long-1234567"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["WHATSAPP_ACCESS_TOKEN"] = "test-token"
os.environ["WHATSAPP_PHONE_NUMBER_ID"] = "10987654321"
os.environ["WHATSAPP_VERIFY_TOKEN"] = "test-verify-secret"
os.environ["WHATSAPP_RECIPIENT_NUMBER"] = "15550001111"
os.environ["GMAIL_PUBSUB_TOPIC"] = "projects/test/topics/mail"

from app.database import Base, get_db
from app.main import app
from app.models.gmail_account import GmailAccount
from app.utils.security import encrypt_token

# Test engine using in-memory SQLite
test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session():
    """Provides a transactional database session for each test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    """FastAPI TestClient with overridden get_db dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_account(db_session):
    """Creates a sample connected Gmail account in the test DB."""
    account = GmailAccount(
        email="testuser@example.com",
        refresh_token_ref=encrypt_token("test-mock-refresh-token"),
        access_token="test-access-token",
        history_id="1000",
        is_active=True,
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    return account
