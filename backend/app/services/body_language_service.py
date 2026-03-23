"""
Body Language Analysis Service

This service provides computer vision-based analysis of body language including:
- Posture detection and analysis
- Gesture recognition
- Facial expression analysis
- Eye contact estimation
"""

import cv2
import mediapipe as mp
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
import logging
import io
from PIL import Image

from app.models.speech import BodyLanguageAnalysis

logger = logging.getLogger(__name__)


class BodyLanguageAnalysisService:
    """Service for analyzing body language from video frames"""
    
    def __init__(self):
        # Initialize MediaPipe solutions
        self.mp_pose = mp.solutions.pose
        self.mp_hands = mp.solutions.hands
        self.mp_face_mesh = mp.solutions.face_mesh
        self.mp_face_detection = mp.solutions.face_detection
        
        # Initialize pose detector
        self.pose_detector = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
        # Initialize hand detector
        self.hand_detector = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
        # Initialize face mesh detector
        self.face_mesh_detector = self.mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
        logger.info("Body Language Analysis Service initialized")
    
    async def analyze_video_frames(
        self, 
        video_data: bytes, 
        frame_rate: int = 30,
        sample_rate: int = 5
    ) -> BodyLanguageAnalysis:
        """
        Analyze body language from video data
        
        Args:
            video_data: Raw video bytes
            frame_rate: Video frame rate
            sample_rate: Analyze every Nth frame (to reduce processing)
            
        Returns:
            BodyLanguageAnalysis with comprehensive body language metrics
        """
        try:
            # Extract frames from video
            frames = self._extract_frames_from_video(video_data, sample_rate)
            
            if not frames:
                logger.warning("No frames extracted from video")
                return self._get_default_analysis()
            
            # Analyze each frame
            posture_results = []
            gesture_results = []
            facial_results = []
            
            for frame in frames:
                # Analyze posture
                posture = self._analyze_posture(frame)
                if posture:
                    posture_results.append(posture)
                
                # Analyze gestures
                gestures = self._analyze_gestures(frame)
                if gestures:
                    gesture_results.append(gestures)
                
                # Analyze facial expressions
                facial = self._analyze_facial_expression(frame)
                if facial:
                    facial_results.append(facial)
            
            # Aggregate results
            posture_analysis = self._aggregate_posture_results(posture_results)
            gesture_analysis = self._aggregate_gesture_results(gesture_results)
            facial_analysis = self._aggregate_facial_results(facial_results)
            
            # Calculate overall confidence
            overall_confidence = self._calculate_overall_confidence(
                posture_analysis,
                gesture_analysis,
                facial_analysis
            )
            
            # Generate recommendations
            recommendations = self._generate_body_language_recommendations(
                posture_analysis,
                gesture_analysis,
                facial_analysis
            )
            
            return BodyLanguageAnalysis(
                posture=posture_analysis,
                facial_expression=facial_analysis,
                gestures=gesture_analysis,
                overall_confidence=overall_confidence,
                recommendations=recommendations
            )
            
        except Exception as e:
            logger.error(f"Body language analysis failed: {e}")
            return self._get_default_analysis()
    
    def _extract_frames_from_video(
        self, 
        video_data: bytes, 
        sample_rate: int = 5
    ) -> List[np.ndarray]:
        """Extract frames from video data"""
        try:
            # Save video data to temporary file
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
                temp_file.write(video_data)
                temp_file_path = temp_file.name
            
            # Open video with OpenCV
            cap = cv2.VideoCapture(temp_file_path)
            frames = []
            frame_count = 0
            
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Sample frames
                if frame_count % sample_rate == 0:
                    # Convert BGR to RGB
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frames.append(frame_rgb)
                
                frame_count += 1
            
            cap.release()
            
            # Clean up temp file
            import os
            os.unlink(temp_file_path)
            
            logger.info(f"Extracted {len(frames)} frames from video")
            return frames
            
        except Exception as e:
            logger.error(f"Frame extraction failed: {e}")
            return []
    
    def _analyze_posture(self, frame: np.ndarray) -> Optional[Dict[str, Any]]:
        """Analyze posture from a single frame"""
        try:
            # Process frame with pose detector
            results = self.pose_detector.process(frame)
            
            if not results.pose_landmarks:
                return None
            
            landmarks = results.pose_landmarks.landmark
            
            # Calculate shoulder position
            left_shoulder = landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER]
            right_shoulder = landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER]
            shoulder_y_avg = (left_shoulder.y + right_shoulder.y) / 2
            
            # Calculate head position
            nose = landmarks[self.mp_pose.PoseLandmark.NOSE]
            head_y = nose.y
            
            # Determine posture quality
            shoulder_level_diff = abs(left_shoulder.y - right_shoulder.y)
            is_shoulders_level = shoulder_level_diff < 0.05
            
            # Check if leaning forward (head significantly lower than shoulders)
            is_leaning_forward = head_y > shoulder_y_avg + 0.1
            
            # Check if slouching (shoulders too low)
            is_slouching = shoulder_y_avg > 0.6
            
            # Determine posture category
            if is_shoulders_level and not is_leaning_forward and not is_slouching:
                posture_category = "excellent"
                confidence = 0.9
            elif is_shoulders_level:
                posture_category = "good"
                confidence = 0.75
            else:
                posture_category = "needs_improvement"
                confidence = 0.5
            
            return {
                "confidence": confidence,
                "shoulder_position": "level" if is_shoulders_level else "uneven",
                "head_position": "forward" if is_leaning_forward else "upright",
                "is_slouching": is_slouching,
                "posture_quality": posture_category
            }
            
        except Exception as e:
            logger.error(f"Posture analysis failed: {e}")
            return None
    
    def _analyze_gestures(self, frame: np.ndarray) -> Optional[Dict[str, Any]]:
        """Analyze hand gestures from a single frame"""
        try:
            # Process frame with hand detector
            results = self.hand_detector.process(frame)
            
            if not results.multi_hand_landmarks:
                return {
                    "hands_detected": 0,
                    "hand_movement": 0.0,
                    "gesture_types": [],
                    "appropriateness": 0.5
                }
            
            hands_detected = len(results.multi_hand_landmarks)
            
            # Calculate hand movement (simplified)
            # In a real implementation, we'd track hand positions across frames
            hand_movement = 0.5  # Placeholder
            
            # Detect gesture types (simplified)
            gesture_types = []
            if hands_detected == 1:
                gesture_types.append("pointing")
            elif hands_detected == 2:
                gesture_types.append("descriptive")
            
            # Calculate appropriateness (placeholder)
            appropriateness = 0.8
            
            return {
                "hands_detected": hands_detected,
                "hand_movement": hand_movement,
                "gesture_types": gesture_types,
                "appropriateness": appropriateness
            }
            
        except Exception as e:
            logger.error(f"Gesture analysis failed: {e}")
            return None
    
    def _analyze_facial_expression(self, frame: np.ndarray) -> Optional[Dict[str, Any]]:
        """Analyze facial expressions from a single frame"""
        try:
            # Process frame with face mesh detector
            results = self.face_mesh_detector.process(frame)
            
            if not results.multi_face_landmarks:
                return None
            
            landmarks = results.multi_face_landmarks[0].landmark
            
            # Calculate engagement based on facial features
            # This is a simplified version - real implementation would use more sophisticated methods
            
            # Estimate eye openness (simplified)
            left_eye_top = landmarks[159]
            left_eye_bottom = landmarks[145]
            eye_openness = abs(left_eye_top.y - left_eye_bottom.y)
            
            # Estimate mouth openness (for speaking detection)
            upper_lip = landmarks[13]
            lower_lip = landmarks[14]
            mouth_openness = abs(upper_lip.y - lower_lip.y)
            
            # Calculate engagement score
            engagement = min(1.0, eye_openness * 10)  # Normalize
            
            # Estimate eye contact (looking at camera)
            # In real implementation, would use gaze estimation
            eye_contact = 0.7  # Placeholder
            
            # Detect expressions (simplified)
            expressions = []
            if mouth_openness > 0.02:
                expressions.append("speaking")
            if engagement > 0.7:
                expressions.append("engaged")
            else:
                expressions.append("neutral")
            
            return {
                "engagement": engagement,
                "eye_contact": eye_contact,
                "expressions": expressions,
                "eye_openness": eye_openness,
                "mouth_openness": mouth_openness
            }
            
        except Exception as e:
            logger.error(f"Facial expression analysis failed: {e}")
            return None
    
    def _aggregate_posture_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate posture results across frames"""
        if not results:
            return {
                "confidence": 0.5,
                "shoulderPosition": "unknown",
                "headPosition": "unknown"
            }
        
        # Calculate averages
        avg_confidence = np.mean([r["confidence"] for r in results])
        
        # Most common shoulder position
        shoulder_positions = [r["shoulder_position"] for r in results]
        most_common_shoulder = max(set(shoulder_positions), key=shoulder_positions.count)
        
        # Most common head position
        head_positions = [r["head_position"] for r in results]
        most_common_head = max(set(head_positions), key=head_positions.count)
        
        return {
            "confidence": float(avg_confidence),
            "shoulderPosition": most_common_shoulder,
            "headPosition": most_common_head
        }
    
    def _aggregate_gesture_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate gesture results across frames"""
        if not results:
            return {
                "handMovement": 0.0,
                "gestureTypes": [],
                "appropriateness": 0.5
            }
        
        # Calculate averages
        avg_hand_movement = np.mean([r["hand_movement"] for r in results])
        avg_appropriateness = np.mean([r["appropriateness"] for r in results])
        
        # Collect all gesture types
        all_gesture_types = []
        for r in results:
            all_gesture_types.extend(r["gesture_types"])
        
        # Get unique gesture types
        unique_gestures = list(set(all_gesture_types))
        
        return {
            "handMovement": float(avg_hand_movement),
            "gestureTypes": unique_gestures,
            "appropriateness": float(avg_appropriateness)
        }
    
    def _aggregate_facial_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate facial expression results across frames"""
        if not results:
            return {
                "engagement": 0.5,
                "eyeContact": 0.5,
                "expressions": ["neutral"]
            }
        
        # Calculate averages
        avg_engagement = np.mean([r["engagement"] for r in results])
        avg_eye_contact = np.mean([r["eye_contact"] for r in results])
        
        # Collect all expressions
        all_expressions = []
        for r in results:
            all_expressions.extend(r["expressions"])
        
        # Get most common expressions
        unique_expressions = list(set(all_expressions))
        
        return {
            "engagement": float(avg_engagement),
            "eyeContact": float(avg_eye_contact),
            "expressions": unique_expressions
        }
    
    def _calculate_overall_confidence(
        self,
        posture: Dict[str, Any],
        gestures: Dict[str, Any],
        facial: Dict[str, Any]
    ) -> float:
        """Calculate overall body language confidence score"""
        # Weighted average of different components
        posture_score = posture.get("confidence", 0.5)
        gesture_score = gestures.get("appropriateness", 0.5)
        facial_score = (facial.get("engagement", 0.5) + facial.get("eyeContact", 0.5)) / 2
        
        overall = (
            posture_score * 0.35 +
            gesture_score * 0.30 +
            facial_score * 0.35
        )
        
        return float(overall)
    
    def _generate_body_language_recommendations(
        self,
        posture: Dict[str, Any],
        gestures: Dict[str, Any],
        facial: Dict[str, Any]
    ) -> List[str]:
        """Generate personalized body language recommendations"""
        recommendations = []
        
        # Posture recommendations
        if posture.get("confidence", 1.0) < 0.7:
            if posture.get("shoulderPosition") == "uneven":
                recommendations.append("Keep your shoulders level and relaxed")
            if posture.get("headPosition") == "forward":
                recommendations.append("Avoid leaning forward - maintain an upright posture")
        
        # Gesture recommendations
        if gestures.get("handMovement", 0) < 0.3:
            recommendations.append("Use more hand gestures to emphasize your points")
        elif gestures.get("handMovement", 0) > 0.8:
            recommendations.append("Reduce excessive hand movements for a calmer presence")
        
        # Facial expression recommendations
        if facial.get("engagement", 1.0) < 0.6:
            recommendations.append("Show more facial engagement and expression")
        if facial.get("eyeContact", 1.0) < 0.6:
            recommendations.append("Maintain better eye contact with the camera/audience")
        
        if not recommendations:
            recommendations.append("Excellent body language! Keep it up.")
        
        return recommendations
    
    def _get_default_analysis(self) -> BodyLanguageAnalysis:
        """Return default body language analysis when processing fails"""
        return BodyLanguageAnalysis(
            posture={
                "confidence": 0.5,
                "shoulderPosition": "unknown",
                "headPosition": "unknown"
            },
            facial_expression={
                "engagement": 0.5,
                "eyeContact": 0.5,
                "expressions": ["neutral"]
            },
            gestures={
                "handMovement": 0.5,
                "gestureTypes": [],
                "appropriateness": 0.5
            },
            overall_confidence=0.5,
            recommendations=["Unable to analyze body language from video"]
        )
    
    def __del__(self):
        """Cleanup MediaPipe resources"""
        try:
            self.pose_detector.close()
            self.hand_detector.close()
            self.face_mesh_detector.close()
        except Exception:
            pass
