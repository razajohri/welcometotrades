(function () {
    const STORAGE_KEY = 'rjc_visited_jobs';
    const MAX_ENTRIES = 500;

    function normalizeJobUrl(url) {
        try {
            const parsed = new URL(url, window.location.origin);
            return parsed.href.replace(/\/$/, '');
        } catch {
            return (url || '').trim();
        }
    }

    function readVisited() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            const list = raw ? JSON.parse(raw) : [];
            return Array.isArray(list) ? list : [];
        } catch {
            return [];
        }
    }

    function writeVisited(list) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(list.slice(-MAX_ENTRIES)));
        } catch {
            /* localStorage full or unavailable */
        }
    }

    function markVisited(url) {
        const normalized = normalizeJobUrl(url);
        if (!normalized) return;
        const list = readVisited().filter((entry) => entry !== normalized);
        list.push(normalized);
        writeVisited(list);
    }

    function isVisited(url) {
        return readVisited().includes(normalizeJobUrl(url));
    }

    function applyVisitedState(card) {
        const url = card.getAttribute('data-job-url');
        if (url && isVisited(url)) {
            card.classList.add('job-card--visited');
        }
    }

    function initVisitedJobs(root) {
        const scope = root || document;
        scope.querySelectorAll('.job-card[data-job-url]').forEach(applyVisitedState);

        scope.querySelectorAll('.job-visit-link').forEach((link) => {
            link.addEventListener('click', () => {
                const card = link.closest('.job-card');
                const url = (card && card.getAttribute('data-job-url')) || link.getAttribute('href');
                if (!url) return;
                markVisited(url);
                if (card) card.classList.add('job-card--visited');
            });
        });
    }

    window.initVisitedJobs = initVisitedJobs;
    document.addEventListener('DOMContentLoaded', () => initVisitedJobs());
})();
