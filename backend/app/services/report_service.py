"""
Report Service - Generates comprehensive performance reports for sessions

This service handles:
- Comprehensive session report generation for each participant
- Report generation with all analysis data
- Session history retrieval and formatting
- Report export functionality (JSON, PDF-ready format)
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import json

from app.models.session import Session, SessionStatus
from app.models.speech import SpeechAnalysis, ProsodyMetrics
from app.services.session_service import SessionService
from app.services.advanced_speech_service import AdvancedSpeechAnalysisService
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class ReportService:
    """Service for generating comprehensive performance reports"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.session_service = SessionService(db)
        self.speech_service = AdvancedSpeechAnalysisService()
        logger.info("Report Service initialized")
    
    async def generate_participant_report(
        self,
        session_id: str,
        participant_id: str
    ) -> Dict[str, Any]:
        """
        Generate comprehensive performance report for a participant
        
        Args:
            session_id: ID of the session
            participant_id: ID of the participant
            
        Returns:
            Comprehensive report dictionary
        """
        # Get session data
        session_data = await self.session_service.get_session_with_analyses(session_id)
        if not session_data:
            raise ValueError(f"Session {session_id} not found")
        
        session = session_data["session"]
        
        # Get all speech analyses for this participant
        analyses = await self.db.speech_analyses.find({
            "session_id": session_id,
            "participant_id": participant_id
        }).sort("timestamp", 1).to_list(None)
        
        # Calculate aggregated metrics
        aggregated_metrics = await self.session_service.calculate_aggregated_metrics(
            session_id, participant_id
        )
        
        # Calculate speech quality scores
        quality_scores = self._calculate_quality_scores(analyses)
        
        # Generate insights and recommendations
        insights = self._generate_insights(analyses, aggregated_metrics)
        recommendations = self._generate_recommendations(analyses, aggregated_metrics, quality_scores)
        
        # Get transcripts for this participant
        participant_transcripts = [
            t for t in session.transcripts
            if t.participant_id == participant_id
        ]
        
        # Build comprehensive report
        report = {
            "report_id": f"{session_id}_{participant_id}_{int(datetime.utcnow().timestamp())}",
            "generated_at": datetime.utcnow().isoformat(),
            "session_info": {
                "session_id": session_id,
                "room_id": session.room_id,
                "start_time": session.start_time.isoformat(),
                "end_time": session.end_time.isoformat() if session.end_time else None,
                "duration_minutes": self._calculate_session_duration(session),
                "status": session.status
            },
            "participant_info": {
                "participant_id": participant_id,
                "total_speeches": len(analyses),
                "total_transcripts": len(participant_transcripts)
            },
            "performance_summary": {
                "overall_score": quality_scores.get("overall_score", 0),
                "grade": quality_scores.get("grade", "N/A"),
                "category_scores": quality_scores.get("category_scores", {}),
                "aggregated_metrics": aggregated_metrics
            },
            "detailed_analysis": {
                "speech_breakdown": self._create_speech_breakdown(analyses),
                "prosody_trends": self._analyze_prosody_trends(analyses),
                "improvement_areas": self._identify_improvement_areas(analyses, aggregated_metrics)
            },
            "insights": insights,
            "recommendations": recommendations,
            "transcripts": [
                {
                    "text": t.text,
                    "timestamp": t.timestamp.isoformat(),
                    "confidence": t.confidence
                }
                for t in participant_transcripts
            ]
        }
        
        # Store report in database
        await self.db.reports.insert_one(report)
        
        logger.info(f"Generated report for participant {participant_id} in session {session_id}")
        return report
    
    async def generate_session_report(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Generate comprehensive report for entire session (all participants)
        
        Args:
            session_id: ID of the session
            
        Returns:
            Session-wide report dictionary
        """
        # Get session data
        session_data = await self.session_service.get_session_with_analyses(session_id)
        if not session_data:
            raise ValueError(f"Session {session_id} not found")
        
        session = session_data["session"]
        
        # Generate reports for each participant
        participant_reports = []
        for participant_id in session.participants:
            try:
                report = await self.generate_participant_report(session_id, participant_id)
                participant_reports.append(report)
            except Exception as e:
                logger.error(f"Failed to generate report for participant {participant_id}: {e}")
        
        # Calculate session-wide statistics
        session_stats = self._calculate_session_statistics(participant_reports)
        
        # Build session report
        session_report = {
            "report_id": f"session_{session_id}_{int(datetime.utcnow().timestamp())}",
            "generated_at": datetime.utcnow().isoformat(),
            "session_info": {
                "session_id": session_id,
                "room_id": session.room_id,
                "start_time": session.start_time.isoformat(),
                "end_time": session.end_time.isoformat() if session.end_time else None,
                "duration_minutes": self._calculate_session_duration(session),
                "status": session.status,
                "participant_count": len(session.participants)
            },
            "session_statistics": session_stats,
            "participant_reports": participant_reports,
            "ai_interactions": [
                {
                    "participant_id": ai.participant_id,
                    "timestamp": ai.timestamp.isoformat(),
                    "response_time": ai.response_time
                }
                for ai in session.ai_interactions
            ]
        }
        
        # Store session report
        await self.db.session_reports.insert_one(session_report)
        
        logger.info(f"Generated session report for session {session_id}")
        return session_report
    
    async def get_participant_history(
        self,
        participant_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get session history for a participant with summary metrics
        
        Args:
            participant_id: ID of the participant
            limit: Maximum number of sessions to return
            
        Returns:
            List of session summaries
        """
        # Get participant sessions
        sessions = await self.session_service.get_participant_sessions(
            participant_id, limit, SessionStatus.COMPLETED
        )
        
        history = []
        for session in sessions:
            # Get aggregated metrics for this session
            try:
                metrics = await self.session_service.calculate_aggregated_metrics(
                    session.id, participant_id
                )
                
                # Get quality score if available
                analyses = await self.db.speech_analyses.find({
                    "session_id": session.id,
                    "participant_id": participant_id
                }).to_list(None)
                
                quality_scores = self._calculate_quality_scores(analyses)
                
                history.append({
                    "session_id": session.id,
                    "room_id": session.room_id,
                    "start_time": session.start_time.isoformat(),
                    "end_time": session.end_time.isoformat() if session.end_time else None,
                    "duration_minutes": self._calculate_session_duration(session),
                    "metrics_summary": {
                        "total_speeches": metrics.get("total_speeches", 0),
                        "total_words": metrics.get("total_words", 0),
                        "average_wpm": metrics.get("average_wpm", 0),
                        "overall_score": quality_scores.get("overall_score", 0),
                        "grade": quality_scores.get("grade", "N/A")
                    }
                })
            except Exception as e:
                logger.error(f"Failed to get metrics for session {session.id}: {e}")
                continue
        
        return history
    
    async def export_report(
        self,
        report_id: str,
        format: str = "json"
    ) -> Dict[str, Any]:
        """
        Export a report in specified format
        
        Args:
            report_id: ID of the report to export
            format: Export format (json, pdf-ready)
            
        Returns:
            Exported report data
        """
        # Get report from database
        report = await self.db.reports.find_one({"report_id": report_id})
        if not report:
            # Try session reports
            report = await self.db.session_reports.find_one({"report_id": report_id})
        
        if not report:
            raise ValueError(f"Report {report_id} not found")
        
        if format == "json":
            # Remove MongoDB _id field
            report.pop("_id", None)
            return report
        
        elif format == "pdf-ready":
            # Format for PDF generation (simplified structure)
            return self._format_for_pdf(report)
        
        else:
            raise ValueError(f"Unsupported export format: {format}")
    
    def _calculate_session_duration(self, session: Session) -> float:
        """Calculate session duration in minutes"""
        if not session.end_time:
            return 0.0
        
        duration = (session.end_time - session.start_time).total_seconds() / 60
        return round(duration, 2)
    
    def _calculate_quality_scores(self, analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate overall quality scores from analyses"""
        if not analyses:
            return {
                "overall_score": 0,
                "grade": "N/A",
                "category_scores": {}
            }
        
        # Calculate average scores across all speeches
        all_scores = []
        category_totals = {
            "pitch_quality": [],
            "voice_quality": [],
            "fluency": [],
            "pace": []
        }
        
        for analysis in analyses:
            prosody = analysis.get("prosody_metrics", {})
            
            # Calculate scores for this speech
            pitch_score = self._score_pitch(prosody)
            voice_score = self._score_voice_quality(prosody)
            fluency_score = self._score_fluency(prosody)
            pace_score = self._score_pace(prosody)
            
            category_totals["pitch_quality"].append(pitch_score)
            category_totals["voice_quality"].append(voice_score)
            category_totals["fluency"].append(fluency_score)
            category_totals["pace"].append(pace_score)
            
            overall = (pitch_score * 0.25 + voice_score * 0.30 + 
                      fluency_score * 0.25 + pace_score * 0.20)
            all_scores.append(overall)
        
        # Calculate averages
        avg_overall = sum(all_scores) / len(all_scores)
        category_scores = {
            category: round(sum(scores) / len(scores), 2)
            for category, scores in category_totals.items()
        }
        
        return {
            "overall_score": round(avg_overall, 2),
            "grade": self._score_to_grade(avg_overall),
            "category_scores": category_scores
        }
    
    def _score_pitch(self, prosody: Dict[str, Any]) -> float:
        """Score pitch quality"""
        pitch_range = prosody.get("pitch_range", 0)
        if pitch_range < 30:
            return 60
        elif pitch_range > 150:
            return 70
        return 100
    
    def _score_voice_quality(self, prosody: Dict[str, Any]) -> float:
        """Score voice quality"""
        score = 100
        jitter = prosody.get("jitter", 0)
        shimmer = prosody.get("shimmer", 0)
        hnr = prosody.get("harmonic_to_noise_ratio", 15)
        
        if jitter > 0.02:
            score -= 20
        if shimmer > 0.08:
            score -= 20
        if hnr < 10:
            score -= 30
        
        return max(0, score)
    
    def _score_fluency(self, prosody: Dict[str, Any]) -> float:
        """Score fluency"""
        score = 100
        filler_count = prosody.get("filler_word_count", 0)
        avg_pause = prosody.get("average_pause_length", 0)
        
        if filler_count > 5:
            score -= min(50, filler_count * 5)
        if avg_pause > 1.0:
            score -= 20
        
        return max(0, score)
    
    def _score_pace(self, prosody: Dict[str, Any]) -> float:
        """Score speaking pace"""
        wpm = prosody.get("words_per_minute", 150)
        if wpm < 100:
            return 60
        elif wpm > 200:
            return 70
        elif wpm < 140 or wpm > 180:
            return 85
        return 100
    
    def _score_to_grade(self, score: float) -> str:
        """Convert score to letter grade"""
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        return "F"
    
    def _create_speech_breakdown(self, analyses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create breakdown of individual speeches"""
        breakdown = []
        for i, analysis in enumerate(analyses, 1):
            prosody = analysis.get("prosody_metrics", {})
            breakdown.append({
                "speech_number": i,
                "timestamp": analysis.get("timestamp"),
                "duration": prosody.get("duration", 0),
                "word_count": len(analysis.get("transcript", "").split()),
                "wpm": prosody.get("words_per_minute", 0),
                "filler_words": prosody.get("filler_word_count", 0),
                "average_pitch": prosody.get("average_pitch", 0)
            })
        return breakdown
    
    def _analyze_prosody_trends(self, analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze trends in prosody metrics over time"""
        if not analyses:
            return {}
        
        wpm_values = []
        pitch_values = []
        filler_values = []
        
        for analysis in analyses:
            prosody = analysis.get("prosody_metrics", {})
            wpm_values.append(prosody.get("words_per_minute", 0))
            pitch_values.append(prosody.get("average_pitch", 0))
            filler_values.append(prosody.get("filler_word_count", 0))
        
        return {
            "wpm_trend": self._calculate_trend(wpm_values),
            "pitch_trend": self._calculate_trend(pitch_values),
            "filler_trend": self._calculate_trend(filler_values),
            "wpm_range": {"min": min(wpm_values), "max": max(wpm_values)},
            "pitch_range": {"min": min(pitch_values), "max": max(pitch_values)}
        }
    
    def _calculate_trend(self, values: List[float]) -> str:
        """Calculate trend direction"""
        if len(values) < 2:
            return "stable"
        
        first_half = sum(values[:len(values)//2]) / (len(values)//2)
        second_half = sum(values[len(values)//2:]) / (len(values) - len(values)//2)
        
        diff_percent = ((second_half - first_half) / first_half * 100) if first_half > 0 else 0
        
        if diff_percent > 10:
            return "improving"
        elif diff_percent < -10:
            return "declining"
        return "stable"
    
    def _identify_improvement_areas(
        self,
        analyses: List[Dict[str, Any]],
        aggregated_metrics: Dict[str, Any]
    ) -> List[str]:
        """Identify areas needing improvement"""
        areas = []
        
        avg_wpm = aggregated_metrics.get("average_wpm", 0)
        if avg_wpm < 120:
            areas.append("Speaking pace is too slow")
        elif avg_wpm > 200:
            areas.append("Speaking pace is too fast")
        
        filler_per_min = aggregated_metrics.get("filler_words_per_minute", 0)
        if filler_per_min > 3:
            areas.append("High frequency of filler words")
        
        if analyses:
            avg_pitch_range = sum(
                a.get("prosody_metrics", {}).get("pitch_range", 0)
                for a in analyses
            ) / len(analyses)
            
            if avg_pitch_range < 30:
                areas.append("Monotone delivery - increase pitch variation")
        
        return areas if areas else ["No major areas of concern - keep practicing!"]
    
    def _generate_insights(
        self,
        analyses: List[Dict[str, Any]],
        aggregated_metrics: Dict[str, Any]
    ) -> List[str]:
        """Generate insights from analysis data"""
        insights = []
        
        total_speeches = aggregated_metrics.get("total_speeches", 0)
        total_duration = aggregated_metrics.get("total_duration", 0)
        
        insights.append(
            f"Delivered {total_speeches} speeches totaling {total_duration:.1f} seconds"
        )
        
        avg_wpm = aggregated_metrics.get("average_wpm", 0)
        if 140 <= avg_wpm <= 180:
            insights.append(f"Speaking pace ({avg_wpm:.0f} WPM) is in the ideal range")
        
        filler_per_min = aggregated_metrics.get("filler_words_per_minute", 0)
        if filler_per_min < 2:
            insights.append("Excellent fluency with minimal filler words")
        
        return insights
    
    def _generate_recommendations(
        self,
        analyses: List[Dict[str, Any]],
        aggregated_metrics: Dict[str, Any],
        quality_scores: Dict[str, Any]
    ) -> List[str]:
        """Generate personalized recommendations"""
        recommendations = []
        
        category_scores = quality_scores.get("category_scores", {})
        
        if category_scores.get("pitch_quality", 100) < 80:
            recommendations.append(
                "Practice varying your pitch to sound more engaging"
            )
        
        if category_scores.get("voice_quality", 100) < 80:
            recommendations.append(
                "Work on voice stability through breath control exercises"
            )
        
        if category_scores.get("fluency", 100) < 80:
            recommendations.append(
                "Reduce filler words by pausing instead"
            )
        
        if category_scores.get("pace", 100) < 80:
            avg_wpm = aggregated_metrics.get("average_wpm", 0)
            if avg_wpm < 140:
                recommendations.append("Increase your speaking pace")
            elif avg_wpm > 180:
                recommendations.append("Slow down your speaking pace")
        
        if not recommendations:
            recommendations.append("Excellent performance! Continue practicing to maintain your skills")
        
        return recommendations
    
    def _calculate_session_statistics(
        self,
        participant_reports: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calculate session-wide statistics"""
        if not participant_reports:
            return {}
        
        total_speeches = sum(
            r["participant_info"]["total_speeches"]
            for r in participant_reports
        )
        
        avg_score = sum(
            r["performance_summary"]["overall_score"]
            for r in participant_reports
        ) / len(participant_reports)
        
        return {
            "total_participants": len(participant_reports),
            "total_speeches": total_speeches,
            "average_session_score": round(avg_score, 2),
            "participant_grades": [
                {
                    "participant_id": r["participant_info"]["participant_id"],
                    "grade": r["performance_summary"]["grade"],
                    "score": r["performance_summary"]["overall_score"]
                }
                for r in participant_reports
            ]
        }
    
    def _format_for_pdf(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """Format report for PDF generation"""
        # Simplified structure optimized for PDF rendering
        return {
            "title": "BreakThrough Performance Report",
            "generated_at": report.get("generated_at"),
            "session_info": report.get("session_info"),
            "participant_info": report.get("participant_info"),
            "summary": {
                "overall_score": report.get("performance_summary", {}).get("overall_score"),
                "grade": report.get("performance_summary", {}).get("grade"),
                "key_metrics": report.get("performance_summary", {}).get("aggregated_metrics")
            },
            "insights": report.get("insights", []),
            "recommendations": report.get("recommendations", []),
            "detailed_breakdown": report.get("detailed_analysis", {}).get("speech_breakdown", [])
        }
