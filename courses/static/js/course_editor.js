document.addEventListener('DOMContentLoaded', function() {
    // Initialize all rich text editors
    initializeRichTextEditors();

    // Setup auto-save functionality
    setupAutoSave();

    // Setup form submission
    setupFormSubmission();

    // Setup dynamic content handlers
    setupDynamicContentHandlers();
});

// Initialize rich text editors
function initializeRichTextEditors() {
    const editors = document.querySelectorAll('.rich-text-editor');
    editors.forEach(editor => {
        // Add input event listener for auto-save
        editor.addEventListener('input', function() {
            const chapter = this.dataset.chapter;
            const section = this.dataset.section;
            autoSaveContent(this.innerHTML, chapter, section);
        });

        // Add focus handler to save selection state
        editor.addEventListener('focus', function() {
            this.lastSelection = null;
        });

        // Add blur handler to restore selection
        editor.addEventListener('blur', function() {
            this.lastSelection = null;
        });
    });

    // Setup toolbar buttons
    document.querySelectorAll('.editor-toolbar button').forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const command = this.dataset.command;
            const editor = this.closest('.rich-text-container').querySelector('.rich-text-editor');
            document.execCommand(command, false, null);
            editor.focus();
        });
    });
}

// Auto-save functionality
function setupAutoSave() {
    // Auto-save for text inputs
    document.querySelectorAll('input[type="text"]').forEach(input => {
        input.addEventListener('input', function() {
            if (this.id === 'course-title' || this.id === 'course-topic') {
                autoSaveContent(this.value, null, this.id.replace('course-', ''));
            } else if (this.classList.contains('chapter-title')) {
                const chapter = this.dataset.chapter;
                autoSaveContent(this.value, chapter, 'title');
            }
        });
    });
}

function autoSaveContent(content, chapter, section) {
    const formData = new FormData();
    const csrfToken = document.querySelector('input[name="csrfmiddlewaretoken"]').value;

    formData.append('csrfmiddlewaretoken', csrfToken);
    formData.append('content', content);
    formData.append('section', section);
    if (chapter) formData.append('chapter_id', chapter);

    fetch(document.getElementById('save-preview-form').action, {
        method: 'POST',
        body: formData,
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            showSaveStatus(chapter);
        }
    })
    .catch(error => console.error('Error saving content:', error));
}

function showSaveStatus(chapter) {
    const statusElement = chapter ? 
        document.getElementById(`chapter-${chapter}-status`) :
        document.getElementById('course-info-status');
    
    statusElement.classList.add('visible');
    setTimeout(() => {
        statusElement.classList.remove('visible');
    }, 2000);
}

// Setup form submission
function setupFormSubmission() {
    const form = document.getElementById('save-preview-form');
    if (!form) return;

    form.addEventListener('submit', function(e) {
        e.preventDefault();
        updateHiddenFields();
        this.submit();
    });
}

function updateHiddenFields() {
    // Course info
    document.getElementById('hidden-course-title').value = document.getElementById('course-title').value;
    document.getElementById('hidden-course-description').value = document.querySelector('#course-description').innerHTML;
    document.getElementById('hidden-course-topic').value = document.getElementById('course-topic').value;

    // Count chapters
    const chapters = document.querySelectorAll('.chapter-section');
    document.getElementById('hidden-chapter-count').value = chapters.length;

    // Update chapter data
    chapters.forEach(chapterSection => {
        const chapterNum = chapterSection.querySelector('.chapter-title').dataset.chapter;
        
        // Basic chapter info
        document.getElementById(`hidden-chapter-${chapterNum}-title`).value = 
            chapterSection.querySelector('.chapter-title').value;
        
        document.getElementById(`hidden-chapter-${chapterNum}-introduction`).value = 
            chapterSection.querySelector(`#chapter-${chapterNum}-introduction`).innerHTML;
        
        document.getElementById(`hidden-chapter-${chapterNum}-main-content`).value = 
            chapterSection.querySelector(`#chapter-${chapterNum}-main-content`).innerHTML;

        // Learning objectives
        const objectives = Array.from(
            chapterSection.querySelectorAll('.objective-input')
        ).map(input => input.value.trim()).filter(val => val);
        document.getElementById(`hidden-chapter-${chapterNum}-objectives`).value = objectives.join('|');

        // Examples
        const examples = Array.from(
            chapterSection.querySelectorAll('.example-input')
        ).map(input => input.value.trim()).filter(val => val);
        document.getElementById(`hidden-chapter-${chapterNum}-examples`).value = examples.join('|');

        // Quiz questions
        const quizSection = chapterSection.querySelector('.quiz-editor');
        const questions = quizSection.querySelectorAll('.question-editor');
        document.getElementById(`hidden-chapter-${chapterNum}-quiz-count`).value = questions.length;

        questions.forEach((questionDiv, idx) => {
            const questionNum = idx + 1;
            const questionText = questionDiv.querySelector('.question-text').value;
            const options = Array.from(
                questionDiv.querySelectorAll('.option-text')
            ).map(input => input.value.trim()).filter(val => val);
            const correctOption = questionDiv.querySelector('input[type="radio"]:checked')?.value;

            document.getElementById(`hidden-chapter-${chapterNum}-quiz-question-${questionNum}`).value = questionText;
            document.getElementById(`hidden-chapter-${chapterNum}-quiz-options-${questionNum}`).value = options.join('|');
            document.getElementById(`hidden-chapter-${chapterNum}-quiz-correct-${questionNum}`).value = correctOption || '';
        });
    });
}

// Setup dynamic content handlers
function setupDynamicContentHandlers() {
    // Event delegation for dynamic content
    document.addEventListener('click', function(e) {
        // Learning Objectives
        if (e.target.classList.contains('add-objective')) {
            handleAddObjective(e.target);
        }
        if (e.target.classList.contains('remove-objective')) {
            e.target.closest('.objective-row').remove();
        }

        // Examples
        if (e.target.classList.contains('add-example')) {
            handleAddExample(e.target);
        }
        if (e.target.classList.contains('remove-example')) {
            e.target.closest('.example-row').remove();
        }

        // Quiz Questions
        if (e.target.classList.contains('add-question')) {
            handleAddQuestion(e.target);
        }
        if (e.target.classList.contains('remove-question')) {
            e.target.closest('.question-editor').remove();
        }

        // Quiz Options
        if (e.target.classList.contains('add-option')) {
            handleAddOption(e.target);
        }
        if (e.target.classList.contains('remove-option')) {
            handleRemoveOption(e.target);
        }
    });

    // Update radio values when option text changes
    document.addEventListener('input', function(e) {
        if (e.target.classList.contains('option-text')) {
            const radio = e.target.closest('.option-row').querySelector('input[type="radio"]');
            radio.value = e.target.value.trim();
        }
    });
}

function handleAddObjective(button) {
    const chapter = button.closest('.objectives-editor').dataset.chapter;
    const newObjective = `
        <div class="objective-row">
            <input type="text" class="form-control objective-input" data-chapter="${chapter}" placeholder="New Objective">
            <button type="button" class="btn btn-danger remove-objective">Remove</button>
        </div>`;
    button.insertAdjacentHTML('beforebegin', newObjective);
}

function handleAddExample(button) {
    const chapter = button.closest('.examples-editor').dataset.chapter;
    const newExample = `
        <div class="example-row">
            <input type="text" class="form-control example-input" data-chapter="${chapter}" placeholder="New Example">
            <button type="button" class="btn btn-danger remove-example">Remove</button>
        </div>`;
    button.insertAdjacentHTML('beforebegin', newExample);
}

function handleAddQuestion(button) {
    const quizEditor = button.closest('.quiz-editor');
    const chapter = quizEditor.dataset.chapter;
    const questionCount = quizEditor.querySelectorAll('.question-editor').length + 1;
    
    const newQuestion = `
        <div class="question-editor" data-question-number="${questionCount}">
            <input type="text" class="form-control question-text" placeholder="New Question">
            <div class="options-container">
                <div class="option-row">
                    <input type="text" class="form-control option-text" placeholder="Option 1">
                    <input type="radio" name="correct-${chapter}-${questionCount}" value="">
                    <button type="button" class="btn btn-danger remove-option">Remove</button>
                </div>
            </div>
            <button type="button" class="btn btn-primary add-option">Add Option</button>
            <button type="button" class="btn btn-danger remove-question">Remove Question</button>
        </div>`;
    button.insertAdjacentHTML('beforebegin', newQuestion);
}

function handleAddOption(button) {
    const questionEditor = button.closest('.question-editor');
    const optionsContainer = questionEditor.querySelector('.options-container');
    const chapter = button.closest('.quiz-editor').dataset.chapter;
    const questionNum = questionEditor.dataset.questionNumber;
    const optionCount = optionsContainer.querySelectorAll('.option-row').length + 1;

    const newOption = `
        <div class="option-row">
            <input type="text" class="form-control option-text" placeholder="Option ${optionCount}">
            <input type="radio" name="correct-${chapter}-${questionNum}" value="">
            <button type="button" class="btn btn-danger remove-option">Remove</button>
        </div>`;
    optionsContainer.insertAdjacentHTML('beforeend', newOption);
}

function handleRemoveOption(button) {
    const optionRow = button.closest('.option-row');
    const optionsContainer = optionRow.closest('.options-container');
    
    // Don't remove if it's the last option
    if (optionsContainer.querySelectorAll('.option-row').length > 1) {
        optionRow.remove();
    }
}

// Exam configuration handling for course creation
document.addEventListener('DOMContentLoaded', function() {
    const enableExamCheckbox = document.getElementById('enable-exam');
    const examConfigDetails = document.getElementById('exam-config-details');
    const examTypeSelect = document.getElementById('exam_type');
    const promptSection = document.getElementById('prompt-section');
    const templateSection = document.getElementById('template-section');
    
    // Toggle exam settings visibility
    if (enableExamCheckbox && examConfigDetails) {
        enableExamCheckbox.addEventListener('change', function() {
            examConfigDetails.style.display = this.checked ? 'block' : 'none';
            updateFormValidation();
        });
        
        // Initialize visibility
        examConfigDetails.style.display = enableExamCheckbox.checked ? 'block' : 'none';
    }
    
    // Toggle prompt/template sections based on exam type
    if (examTypeSelect && promptSection && templateSection) {
        examTypeSelect.addEventListener('change', function() {
            if (this.value === 'custom') {
                promptSection.style.display = 'block';
                templateSection.style.display = 'none';
            } else if (this.value === 'template') {
                promptSection.style.display = 'none';
                templateSection.style.display = 'block';
            } else {
                promptSection.style.display = 'none';
                templateSection.style.display = 'none';
            }
            updateFormValidation();
        });
        
        // Initialize visibility
        if (examTypeSelect.value === 'custom') {
            promptSection.style.display = 'block';
            templateSection.style.display = 'none';
        } else if (examTypeSelect.value === 'template') {
            promptSection.style.display = 'none';
            templateSection.style.display = 'block';
        } else {
            promptSection.style.display = 'none';
            templateSection.style.display = 'none';
        }
    }
    
    // Form validation for exam configuration
    function updateFormValidation() {
        const examPrompt = document.getElementById('exam_prompt');
        const examTemplate = document.getElementById('exam_template');
        
        if (enableExamCheckbox.checked) {
            if (examTypeSelect.value === 'custom') {
                examPrompt.setAttribute('required', 'required');
                examTemplate.removeAttribute('required');
            } else if (examTypeSelect.value === 'template') {
                examTemplate.setAttribute('required', 'required');
                examPrompt.removeAttribute('required');
            } else {
                examPrompt.removeAttribute('required');
                examTemplate.removeAttribute('required');
            }
        } else {
            examPrompt.removeAttribute('required');
            examTemplate.removeAttribute('required');
        }
    }
    
    // Initialize form validation
    updateFormValidation();
    
    // Handle exam template file upload
    const examTemplateInput = document.getElementById('exam_template');
    if (examTemplateInput) {
        examTemplateInput.addEventListener('change', function() {
            const file = this.files[0];
            if (file) {
                // Validate file type
                const allowedTypes = ['.pdf', '.doc', '.docx', '.txt'];
                const fileExtension = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
                
                if (!allowedTypes.includes(fileExtension)) {
                    alert('Please select a PDF, Word, or text file.');
                    this.value = '';
                    return;
                }
                
                // Validate file size (max 10MB)
                if (file.size > 10 * 1024 * 1024) {
                    alert('File size must be less than 10MB.');
                    this.value = '';
                    return;
                }
                
                // Show file name
                const fileNameDisplay = document.getElementById('file-name-display') || 
                    createFileNameDisplay();
                fileNameDisplay.textContent = `Selected file: ${file.name}`;
            }
        });
    }
    
    // Create file name display element
    function createFileNameDisplay() {
        const display = document.createElement('div');
        display.id = 'file-name-display';
        display.style.marginTop = '5px';
        display.style.fontSize = '0.9em';
        display.style.color = '#28a745';
        
        examTemplateInput.parentNode.appendChild(display);
        return display;
    }
    
    // AI exam generation preview
    const generateExamBtn = document.getElementById('generate-exam-preview');
    if (generateExamBtn) {
        generateExamBtn.addEventListener('click', function() {
            generateExamPreview();
        });
    }
    
    // Generate exam preview using AI
    async function generateExamPreview() {
        const courseTitle = document.getElementById('course-title').value;
        const courseDescription = document.getElementById('course-description').value;
        const examPrompt = document.getElementById('exam_prompt').value;
        const examType = document.getElementById('exam_type').value;
        
        if (!courseTitle) {
            alert('Please enter a course title first.');
            return;
        }
        
        if (examType === 'custom' && !examPrompt) {
            alert('Please enter exam instructions for the AI.');
            return;
        }
        
        // Show loading state
        generateExamBtn.disabled = true;
        generateExamBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating...';
        
        try {
            const response = await fetch('/api/generate-exam-preview/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                },
                body: JSON.stringify({
                    course_title: courseTitle,
                    course_description: courseDescription,
                    exam_type: examType,
                    exam_prompt: examPrompt
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                showExamPreview(data.exam_preview);
            } else {
                throw new Error('Failed to generate exam preview');
            }
        } catch (error) {
            console.error('Error generating exam preview:', error);
            alert('Failed to generate exam preview. Please try again.');
        } finally {
            // Reset button state
            generateExamBtn.disabled = false;
            generateExamBtn.innerHTML = 'Generate Exam Preview';
        }
    }
    
    // Show exam preview in a modal
    function showExamPreview(previewData) {
        // Create modal element
        const modal = document.createElement('div');
        modal.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.7);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 10000;
        `;
        
        // Modal content
        modal.innerHTML = `
            <div style="background-color: white; padding: 20px; border-radius: 10px; max-width: 80%; max-height: 80%; overflow-y: auto;">
                <h2>AI-Generated Exam Preview</h2>
                <div id="exam-preview-content">
                    ${formatExamPreview(previewData)}
                </div>
                <div style="margin-top: 20px; text-align: right;">
                    <button id="close-preview" style="padding: 8px 16px; background-color: #6f42c1; color: white; border: none; border-radius: 4px; cursor: pointer;">
                        Close
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // Close button event
        document.getElementById('close-preview').addEventListener('click', function() {
            document.body.removeChild(modal);
        });
        
        // Close modal when clicking outside
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                document.body.removeChild(modal);
            }
        });
    }
    
    // Format exam preview data for display
    function formatExamPreview(previewData) {
        if (!previewData || !previewData.questions) {
            return '<p>No exam preview available.</p>';
        }
        
        let html = `
            <p><strong>Exam Title:</strong> ${previewData.title || 'Generated Exam'}</p>
            <p><strong>Description:</strong> ${previewData.description || 'No description'}</p>
            <p><strong>Total Questions:</strong> ${previewData.questions.length}</p>
            <hr>
            <h3>Questions:</h3>
        `;
        
        previewData.questions.forEach((question, index) => {
            html += `
                <div style="margin-bottom: 20px; padding: 10px; border: 1px solid #eee; border-radius: 5px;">
                    <p><strong>Question ${index + 1}:</strong> ${question.question_text}</p>
                    <p><strong>Type:</strong> ${question.question_type}</p>
                    <p><strong>Points:</strong> ${question.points}</p>
            `;
            
            if (question.options && question.options.length > 0) {
                html += `<p><strong>Options:</strong></p><ul>`;
                question.options.forEach(option => {
                    html += `<li>${option}</li>`;
                });
                html += `</ul>`;
            }
            
            html += `</div>`;
        });
        
        return html;
    }
    
    // Get CSRF token
    function getCSRFToken() {
        const cookieValue = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrftoken='))
            ?.split('=')[1];
        return cookieValue || '';
    }
});