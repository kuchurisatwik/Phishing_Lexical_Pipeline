document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('verify-form');
    const input = document.getElementById('url-input');
    const btn = document.getElementById('verify-btn');
    const btnText = btn.querySelector('.btn-text');
    const spinner = btn.querySelector('.spinner');
    const resultContainer = document.getElementById('result-container');

    const icons = {
        safe: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>`,
        suspicious: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`,
        danger: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>`
    };

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const url = input.value.trim();
        if (!url) return;

        // Reset UI
        resultContainer.classList.remove('visible');
        setTimeout(() => {
            resultContainer.classList.add('hidden');
        }, 300);

        // Loading state
        btn.disabled = true;
        btnText.classList.add('hidden');
        spinner.classList.remove('hidden');

        try {
            const response = await fetch('/verify', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ url: url })
            });

            const data = await response.json();
            renderResult(data);

        } catch (error) {
            renderError(error.message || "Failed to connect to the verification API.");
        } finally {
            // Restore button
            btn.disabled = false;
            btnText.classList.remove('hidden');
            spinner.classList.add('hidden');
        }
    });

    function getStatusTheme(classification) {
        if (!classification) return 'safe';
        
        const finalClass = classification.final_classification;
        if (finalClass === 'confirmed_phishing' || finalClass === 'high_risk') return 'danger';
        if (finalClass === 'suspicious_needs_review' || finalClass === 'medium_risk') return 'suspicious';
        return 'safe';
    }

    function renderResult(data) {
        const theme = getStatusTheme(data.classification);
        const icon = icons[theme];
        
        let title = "Safe Website";
        if (theme === 'danger') title = "Phishing Detected!";
        if (theme === 'suspicious') title = "Suspicious Website";

        // Format scores
        let scoresHtml = '';
        if (data.classification && data.classification.standard_score !== undefined) {
            const stdScore = (data.classification.standard_score * 100).toFixed(1) + '%';
            const hrdScore = (data.classification.hardened_score * 100).toFixed(1) + '%';
            
            scoresHtml = `
                <div class="detail-item">
                    <div class="detail-label">Model Confidence</div>
                    <div class="detail-value">Standard: ${stdScore} | Hardened: ${hrdScore}</div>
                </div>
            `;
        }

        // Format Lexical match
        let lexicalHtml = '';
        if (data.lexical_result && data.lexical_result.cse) {
            const cseName = data.lexical_result.cse.toUpperCase();
            lexicalHtml = `
                <div class="detail-item">
                    <div class="detail-label">Target Brand Match</div>
                    <div class="detail-value">Matches brand token: <strong>${cseName}</strong></div>
                </div>
            `;
        }

        const reason = data.classification?.classification_reason || data.reason || "No suspicious indicators detected.";

        resultContainer.className = `glass-card result-card status-${theme} hidden`;
        resultContainer.innerHTML = `
            <div class="result-header">
                <div class="status-icon">
                    ${icon}
                </div>
                <div class="result-title">
                    <h2>${title}</h2>
                    <p>${data.url}</p>
                </div>
            </div>
            <div class="result-details">
                <div class="detail-item">
                    <div class="detail-label">Analysis Reason</div>
                    <div class="detail-value">${reason}</div>
                </div>
                ${lexicalHtml}
                ${scoresHtml}
            </div>
        `;

        // Animate in
        resultContainer.classList.remove('hidden');
        // Trigger reflow
        void resultContainer.offsetWidth;
        resultContainer.classList.add('visible');
    }

    function renderError(message) {
        resultContainer.className = `glass-card result-card status-danger hidden`;
        resultContainer.innerHTML = `
            <div class="result-header">
                <div class="status-icon">
                    ${icons.danger}
                </div>
                <div class="result-title">
                    <h2>Verification Error</h2>
                    <p>Something went wrong</p>
                </div>
            </div>
            <div class="result-details">
                <div class="detail-item">
                    <div class="detail-label">Error Details</div>
                    <div class="detail-value">${message}</div>
                </div>
            </div>
        `;

        resultContainer.classList.remove('hidden');
        void resultContainer.offsetWidth;
        resultContainer.classList.add('visible');
    }
});
