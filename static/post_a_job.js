(function () {
    function showMessage(form, type, text) {
        const messageDiv = form.querySelector('[data-post-job-message]');
        if (!messageDiv) return;
        messageDiv.hidden = false;
        messageDiv.textContent = text;
        messageDiv.classList.remove('post-job-form-message--success', 'post-job-form-message--error');
        messageDiv.classList.add(type === 'success' ? 'post-job-form-message--success' : 'post-job-form-message--error');
    }

    function initPostJobForm(form) {
        const submitBtn = form.querySelector('[data-post-job-submit]');
        const recaptchaEnabled = form.dataset.recaptchaEnabled === 'true';
        const recaptchaSiteKey = form.dataset.recaptchaSiteKey || '';

        form.addEventListener('submit', async function (event) {
            event.preventDefault();

            const companyName = form.company_name.value.trim();
            const jobTitle = form.job_title.value.trim();
            const tags = form.tags.value.trim();
            const salaryRange = form.salary_range.value.trim();
            const jobDescription = form.job_description.value.trim();
            const applyMethod = form.apply_method.value.trim();
            const invoiceEmail = form.invoice_email.value.trim();
            const questions = form.questions.value.trim();
            const pricingOption = form.querySelector('input[name="pricing_option"]:checked');
            const honeypot = form.website.value.trim();

            if (!companyName || !jobTitle || !jobDescription || !applyMethod || !invoiceEmail || !pricingOption) {
                showMessage(form, 'error', 'Please fill in all required fields and choose a pricing option.');
                return;
            }

            submitBtn.disabled = true;
            showMessage(form, 'success', 'Submitting…');

            try {
                let recaptchaToken = '';
                if (recaptchaEnabled && recaptchaSiteKey && window.grecaptcha) {
                    await new Promise(function (resolve) {
                        grecaptcha.ready(resolve);
                    });
                    recaptchaToken = await grecaptcha.execute(recaptchaSiteKey, { action: 'post_job_form' });
                }

                const response = await fetch('/api/post-job', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        company_name: companyName,
                        job_title: jobTitle,
                        tags: tags,
                        salary_range: salaryRange,
                        job_description: jobDescription,
                        apply_method: applyMethod,
                        invoice_email: invoiceEmail,
                        questions: questions,
                        pricing_option: pricingOption.value,
                        website: honeypot,
                        recaptcha_token: recaptchaToken,
                    }),
                });

                const data = await response.json().catch(function () {
                    return {};
                });

                if (!response.ok) {
                    showMessage(form, 'error', data.error || 'Something went wrong. Please try again.');
                    return;
                }

                showMessage(form, 'success', data.message || 'Thank you! We received your job posting request.');
                form.reset();
            } catch (error) {
                showMessage(form, 'error', 'Network error. Please check your connection and try again.');
            } finally {
                submitBtn.disabled = false;
            }
        });
    }

    document.querySelectorAll('[data-post-job-form]').forEach(initPostJobForm);
})();
