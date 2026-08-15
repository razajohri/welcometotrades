(function () {
    function initContactForm(form) {
        const messageDiv = form.querySelector('[data-contact-message]');
        const submitBtn = form.querySelector('[data-contact-submit]');
        if (!submitBtn) return;

        const recaptchaEnabled = form.dataset.recaptchaEnabled === 'true';
        const recaptchaSiteKey = (form.dataset.recaptchaSiteKey || '').trim();
        let recaptchaReady = false;

        if (recaptchaEnabled && recaptchaSiteKey && typeof grecaptcha !== 'undefined') {
            grecaptcha.ready(function () {
                recaptchaReady = true;
            });
        }

        form.addEventListener('submit', async function (event) {
            event.preventDefault();

            const email = (form.querySelector('[name="email"]')?.value || '').trim();
            const subject = (form.querySelector('[name="subject"]')?.value || '').trim();
            const message = (form.querySelector('[name="message"]')?.value || '').trim();
            const website = form.querySelector('[name="website"]')?.value || '';

            if (!email || !subject || !message) {
                showMessage(messageDiv, 'Please fill in all fields.', 'error');
                return;
            }
            if (subject.length < 3) {
                showMessage(messageDiv, 'Subject must be at least 3 characters.', 'error');
                return;
            }
            if (message.length < 10) {
                showMessage(messageDiv, 'Message must be at least 10 characters.', 'error');
                return;
            }

            submitBtn.disabled = true;
            const originalLabel = submitBtn.textContent;
            submitBtn.textContent = 'Sending...';

            try {
                let recaptchaToken = '';
                if (recaptchaEnabled && recaptchaSiteKey) {
                    if (!recaptchaReady || typeof grecaptcha === 'undefined') {
                        showMessage(
                            messageDiv,
                            'Security check is still loading. Please wait a moment and try again.',
                            'error'
                        );
                        return;
                    }
                    recaptchaToken = await grecaptcha.execute(recaptchaSiteKey, { action: 'contact_form' });
                }

                const response = await fetch('/api/contact', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        email,
                        subject,
                        message,
                        website,
                        recaptcha_token: recaptchaToken,
                    }),
                });

                let data = {};
                try {
                    data = await response.json();
                } catch (parseError) {
                    throw new Error('Invalid server response');
                }

                if (response.ok && data.success) {
                    showMessage(
                        messageDiv,
                        data.message || 'Thank you! Your message has been sent.',
                        'success'
                    );
                    form.reset();
                } else {
                    showMessage(messageDiv, data.error || 'Something went wrong. Please try again.', 'error');
                }
            } catch (error) {
                console.error('Contact form error:', error);
                showMessage(messageDiv, 'Failed to send message. Please try again later.', 'error');
            } finally {
                submitBtn.disabled = false;
                submitBtn.textContent = originalLabel;
            }
        });
    }

    function showMessage(messageDiv, text, type) {
        if (!messageDiv) return;
        messageDiv.textContent = text;
        messageDiv.hidden = false;
        messageDiv.classList.remove('contact-message--success', 'contact-message--error');
        messageDiv.classList.add(type === 'success' ? 'contact-message--success' : 'contact-message--error');
        window.clearTimeout(messageDiv._hideTimer);
        messageDiv._hideTimer = window.setTimeout(function () {
            messageDiv.hidden = true;
        }, 8000);
    }

    document.querySelectorAll('[data-contact-form]').forEach(initContactForm);
})();
