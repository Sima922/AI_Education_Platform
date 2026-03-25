document.addEventListener('DOMContentLoaded', function() {
    // Add new question
    document.querySelectorAll('.add-question').forEach(button => {
        button.addEventListener('click', function() {
            const chapter = this.dataset.chapter;
            const newQuestion = `
                <div class="quiz-question">
                    <input type="text" name="new_question_${chapter}_${Date.now()}" 
                           placeholder="New question text" class="editable-field">
                    <div class="quiz-options">
                        <input type="text" name="new_option_${chapter}_${Date.now()}_1" 
                               placeholder="Option 1" class="editable-field">
                        <input type="text" name="new_option_${chapter}_${Date.now()}_2" 
                               placeholder="Option 2" class="editable-field">
                    </div>
                </div>`;
            this.insertAdjacentHTML('beforebegin', newQuestion);
        });
    });

    // Add YouTube video
    document.querySelectorAll('.add-video').forEach(button => {
        button.addEventListener('click', async function() {
            const chapter = this.dataset.chapter;
            const searchQuery = prompt("Enter YouTube search query:");
            if (searchQuery) {
                const response = await fetch(`/api/youtube-search?q=${encodeURIComponent(searchQuery)}`);
                const videos = await response.json();
                // Display video selection UI
            }
        });
    });
});