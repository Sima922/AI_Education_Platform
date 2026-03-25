// Exam proctoring functionality - camera, microphone, and tab monitoring
class ExamProctoring {
    constructor(sessionId) {
        this.sessionId = sessionId;
        this.videoStream = null;
        this.audioStream = null;
        this.tabSwitchCount = 0;
        this.fullscreenExitCount = 0;
        this.faceDetectionInterval = null;
        this.isMonitoring = false;
        this.faceDetectionEnabled = false;
    }

    // Initialize proctoring checks
    async initProctoringChecks() {
        try {
            // Request camera and microphone access
            await this.requestMediaAccess();
            
            // Set up event listeners
            this.setupEventListeners();
            
            // Start periodic checks
            this.startPeriodicChecks();
            
            // Send initial system check to server
            await this.sendProctoringEvent('system_check', { status: 'initialized' });
            
            return true;
        } catch (error) {
            console.error('Proctoring initialization failed:', error);
            await this.sendProctoringEvent('no_webcam', { error: error.message });
            return false;
        }
    }

    // Request camera and microphone access
    async requestMediaAccess() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                video: true,
                audio: true
            });
            
            this.videoStream = stream;
            this.audioStream = stream;
            
            // Display camera feed for user verification
            const videoElement = document.getElementById('camera-preview');
            if (videoElement) {
                videoElement.srcObject = stream;
            }
            
            // Update status
            document.getElementById('camera-status').textContent = 'Camera access granted';
            document.getElementById('mic-status').textContent = 'Microphone access granted';
            
            return true;
        } catch (error) {
            console.error('Media access error:', error);
            document.getElementById('camera-status').textContent = 'Camera access denied';
            document.getElementById('mic-status').textContent = 'Microphone access denied';
            
            throw error;
        }
    }

    // Set up event listeners for tab switching and fullscreen changes
    setupEventListeners() {
        // Tab visibility change
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.handleTabSwitch();
            }
        });

        // Fullscreen change
        document.addEventListener('fullscreenchange', () => {
            if (!document.fullscreenElement) {
                this.handleFullscreenExit();
            }
        });

        // Window blur (potential tab switch or window change)
        window.addEventListener('blur', () => {
            this.handlePotentialTabSwitch();
        });

        // Beforeunload (user trying to leave)
        window.addEventListener('beforeunload', (e) => {
            if (this.isMonitoring) {
                e.preventDefault();
                e.returnValue = 'Are you sure you want to leave? Your exam may be terminated.';
                return e.returnValue;
            }
        });
    }

    // Handle tab switching
    handleTabSwitch() {
        this.tabSwitchCount++;
        this.sendProctoringEvent('tab_switch', { count: this.tabSwitchCount });
        
        // Show warning to user
        this.showWarning('Tab switch detected. Repeated tab switching may result in exam termination.');
    }

    // Handle fullscreen exit
    handleFullscreenExit() {
        this.fullscreenExitCount++;
        this.sendProctoringEvent('fullscreen_exit', { count: this.fullscreenExitCount });
        
        // Show warning
        this.showWarning('Fullscreen exited. Please return to fullscreen mode to continue your exam.');
        
        // Try to re-enter fullscreen
        this.requestFullscreen();
    }

    // Handle potential tab switch (window blur)
    handlePotentialTabSwitch() {
        // Debounce this check to avoid false positives
        setTimeout(() => {
            if (!document.hidden) return;
            this.handleTabSwitch();
        }, 100);
    }

    // Request fullscreen mode
    requestFullscreen() {
        const elem = document.documentElement;
        if (elem.requestFullscreen) {
            elem.requestFullscreen().catch(err => {
                console.error('Fullscreen error:', err);
            });
        }
    }

    // Start periodic checks (face detection, audio monitoring)
    startPeriodicChecks() {
        this.isMonitoring = true;
        
        // Check for face every 5 seconds
        this.faceDetectionInterval = setInterval(() => {
            this.checkFaceVisibility();
        }, 5000);
        
        // Start audio monitoring (simplified)
        this.startAudioMonitoring();
    }

    // Check if face is visible in camera
    async checkFaceVisibility() {
        if (!this.faceDetectionEnabled) return;
        
        // This is a simplified version - in a real implementation, you'd use
        // a face detection library like face-api.js or similar
        
        const video = document.getElementById('camera-preview');
        if (!video || !this.videoStream) return;
        
        // Simulate face detection - in a real implementation, this would
        // use computer vision to detect faces
        const hasFace = Math.random() > 0.1; // 90% chance of detecting face
        
        if (!hasFace) {
            this.sendProctoringEvent('face_not_visible', { timestamp: Date.now() });
            this.showWarning('Face not detected. Please ensure your face is visible to the camera.');
        }
    }

    // Start audio monitoring
    startAudioMonitoring() {
        if (!this.audioStream) return;
        
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const source = audioContext.createMediaStreamSource(this.audioStream);
        const analyser = audioContext.createAnalyser();
        source.connect(analyser);
        
        const dataArray = new Uint8Array(analyser.frequencyBinCount);
        
        setInterval(() => {
            analyser.getByteFrequencyData(dataArray);
            
            // Calculate volume (simplified)
            let sum = 0;
            for (let i = 0; i < dataArray.length; i++) {
                sum += dataArray[i];
            }
            const average = sum / dataArray.length;
            
            // If volume is above threshold, assume audio is detected
            if (average > 10) {
                this.sendProctoringEvent('audio_detected', { volume: average });
            }
        }, 1000);
    }

    // Send proctoring event to server
    async sendProctoringEvent(eventType, details = {}) {
        try {
            const response = await fetch('/api/exam/proctoring-event/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    event_type: eventType,
                    details: details,
                    timestamp: new Date().toISOString()
                })
            });
            
            if (!response.ok) {
                console.error('Failed to send proctoring event');
            }
        } catch (error) {
            console.error('Error sending proctoring event:', error);
        }
    }

    // Show warning to user
    showWarning(message) {
        // Create or update warning element
        let warningElement = document.getElementById('proctoring-warning');
        if (!warningElement) {
            warningElement = document.createElement('div');
            warningElement.id = 'proctoring-warning';
            warningElement.style.cssText = `
                position: fixed;
                top: 20px;
                left: 50%;
                transform: translateX(-50%);
                background-color: #ffcc00;
                color: #000;
                padding: 10px 20px;
                border-radius: 5px;
                z-index: 10000;
                box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            `;
            document.body.appendChild(warningElement);
        }
        
        warningElement.textContent = message;
        
        // Auto-hide after 5 seconds
        setTimeout(() => {
            warningElement.style.display = 'none';
        }, 5000);
    }

    // Get CSRF token
    getCSRFToken() {
        const cookieValue = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrftoken='))
            ?.split('=')[1];
        return cookieValue || '';
    }

    // Stop proctoring
    stopProctoring() {
        this.isMonitoring = false;
        
        // Clear intervals
        if (this.faceDetectionInterval) {
            clearInterval(this.faceDetectionInterval);
        }
        
        // Stop media streams
        if (this.videoStream) {
            this.videoStream.getTracks().forEach(track => track.stop());
        }
    }
}

// Initialize proctoring when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Check if we're on an exam page
    const sessionIdElement = document.querySelector('[data-session-id]');
    if (sessionIdElement) {
        const sessionId = sessionIdElement.dataset.sessionId;
        window.examProctor = new ExamProctoring(sessionId);
    }
});

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ExamProctoring;
}