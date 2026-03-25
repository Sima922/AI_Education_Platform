// Exam timer functionality
class ExamTimer {
    constructor(timeLimitMinutes, sessionId) {
        this.timeLimitMinutes = timeLimitMinutes;
        this.sessionId = sessionId;
        this.timeRemaining = timeLimitMinutes * 60; // in seconds
        this.timerInterval = null;
        this.isRunning = false;
        this.warningThreshold = 300; // 5 minutes warning
        this.warningShown = false;
    }

    // Start the timer
    start() {
        if (this.isRunning) return;
        
        this.isRunning = true;
        this.startTime = Date.now();
        
        // Load saved time if available
        this.loadSavedTime();
        
        // Start the timer interval
        this.timerInterval = setInterval(() => {
            this.tick();
        }, 1000);
        
        // Auto-save time every 30 seconds
        this.autoSaveInterval = setInterval(() => {
            this.saveTime();
        }, 30000);
    }

    // Timer tick
    tick() {
        this.timeRemaining--;
        
        // Update display
        this.updateDisplay();
        
        // Check for warnings
        this.checkWarnings();
        
        // Check if time is up
        if (this.timeRemaining <= 0) {
            this.timeUp();
        }
    }

    // Update timer display
    updateDisplay() {
        const timerElement = document.getElementById('exam-timer');
        if (timerElement) {
            const minutes = Math.floor(this.timeRemaining / 60);
            const seconds = this.timeRemaining % 60;
            timerElement.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
            
            // Change color when time is running low
            if (this.timeRemaining < 60) {
                timerElement.style.color = '#ff0000';
                timerElement.classList.add('pulse');
            } else if (this.timeRemaining < this.warningThreshold) {
                timerElement.style.color = '#ff9900';
            }
        }
    }

    // Check for warnings
    checkWarnings() {
        // Show 5-minute warning
        if (this.timeRemaining <= this.warningThreshold && !this.warningShown) {
            this.showWarning('You have 5 minutes remaining!');
            this.warningShown = true;
        }
        
        // Show 1-minute warning
        if (this.timeRemaining === 60) {
            this.showWarning('You have 1 minute remaining!');
        }
    }

    // Show warning message
    showWarning(message) {
        // Create warning element
        const warningElement = document.createElement('div');
        warningElement.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background-color: #ff9900;
            color: #000;
            padding: 20px;
            border-radius: 10px;
            z-index: 10000;
            font-size: 1.5em;
            font-weight: bold;
            box-shadow: 0 0 20px rgba(0,0,0,0.5);
        `;
        warningElement.textContent = message;
        
        document.body.appendChild(warningElement);
        
        // Remove after 3 seconds
        setTimeout(() => {
            document.body.removeChild(warningElement);
        }, 3000);
        
        // Play alert sound
        this.playAlertSound();
    }

    // Play alert sound
    playAlertSound() {
        try {
            const audio = new Audio('/static/sounds/alert.mp3');
            audio.play().catch(e => console.log('Audio play failed:', e));
        } catch (error) {
            console.log('Could not play alert sound:', error);
        }
    }

    // Time's up handler
    timeUp() {
        this.stop();
        
        // Show time up message
        this.showWarning('Time is up! Your exam will be submitted automatically.');
        
        // Submit the exam after a short delay
        setTimeout(() => {
            this.submitExam();
        }, 3000);
    }

    // Stop the timer
    stop() {
        this.isRunning = false;
        
        if (this.timerInterval) {
            clearInterval(this.timerInterval);
        }
        
        if (this.autoSaveInterval) {
            clearInterval(this.autoSaveInterval);
        }
        
        // Save final time
        this.saveTime();
    }

    // Pause the timer
    pause() {
        this.isRunning = false;
        
        if (this.timerInterval) {
            clearInterval(this.timerInterval);
        }
        
        // Save current time
        this.saveTime();
    }

    // Resume the timer
    resume() {
        if (!this.isRunning) {
            this.start();
        }
    }

    // Save time to server
    async saveTime() {
        try {
            const response = await fetch('/api/exam/save-time/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    time_remaining: this.timeRemaining,
                    time_spent: (this.timeLimitMinutes * 60) - this.timeRemaining
                })
            });
            
            if (!response.ok) {
                console.error('Failed to save time');
            }
        } catch (error) {
            console.error('Error saving time:', error);
        }
    }

    // Load saved time from server
    async loadSavedTime() {
        try {
            const response = await fetch(`/api/exam/get-time/?session_id=${this.sessionId}`);
            if (response.ok) {
                const data = await response.json();
                if (data.time_remaining) {
                    this.timeRemaining = data.time_remaining;
                    this.updateDisplay();
                }
            }
        } catch (error) {
            console.error('Error loading saved time:', error);
        }
    }

    // Submit the exam
    async submitExam() {
        try {
            // Submit all answers first
            await this.saveAllAnswers();
            
            // Then submit the exam
            const response = await fetch(`/exams/${this.sessionId}/submit/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                }
            });
            
            if (response.ok) {
                window.location.href = `/exams/${this.sessionId}/results/`;
            } else {
                console.error('Failed to submit exam');
            }
        } catch (error) {
            console.error('Error submitting exam:', error);
        }
    }

    // Save all answers
    async saveAllAnswers() {
        const form = document.getElementById('exam-form');
        if (!form) return;
        
        const formData = new FormData(form);
        const answers = {};
        
        for (const [key, value] of formData.entries()) {
            if (key.startsWith('question_')) {
                answers[key] = value;
            }
        }
        
        try {
            await fetch('/api/exam/save-answers/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    answers: answers
                })
            });
        } catch (error) {
            console.error('Error saving answers:', error);
        }
    }

    // Get CSRF token
    getCSRFToken() {
        const cookieValue = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrftoken='))
            ?.split('=')[1];
        return cookieValue || '';
    }
}

// Initialize timer when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Check if we're on an exam page
    const timerElement = document.getElementById('exam-timer');
    const sessionIdElement = document.querySelector('[data-session-id]');
    
    if (timerElement && sessionIdElement) {
        const timeLimit = parseInt(timerElement.dataset.timeLimit) || 120;
        const sessionId = sessionIdElement.dataset.sessionId;
        
        window.examTimer = new ExamTimer(timeLimit, sessionId);
        window.examTimer.start();
    }
});

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ExamTimer;
}