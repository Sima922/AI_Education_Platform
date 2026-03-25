// Exam interface functionality - question navigation and interaction
class ExamInterface {
    constructor(totalQuestions, sessionId) {
        this.totalQuestions = totalQuestions;
        this.sessionId = sessionId;
        this.currentQuestion = 1;
        this.answers = {};
        this.autoSaveInterval = null;
    }

    // Initialize the exam interface
    init() {
        // Load saved answers
        this.loadSavedAnswers();
        
        // Set up event listeners
        this.setupEventListeners();
        
        // Show first question
        this.showQuestion(this.currentQuestion);
        
        // Start auto-save
        this.startAutoSave();
    }

    // Set up event listeners
    setupEventListeners() {
        // Previous question button
        const prevButton = document.getElementById('prev-question');
        if (prevButton) {
            prevButton.addEventListener('click', () => {
                this.previousQuestion();
            });
        }

        // Next question button
        const nextButton = document.getElementById('next-question');
        if (nextButton) {
            nextButton.addEventListener('click', () => {
                this.nextQuestion();
            });
        }

        // Submit exam button
        const submitButton = document.getElementById('submit-exam');
        if (submitButton) {
            submitButton.addEventListener('click', () => {
                this.confirmSubmit();
            });
        }

        // Answer change events
        document.addEventListener('change', (e) => {
            if (e.target.matches('input[type="radio"], textarea')) {
                this.saveAnswer(this.currentQuestion);
            }
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            this.handleKeyboardShortcuts(e);
        });
    }

    // Show a specific question
    showQuestion(questionNumber) {
        // Hide all questions
        document.querySelectorAll('.question-card').forEach(card => {
            card.classList.add('d-none');
            card.classList.remove('active-question');
        });

        // Show the selected question
        const questionElement = document.querySelector(`[data-question-id="${questionNumber}"]`);
        if (questionElement) {
            questionElement.classList.remove('d-none');
            questionElement.classList.add('active-question');
        }

        // Update question counter
        document.getElementById('current-question').textContent = questionNumber;

        // Update navigation buttons
        this.updateNavigationButtons();

        // Update answer display if already answered
        this.loadAnswer(questionNumber);
    }

    // Navigate to next question
    nextQuestion() {
        if (this.currentQuestion < this.totalQuestions) {
            this.saveAnswer(this.currentQuestion);
            this.currentQuestion++;
            this.showQuestion(this.currentQuestion);
        } else {
            // If on last question, show submit button
            document.getElementById('submit-exam').classList.remove('d-none');
        }
    }

    // Navigate to previous question
    previousQuestion() {
        if (this.currentQuestion > 1) {
            this.saveAnswer(this.currentQuestion);
            this.currentQuestion--;
            this.showQuestion(this.currentQuestion);
        }
    }

    // Update navigation buttons
    updateNavigationButtons() {
        const prevButton = document.getElementById('prev-question');
        const nextButton = document.getElementById('next-question');
        const submitButton = document.getElementById('submit-exam');

        if (prevButton) {
            prevButton.disabled = this.currentQuestion === 1;
        }

        if (nextButton) {
            nextButton.disabled = this.currentQuestion === this.totalQuestions;
        }

        if (submitButton) {
            submitButton.style.display = this.currentQuestion === this.totalQuestions ? 
                'block' : 'none';
        }
    }

    // Save answer for current question
    saveAnswer(questionNumber) {
        const questionElement = document.querySelector(`[data-question-id="${questionNumber}"]`);
        if (!questionElement) return;

        const questionType = questionElement.dataset.questionType;
        let answer = '';

        if (questionType === 'multiple_choice' || questionType === 'true_false') {
            const selectedOption = questionElement.querySelector('input[type="radio"]:checked');
            if (selectedOption) {
                answer = selectedOption.value;
            }
        } else {
            // Short answer or essay
            const textarea = questionElement.querySelector('textarea');
            if (textarea) {
                answer = textarea.value;
            }
        }

        // Store answer
        this.answers[questionNumber] = answer;

        // Mark question as answered in navigation
        this.markQuestionAnswered(questionNumber, answer !== '');
    }

    // Load answer for a question
    loadAnswer(questionNumber) {
        const answer = this.answers[questionNumber];
        if (!answer) return;

        const questionElement = document.querySelector(`[data-question-id="${questionNumber}"]`);
        if (!questionElement) return;

        const questionType = questionElement.dataset.questionType;

        if (questionType === 'multiple_choice' || questionType === 'true_false') {
            const option = questionElement.querySelector(`input[value="${answer}"]`);
            if (option) {
                option.checked = true;
            }
        } else {
            // Short answer or essay
            const textarea = questionElement.querySelector('textarea');
            if (textarea) {
                textarea.value = answer;
            }
        }
    }

    // Mark question as answered in navigation
    markQuestionAnswered(questionNumber, isAnswered) {
        // This would update a question navigation panel if available
        const questionIndicator = document.querySelector(`.question-indicator[data-question="${questionNumber}"]`);
        if (questionIndicator) {
            questionIndicator.classList.toggle('answered', isAnswered);
        }
    }

    // Handle keyboard shortcuts
    handleKeyboardShortcuts(event) {
        // Ctrl + Arrow Left: Previous question
        if (event.ctrlKey && event.key === 'ArrowLeft') {
            event.preventDefault();
            this.previousQuestion();
        }
        
        // Ctrl + Arrow Right: Next question
        if (event.ctrlKey && event.key === 'ArrowRight') {
            event.preventDefault();
            this.nextQuestion();
        }
        
        // Ctrl + S: Save answers
        if (event.ctrlKey && event.key === 's') {
            event.preventDefault();
            this.saveAllAnswers();
        }
    }

    // Start auto-saving answers
    startAutoSave() {
        this.autoSaveInterval = setInterval(() => {
            this.saveAllAnswers();
        }, 30000); // Save every 30 seconds
    }

    // Save all answers to server
    async saveAllAnswers() {
        try {
            const response = await fetch('/api/exam/save-answers/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    answers: this.answers,
                    current_question: this.currentQuestion
                })
            });
            
            if (response.ok) {
                console.log('Answers saved successfully');
            } else {
                console.error('Failed to save answers');
            }
        } catch (error) {
            console.error('Error saving answers:', error);
        }
    }

    // Load saved answers from server
    async loadSavedAnswers() {
        try {
            const response = await fetch(`/api/exam/load-answers/?session_id=${this.sessionId}`);
            if (response.ok) {
                const data = await response.json();
                if (data.answers) {
                    this.answers = data.answers;
                    
                    // Restore current question if available
                    if (data.current_question) {
                        this.currentQuestion = data.current_question;
                    }
                    
                    // Update answered status for all questions
                    for (let i = 1; i <= this.totalQuestions; i++) {
                        this.markQuestionAnswered(i, this.answers[i] !== undefined && this.answers[i] !== '');
                    }
                }
            }
        } catch (error) {
            console.error('Error loading saved answers:', error);
        }
    }

    // Confirm exam submission
    confirmSubmit() {
        if (confirm('Are you sure you want to submit your exam? You will not be able to make changes after submission.')) {
            this.submitExam();
        }
    }

    // Submit the exam
    async submitExam() {
        // Save all answers first
        await this.saveAllAnswers();
        
        // Stop auto-saving
        if (this.autoSaveInterval) {
            clearInterval(this.autoSaveInterval);
        }
        
        // Submit the exam
        try {
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
                alert('Failed to submit exam. Please try again.');
            }
        } catch (error) {
            console.error('Error submitting exam:', error);
            alert('An error occurred while submitting your exam. Please try again.');
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

// Initialize exam interface when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Check if we're on an exam page
    const totalQuestionsElement = document.getElementById('total-questions');
    const sessionIdElement = document.querySelector('[data-session-id]');
    
    if (totalQuestionsElement && sessionIdElement) {
        const totalQuestions = parseInt(totalQuestionsElement.textContent) || 0;
        const sessionId = sessionIdElement.dataset.sessionId;
        
        window.examInterface = new ExamInterface(totalQuestions, sessionId);
        window.examInterface.init();
    }
});

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ExamInterface;
}