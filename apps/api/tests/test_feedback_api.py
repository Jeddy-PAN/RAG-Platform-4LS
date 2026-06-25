from app.models.conversation import Conversation, Message, MessageRole
from app.models.feedback import Feedback, FeedbackRating
from tests.retrieval_test_helpers import seed_retrieval_chunk


def seed_assistant_message(sqlite_session_factory):
    with sqlite_session_factory() as db:
        project, _, _ = seed_retrieval_chunk(db, "feedback", "alpha", [0.1] * 1024)
        conversation = Conversation(project_id=project.id)
        db.add(conversation)
        db.flush()
        message = Message(
            project_id=project.id,
            conversation_id=conversation.id,
            role=MessageRole.assistant,
            content="Answer",
        )
        db.add(message)
        db.commit()
        return project.id, conversation.id, message.id


def test_feedback_api_stores_useful_rating(api_client, sqlite_session_factory) -> None:
    """Feedback API should store useful/not_useful ratings for assistant messages."""

    project_id, conversation_id, message_id = seed_assistant_message(sqlite_session_factory)

    response = api_client.post(
        f"/api/projects/{project_id}/feedback",
        json={
            "conversation_id": str(conversation_id),
            "message_id": str(message_id),
            "rating": "useful",
            "comment": "Good citation",
        },
    )

    assert response.status_code == 201
    assert response.json()["rating"] == "useful"
    with sqlite_session_factory() as db:
        feedback = db.query(Feedback).one()
    assert feedback.rating == FeedbackRating.useful


def test_feedback_rejects_user_messages(api_client, sqlite_session_factory) -> None:
    """Feedback should only target assistant messages."""

    with sqlite_session_factory() as db:
        project, _, _ = seed_retrieval_chunk(db, "feedback-user", "alpha", [0.1] * 1024)
        conversation = Conversation(project_id=project.id)
        db.add(conversation)
        db.flush()
        message = Message(
            project_id=project.id,
            conversation_id=conversation.id,
            role=MessageRole.user,
            content="Question",
        )
        db.add(message)
        db.commit()
        project_id = project.id
        conversation_id = conversation.id
        message_id = message.id

    response = api_client.post(
        f"/api/projects/{project_id}/feedback",
        json={
            "conversation_id": str(conversation_id),
            "message_id": str(message_id),
            "rating": "useful",
        },
    )

    assert response.status_code == 400


def test_feedback_rejects_cross_project_message(api_client, sqlite_session_factory) -> None:
    """Feedback cannot target another project's assistant message."""

    project_id, _, _ = seed_assistant_message(sqlite_session_factory)
    other_project_id, conversation_id, message_id = seed_assistant_message(sqlite_session_factory)

    response = api_client.post(
        f"/api/projects/{project_id}/feedback",
        json={
            "conversation_id": str(conversation_id),
            "message_id": str(message_id),
            "rating": "not_useful",
        },
    )

    assert response.status_code == 404
    assert project_id != other_project_id
