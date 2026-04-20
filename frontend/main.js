// Authentication helpers
function setToken(token) {
    localStorage.setItem('access_token', token);
}

function getToken() {
    return localStorage.getItem('access_token');
}

function logout() {
    localStorage.removeItem('access_token');
    window.location.href = '/login';
}

function showToast(message, isError = false) {
    const toast = document.getElementById('toast') || createToastElement();
    toast.textContent = message;
    toast.style.background = isError ? 'var(--danger-color)' : 'var(--text-primary)';
    toast.classList.add('show');
    
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

function createToastElement() {
    const toast = document.createElement('div');
    toast.id = 'toast';
    document.body.appendChild(toast);
    return toast;
}

// Ensure Auth State for Protected Pages
async function checkAuth() {
    const token = getToken();
    const protectedPages = ['/dashboard'];
    const currentPath = window.location.pathname;

    if (protectedPages.includes(currentPath)) {
        if (!token) {
            window.location.href = '/login';
            return null;
        }

        try {
            const response = await fetch('/api/me', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (!response.ok) {
                logout();
                return null;
            }
            const data = await response.json();
            return data;
        } catch (e) {
            logout();
        }
    }
    
    // Auth page redirect if already logged in
    if (['/login', '/signup'].includes(currentPath) && token) {
        window.location.href = '/dashboard';
    }
    return null;
}

// API Calls
async function apiCall(endpoint, method = 'GET', body = null) {
    const headers = {
        'Content-Type': 'application/json'
    };
    
    const token = getToken();
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const config = { method, headers };
    if (body) {
        config.body = JSON.stringify(body);
    }

    const res = await fetch(`/api${endpoint}`, config);
    const data = await res.json();
    
    if (!res.ok) {
        throw new Error(data.detail || 'API request failed');
    }
    return data;
}

// Generate Auth Forms behavior
document.addEventListener('DOMContentLoaded', () => {
    const signupForm = document.getElementById('signupForm');
    const loginForm = document.getElementById('loginForm');
    
    if (signupForm) {
        signupForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            try {
                const data = await apiCall('/signup', 'POST', { email, password });
                setToken(data.access_token);
                window.location.href = '/dashboard';
            } catch (err) {
                showToast(err.message, true);
            }
        });
    }

    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const params = new URLSearchParams();
            params.append('username', document.getElementById('email').value);
            params.append('password', document.getElementById('password').value);
            
            try {
                const res = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: params
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Login failed');
                
                setToken(data.access_token);
                window.location.href = '/dashboard';
            } catch (err) {
                showToast(err.message, true);
            }
        });
    }

    // Dashboard initialization
    if (window.location.pathname === '/dashboard') {
        const initDashboard = async () => {
            const user = await checkAuth();
            if(!user) return;
            
            document.getElementById('userEmail').textContent = user.email;
            
            // Fill forms
            document.getElementById('watchSenders').value = user.watch_senders.join(', ');
            document.getElementById('watchKeywords').value = user.watch_keywords.join(', ');
            document.getElementById('twilioSid').value = user.twilio_sid || '';
            document.getElementById('twilioToken').value = user.twilio_token || '';
            document.getElementById('twilioFrom').value = user.twilio_from || '+14155238886';
            document.getElementById('whatsappPhone').value = user.whatsapp_phone || '';
            document.getElementById('gmailToken').value = user.gmail_token_json || '';
            document.getElementById('notificationTime').value = user.notification_time || '08:00';
            document.getElementById('botEnabled').checked = user.bot_enabled;
            document.getElementById('enableDevpost').checked = user.enable_devpost;
            document.getElementById('enableUnstop').checked = user.enable_unstop;

            // Show warning if enabled
            if(user.bot_enabled) {
                document.getElementById('sandboxWarning').style.display = 'block';
            }
        };

        const saveSettings = async (e) => {
            if(e) e.preventDefault();
            const sendersRaw = document.getElementById('watchSenders').value;
            const senders = sendersRaw.split(',').map(s => s.trim()).filter(s => s);
            
            const keywordsRaw = document.getElementById('watchKeywords').value;
            const keywords = keywordsRaw.split(',').map(s => s.trim()).filter(s => s);
            
            const payload = {
                bot_enabled: document.getElementById('botEnabled').checked,
                notification_time: document.getElementById('notificationTime').value,
                watch_senders: senders,
                watch_keywords: keywords,
                gmail_token_json: document.getElementById('gmailToken').value.trim(),
                twilio_sid: document.getElementById('twilioSid').value.trim(),
                twilio_token: document.getElementById('twilioToken').value.trim(),
                twilio_from: document.getElementById('twilioFrom').value.trim(),
                whatsapp_phone: document.getElementById('whatsappPhone').value.trim(),
                enable_devpost: document.getElementById('enableDevpost').checked,
                enable_unstop: document.getElementById('enableUnstop').checked
            };
            
            try {
                const data = await apiCall('/settings', 'POST', payload);
                showToast(data.message);
                if(payload.bot_enabled) {
                    document.getElementById('sandboxWarning').style.display = 'block';
                } else {
                    document.getElementById('sandboxWarning').style.display = 'none';
                }
            } catch (err) {
                showToast(err.message, true);
            }
        };

        const testWhatsapp = async () => {
            const payload = {
                bot_enabled: false,
                notification_time: "00:00",
                watch_senders: [],
                watch_keywords: [],
                gmail_token_json: "",
                twilio_sid: document.getElementById('twilioSid').value.trim(),
                twilio_token: document.getElementById('twilioToken').value.trim(),
                twilio_from: document.getElementById('twilioFrom').value.trim(),
                whatsapp_phone: document.getElementById('whatsappPhone').value.trim(),
                enable_devpost: false,
                enable_unstop: false
            };

            if(!payload.twilio_sid || !payload.twilio_token || !payload.whatsapp_phone) {
                showToast("Please fill SID, Token, and WhatsApp number first", true);
                return;
            }

            try {
                showToast("Sending test message...");
                const data = await apiCall('/test-whatsapp', 'POST', payload);
                showToast(data.message);
            } catch (err) {
                showToast(err.message, true);
            }
        };

        document.getElementById('settingsForm').addEventListener('submit', saveSettings);
        document.getElementById('testWhatsappBtn').addEventListener('click', testWhatsapp);
        
        // Onboarding Wizard Logic
        const modal = document.getElementById('onboardingModal');
        const openBtn = document.getElementById('openWizardBtn');
        const closeBtn = document.querySelector('.close-modal');
        const nextBtn = document.getElementById('nextBtn');
        const prevBtn = document.getElementById('prevBtn');
        const stepDots = document.getElementById('stepDots');
        const wizardTitle = document.getElementById('wizardTitle');
        const wizardBody = document.getElementById('wizardBody');

        let currentStep = 1;
        const totalSteps = 5;

        const steps = [
            {
                title: "Step 1 — Create Twilio account",
                content: `
                    <p>First, you'll need a Twilio account to send WhatsApp messages.</p>
                    <ul style="margin-left: 1.5rem; margin-bottom: 1rem;">
                        <li>Go to <a href="https://www.twilio.com" target="_blank">twilio.com</a> and sign up.</li>
                        <li>Twilio offers a <strong>free trial</strong> with ~$15 credit.</li>
                        <li>No credit card is required to start!</li>
                    </ul>
                `
            },
            {
                title: "Step 2 — Find Account SID and Auth Token",
                content: `
                    <p>Login to your Twilio Console to find your credentials.</p>
                    <div class="screenshot-placeholder">
                        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                            <line x1="3" y1="9" x2="21" y2="9"></line>
                        </svg>
                        <div class="screenshot-annotation">Found on Console Dashboard homepage</div>
                    </div>
                    <p class="help-text">Copy these from <a href="https://console.twilio.com" target="_blank">console.twilio.com</a>. You'll need them in Step 4.</p>
                `
            },
            {
                title: "Step 3 — Activate WhatsApp Sandbox",
                content: `
                    <p>Before sending messages, you must join your own sandbox:</p>
                    <ol style="margin-left: 1.5rem; margin-bottom: 1rem;">
                        <li>Go to <strong>Messaging</strong> → <strong>Try it out</strong> → <strong>Send a WhatsApp message</strong>.</li>
                        <li>Save the sandbox number <strong>(+1 415 523 8886)</strong> as a contact.</li>
                        <li>Send the "join keyword" (e.g., <i>join apple-pie</i>) shown on your Twilio screen to that number.</li>
                        <li>Wait for the confirmation reply from Twilio.</li>
                    </ol>
                `
            },
            {
                title: "Step 4 — Enter your details",
                content: `
                    <div class="form-group">
                        <label>Account SID</label>
                        <input type="text" id="wizSid" placeholder="AC...">
                    </div>
                    <div class="form-group">
                        <label>Auth Token</label>
                        <input type="password" id="wizToken" placeholder="Token">
                    </div>
                    <div class="form-group">
                        <label>WhatsApp Number</label>
                        <input type="text" id="wizPhone" placeholder="+91XXXXXXXXXX">
                    </div>
                `
            },
            {
                title: "Step 5 — You're all set!",
                content: `
                    <p>Everything is configured! Click the button below to send a real test message and verify.</p>
                    <div class="text-center mt-8">
                        <button id="wizTestBtn" class="btn btn-primary">Send Test Message Now</button>
                    </div>
                    <p class="help-text mt-4 text-center">After testing, click "Finish" to save and return to dashboard.</p>
                `
            }
        ];

        const updateWizard = () => {
            const step = steps[currentStep - 1];
            wizardTitle.textContent = step.title;
            wizardBody.innerHTML = step.content;

            // Update button visibility
            prevBtn.style.visibility = (currentStep === 1) ? 'hidden' : 'visible';
            nextBtn.textContent = (currentStep === totalSteps) ? 'Finish' : 'Next';

            // Update dots
            stepDots.innerHTML = '';
            for(let i=1; i<=totalSteps; i++) {
                const dot = document.createElement('div');
                dot.className = `dot ${i === currentStep ? 'active' : ''}`;
                stepDots.appendChild(dot);
            }

            // Persistence for Step 4
            if(currentStep === 4) {
                document.getElementById('wizSid').value = document.getElementById('twilioSid').value;
                document.getElementById('wizToken').value = document.getElementById('twilioToken').value;
                document.getElementById('wizPhone').value = document.getElementById('whatsappPhone').value;
                
                ['wizSid', 'wizToken', 'wizPhone'].forEach(id => {
                    document.getElementById(id).addEventListener('input', () => {
                        const targetId = id === 'wizSid' ? 'twilioSid' : (id === 'wizToken' ? 'twilioToken' : 'whatsappPhone');
                        document.getElementById(targetId).value = document.getElementById(id).value;
                    });
                });
            }

            // Step 5 Test button
            if(currentStep === 5) {
                document.getElementById('wizTestBtn').addEventListener('click', testWhatsapp);
            }
        };

        openBtn.addEventListener('click', () => {
            currentStep = 1;
            updateWizard();
            modal.style.display = 'block';
        });

        closeBtn.addEventListener('click', () => {
            modal.style.display = 'none';
        });

        window.addEventListener('click', (e) => {
            if(e.target === modal) modal.style.display = 'none';
        });

        nextBtn.addEventListener('click', () => {
            if(currentStep < totalSteps) {
                currentStep++;
                updateWizard();
            } else {
                modal.style.display = 'none';
                showToast("Wizard completed! Don't forget to Save Configuration.");
            }
        });

        prevBtn.addEventListener('click', () => {
            if(currentStep > 1) {
                currentStep--;
                updateWizard();
            }
        });

        initDashboard();
    } else {
        checkAuth(); // Kick non-logged in users out if needed, or update nav
    }

    // Dynamically load Gemini AI Hero if on index page
    const aiHeroContainer = document.getElementById('aiHeroContainer');
    if (aiHeroContainer) {
        const loadHero = async () => {
            aiHeroContainer.innerHTML = '<span style="color:var(--text-muted)">Generating AI visual with Gemini 1.5 Flash...</span>';
            try {
                const res = await fetch('/api/generate-hero');
                const svgText = await res.text();
                aiHeroContainer.innerHTML = svgText;
            } catch (e) {
                aiHeroContainer.innerHTML = '<span>Failed to load AI graphic.</span>';
            }
        };

        loadHero();
        const regenBtn = document.getElementById('regenHero');
        if(regenBtn) regenBtn.addEventListener('click', loadHero);
    }
});
