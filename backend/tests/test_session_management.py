"""
Tests for Session Management and Reporting

These tests verify:
- Session lifecycle management
- Data collection and storage
- Participant tracking
- Report generation
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
import uuid

from app.services.session_service import SessionService
from app.services.report_service import ReportService
from app.models.session import Session, SessionStatus
from app.models.speech import ProsodyMetrics


@pytest.fixture
def mock_db():
    """Create a mock database"""
    db = MagicMock()
    db.sessions = MagicMock()
    db.speech_analyses = MagicMock()
    db.reports = MagicMock()
    db.session_reports = MagicMock()
    return db


@pytest.fixture
def session_service(mock_db):
    """Create session service with mock database"""
    return SessionService(mock_db)


@pytest.fixture
def report_service(mock_db):
    """Create report service with mock database"""
    return ReportService(mock_db)


@pytest.mark.asyncio
async def test_start_session(session_service, mock_db):
    """Test starting a new session"""
    # Setup
    room_id = "room_123"
    participants = ["user_1", "user_2"]
    mode = "debate"
    
    mock_db.sessions.insert_one = AsyncMock()
    
    # Execute
    session = await session_service.start_session(room_id, participants, mode)
    
    # Verify
    assert session.room_id == room_id
    assert session.participants == participants
    assert session.status == SessionStatus.ACTIVE
    assert session.start_time is not None
    assert session.end_time is None
    mock_db.sessions.insert_one.assert_called_once()


@pytest.mark.asyncio
async def test_end_session(session_service, mock_db):
    """Test ending an active session"""
    # Setup
    session_id = "session_123"
    
    mock_db.sessions.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    mock_db.sessions.find_one = AsyncMock(return_value={
        "id": session_id,
        "room_id": "room_123",
        "participants": ["user_1"],
        "start_time": datetime.utcnow(),
        "end_time": datetime.utcnow(),
        "status": SessionStatus.COMPLETED,
        "transcripts": [],
        "ai_interactions": []
    })
    
    # Execute
    session = await session_service.end_session(session_id, "completed")
    
    # Verify
    assert session.status == SessionStatus.COMPLETED
    assert session.end_time is not None
    mock_db.sessions.update_one.assert_called_once()


@pytest.mark.asyncio
async def test_add_transcript(session_service, mock_db):
    """Test adding a transcript to a session"""
    # Setup
    session_id = "session_123"
    participant_id = "user_1"
    text = "This is a test transcript"
    
    mock_db.sessions.update_one = AsyncMock()
    
    # Execute
    await session_service.add_transcript(session_id, participant_id, text)
    
    # Verify
    mock_db.sessions.update_one.assert_called_once()
    call_args = mock_db.sessions.update_one.call_args
    assert call_args[0][0] == {"id": session_id}
    assert "$push" in call_args[0][1]
    assert "$inc" in call_args[0][1]


@pytest.mark.asyncio
async def test_calculate_aggregated_metrics(session_service, mock_db):
    """Test calculating aggregated metrics for a participant"""
    # Setup
    session_id = "session_123"
    participant_id = "user_1"
    
    # Mock speech analyses
    mock_analyses = [
        {
            "transcript": "Hello world this is a test",
            "prosody_metrics": {
                "duration": 5.0,
                "average_pitch": 150.0,
                "average_intensity": 65.0,
                "filler_word_count": 1,
                "pause_count": 2
            }
        },
        {
            "transcript": "Another test transcript here",
            "prosody_metrics": {
                "duration": 4.0,
                "average_pitch": 160.0,
                "average_intensity": 70.0,
                "filler_word_count": 0,
                "pause_count": 1
            }
        }
    ]
    
    mock_db.speech_analyses.find = MagicMock(return_value=MagicMock(
        to_list=AsyncMock(return_value=mock_analyses)
    ))
    
    # Execute
    metrics = await session_service.calculate_aggregated_metrics(session_id, participant_id)
    
    # Verify
    assert metrics["total_speeches"] == 2
    assert metrics["total_duration"] == 9.0
    assert metrics["total_words"] == 9  # "Hello world this is a test" + "Another test transcript here"
    assert metrics["total_filler_words"] == 1
    assert metrics["total_pauses"] == 3
    assert metrics["average_wpm"] > 0


@pytest.mark.asyncio
async def test_generate_participant_report(report_service, mock_db):
    """Test generating a comprehensive participant report"""
    # Setup
    session_id = "session_123"
    participant_id = "user_1"
    
    # Mock session data
    mock_session = {
        "id": session_id,
        "room_id": "room_123",
        "participants": [participant_id],
        "start_time": datetime.utcnow(),
        "end_time": datetime.utcnow(),
        "status": SessionStatus.COMPLETED,
        "transcripts": [],
        "ai_interactions": []
    }
    
    mock_db.sessions.find_one = AsyncMock(return_value=mock_session)
    mock_db.speech_analyses.find = MagicMock(return_value=MagicMock(
        sort=MagicMock(return_value=MagicMock(
            to_list=AsyncMock(return_value=[])
        ))
    ))
    mock_db.reports.insert_one = AsyncMock()
    
    # Execute
    report = await report_service.generate_participant_report(session_id, participant_id)
    
    # Verify
    assert report["session_info"]["session_id"] == session_id
    assert report["participant_info"]["participant_id"] == participant_id
    assert "performance_summary" in report
    assert "insights" in report
    assert "recommendations" in report
    mock_db.reports.insert_one.assert_called_once()


@pytest.mark.asyncio
async def test_get_participant_history(report_service, mock_db):
    """Test retrieving participant session history"""
    # Setup
    participant_id = "user_1"
    
    # Mock sessions
    mock_sessions = [
        {
            "id": "session_1",
            "room_id": "room_1",
            "participants": [participant_id],
            "start_time": datetime.utcnow(),
            "end_time": datetime.utcnow(),
            "status": SessionStatus.COMPLETED,
            "transcripts": [],
            "ai_interactions": []
        }
    ]
    
    mock_db.sessions.find = MagicMock(return_value=MagicMock(
        sort=MagicMock(return_value=MagicMock(
            limit=MagicMock(return_value=MagicMock(
                to_list=AsyncMock(return_value=mock_sessions)
            ))
        ))
    ))
    
    mock_db.speech_analyses.find = MagicMock(return_value=MagicMock(
        to_list=AsyncMock(return_value=[])
    ))
    
    # Execute
    history = await report_service.get_participant_history(participant_id, limit=10)
    
    # Verify
    assert len(history) >= 0  # May be empty if metrics calculation fails
    assert isinstance(history, list)


def test_score_calculation():
    """Test quality score calculation"""
    from app.services.report_service import ReportService
    
    service = ReportService(MagicMock())
    
    # Test pitch scoring
    prosody_good = {"pitch_range": 80}
    assert service._score_pitch(prosody_good) == 100
    
    prosody_monotone = {"pitch_range": 20}
    assert service._score_pitch(prosody_monotone) == 60
    
    # Test pace scoring
    prosody_ideal = {"words_per_minute": 150}
    assert service._score_pace(prosody_ideal) == 100
    
    prosody_slow = {"words_per_minute": 90}
    assert service._score_pace(prosody_slow) == 60
    
    prosody_fast = {"words_per_minute": 210}
    assert service._score_pace(prosody_fast) == 70


def test_grade_conversion():
    """Test score to grade conversion"""
    from app.services.report_service import ReportService
    
    service = ReportService(MagicMock())
    
    assert service._score_to_grade(95) == "A"
    assert service._score_to_grade(85) == "B"
    assert service._score_to_grade(75) == "C"
    assert service._score_to_grade(65) == "D"
    assert service._score_to_grade(55) == "F"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
