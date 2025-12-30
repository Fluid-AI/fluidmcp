// FluidMCP Auth0 Handler
(function() {
    'use strict';

    // Check if already logged in
    function checkExistingAuth() {
        const accessToken = localStorage.getItem('access_token');

        if (accessToken) {
            // Verify token is still valid
            fetch('/auth/me', {
                headers: {
                    'Authorization': `Bearer ${accessToken}`
                }
            })
            .then(response => {
                if (response.ok) {
                    // Token valid, redirect to docs
                    console.log('Already authenticated, redirecting...');
                    window.location.href = '/docs';
                } else {
                    // Token invalid, clear storage
                    console.log('Token invalid, clearing auth');
                    clearAuth();
                }
            })
            .catch((error) => {
                console.log('Error checking auth:', error);
                clearAuth();
            });
        }
    }

    function clearAuth() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('session_id');
    }

    function loginWithProvider(connection) {
        console.log(`Initiating login with ${connection}...`);
        // Redirect to Auth0 login with specific provider
        window.location.href = `/auth/login?connection=${connection}`;
    }

    function loginWithAuth0() {
        console.log('Initiating Auth0 Universal Login...');
        // Redirect to Auth0 Universal Login (no connection parameter)
        window.location.href = '/auth/login';
    }

    function logout() {
        fetch('/auth/logout', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
                'X-Session-ID': localStorage.getItem('session_id')
            }
        })
        .then(response => response.json())
        .then(data => {
            clearAuth();
            window.location.href = data.logout_url;
        })
        .catch(() => {
            clearAuth();
            window.location.href = '/';
        });
    }

    // Make functions available globally
    window.loginWithProvider = loginWithProvider;
    window.loginWithAuth0 = loginWithAuth0;
    window.logout = logout;

    // Check auth on page load
    document.addEventListener('DOMContentLoaded', checkExistingAuth);

})();
